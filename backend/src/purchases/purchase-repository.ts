import { isDeepStrictEqual } from 'node:util';
import { Prisma } from '../../generated/prisma/client.js';
import { PrismaService } from '../prisma/prisma.service.js';
import type { DatabaseTransaction } from '../prisma/prisma.service.js';
import { checkPurchaseIdempotency, preparePurchase, PURCHASE_CONTRACT } from './purchase-contract.js';
import type { PreparedPurchase, PurchaseErrorCode } from './purchase-contract.js';
import { PURCHASE_CATALOG } from './purchase-catalog.js';

type StorageCode = 'P4_STORAGE_FAILURE' | 'P4_STORAGE_PERMISSION' | 'P4_STORAGE_INTEGRITY'
  | 'P4_STORAGE_BUSY' | 'P4_REFERENCE_UNAVAILABLE' | 'P4_INVALID_QUERY' | 'P4_NOT_FOUND';
export type RepositoryResult<T> = { ok: true; value: T } | { ok: false; error: { code: StorageCode | PurchaseErrorCode } };
export interface PurchaseRepositoryConfig { technicalUser: { issuer: string; subject: string } }
export interface PurchaseCursor { recorded_at: string; id: string }
export interface PurchaseRecord {
  id: string; version_id: string; revision_no: number; recorded_at: string; source_reference_id: string;
  purchase: PreparedPurchase['original_content']['purchase'];
  source: PreparedPurchase['source']; content_sha256: string; analysis: PreparedPurchase['analysis'];
}
class RepositoryError extends Error {
  constructor(readonly code: StorageCode | PurchaseErrorCode) { super(code); }
}
class DuplicateSubmission extends Error {}
function ensure(condition: unknown, code: StorageCode | PurchaseErrorCode = 'P4_STORAGE_INTEGRITY'): asserts condition {
  if (!condition) throw new RepositoryError(code);
}
function object(value: unknown): Record<string, unknown> {
  ensure(value !== null && typeof value === 'object' && !Array.isArray(value));
  return value as Record<string, unknown>;
}
function shape(value: unknown, keys: readonly string[]): Record<string, unknown> {
  const row = object(value);
  ensure(Object.keys(row).length === keys.length && keys.every(key => Object.hasOwn(row, key)));
  return row;
}
function uuid(value: unknown): value is string {
  return typeof value === 'string' && value.length === 36 && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value);
}
function instant(value: unknown): value is string {
  return typeof value === 'string' && value.length === 24 && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
}
function one(rows: unknown): Record<string, unknown> {
  ensure(Array.isArray(rows) && rows.length === 1); return object(rows[0]);
}
function returnedId(rows: unknown): string { const row = one(rows); ensure(uuid(row.id)); return row.id; }
function envelope(rows: unknown, fields: readonly string[]): Record<string, unknown> {
  const row = shape(one(rows), ['result']);
  const result = shape(row.result, ['contract', ...fields]);
  ensure(result.contract === 'p4-storage/1.0');
  return result;
}
function numeric(value: unknown): string {
  ensure(typeof value === 'string' && value.length <= 40 && /^(0|[1-9]\d*)(\.\d+)?$/.exec(value)?.[0] === value);
  const [whole, fraction = ''] = value.split('.'); return `${whole}.${fraction.replace(/0+$/, '')}`;
}
function sqlState(error: unknown): string | undefined {
  if (!error || typeof error !== 'object') return;
  const e = error as { code?: unknown; meta?: { driverAdapterError?: { cause?: { originalCode?: unknown } } } };
  const code = e.code === 'P2010' ? e.meta?.driverAdapterError?.cause?.originalCode : e.code;
  return typeof code === 'string' && code.length === 5 && /^[0-9]{2}[0-9A-Z]{3}$/.test(code) ? code : undefined;
}
function failure(error: unknown): { ok: false; error: { code: StorageCode | PurchaseErrorCode } } {
  if (error instanceof RepositoryError) return { ok: false, error: { code: error.code } };
  const state = sqlState(error);
  const code: StorageCode = state === '42501' ? 'P4_STORAGE_PERMISSION'
    : ['23503', '23505', '23514', '22023', '55000'].includes(state ?? '') ? 'P4_STORAGE_INTEGRITY'
    : ['40001', '40P01', '55P03', '57014'].includes(state ?? '') ? 'P4_STORAGE_BUSY' : 'P4_STORAGE_FAILURE';
  // Never inspect/return driver messages, details, queries, credentials or stacks.
  return { ok: false, error: { code } };
}

