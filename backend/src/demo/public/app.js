/* global document, fetch, AbortController */
(() => {
  const button = document.getElementById('run-button');
  const status = document.getElementById('run-status');
  const panel = document.getElementById('results-panel');
  const empty = document.getElementById('empty-state');
  const ranking = document.getElementById('ranking-container');
  const rows = document.getElementById('ranking-rows');
  const details = document.getElementById('result-details');
  const model = document.getElementById('model-hash');
  const time = document.getElementById('execution-time');
  let pending = false;

  // Display guard only. The backend and Python remain the contract authorities.
  function validResponse(value) {
    if (!value || value.contract !== 'invoice-demo/1.0' || value.origin !== 'synthetic'
      || value.source_reconciled !== false || value.score_kind !== 'negative_score_samples'
      || value.score_direction !== 'higher_is_more_anomalous'
      || typeof value.model_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(value.model_sha256)
      || !Array.isArray(value.rows) || value.rows.length !== 3) return false;
    const ids = new Set(['demo-001', 'demo-002', 'demo-003']);
    return value.rows.every((row, index) => {
      if (!row || !ids.delete(row.id) || row.rank !== index + 1
        || typeof row.score !== 'number' || !Number.isFinite(row.score)) return false;
      const previous = value.rows[index - 1];
      return !previous || previous.score > row.score
        || (previous.score === row.score && previous.id < row.id);
    });
  }

  function render(value) {
    const rendered = value.rows.map((row) => {
      const tr = document.createElement('tr');
      // Scores are displayed as supplied, with no percentage or rescaling.
      for (const text of [String(row.rank), row.id, String(row.score)]) {
        const cell = document.createElement('td');
        cell.textContent = text;
        tr.appendChild(cell);
      }
      return tr;
    });
    rows.replaceChildren(...rendered);
    model.textContent = value.model_sha256;
    const receivedAt = new Date();
    time.textContent = receivedAt.toLocaleString('pt-BR', { timeZoneName: 'short' });
    time.setAttribute('datetime', receivedAt.toISOString());
    ranking.hidden = false;
    details.hidden = false;
    empty.hidden = true;
  }

  const messages = {
    400: 'A solicitação foi recusada. Esta demonstração usa apenas o lote sintético fixo.',
    409: 'Já existe uma análise em execução. Aguarde antes de tentar novamente.',
    502: 'Não foi possível obter um resultado válido do executor. Confira o ambiente local.',
    503: 'O executor está indisponível. Confira o ambiente Python e tente novamente depois.',
    504: 'A análise excedeu o tempo permitido. Nenhuma nova tentativa foi iniciada.',
  };

  button.disabled = false;
  button.addEventListener('click', async () => {
    if (pending) return;
    pending = true;
    button.disabled = true;
    button.textContent = 'Analisando…';
    panel.setAttribute('aria-busy', 'true');
    status.textContent = 'Analisando as três faturas sintéticas. Aguarde…';
    status.setAttribute('data-state', 'loading');
    rows.replaceChildren();
    ranking.hidden = true;
    details.hidden = true;
    model.textContent = '';
    time.textContent = '';
    time.removeAttribute('datetime');
    empty.hidden = false;
    empty.textContent = 'O ranking será exibido quando esta análise terminar.';

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 35_000);
    let readingResponse = false;
    try {
      const response = await fetch('/demo/invoice-runs', {
        method: 'POST', cache: 'no-store', credentials: 'omit', signal: controller.signal,
      });
      if (!response.ok) {
        status.textContent = messages[response.status]
          || 'Não foi possível concluir a análise. Confira o servidor local.';
        status.setAttribute('data-state', 'error');
        return;
      }
      readingResponse = true;
      const value = await response.json();
      if (!validResponse(value)) throw new Error('INVALID_RESPONSE');
      render(value);
      status.textContent = 'Análise concluída. Ranking do lote sintético disponível abaixo.';
      status.setAttribute('data-state', 'success');
    } catch {
      status.textContent = controller.signal.aborted
        ? 'O tempo de espera terminou. O servidor pode ainda estar encerrando a análise; aguarde antes de tentar novamente.'
        : readingResponse
          ? 'A resposta recebida é inválida. Nenhum ranking foi exibido.'
          : 'Não foi possível contatar o servidor local. Verifique se ele está em execução.';
      status.setAttribute('data-state', 'error');
    } finally {
      clearTimeout(timeout);
      pending = false;
      button.disabled = false;
      button.textContent = 'Executar análise';
      panel.setAttribute('aria-busy', 'false');
      if (ranking.hidden) empty.textContent = 'Sem resultado nesta tentativa. Consulte a mensagem acima.';
    }
  });
})();
