/* global document */
(() => {
  // Fictional display catalog: not the academic Supplier/Purchase datasets.
  const catalog = {
    suppliers: [
      { id: 'sup-obra', name: 'Obra Exemplo — materiais de construção' },
      { id: 'sup-base', name: 'Base Exemplo — suprimentos' },
      { id: 'sup-estrutura', name: 'Estrutura Exemplo — materiais' },
    ],
    products: [
      { id: 'prod-cimento', name: 'Cimento CP II · saco de 50 kg', unit: 'saco de 50 kg' },
      { id: 'prod-tijolo', name: 'Tijolo cerâmico · unidade', unit: 'unidade' },
      { id: 'prod-vergalhao', name: 'Vergalhão de aço · barra de 12 m', unit: 'barra de 12 m' },
      { id: 'prod-argamassa', name: 'Argamassa · saco de 20 kg', unit: 'saco de 20 kg' },
      { id: 'prod-tubo', name: 'Tubo PVC · barra de 6 m', unit: 'barra de 6 m' },
    ],
    departments: [
      { id: 'dep-obras', name: 'Obras' },
      { id: 'dep-manutencao', name: 'Manutenção' },
      { id: 'dep-almoxarifado', name: 'Almoxarifado' },
    ],
  };

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
    if (!validDate(raw.date)) errors.date = 'Informe uma data válida, com dia, mês e ano.';
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

  for (const [field, entries] of [
    ['supplier', catalog.suppliers], ['product', catalog.products], ['department', catalog.departments],
  ]) {
    for (const entry of entries) {
      const option = document.createElement('option');
      option.value = entry.id;
      option.textContent = entry.name;
      fields[field].appendChild(option);
    }
  }

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
    summary.hidden = true;
    values.replaceChildren();
    status.textContent = 'Confira os campos e prepare um novo resumo. Nenhuma análise de risco é executada.';
    status.removeAttribute('data-state');
    clearErrors();
    updateTotal();
  }

  form.addEventListener('input', invalidateSummary);
  form.addEventListener('change', invalidateSummary);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
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
    const operation = result.operation;
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
    status.textContent = 'Resumo preparado somente nesta página. Nenhum score ou avaliação de risco foi calculado.';
    status.setAttribute('data-state', 'success');
  });
  updateTotal();
  document.getElementById('purchase-prepare').disabled = false;
})();