function decode(row: Record<string, unknown>): PurchaseRecord {
  shape(row, ['id', 'version_id', 'revision_no', 'recorded_at', 'source_reference_id', 'source_identity_id',
    'source_namespace', 'source_entity_kind', 'source_id', 'reference_namespace', 'reference_kind',
    'source_version', 'source_record_key', 'content_hash', 'original_content', 'payload_schema', 'state',
    'currency_code', 'supplier_matches', 'department_matches']);
  ensure(uuid(row.id) && uuid(row.version_id) && uuid(row.source_reference_id) && instant(row.recorded_at));
  ensure(row.revision_no === 1 && row.payload_schema === 1 && row.source_identity_id === null);
  ensure(row.source_namespace === 'p4-manual/1.0' && row.reference_namespace === row.source_namespace
    && row.source_entity_kind === 'purchase_order_line' && row.reference_kind === row.source_entity_kind
    && row.source_record_key === row.source_id && row.source_version === PURCHASE_CONTRACT);
  const original = object(row.original_content); const p = object(original.purchase);
  // A stored receipt is checked at its immutable registration instant, using
  // P4.2's Sao Paulo civil-date rule; the current clock cannot legitimize it later.
  const checked = preparePurchase({
    contract: original.contract, origin: original.origin, idempotency_key: row.source_id,
    purchase: {
      supplier_id: object(p.supplier).id, product_id: object(p.product).id, department_id: object(p.department).id,
      quantity: p.quantity, unit_price: p.unit_price, currency: p.currency, purchase_date: p.purchase_date, payment_days: p.payment_days,
    },
  }, new Date(row.recorded_at));
  ensure(checked.ok); const expected = checked.value;
  ensure(isDeepStrictEqual(original, expected.original_content) && row.content_hash === expected.content_sha256);
  ensure(row.currency_code === 'BRL' && row.supplier_matches === true && row.department_matches === true);
  const state = object(row.state);
  ensure(Object.keys(state).length === 5 && state.description === expected.state.description && state.po_date === expected.state.po_date);
  for (const key of ['quantity', 'unit_price', 'amount'] as const) ensure(numeric(state[key]) === numeric(expected.state[key]));
  return { id: row.id, version_id: row.version_id, revision_no: 1, recorded_at: row.recorded_at,
    source_reference_id: row.source_reference_id, purchase: expected.original_content.purchase,
    source: expected.source, content_sha256: expected.content_sha256, analysis: expected.analysis };
}
function decodeReceipt(rows: unknown): PurchaseRecord | null {
  const result = envelope(rows, ['status', 'receipt']);
  ensure(result.status === 'absent' || result.status === 'found');
  if (result.status === 'absent') { ensure(result.receipt === null); return null; }
  return decode(object(result.receipt));
}
function mappings(value: unknown, catalog: readonly { id: string }[]): Map<string, string> {
  const expected = catalog.map(entry => entry.id).sort();
  ensure(Array.isArray(value) && value.length === expected.length);
  const result = new Map<string, string>();
  value.forEach((entry, index) => {
    const row = shape(entry, ['source_id', 'id']);
    ensure(row.source_id === expected[index] && uuid(row.id));
    result.set(expected[index], row.id);
  });
  ensure(new Set(result.values()).size === result.size);
  return result;
}
function earlier(a: PurchaseCursor, b: PurchaseCursor): boolean {
  return a.recorded_at < b.recorded_at || (a.recorded_at === b.recorded_at && a.id < b.id);
}

/** No module registration/HTTP/env defaults. The future application supplies an
 * explicitly provisioned active technical user; this is not human authentication.
 * Reads are creation history only; editing purchases is outside this increment. */
export class PurchaseRepository {
  private readonly actor: Readonly<{ issuer: string; subject: string }>;
  constructor(private readonly prisma: PrismaService, config: PurchaseRepositoryConfig, private readonly clock: () => Date = () => new Date()) {
    const actor = config?.technicalUser;
    if (!actor || ![actor.issuer, actor.subject].every(v => typeof v === 'string' && v.length > 0 && v.length <= 200
      && v.trim() === v && !Array.from(v).some(c => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127))) throw new Error('P4_INVALID_REPOSITORY_CONFIG');
    this.actor = Object.freeze({ ...actor });
  }

