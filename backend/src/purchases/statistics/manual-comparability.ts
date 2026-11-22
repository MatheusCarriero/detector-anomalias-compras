import { createHash } from 'node:crypto';
import type { PurchaseRecord } from '../purchase-repository.js';

export const MANUAL_COMPARABILITY_CONTRACT = 'p4-manual-comparability/1.0';
export const COMPARABILITY_FIELDS = Object.freeze([
  'specification', 'unit', 'packaging', 'currency', 'price_basis', 'payment_days', 'delivery', 'quantity_pricing',
] as const);
type Field = (typeof COMPARABILITY_FIELDS)[number];
interface Values {
  specification: { id: string; version: string; product_id: string; sha256: string };
  unit: string; // Exact purchased/priced unit label, not a conversion inferred from its name.
  packaging: { id: string; version: string; quantity_per_package: string; content_unit: string };
  currency: 'BRL';
  price_basis: {
    id: string; version: string;
    discounts: 'deducted' | 'not_deducted' | 'not_applicable';
    taxes: 'included' | 'excluded'; tax_credits: 'none' | 'deducted' | 'not_deducted';
    freight: 'included' | 'excluded' | 'not_applicable';
    other_charges: 'included' | 'excluded' | 'not_applicable';
  };
  payment_days: number;
  delivery: { condition_id: string; condition_version: string; location_id: string };
  quantity_pricing: { regime: 'same_quantity_only' | 'quantity_independent' } |
    { regime: 'tier'; schedule_id: string; schedule_version: string; min_quantity: number; max_quantity: number };
}
interface Declaration { kind: 'declared'; actor_id: string; declared_at: string; evidence_ref?: string }
type Attributes = { [F in Field]?: { value: Values[F]; provenance: Declaration } };
export interface ManualComparabilityRequest {
  contract: typeof MANUAL_COMPARABILITY_CONTRACT;
  id: string; revision: number;
  supersedes: { id: string; revision: number; content_sha256: string } | null;
  purchase: { id: string; version_id: string; content_sha256: string };
  attributes: Attributes;
}

/** Internal attestation, NEVER accepted inside the declarant's request. A future
 * authorized verifier must resolve evidence and identity before supplying this.
 * A hash binds a statement; it does not establish commercial truth by itself. */
export interface TrustedVerification {
  field: Field; comparability_sha256: string; evidence_id: string; verified_by: string; verified_at: string;
}
interface Context { purchase: PurchaseRecord; now: Date; verifications?: readonly TrustedVerification[] }
type Code = 'invalid_structure' | 'invalid_value' | 'unsupported_contract' | 'receipt_mismatch' |
  'invalid_revision' | 'invalid_context' | 'invalid_verification';
