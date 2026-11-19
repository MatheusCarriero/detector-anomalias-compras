/* global document, fetch, AbortController, sessionStorage, crypto */
(() => {
  const contract = 'p4-purchase/1.0';
  const storageKey = `${contract}:submission`;
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const keyPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  let catalog = { suppliers: [], products: [], departments: [] };
  let ready = false, busy = false, blocked = false, confirmed = false;
  let activity = null;
  let draft = null, submission = null;

  function today() {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(new Date());
    return ['year', 'month', 'day'].map(type => parts.find(p => p.type === type).value).join('-');
  }

  // Commercial input rules only; no model features, historical statistics or scores.
  function integer(text, max, min = 0) {
    if (typeof text !== 'string' || !/^\d{1,7}$/.test(text.trim())) return null;
    const value = Number(text.trim());
    return value >= min && value <= max ? value : null;
  }

  function priceInCents(text) {
    if (typeof text !== 'string') return null;
    const parts = /^(\d{1,7})(?:[.,](\d{1,2}))?$/.exec(text.trim());
    if (!parts) return null;
    const cents = Number(parts[1]) * 100 + Number((parts[2] ?? '').padEnd(2, '0'));
    return cents > 0 && cents <= 100_000_000 ? cents : null;
  }

  function validDate(text) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return false;
    const [year, month, day] = text.split('-').map(Number);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1];
  }

  function money(cents) {
    // No multiplication of decimal floating-point prices, rounding or currency conversion.
    return `R$ ${Math.floor(cents / 100).toLocaleString('pt-BR')},${String(cents % 100).padStart(2, '0')}`;
  }

  function validateOperation(raw) {
    const errors = {};
    const supplier = catalog.suppliers.find((entry) => entry.id === raw.supplier);
    const product = catalog.products.find((entry) => entry.id === raw.product);
    const department = catalog.departments.find((entry) => entry.id === raw.department);
    if (!supplier) errors.supplier = 'Selecione um fornecedor do catálogo sintético.';
    if (!product) errors.product = 'Selecione um produto do catálogo sintético.';
    if (!department) errors.department = 'Selecione um departamento da lista.';
    const quantity = integer(raw.quantity, 1_000_000, 1);
    const unitPriceCents = priceInCents(raw['unit-price']);
    const paymentDays = integer(raw['payment-days'], 3650);
    if (quantity === null) errors.quantity = 'Informe uma quantidade inteira de 1 a 1.000.000.';
    if (unitPriceCents === null) errors['unit-price'] = 'Informe um preço de R$ 0,01 a R$ 1.000.000,00, com até duas casas decimais e sem separador de milhar.';
    if (paymentDays === null) errors['payment-days'] = 'Informe um prazo inteiro de 0 a 3.650 dias. Zero representa pagamento à vista.';
    if (!validDate(raw.date) || raw.date > today()) errors.date = 'Informe uma data válida, até hoje em America/Sao_Paulo. Datas retroativas são permitidas.';
    if (Object.keys(errors).length) return { errors, operation: null };
    return {
      errors,
      operation: {
        supplier, product, department, quantity, unitPriceCents, paymentDays,
        date: raw.date, currency: 'BRL', totalCents: quantity * unitPriceCents,
      },
    };
  }

  const form = document.getElementById('purchase-form');
  const names = ['supplier', 'product', 'department', 'quantity', 'unit-price', 'payment-days', 'date'];
  const fields = Object.fromEntries(names.map((name) => [name, document.getElementById(`purchase-${name}`)]));
  const errors = Object.fromEntries(names.map((name) => [name, document.getElementById(`purchase-${name}-error`)]));
  const total = document.getElementById('purchase-total');
  const unit = document.getElementById('purchase-unit');
  const status = document.getElementById('purchase-status');
  const summary = document.getElementById('purchase-summary');
  const values = document.getElementById('purchase-summary-values');
  const prepare = document.getElementById('purchase-prepare');
  const save = document.getElementById('purchase-save');
  const check = document.getElementById('purchase-check');
  const retry = document.getElementById('purchase-retry');
  const fresh = document.getElementById('purchase-new');
  const identity = document.getElementById('purchase-key');
  const receipt = document.getElementById('purchase-receipt');
  const catalogStatus = document.getElementById('purchase-catalog-status');
  const reload = document.getElementById('purchase-catalog-reload');
  const historyLoad = document.getElementById('purchase-history-load');
  const historyMore = document.getElementById('purchase-history-more');
  const historyRows = document.getElementById('purchase-history-rows');
  const historyStatus = document.getElementById('purchase-history-status');
  let historyBusy = false, cursor = null;
  const historyIds = new Set();

  function controls() {
    for (const field of Object.values(fields)) field.disabled = !ready || busy || blocked || !!submission;
    prepare.disabled = !ready || busy || blocked || !!submission;
    save.disabled = !draft || !ready || busy || blocked || !!submission;
    check.disabled = !submission || busy || blocked;
    retry.disabled = !submission || busy || blocked || confirmed;
    fresh.disabled = !confirmed || busy || blocked;
    // Being disabled after confirmation protects idempotency; it is not loading.
    const sending = busy && activity === 'send';
    const checking = busy && activity === 'check';
    save.textContent = sending ? 'Cadastrando...' : confirmed ? 'Compra cadastrada' : submission ? 'Cadastro não confirmado' : 'Cadastrar compra';
    save.setAttribute('aria-busy', String(sending));
    save.setAttribute('data-state', sending ? 'sending' : confirmed ? 'confirmed' : submission ? 'uncertain' : 'idle');
    prepare.textContent = confirmed ? 'Resumo cadastrado' : 'Conferir resumo';
    retry.textContent = sending ? 'Cadastrando...' : 'Repetir mesmo envio';
    retry.setAttribute('aria-busy', String(sending));
    check.textContent = checking ? 'Consultando...' : 'Consultar mesma chave';
    check.setAttribute('aria-busy', String(checking));
    fresh.setAttribute('data-primary', String(!fresh.disabled));
    form.setAttribute('aria-busy', String(busy));
    identity.textContent = submission ? submission.idempotency_key : 'Gerada ao cadastrar; preservada até a confirmação.';
  }
  function message(text, error = false) {
    status.textContent = text;
    status.setAttribute('data-state', error ? 'error' : 'success');
  }
  async function api(path, request) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20_000);
    try {
      const response = await fetch(`/demo/p4/${path}`, {
        method: request ? 'POST' : 'GET', credentials: 'omit', cache: 'no-store', redirect: 'error',
        headers: request ? { 'Content-Type': 'application/json', 'X-P4-Local': contract } : { Accept: 'application/json' },
        ...(request ? { body: JSON.stringify(request) } : {}), signal: controller.signal,
      });
      if (!response.ok) {
        // Never render server/driver messages, even on malformed error bodies.
        const error = new Error('P4_HTTP'); error.status = response.status; throw error;
      }
      const data = await response.json();
      if (!data || data.contract !== contract) throw new Error('P4_RESPONSE');
      return { data, status: response.status };
    } finally { clearTimeout(timer); }
  }
  function decimal(cents) { return `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, '0')}`; }
  function purchaseInput(op) {
    return { supplier_id: op.supplier.id, product_id: op.product.id, department_id: op.department.id,
      quantity: op.quantity, unit_price: decimal(op.unitPriceCents), currency: 'BRL', purchase_date: op.date, payment_days: op.paymentDays };
  }
  function operationFrom(p) {
    if (!p || p.currency !== 'BRL' || typeof p.quantity !== 'number' || typeof p.payment_days !== 'number' || typeof p.unit_price !== 'string') throw new Error('P4_RESPONSE');
    const result = validateOperation({ supplier: p.supplier_id, product: p.product_id, department: p.department_id,
      quantity: String(p.quantity), 'unit-price': p.unit_price, 'payment-days': String(p.payment_days), date: p.purchase_date });
    if (!result.operation || p.unit_price !== decimal(result.operation.unitPriceCents)) throw new Error('P4_RESPONSE');
    return result.operation;
  }
  function validReceipt(r) {
    if (!r || !uuid.test(r.id) || !keyPattern.test(r.idempotency_key) || r.revision_no !== 1 ||
      typeof r.recorded_at !== 'string' || !Number.isFinite(Date.parse(r.recorded_at)) ||
      r.analysis?.status !== 'unavailable' || r.analysis.reason !== 'manual_source_incompatible_with_procurement_v2') throw new Error('P4_RESPONSE');
    const p = r.purchase;
    const op = operationFrom({ ...p, supplier_id: p?.supplier?.id, product_id: p?.product?.id, department_id: p?.department?.id });
    if (p.total !== decimal(op.totalCents) || p.supplier.name !== op.supplier.name || p.product.name !== op.product.name ||
      p.product.unit !== op.product.unit || p.department.name !== op.department.name) throw new Error('P4_RESPONSE');
    return op;
  }
  function confirmedReceipt(r) {
    const op = validReceipt(r);
    if (r.idempotency_key !== submission.idempotency_key ||
      JSON.stringify(purchaseInput(op)) !== JSON.stringify(submission.purchase)) throw new Error('P4_RECEIPT_MISMATCH');
    confirmed = true;
    receipt.textContent = `Compra cadastrada com sucesso. UUID: ${r.id}. Total ${money(op.totalCents)}. Registro em ${new Date(r.recorded_at).toLocaleString('pt-BR')}. Revisão 1. Análise por IA indisponível.`;
    message('Compra cadastrada com sucesso. Para iniciar um novo cadastro, selecione Preparar outra compra. A chave e o recibo desta operação foram preservados.');
  }
  function uncertain(error) {
    const detail = error?.status === 409 ? 'Conflito: a chave está associada a outro conteúdo. Solicite conferência antes de iniciar outra compra.'
      : error?.status === 400 ? 'Dados recusados pela API. Confira o contrato; a chave e os dados enviados foram preservados.'
      : error?.status === 404 ? 'Compra ainda não encontrada. Isso não comprova que um envio anterior foi cancelado.'
      : 'Não foi possível confirmar o cadastro. A API pode estar indisponível ou a resposta pode ter sido interrompida.';
    message(`${detail} Consulte a mesma chave ou repita exatamente o envio. Não abra outra compra para contornar esta pendência.`, true);
  }
  async function send() {
    if (busy || blocked || !submission || confirmed) return;
    activity = 'send'; busy = true; controls(); message('Cadastrando... Aguarde a confirmação.');
    try {
      const { data, status: code } = await api('purchases', submission);
      if (!((code === 201 && data.outcome === 'created') || (code === 200 && data.outcome === 'replay'))) throw new Error('P4_RESPONSE');
      confirmedReceipt(data.purchase);
    } catch (error) { uncertain(error); }
    finally { busy = false; activity = null; controls(); if (confirmed && !fresh.disabled) fresh.focus(); }
  }
  save.addEventListener('click', async () => {
    if (busy || blocked || submission || !draft || !ready) return;
    try {
      const request = { contract, origin: 'manual', idempotency_key: crypto.randomUUID(), purchase: purchaseInput(draft) };
      const encoded = JSON.stringify({ version: 1, request });
      // Durable within this tab BEFORE any POST. Never clear an uncertain submission.
      sessionStorage.setItem(storageKey, encoded);
      if (sessionStorage.getItem(storageKey) !== encoded) throw new Error('P4_STORAGE');
      submission = request;
    } catch {
      blocked = true; controls(); message('Não foi possível preservar a chave nesta aba. Nenhum envio foi realizado. Verifique o armazenamento da sessão antes de recarregar.', true); return;
    }
    await send();
  });
  retry.addEventListener('click', send);
  check.addEventListener('click', async () => {
    if (busy || blocked || !submission) return;
    activity = 'check'; busy = true; controls();
    try { const { data } = await api(`purchases/by-key/${submission.idempotency_key}`); confirmedReceipt(data.purchase); }
    catch (error) { uncertain(error); }
    finally { busy = false; activity = null; controls(); if (confirmed && !fresh.disabled) fresh.focus(); }
  });
  fresh.addEventListener('click', () => {
    if (busy || blocked || !confirmed) return;
    try {
      sessionStorage.removeItem(storageKey);
      if (sessionStorage.getItem(storageKey) !== null) throw new Error('P4_STORAGE');
    } catch { message('Não foi possível encerrar a submissão nesta aba. A chave permanece preservada.', true); return; }
    submission = null; confirmed = false; draft = null; receipt.textContent = '';
    invalidateSummary(); controls(); fields.supplier.focus();
  });

  function clearErrors() {
    for (const name of names) {
      errors[name].textContent = '';
      fields[name].removeAttribute('aria-invalid');
    }
  }

  function updateTotal() {
    const quantity = integer(fields.quantity.value, 1_000_000, 1);
    const cents = priceInCents(fields['unit-price'].value);
    total.textContent = quantity === null || cents === null ? '—' : money(quantity * cents);
    const product = catalog.products.find((entry) => entry.id === fields.product.value);
    unit.textContent = product ? `Unidade: ${product.unit}. Informe quantidades inteiras.` : 'Selecione o produto para conferir a unidade.';
  }

  function invalidateSummary() {
    if (submission || busy || blocked) return;
    draft = null;
    summary.hidden = true;
    values.replaceChildren();
    status.textContent = 'Confira os campos e prepare um novo resumo. Nenhuma análise de risco é executada.';
    status.removeAttribute('data-state');
    clearErrors();
    updateTotal();
    controls();
  }

  form.addEventListener('input', invalidateSummary);
  form.addEventListener('change', invalidateSummary);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!ready || submission || busy || blocked) return;
    clearErrors();
    summary.hidden = true;
    values.replaceChildren();
    updateTotal();
    const raw = Object.fromEntries(names.map((name) => [name, fields[name].value]));
    const result = validateOperation(raw);
    if (!result.operation) {
      for (const [name, message] of Object.entries(result.errors)) {
        errors[name].textContent = message;
        fields[name].setAttribute('aria-invalid', 'true');
      }
      status.textContent = 'Revise os campos indicados. O resumo ainda não foi preparado.';
      status.setAttribute('data-state', 'error');
      fields[Object.keys(result.errors)[0]].focus();
      return;
    }
    draft = result.operation;
    renderSummary(draft);
    message('Resumo conferido localmente. Use Cadastrar compra para persistir no banco sintético. Análise por IA indisponível.');
    controls();
  });
  function renderSummary(operation) {
    values.replaceChildren();
    const entries = [
      ['Fornecedor sintético', operation.supplier.name],
      ['Produto', operation.product.name],
      ['Departamento', operation.department.name],
      ['Quantidade', `${operation.quantity.toLocaleString('pt-BR')} (${operation.product.unit})`],
      ['Preço unitário', money(operation.unitPriceCents)],
      ['Prazo de pagamento', operation.paymentDays === 0 ? 'À vista (0 dias)' : `${operation.paymentDays} dias`],
      ['Data da operação', operation.date.split('-').reverse().join('/')],
      ['Total da compra (BRL)', money(operation.totalCents)],
    ];
    for (const [label, text] of entries) {
      const group = document.createElement('div');
      const term = document.createElement('dt');
      const description = document.createElement('dd');
      term.textContent = label;
      description.textContent = text;
      group.appendChild(term);
      group.appendChild(description);
      values.appendChild(group);
    }
    summary.hidden = false;
  }

  async function loadCatalog() {
    if (reload.disabled) return;
    reload.disabled = true;
    catalogStatus.textContent = 'Carregando catálogo da API local…';
    try {
      const { data } = await api('catalog'); const c = data.catalog;
      if (data.currency !== 'BRL' || c?.version !== 'p4-catalog/1.0' || c.origin !== 'synthetic') throw new Error('P4_CATALOG');
      for (const group of ['suppliers', 'products', 'departments']) {
        if (!Array.isArray(c[group]) || !c[group].length || c[group].length > 100 ||
          new Set(c[group].map(e => e.id)).size !== c[group].length || c[group].some(e =>
            typeof e.id !== 'string' || !/^[a-z0-9-]{1,80}$/.test(e.id) || typeof e.name !== 'string' ||
            !e.name.length || e.name.length > 200 || (group === 'products' && (typeof e.unit !== 'string' || !e.unit.length || e.unit.length > 100)))) throw new Error('P4_CATALOG');
      }
      catalog = c;
      for (const [field, entries] of [['supplier', c.suppliers], ['product', c.products], ['department', c.departments]]) {
        const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = 'Selecione';
        fields[field].replaceChildren(placeholder);
        for (const entry of entries) {
          const option = document.createElement('option'); option.value = entry.id; option.textContent = entry.name;
          fields[field].appendChild(option);
        }
      }
      ready = true;
      catalogStatus.textContent = 'Catálogo sintético carregado da API P4. Moeda BRL.';
      reload.hidden = true;
      // Restoration never sends or retries a purchase automatically.
      const encoded = sessionStorage.getItem(storageKey);
      if (encoded !== null) {
        const stored = JSON.parse(encoded);
        const r = stored?.request;
        if (stored?.version !== 1 || !r || r.contract !== contract || r.origin !== 'manual' ||
          !keyPattern.test(r.idempotency_key) || Object.keys(r).sort().join() !== 'contract,idempotency_key,origin,purchase') throw new Error('P4_STORED');
        const op = operationFrom(r.purchase);
        if (JSON.stringify(r.purchase) !== JSON.stringify(purchaseInput(op))) throw new Error('P4_STORED');
        submission = r;
        const raw = { supplier: op.supplier.id, product: op.product.id, department: op.department.id,
          quantity: String(op.quantity), 'unit-price': decimal(op.unitPriceCents), 'payment-days': String(op.paymentDays), date: op.date };
        for (const name of names) fields[name].value = raw[name];
        renderSummary(op); updateTotal();
        message('Submissão recuperada nesta aba. Consulte a mesma chave para confirmar o resultado antes de continuar.', true);
      }
    } catch {
      if (ready) { blocked = true; message('Não foi possível validar a submissão preservada nesta aba. Nenhum envio será feito; não apague a pendência sem conferência.', true); }
      else catalogStatus.textContent = 'Catálogo indisponível. Verifique se a API local da porta 3002 está iniciada e tente carregar novamente.';
    } finally { reload.disabled = false; controls(); }
  }
  reload.addEventListener('click', loadCatalog);

  async function history(more) {
    if (historyBusy || !ready || (more && !cursor)) return;
    historyBusy = true; historyLoad.disabled = true; historyMore.disabled = true;
    historyStatus.textContent = 'Consultando histórico persistente…';
    try {
      const query = new URLSearchParams({ limit: '20' });
      if (more) { query.set('after_recorded_at', cursor.recorded_at); query.set('after_id', cursor.id); }
      const { data } = await api(`purchases?${query}`);
      if (!Array.isArray(data.items) || data.items.length > 20) throw new Error('P4_RESPONSE');
      const operations = data.items.map(validReceipt);
      if (data.next_cursor !== null) {
        const last = data.items.at(-1);
        if (!last || data.next_cursor?.id !== last.id || data.next_cursor?.recorded_at !== last.recorded_at ||
          (more && data.next_cursor.id === cursor.id && data.next_cursor.recorded_at === cursor.recorded_at)) throw new Error('P4_CURSOR');
      }
      if (!more) { historyRows.replaceChildren(); historyIds.clear(); }
      data.items.forEach((r, i) => {
        if (historyIds.has(r.id)) return;
        const op = operations[i]; const row = document.createElement('tr');
        for (const text of [r.id, op.date.split('-').reverse().join('/'), new Date(r.recorded_at).toLocaleString('pt-BR'),
          op.supplier.name, op.product.name, op.department.name, `${op.quantity} (${op.product.unit})`, money(op.unitPriceCents), money(op.totalCents), 'Indisponível']) {
          const cell = document.createElement('td'); cell.textContent = text; row.appendChild(cell);
        }
        historyRows.appendChild(row); historyIds.add(r.id);
      });
      cursor = data.next_cursor;
      historyStatus.textContent = historyIds.size ? `${historyIds.size} compra(s) exibida(s), por data de registro decrescente. Análise por IA indisponível.` : 'Nenhuma compra cadastrada nesta origem.';
    } catch { historyStatus.textContent = 'Não foi possível consultar esta página do histórico. Os registros já exibidos foram preservados. Tente novamente.'; }
    finally { historyBusy = false; historyLoad.disabled = false; historyMore.disabled = !cursor; }
  }
  historyLoad.addEventListener('click', () => history(false));
  historyMore.addEventListener('click', () => history(true));
  updateTotal();
  controls();
  void loadCatalog();
})();