  private async read(tx: DatabaseTransaction, id: string): Promise<PurchaseRecord | null> {
    const rows = await tx.$queryRaw(Prisma.sql`SELECT app.p4_v1_receipt_by_id(${id}::uuid) AS result`);
    const purchase = decodeReceipt(rows); ensure(!purchase || purchase.id === id); return purchase;
  }
  private async replay(tx: DatabaseTransaction, candidate: PreparedPurchase) {
    const rows = await tx.$queryRaw(Prisma.sql`SELECT app.p4_v1_receipt_by_key(${candidate.source.source_id}::uuid) AS result`);
    const record = decodeReceipt(rows); if (!record) return null;
    const comparison = checkPurchaseIdempotency(candidate, { ...record.source, content_sha256: record.content_sha256 });
    if (!comparison.ok) throw new RepositoryError(comparison.error.code);
    return record;
  }
  private async context(tx: DatabaseTransaction, candidate: PreparedPurchase) {
    let rows: unknown;
    try { rows = await tx.$queryRaw(Prisma.sql`SELECT app.p4_v1_context() AS result`); }
    catch (error) {
      if (sqlState(error) === '55000') throw new RepositoryError('P4_REFERENCE_UNAVAILABLE');
      throw error;
    }
    const result = envelope(rows, ['catalog_version', 'actor', 'currency', 'suppliers', 'departments']);
    ensure(result.catalog_version === PURCHASE_CATALOG.version && result.catalog_version === candidate.references.catalog_namespace);
    const actor = shape(result.actor, ['id', 'issuer', 'subject']);
    ensure(uuid(actor.id) && actor.issuer === 'p4-demo' && actor.subject === 'manual-purchase-service');
    ensure(actor.issuer === this.actor.issuer && actor.subject === this.actor.subject, 'P4_REFERENCE_UNAVAILABLE');
    const currency = shape(result.currency, ['id', 'code']); ensure(uuid(currency.id) && currency.code === 'BRL');
    const suppliers = mappings(result.suppliers, PURCHASE_CATALOG.suppliers);
    const departments = mappings(result.departments, PURCHASE_CATALOG.departments);
    const supplier = suppliers.get(candidate.references.supplier_source_id);
    const department = departments.get(candidate.references.department_source_id);
    ensure(supplier && department);
    return { actor: actor.id, supplier_id: supplier, department_id: department, currency_id: currency.id };
  }

  async create(input: unknown): Promise<RepositoryResult<{ outcome: 'created' | 'replay'; purchase: PurchaseRecord }>> {
    let now: Date; let candidate: PreparedPurchase;
    try {
      now = this.clock(); const result = preparePurchase(input, now); if (!result.ok) return result;
      candidate = result.value;
    } catch (error) { return failure(error); }
    try {
      const value = await this.prisma.transaction(async tx => {
        const existing = await this.replay(tx, candidate);
        if (existing) return { outcome: 'replay' as const, purchase: existing };
        const references = await this.context(tx, candidate); const actor = references.actor;
        let identityId: string;
        try {
          identityId = returnedId(await tx.$queryRaw(Prisma.sql`
            SELECT app.register_source_identity(${candidate.source.source_namespace}::text, 'purchase_order_line'::text,
              ${candidate.source.source_id}::text, ${actor}::uuid) AS id`));
        } catch (error) {
          // Only a unique violation at reservation can be a competing submission.
          // Escape the callback: no query is allowed in that aborted transaction.
          if (sqlState(error) === '23505') throw new DuplicateSubmission();
          throw error;
        }
        // check_version_insert rejects unresolved identities. The supported NULL
        // identity reference is linked directly to the new version by FK, with
        // the canonical submission key retained in source_record_key. Never
        // disable that trigger, revise artificially or UPDATE an immutable source.
        const sourceId = returnedId(await tx.$queryRaw(Prisma.sql`
          SELECT app.observe_source(${candidate.source.source_namespace}::text, 'purchase_order_line'::text,
            ${actor}::uuid, NULL::uuid, ${PURCHASE_CONTRACT}::text, ${candidate.source.source_id}::text,
            NULL::text, ${candidate.content_sha256}::text, ${JSON.stringify(candidate.original_content)}::jsonb, NULL::text) AS id`));
        const created = one(await tx.$queryRaw(Prisma.sql`
          SELECT * FROM app.write_purchase_order_line(NULL::uuid, NULL::uuid, ${JSON.stringify(candidate.state)}::jsonb,
            ${references.supplier_id}::uuid, ${references.department_id}::uuid, ${references.currency_id}::uuid,
            ${actor}::uuid, ${sourceId}::uuid, NULL::text, NULL::text)`));
        ensure(uuid(created.entity_id) && uuid(created.version_id) && created.revision_no === 1);
        const resolved = one(await tx.$queryRaw(Prisma.sql`
          SELECT 1 AS resolved FROM app.resolve_source_identity(${identityId}::uuid, NULL::uuid, NULL::uuid, ${created.entity_id}::uuid, ${actor}::uuid)`));
        ensure(resolved.resolved === 1);
        const purchase = await this.read(tx, created.entity_id);
        ensure(purchase && purchase.version_id === created.version_id && purchase.source_reference_id === sourceId
          && purchase.source.source_id === candidate.source.source_id && purchase.content_sha256 === candidate.content_sha256);
        await tx.$executeRaw(Prisma.sql`SET CONSTRAINTS ALL IMMEDIATE`);
        return { outcome: 'created' as const, purchase };
      }, 'write');
      return { ok: true, value }; // Only after the outer COMMIT has succeeded.
    } catch (error) {
      if (!(error instanceof DuplicateSubmission)) return failure(error);
      try {
        const purchase = await this.prisma.transaction(tx => this.replay(tx, candidate), 'read');
        ensure(purchase); // Never restart a writer if the supposed winner is absent.
        return { ok: true, value: { outcome: 'replay', purchase } };
      } catch (lookupError) { return failure(lookupError); }
    }
  }

