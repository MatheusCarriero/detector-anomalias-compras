import { preparePurchase } from '../purchase-contract.js';
import type { PurchaseRecord } from '../purchase-repository.js';
import {
  COMPARABILITY_FIELDS, validateManualComparability, compareManualComparability,
} from './manual-comparability.js';
import type { ManualComparabilityRequest, TrustedVerification } from './manual-comparability.js';

vi.mock('./price-analysis.js', () => { throw new Error('Experimental execution forbidden'); });
vi.mock('pg', () => { throw new Error('Database forbidden'); });
vi.mock('@prisma/adapter-pg', () => { throw new Error('Database adapter forbidden'); });
vi.mock('node:net', () => { throw new Error('Network forbidden'); });
vi.mock('node:child_process', () => { throw new Error('Model execution forbidden'); });

const now = new Date('2026-11-19T15:00:00.000Z');
function receipt(quantity = 3, price = '0.10', paymentDays = 30): PurchaseRecord {
  const p = preparePurchase({ contract: 'p4-purchase/1.0', origin: 'manual',
    idempotency_key: '935af6ba-e660-40dc-a268-b13a158599cc', purchase: {
      supplier_id: 'sup-obra', product_id: 'prod-cimento', department_id: 'dep-obras',
      quantity, unit_price: price, currency: 'BRL', purchase_date: '2026-11-03', payment_days: paymentDays,
    } }, now);
  if (!p.ok) throw new Error('Invalid fixture');
  return { id: '77777777-7777-4777-8777-777777777777', version_id: '88888888-8888-4888-8888-888888888888',
    revision_no: 1, recorded_at: '2026-11-15T15:00:00.000Z', source_reference_id: '66666666-6666-4666-8666-666666666666',
    source: p.value.source, content_sha256: p.value.content_sha256, purchase: p.value.original_content.purchase, analysis: p.value.analysis };
}
function request(p = receipt()): ManualComparabilityRequest {
  const declared = <T>(value: T) => ({ value, provenance: {
    kind: 'declared' as const, actor_id: 'test-declarant', declared_at: '2026-11-18T15:00:00.000Z', evidence_ref: 'test-document-1',
  } });
  return {
    contract: 'p4-manual-comparability/1.0', id: '99999999-9999-4999-8999-999999999999', revision: 1, supersedes: null,
    purchase: { id: p.id, version_id: p.version_id, content_sha256: p.content_sha256 },
    attributes: {
      specification: declared({ id: 'test-spec-cement', version: '1', product_id: 'prod-cimento', sha256: 'a'.repeat(64) }),
      unit: declared('saco de 50 kg'),
      packaging: declared({ id: 'test-package', version: '1', quantity_per_package: '50.000000', content_unit: 'kg' }),
      currency: declared('BRL'),
      price_basis: declared({ id: 'test-price-basis', version: '1', discounts: 'deducted' as const,
        taxes: 'included' as const, tax_credits: 'none' as const, freight: 'excluded' as const, other_charges: 'not_applicable' as const }),
      payment_days: declared(p.purchase.payment_days),
      delivery: declared({ condition_id: 'test-standard', condition_version: '1', location_id: 'test-site-a' }),
      quantity_pricing: declared({ regime: 'same_quantity_only' as const }),
    },
  };
}
function set(input: unknown, path: string, value: unknown) {
  const parts = path.split('.'); let target = input as Record<string, unknown>;
  for (const part of parts.slice(0, -1)) target = target[part] as Record<string, unknown>;
  target[parts.at(-1)!] = value;
}
function valid(input = request(), purchase = receipt(), verifications: TrustedVerification[] = []) {
  const result = validateManualComparability(input, { purchase, now, verifications });
  if (!result.ok) throw new Error(JSON.stringify(result.error));
  return result.value;
}
function attest(input = request(), purchase = receipt()) {
  const initial = valid(input, purchase);
  return COMPARABILITY_FIELDS.filter(field => input.attributes[field]).map(field => ({
    field, comparability_sha256: initial.content_sha256, evidence_id: `test-evidence-${field}`,
    verified_by: 'test-reviewer', verified_at: '2026-11-19T14:00:00.000Z',
  }));
}

