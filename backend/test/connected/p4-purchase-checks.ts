import { isDeepStrictEqual } from 'node:util';
import { Prisma } from '../../generated/prisma/client.js';
import type { DatabaseTransaction, PrismaService } from '../../src/prisma/prisma.service.js';
import { preparePurchase, type PurchaseRequest } from '../../src/purchases/purchase-contract.js';
import { PurchaseRepository, type PurchaseCursor, type PurchaseRecord } from '../../src/purchases/purchase-repository.js';
import { diagnosticError } from './diagnostics.mjs';
import { sqlState } from './sqlstate.js';

// Fixed manifest: two durable lines; the third submission must roll back.
// Never delete evidence or generate new keys automatically after a failed run.
export const P4_FIXTURES: readonly PurchaseRequest[] = Object.freeze([
  ['47000001-0000-4000-8000-000000000001', 'sup-obra', 'prod-cimento', 'dep-obras', 2, '48.50', 30],
  ['47000002-0000-4000-8000-000000000002', 'sup-base', 'prod-tijolo', 'dep-almoxarifado', 100, '1.26', 15],
  ['47000003-0000-4000-8000-000000000003', 'sup-estrutura', 'prod-argamassa', 'dep-manutencao', 1, '23.90', 0],
].map(([key, supplier, product, department, quantity, price, days]) => Object.freeze({
  contract: 'p4-purchase/1.0' as const, origin: 'manual' as const, idempotency_key: String(key),
  purchase: Object.freeze({ supplier_id: String(supplier), product_id: String(product), department_id: String(department),
    quantity: Number(quantity), unit_price: String(price), currency: 'BRL' as const,
    purchase_date: '2026-11-16', payment_days: Number(days) }),
})));

const actor = { technicalUser: { issuer: 'p4-demo', subject: 'manual-purchase-service' } };
const tables = ['currencies', 'users', 'suppliers', 'departments', 'purchase_order_lines',
  'source_identities', 'source_references', 'record_versions', 'decision_snapshots', 'snapshot_members', 'audit_events'];
function requireCheck(value: unknown, code: string): asserts value {
  if (!value) throw diagnosticError(code);
}

async function requireAbsent(prisma: PrismaService, input: PurchaseRequest) {
  const rows = await prisma.transaction(tx => tx.$queryRaw<{ result: unknown }[]>(Prisma.sql`
    SELECT app.p4_v1_receipt_by_key(${input.idempotency_key}::uuid) AS result`), 'read');
  requireCheck(rows.length === 1, 'P4_RECEIPT');
  const result = rows[0].result as { status?: string } | null;
  if (result?.status === 'found') throw diagnosticError('P4_FIXTURE_EXISTS');
  requireCheck(isDeepStrictEqual(result, { contract: 'p4-storage/1.0', status: 'absent', receipt: null }), 'P4_RECEIPT');
}

// Only a transaction decorator: all I/O continues through the existing service
// and its lifecycle-managed client. No second pool or alternate credential.
type AwaitedTransaction = {
  $queryRaw<T = unknown>(...args: Parameters<DatabaseTransaction['$queryRaw']>): Promise<T>;
  $executeRaw(...args: Parameters<DatabaseTransaction['$executeRaw']>): Promise<number>;
};
function decorated(prisma: PrismaService, wrap: (tx: DatabaseTransaction) => AwaitedTransaction): PrismaService {
  // P4.3 awaits individual operations; it never passes these promises to Prisma's
  // array transaction API. The decorator intentionally provides native Promises.
  return { transaction: <T>(work: (tx: DatabaseTransaction) => Promise<T>, access: 'read' | 'write') =>
    prisma.transaction(tx => work(wrap(tx) as DatabaseTransaction), access) } as PrismaService;
}

function validateReceipt(record: PurchaseRecord, request: PurchaseRequest) {
  const expected = preparePurchase(request, new Date(record.recorded_at));
  requireCheck(expected.ok, 'P4_RECEIPT');
  requireCheck(record.revision_no === 1 && record.source.source_id === request.idempotency_key &&
    record.content_sha256 === expected.value.content_sha256 &&
    isDeepStrictEqual(record.purchase, expected.value.original_content.purchase) &&
    isDeepStrictEqual(record.analysis, expected.value.analysis), 'P4_RECEIPT');
}

/** Called only after the harness's exact-target gate, identity and catalog audit.
 * Does not open a connection on import. Real execution requires separate approval.
 * A failure can leave earlier committed fixtures: no retry or destructive cleanup.
 */
