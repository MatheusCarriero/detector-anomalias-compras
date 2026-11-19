import { Socket } from 'node:net';
import { Prisma } from '../../generated/prisma/client.js';
import { PrismaService } from '../prisma/prisma.service.js';
import { preparePurchase } from './purchase-contract.js';
import { PurchaseRepository } from './purchase-repository.js';

vi.mock('pg', () => { throw new Error('Real database forbidden'); });
vi.mock('@prisma/adapter-pg', () => ({ PrismaPg: class { constructor() { throw new Error('Real adapter forbidden'); } } }));
vi.mock('node:child_process', () => { throw new Error('Model execution forbidden'); });

const now = new Date('2026-11-15T15:00:00.000Z');
const ids = {
  actor: '11111111-1111-4111-8111-111111111111', supplier: '22222222-2222-4222-8222-222222222222',
  department: '33333333-3333-4333-8333-333333333333', currency: '44444444-4444-4444-8444-444444444444',
  identity: '55555555-5555-4555-8555-555555555555', reference: '66666666-6666-4666-8666-666666666666',
  line: '77777777-7777-4777-8777-777777777777', version: '88888888-8888-4888-8888-888888888888',
};
const config = { technicalUser: { issuer: 'p4-demo', subject: 'manual-purchase-service' } };
function request() {
  return { contract: 'p4-purchase/1.0', origin: 'manual', idempotency_key: '935af6ba-e660-40dc-a268-b13a158599cc', purchase: {
    supplier_id: 'sup-obra', product_id: 'prod-cimento', department_id: 'dep-obras', quantity: 3,
    unit_price: '0.10', currency: 'BRL', purchase_date: '2026-11-03', payment_days: 30,
  } };
}
function receipt() {
  const result = preparePurchase(request(), now); if (!result.ok) throw new Error('Fixture invalid');
  return {
    id: ids.line, version_id: ids.version, revision_no: 1, recorded_at: '2026-11-15T15:00:00.000Z',
    source_reference_id: ids.reference, source_identity_id: null,
    source_namespace: 'p4-manual/1.0', source_entity_kind: 'purchase_order_line', source_id: request().idempotency_key,
    reference_namespace: 'p4-manual/1.0', reference_kind: 'purchase_order_line',
    source_version: 'p4-purchase/1.0', source_record_key: request().idempotency_key,
    content_hash: result.value.content_sha256, original_content: result.value.original_content,
    payload_schema: 1, state: { description: 'Cimento CP II · saco de 50 kg', po_date: '2026-11-03', quantity: '3.000000', unit_price: '0.10000000', amount: '0.300000' },
    currency_code: 'BRL', supplier_matches: true, department_matches: true,
  };
}
function datedReceipt(purchaseDate: string, recordedAt: string) {
  const input = request(); input.purchase.purchase_date = purchaseDate;
  // Build a complete, internally consistent synthetic receipt, including its
  // canonical hash. Only its historical temporal validity is under test.
  const prepared = preparePurchase(input, now);
  if (!prepared.ok) throw new Error('Invalid dated fixture');
  return { ...receipt(), recorded_at: recordedAt,
    original_content: prepared.value.original_content, content_hash: prepared.value.content_sha256,
    state: { ...receipt().state, po_date: purchaseDate } };
}
function context() {
  return {
    contract: 'p4-storage/1.0', catalog_version: 'p4-catalog/1.0',
    actor: { id: ids.actor, issuer: config.technicalUser.issuer, subject: config.technicalUser.subject },
    currency: { id: ids.currency, code: 'BRL' },
    suppliers: [
      { source_id: 'sup-base', id: '22222222-2222-4222-8222-222222222220' },
      { source_id: 'sup-estrutura', id: '22222222-2222-4222-8222-222222222221' },
      { source_id: 'sup-obra', id: ids.supplier },
    ],
    departments: [
      { source_id: 'dep-almoxarifado', id: '33333333-3333-4333-8333-333333333330' },
      { source_id: 'dep-manutencao', id: '33333333-3333-4333-8333-333333333331' },
      { source_id: 'dep-obras', id: ids.department },
    ],
  };
}
function wrapped(result: unknown) { return [{ result }]; }
function receiptResult(row: unknown = receipt()) {
  return wrapped({ contract: 'p4-storage/1.0', status: row === null ? 'absent' : 'found', receipt: row });
}
function history(items: unknown[] = [], next_cursor: unknown = null) {
  return wrapped({ contract: 'p4-storage/1.0', items, next_cursor });
}

