import { createHash } from 'node:crypto';
import { Socket } from 'node:net';
import { Prisma } from '../../generated/prisma/client.js';
import type { DatabaseTransaction, PrismaService } from '../../src/prisma/prisma.service.js';
import { preparePurchase } from '../../src/purchases/purchase-contract.js';
import type { PurchaseRecord } from '../../src/purchases/purchase-repository.js';
import { validateManualComparability, type ManualComparabilityRequest } from '../../src/purchases/statistics/manual-comparability.js';
import { CMP_PURCHASES, CMP_DEFINITION, comparabilityRequest, independentPair, runComparabilityChecks } from './comparability-checks.js';

vi.mock('pg', () => { throw new Error('Offline driver guard'); });
vi.mock('@prisma/adapter-pg', () => { throw new Error('Offline adapter guard'); });
const fake = vi.hoisted(() => ({ create: vi.fn(), get: vi.fn(), getByKey: vi.fn(), list: vi.fn() }));
vi.mock('../../src/purchases/purchase-repository.js', () => ({ PurchaseRepository: class {
  create = fake.create; get = fake.get; getByKey = fake.getByKey; list = fake.list;
} }));
const now = new Date('2026-11-21T15:00:00.000Z');
const uid = (n: number) => `62000000-0000-4000-8000-${String(n).padStart(12, '0')}`;
function receipt(index: number): PurchaseRecord {
  const prepared = preparePurchase(CMP_PURCHASES[index], now);
  if (!prepared.ok) throw new Error('Invalid fixture');
  return { id: uid(index + 1), version_id: uid(index + 10), revision_no: 1, recorded_at: now.toISOString(),
    source_reference_id: uid(index + 20), source: prepared.value.source, content_sha256: prepared.value.content_sha256,
    purchase: prepared.value.original_content.purchase, analysis: prepared.value.analysis };
}
type Stored = { canonical_content: string; content_sha256: string; definitions: unknown;
  recorded_at: string; source_reference_id: string; actor_user_id: string };
