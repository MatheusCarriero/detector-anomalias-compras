// Transport boundary for the fixed P0 demonstration, not scientific validation.
export const MODEL_SHA256 = 'c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b';

export interface InvoiceDemoRow {
  id: string;
  score: number;
  rank: number;
}

export interface InvoiceDemoResponse {
  contract: 'invoice-demo/1.0';
  origin: 'synthetic';
  source_reconciled: false;
  model_sha256: typeof MODEL_SHA256;
  score_kind: 'negative_score_samples';
  score_direction: 'higher_is_more_anomalous';
  rows: InvoiceDemoRow[];
}

function hasKeys(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const actual = Object.keys(value);
  return actual.length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

function invalid(): never {
  throw new Error('DEMO_INVALID_RESPONSE');
}

export function parseInvoiceDemoResponse(output: string): InvoiceDemoResponse {
  let value: unknown;
  try {
    value = JSON.parse(output) as unknown;
  } catch {
    invalid();
  }
  if (!hasKeys(value, ['contract', 'origin', 'source_reconciled', 'model_sha256',
    'score_kind', 'score_direction', 'rows'])) invalid();
  if (value.contract !== 'invoice-demo/1.0' || value.origin !== 'synthetic'
    || value.source_reconciled !== false || value.model_sha256 !== MODEL_SHA256
    || value.score_kind !== 'negative_score_samples'
    || value.score_direction !== 'higher_is_more_anomalous'
    || !Array.isArray(value.rows) || value.rows.length !== 3) invalid();

  const expected = new Set(['demo-001', 'demo-002', 'demo-003']);
  const rows: InvoiceDemoRow[] = [];
  for (const [index, row] of value.rows.entries()) {
    if (!hasKeys(row, ['id', 'score', 'rank']) || typeof row.id !== 'string'
      || !expected.delete(row.id) || typeof row.score !== 'number'
      || !Number.isFinite(row.score) || row.rank !== index + 1) invalid();
    const previous = rows.at(-1);
    if (previous && (previous.score < row.score
      || (previous.score === row.score && previous.id > row.id))) invalid();
    rows.push({ id: row.id, score: row.score, rank: index + 1 });
  }
  return {
    contract: 'invoice-demo/1.0', origin: 'synthetic', source_reconciled: false,
    model_sha256: MODEL_SHA256, score_kind: 'negative_score_samples',
    score_direction: 'higher_is_more_anomalous', rows,
  };
}