// Transaction double, NOT a PostgreSQL simulator: it records boundary decisions
// and only publishes synthetic state if the callback/commit both succeed.
function setup() {
  const calls: { sql: string; values: unknown[]; tx: number }[] = [];
  const events: string[] = [];
  let committed = false; let count = 0;
  let owner: number | null = null; let release: (() => void) | undefined; let reservation: Promise<void>;
  let fail: ((sql: string, tx: number) => unknown) | undefined;
  let respond: ((sql: string, values: unknown[]) => unknown) | undefined;
  let change: ((row: ReturnType<typeof receipt>) => unknown) = row => row;
  const client = { $connect: vi.fn(), $disconnect: vi.fn(), $transaction: vi.fn(async (work: (tx: unknown) => Promise<unknown>) => {
    const txId = ++count; events.push(`begin:${txId}`); let pending = false;
    const execute = async (query: Prisma.Sql) => {
      const sql = query.sql.replace(/\s+/g, ' ').trim(); calls.push({ sql, values: query.values, tx: txId });
      const error = fail?.(sql, txId); if (error) throw error;
      const override = respond?.(sql, query.values); if (override !== undefined) return override;
      if (sql.includes('app.p4_v1_context(')) return wrapped(context());
      if (sql.includes('app.p4_v1_receipt_by_key(')) return receiptResult(committed ? change(structuredClone(receipt())) : null);
      if (sql.includes('app.register_source_identity(')) {
        if (owner !== null && owner !== txId) await reservation;
        if (committed) throw { code: '23505' };
        owner = txId; reservation = new Promise<void>(resolve => { release = resolve; });
        return [{ id: ids.identity }];
      }
      if (sql.includes('app.observe_source(')) return [{ id: ids.reference }];
      if (sql.includes('app.write_purchase_order_line(')) { pending = true; return [{ entity_id: ids.line, version_id: ids.version, revision_no: 1 }]; }
      if (sql.includes('app.resolve_source_identity(')) return [{ resolved: 1 }];
      if (sql.includes('app.p4_v1_receipt_by_id(')) return receiptResult(pending || committed ? change(structuredClone(receipt())) : null);
      if (sql.includes('app.p4_v1_history(')) return history();
      if (sql.startsWith('SET ')) return 0;
      throw new Error(`Unexpected synthetic query: ${sql}`);
    };
    try {
      const value = await work({ $queryRaw: execute, $executeRaw: execute });
      const error = fail?.('COMMIT', txId); if (error) throw error;
      if (pending) committed = true; events.push(`commit:${txId}`); return value;
    } catch (error) { events.push(`rollback:${txId}`); throw error; }
    finally { if (owner === txId) { owner = null; release?.(); } }
  }) };
  const prisma = new PrismaService(client as unknown as ConstructorParameters<typeof PrismaService>[0]);
  return {
    repo: new PurchaseRepository(prisma, config, () => now), calls, events, client,
    failWith(fn: typeof fail) { fail = fn; }, alterRow(fn: typeof change) { change = fn; }, respondWith(fn: typeof respond) { respond = fn; },
    another(clock: () => Date = () => now, actor = config.technicalUser) { return new PurchaseRepository(prisma, { technicalUser: actor }, clock); },
    seed() { committed = true; }, get committed() { return committed; },
  };
}

let networkAttempts = 0;
beforeEach(() => { networkAttempts = 0; vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => { networkAttempts++; throw new Error('Network forbidden'); }); });
afterEach(() => { expect(networkAttempts).toBe(0); vi.restoreAllMocks(); });