class Invalid extends Error {
  constructor(readonly code: Code, readonly field: string) { super(code); }
}
function check(ok: unknown, field: string, code: Code = 'invalid_value'): asserts ok {
  if (!ok) throw new Invalid(code, field);
}
function object(value: unknown, allowed: readonly string[], field: string, required = allowed): Record<string, unknown> {
  check(value !== null && typeof value === 'object' && !Array.isArray(value), field, 'invalid_structure');
  check(Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null, field, 'invalid_structure');
  check(Reflect.ownKeys(value).every(key => typeof key === 'string' && allowed.includes(key)
    && Object.getOwnPropertyDescriptor(value, key)?.enumerable
    && Object.hasOwn(Object.getOwnPropertyDescriptor(value, key)!, 'value'))
    && required.every(key => Object.hasOwn(value, key)), field, 'invalid_structure');
  return value as Record<string, unknown>;
}
function matches(value: unknown, pattern: RegExp): value is string {
  return typeof value === 'string' && pattern.exec(value)?.[0] === value;
}
function text(value: unknown, field: string): asserts value is string {
  check(typeof value === 'string' && value.length > 0 && value.length <= 200 && value.trim() === value
    && !Array.from(value).some(c => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127), field);
}
function uuid(value: unknown, field: string) {
  check(matches(value, /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/), field);
}
function hash(value: unknown, field: string) { check(matches(value, /^[0-9a-f]{64}$/), field); }
function instant(value: unknown, field: string): asserts value is string {
  check(matches(value, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
    && value.slice(0, 4) !== '0000' && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value, field);
}
function integer(value: unknown, min: number, max: number, field: string): asserts value is number {
  check(typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max, field);
}
function decimalUnits(value: unknown, field: string): bigint {
  check(matches(value, /^(0|[1-9]\d{0,8})(\.\d{1,6})?$/), field);
  const [whole, fraction = ''] = value.split('.');
  const units = BigInt(whole) * 1_000_000n + BigInt(fraction.padEnd(6, '0'));
  check(units > 0n, field); return units;
}
function choice(value: unknown, options: readonly string[], field: string) {
  check(typeof value === 'string' && options.includes(value), field);
}
function valueFor(field: Field, value: unknown, purchase: PurchaseRecord['purchase']) {
  const path = `attributes.${field}.value`;
  switch (field) {
    case 'specification': {
      const v = object(value, ['id', 'version', 'product_id', 'sha256'], path);
      text(v.id, path); text(v.version, path); hash(v.sha256, path);
      check(v.product_id === purchase.product.id, path, 'receipt_mismatch'); break;
    }
    case 'unit': text(value, path); check(value === purchase.product.unit, path, 'receipt_mismatch'); break;
    case 'packaging': {
      const v = object(value, ['id', 'version', 'quantity_per_package', 'content_unit'], path);
      text(v.id, path); text(v.version, path); text(v.content_unit, path); decimalUnits(v.quantity_per_package, path); break;
    }
    case 'currency': check(value === 'BRL' && value === purchase.currency, path, 'receipt_mismatch'); break;
    case 'price_basis': {
      const v = object(value, ['id', 'version', 'discounts', 'taxes', 'tax_credits', 'freight', 'other_charges'], path);
      text(v.id, path); text(v.version, path);
      choice(v.discounts, ['deducted', 'not_deducted', 'not_applicable'], path);
      choice(v.taxes, ['included', 'excluded'], path);
      choice(v.tax_credits, ['none', 'deducted', 'not_deducted'], path);
      choice(v.freight, ['included', 'excluded', 'not_applicable'], path);
      choice(v.other_charges, ['included', 'excluded', 'not_applicable'], path); break;
    }
    case 'payment_days': integer(value, 0, 3650, path); check(value === purchase.payment_days, path, 'receipt_mismatch'); break;
    case 'delivery': {
      const v = object(value, ['condition_id', 'condition_version', 'location_id'], path);
      for (const part of Object.values(v)) text(part, path); break;
    }
    case 'quantity_pricing': {
      const v = object(value, ['regime', 'schedule_id', 'schedule_version', 'min_quantity', 'max_quantity'], path, ['regime']);
      choice(v.regime, ['same_quantity_only', 'quantity_independent', 'tier'], path);
      if (v.regime === 'tier') {
        object(v, ['regime', 'schedule_id', 'schedule_version', 'min_quantity', 'max_quantity'], path);
        text(v.schedule_id, path); text(v.schedule_version, path);
        integer(v.min_quantity, 1, 1_000_000, path); integer(v.max_quantity, 1, 1_000_000, path);
        check(v.min_quantity <= purchase.quantity && purchase.quantity <= v.max_quantity, path, 'receipt_mismatch');
      } else object(v, ['regime'], path);
    }
  }
}

// Canonical object-key order makes identity independent of request key order.
// Only validated JSON objects/scalars reach this function; no rounding of money.
function canonical(value: unknown): string {
  if (value !== null && typeof value === 'object') {
    const v = value as Record<string, unknown>;
    return `{${Object.keys(v).sort().map(key => `${JSON.stringify(key)}:${canonical(v[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}
function freeze<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
}
type Diagnostic = { category: 'missing' | 'unverified'; code: 'required_information_missing' | 'verification_required'; field: Field };

function validate(input: unknown, context: Context) {
  const { purchase: receipt, now } = context;
  check(now instanceof Date && Number.isFinite(now.getTime()) && now.getUTCFullYear() >= 1 && now.getUTCFullYear() <= 9999, 'now', 'invalid_context');
  const validatedAt = now.toISOString();
  check(receipt.recorded_at <= validatedAt, 'purchase.recorded_at', 'invalid_context');
  const r = object(input, ['contract', 'id', 'revision', 'supersedes', 'purchase', 'attributes'], 'request');
  check(r.contract === MANUAL_COMPARABILITY_CONTRACT, 'contract', 'unsupported_contract');
  uuid(r.id, 'id'); integer(r.revision, 1, Number.MAX_SAFE_INTEGER, 'revision');
  if (r.revision === 1) check(r.supersedes === null, 'supersedes', 'invalid_revision');
  else {
    const previous = object(r.supersedes, ['id', 'revision', 'content_sha256'], 'supersedes');
    uuid(previous.id, 'supersedes.id'); hash(previous.content_sha256, 'supersedes.content_sha256');
    check(previous.id !== r.id && previous.revision === r.revision - 1, 'supersedes', 'invalid_revision');
  }
  const link = object(r.purchase, ['id', 'version_id', 'content_sha256'], 'purchase');
  check(link.id === receipt.id && link.version_id === receipt.version_id && link.content_sha256 === receipt.content_sha256,
    'purchase', 'receipt_mismatch');
  const attributes = object(r.attributes, COMPARABILITY_FIELDS, 'attributes', []);
  for (const field of COMPARABILITY_FIELDS) {
    if (!Object.hasOwn(attributes, field)) continue;
    const entry = object(attributes[field], ['value', 'provenance'], `attributes.${field}`);
    valueFor(field, entry.value, receipt.purchase);
    const p = object(entry.provenance, ['kind', 'actor_id', 'declared_at', 'evidence_ref'], `attributes.${field}.provenance`, ['kind', 'actor_id', 'declared_at']);
    check(p.kind === 'declared', `attributes.${field}.provenance.kind`);
    text(p.actor_id, `attributes.${field}.provenance.actor_id`);
    instant(p.declared_at, `attributes.${field}.provenance.declared_at`);
    check(p.declared_at <= validatedAt, `attributes.${field}.provenance.declared_at`);
    if (Object.hasOwn(p, 'evidence_ref')) text(p.evidence_ref, `attributes.${field}.provenance.evidence_ref`);
  }
  const serialized = canonical(r);
  const content = JSON.parse(serialized) as ManualComparabilityRequest;
  const contentHash = createHash('sha256').update(serialized, 'utf8').digest('hex');
  const verified = new Map<Field, TrustedVerification>();
  const attestations = context.verifications ?? [];
  check(Array.isArray(attestations) && attestations.length <= COMPARABILITY_FIELDS.length, 'verifications', 'invalid_verification');
  for (const attestation of attestations) {
    const a = object(attestation, ['field', 'comparability_sha256', 'evidence_id', 'verified_by', 'verified_at'], 'verifications');
    check(COMPARABILITY_FIELDS.includes(a.field as Field), 'verifications', 'invalid_verification');
    const field = a.field as Field;
    const declared = content.attributes[field];
    check(declared && !verified.has(field) && a.comparability_sha256 === contentHash, 'verifications', 'invalid_verification');
    text(a.evidence_id, 'verifications.evidence_id'); text(a.verified_by, 'verifications.verified_by');
    instant(a.verified_at, 'verifications.verified_at');
    check(a.verified_at >= declared.provenance.declared_at && a.verified_at <= validatedAt, 'verifications', 'invalid_verification');
    verified.set(field, { ...attestation });
  }
  const diagnostics: Diagnostic[] = [];
  const provenance: Partial<Record<Field, { status: 'declared' } | { status: 'verified'; verification: TrustedVerification }>> = {};
  for (const field of COMPARABILITY_FIELDS) {
    if (!content.attributes[field]) diagnostics.push({ category: 'missing', code: 'required_information_missing', field });
    else {
      const verification = verified.get(field);
      provenance[field] = verification ? { status: 'verified', verification } : { status: 'declared' };
      if (!verification) diagnostics.push({ category: 'unverified', code: 'verification_required', field });
    }
  }
  return freeze({
    content, content_sha256: contentHash, validated_at: validatedAt,
    status: diagnostics.some(d => d.category === 'missing') ? 'incomplete' as const
      : diagnostics.length ? 'unverified' as const : 'verified_metadata' as const,
    provenance, diagnostics,
    purchase_evidence: {
      ...content.purchase, revision_no: receipt.revision_no, source_reference_id: receipt.source_reference_id,
      source: { ...receipt.source }, recorded_at: receipt.recorded_at, product_id: receipt.purchase.product.id,
      quantity: receipt.purchase.quantity, unit_price: receipt.purchase.unit_price, total: receipt.purchase.total,
    },
  });
}
export type ValidatedManualComparability = ReturnType<typeof validate>;

/** Pure validation for a repository-verified receipt and trusted server context.
 * No receipt mutation, backfill, evidence lookup or availability certification.
 * The supersedes chain is structurally checked; future persistence must enforce
 * predecessor existence, ownership, uniqueness and atomic revision ordering.
 * Package content is declared per ONE purchased/priced unit. Price-basis and
 * delivery IDs/versions identify full external definitions, not free-text proof.
 * Metadata verification never authorizes p4-price-analysis/1.0 execution.
 */
export function validateManualComparability(input: unknown, context: Context):
  { ok: true; value: ValidatedManualComparability } | { ok: false; error: { code: Code; field: string } } {
  try { return { ok: true, value: validate(input, context) }; }
  catch (error) {
    return { ok: false, error: error instanceof Invalid ? { code: error.code, field: error.field }
      : { code: 'invalid_context', field: 'context' } };
  }
}

/** Compares already validated metadata only. Matching verified metadata does
 * not establish historical coverage, temporal eligibility or statistical risk.
 * No price conversions, normalization of units or specification lookup. */
export function compareManualComparability(a: ValidatedManualComparability, b: ValidatedManualComparability) {
  const differences: string[] = [];
  for (const field of COMPARABILITY_FIELDS) {
    const left = a.content.attributes[field]?.value; const right = b.content.attributes[field]?.value;
    if (left === undefined || right === undefined) continue;
    if (field === 'packaging') {
      const l = a.content.attributes.packaging!.value; const r = b.content.attributes.packaging!.value;
      if (l.id !== r.id || l.version !== r.version || l.content_unit !== r.content_unit
        || decimalUnits(l.quantity_per_package, field) !== decimalUnits(r.quantity_per_package, field)) differences.push(field);
    } else if (canonical(left) !== canonical(right)) differences.push(field);
  }
  if (a.purchase_evidence.product_id !== b.purchase_evidence.product_id) differences.push('product_id');
  if (a.content.attributes.quantity_pricing?.value.regime === 'same_quantity_only'
    && b.content.attributes.quantity_pricing?.value.regime === 'same_quantity_only'
    && a.purchase_evidence.quantity !== b.purchase_evidence.quantity) differences.push('quantity');
  return { status: differences.length ? 'different_metadata' as const
    : a.status === 'incomplete' || b.status === 'incomplete' ? 'incomplete' as const
    : a.status !== 'verified_metadata' || b.status !== 'verified_metadata' ? 'unverified' as const
    : 'matching_verified_metadata' as const, differences };
}
