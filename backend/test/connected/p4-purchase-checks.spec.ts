import { Socket } from 'node:net';
import { matchesGlob } from 'node:path';
import unitConfig from '../../vitest.config.js';
import e2eConfig from '../../vitest.config.e2e.js';
import { Prisma } from '../../generated/prisma/client.js';
import type { PrismaService, DatabaseTransaction } from '../../src/prisma/prisma.service.js';
import { preparePurchase, type PurchaseRequest } from '../../src/purchases/purchase-contract.js';
import { P4_FIXTURES, runP4PurchaseChecks } from './p4-purchase-checks.js';

const fake = vi.hoisted(() => ({ create: vi.fn(), get: vi.fn(), list: vi.fn() }));
vi.mock('../../src/purchases/purchase-repository.js', () => ({ PurchaseRepository: class {
  constructor(readonly prisma: PrismaService) {}
  create(input: unknown) { return fake.create(this.prisma, input); }
  get(id: string) { return fake.get(id); }
  list(input?: unknown) { return fake.list(input); }
} }));
vi.mock('pg', () => { throw new Error('Offline: driver forbidden'); });

// These doubles exercise orchestration, not PostgreSQL locking or SQL execution.
// The existing PurchaseRepository suite exercises the real repository with mocks.
function scenario() {
  const records = P4_FIXTURES.slice(0, 2).map((input, i) => {
    const result = preparePurchase(input, new Date('2026-11-17T12:00:00Z'));
    if (!result.ok) throw new Error('Fixture invalid');
    return { id: `5700000${i + 1}-0000-4000-8000-000000000001`, version_id: `6700000${i + 1}-0000-4000-8000-000000000001`,
      source_reference_id: `7700000${i + 1}-0000-4000-8000-000000000001`, revision_no: 1,
      recorded_at: '2026-11-17T12:00:00.000Z', purchase: result.value.original_content.purchase,
      source: result.value.source, content_sha256: result.value.content_sha256, analysis: result.value.analysis };
  });
  let permission: string | undefined = '42501';
  let rejection: string | undefined = '22023';
  const queries: string[] = [];
  const events: string[] = [];
  const query = vi.fn(async (sql: Prisma.Sql) => {
    queries.push(sql.sql);
    if (sql.sql.includes('LIMIT 0')) { if (permission) throw { code: 'P2010', meta: { driverAdapterError: { cause: { originalCode: permission } } } }; return []; }
    if (sql.sql.includes('p4_v1_history(')) { if (rejection) throw { code: rejection }; return []; }
    if (sql.sql.includes('receipt_by_key(')) return [{ result: { contract: 'p4-storage/1.0', status: 'absent', receipt: null } }];
    if (sql.sql.includes('register_source_identity(')) return [];
    throw new Error('Unexpected offline SQL');
  });
  const execute = vi.fn(async () => 0);
  const transaction = vi.fn(async (work: (tx: DatabaseTransaction) => Promise<unknown>, access: string) => {
    events.push(`begin:${access}`);
    try { const result = await work({ $queryRaw: query, $executeRaw: execute } as unknown as DatabaseTransaction); events.push(`commit:${access}`); return result; }
    catch (error) { events.push(`rollback:${access}`); throw error; }
  });
  const success = (index: number, outcome: string) => ({ ok: true, value: { outcome, purchase: records[index] } });
  let firstCalls = 0; let concurrent = 0;
  fake.create.mockImplementation(async (prisma: PrismaService, input: PurchaseRequest) => {
    if (input.purchase.quantity === 0) return { ok: false, error: { code: 'P4_INVALID_QUANTITY' } };
    if (input.idempotency_key === P4_FIXTURES[2].idempotency_key) {
      try { await prisma.transaction(tx => tx.$executeRaw(Prisma.sql`SET CONSTRAINTS ALL IMMEDIATE`), 'write'); }
      catch { return { ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } }; }
      return success(0, 'created');
    }
    if (input.idempotency_key === P4_FIXTURES[0].idempotency_key) {
      if (input.purchase.quantity !== P4_FIXTURES[0].purchase.quantity) return { ok: false, error: { code: 'P4_IDEMPOTENCY_CONFLICT' } };
      return success(0, firstCalls++ === 0 ? 'created' : 'replay');
    }
    const position = concurrent++;
    await prisma.transaction(tx => tx.$queryRaw(Prisma.sql`SELECT app.register_source_identity('fixture')`), 'write');
    return success(1, position === 0 ? 'created' : 'replay');
  });
  fake.get.mockImplementation((id: string) => ({ ok: true, value: records.find(record => record.id === id) }));
  fake.list.mockResolvedValueOnce({ ok: true, value: { items: [], next_cursor: null } })
    .mockResolvedValueOnce({ ok: true, value: { items: [records[0]], next_cursor: { recorded_at: records[0].recorded_at, id: records[0].id } } })
    .mockResolvedValueOnce({ ok: true, value: { items: [records[1]], next_cursor: null } });
  return { prisma: { transaction } as unknown as PrismaService, query, execute, events, queries, records, transaction,
    permission(code: string | undefined) { permission = code; }, rejection(code: string | undefined) { rejection = code; } };
}

