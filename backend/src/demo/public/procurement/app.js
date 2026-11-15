(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const base = '/demo/procurement-v2';
  const sourceHash = 'fba22a467e5dd800a0af960930d2ca5e2ecbd9d2bc747e37304867d8d031ae21';
  const features = [
    ['price_to_item_median_90d', 'Preço / mediana histórica do material'],
    ['quantity_to_item_median_90d', 'Quantidade / mediana histórica do material'],
    ['item_price_relative_iqr_90d', 'Dispersão relativa do preço do material'],
    ['supplier_item_lines_90d', 'Compras do fornecedor para o material'],
    ['business_unit_lines_90d', 'Compras da unidade de negócio'],
  ];
  const reasons = {
    insufficient_history: 'Histórico insuficiente: a referência exige pelo menos 20 observações anteriores.',
    zero_denominator: 'A referência é zero e não permite calcular a razão.',
    zero_iqr: 'Dispersão IQR igual a zero; esta referência não permite o cálculo.',
    partial_window: 'A fonte não cobre integralmente a janela histórica.',
    missing_history: 'Histórico não fornecido para esta referência.',
  };
  const errors = {
    PROCUREMENT_MODEL_UNAVAILABLE: 'O modelo local não está disponível. Verifique a preparação do ambiente.',
    PROCUREMENT_MODEL_INTEGRITY: 'A integridade do modelo não foi confirmada. A análise foi bloqueada.',
    PROCUREMENT_MODEL_INCOMPATIBLE: 'O modelo ou o ambiente é incompatível. A análise foi bloqueada.',
    PROCUREMENT_MODEL_LOAD_FAILED: 'Não foi possível carregar o modelo com segurança.',
    PROCUREMENT_TIMEOUT: 'A execução excedeu o tempo permitido. Aguarde antes de tentar novamente.',
    PROCUREMENT_BUSY: 'O demonstrador já está executando uma operação. Aguarde e tente novamente.',
    PROCUREMENT_INVALID_REQUEST: 'A requisição foi rejeitada. Consulte novamente o catálogo.',
    PROCUREMENT_SOURCE_UNAVAILABLE: 'A fonte sintética local não está disponível.',
    PROCUREMENT_SOURCE_HASH: 'A integridade da fonte não foi confirmada. A consulta foi bloqueada.',
    PROCUREMENT_EXECUTOR_UNAVAILABLE: 'O executor Python não está disponível neste ambiente.',
    PROCUREMENT_INVALID_RESPONSE: 'O servidor retornou uma resposta incompatível. Nenhum resultado foi exibido.',
  };
  const invalid = () => { throw new Error('INVALID_RESPONSE'); };
  const object = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
  const string = (v) => typeof v === 'string' && v.length > 0 && v.length <= 1000;
  const finite = (v) => typeof v === 'number' && Number.isFinite(v);
  const count = (v) => Number.isSafeInteger(v) && v >= 0;
  const hash = (v) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
  const sameOperation = (a, b) => object(a) && object(b) &&
    a.po_id === b.po_id && a.order_date === b.order_date && a.occurrence === b.occurrence;
  const date = (v) => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v);
  let catalog = null;
  let selected = null;
  let prepared = null;
  let revision = 0;
  let busy = false;

  function sourceValid(s) {
    return object(s) && s.source_id === 'procurement-spend' && s.source_version === sourceHash &&
      s.origin === 'synthetic' && s.entity_namespace === 'procurement-spend-synthetic' &&
      s.monetary_unit === 'unspecified_source_unit' && s.temporal_assumption === 'available_at_order_no_revisions';
  }
  function contextValid(c) {
    return object(c) && ['supplier_id', 'supplier_name', 'supplier_country', 'category', 'item', 'business_unit'].every(k => string(c[k])) &&
      ['unit_price', 'line_total'].every(k => typeof c[k] === 'string' && /^\d+(\.\d+)?$/.test(c[k]) && c[k].length <= 50) &&
      Number.isSafeInteger(c.quantity) && c.quantity > 0;
  }
  function catalogValid(c) {
    if (!object(c) || c.contract !== 'procurement-demo/1.0' || !sourceValid(c.source) || !Array.isArray(c.operations) || c.operations.length !== 7) return false;
    const keys = new Set();
    return c.operations.every(entry => {
      if (!object(entry) || !object(entry.operation) || !contextValid(entry.context)) return false;
      const op = entry.operation;
      if (!string(op.po_id) || !date(op.order_date) || !Number.isSafeInteger(op.occurrence) || op.occurrence < 1) return false;
      const key = JSON.stringify([op.po_id, op.order_date, op.occurrence]);
      if (keys.has(key)) return false;
      keys.add(key); return true;
    });
  }
  // Presentation guards only. Scientific validation and feature calculations stay in Python.
  function preparationValid(p, entry) {
    if (!object(p) || p.contract !== catalog.contract || !sourceValid(p.source) || !sameOperation(p.operation, entry.operation) ||
      !contextValid(p.context) || !Object.keys(entry.context).every(k => p.context[k] === entry.context[k]) ||
      p.feature_contract !== 'procurement-temporal-features/1.0' || p.matrix_contract !== 'procurement-experimental-matrix/1.0' ||
      p.cutoff_date !== entry.operation.order_date || !object(p.window) || !date(p.window.start) || p.window.end !== p.cutoff_date || p.window.end_exclusive !== true ||
      !object(p.support) || !['window', 'item', 'supplier', 'supplier_item', 'business_unit'].every(k => count(p.support[k])) ||
      !Array.isArray(p.feature_names) || p.feature_names.length !== 5 || !features.every(([name], i) => p.feature_names[i] === name) ||
      !object(p.unavailability) || !object(p.diagnostics) || !object(p.diagnostics.features) || !object(p.diagnostics.references)) return false;
    const refs = p.diagnostics.references;
    if (!object(refs.item) || !object(refs.supplier_item) ||
      ![refs.item.unit_price, refs.item.quantity, refs.item.line_total, refs.supplier_item.unit_price].every(s =>
        s === null || object(s) && ['median', 'iqr', 'mad'].every(k => finite(s[k])))) return false;
    if (p.status === 'eligible') return Array.isArray(p.values) && p.values.length === 5 && p.values.every(finite) &&
      features.every(([name], i) => p.diagnostics.features[name] === p.values[i]) && Object.keys(p.unavailability).length === 0;
    return p.status === 'unavailable' && p.values === null && Object.keys(p.unavailability).length > 0 &&
      Object.entries(p.unavailability).every(([name, reason]) => features.some(f => f[0] === name) && Object.hasOwn(reasons, reason)) &&
      features.every(([name]) => p.diagnostics.features[name] === null ? Object.hasOwn(p.unavailability, name) : finite(p.diagnostics.features[name]));
  }
  function runValid(r, entry) {
    if (!object(r) || r.contract !== 'procurement-demo-inference/1.0' || r.score_convention !== '-score_samples' ||
      r.score_semantics !== 'statistical_anomaly' || r.score_direction !== 'higher_is_more_anomalous' || !preparationValid(r.preparation, entry)) return false;
    if (r.status === 'unavailable') return r.preparation.status === 'unavailable' && r.anomaly_score === null && r.model === null;
    return r.status === 'scored' && r.preparation.status === 'eligible' && finite(r.anomaly_score) && object(r.model) &&
      r.model.domain === 'procurement_v2' && string(r.model.artifact_id) && hash(r.model.model_sha256) && hash(r.model.metadata_sha256);
  }
  function node(tag, value, className) {
    const e = document.createElement(tag);
    if (value !== undefined) e.textContent = String(value);
    if (className) e.className = className;
    return e;
  }
  function definitionList(id, entries) {
    $(id).replaceChildren(...entries.map(([label, value]) => {
      const group = node('div'); group.append(node('dt', label), node('dd', value)); return group;
    }));
  }
  function status(id, message, kind = '') { $(id).textContent = message; $(id).setAttribute('data-state', kind); }
  function controls() {
    $('prepare-button').disabled = busy || !selected;
    $('analyze-button').disabled = busy || prepared?.status !== 'eligible';
    $('catalog-retry').disabled = busy;
    $('catalog-retry').hidden = catalog !== null;
    $('catalog-panel').setAttribute('aria-busy', String(busy && !catalog));
    $('analysis-panel').setAttribute('aria-busy', String(busy && !!catalog));
  }
  function clearScore() {
    $('scored-result').hidden = true; $('result-empty').hidden = false;
    $('anomaly-score').textContent = ''; $('result-operation').textContent = '';
    $('provenance-values').replaceChildren();
  }
  function clearPreparation() {
    prepared = null; clearScore(); $('history-content').hidden = true; $('unavailable-note').hidden = true;
    $('feature-rows').replaceChildren(); $('reference-rows').replaceChildren(); $('history-support').replaceChildren();
    $('unavailable-reasons').replaceChildren(); $('history-window').textContent = ''; $('preparation-badge').textContent = 'Não consultado';
    $('preparation-badge').setAttribute('data-state', '');
  }
  function select(entry) {
    selected = entry; revision++; clearPreparation();
    $('selection-empty').hidden = true; $('operation-details').hidden = false;
    const c = entry.context; const op = entry.operation;
    $('operation-product').textContent = c.item;
    $('operation-identity').textContent = `${op.po_id} · ${op.order_date} · ocorrência ${op.occurrence}`;
    definitionList('commercial-values', [
      ['Fornecedor', `${c.supplier_name} (${c.supplier_id})`], ['País do fornecedor', c.supplier_country],
      ['Categoria', c.category], ['Unidade de negócio', c.business_unit], ['Quantidade', c.quantity],
      ['Preço unitário · unidade da fonte', c.unit_price], ['Valor total · unidade da fonte', c.line_total],
    ]);
    catalog.operations.forEach((opEntry, i) => $('operation-list').children[i].setAttribute('aria-pressed', String(opEntry === entry)));
    status('action-status', busy ? 'Seleção alterada. Aguarde a requisição em andamento; o resultado anterior será descartado.' : 'Consulte o histórico desta operação para habilitar a análise.');
    controls();
  }
  async function request(path, payload) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 35_000);
    try {
      const response = await fetch(`${base}/${path}`, {
        method: payload ? 'POST' : 'GET', cache: 'no-store', credentials: 'omit', signal: controller.signal,
        ...(payload ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) } : {}),
      });
      if (!response.ok) {
        let code;
        try { const body = await response.json(); if (object(body) && Object.hasOwn(errors, body.message)) code = body.message; } catch { /* Only predefined codes may reach the UI. */ }
        throw new Error(code || ({ 400: 'PROCUREMENT_INVALID_REQUEST', 409: 'PROCUREMENT_BUSY', 504: 'PROCUREMENT_TIMEOUT' }[response.status]) || 'TECHNICAL');
      }
      try { return await response.json(); } catch { invalid(); }
    } catch (error) {
      if (controller.signal.aborted) throw new Error('PROCUREMENT_TIMEOUT');
      if (error instanceof Error && (Object.hasOwn(errors, error.message) || ['INVALID_RESPONSE', 'TECHNICAL'].includes(error.message))) throw error;
      throw new Error('NETWORK');
    } finally { clearTimeout(timer); }
  }
  function errorText(error) {
    if (Object.hasOwn(errors, error.message)) return errors[error.message];
    if (error.message === 'INVALID_RESPONSE') return errors.PROCUREMENT_INVALID_RESPONSE;
    if (error.message === 'NETWORK') return 'Não foi possível comunicar com o servidor local. Verifique se ele está em execução e tente novamente.';
    return 'A execução não pôde ser concluída. Verifique o ambiente local antes de tentar novamente.';
  }
  async function loadCatalog() {
    if (busy) return;
    busy = true; controls(); status('catalog-status', 'Carregando catálogo…', 'loading');
    try {
      const result = await request('operations'); if (!catalogValid(result)) invalid(); catalog = result;
      $('operation-list').replaceChildren(...catalog.operations.map(entry => {
        const button = node('button', undefined, 'operation'); button.setAttribute('type', 'button'); button.setAttribute('aria-pressed', 'false');
        button.append(node('span', entry.operation.po_id, 'op-id'), node('strong', entry.context.item, 'op-item'),
          node('span', `${entry.context.supplier_id} · ${entry.context.business_unit}`, 'op-context'), node('span', entry.operation.order_date, 'op-date'));
        button.addEventListener('click', () => select(entry)); return button;
      }));
      $('catalog-count').textContent = String(catalog.operations.length); status('catalog-status', 'Catálogo disponível. Selecione uma operação.', 'success');
    } catch (error) { status('catalog-status', errorText(error), 'error'); }
    finally { busy = false; controls(); }
  }
  function renderPreparation(p) {
    prepared = p; $('history-content').hidden = false;
    $('preparation-badge').textContent = p.status === 'eligible' ? 'Elegível para análise' : 'Indisponível';
    $('preparation-badge').setAttribute('data-state', p.status);
    $('history-window').textContent = `[${p.window.start}, ${p.window.end}) · início incluído, data da compra excluída.`;
    definitionList('history-support', [['Compras na janela', p.support.window], ['Do material', p.support.item],
      ['Do fornecedor', p.support.supplier], ['Fornecedor + material', p.support.supplier_item], ['Da unidade', p.support.business_unit]]);
    $('unavailable-note').hidden = p.status !== 'unavailable';
    $('unavailable-reasons').replaceChildren(...Object.entries(p.unavailability).map(([name, reason]) =>
      node('li', `${features.find(f => f[0] === name)[1]}: ${reasons[reason]}`)));
    $('feature-rows').replaceChildren(...features.map(([name, label], i) => {
      const row = node('tr'); const heading = node('th'); heading.setAttribute('scope', 'row');
      heading.append(node('span', label), node('code', name));
      const value = p.status === 'eligible' ? p.values[i] : p.diagnostics.features[name];
      row.append(heading, node('td', value === null ? 'Indisponível' : value)); return row;
    }));
    const r = p.diagnostics.references;
    $('reference-rows').replaceChildren(...[
      ['Preço do material', r.item.unit_price], ['Quantidade do material', r.item.quantity],
      ['Total do material', r.item.line_total], ['Preço fornecedor + material', r.supplier_item.unit_price],
    ].map(([label, stats]) => { const row = node('tr'); row.append(node('th', label), ...['median', 'iqr', 'mad'].map(k => node('td', stats === null ? 'Indisponível' : stats[k]))); return row; }));
    status('action-status', p.status === 'eligible' ? 'Histórico consultado. A operação está elegível; a inferência só ocorrerá ao clicar em “Analisar com IA”.' : 'Histórico indisponível para a análise. Nenhum score foi calculado.', p.status === 'eligible' ? 'success' : 'unavailable');
  }
  function renderScore(r) {
    $('scored-result').hidden = false; $('result-empty').hidden = true;
    $('anomaly-score').textContent = String(r.anomaly_score);
    const p = r.preparation;
    $('result-operation').textContent = `${p.operation.po_id} · ${p.operation.order_date} · ocorrência ${p.operation.occurrence} · ${p.context.item} · ${p.context.supplier_name} (${p.context.supplier_id})`;
    definitionList('provenance-values', [['Artefato', r.model.artifact_id], ['Domínio', r.model.domain],
      ['SHA-256 do modelo', r.model.model_sha256], ['SHA-256 da metadata', r.model.metadata_sha256],
      ['Fonte', p.source.source_id], ['SHA-256 da fonte', p.source.source_version], ['Origem', 'Sintética'],
      ['Moeda', 'Não identificada'], ['Contrato da resposta', r.contract], ['Contrato de features', p.feature_contract],
      ['Hipótese temporal da fonte', p.source.temporal_assumption]]);
    status('action-status', 'Análise concluída. O resultado descreve atipicidade estatística desta operação.', 'success');
  }
  async function action(kind) {
    if (busy || !selected || kind === 'runs' && prepared?.status !== 'eligible') return;
    const entry = selected; const token = revision;
    if (kind === 'prepare') clearPreparation(); else clearScore();
    busy = true; controls(); status('action-status', kind === 'prepare' ? 'Consultando o histórico temporal…' : 'Executando a análise com o modelo local…', 'loading');
    try {
      const result = await request(kind, { contract: catalog.contract, source_sha256: catalog.source.source_version, operation: { ...entry.operation } });
      if (token !== revision) return;
      if (kind === 'prepare') { if (!preparationValid(result, entry)) invalid(); renderPreparation(result); }
      else {
        if (!runValid(result, entry)) invalid(); renderPreparation(result.preparation);
        if (result.status === 'scored') renderScore(result);
      }
    } catch (error) { if (token === revision) status('action-status', errorText(error), 'error'); }
    finally {
      busy = false; controls();
      if (token !== revision) status('action-status', 'Seleção atualizada. Consulte o histórico da operação selecionada.');
    }
  }
  clearPreparation(); $('operation-details').hidden = true; controls();
  $('catalog-retry').addEventListener('click', loadCatalog);
  $('prepare-button').addEventListener('click', () => action('prepare'));
  $('analyze-button').addEventListener('click', () => action('runs'));
  void loadCatalog();
})();
