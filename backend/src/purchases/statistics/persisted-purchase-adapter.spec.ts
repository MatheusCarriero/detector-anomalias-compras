import { preparePurchase } from '../purchase-contract.js';
import { PURCHASE_CATALOG } from '../purchase-catalog.js';
import type { PurchaseRecord } from '../purchase-repository.js';
import { adaptPersistedPurchase } from './persisted-purchase-adapter.js';

vi.mock('./price-analysis.js', () => { throw new Error('Eligibility must not import the statistical executor'); });
vi.mock('pg', () => { throw new Error('Database forbidden'); });
vi.mock('@prisma/adapter-pg', () => { throw new Error('Database adapter forbidden'); });
vi.mock('node:net', () => { throw new Error('Network forbidden'); });
vi.mock('node:child_process', () => { throw new Error('Model execution forbidden'); });

function receipt(productId = 'prod-cimento'): PurchaseRecord {
  const prepared = preparePurchase({
    contract: 'p4-purchase/1.0', origin: 'manual',
    idempotency_key: '935af6ba-e660-40dc-a268-b13a158599cc',
    purchase: { supplier_id: 'sup-obra', product_id: productId, department_id: 'dep-obras',
      quantity: 3, unit_price: '0.10', currency: 'BRL', purchase_date: '2026-11-03', payment_days: 30 },
  }, new Date('2026-11-15T15:00:00.000Z'));
  if (!prepared.ok) throw new Error('Invalid synthetic fixture');
  return {
    id: '77777777-7777-4777-8777-777777777777', version_id: '88888888-8888-4888-8888-888888888888',
    revision_no: 1, recorded_at: '2026-11-15T15:00:00.000Z',
    source_reference_id: '66666666-6666-4666-8666-666666666666',
    source: prepared.value.source, content_sha256: prepared.value.content_sha256,
    purchase: prepared.value.original_content.purchase, analysis: prepared.value.analysis,
  };
}

describe('persisted P4 purchase eligibility, without statistical execution', () => {
  it('returns a diagnostic contract, not an experimental statistical result', () => {
    const result = adaptPersistedPurchase(receipt());
    expect(result.contract).toBe('p4-persisted-price-eligibility/1.0');
    expect(result.target_contract).toBe('p4-price-analysis/1.0');
    expect(result.status).toBe('unavailable');
    expect(result).not.toHaveProperty('medianUnitPrice');
    expect(result).not.toHaveProperty('percentDifference');
    expect(result).not.toHaveProperty('score');
  });

  it.each([
    ['contract_incompatibility', 'manual_origin_not_supported', 'origin'],
    ['missing_requirement', 'technical_specification_missing', 'specificationId'],
    ['missing_requirement', 'packaging_not_explicit', 'packaging'],
    ['missing_requirement', 'price_composition_unknown', 'priceBasis'],
    ['missing_requirement', 'delivery_conditions_missing', 'deliveryZone'],
    ['missing_requirement', 'quantity_pricing_unknown', 'quantityPricing'],
    ['insufficient_historical_evidence', 'availability_not_established', 'availableAt'],
    ['insufficient_historical_evidence', 'historical_coverage_not_established', 'history.coverage'],
  ])('distinguishes %s / %s', (category, code, field) => {
    expect(adaptPersistedPurchase(receipt()).diagnostics).toContainEqual({ category, code, field });
  });

  it('preserves identities, original hash and the repository-verified provenance', () => {
    const input = receipt();
    expect(adaptPersistedPurchase(input).evidence).toEqual({
      id: input.id, version_id: input.version_id, revision_no: 1, recorded_at: input.recorded_at,
      source_reference_id: input.source_reference_id, source: input.source, content_sha256: input.content_sha256,
      purchase_contract: 'p4-purchase/1.0', origin: 'manual',
      catalog_version: 'p4-catalog/1.0', catalog_origin: 'synthetic',
    });
  });

  it.each(PURCHASE_CATALOG.products)('does not infer specifications or packaging for $id', product => {
    const input = receipt(product.id);
    const result = adaptPersistedPurchase(input);
    expect(result.recorded).toEqual(input.purchase);
    expect(result.recorded.product.unit).toBe(product.unit);
    for (const field of ['specificationId', 'packaging', 'priceBasis', 'deliveryZone', 'quantityPricing', 'availableAt']) {
      expect(result.recorded).not.toHaveProperty(field);
    }
    expect(result.status).toBe('unavailable');
    expect(result.diagnostics).toHaveLength(8);
  });

  it('retains monetary strings, quantity and payment terms without conversion', () => {
    expect(adaptPersistedPurchase(receipt()).recorded).toMatchObject({
      quantity: 3, unit_price: '0.10', total: '0.30', currency: 'BRL', payment_days: 30,
    });
  });

  it('does not substitute registration time for availability or invent historical support', () => {
    const result = adaptPersistedPurchase(receipt());
    expect(result.recorded.purchase_date).toBe('2026-11-03');
    expect(result.evidence.recorded_at).toBe('2026-11-15T15:00:00.000Z');
    expect(result.history).toEqual({ status: 'not_assessed' });
    expect(result).not.toHaveProperty('analysisAt');
    expect(result).not.toHaveProperty('support');
  });

  it('does not forward extra properties as verified comparability metadata', () => {
    const input = receipt();
    const extended = { ...input, purchase: { ...input.purchase, specificationId: 'unverified', packaging: 'unverified' } };
    expect(adaptPersistedPurchase(extended)).toEqual(adaptPersistedPurchase(input));
  });

  it('is deterministic, accepts frozen receipts and leaves the V2 analysis policy untouched', () => {
    const input = receipt();
    Object.freeze(input);
    const before = structuredClone(input);
    const first = adaptPersistedPurchase(input);
    expect(adaptPersistedPurchase(input)).toEqual(first);
    expect(input).toEqual(before);
    expect(input.analysis).toEqual({ status: 'unavailable', reason: 'manual_source_incompatible_with_procurement_v2' });
  });

  it('returns detached objects, including evidence, entities and diagnostic arrays', () => {
    const input = receipt();
    const before = structuredClone(input);
    const first = adaptPersistedPurchase(input);
    const second = adaptPersistedPurchase(input);
    first.evidence.id = 'changed';
    first.evidence.source.source_id = 'changed';
    first.diagnostics.pop();
    expect(first.recorded.product).not.toBe(input.purchase.product);
    expect(first.recorded.supplier).not.toBe(input.purchase.supplier);
    expect(first.recorded.department).not.toBe(input.purchase.department);
    expect(input).toEqual(before);
    expect(adaptPersistedPurchase(input)).toEqual(second);
  });
});
