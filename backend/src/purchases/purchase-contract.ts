import { createHash } from 'node:crypto';
import { PURCHASE_CATALOG } from './purchase-catalog.js';

export const PURCHASE_CONTRACT = 'p4-purchase/1.0';
export const PURCHASE_TIME_ZONE = 'America/Sao_Paulo';

// HTTP/Prisma-independent JSON boundary. Prices use decimal strings with a dot,
// never JSON numbers, currency symbols, grouping separators or rounding.
export interface PurchaseRequest {
  contract: typeof PURCHASE_CONTRACT;
  origin: 'manual';
  idempotency_key: string; // UUID v4 for one submission; retries reuse it.
  purchase: {
    supplier_id: string;
    product_id: string;
    department_id: string;
    quantity: number;
    unit_price: string;
    currency: 'BRL';
    purchase_date: string; // Civil date, not approval or historical availability.
    payment_days: number;
  };
}

export type PurchaseErrorCode =
  | 'P4_INVALID_STRUCTURE' | 'P4_UNSUPPORTED_CONTRACT' | 'P4_INVALID_ORIGIN'
  | 'P4_INVALID_IDEMPOTENCY_KEY' | 'P4_UNAUTHORIZED_CATALOG_ENTRY'
  | 'P4_INVALID_CURRENCY' | 'P4_INVALID_QUANTITY' | 'P4_INVALID_UNIT_PRICE'
  | 'P4_INVALID_PAYMENT_DAYS' | 'P4_INVALID_PURCHASE_DATE' | 'P4_FUTURE_PURCHASE_DATE'
  | 'P4_INVALID_CLOCK' | 'P4_INVALID_IDEMPOTENCY_RECORD' | 'P4_IDEMPOTENCY_CONFLICT'
  | 'P4_VALIDATION_FAILED';
type Field = keyof PurchaseRequest | keyof PurchaseRequest['purchase'] | 'server_clock' | 'request';
export type PurchaseFailure = { ok: false; error: { code: PurchaseErrorCode; field: Field } };

