import { analyzePrice } from './price-analysis.js';

// Hand-checked examples, independent of the experimental fixture builder.
function row(id = 'candidate') {
  return { id, productId: 'prod-cimento', specificationId: 'exp-cimento-1',
    unit: 'saco', packaging: '50 kg', currency: 'BRL', priceBasis: 'experimental-net-tax-included-no-freight/1',
    supplierId: 'experimental-supplier-a', departmentId: 'experimental-department-a',
    quantity: 10, unitPrice: '10.00', purchaseDate: '2026-04-01', availableAt: '2026-04-01T12:00:00.000Z',
    paymentDays: 30, deliveryZone: 'experimental-site-a', quantityPricing: 'independent-by-experiment' };
}
function input(n = 20) {
  return { contract: 'p4-price-analysis/1.0', origin: 'synthetic-experiment',
    analysisAt: '2026-04-01T15:00:00.000Z', operation: row(),
    history: { coverage: { startDate: '2026-01-01', endDate: '2026-03-31', complete: true },
      rows: Array.from({ length: n }, (_, i) => ({ ...row(`history-${i}`),
        purchaseDate: `2026-03-${String(i % 20 + 1).padStart(2, '0')}`, availableAt: '2026-03-31T12:00:00.000Z' })) } };
}

describe('P4 experimental price analysis (pure/offline)', () => {
  it.each([[19, 'unavailable'], [20, 'available']])('requires twenty comparable references (%i)', (n, status) => {
    expect(analyzePrice(input(Number(n)))).toMatchObject({ status, ...(Number(n) < 20 ? { reason: 'insufficient_history' } : {}) });
  });
  it.each([
    ['10.00', '0', '1', '0.000000'], ['12.50', '25', '1', '25.000000'], ['7.50', '-25', '1', '-25.000000'],
  ])('reports exact signed deviation for %s', (price, numerator, denominator, display) => {
    const value = input(); value.operation.unitPrice = price;
    expect(analyzePrice(value)).toMatchObject({ status: 'available', medianUnitPrice: '10.000',
      percentDifference: { numerator, denominator, display, decimalPlaces: 6, rounding: 'half-away-from-zero' },
      constantReferencePrice: true, context: { support: { references: 20, dates: 20, suppliers: 1 } } });
  });
  it('retains a half-cent median and recurring percentage as an exact fraction', () => {
    const value = input(); value.history.rows.forEach((r, i) => { r.unitPrice = i < 10 ? '10.00' : '10.01'; });
    expect(analyzePrice(value)).toMatchObject({ status: 'available', medianUnitPrice: '10.005',
      percentDifference: { numerator: '-100', denominator: '2001', display: '-0.049975' }, constantReferencePrice: false });
  });
  it('uses the middle value for odd counts rather than averaging all prices', () => {
    const value = input(21);
    value.history.rows.forEach((r, i) => { r.unitPrice = i < 10 ? '1.00' : i === 10 ? '10.00' : '900.00'; });
    expect(analyzePrice(value)).toMatchObject({ medianUnitPrice: '10.000' });
  });
  it.each([
    ['productId', 'prod-tubo'], ['specificationId', 'other-spec'], ['unit', 'kg'],
    ['packaging', '25 kg'], ['currency', 'USD'], ['priceBasis', 'gross-with-freight'],
    ['paymentDays', 60], ['deliveryZone', 'other-site'], ['quantityPricing', 'same-quantity-only'],
  ])('excludes incompatible historical %s without widening the group', (key, changed) => {
    const value = input(21); Object.assign(value.history.rows[0], { [key]: changed });
    expect(analyzePrice(value)).toMatchObject({ status: 'available', context: {
      support: { references: 20 }, excluded: { incomparable: 1 } } });
  });
  it('allows quantity differences only under an explicit quantity-independent experiment', () => {
    const value = input(); value.history.rows.forEach((r, i) => { r.quantity = i + 1; });
    expect(analyzePrice(value)).toMatchObject({ status: 'available' });
    value.operation.quantityPricing = 'same-quantity-only';
    value.history.rows.forEach(r => { r.quantityPricing = 'same-quantity-only'; });
    expect(analyzePrice(value)).toMatchObject({ status: 'unavailable', reason: 'insufficient_history' });
  });
  it('accepts equal quantities under same-quantity-only with different suppliers and departments', () => {
    const value = input(); value.operation.quantityPricing = 'same-quantity-only';
    value.history.rows.forEach((r, i) => {
      r.quantityPricing = 'same-quantity-only'; r.supplierId = `supplier-${i % 3}`; r.departmentId = `department-${i % 2}`;
    });
    expect(analyzePrice(value)).toMatchObject({ status: 'available', context: { quantity: 10, support: { suppliers: 3 } } });
  });
  it('includes day -90 and excludes day -91, current day and future', () => {
    const value = input(19);
    value.history.rows.push({ ...row('boundary'), purchaseDate: '2026-01-01', availableAt: '2026-01-01T12:00:00.000Z' },
      { ...row('too-old'), purchaseDate: '2025-12-31' }, row('same-day'), { ...row('future'), purchaseDate: '2026-04-02' });
    expect(analyzePrice(value)).toMatchObject({ status: 'available', context: {
      window: { startDate: '2026-01-01', endExclusive: '2026-04-01', days: 90 },
      support: { references: 20 }, excluded: { outside_window: 3 } } });
  });
  it('excludes own ID even with an older commercial date', () => {
    const value = input(21); value.history.rows[0].id = 'candidate';
    expect(analyzePrice(value)).toMatchObject({ status: 'available', context: { excluded: { self: 1 } } });
  });
  it('excludes late records including equality with the analysis cutoff', () => {
    const value = input(22); value.history.rows[0].availableAt = value.analysisAt;
    value.history.rows[1].availableAt = '2026-04-02T15:00:00.000Z';
    expect(analyzePrice(value)).toMatchObject({ status: 'available', context: { excluded: { not_available: 2 } } });
  });
  it('reviews a retroactive purchase at analysis time without using later commercial dates', () => {
    const value = input(19); value.analysisAt = '2026-05-01T15:00:00.000Z'; value.operation.availableAt = value.analysisAt;
    value.history.rows.push({ ...row('known-now'), purchaseDate: '2026-03-10', availableAt: '2026-04-30T12:00:00.000Z' },
      { ...row('commercial-future'), purchaseDate: '2026-04-20', availableAt: '2026-04-20T12:00:00.000Z' });
    expect(analyzePrice(value)).toMatchObject({ status: 'available', context: { support: { references: 20 },
      purpose: 'review_at_analysis_time_not_preapproval', excluded: { outside_window: 1 } } });
  });
  it('does not inspect future prices or let them change the reference', () => {
    const value = input(); value.history.rows.push({ ...row('future'), purchaseDate: '2026-04-02', unitPrice: 'invalid' });
    expect(analyzePrice(value)).toMatchObject({ status: 'available', medianUnitPrice: '10.000',
      percentDifference: { numerator: '0', denominator: '1' } });
  });
  it('distinguishes absent history, incomplete coverage and insufficient support', () => {
    expect(analyzePrice(input(0))).toMatchObject({ reason: 'no_history' });
    const value = input(); value.history.coverage.complete = false;
    expect(analyzePrice(value)).toMatchObject({ reason: 'incomplete_coverage' });
    value.history.coverage.complete = true; value.history.coverage.startDate = '2026-01-02';
    expect(analyzePrice(value)).toMatchObject({ reason: 'incomplete_coverage' });
    value.history.coverage.startDate = '2026-01-01'; value.history.coverage.endDate = '2026-03-30';
    expect(analyzePrice(value)).toMatchObject({ reason: 'incomplete_coverage' });
  });
  it.each(['0.00', '-1.00', 'NaN', 'Infinity', '1e2', '10.001', ' 10.00', '10.00\n'])('rejects inconsistent historical money %s', price => {
    const value = input(); value.history.rows[0].unitPrice = price;
    expect(analyzePrice(value)).toMatchObject({ status: 'unavailable', reason: 'invalid_history' });
  });
  it.each([0, -1, 1.5, NaN, Infinity])('rejects invalid quantities %s', quantity => {
    const value = input(); value.operation.quantity = quantity;
    expect(analyzePrice(value)).toMatchObject({ reason: 'invalid_operation' });
  });
  it.each(['2026-02-30', '2026-13-01', '2026-1-01', '2026-04-01\n'])('rejects invalid dates %s', day => {
    const value = input(); value.operation.purchaseDate = day;
    expect(analyzePrice(value)).toMatchObject({ reason: 'invalid_operation' });
  });
  it('rejects future purchases according to the Sao Paulo civil date', () => {
    const value = input(); value.analysisAt = '2026-04-01T01:00:00.000Z'; value.operation.availableAt = value.analysisAt;
    expect(analyzePrice(value)).toMatchObject({ reason: 'invalid_operation' });
  });
  it('refuses not-yet-available candidates and unproven specifications', () => {
    const value = input(); value.operation.availableAt = '2026-04-02T15:00:00.000Z';
    expect(analyzePrice(value)).toMatchObject({ reason: 'operation_not_available' });
    value.operation.availableAt = value.analysisAt; value.operation.specificationId = 'inferred-from-existing-p4';
    expect(analyzePrice(value)).toMatchObject({ reason: 'unsupported_comparability' });
  });
  it('refuses repeated eligible identities, whether identical or conflicting', () => {
    const value = input(19); value.history.rows.push({ ...value.history.rows[0] });
    expect(analyzePrice(value)).toMatchObject({ reason: 'duplicate_history_identity' });
    value.history.rows[19].unitPrice = '999.00';
    expect(analyzePrice(value)).toMatchObject({ reason: 'duplicate_history_identity' });
  });
  it.each([null, [], {}, { ...input(), origin: 'real' }, { ...input(), contract: 'p4-purchase/1.0' },
    { ...input(), extra: true }])('rejects malformed requests or provenance (%s)', value => {
    expect(analyzePrice(value)).toMatchObject({ status: 'unavailable', reason: 'invalid_request' });
  });
  it('is deterministic, JSON serializable and never mutates frozen inputs', () => {
    const value = input(30); const copy = structuredClone(value);
    const freeze = (object: object) => { Object.values(object).forEach(v => { if (v && typeof v === 'object') freeze(v); }); Object.freeze(object); };
    freeze(value); const result = analyzePrice(value);
    expect(value).toEqual(copy); copy.history.rows.reverse(); expect(analyzePrice(copy)).toEqual(result);
    expect(JSON.parse(JSON.stringify(result))).toEqual(result);
  });
  it('retains exact percentages for extreme valid prices and repeating thirds', () => {
    const value = input(); value.history.rows.forEach(r => { r.unitPrice = '0.01'; });
    value.operation.unitPrice = '1000000.00';
    expect(analyzePrice(value)).toMatchObject({ percentDifference: { numerator: '9999999900', denominator: '1', display: '9999999900.000000' } });
    value.history.rows.forEach(r => { r.unitPrice = '3.00'; }); value.operation.unitPrice = '1.00';
    expect(analyzePrice(value)).toMatchObject({ percentDifference: { numerator: '-200', denominator: '3', display: '-66.666667' } });
  });
  it.each(['currency', 'unit', 'packaging', 'priceBasis', 'productId'])('refuses unsupported candidate %s', key => {
    const value = input(); Object.assign(value.operation, { [key]: 'unsupported' });
    expect(analyzePrice(value)).toMatchObject({ status: 'unavailable', reason: 'unsupported_comparability' });
  });
  it.each([
    { unitPrice: 10 }, { unitPrice: '1000000.01' }, { paymentDays: -1 }, { paymentDays: 1.5 },
    { quantityPricing: 'unspecified' }, { availableAt: '2026-04-01T12:00:00-03:00' },
    { availableAt: '2026-03-31T12:00:00.000Z' }, { extra: 'unexpected' },
  ])('refuses invalid candidate fields (%j)', change => {
    const value = input(); Object.assign(value.operation, change);
    expect(analyzePrice(value)).toMatchObject({ status: 'unavailable', reason: 'invalid_operation' });
  });
  it('rejects missing history, invalid coverage and invalid analysis instants', () => {
    expect(analyzePrice({ ...input(), history: null })).toMatchObject({ reason: 'invalid_history' });
    const value = input(); value.history.coverage.startDate = '2026-04-02';
    expect(analyzePrice(value)).toMatchObject({ reason: 'invalid_history' });
    expect(analyzePrice({ ...input(), analysisAt: 'invalid' })).toMatchObject({ reason: 'invalid_request' });
  });
  it('does not inflate support through mismatched groups or silently impute prices', () => {
    const value = input(); value.history.rows.forEach(r => { r.packaging = '25 kg'; });
    expect(analyzePrice(value)).toMatchObject({ status: 'unavailable', reason: 'no_history', context: {
      support: { references: 0 }, excluded: { incomparable: 20 } } });
    value.history.rows = input().history.rows;
    Object.assign(value.history.rows[0], { unitPrice: undefined });
    expect(analyzePrice(value)).toMatchObject({ reason: 'invalid_history' });
  });
  it('adds leap day to a 90-calendar-day window and accepts legitimate leap dates', () => {
    const value = input(); value.operation.purchaseDate = '2024-03-01'; value.operation.availableAt = '2024-03-01T12:00:00.000Z';
    value.analysisAt = '2024-03-01T15:00:00.000Z';
    value.history.coverage = { startDate: '2023-12-02', endDate: '2024-02-29', complete: true };
    value.history.rows.forEach(r => { r.purchaseDate = '2024-02-29'; r.availableAt = '2024-02-29T12:00:00.000Z'; });
    expect(analyzePrice(value)).toMatchObject({ status: 'available', context: {
      window: { startDate: '2023-12-02', endExclusive: '2024-03-01' }, support: { dates: 1 } } });
  });
});
