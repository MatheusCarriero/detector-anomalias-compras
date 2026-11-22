import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { Prisma } from '../../generated/prisma/client.js';
import type { PrismaService } from '../../src/prisma/prisma.service.js';
import { PurchaseRepository, type PurchaseRecord, type PurchaseCursor } from '../../src/purchases/purchase-repository.js';
import { PurchaseComparabilityRepository } from '../../src/purchases/purchase-comparability.repository.js';
import type { ManualComparabilityRequest } from '../../src/purchases/statistics/manual-comparability.js';
import { P4_FIXTURES } from './p4-purchase-checks.js';
import { diagnosticError } from './diagnostics.mjs';
import { rejectsSqlState } from './sqlstate.js';
import { COMPARABILITY_DATABASE } from './config.js';

type Service = Pick<PrismaService, 'transaction'>;
function check(value: unknown, code: string): asserts value { if (!value) throw diagnosticError(code); }
export const CMP_PURCHASES = Object.freeze(P4_FIXTURES.slice(0, 2).map((p, i) => Object.freeze({ ...p,
  idempotency_key: `5100000${i + 1}-0000-4000-8000-000000000001` })));
const uuid = (n: number) => `51000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
// Raw negative cases must reach SQL (including invalid links), independently of
// the repository's early validation. Canonical JSON here is test input only.
function canonical(value: unknown): string {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const fields = value as Record<string, unknown>;
    return `{${Object.keys(fields).sort().map(k => `${JSON.stringify(k)}:${canonical(fields[k])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}
export const CMP_DEFINITION = 'Synthetic E.5A specification, declared only; no statistical analysis.';
export function comparabilityRequest(purchase: PurchaseRecord, n: number): ManualComparabilityRequest {
  return { contract: 'p4-manual-comparability/1.0', id: uuid(n), revision: 1, supersedes: null,
    purchase: { id: purchase.id, version_id: purchase.version_id, content_sha256: purchase.content_sha256 },
    attributes: { specification: { value: { id: `e5a-${purchase.purchase.product.id}`, version: '1',
      product_id: purchase.purchase.product.id, sha256: createHash('sha256').update(CMP_DEFINITION).digest('hex') },
    provenance: { kind: 'declared', actor_id: 'e5a-synthetic-test', declared_at: purchase.recorded_at } } } };
}

/** Rendezvous INSIDE two interactive transactions, before the write function.
 * Both callbacks must hold different database sessions. Never retry; drain both
 * promises before allowing Nest to close its existing pool. The gate has its own
 * shorter timeout, within the existing lock/transaction/process deadlines.
 */
export async function independentPair<T>(prisma: Service, work: (service: Service, index: number) => Promise<T>) {
  const pids: number[] = []; let release!: () => void;
  const ready = new Promise<void>(resolve => { release = resolve; });
  const service: Service = { transaction: (callback, access) => prisma.transaction(async tx => {
    if (access === 'write') {
      const rows = await tx.$queryRaw<Record<string, unknown>[]>(Prisma.sql`SELECT pg_catalog.pg_backend_pid()::integer AS pid,
        pg_catalog.current_database() AS database, session_user::text AS session_user, current_user::text AS current_user,
        pg_catalog.host(pg_catalog.inet_server_addr()) AS host, pg_catalog.inet_server_port() AS port,
        pg_catalog.current_setting('transaction_isolation') AS isolation, pg_catalog.current_setting('transaction_read_only') AS read_only`);
      const r = rows[0];
      check(rows.length === 1 && Number.isInteger(r.pid) && Number(r.pid) > 0 && r.database === COMPARABILITY_DATABASE
        && r.session_user === 'detector_runtime' && r.current_user === 'detector_runtime' && r.host === '127.0.0.1'
        && r.port === 5432 && r.isolation === 'read committed' && r.read_only === 'off', 'CMP_SESSIONS');
      pids.push(r.pid as number);
      if (pids.length === 2) release();
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        await Promise.race([ready, new Promise<never>((_, reject) => {
          timer = setTimeout(() => reject(diagnosticError('CMP_SESSIONS')), 1500);
        })]);
        check(pids.length === 2 && pids[0] !== pids[1], 'CMP_SESSIONS');
      } finally { clearTimeout(timer); }
    }
    return callback(tx);
  }, access) };
  const pair = await Promise.allSettled([work(service, 0), work(service, 1)]);
  check(pids.length === 2 && pids[0] !== pids[1] && pair.every(p => p.status === 'fulfilled'), 'CMP_SESSIONS');
  return pair.map(p => (p as PromiseFulfilledResult<T>).value);
}

async function history(repo: PurchaseRepository) {
  const rows: PurchaseRecord[] = []; let after: PurchaseCursor | undefined;
  for (let page = 0; page < 10; page++) {
    const result = await repo.list({ limit: 100, ...(after ? { after } : {}) });
    check(result.ok, 'CMP_PRESERVATION'); rows.push(...result.value.items);
    check(new Set(rows.map(r => r.id)).size === rows.length, 'CMP_PRESERVATION');
    if (!result.value.next_cursor) return rows;
    after = result.value.next_cursor;
  }
  throw diagnosticError('CMP_PREFLIGHT'); // Disposable fixture database must be small.
}

async function negatives(prisma: Service, input: ManualComparabilityRequest, enter: (code: string) => void) {
  await prisma.transaction(async tx => {
    await tx.$executeRaw`SET CONSTRAINTS ALL IMMEDIATE`;
    const write = (candidate: ManualComparabilityRequest, defs = { specification: CMP_DEFINITION }) =>
      tx.$queryRaw(Prisma.sql`SELECT app.p4_cmp_write(${canonical(candidate)}::text,${JSON.stringify(defs)}::jsonb)`);
    await rejectsSqlState(tx, () => write({ ...input, purchase: { ...input.purchase, id: uuid(999) } }), '23503');
    await rejectsSqlState(tx, () => write({ ...input, purchase: { ...input.purchase, version_id: uuid(999) } }), '22023');
    await rejectsSqlState(tx, () => write({ ...input, purchase: { ...input.purchase, content_sha256: '0'.repeat(64) } }), '22023');
    const claimed = structuredClone(input) as unknown as { attributes: { specification: { provenance: { kind: string } } } };
    claimed.attributes.specification.provenance.kind = 'verified';
    await rejectsSqlState(tx, () => write(claimed as unknown as ManualComparabilityRequest), '22023');
    await rejectsSqlState(tx, () => tx.$queryRaw(Prisma.sql`SELECT app.p4_cmp_read(${input.purchase.id}::uuid,0::integer)`), '22023');
    await rejectsSqlState(tx, () => tx.$queryRaw(Prisma.sql`SELECT app.p4_cmp_read(${uuid(999)}::uuid,NULL::integer)`), '23503');
    enter('CMP_PERMISSIONS');
    // Valid SQL: syntax/aborted-transaction errors are NOT permission evidence.
    const forbidden = [
      Prisma.sql`SELECT * FROM app.p4_comparability_revisions LIMIT 0`,
      Prisma.sql`SELECT * FROM app.p4_comparability_definitions LIMIT 0`,
      Prisma.sql`SELECT * FROM app.purchase_order_lines LIMIT 0`,
      Prisma.sql`UPDATE app.p4_comparability_revisions SET revision=revision WHERE false`,
      Prisma.sql`DELETE FROM app.p4_comparability_revisions WHERE false`,
      Prisma.sql`UPDATE app.p4_comparability_definitions SET original_text=original_text WHERE false`,
      Prisma.sql`DELETE FROM app.p4_comparability_definitions WHERE false`,
      Prisma.sql`SELECT app.p4_cmp_assert(true)`,
      Prisma.sql`SELECT app.p4_cmp_shape('{}'::jsonb,ARRAY[]::text[],ARRAY[]::text[])`,
      Prisma.sql`SELECT app.p4_cmp_text('"x"'::jsonb)`,
      Prisma.sql`SELECT app.p4_cmp_canonical('{}'::jsonb)`,
      Prisma.sql`SELECT app.p4_cmp_validate('{}'::jsonb,'{}'::jsonb,pg_catalog.now())`,
      Prisma.sql`SELECT app.p4_cmp_definition_key('specification','{}'::jsonb)`,
      Prisma.sql`SELECT app.p4_cmp_definitions('{}'::jsonb,'{}'::jsonb)`,
      Prisma.sql`SELECT app.p4_cmp_pack(NULL::uuid)`,
    ];
    for (const query of forbidden) await rejectsSqlState(tx, () => tx.$executeRaw(query), '42501');
  }, 'write');
}

/** Called only by the bounded harness after exact identity + 13-table catalog.
 * Two fixed durable purchase lines, three durable metadata revisions. Failures
 * can leave earlier commits; never rerun automatically or erase that evidence.
 */
export async function runComparabilityChecks(prisma: PrismaService, enter: (code: string) => void = () => {}) {
  const purchases = new PurchaseRepository(prisma, { technicalUser: { issuer: 'p4-demo', subject: 'manual-purchase-service' } });
  const repo = new PurchaseComparabilityRepository(prisma, purchases);
  enter('CMP_PREFLIGHT');
  for (const p of CMP_PURCHASES) {
    const found = await purchases.getByKey(p.idempotency_key);
    check(!found.ok && found.error.code === 'P4_NOT_FOUND', 'CMP_FIXTURE_EXISTS');
  }
  const before = await history(purchases);
  const context = await prisma.transaction(tx => tx.$queryRaw(Prisma.sql`SELECT app.p4_v1_context() AS result`), 'read');
  const receipts: PurchaseRecord[] = [];
  enter('CMP_CREATE');
  for (const p of CMP_PURCHASES) {
    const created = await purchases.create(p);
    check(created.ok && created.value.outcome === 'created', 'CMP_CREATE'); receipts.push(created.value.purchase);
    const absent = await repo.get(created.value.purchase.id); check(absent.ok && absent.value === null, 'CMP_CREATE');
  }
  const first = comparabilityRequest(receipts[0], 1); const second = comparabilityRequest(receipts[1], 10);
  enter('CMP_BINDING'); await negatives(prisma, first, enter);
  enter('CMP_ROLLBACK');
  let inserted = false;
  const rollback: Service = { transaction: (work, access) => prisma.transaction(async tx => {
    const result = await work(tx);
    if (access === 'write') { inserted = true; throw diagnosticError('CMP_ROLLBACK'); }
    return result;
  }, access) };
  const rollbackText = 'This definition must roll back, then its key can receive the approved fixture.';
  const rollbackRequest = structuredClone(second);
  rollbackRequest.attributes.specification!.value.sha256 = createHash('sha256').update(rollbackText).digest('hex');
  const rolled = await new PurchaseComparabilityRepository(rollback, purchases).save(rollbackRequest, { specification: rollbackText });
  check(inserted && !rolled.ok && rolled.error.code === 'P4_STORAGE_FAILURE', 'CMP_ROLLBACK');
  const absent = await repo.get(receipts[1].id); check(absent.ok && absent.value === null, 'CMP_ROLLBACK');
  enter('CMP_CONCURRENCY');
  const competing = [first, { ...first, id: uuid(2) }];
  const race = async (inputs: ManualComparabilityRequest[]) => independentPair(prisma, (service, i) =>
    new PurchaseComparabilityRepository(service, purchases).save(inputs[i], { specification: CMP_DEFINITION }));
  const winner = (results: Awaited<ReturnType<typeof race>>) => {
    const good = results.filter(r => r.ok); const bad = results.filter(r => !r.ok);
    check(good.length === 1 && good[0].ok && good[0].value.outcome === 'created'
      && bad.length === 1 && !bad[0].ok && bad[0].error.code === 'P4_COMPARABILITY_CONFLICT', 'CMP_CONCURRENCY');
    return good[0].value.revision;
  };
  const revision1 = winner(await race(competing));
  const content1 = revision1.validation.content;
  const next: ManualComparabilityRequest = { ...content1, id: uuid(3), revision: 2,
    supersedes: { id: content1.id, revision: 1, content_sha256: revision1.validation.content_sha256 } };
  const revision2 = winner(await race([next, { ...next, id: uuid(4) }]));
  const identical = await race([second, second]);
  check(identical.every(r => r.ok) && identical.map(r => r.ok && r.value.outcome).sort().join(',') === 'created,replay'
    && identical[0].ok && identical[1].ok && isDeepStrictEqual(identical[0].value.revision, identical[1].value.revision), 'CMP_REPLAY');
  enter('CMP_REPLAY');
  const replay = await repo.save(content1, { specification: CMP_DEFINITION });
  check(replay.ok && replay.value.outcome === 'replay' && isDeepStrictEqual(replay.value.revision, revision1), 'CMP_REPLAY');
  const changed = structuredClone(content1); changed.attributes.specification!.provenance.actor_id = 'changed';
  const conflict = await repo.save(changed, { specification: CMP_DEFINITION });
  check(!conflict.ok && conflict.error.code === 'P4_COMPARABILITY_CONFLICT', 'CMP_REPLAY');
  enter('CMP_IMMUTABILITY');
  const old = await repo.get(receipts[0].id, 1); const latest = await repo.get(receipts[0].id);
  check(old.ok && isDeepStrictEqual(old.value, revision1) && latest.ok && isDeepStrictEqual(latest.value, revision2), 'CMP_IMMUTABILITY');
  const nonexistent = await repo.get(receipts[0].id, 3); check(nonexistent.ok && nonexistent.value === null, 'CMP_IMMUTABILITY');
  enter('CMP_PRESERVATION');
  const after = await history(purchases);
  check(after.length === before.length + receipts.length, 'CMP_PRESERVATION');
  for (const p of [...before, ...receipts]) check(isDeepStrictEqual(after.find(r => r.id === p.id), p), 'CMP_PRESERVATION');
  const contextAfter = await prisma.transaction(tx => tx.$queryRaw(Prisma.sql`SELECT app.p4_v1_context() AS result`), 'read');
  check(isDeepStrictEqual(contextAfter, context), 'CMP_PRESERVATION');
  enter('CMP_COMPLETE');
  return { purchases: receipts.map(p => p.id), revisions: 3 };
}
