import { MODEL_SHA256, parseInvoiceDemoResponse } from './invoice-demo-response.js';

// Invented transport values, not scores from the scientific model or dataset.
function fixture(): Record<string, unknown> {
  return {
    contract: 'invoice-demo/1.0', origin: 'synthetic', source_reconciled: false,
    model_sha256: MODEL_SHA256, score_kind: 'negative_score_samples',
    score_direction: 'higher_is_more_anomalous',
    rows: [
      { id: 'demo-002', score: 0.8, rank: 1 },
      { id: 'demo-001', score: 0.2, rank: 2 },
      { id: 'demo-003', score: 0.2, rank: 3 },
    ],
  };
}

function rows(value: Record<string, unknown>) {
  return value.rows as Record<string, unknown>[];
}

describe('parseInvoiceDemoResponse', () => {
  it('accepts the exact contract and preserves scores and ID association', () => {
    const expected = fixture();
    expect(parseInvoiceDemoResponse(JSON.stringify(expected))).toEqual(expected);
    expect(MODEL_SHA256).toBe('c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b');
  });

  it('accepts finite zero and negative scores without assuming probabilities', () => {
    const value = fixture();
    rows(value)[0].score = 0;
    rows(value)[1].score = -2;
    rows(value)[2].score = -2;
    expect(parseInvoiceDemoResponse(JSON.stringify(value))).toEqual(value);
  });

  it.each(['null', '[]', '1', 'true', '"text"', '{', 'private output', '{}\n{}'])(
    'rejects malformed JSON or a non-object: %s', (raw) => {
      expect(() => parseInvoiceDemoResponse(raw)).toThrowError(/^DEMO_INVALID_RESPONSE$/);
    },
  );

  it.each([
    ['contract', 'other/1.0'], ['origin', 'test'], ['source_reconciled', true],
    ['source_reconciled', 'false'], ['model_sha256', 'a'.repeat(64)],
    ['model_sha256', MODEL_SHA256.toUpperCase()], ['score_kind', 'fraud_probability'],
    ['score_direction', 'lower_is_more_anomalous'], ['rows', null], ['rows', {}], ['rows', []],
  ])('rejects incompatible %s', (key, replacement) => {
    const value = fixture();
    value[key as string] = replacement;
    expect(() => parseInvoiceDemoResponse(JSON.stringify(value))).toThrowError(/^DEMO_INVALID_RESPONSE$/);
  });

  it('rejects missing or extra top-level properties', () => {
    for (const key of Object.keys(fixture())) {
      const value = fixture();
      delete value[key];
      expect(() => parseInvoiceDemoResponse(JSON.stringify(value))).toThrowError(/^DEMO_INVALID_RESPONSE$/);
    }
    expect(() => parseInvoiceDemoResponse(JSON.stringify({ ...fixture(), probability: 0.9 })))
      .toThrowError(/^DEMO_INVALID_RESPONSE$/);
  });

  it('rejects missing, extra, unknown or duplicate IDs', () => {
    const variants = [fixture(), fixture(), fixture(), fixture()];
    rows(variants[0]).pop();
    rows(variants[1]).push({ id: 'demo-004', score: 0.1, rank: 4 });
    rows(variants[2])[0].id = 'demo-004';
    rows(variants[3])[0].id = 'demo-001';
    for (const value of variants) {
      expect(() => parseInvoiceDemoResponse(JSON.stringify(value))).toThrowError(/^DEMO_INVALID_RESPONSE$/);
    }
  });

  it('rejects malformed row objects and their extra or missing fields', () => {
    for (const row of [null, [], {}, 'row', { id: 'demo-002', score: 0.8 },
      { id: 'demo-002', score: 0.8, rank: 1, label: 1 }]) {
      const value = fixture();
      value.rows = [row, ...rows(value).slice(1)];
      expect(() => parseInvoiceDemoResponse(JSON.stringify(value))).toThrowError(/^DEMO_INVALID_RESPONSE$/);
    }
  });

  it.each([null, true, '0.8', [], {}])('rejects nonnumeric scores: %j', (score) => {
    const value = fixture();
    rows(value)[0].score = score;
    expect(() => parseInvoiceDemoResponse(JSON.stringify(value))).toThrowError(/^DEMO_INVALID_RESPONSE$/);
  });

  it('rejects nonfinite numbers parsed from JSON exponent notation', () => {
    const raw = JSON.stringify(fixture()).replace('"score":0.8', '"score":1e400');
    expect(() => parseInvoiceDemoResponse(raw)).toThrowError(/^DEMO_INVALID_RESPONSE$/);
  });

  it.each([0, 2, 1.5, true, '1', null])('rejects incompatible rank: %j', (rank) => {
    const value = fixture();
    rows(value)[0].rank = rank;
    expect(() => parseInvoiceDemoResponse(JSON.stringify(value))).toThrowError(/^DEMO_INVALID_RESPONSE$/);
  });

  it('rejects scores out of order and incorrect ID tie-breaking', () => {
    const wrongScore = fixture();
    rows(wrongScore)[1].score = 0.9;
    const wrongTie = fixture();
    rows(wrongTie)[1].id = 'demo-003';
    rows(wrongTie)[2].id = 'demo-001';
    for (const value of [wrongScore, wrongTie]) {
      expect(() => parseInvoiceDemoResponse(JSON.stringify(value))).toThrowError(/^DEMO_INVALID_RESPONSE$/);
    }
  });
});
