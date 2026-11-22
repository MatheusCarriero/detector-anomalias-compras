import { analyzePrice } from './price-analysis.js';
import type { ExperimentalPurchase, PriceAnalysisInput } from './price-analysis.js';
import { createExperimentalScenarios } from './experimental-fixtures.js';

// P4.10D: controlled perturbations, NOT market prices, fraud labels or thresholds.
// Literal oracles were chosen before execution, without consulting analyzePrice.
// Alternating low/high prices give the stated median for 20 or 30 observations.
// The brick reference is deliberately 2.00 here: 10% of the original 1.25 would
// require half cents. No original fixture, contract or rounding rule is changed.
const PRODUCTS = [
  { id: 'prod-cimento', low: '49.00', high: '51.00', center: '50.00', median: '50.000',
    prices: ['50.00', '55.00', '62.50', '100.00', '45.00', '37.50', '25.00'] },
  { id: 'prod-tijolo', low: '1.99', high: '2.01', center: '2.00', median: '2.000',
    prices: ['2.00', '2.20', '2.50', '4.00', '1.80', '1.50', '1.00'] },
  { id: 'prod-vergalhao', low: '79.00', high: '81.00', center: '80.00', median: '80.000',
    prices: ['80.00', '88.00', '100.00', '160.00', '72.00', '60.00', '40.00'] },
  { id: 'prod-argamassa', low: '19.00', high: '21.00', center: '20.00', median: '20.000',
    prices: ['20.00', '22.00', '25.00', '40.00', '18.00', '15.00', '10.00'] },
  { id: 'prod-tubo', low: '29.00', high: '31.00', center: '30.00', median: '30.000',
    prices: ['30.00', '33.00', '37.50', '60.00', '27.00', '22.50', '15.00'] },
] as const;
const PERCENTAGES = ['0', '10', '25', '100', '-10', '-25', '-50'] as const;
type Product = typeof PRODUCTS[number];
const NO_EXCLUSIONS = { self: 0, outside_window: 0, not_available: 0, incomparable: 0 };

// Reuses P4.10C's identities, specifications, dates, provenance and coverage.
function scenario(product: Product, count = 30): PriceAnalysisInput {
  const input = createExperimentalScenarios().find(s => s.operation.productId === product.id);
  if (!input) throw new Error('Missing controlled fixture');
  input.operation.unitPrice = product.center;
  input.history.rows = input.history.rows.slice(0, count).map((r, i) => ({
    ...r, unitPrice: i % 2 === 0 ? product.low : product.high,
  }));
  return input;
}
function available(input: PriceAnalysisInput) {
  const result = analyzePrice(input);
  expect(result.status).toBe('available');
  if (result.status !== 'available') throw new Error(`Unexpected refusal: ${result.reason}`);
  return result;
}
function expectedIds(input: PriceAnalysisInput) { return input.history.rows.map(r => r.id).sort(); }