  async get(id: unknown): Promise<RepositoryResult<PurchaseRecord>> {
    if (!uuid(id)) return { ok: false, error: { code: 'P4_INVALID_QUERY' } };
    try {
      const value = await this.prisma.transaction(tx => this.read(tx, id), 'read');
      ensure(value, 'P4_NOT_FOUND'); return { ok: true, value };
    } catch (error) { return failure(error); }
  }

  async getByKey(key: unknown): Promise<RepositoryResult<PurchaseRecord>> {
    if (typeof key !== 'string' || key.length !== 36 || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(key)) {
      return { ok: false, error: { code: 'P4_INVALID_QUERY' } };
    }
    const canonical = key.toLowerCase();
    try {
      const value = await this.prisma.transaction(async tx => {
        const rows = await tx.$queryRaw(Prisma.sql`SELECT app.p4_v1_receipt_by_key(${canonical}::uuid) AS result`);
        const purchase = decodeReceipt(rows);
        ensure(!purchase || purchase.source.source_id === canonical);
        return purchase;
      }, 'read');
      ensure(value, 'P4_NOT_FOUND'); return { ok: true, value };
    } catch (error) { return failure(error); }
  }

  async list(query: { limit?: number; after?: PurchaseCursor } = {}): Promise<RepositoryResult<{ items: PurchaseRecord[]; next_cursor: PurchaseCursor | null }>> {
    try {
      ensure(query && typeof query === 'object' && !Array.isArray(query)
        && Object.keys(query).every(k => k === 'limit' || k === 'after'), 'P4_INVALID_QUERY');
      const limit = query.limit === undefined ? 20 : query.limit; const after = query.after;
      ensure(Number.isInteger(limit) && limit >= 1 && limit <= 100, 'P4_INVALID_QUERY');
      ensure(after === undefined || (after && Object.keys(after).length === 2 && uuid(after.id) && instant(after.recorded_at)), 'P4_INVALID_QUERY');
      const value = await this.prisma.transaction(async tx => {
        const rows = await tx.$queryRaw(Prisma.sql`SELECT app.p4_v1_history(${limit}::integer, ${after?.recorded_at ?? null}::timestamptz, ${after?.id ?? null}::uuid) AS result`);
        const result = envelope(rows, ['items', 'next_cursor']);
        ensure(Array.isArray(result.items) && result.items.length <= limit);
        const items = result.items.map(row => decode(object(row)));
        ensure(new Set(items.map(r => r.id)).size === items.length);
        items.forEach((row, index) => {
          const previous = index ? items[index - 1] : after;
          ensure(!previous || earlier(row, previous));
        });
        let next_cursor: PurchaseCursor | null = null;
        if (result.next_cursor !== null) {
          const cursor = shape(result.next_cursor, ['recorded_at', 'id']);
          ensure(instant(cursor.recorded_at) && uuid(cursor.id));
          const last = items.at(-1);
          ensure(items.length === limit && last && cursor.recorded_at === last.recorded_at && cursor.id === last.id);
          next_cursor = { recorded_at: cursor.recorded_at, id: cursor.id };
        }
        return { items, next_cursor };
      }, 'read');
      return { ok: true, value };
    } catch (error) { return failure(error); }
  }
}
