import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { Prisma } from '../../generated/prisma/client.js';
import type { PrismaService } from '../prisma/prisma.service.js';
import type { PurchaseRecord, PurchaseRepository, RepositoryResult } from './purchase-repository.js';
import { validateManualComparability } from './statistics/manual-comparability.js';
import type { ValidatedManualComparability } from './statistics/manual-comparability.js';

type Code = Extract<RepositoryResult<never>, { ok: false }>['error']['code'] |
  'P4_COMPARABILITY_INVALID' | 'P4_COMPARABILITY_CONFLICT';
type Result<T> = { ok: true; value: T } | { ok: false; error: { code: Code } };
type DefinitionKind = 'specification' | 'packaging' | 'price_basis' | 'delivery' | 'quantity_pricing';
type Definitions = Partial<Record<DefinitionKind, string>>;
export interface ComparabilityRevision {
  validation: ValidatedManualComparability; definitions: Definitions;
  recorded_at: string; source_reference_id: string; actor_user_id: string;
}
class Failure extends Error { constructor(readonly code: Code) { super(code); } }
function ensure(ok: unknown, code: Code = 'P4_COMPARABILITY_INVALID'): asserts ok { if (!ok) throw new Failure(code); }
function object(value: unknown, keys?: readonly string[]): Record<string, unknown> {
  ensure(value !== null && typeof value === 'object' && !Array.isArray(value));
  ensure(Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null);
  const names = Reflect.ownKeys(value);
  ensure(names.every(k => typeof k === 'string' && Object.getOwnPropertyDescriptor(value, k)?.enumerable
    && Object.hasOwn(Object.getOwnPropertyDescriptor(value, k)!, 'value')));
  if (keys) ensure(names.length === keys.length && keys.every(k => Object.hasOwn(value, k)));
  return value as Record<string, unknown>;
}
function canonical(value: unknown): string {
  if (value !== null && typeof value === 'object') {
    const v = value as Record<string, unknown>;
    return `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}
function utf8(value: unknown): boolean {
  if (typeof value === 'string') return Buffer.from(value, 'utf8').toString('utf8') === value;
  return value === null || typeof value !== 'object' || Object.values(value).every(utf8);
}
function definitionsFor(input: unknown, validated: ValidatedManualComparability): Definitions {
  const fields: DefinitionKind[] = ['specification', 'packaging', 'price_basis', 'delivery'];
  if (validated.content.attributes.quantity_pricing?.value.regime === 'tier') fields.push('quantity_pricing');
  const required = fields.filter(f => validated.content.attributes[f]);
  const values = object(input, required); const result: Definitions = {};
  for (const key of required.sort()) {
    const text = values[key];
    ensure(typeof text === 'string' && text.trim().length > 0 && Buffer.byteLength(text, 'utf8') <= 16000
      && Buffer.from(text, 'utf8').toString('utf8') === text && !text.includes('\0'));
    if (key === 'specification') ensure(createHash('sha256').update(text, 'utf8').digest('hex')
      === validated.content.attributes.specification!.value.sha256);
    result[key] = text;
  }
  return result;
}
function uuid(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.exec(value)?.[0] === value;
}
function decode(value: unknown, purchase: PurchaseRecord): ComparabilityRevision {
  try {
    const row = object(value, ['canonical_content', 'content_sha256', 'definitions', 'recorded_at', 'source_reference_id', 'actor_user_id']);
    ensure(typeof row.canonical_content === 'string' && Buffer.byteLength(row.canonical_content, 'utf8') <= 65536);
    ensure(typeof row.recorded_at === 'string' && row.recorded_at.length === 24
      && Number.isFinite(Date.parse(row.recorded_at)) && new Date(row.recorded_at).toISOString() === row.recorded_at);
    ensure(uuid(row.source_reference_id) && uuid(row.actor_user_id));
    const checked = validateManualComparability(JSON.parse(row.canonical_content), { purchase, now: new Date(row.recorded_at) });
    ensure(checked.ok);
    ensure(canonical(checked.value.content) === row.canonical_content && checked.value.content_sha256 === row.content_sha256);
    return { validation: checked.value, definitions: definitionsFor(row.definitions, checked.value),
      recorded_at: row.recorded_at, source_reference_id: row.source_reference_id, actor_user_id: row.actor_user_id };
  } catch { throw new Failure('P4_STORAGE_INTEGRITY'); }
}
function envelope(rows: unknown) {
  ensure(Array.isArray(rows) && rows.length === 1, 'P4_STORAGE_INTEGRITY');
  try {
    const result = object(object(rows[0], ['result']).result, ['contract', 'outcome', 'revision']);
    ensure(result.contract === 'p4-comparability-storage/1.0'); return result;
  } catch { throw new Failure('P4_STORAGE_INTEGRITY'); }
}
function failure(error: unknown): { ok: false; error: { code: Code } } {
  if (error instanceof Failure) return { ok: false, error: { code: error.code } };
  const e = error as { code?: string; meta?: { driverAdapterError?: { cause?: { originalCode?: string } } } } | null;
  const state = e?.code === 'P2010' ? e.meta?.driverAdapterError?.cause?.originalCode : e?.code;
  const code: Code = state === '23505' ? 'P4_COMPARABILITY_CONFLICT' : state === '22023' ? 'P4_COMPARABILITY_INVALID'
    : state === '42501' ? 'P4_STORAGE_PERMISSION' : ['23503', '23514'].includes(state ?? '') ? 'P4_STORAGE_INTEGRITY'
    : ['40001', '40P01', '55P03', '57014'].includes(state ?? '') ? 'P4_STORAGE_BUSY' : 'P4_STORAGE_FAILURE';
  return { ok: false, error: { code } };
}

/** No HTTP/module registration, new pool or retry. Definition strings preserve
 * their original UTF-8 bytes; specification.sha256 must identify those bytes.
 * All input is a declaration. No verification context is accepted here.
 * PurchaseRepository checks the receipt first; SQL checks the binding again
 * under the purchase lock before inserting metadata, origin and audit atomically.
 */
export class PurchaseComparabilityRepository {
  constructor(private readonly prisma: Pick<PrismaService, 'transaction'>,
    private readonly purchases: Pick<PurchaseRepository, 'get'>, private readonly clock: () => Date = () => new Date()) {}

  async save(input: unknown, definitions: unknown): Promise<Result<{ outcome: 'created' | 'replay'; revision: ComparabilityRevision }>> {
    try {
      const root = object(input, ['contract', 'id', 'revision', 'supersedes', 'purchase', 'attributes']);
      const link = object(root.purchase, ['id', 'version_id', 'content_sha256']);
      ensure(uuid(link.id));
      const purchase = await this.purchases.get(link.id); if (!purchase.ok) return purchase;
      const checked = validateManualComparability(input, { purchase: purchase.value, now: this.clock() });
      ensure(checked.ok); ensure(checked.value.content.revision <= 2147483647);
      ensure(utf8(checked.value.content));
      const canonicalContent = canonical(checked.value.content);
      ensure(Buffer.byteLength(canonicalContent, 'utf8') <= 65536);
      const originalDefinitions = definitionsFor(definitions, checked.value);
      const value = await this.prisma.transaction(async tx => {
        const result = envelope(await tx.$queryRaw(Prisma.sql`SELECT app.p4_cmp_write(${canonicalContent}::text, ${JSON.stringify(originalDefinitions)}::jsonb) AS result`));
        ensure(result.outcome === 'created' || result.outcome === 'replay', 'P4_STORAGE_INTEGRITY');
        const revision = decode(result.revision, purchase.value);
        ensure(isDeepStrictEqual(revision.validation.content, checked.value.content)
          && isDeepStrictEqual(revision.definitions, originalDefinitions), 'P4_STORAGE_INTEGRITY');
        await tx.$executeRaw(Prisma.sql`SET CONSTRAINTS ALL IMMEDIATE`);
        return { outcome: result.outcome as 'created' | 'replay', revision };
      }, 'write');
      return { ok: true, value }; // Only after successful COMMIT.
    } catch (error) { return failure(error); }
  }

  async get(purchaseId: unknown, revision: number | null = null): Promise<Result<ComparabilityRevision | null>> {
    try {
      ensure(uuid(purchaseId) && (revision === null || (Number.isInteger(revision) && revision >= 1 && revision <= 2147483647)));
      const purchase = await this.purchases.get(purchaseId); if (!purchase.ok) return purchase;
      const value = await this.prisma.transaction(async tx => {
        const result = envelope(await tx.$queryRaw(Prisma.sql`SELECT app.p4_cmp_read(${purchaseId}::uuid, ${revision}::integer) AS result`));
        if (result.outcome === 'absent') { ensure(result.revision === null, 'P4_STORAGE_INTEGRITY'); return null; }
        ensure(result.outcome === 'found', 'P4_STORAGE_INTEGRITY');
        const stored = decode(result.revision, purchase.value);
        ensure(revision === null || stored.validation.content.revision === revision, 'P4_STORAGE_INTEGRITY');
        return stored;
      }, 'read');
      return { ok: true, value };
    } catch (error) { return failure(error); }
  }
}