// In-memory transaction double: SQLSTATE/savepoint paths and orchestrator are
// exercised here, NOT PostgreSQL syntax, locks, ACLs, triggers or concurrency.
function scenario() {
  const receipts: PurchaseRecord[] = []; let stored: Stored[] = []; let tail = Promise.resolve(); let serial = 0;
  const trace: string[] = []; let permission = '42501'; let negative = '22023'; let keepRollback = false;
  const found = (row: PurchaseRecord | undefined) => row ? { ok: true, value: structuredClone(row) }
    : { ok: false, error: { code: 'P4_NOT_FOUND' } };
  fake.create.mockImplementation(() => { const row = receipt(receipts.length); receipts.push(row);
    return { ok: true, value: { outcome: 'created', purchase: structuredClone(row) } }; });
  fake.get.mockImplementation((id: string) => found(receipts.find(r => r.id === id)));
  fake.getByKey.mockImplementation((key: string) => found(receipts.find(r => r.source.source_id === key)));
  fake.list.mockImplementation(() => ({ ok: true, value: { items: structuredClone(receipts), next_cursor: null } }));
  const transaction = async <T>(work: (tx: DatabaseTransaction) => Promise<T>, access: string): Promise<T> => {
    const pid = ++serial; let pending: Stored[] | undefined; let release: (() => void) | undefined;
    const query = async (sql: Prisma.Sql) => {
      trace.push(sql.sql);
      if (sql.sql.includes('pg_backend_pid')) return [{ pid, database: 'synthetic_p4_comparability_test', session_user: 'detector_runtime',
        current_user: 'detector_runtime', host: '127.0.0.1', port: 5432, isolation: 'read committed', read_only: 'off' }];
      if (sql.sql.includes('p4_v1_context')) return [{ result: { context: 'unchanged' } }];
      let row: Stored | undefined; let outcome = 'found';
      if (sql.sql.includes('p4_cmp_write')) {
        const [canonical, defs] = sql.values as [string, string]; const content = JSON.parse(canonical) as ManualComparabilityRequest;
        const purchase = receipts.find(p => p.id === content.purchase.id);
        if (!purchase) throw { code: '23503' };
        if (!validateManualComparability(content, { purchase, now }).ok) throw { code: negative };
        // Simulated locking only after entering the operation (the rendezvous
        // requires both transactions already to own independent sessions).
        if (!pending) { const previous = tail; tail = new Promise(r => { release = r; }); await previous; pending = structuredClone(stored); }
        row = pending.find(r => JSON.parse(r.canonical_content).id === content.id);
        if (row) { if (row.canonical_content !== canonical) throw { code: '23505' }; outcome = 'replay'; }
        else {
          const revisions = pending.filter(r => JSON.parse(r.canonical_content).purchase.id === purchase.id);
          const head = revisions.at(-1); const prev = head && JSON.parse(head.canonical_content);
          if (content.revision !== revisions.length + 1 || (head && (content.supersedes?.id !== prev.id
            || content.supersedes?.content_sha256 !== head.content_sha256))) throw { code: '23505' };
          row = { canonical_content: canonical, content_sha256: createHash('sha256').update(canonical).digest('hex'), definitions: JSON.parse(defs),
            recorded_at: now.toISOString(), source_reference_id: uid(pid + 100), actor_user_id: uid(50) };
          pending.push(row); outcome = 'created';
        }
      } else if (sql.sql.includes('p4_cmp_read')) {
        const [id, revision] = sql.values;
        if (!receipts.some(p => p.id === id)) throw { code: '23503' };
        if (revision === 0 || sql.sql.includes(',0::integer)')) throw { code: negative };
        row = stored.filter(r => { const c = JSON.parse(r.canonical_content); return c.purchase.id === id && (revision === null || c.revision === revision); }).at(-1);
      } else throw new Error('Unexpected synthetic SQL');
      return [{ result: { contract: 'p4-comparability-storage/1.0', outcome: row ? outcome : 'absent', revision: structuredClone(row ?? null) } }];
    };
    const execute = async (sql: Prisma.Sql | TemplateStringsArray) => {
      const text = 'sql' in sql ? sql.sql : sql[0]; trace.push(text);
      if (/^(SELECT|UPDATE|DELETE)/.test(text)) throw { code: permission };
      return 0;
    };
    try {
      const value = await work({ $queryRaw: query, $executeRaw: execute } as unknown as DatabaseTransaction);
      if (pending) stored = pending; trace.push(`commit:${access}`); return value;
    } catch (e) {
      if (pending && keepRollback) stored = pending;
      trace.push(`rollback:${access}`); throw e;
    } finally { release?.(); }
  };
  return { prisma: { transaction } as PrismaService, trace, receipts, rows: () => structuredClone(stored),
    permission: (value: string) => { permission = value; }, negative: (value: string) => { negative = value; },
    leak: () => { keepRollback = true; } };
}