export async function runP4PurchaseChecks(prisma: PrismaService, enter: (code: string) => void = () => {}) {
  const repo = new PurchaseRepository(prisma, actor);
  enter('P4_PREFLIGHT');
  for (const input of P4_FIXTURES) await requireAbsent(prisma, input);
  const initial = await repo.list({ limit: 1 });
  requireCheck(initial.ok, 'P4_HISTORY'); // Includes SQL's orphan/integrity checks.

  enter('P4_PERMISSIONS');
  for (const table of tables) {
    let state: string | undefined;
    try {
      // Identifiers are internal constants only. LIMIT 0 reads no business rows.
      await prisma.transaction(tx => tx.$queryRaw(Prisma.sql`SELECT 1 FROM ${Prisma.raw(`app.${table}`)} LIMIT 0`), 'read');
    } catch (error) { state = sqlState(error); }
    requireCheck(state === '42501', 'P4_PERMISSIONS'); // Neither 42601 nor 25P02 proves denial.
  }

  enter('P4_ROLLBACK');
  const invalid = await repo.create({ ...P4_FIXTURES[2], purchase: { ...P4_FIXTURES[2].purchase, quantity: 0 } });
  requireCheck(!invalid.ok && invalid.error.code === 'P4_INVALID_QUANTITY', 'P4_ROLLBACK');
  let rejection: string | undefined;
  let injected = false;
  const rollback = new PurchaseRepository(decorated(prisma, tx => ({
    $queryRaw: tx.$queryRaw.bind(tx),
    $executeRaw: async (...args) => {
      const result = await tx.$executeRaw(...args);
      // P4.3 reaches this after origin, line, version, audit and resolution.
      // Force a genuine server 22023 after checking all deferred constraints.
      if ((args[0] as Prisma.Sql).sql === 'SET CONSTRAINTS ALL IMMEDIATE') {
        injected = true;
        try { await tx.$queryRaw(Prisma.sql`SELECT app.p4_v1_history(0::integer, NULL::timestamptz, NULL::uuid)`); }
        catch (error) { rejection = sqlState(error); throw error; }
        throw diagnosticError('P4_ROLLBACK'); // Never commit if the invalid call succeeds.
      }
      return result;
    },
  })), actor);
  const failed = await rollback.create(P4_FIXTURES[2]);
  requireCheck(injected && rejection === '22023' && !failed.ok && failed.error.code === 'P4_STORAGE_INTEGRITY', 'P4_ROLLBACK');
  await requireAbsent(prisma, P4_FIXTURES[2]);

  enter('P4_CREATE');
  const first = await repo.create(P4_FIXTURES[0]);
  requireCheck(first.ok && first.value.outcome === 'created', 'P4_CREATE');
  validateReceipt(first.value.purchase, P4_FIXTURES[0]);
  enter('P4_IDEMPOTENCY');
  const replay = await repo.create(P4_FIXTURES[0]);
  requireCheck(replay.ok && replay.value.outcome === 'replay' &&
    isDeepStrictEqual(replay.value.purchase, first.value.purchase), 'P4_IDEMPOTENCY');
  const conflict = await repo.create({ ...P4_FIXTURES[0], purchase: { ...P4_FIXTURES[0].purchase, quantity: 3 } });
  requireCheck(!conflict.ok && conflict.error.code === 'P4_IDEMPOTENCY_CONFLICT', 'P4_IDEMPOTENCY');

  enter('P4_CONCURRENCY');
  // Rendezvous after both transactions saw an absent key, before reservation.
  // This proves overlapping attempts, rather than merely concurrent Promises.
  let arrived = 0;
  let release!: () => void;
  const ready = new Promise<void>(resolve => { release = resolve; });
  const concurrent = new PurchaseRepository(decorated(prisma, tx => ({
    $executeRaw: tx.$executeRaw.bind(tx),
    $queryRaw: async (...args) => {
      if ((args[0] as Prisma.Sql).sql.includes('app.register_source_identity(')) {
        arrived++;
        if (arrived === 2) release();
        let timer: ReturnType<typeof setTimeout> | undefined;
        try {
          await Promise.race([ready, new Promise<never>((_, reject) => {
            timer = setTimeout(() => reject(diagnosticError('P4_CONCURRENCY')), 1500);
          })]);
        } finally { clearTimeout(timer); }
      }
      return tx.$queryRaw(...args);
    },
  })), actor);
  const pair = await Promise.allSettled([concurrent.create(P4_FIXTURES[1]), concurrent.create(P4_FIXTURES[1])]);
  const a = pair[0].status === 'fulfilled' ? pair[0].value : null;
  const b = pair[1].status === 'fulfilled' ? pair[1].value : null;
  requireCheck(arrived === 2 && a?.ok && b?.ok &&
    [a.value.outcome, b.value.outcome].sort().join(',') === 'created,replay' &&
    isDeepStrictEqual(a.value.purchase, b.value.purchase), 'P4_CONCURRENCY');
  validateReceipt(a.value.purchase, P4_FIXTURES[1]);

  enter('P4_HISTORY');
  const expected = [first.value.purchase, a.value.purchase];
  requireCheck(expected[0].id !== expected[1].id && expected[0].version_id !== expected[1].version_id &&
    expected[0].source_reference_id !== expected[1].source_reference_id, 'P4_RECEIPT');
  for (const record of expected) {
    const found = await repo.get(record.id);
    requireCheck(found.ok && isDeepStrictEqual(found.value, record), 'P4_RECEIPT');
  }
  const seen = new Set<string>();
  const remaining = new Set(expected.map(record => record.id));
  let after: PurchaseCursor | undefined;
  for (let page = 0; page < 100 && remaining.size; page++) {
    const result = await repo.list({ limit: 1, ...(after ? { after } : {}) });
    requireCheck(result.ok, 'P4_HISTORY');
    for (const record of result.value.items) {
      requireCheck(!seen.has(record.id), 'P4_HISTORY'); seen.add(record.id);
      if (remaining.has(record.id)) {
        requireCheck(isDeepStrictEqual(record, expected.find(item => item.id === record.id)), 'P4_HISTORY');
        remaining.delete(record.id);
      }
    }
    if (!result.value.next_cursor) break;
    after = result.value.next_cursor;
  }
  requireCheck(remaining.size === 0, 'P4_HISTORY');
  await requireAbsent(prisma, P4_FIXTURES[2]);
  enter('P4_COMPLETE');
  // Only UUIDs and canonical receipts; no secret, driver detail or connection URL.
  // The bounded runner deliberately emits only the P4_COMPLETE diagnostic.
  return { purchases: expected, rollback_key: P4_FIXTURES[2].idempotency_key };
}
