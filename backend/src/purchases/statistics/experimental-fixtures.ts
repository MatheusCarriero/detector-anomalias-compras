import type { PriceAnalysisInput } from './price-analysis.js';
import { EXPERIMENTAL_PRODUCTS, PRICE_BASIS } from './experimental-specifications.js';

/** Deterministic, constructed examples, not learned market distributions.
 * 30 separate simulated events/product, three suppliers/departments, every third
 * day from Jan 2 to Mar 30. Full Jan-Mar coverage is declared by construction.
 * Quantity-independent pricing, no urgency, same site and 30-day terms are
 * experimental assumptions, NOT inferred attributes of existing P4 purchases.
 * No I/O, seed, persistence, production catalog import or randomness. */
export function createExperimentalScenarios(): PriceAnalysisInput[] {
  const centers = [5000n, 125n, 8000n, 2000n, 3000n];
  const decimal = (cents: bigint) => `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`;
  return EXPERIMENTAL_PRODUCTS.map((spec, index) => {
    const common = {
      productId: spec.productId, specificationId: spec.specificationId, unit: spec.unit, packaging: spec.packaging,
      currency: 'BRL', priceBasis: PRICE_BASIS.id, paymentDays: 30, deliveryZone: 'experimental-site-a',
      quantityPricing: 'independent-by-experiment' as const,
    };
    return {
      contract: 'p4-price-analysis/1.0', origin: 'synthetic-experiment', analysisAt: '2026-04-01T15:00:00.000Z',
      operation: { ...common, id: `experiment-${spec.productId}-candidate`,
        supplierId: 'experimental-supplier-0', departmentId: 'experimental-department-0', quantity: 10,
        unitPrice: decimal(centers[index] * 120n / 100n), purchaseDate: '2026-04-01', availableAt: '2026-04-01T12:00:00.000Z' },
      history: {
        coverage: { startDate: '2026-01-01', endDate: '2026-03-31', complete: true },
        rows: Array.from({ length: 30 }, (_, i) => {
          const date = new Date(Date.UTC(2026, 0, 2) + i * 3 * 86_400_000).toISOString().slice(0, 10);
          const offset = BigInt(i < 15 ? i - 15 : i - 14); // -15..-1, 1..15 cents; exact central median.
          return { ...common, id: `experiment-${spec.productId}-reference-${String(i).padStart(2, '0')}`,
            supplierId: `experimental-supplier-${i % 3}`, departmentId: `experimental-department-${Math.floor(i / 3) % 3}`,
            quantity: 5 + i % 5, unitPrice: decimal(centers[index] + offset), purchaseDate: date, availableAt: `${date}T12:00:00.000Z` };
        }),
      },
    };
  });
}