describe('PurchaseRepository with synthetic transactions', () => {
  it('writes through the four authorized functions with exact source evidence and no CRUD', async () => {
    const s = setup(); const result = await s.repo.create(request());
    expect(result).toMatchObject({ ok: true, value: { outcome: 'created', purchase: { id: ids.line, version_id: ids.version, revision_no: 1, purchase: { unit_price: '0.10', total: '0.30', payment_days: 30 } } } });
    expect(s.committed).toBe(true);
    expect(s.calls.filter(c => c.sql.includes('app.register_') || c.sql.includes('app.observe_') || c.sql.includes('app.write_') || c.sql.includes('app.resolve_')).map(c => c.sql.match(/app\.(\w+)\(/)?.[1]))
      .toEqual(['register_source_identity', 'observe_source', 'write_purchase_order_line', 'resolve_source_identity']);
    const observation = s.calls.find(c => c.sql.includes('app.observe_source('))!;
    expect(observation.sql).toContain('NULL::uuid');
    expect(observation.values).toContain(request().idempotency_key);
    expect(observation.values).toContain(JSON.stringify(receipt().original_content));
    const write = s.calls.find(c => c.sql.includes('app.write_purchase_order_line('))!;
    expect(write.sql).toContain('NULL::uuid, NULL::uuid');
    expect(write.values).toEqual([JSON.stringify({ description: 'Cimento CP II · saco de 50 kg', po_date: '2026-11-03', quantity: '3', unit_price: '0.10', amount: '0.30' }), ids.supplier, ids.department, ids.currency, ids.actor, ids.reference]);
    expect(s.calls.at(-1)?.sql).toBe('SET CONSTRAINTS ALL IMMEDIATE');
    expect(s.events).toEqual(['begin:1', 'commit:1']);
    expect(s.calls.some(c => /\b(?:FROM|JOIN) app\.(?:users|suppliers|departments|currencies|source_identities|source_references|record_versions|purchase_order_lines)\b/.test(c.sql))).toBe(false);
    expect(s.calls.find(c => c.sql.includes('app.p4_v1_context('))?.values).toEqual([]);
  });
  it('recalculates through P4.2 before opening a transaction', async () => {
    const s = setup(); const input = { ...request(), purchase: { ...request().purchase, total: '999' } };
    expect(await s.repo.create(input)).toMatchObject({ ok: false, error: { code: 'P4_INVALID_STRUCTURE' } });
    expect(s.client.$transaction).not.toHaveBeenCalled();
  });
  it('returns the existing immutable receipt on retry without invoking a writer', async () => {
    const s = setup(); s.seed();
    expect(await s.repo.create(request())).toMatchObject({ ok: true, value: { outcome: 'replay', purchase: { id: ids.line } } });
    expect(s.calls.some(c => c.sql.includes('app.write_') || c.sql.includes('app.register_'))).toBe(false);
  });
  it('rejects changed content for the same key', async () => {
    const s = setup(); s.seed(); const input = request(); input.purchase.quantity = 4;
    expect(await s.repo.create(input)).toMatchObject({ ok: false, error: { code: 'P4_IDEMPOTENCY_CONFLICT' } });
    expect(s.events).toContain('rollback:1');
  });
  it.each(['app.observe_source(', 'app.write_purchase_order_line(', 'app.resolve_source_identity(', 'SET CONSTRAINTS', 'COMMIT'])('does not report success or leave staged data after failure at %s', async (stage) => {
    const s = setup(); s.failWith(sql => sql.includes(stage) ? { code: '23514', message: 'secret' } : undefined);
    expect(await s.repo.create(request())).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
    expect(s.committed).toBe(false); expect(s.events).toEqual(['begin:1', 'rollback:1']);
  });
  it('handles two concurrent repository instances with one write and a fresh read after the losing rollback', async () => {
    const s = setup(); const other = s.another();
    const results = await Promise.all([s.repo.create(request()), other.create(request())]);
    expect(results.map(r => r.ok ? r.value.outcome : 'failed').sort((a, b) => a.localeCompare(b))).toEqual(['created', 'replay']);
    expect(s.calls.filter(c => c.sql.includes('app.write_purchase_order_line('))).toHaveLength(1);
    expect(s.events.indexOf('rollback:2')).toBeGreaterThan(s.events.indexOf('commit:1'));
    expect(s.events.indexOf('begin:3')).toBeGreaterThan(s.events.indexOf('rollback:2'));
    expect(s.calls.filter(c => c.tx === 3)[0].sql).toBe('SET TRANSACTION READ ONLY');
  });
  it('returns conflict for a concurrent different payload, without a second write', async () => {
    const s = setup(); const other = request(); other.purchase.quantity = 4;
    const results = await Promise.all([s.repo.create(request()), s.another().create(other)]);
    expect(results[0]).toMatchObject({ ok: true, value: { outcome: 'created' } });
    expect(results[1]).toEqual({ ok: false, error: { code: 'P4_IDEMPOTENCY_CONFLICT' } });
    expect(s.calls.filter(c => c.sql.includes('app.write_purchase_order_line('))).toHaveLength(1);
  });
  it('lets the waiting submission reserve the key if the first transaction rolls back', async () => {
    const s = setup(); s.failWith((sql, tx) => tx === 1 && sql.includes('app.resolve_source_identity(') ? { code: '23514' } : undefined);
    const results = await Promise.all([s.repo.create(request()), s.another().create(request())]);
    expect(results[0]).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
    expect(results[1]).toMatchObject({ ok: true, value: { outcome: 'created' } });
    expect(s.events).toEqual(['begin:1', 'begin:2', 'rollback:1', 'commit:2']);
  });
  it('does not retry a writer when a unique violation has no verified winning receipt', async () => {
    const s = setup(); s.failWith(sql => sql.includes('app.register_source_identity(') ? { code: '23505' } : undefined);
    expect(await s.repo.create(request())).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
    expect(s.calls.filter(c => c.sql.includes('app.register_source_identity('))).toHaveLength(1);
    expect(s.events).toEqual(['begin:1', 'rollback:1', 'begin:2', 'commit:2']);
  });
  it('handles the installed Prisma P2010 originalCode shape without parsing driver messages', async () => {
    const s = setup();
    s.failWith(sql => {
      if (!sql.includes('app.register_source_identity(')) return;
      s.seed(); return { code: 'P2010', meta: { driverAdapterError: { cause: { originalCode: '23505', originalMessage: 'secret' } } } };
    });
    expect(await s.repo.create(request())).toMatchObject({ ok: true, value: { outcome: 'replay' } });
  });
  it.each([
    ['42501', 'P4_STORAGE_PERMISSION'], ['23503', 'P4_STORAGE_INTEGRITY'], ['22023', 'P4_STORAGE_INTEGRITY'],
    ['40001', 'P4_STORAGE_BUSY'], ['40P01', 'P4_STORAGE_BUSY'], ['55P03', 'P4_STORAGE_BUSY'], ['57014', 'P4_STORAGE_BUSY'],
    ['42601', 'P4_STORAGE_FAILURE'], ['25P02', 'P4_STORAGE_FAILURE'], ['P2028', 'P4_STORAGE_FAILURE'],
  ])('sanitizes %s without treating it as a legitimate replay', async (code, expected) => {
    const s = setup(); s.failWith(sql => sql.includes('app.write_purchase_order_line(') ? { code, message: 'postgresql://secret', stack: 'private/path' } : undefined);
    expect(await s.repo.create(request())).toEqual({ ok: false, error: { code: expected } });
    expect(s.events).toEqual(['begin:1', 'rollback:1']); expect(s.committed).toBe(false);
  });
  it('does not infer a SQLSTATE from text or unsupported Prisma metadata', async () => {
    const s = setup(); s.failWith(() => ({ code: 'P2010', meta: { code: '23505' }, message: '23505 secret' }));
    expect(await s.repo.create(request())).toEqual({ ok: false, error: { code: 'P4_STORAGE_FAILURE' } });
    expect(s.events).toEqual(['begin:1', 'rollback:1']);
  });
  it('refuses missing/inactive context instead of provisioning it', async () => {
    const s = setup(); s.failWith(sql => sql.includes('app.p4_v1_context(') ? { code: '55000', message: 'private reference' } : undefined);
    expect(await s.repo.create(request())).toEqual({ ok: false, error: { code: 'P4_REFERENCE_UNAVAILABLE' } });
    expect(s.calls.some(c => c.sql.includes('app.register_'))).toBe(false);
  });
  it.each([
    'contract', 'catalog', 'actor-id', 'actor-issuer', 'actor-subject', 'actor-extra', 'currency',
    'supplier-missing', 'supplier-extra', 'supplier-source', 'supplier-id', 'supplier-duplicate', 'supplier-order',
    'department-missing', 'department-source', 'department-id', 'department-duplicate', 'extra-field',
  ])('refuses incompatible context %s before any writer', async problem => {
    const value = context();
    if (problem === 'contract') value.contract = 'p4-storage/2.0';
    if (problem === 'catalog') value.catalog_version = 'untrusted';
    if (problem === 'actor-id') value.actor.id = 'invalid';
    if (problem === 'actor-issuer') value.actor.issuer = 'external';
    if (problem === 'actor-subject') value.actor.subject = 'someone';
    if (problem === 'actor-extra') Object.assign(value.actor, { role: 'admin' });
    if (problem === 'currency') value.currency.code = 'USD';
    if (problem === 'supplier-missing') value.suppliers.pop();
    if (problem === 'supplier-extra') value.suppliers.push({ source_id: 'sup-other', id: ids.identity });
    if (problem === 'supplier-source') value.suppliers[0].source_id = 'external';
    if (problem === 'supplier-id') value.suppliers[0].id = 'invalid';
    if (problem === 'supplier-duplicate') value.suppliers[0].id = value.suppliers[1].id;
    if (problem === 'supplier-order') value.suppliers.reverse();
    if (problem === 'department-missing') value.departments.pop();
    if (problem === 'department-source') value.departments[0].source_id = 'external';
    if (problem === 'department-id') value.departments[0].id = 'invalid';
    if (problem === 'department-duplicate') value.departments[0].id = value.departments[1].id;
    if (problem === 'extra-field') Object.assign(value, { unsafe: 'postgresql://secret' });
    const s = setup(); s.respondWith(sql => sql.includes('app.p4_v1_context(') ? wrapped(value) : undefined);
    expect(await s.repo.create(request())).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
    expect(s.calls.some(c => c.sql.includes('app.register_'))).toBe(false);
  });
  it('checks the configured technical actor against the fixed server-owned identity', async () => {
    const s = setup(); const repo = s.another(() => now, { issuer: 'different', subject: 'manual-purchase-service' });
    expect(await repo.create(request())).toEqual({ ok: false, error: { code: 'P4_REFERENCE_UNAVAILABLE' } });
    expect(s.calls.some(c => c.sql.includes('app.register_'))).toBe(false);
    expect(s.calls.find(c => c.sql.includes('app.p4_v1_context('))?.values).toEqual([]);
  });
  it.each([
    [], [{ result: null }], [{ result: '{}' }], [{ result: {} }, { result: {} }],
    [{ result: {}, extra: true }],
    wrapped({ contract: 'unknown', status: 'absent', receipt: null }),
    wrapped({ contract: 'p4-storage/1.0', status: 'absent' }),
    wrapped({ contract: 'p4-storage/1.0', status: 'absent', receipt: receipt() }),
    wrapped({ contract: 'p4-storage/1.0', status: 'found', receipt: null }),
    wrapped({ contract: 'p4-storage/1.0', status: 'missing', receipt: null }),
    wrapped({ contract: 'p4-storage/1.0', status: 'absent', receipt: null, details: 'private' }),
    receiptResult({ ...receipt(), extra: 'private' }),
  ].map(response => ({ response })))('does not confuse malformed receipt envelopes with absence: %#', async ({ response }) => {
    const s = setup(); s.respondWith(sql => sql.includes('app.p4_v1_receipt_by_id(') ? response : undefined);
    expect(await s.repo.get(ids.line)).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
  });
  it('validates the same receipt envelope on idempotency reads and preserves permission failures', async () => {
    const s = setup(); s.respondWith(sql => sql.includes('app.p4_v1_receipt_by_key(')
      ? wrapped({ contract: 'p4-storage/1.0', status: 'absent', receipt: receipt() }) : undefined);
    expect(await s.repo.create(request())).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
    expect(s.calls.some(c => c.sql.includes('app.register_'))).toBe(false);
    s.respondWith(undefined); s.failWith(sql => sql.includes('app.p4_v1_receipt_by_key(') ? { code: '42501' } : undefined);
    expect(await s.repo.create(request())).toEqual({ ok: false, error: { code: 'P4_STORAGE_PERMISSION' } });
  });
  it('refuses an existing unresolved identity instead of repairing or overwriting it', async () => {
    const s = setup(); s.failWith(sql => sql.includes('app.p4_v1_receipt_by_key(') ? { code: '23514' } : undefined);
    expect(await s.repo.create(request())).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
    expect(s.calls.some(c => c.sql.includes('app.resolve_') || c.sql.includes('app.register_'))).toBe(false);
  });
  it.each(['hash', 'total', 'payload', 'source', 'identity', 'version', 'currency', 'supplier', 'department', 'date'])('rejects corrupt stored %s on a read', async (problem) => {
    const s = setup(); s.seed(); s.alterRow(row => {
      if (problem === 'hash') row.content_hash = '0'.repeat(64);
      if (problem === 'total') row.original_content.purchase.total = '999.00';
      if (problem === 'payload') row.state.amount = '9.000000';
      if (problem === 'source') row.source_record_key = 'wrong';
      if (problem === 'identity') Object.assign(row, { source_identity_id: ids.identity });
      if (problem === 'version') row.revision_no = 2;
      if (problem === 'currency') row.currency_code = 'USD';
      if (problem === 'supplier') row.supplier_matches = false;
      if (problem === 'department') row.department_matches = false;
      if (problem === 'date') row.recorded_at = '2026-02-30T00:00:00.000Z';
      return row;
    });
    expect(await s.repo.get(ids.line)).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
  });
  it('reads a creation receipt under READ ONLY with unavailable analysis and preserved product/unit/terms', async () => {
    const s = setup(); s.seed();
    expect(await s.repo.get(ids.line)).toMatchObject({ ok: true, value: { id: ids.line, purchase: { product: { id: 'prod-cimento', unit: 'saco de 50 kg' }, payment_days: 30 }, analysis: { status: 'unavailable', reason: 'manual_source_incompatible_with_procurement_v2' } } });
    expect(s.calls[0].sql).toBe('SET TRANSACTION READ ONLY');
    const read = s.calls.find(c => c.sql.includes('app.p4_v1_receipt_by_id('))!;
    expect(read.values).toEqual([ids.line]); expect(read.sql).not.toContain(ids.line);
  });
  it.each([
    ['2020-02-29', '2026-11-03T03:00:00.000Z', true],
    ['2026-11-03', '2026-11-03T03:00:00.000Z', true],
    ['2026-11-02', '2026-11-03T02:59:59.999Z', true],
    ['2026-11-03', '2026-11-03T02:59:59.999Z', false],
    ['2026-11-03', '2026-11-02T15:00:00.000Z', false],
  ] as const)('validates commercial date %s against revision time %s in Sao Paulo, eligible=%s', async (purchaseDate, recordedAt, eligible) => {
    const row = datedReceipt(purchaseDate, recordedAt); const s = setup();
    s.respondWith(sql => sql.includes('app.p4_v1_receipt_by_id(') ? receiptResult(row)
      : sql.includes('app.p4_v1_history(') ? history([row]) : undefined);
    const read = await s.repo.get(ids.line); const page = await s.repo.list();
    if (eligible) {
      expect(read).toMatchObject({ ok: true, value: { recorded_at: recordedAt, purchase: { purchase_date: purchaseDate } } });
      expect(page).toMatchObject({ ok: true, value: { items: [{ recorded_at: recordedAt, purchase: { purchase_date: purchaseDate } }] } });
    } else {
      const failure = { ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } };
      expect(read).toEqual(failure); expect(page).toEqual(failure);
      // Passing time must never legitimize a purchase that was future-dated at registration.
      expect(await s.another(() => new Date('2030-01-01T15:00:00.000Z')).get(ids.line)).toEqual(failure);
    }
  });
  it('does not replay an otherwise consistent purchase that was future-dated when registered', async () => {
    const s = setup();
    s.respondWith(sql => sql.includes('app.p4_v1_receipt_by_key(')
      ? receiptResult(datedReceipt('2026-11-03', '2026-11-02T15:00:00.000Z')) : undefined);
    expect(await s.repo.create(request())).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
    expect(s.calls.some(c => c.sql.includes('app.write_') || c.sql.includes('app.register_'))).toBe(false);
  });
  it('returns not found without disclosing purchases from other namespaces', async () => {
    const s = setup(); expect(await s.repo.get(ids.line)).toEqual({ ok: false, error: { code: 'P4_NOT_FOUND' } });
    expect(s.calls.at(-1)?.sql).toBe('SELECT app.p4_v1_receipt_by_id(?::uuid) AS result');
  });
  it('reads by canonical idempotency UUID with the authorized function and no writer', async () => {
    const s = setup(); s.seed();
    expect(await s.repo.getByKey(request().idempotency_key.toUpperCase())).toMatchObject({ ok: true, value: { id: ids.line } });
    expect(s.calls[0].sql).toBe('SET TRANSACTION READ ONLY');
    expect(s.calls.at(-1)).toMatchObject({ sql: 'SELECT app.p4_v1_receipt_by_key(?::uuid) AS result', values: [request().idempotency_key] });
    expect(s.calls.some(c => /app\.(write_|register_|observe_|resolve_)/.test(c.sql))).toBe(false);
  });
  it('distinguishes missing, mismatched and corrupted idempotency receipts', async () => {
    const s = setup();
    expect(await s.repo.getByKey(request().idempotency_key)).toEqual({ ok: false, error: { code: 'P4_NOT_FOUND' } });
    s.seed();
    expect(await s.repo.getByKey('00000000-0000-4000-8000-000000000000')).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
    s.respondWith(sql => sql.includes('receipt_by_key') ? receiptResult({ ...receipt(), revision_no: 2 }) : undefined);
    expect(await s.repo.getByKey(request().idempotency_key)).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
  });
  it.each([null, '', "' OR true --", '00000000-0000-1000-8000-000000000000', `${request().idempotency_key}\n`])(
    'rejects an invalid idempotency lookup before SQL: %s', async key => {
      const s = setup();
      expect(await s.repo.getByKey(key)).toEqual({ ok: false, error: { code: 'P4_INVALID_QUERY' } });
      expect(s.client.$transaction).not.toHaveBeenCalled();
    },
  );
  it.each(["' OR true --", '', null, `${ids.line}\n`])('rejects invalid identifier %s before a transaction', async id => {
    const s = setup(); expect(await s.repo.get(id)).toEqual({ ok: false, error: { code: 'P4_INVALID_QUERY' } });
    expect(s.client.$transaction).not.toHaveBeenCalled();
  });
  it('lists creation history with a bounded keyset page and a stable timestamp/UUID tie-break', async () => {
    const s = setup(); s.respondWith((sql, values) => {
      if (!sql.includes('app.p4_v1_history(')) return;
      return values[1] === null ? history([receipt()], { recorded_at: now.toISOString(), id: ids.line })
        : history([{ ...receipt(), id: '66666666-6666-4666-8666-666666666666' }]);
    });
    const first = await s.repo.list({ limit: 1 });
    expect(first).toMatchObject({ ok: true, value: { items: [{ id: ids.line }], next_cursor: { recorded_at: now.toISOString(), id: ids.line } } });
    const after = { recorded_at: now.toISOString(), id: ids.line };
    expect(await s.repo.list({ limit: 1, after })).toMatchObject({ ok: true, value: { next_cursor: null } });
    const reads = s.calls.filter(c => c.sql.includes('app.p4_v1_history('));
    expect(reads[0].values).toEqual([1, null, null]);
    expect(reads[1].values).toEqual([1, now.toISOString(), ids.line]);
    expect(reads[1].sql).toBe('SELECT app.p4_v1_history(?::integer, ?::timestamptz, ?::uuid) AS result');
  });
  it('returns an empty page and no cursor when history is empty', async () => {
    const s = setup(); expect(await s.repo.list()).toEqual({ ok: true, value: { items: [], next_cursor: null } });
  });
  it.each([
    'contract', 'extra', 'items', 'overflow', 'duplicate', 'ascending', 'same-as-cursor',
    'newer-than-cursor', 'cursor-extra', 'cursor-id', 'cursor-time', 'cursor-empty', 'cursor-partial-page',
  ])('rejects inconsistent history %s', async problem => {
    const row = receipt();
    let response = history([row]); let limit = 2;
    const after = { id: '99999999-9999-4999-8999-999999999999', recorded_at: now.toISOString() };
    if (problem === 'contract') response = wrapped({ contract: 'p4-storage/2.0', items: [], next_cursor: null });
    if (problem === 'extra') response = wrapped({ contract: 'p4-storage/1.0', items: [], next_cursor: null, unexpected: true });
    if (problem === 'items') response = wrapped({ contract: 'p4-storage/1.0', items: {}, next_cursor: null });
    if (problem === 'overflow') { limit = 1; response = history([row, row]); }
    if (problem === 'duplicate') response = history([row, row]);
    if (problem === 'ascending') response = history([row, { ...row, id: '88888888-8888-4888-8888-888888888888' }]);
    if (problem === 'same-as-cursor') response = history([{ ...row, ...after }]);
    if (problem === 'newer-than-cursor') response = history([{ ...row, recorded_at: '2026-11-15T15:01:00.000Z' }]);
    if (problem === 'cursor-extra') { limit = 1; response = history([row], { recorded_at: row.recorded_at, id: row.id, extra: true }); }
    if (problem === 'cursor-id') { limit = 1; response = history([row], after); }
    if (problem === 'cursor-time') { limit = 1; response = history([row], { id: row.id, recorded_at: '2026-11-15' }); }
    if (problem === 'cursor-empty') response = history([], after);
    if (problem === 'cursor-partial-page') response = history([row], { id: row.id, recorded_at: row.recorded_at });
    const s = setup(); s.respondWith(sql => sql.includes('app.p4_v1_history(') ? response : undefined);
    expect(await s.repo.list({ limit, after })).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
  });
  it('preserves explicit catalog and receipt errors without exposing driver details', async () => {
    const s = setup(); s.failWith(sql => sql.includes('app.p4_v1_history(')
      ? { code: '23514', message: 'private namespace content' } : undefined);
    expect(await s.repo.list()).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
  });
  it.each([{ limit: 0 }, { limit: 101 }, { limit: 1.2 }, { limit: null }, { limit: '2' }, { after: { id: ids.line } }, { after: { id: ids.line, recorded_at: 'bad' } }, { sql: 'DROP TABLE app.users' }])('rejects invalid page input %s', async query => {
    const s = setup(); expect(await s.repo.list(query as never)).toEqual({ ok: false, error: { code: 'P4_INVALID_QUERY' } });
    expect(s.client.$transaction).not.toHaveBeenCalled();
  });
  it('sanitizes a failed trusted clock before starting any transaction', async () => {
    const s = setup(); const repo = s.another(() => { throw new Error('private environment details'); });
    expect(await repo.create(request())).toEqual({ ok: false, error: { code: 'P4_STORAGE_FAILURE' } });
    expect(s.client.$transaction).not.toHaveBeenCalled();
  });
});