class InvalidPurchase extends Error {
  constructor(readonly code: PurchaseErrorCode, readonly field: Field) { super(code); }
}
function check(condition: unknown, code: PurchaseErrorCode, field: Field): asserts condition {
  if (!condition) throw new InvalidPurchase(code, field);
}
function failure(error: unknown): PurchaseFailure {
  return { ok: false, error: error instanceof InvalidPurchase
    ? { code: error.code, field: error.field }
    : { code: 'P4_VALIDATION_FAILED', field: 'request' } };
}
function object(value: unknown, keys: readonly string[], field: Field): Record<string, unknown> {
  check(value !== null && typeof value === 'object' && !Array.isArray(value), 'P4_INVALID_STRUCTURE', field);
  check(Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null, 'P4_INVALID_STRUCTURE', field);
  check(Reflect.ownKeys(value).length === keys.length && keys.every((key) => {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return descriptor?.enumerable && Object.hasOwn(descriptor, 'value');
  }), 'P4_INVALID_STRUCTURE', field);
  return value as Record<string, unknown>;
}
function matches(value: unknown, pattern: RegExp): value is string {
  // JS '$' can match before a final newline; require the match to consume all bytes.
  return typeof value === 'string' && pattern.exec(value)?.[0] === value;
}
function civilDate(value: unknown): value is string {
  if (!matches(value, /^\d{4}-\d{2}-\d{2}$/)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return year >= 1 && month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1];
}
function commercialToday(now: Date): string {
  check(now instanceof Date && Number.isFinite(now.getTime()) && now.getUTCFullYear() >= 1
    && now.getUTCFullYear() <= 9999, 'P4_INVALID_CLOCK', 'server_clock');
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: PURCHASE_TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const part = (name: string) => parts.find(({ type }) => type === name)?.value ?? '';
  const today = `${part('year').padStart(4, '0')}-${part('month')}-${part('day')}`;
  check(civilDate(today), 'P4_INVALID_CLOCK', 'server_clock');
  return today;
}
function entry<T extends { readonly id: string }>(entries: readonly T[], id: unknown, field: Field): T {
  const found = entries.find((candidate) => candidate.id === id);
  check(found, 'P4_UNAUTHORIZED_CATALOG_ENTRY', field);
  return found;
}
function decimal(cents: bigint): string {
  return `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`;
}
function freeze<T>(value: T): Readonly<T> {
  if (value !== null && typeof value === 'object') {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
}

function prepareValidated(input: unknown, now: Date) {
  const today = commercialToday(now); // Trusted injected server clock, never a request field.
  const request = object(input, ['contract', 'origin', 'idempotency_key', 'purchase'], 'request');
  check(request.contract === PURCHASE_CONTRACT, 'P4_UNSUPPORTED_CONTRACT', 'contract');
  check(request.origin === 'manual', 'P4_INVALID_ORIGIN', 'origin');
  check(matches(request.idempotency_key, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i),
    'P4_INVALID_IDEMPOTENCY_KEY', 'idempotency_key');
  const purchase = object(request.purchase, [
    'supplier_id', 'product_id', 'department_id', 'quantity', 'unit_price', 'currency', 'purchase_date', 'payment_days',
  ], 'purchase');
  const supplier = entry(PURCHASE_CATALOG.suppliers, purchase.supplier_id, 'supplier_id');
  const product = entry(PURCHASE_CATALOG.products, purchase.product_id, 'product_id');
  const department = entry(PURCHASE_CATALOG.departments, purchase.department_id, 'department_id');
  check(purchase.currency === 'BRL', 'P4_INVALID_CURRENCY', 'currency');
  const quantity = purchase.quantity;
  check(typeof quantity === 'number' && Number.isSafeInteger(quantity) && quantity >= 1 && quantity <= 1_000_000,
    'P4_INVALID_QUANTITY', 'quantity');
  const price = purchase.unit_price;
  check(matches(price, /^(0|[1-9]\d{0,6})(?:\.\d{1,2})?$/), 'P4_INVALID_UNIT_PRICE', 'unit_price');
  const [whole, fraction = ''] = price.split('.');
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
  check(cents > 0n && cents <= 100_000_000n, 'P4_INVALID_UNIT_PRICE', 'unit_price');
  const days = purchase.payment_days;
  check(typeof days === 'number' && Number.isSafeInteger(days) && days >= 0 && days <= 3650,
    'P4_INVALID_PAYMENT_DAYS', 'payment_days');
  check(civilDate(purchase.purchase_date), 'P4_INVALID_PURCHASE_DATE', 'purchase_date');
  check(purchase.purchase_date <= today, 'P4_FUTURE_PURCHASE_DATE', 'purchase_date');

  const unitPrice = decimal(cents);
  const total = decimal(cents * BigInt(quantity));
  // Fixed construction order is the p4-purchase/1.0 content-hash serialization.
  // No key, validation timestamp, database ID or analysis status enters this hash.
  const original = {
    contract: PURCHASE_CONTRACT, origin: 'manual' as const,
    catalog_version: PURCHASE_CATALOG.version, catalog_origin: PURCHASE_CATALOG.origin,
    purchase: {
      supplier: { ...supplier }, product: { ...product }, department: { ...department },
      quantity, unit_price: unitPrice, total, currency: 'BRL' as const,
      purchase_date: purchase.purchase_date, payment_days: days === 0 ? 0 : days,
    },
  };
  return freeze({
    contract: PURCHASE_CONTRACT, validated_at: now.toISOString(),
    source: {
      source_namespace: 'p4-manual/1.0', source_entity_kind: 'purchase_order_line' as const,
      source_id: request.idempotency_key.toLowerCase(),
    },
    original_content: original,
    content_sha256: createHash('sha256').update(JSON.stringify(original), 'utf8').digest('hex'),
    // Only the scalar whitelist accepted by app.write_purchase_order_line.
    state: {
      description: product.name, po_date: purchase.purchase_date,
      quantity: String(quantity), unit_price: unitPrice, amount: total,
    },
    // A future repository must resolve these to real UUIDs, plus a trusted actor.
    // They are never passed as UUIDs or embedded into the SQL scalar state.
    references: {
      catalog_namespace: PURCHASE_CATALOG.version, supplier_source_id: supplier.id,
      department_source_id: department.id, currency_code: 'BRL' as const,
    },
    analysis: {
      status: 'unavailable' as const,
      reason: 'manual_source_incompatible_with_procurement_v2' as const,
    },
  });
}

export type PreparedPurchase = ReturnType<typeof prepareValidated>;
export type PurchasePreparation = { ok: true; value: PreparedPurchase } | PurchaseFailure;

/** Pure preparation, not a saved record. DB recorded_at must come from the DB,
 * not purchase_date/validated_at. No claim of historical availability is made. */
export function preparePurchase(input: unknown, now: Date): PurchasePreparation {
  try { return { ok: true, value: prepareValidated(input, now) }; }
  catch (error) { return failure(error); }
}

/** Compare a trusted prepared submission with the receipt retrieved for this key.
 * null means a confirmed absence, not a failed lookup. This performs no lookup,
 * reservation or write: atomic uniqueness/replay still requires a transaction.
 * Compare the stored hash; PostgreSQL JSONB serialization is not this hash format. */
export function checkPurchaseIdempotency(candidate: PreparedPurchase, existing: unknown):
  { ok: true; outcome: 'new' | 'replay' } | PurchaseFailure {
  if (existing === null) return { ok: true, outcome: 'new' };
  try {
    let receipt: Record<string, unknown>;
    try {
      receipt = object(existing, ['source_namespace', 'source_entity_kind', 'source_id', 'content_sha256'], 'idempotency_key');
    } catch { throw new InvalidPurchase('P4_INVALID_IDEMPOTENCY_RECORD', 'idempotency_key'); }
    check(receipt.source_namespace === candidate.source.source_namespace
      && receipt.source_entity_kind === candidate.source.source_entity_kind
      && receipt.source_id === candidate.source.source_id
      && matches(receipt.content_sha256, /^[0-9a-f]{64}$/), 'P4_INVALID_IDEMPOTENCY_RECORD', 'idempotency_key');
    check(receipt.content_sha256 === candidate.content_sha256, 'P4_IDEMPOTENCY_CONFLICT', 'idempotency_key');
    return { ok: true, outcome: 'replay' };
  } catch (error) { return failure(error); }
}