describe('manual comparability contract, isolated from experimental analysis', () => {
  it.each([null, undefined, [], 'invalid', 42])('rejects a non-object request (%s)', input => {
    expect(validateManualComparability(input, { purchase: receipt(), now })).toEqual({
      ok: false, error: { code: 'invalid_structure', field: 'request' },
    });
  });

  it('accepts complete declarations without certifying their commercial truth', () => {
    const result = valid();
    expect(result.status).toBe('unverified');
    expect(result.diagnostics).toEqual(COMPARABILITY_FIELDS.map(field => ({ category: 'unverified', code: 'verification_required', field })));
    expect(Object.values(result.provenance).every(p => p.status === 'declared')).toBe(true);
    expect(result.content.contract).toBe('p4-manual-comparability/1.0');
    expect(result).not.toHaveProperty('score');
    expect(result).not.toHaveProperty('availableAt');
  });

  it.each(COMPARABILITY_FIELDS)('reports missing %s without defaults', field => {
    const input = request(); delete input.attributes[field];
    const result = valid(input);
    expect(result.status).toBe('incomplete');
    expect(result.diagnostics).toContainEqual({ category: 'missing', code: 'required_information_missing', field });
    expect(result.content.attributes).not.toHaveProperty(field);
    expect(result.provenance).not.toHaveProperty(field);
  });

  it('accepts an entirely absent set of attributes as incomplete, not valid for analysis', () => {
    const input = request(); input.attributes = {};
    expect(valid(input).diagnostics).toHaveLength(8);
    expect(valid(input).status).toBe('incomplete');
  });

  it.each([
    ['contract', 'p4-price-analysis/1.0'], ['extra', true], ['id', 'bad'], ['revision', 0], ['revision', 1.5],
    ['purchase.id', '11111111-1111-4111-8111-111111111111'], ['purchase.version_id', '11111111-1111-4111-8111-111111111111'],
    ['purchase.content_sha256', 'b'.repeat(64)], ['attributes.extra', {}],
    ['attributes.specification.value.version', ''], ['attributes.specification.value.sha256', 'bad'],
    ['attributes.specification.value.product_id', 'prod-tubo'], ['attributes.unit.value', 'kg'],
    ['attributes.packaging.value.quantity_per_package', '0'], ['attributes.packaging.value.quantity_per_package', '-1'],
    ['attributes.packaging.value.quantity_per_package', 50], ['attributes.packaging.value.quantity_per_package', '1e2'],
    ['attributes.packaging.value.quantity_per_package', '0.0000001'], ['attributes.packaging.value.content_unit', ''],
    ['attributes.currency.value', 'USD'], ['attributes.price_basis.value.freight', 'unknown'],
    ['attributes.price_basis.value.discounts', null], ['attributes.price_basis.value.tax_credits', 'unknown'],
    ['attributes.payment_days.value', 31], ['attributes.payment_days.value', -1], ['attributes.payment_days.value', 30.5],
    ['attributes.delivery.value.location_id', ''], ['attributes.quantity_pricing.value.regime', 'independent-by-experiment'],
    ['attributes.unit.provenance.kind', 'verified'], ['attributes.unit.provenance.declared_at', '2026-11-20T15:00:00.000Z'],
    ['attributes.unit.provenance.declared_at', '2026-02-30T15:00:00.000Z'], ['attributes.unit.provenance.actor_id', ''],
    ['attributes.unit.value', 'saco de 50 kg\n'], ['attributes.unit', null],
  ])('rejects malformed or receipt-incompatible %s', (path, value) => {
    const input = request(); set(input, path, value);
    expect(validateManualComparability(input, { purchase: receipt(), now }).ok).toBe(false);
  });

  it('rejects accessors without executing them', () => {
    const input = request(); const getter = vi.fn(() => 'private');
    Object.defineProperty(input.attributes.unit!, 'value', { enumerable: true, get: getter });
    expect(validateManualComparability(input, { purchase: receipt(), now }).ok).toBe(false);
    expect(getter).not.toHaveBeenCalled();
  });

  it('validates independent revision lineage without modifying the receipt', () => {
    const input = request(); input.revision = 2;
    expect(validateManualComparability(input, { purchase: receipt(), now }).ok).toBe(false);
    input.supersedes = { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', revision: 1, content_sha256: 'c'.repeat(64) };
    expect(valid(input).content.supersedes).toEqual(input.supersedes);
    input.supersedes.revision = 2;
    expect(validateManualComparability(input, { purchase: receipt(), now }).ok).toBe(false);
  });

  it('rejects a self-predecessor and a predecessor on revision one', () => {
    const input = request();
    input.supersedes = { id: input.id, revision: 1, content_sha256: 'c'.repeat(64) };
    expect(validateManualComparability(input, { purchase: receipt(), now }).ok).toBe(false);
    input.revision = 2;
    expect(validateManualComparability(input, { purchase: receipt(), now }).ok).toBe(false);
  });

  it('requires provenance even when a field value is syntactically valid', () => {
    const input = request();
    set(input, 'attributes.unit', { value: 'saco de 50 kg' });
    expect(validateManualComparability(input, { purchase: receipt(), now }).ok).toBe(false);
  });

  it('does not accept verification evidence through the public declaration structure', () => {
    const input = request(); set(input, 'verifications', attest());
    expect(validateManualComparability(input, { purchase: receipt(), now }).ok).toBe(false);
  });

  it('binds internal verification to the exact content and each field', () => {
    const input = request(); const evidence = attest(input);
    const result = valid(input, receipt(), evidence);
    expect(result.status).toBe('verified_metadata');
    expect(result.diagnostics).toEqual([]);
    expect(result.provenance.unit).toEqual({ status: 'verified', verification: evidence[1] });
    const partial = valid(input, receipt(), evidence.slice(0, 1));
    expect(partial.status).toBe('unverified');
    expect(partial.diagnostics).toHaveLength(7);
  });

  it.each(['hash', 'duplicate', 'future', 'before_declaration', 'missing_field', 'empty_actor'])('rejects invalid internal verification: %s', scenario => {
    const input = request(); const evidence = attest(input);
    if (scenario === 'hash') evidence[0].comparability_sha256 = '0'.repeat(64);
    if (scenario === 'duplicate') evidence.push(evidence[0]);
    if (scenario === 'future') evidence[0].verified_at = '2026-11-20T15:00:00.000Z';
    if (scenario === 'before_declaration') evidence[0].verified_at = '2026-11-17T15:00:00.000Z';
    if (scenario === 'missing_field') delete input.attributes.specification;
    if (scenario === 'empty_actor') evidence[0].verified_by = '';
    expect(validateManualComparability(input, { purchase: receipt(), now, verifications: evidence })).toMatchObject({ ok: false });
  });

  it('does not carry verification to a different revision', () => {
    const input = request(); const evidence = attest(input);
    input.revision = 2; input.supersedes = { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', revision: 1, content_sha256: 'c'.repeat(64) };
    expect(validateManualComparability(input, { purchase: receipt(), now, verifications: evidence }).ok).toBe(false);
  });

  it('does not carry verification after modifying a previously declared value', () => {
    const input = request(); const evidence = attest(input);
    input.attributes.delivery!.value.location_id = 'changed-site';
    expect(validateManualComparability(input, { purchase: receipt(), now, verifications: evidence }).ok).toBe(false);
  });

  it.each(['0.01', '0.10', '123456.78', '1000000.00'])('preserves exact stored money %s without recalculation', price => {
    const p = receipt(3, price); const result = valid(request(p), p);
    expect(result.purchase_evidence.unit_price).toBe(price);
    expect(result.purchase_evidence.total).toBe(p.purchase.total);
    expect(result.purchase_evidence.content_sha256).toBe(p.content_sha256);
  });

  it('validates tier bounds and requires the purchased quantity to be in the declared tier', () => {
    const input = request(); input.attributes.quantity_pricing!.value = {
      regime: 'tier', schedule_id: 'test-schedule', schedule_version: '1', min_quantity: 2, max_quantity: 5,
    };
    expect(valid(input).status).toBe('unverified');
    input.attributes.quantity_pricing!.value.min_quantity = 4;
    expect(validateManualComparability(input, { purchase: receipt(), now }).ok).toBe(false);
  });

  it('is deterministic across key order and detaches/freezes results without freezing inputs', () => {
    const input = request(); const p = receipt(); const before = structuredClone({ input, p });
    const a = valid(input, p);
    const reversed = { ...input, attributes: Object.fromEntries(Object.entries(input.attributes).reverse()) };
    expect(validateManualComparability(reversed, { purchase: p, now })).toEqual({ ok: true, value: a });
    expect({ input, p }).toEqual(before);
    expect(Object.isFrozen(input)).toBe(false);
    expect(Object.isFrozen(a.content.attributes)).toBe(true);
    expect(a.content.attributes.unit).not.toBe(input.attributes.unit);
  });

  it('does not accept invalid clocks or expose exception details', () => {
    expect(validateManualComparability(request(), { purchase: receipt(), now: new Date(NaN) })).toEqual({
      ok: false, error: { code: 'invalid_context', field: 'now' },
    });
  });

  it('rejects a validation time earlier than the referenced receipt', () => {
    expect(validateManualComparability(request(), { purchase: receipt(), now: new Date('2026-11-14T15:00:00.000Z') })).toEqual({
      ok: false, error: { code: 'invalid_context', field: 'purchase.recorded_at' },
    });
  });
});

describe('comparison of metadata only, without statistical or temporal eligibility', () => {
  it.each([
    ['specification', 'id', 'other-spec'], ['specification', 'version', '2'], ['specification', 'sha256', 'b'.repeat(64)],
    ['packaging', 'id', 'other-package'], ['packaging', 'quantity_per_package', '25'],
    ['price_basis', 'freight', 'included'], ['price_basis', 'taxes', 'excluded'],
    ['price_basis', 'discounts', 'not_deducted'], ['delivery', 'location_id', 'other-site'],
    ['delivery', 'condition_version', '2'], ['quantity_pricing', 'regime', 'quantity_independent'],
  ])('identifies a declared difference in %s.%s', (field, key, value) => {
    const other = request(); set(other, `attributes.${field}.value.${key}`, value);
    const result = compareManualComparability(valid(), valid(other));
    expect(result.status).toBe('different_metadata');
    expect(result.differences).toContain(field);
  });

  it('equal declarations do not prove verified equivalence', () => {
    expect(compareManualComparability(valid(), valid())).toEqual({ status: 'unverified', differences: [] });
    const input = request(); input.attributes = {};
    expect(compareManualComparability(valid(input), valid(input)).status).toBe('incomplete');
  });

  it('detects different payment terms even when both match their own receipts', () => {
    const other = receipt(3, '0.10', 60);
    expect(compareManualComparability(valid(), valid(request(other), other))).toEqual({
      status: 'different_metadata', differences: ['payment_days'],
    });
  });

  it('compares equal verified metadata without declaring statistical availability', () => {
    const result = valid(request(), receipt(), attest());
    expect(compareManualComparability(result, result)).toEqual({ status: 'matching_verified_metadata', differences: [] });
  });

  it('does not compare monetary prices as metadata or silently allow quantity discounts', () => {
    const other = receipt(4, '150.00');
    expect(compareManualComparability(valid(), valid(request(other), other)).differences).toEqual(['quantity']);
    const a = request(); a.attributes.quantity_pricing!.value = { regime: 'quantity_independent' };
    const b = request(other); b.attributes.quantity_pricing!.value = { regime: 'quantity_independent' };
    expect(compareManualComparability(valid(a), valid(b, other))).toEqual({ status: 'unverified', differences: [] });
  });

  it('compares packaging decimal values exactly, without binary floating point', () => {
    const other = request(); other.attributes.packaging!.value.quantity_per_package = '50';
    expect(compareManualComparability(valid(), valid(other)).differences).toEqual([]);
  });
});