describe('P4.10D controlled offline evaluation', () => {
  const perturbations = PRODUCTS.flatMap(product => PERCENTAGES.map((percentage, i) => ({
    product, productId: product.id, percentage, price: product.prices[i],
  })));
  it.each(perturbations)('$productId: exact $percentage% perturbation on diverse history', ({ product, percentage, price }) => {
    const input = scenario(product); input.operation.unitPrice = price;
    const before = structuredClone(input);
    const result = available(input);
    expect(result).toMatchObject({ contract: 'p4-price-analysis/1.0', origin: 'synthetic-experiment',
      unitPrice: price, medianUnitPrice: product.median, constantReferencePrice: false,
      percentDifference: { numerator: percentage, denominator: '1', display: `${percentage}.000000`,
        decimalPlaces: 6, rounding: 'half-away-from-zero' },
      context: { operationId: input.operation.id, productId: product.id,
        purpose: 'review_at_analysis_time_not_preapproval', minimumReferences: 20,
        window: { startDate: '2026-01-01', endExclusive: '2026-04-01', days: 90 },
        support: { references: 30, dates: 30, suppliers: 3 }, referenceIds: expectedIds(input), excluded: NO_EXCLUSIONS } });
    expect(input).toEqual(before);
    input.history.rows.reverse(); expect(analyzePrice(input)).toEqual(result);
    expect(JSON.parse(JSON.stringify(result))).toEqual(result);
  });

  it.each(PRODUCTS.flatMap(product => [0, 19, 20, 30].map(count => ({ product, productId: product.id, count }))))(
    '$productId: support=$count after a fixed +100% perturbation', ({ product, count }) => {
      const input = scenario(product, count); input.operation.unitPrice = product.prices[3];
      const result = analyzePrice(input);
      expect(result.context).toMatchObject({ support: { references: count, dates: count, suppliers: count === 0 ? 0 : 3 },
        referenceIds: expectedIds(input), excluded: NO_EXCLUSIONS });
      if (count < 20) {
        expect(result).toMatchObject({ status: 'unavailable', reason: count === 0 ? 'no_history' : 'insufficient_history' });
        expect(result).not.toHaveProperty('medianUnitPrice'); expect(result).not.toHaveProperty('percentDifference');
      } else {
        expect(result).toMatchObject({ status: 'available', medianUnitPrice: product.median,
          percentDifference: { numerator: '100', denominator: '1', display: '100.000000' } });
      }
    });

  it.each(PRODUCTS)('$id: mixed incompatible extreme references cannot change the eligible population', product => {
    const input = scenario(product, 20); const ids = expectedIds(input);
    const differences: Partial<ExperimentalPurchase>[] = [
      { productId: 'another-product' }, { specificationId: 'another-specification' },
      { unit: 'kg' }, { packaging: 'another-package' }, { currency: 'USD' },
      { priceBasis: 'freight-included' }, { paymentDays: 60 }, { deliveryZone: 'another-site' },
      { quantityPricing: 'same-quantity-only' },
    ];
    input.history.rows.push(...differences.map((difference, i) => ({ ...input.history.rows[0],
      id: `incompatible-${i}`, unitPrice: '1000000.00', ...difference })));
    const result = available(input);
    expect(result).toMatchObject({ medianUnitPrice: product.median,
      percentDifference: { numerator: '0', denominator: '1' }, context: {
        referenceIds: ids, support: { references: 20, dates: 20, suppliers: 3 },
        excluded: { ...NO_EXCLUSIONS, incomparable: 9 } } });
    input.history.rows.reverse(); expect(analyzePrice(input)).toEqual(result);
    input.history.rows = input.history.rows.filter(r => r.id !== ids[0]);
    expect(analyzePrice(input)).toMatchObject({ status: 'unavailable', reason: 'insufficient_history', context: {
      support: { references: 19 }, excluded: { ...NO_EXCLUSIONS, incomparable: 9 } } });
  });

  it.each(PRODUCTS)('$id: combined temporal exclusions preserve the exact day -90 boundary', product => {
    const input = scenario(product, 20);
    const boundary = input.history.rows[19]; // High price balances the 10 low and 9 high retained prices.
    boundary.purchaseDate = '2026-01-01'; boundary.availableAt = '2026-01-01T12:00:00.000Z';
    const ids = expectedIds(input);
    const reference = input.history.rows[0];
    input.history.rows.push(
      { ...reference, id: 'old', purchaseDate: '2025-12-31', unitPrice: '1000000.00' },
      { ...reference, id: 'same-day', purchaseDate: '2026-04-01', availableAt: input.analysisAt, unitPrice: '1000000.00' },
      { ...reference, id: 'future', purchaseDate: '2026-04-02', availableAt: '2026-04-02T12:00:00.000Z', unitPrice: '1000000.00' },
      { ...reference, id: 'late', availableAt: '2026-04-02T12:00:00.000Z', unitPrice: '1000000.00' },
      { ...reference, id: 'cutoff-tie', availableAt: input.analysisAt, unitPrice: '1000000.00' },
      { ...reference, id: input.operation.id, unitPrice: '1000000.00' },
    );
    const result = available(input);
    expect(result).toMatchObject({ medianUnitPrice: product.median,
      percentDifference: { numerator: '0', denominator: '1' }, context: {
        referenceIds: ids, support: { references: 20, dates: 20, suppliers: 3 },
        excluded: { self: 1, outside_window: 3, not_available: 2, incomparable: 0 } } });
    input.history.rows.reverse(); expect(analyzePrice(input)).toEqual(result);
    boundary.purchaseDate = '2025-12-31';
    expect(analyzePrice(input)).toMatchObject({ status: 'unavailable', reason: 'insufficient_history', context: {
      support: { references: 19 }, excluded: { self: 1, outside_window: 4, not_available: 2, incomparable: 0 } } });
  });

  const concentrations = [
    { name: 'one date', singleDate: true, singleSupplier: false, constant: false },
    { name: 'one supplier', singleDate: false, singleSupplier: true, constant: false },
    { name: 'one date and supplier', singleDate: true, singleSupplier: true, constant: false },
    { name: 'constant prices', singleDate: false, singleSupplier: false, constant: true },
    { name: 'all three limitations', singleDate: true, singleSupplier: true, constant: true },
  ];
  it.each(PRODUCTS.flatMap(product => concentrations.map(c => ({ product, productId: product.id, ...c }))))(
    '$productId: describes $name without claiming statistical representativeness', ({ product, singleDate, singleSupplier, constant }) => {
      const input = scenario(product); input.operation.unitPrice = product.prices[2];
      for (const r of input.history.rows) {
        if (singleDate) { r.purchaseDate = '2026-03-01'; r.availableAt = '2026-03-01T12:00:00.000Z'; }
        if (singleSupplier) r.supplierId = 'experimental-single-supplier';
        if (constant) r.unitPrice = product.center;
      }
      // Current contract gates counts, not independence. This is a limitation,
      // not a proposal to label these results reliable or change the minimum.
      expect(available(input)).toMatchObject({ medianUnitPrice: product.median, constantReferencePrice: constant,
        percentDifference: { numerator: '25', denominator: '1', display: '25.000000' }, context: {
          support: { references: 30, dates: singleDate ? 1 : 30, suppliers: singleSupplier ? 1 : 3 },
          referenceIds: expectedIds(input), excluded: NO_EXCLUSIONS } });
    });

  it('quantifies sensitivity to historical contamination without trimming or changing the method', () => {
    const input = scenario(PRODUCTS[0]); input.operation.unitPrice = '62.50';
    input.history.rows.forEach(r => { r.unitPrice = '50.00'; });
    // 14 of 30 extremes: the middle two prices are still 50.
    input.history.rows.slice(0, 14).forEach(r => { r.unitPrice = '1000000.00'; });
    expect(available(input)).toMatchObject({ medianUnitPrice: '50.000',
      percentDifference: { numerator: '25', denominator: '1', display: '25.000000' } });
    // Exactly half: median=(50+1,000,000)/2; delta=(62.50-500025)*100/500025 %.
    // Reduce -49,996,250/500,025 by 25: -1,999,850/20,001.
    input.history.rows[14].unitPrice = '1000000.00';
    expect(available(input)).toMatchObject({ medianUnitPrice: '500025.000',
      percentDifference: { numerator: '-1999850', denominator: '20001', display: '-99.987501' } });
  });
});
