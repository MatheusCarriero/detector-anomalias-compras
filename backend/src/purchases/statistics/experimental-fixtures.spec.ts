import { analyzePrice } from './price-analysis.js';
import { createExperimentalScenarios } from './experimental-fixtures.js';
import { EXPERIMENTAL_PRODUCTS, PRICE_BASIS } from './experimental-specifications.js';
import { PURCHASE_CATALOG } from '../purchase-catalog.js';

// Any accidental runtime connection, model subprocess or file read is a failure.
vi.mock('node:fs', () => { throw new Error('No filesystem access in pure experiment'); });
vi.mock('node:fs/promises', () => { throw new Error('No filesystem access in pure experiment'); });
vi.mock('node:net', () => { throw new Error('No network in pure experiment'); });
vi.mock('node:child_process', () => { throw new Error('No model subprocess in pure experiment'); });
vi.mock('pg', () => { throw new Error('No database in pure experiment'); });
vi.mock('@prisma/adapter-pg', () => { throw new Error('No database adapter in pure experiment'); });

describe('explicit P4.10C synthetic reference scenarios', () => {
  it('has five independent product groups with 30 dated references each', () => {
    const scenarios = createExperimentalScenarios();
    expect(scenarios).toHaveLength(5);
    expect(scenarios.map(s => s.operation.productId)).toEqual(PURCHASE_CATALOG.products.map(p => p.id));
    const identities = new Set<string>();
    for (const scenario of scenarios) {
      expect(scenario.history.rows).toHaveLength(30);
      expect(new Set(scenario.history.rows.map(r => r.purchaseDate)).size).toBe(30);
      expect(new Set(scenario.history.rows.map(r => r.supplierId)).size).toBe(3);
      expect(new Set(scenario.history.rows.map(r => r.departmentId)).size).toBe(3);
      scenario.history.rows.forEach(r => identities.add(r.id));
      expect(scenario.operation.priceBasis).toBe(PRICE_BASIS.id);
      const result = analyzePrice(scenario);
      expect(result).toMatchObject({ status: 'available', context: { support: { references: 30, dates: 30, suppliers: 3 } },
        percentDifference: { numerator: '20', denominator: '1', display: '20.000000' } });
      if (result.status !== 'available') throw new Error('Missing experimental reference');
      expect(['50.000', '1.250', '80.000', '20.000', '30.000']).toContain(result.medianUnitPrice);
    }
    expect(identities.size).toBe(150);
  });
  it('keeps original catalog unchanged and provides explicit fictional specifications separately', () => {
    const before = structuredClone(PURCHASE_CATALOG); createExperimentalScenarios();
    expect(PURCHASE_CATALOG).toEqual(before);
    expect(EXPERIMENTAL_PRODUCTS.every(p => p.specification.includes('fictício'))).toBe(true);
    expect(PURCHASE_CATALOG.products.every(p => !Object.hasOwn(p, 'specificationId'))).toBe(true);
  });
  it('constructs deterministic fixtures with no shared mutable state between calls or scenarios', () => {
    const first = createExperimentalScenarios(); const second = createExperimentalScenarios();
    expect(first).toEqual(second); expect(first).toHaveLength(5);
    first[0].history.rows[0].unitPrice = '999.00'; first[0].history.coverage.complete = false;
    expect(createExperimentalScenarios()).toEqual(second);
    expect(first[1]).toEqual(second[1]);
  });
});