describe('P4 connected scenario orchestration, offline doubles only', () => {
  let attempts = 0;
  beforeEach(() => {
    vi.resetAllMocks(); attempts = 0;
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
      attempts++; throw new Error('Offline network guard');
    });
  });
  afterEach(() => { expect(attempts).toBe(0); vi.restoreAllMocks(); });

  it('keeps the connected entry point outside ordinary unit and E2E collection', () => {
    const file = 'test/connected/p4-purchases/purchases.integration.test.ts';
    for (const config of [unitConfig, e2eConfig]) {
      expect(config.test?.include?.some(pattern => matchesGlob(file, pattern))).toBe(false);
    }
  });

  it('fixes three unique synthetic submissions with exact BRL amounts and no V2 eligibility', () => {
    expect(P4_FIXTURES).toHaveLength(3);
    expect(new Set(P4_FIXTURES.map(f => f.idempotency_key)).size).toBe(3);
    expect(P4_FIXTURES.map(input => {
      const prepared = preparePurchase(input, new Date('2026-11-17T12:00:00Z'));
      expect(prepared.ok).toBe(true);
      if (!prepared.ok) throw new Error('Fixture invalid');
      expect(prepared.value.analysis.status).toBe('unavailable');
      return prepared.value.state.amount;
    })).toEqual(['97.00', '126.00', '23.90']);
    expect(Object.isFrozen(P4_FIXTURES)).toBe(true);
    expect(P4_FIXTURES.every(f => Object.isFrozen(f) && Object.isFrozen(f.purchase))).toBe(true);
  });

  it('refuses a preexisting test identity before any create or permission probe', async () => {
    const query = vi.fn().mockResolvedValue([{ result: { contract: 'p4-storage/1.0', status: 'found', receipt: {} } }]);
    const transaction = vi.fn(async (work: (tx: DatabaseTransaction) => Promise<unknown>) => work({ $queryRaw: query, $executeRaw: vi.fn() }));
    await expect(runP4PurchaseChecks({ transaction } as unknown as PrismaService)).rejects.toMatchObject({ diagnosticCode: 'P4_FIXTURE_EXISTS' });
    expect(fake.create).not.toHaveBeenCalled();
    expect(transaction).toHaveBeenCalledTimes(1);
    expect(query.mock.calls[0][0]).toBeInstanceOf(Prisma.sql`SELECT 1`.constructor);
  });

  it('verifies creation, replay, conflict, overlapping attempts, rollback and paged receipts', async () => {
    const s = scenario(); const stages: string[] = [];
    const result = await runP4PurchaseChecks(s.prisma, stage => stages.push(stage));
    expect(result.purchases).toEqual(s.records);
    expect(result.rollback_key).toBe(P4_FIXTURES[2].idempotency_key);
    expect(stages).toEqual(['P4_PREFLIGHT', 'P4_PERMISSIONS', 'P4_ROLLBACK', 'P4_CREATE', 'P4_IDEMPOTENCY', 'P4_CONCURRENCY', 'P4_HISTORY', 'P4_COMPLETE']);
    expect(s.queries.filter(sql => sql.includes('LIMIT 0'))).toHaveLength(11);
    expect(s.events.filter(e => e === 'rollback:read')).toHaveLength(11);
    expect(s.events.filter(e => e === 'rollback:write')).toHaveLength(1);
    expect(s.execute).toHaveBeenCalledOnce();
    expect(s.queries.filter(sql => sql.includes('register_source_identity'))).toHaveLength(2);
    expect(fake.list.mock.calls[2][0]).toEqual({ limit: 1, after: { id: s.records[0].id, recorded_at: s.records[0].recorded_at } });
    expect(s.queries.filter(sql => sql.includes('receipt_by_key'))).toHaveLength(5);
  });

  it.each(['42601', '25P02', '42P01', undefined])('does not accept %s as a table permission rejection', async (code) => {
    const s = scenario(); s.permission(code);
    await expect(runP4PurchaseChecks(s.prisma)).rejects.toMatchObject({ diagnosticCode: 'P4_PERMISSIONS' });
    expect(fake.create).not.toHaveBeenCalled();
  });
  it.each(['42601', '25P02', '42501', undefined])('refuses a rollback experiment with SQLSTATE %s', async (code) => {
    const s = scenario(); s.rejection(code);
    await expect(runP4PurchaseChecks(s.prisma)).rejects.toMatchObject({ diagnosticCode: 'P4_ROLLBACK' });
    expect(fake.create).toHaveBeenCalledTimes(2);
    expect(s.events).toContain('rollback:write');
  });
  it('stops before writes on history integrity failure', async () => {
    const s = scenario(); fake.list.mockReset().mockResolvedValue({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
    await expect(runP4PurchaseChecks(s.prisma)).rejects.toMatchObject({ diagnosticCode: 'P4_HISTORY' });
    expect(fake.create).not.toHaveBeenCalled();
  });
  it('rejects malformed absence rather than treating it as an available key', async () => {
    const s = scenario(); s.query.mockResolvedValueOnce([{ result: { contract: 'wrong', status: 'absent', receipt: null } }]);
    await expect(runP4PurchaseChecks(s.prisma)).rejects.toMatchObject({ diagnosticCode: 'P4_RECEIPT' });
    expect(fake.create).not.toHaveBeenCalled();
  });
  it('does not label failed transactions as rollback verified if the fault was never reached', async () => {
    const s = scenario(); fake.create.mockReset().mockResolvedValueOnce({ ok: false, error: { code: 'P4_INVALID_QUANTITY' } })
      .mockResolvedValueOnce({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
    await expect(runP4PurchaseChecks(s.prisma)).rejects.toMatchObject({ diagnosticCode: 'P4_ROLLBACK' });
  });
  it('does not claim success when read-back changed a version or origin', async () => {
    const s = scenario(); fake.get.mockResolvedValue({ ok: true, value: { ...s.records[0], version_id: 'changed' } });
    await expect(runP4PurchaseChecks(s.prisma)).rejects.toMatchObject({ diagnosticCode: 'P4_RECEIPT' });
  });
  it('does not accept an incomplete history or repeated pagination item', async () => {
    const s = scenario(); fake.list.mockReset()
      .mockResolvedValueOnce({ ok: true, value: { items: [], next_cursor: null } })
      .mockResolvedValue({ ok: true, value: { items: [s.records[0]], next_cursor: { id: s.records[0].id, recorded_at: s.records[0].recorded_at } } });
    await expect(runP4PurchaseChecks(s.prisma)).rejects.toMatchObject({ diagnosticCode: 'P4_HISTORY' });
    expect(fake.list).toHaveBeenCalledTimes(3);
  });
  it('bounds an unfulfilled concurrency rendezvous and clears its timer', async () => {
    const s = scenario(); const create = fake.create.getMockImplementation()!;
    let pair = 0;
    fake.create.mockImplementation((prisma: PrismaService, input: PurchaseRequest) => {
      if (input.idempotency_key === P4_FIXTURES[1].idempotency_key && ++pair === 2) {
        return { ok: false, error: { code: 'P4_STORAGE_FAILURE' } };
      }
      return create(prisma, input);
    });
    vi.useFakeTimers();
    try {
      const result = expect(runP4PurchaseChecks(s.prisma)).rejects.toMatchObject({ diagnosticCode: 'P4_CONCURRENCY' });
      await vi.advanceTimersByTimeAsync(1501); await result;
      expect(vi.getTimerCount()).toBe(0);
      expect(s.events).toContain('rollback:write');
    } finally { vi.useRealTimers(); }
  });
});