describe('comparability future scenario, offline orchestration', () => {
  let attempts = 0;
  beforeEach(() => { vi.resetAllMocks(); attempts = 0; vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(now);
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => { attempts++; throw new Error('Offline network guard'); }); });
  afterEach(() => { expect(attempts).toBe(0); vi.restoreAllMocks(); vi.useRealTimers(); });

  it('fixes two distinct purchase keys and declared-only content with correct receipt binding', () => {
    const p = receipt(0); const content = comparabilityRequest(p, 1);
    expect(CMP_PURCHASES.map(p => p.idempotency_key)).toEqual(['51000001-0000-4000-8000-000000000001', '51000002-0000-4000-8000-000000000001']);
    expect(Object.isFrozen(CMP_PURCHASES)).toBe(true);
    expect(validateManualComparability(content, { purchase: p, now })).toMatchObject({ ok: true, value: { status: 'incomplete' } });
    expect(content.attributes.specification!.value.sha256).toBe(createHash('sha256').update(CMP_DEFINITION).digest('hex'));
    expect(p.analysis.status).toBe('unavailable');
  });
  it('executes all prepared checks using doubles, two purchases and three immutable revisions', async () => {
    const s = scenario(); const stages: string[] = [];
    expect(await runComparabilityChecks(s.prisma, c => stages.push(c))).toEqual({ purchases: [uid(1), uid(2)], revisions: 3 });
    expect(s.rows()).toHaveLength(3); expect(s.trace).toContain('rollback:write');
    expect(s.trace.filter(q => q.includes('pg_backend_pid'))).toHaveLength(6);
    expect(s.trace.filter(q => q === 'SAVEPOINT db_test_negative')).toHaveLength(21);
    expect(s.trace.filter(q => q === 'RELEASE SAVEPOINT db_test_negative')).toHaveLength(21);
    expect(stages.at(-1)).toBe('CMP_COMPLETE');
  });
  it('refuses a previously used key before any purchase creation', async () => {
    const s = scenario(); fake.getByKey.mockResolvedValue({ ok: true, value: receipt(0) });
    await expect(runComparabilityChecks(s.prisma)).rejects.toThrow('CMP_FIXTURE_EXISTS');
    expect(fake.create).not.toHaveBeenCalled(); expect(s.trace).toEqual([]);
  });
  it.each(['P4_STORAGE_PERMISSION', 'P4_STORAGE_FAILURE', 'P4_STORAGE_INTEGRITY'])('does not mistake %s for absence', async code => {
    const s = scenario(); fake.getByKey.mockResolvedValue({ ok: false, error: { code } });
    await expect(runComparabilityChecks(s.prisma)).rejects.toThrow('CMP_FIXTURE_EXISTS'); expect(fake.create).not.toHaveBeenCalled();
  });
  it.each(['42601', '25P02', '23514'])('rejects wrong negative SQLSTATE %s and restores the savepoint', async state => {
    const s = scenario(); s.negative(state);
    await expect(runComparabilityChecks(s.prisma)).rejects.toThrow('unexpected SQLSTATE');
    expect(s.trace.at(-2)).toBe('RELEASE SAVEPOINT db_test_negative'); expect(s.trace.at(-1)).toBe('rollback:write');
  });
  it.each(['42601', '25P02', '42P01'])('does not accept %s as an ACL denial', async state => {
    const s = scenario(); s.permission(state);
    await expect(runComparabilityChecks(s.prisma)).rejects.toThrow('unexpected SQLSTATE'); expect(s.rows()).toHaveLength(0);
  });
  it('detects leaked rollback state instead of claiming cleanup', async () => {
    const s = scenario(); s.leak();
    await expect(runComparabilityChecks(s.prisma)).rejects.toThrow('CMP_ROLLBACK');
  });
  it('detects changed purchase receipts during preservation checks', async () => {
    const s = scenario(); const list = fake.list.getMockImplementation()!; let calls = 0;
    fake.list.mockImplementation(() => { const result = list(); if (++calls === 2) result.value.items[0].content_sha256 = '0'.repeat(64); return result; });
    await expect(runComparabilityChecks(s.prisma)).rejects.toThrow('CMP_PRESERVATION');
  });
  it('refuses an unbounded history before creating fixtures', async () => {
    const s = scenario(); fake.list.mockResolvedValue({ ok: true, value: { items: [], next_cursor: { id: uid(1), recorded_at: now.toISOString() } } });
    await expect(runComparabilityChecks(s.prisma)).rejects.toThrow('CMP_PREFLIGHT'); expect(fake.create).not.toHaveBeenCalled();
  });
  it('drains both failed participants and rejects reuse of the same session', async () => {
    const s = scenario(); const actual = s.prisma.transaction.bind(s.prisma);
    const service = { transaction: <T>(work: (tx: DatabaseTransaction) => Promise<T>, access: 'read' | 'write') => actual(tx => work({
      ...tx, $queryRaw: async () => [{ pid: 1, database: 'synthetic_p4_comparability_test', session_user: 'detector_runtime', current_user: 'detector_runtime',
        host: '127.0.0.1', port: 5432, isolation: 'read committed', read_only: 'off' }],
    } as unknown as DatabaseTransaction), access) };
    const completed: number[] = [];
    await expect(independentPair(service, async (p, i) => { try { return await p.transaction(async () => i, 'write'); } finally { completed.push(i); } })).rejects.toThrow('CMP_SESSIONS');
    expect(completed.sort((a, b) => a - b)).toEqual([0, 1]);
  });
  it('bounds a missing second participant without waiting for the process deadline', async () => {
    vi.useFakeTimers(); const s = scenario();
    const run = independentPair(s.prisma, async (p, i) => i === 1 ? 1 : p.transaction(async () => 0, 'write'));
    const assertion = expect(run).rejects.toThrow('CMP_SESSIONS');
    await vi.advanceTimersByTimeAsync(1501); await assertion;
  });
});
