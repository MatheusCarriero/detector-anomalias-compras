import { createHash } from 'node:crypto';
import { preparePurchase } from './purchase-contract.js';
import type { PurchaseRecord, PurchaseRepository } from './purchase-repository.js';
import type { PrismaService, DatabaseTransaction } from '../prisma/prisma.service.js';
import type { ManualComparabilityRequest } from './statistics/manual-comparability.js';
import { PurchaseComparabilityRepository } from './purchase-comparability.repository.js';

vi.mock('pg', () => { throw new Error('Real database forbidden'); });
vi.mock('@prisma/adapter-pg', () => { throw new Error('Real adapter forbidden'); });
vi.mock('./statistics/price-analysis.js', () => { throw new Error('Statistical execution forbidden'); });
vi.mock('node:child_process', () => { throw new Error('Model execution forbidden'); });

const now = new Date('2026-11-19T15:00:00.000Z');
const id = '77777777-7777-4777-8777-777777777777';
const definition = 'Synthetic cement specification; not independently verified.';
function receipt(): PurchaseRecord {
  const p = preparePurchase({ contract: 'p4-purchase/1.0', origin: 'manual',
    idempotency_key: '935af6ba-e660-40dc-a268-b13a158599cc', purchase: {
      supplier_id: 'sup-obra', product_id: 'prod-cimento', department_id: 'dep-obras',
      quantity: 3, unit_price: '0.10', currency: 'BRL', purchase_date: '2026-11-03', payment_days: 30,
    } }, now);
  if (!p.ok) throw new Error('Fixture invalid');
  return { id, version_id: '88888888-8888-4888-8888-888888888888', revision_no: 1,
    recorded_at: '2026-11-15T15:00:00.000Z', source_reference_id: '66666666-6666-4666-8666-666666666666',
    source: p.value.source, content_sha256: p.value.content_sha256, purchase: p.value.original_content.purchase, analysis: p.value.analysis };
}
function input(): ManualComparabilityRequest {
  const p = receipt();
  return { contract: 'p4-manual-comparability/1.0', id: '99999999-9999-4999-8999-999999999999', revision: 1, supersedes: null,
    purchase: { id, version_id: p.version_id, content_sha256: p.content_sha256 }, attributes: {
      specification: { value: { id: 'cement', version: '1', product_id: 'prod-cimento', sha256: createHash('sha256').update(definition).digest('hex') },
        provenance: { kind: 'declared', actor_id: 'test-declarant', declared_at: '2026-11-18T15:00:00.000Z' } },
    } };
}
type Stored = { canonical_content: string; content_sha256: string; definitions: unknown;
  recorded_at: string; source_reference_id: string; actor_user_id: string };
// Transaction/locking simulation, NOT evidence of PostgreSQL execution.
function fixture() {
  let stored: Stored[] = []; let definitionsRegistry = new Map<string, string>();
  let queue = Promise.resolve(); let failCommit = false;
  const calls: { sql: string; access: string }[] = [];
  let failure: unknown; let corrupt: ((row: Stored) => Stored) | undefined;
  const purchases = { get: vi.fn<PurchaseRepository['get']>().mockResolvedValue({ ok: true, value: receipt() }) };
  const prisma = { transaction: async <T>(work: (tx: DatabaseTransaction) => Promise<T>, access: 'read' | 'write') => {
    const previous = queue; let release!: () => void; queue = new Promise<void>(r => { release = r; });
    await previous; const pending = structuredClone(stored); const pendingDefinitions = new Map(definitionsRegistry);
    try {
      const query = (sql: { text: string; values: unknown[] }) => {
        calls.push({ sql: sql.text, access }); if (failure) throw failure;
        if (sql.text.startsWith('SET ')) return 0;
        let row: Stored | undefined; let outcome = 'found';
        if (sql.text.includes('p4_cmp_write')) {
          const [canonical, definitions] = sql.values as [string, string];
          const candidate = JSON.parse(canonical) as ManualComparabilityRequest;
          row = pending.find(r => JSON.parse(r.canonical_content).id === candidate.id);
          if (row) {
            if (row.canonical_content !== canonical || JSON.stringify(row.definitions) !== definitions) throw { code: '23505' };
            outcome = 'replay';
          } else {
            const head = pending.at(-1); const predecessor = head && JSON.parse(head.canonical_content) as ManualComparabilityRequest;
            if (candidate.revision !== pending.length + 1 || (predecessor && candidate.supersedes?.id !== predecessor.id)
              || (head && candidate.supersedes?.content_sha256 !== head.content_sha256)) throw { code: '23505' };
            const original = JSON.parse(definitions) as Record<string, string>;
            for (const kind of Object.keys(original).sort()) {
              const attribute = candidate.attributes[kind as keyof typeof candidate.attributes]!;
              const value = attribute.value as Record<string, unknown>;
              const key = JSON.stringify([kind, value.id ?? value.condition_id ?? value.schedule_id,
                value.version ?? value.condition_version ?? value.schedule_version]);
              const declaration = JSON.stringify([value, original[kind]]);
              if (pendingDefinitions.has(key) && pendingDefinitions.get(key) !== declaration) throw { code: '23505' };
              pendingDefinitions.set(key, declaration);
            }
            row = { canonical_content: canonical, content_sha256: createHash('sha256').update(canonical).digest('hex'),
              definitions: JSON.parse(definitions), recorded_at: now.toISOString(),
              source_reference_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', actor_user_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb' };
            pending.push(row); outcome = 'created';
          }
        } else if (sql.text.includes('p4_cmp_read')) {
          const revision = sql.values[1];
          row = revision === null ? pending.at(-1) : pending.find(r => JSON.parse(r.canonical_content).revision === revision);
        } else throw new Error('Unexpected SQL');
        return [{ result: { contract: 'p4-comparability-storage/1.0', outcome: row ? outcome : 'absent',
          revision: row ? corrupt?.(structuredClone(row)) ?? structuredClone(row) : null } }];
      };
      const result = await work({ $queryRaw: query, $executeRaw: query } as unknown as DatabaseTransaction);
      if (failCommit) throw new Error('private commit failure');
      stored = pending; definitionsRegistry = pendingDefinitions; return result;
    } finally { release(); }
  } };
  return { repo: new PurchaseComparabilityRepository(prisma as unknown as PrismaService, purchases, () => now), purchases, calls,
    rows: () => structuredClone(stored), definitions: () => new Map(definitionsRegistry),
    fail: (e: unknown) => { failure = e; }, commitFailure: () => { failCommit = true; },
    corrupt: (f: (r: Stored) => Stored) => { corrupt = f; } };
}

describe('comparability repository, offline transaction simulation', () => {
  it('creates and reads declared metadata, without changing the purchase or running statistics', async () => {
    const f = fixture(); const request = input(); const before = structuredClone(request);
    const saved = await f.repo.save(request, { specification: definition });
    expect(saved).toMatchObject({ ok: true, value: { outcome: 'created', revision: { validation: { status: 'incomplete' } } } });
    expect(await f.repo.get(id, 1)).toMatchObject({ ok: true, value: { validation: { content: request } } });
    expect(request).toEqual(before); expect(f.rows()).toHaveLength(1);
    expect(f.calls.every(c => !/SELECT .*FROM app\.(purchase_order_lines|p4_comparability)/.test(c.sql))).toBe(true);
  });
  it('replays exactly once and rejects altered content with the same UUID', async () => {
    const f = fixture(); await f.repo.save(input(), { specification: definition });
    expect(await f.repo.save(input(), { specification: definition })).toMatchObject({ ok: true, value: { outcome: 'replay' } });
    const changed = input(); changed.attributes.specification!.provenance.actor_id = 'other';
    expect(await f.repo.save(changed, { specification: definition })).toMatchObject({ ok: false, error: { code: 'P4_COMPARABILITY_CONFLICT' } });
    expect(f.rows()).toHaveLength(1);
  });
  it('serializes simulated first-revision races', async () => {
    const f = fixture(); const other = input(); other.id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
    const results = await Promise.all([f.repo.save(input(), { specification: definition }), f.repo.save(other, { specification: definition })]);
    expect(results.filter(r => r.ok)).toHaveLength(1); expect(f.rows()).toHaveLength(1);
  });
  it('returns one creation and one replay for simultaneous identical submissions', async () => {
    const f = fixture();
    const results = await Promise.all([f.repo.save(input(), { specification: definition }), f.repo.save(input(), { specification: definition })]);
    expect(results.map(r => r.ok && r.value.outcome)).toEqual(['created', 'replay']);
    expect(f.rows()).toHaveLength(1); expect(f.definitions().size).toBe(1);
  });
  it('retains prior revisions and rejects competing or stale predecessors', async () => {
    const f = fixture(); await f.repo.save(input(), { specification: definition }); const old = f.rows()[0];
    const next = input(); next.id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'; next.revision = 2;
    next.supersedes = { id: input().id, revision: 1, content_sha256: old.content_sha256 };
    const competing = structuredClone(next); competing.id = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
    const results = await Promise.all([f.repo.save(next, { specification: definition }), f.repo.save(competing, { specification: definition })]);
    expect(results.filter(r => r.ok)).toHaveLength(1); expect(f.rows()[0]).toEqual(old);
    expect(await f.repo.get(id, 1)).toMatchObject({ ok: true });
    expect(await f.repo.get(id)).toMatchObject({ ok: true, value: { validation: { content: { revision: 2 } } } });
  });
  it('does not return success when commit fails', async () => {
    const f = fixture(); f.commitFailure();
    expect(await f.repo.save(input(), { specification: definition })).toMatchObject({ ok: false });
    expect(f.rows()).toEqual([]); expect(f.definitions().size).toBe(0);
  });
  it('requires a new definition version for changed content and keeps the previous definition', async () => {
    const f = fixture(); await f.repo.save(input(), { specification: definition });
    const before = f.rows()[0]; const originalDefinitions = f.definitions();
    const next = input(); next.id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'; next.revision = 2;
    next.supersedes = { id: input().id, revision: 1, content_sha256: before.content_sha256 };
    const revisedText = 'A different synthetic specification.';
    next.attributes.specification!.value.sha256 = createHash('sha256').update(revisedText).digest('hex');
    expect(await f.repo.save(next, { specification: revisedText })).toEqual({ ok: false, error: { code: 'P4_COMPARABILITY_CONFLICT' } });
    expect(f.rows()).toHaveLength(1); expect(f.definitions()).toEqual(originalDefinitions);
    next.attributes.specification!.value.version = '2';
    expect(await f.repo.save(next, { specification: revisedText })).toMatchObject({ ok: true });
    expect(f.definitions().size).toBe(2); expect(f.rows()[0]).toEqual(before);
  });
  it.each(['', ' ', '\0', '\ud800', 'x'.repeat(16001)])('rejects invalid definition bytes without writing', async text => {
    const f = fixture(); const request = input();
    request.attributes.specification!.value.sha256 = createHash('sha256').update(text).digest('hex');
    expect(await f.repo.save(request, { specification: text })).toMatchObject({ ok: false });
    expect(f.calls).toEqual([]);
  });
  it('preserves valid unicode and newlines in the original definition', async () => {
    const f = fixture(); const request = input(); const text = 'Especificação declarada: aço.\nEmbalagem: 50 kg. 🧱';
    request.attributes.specification!.value.sha256 = createHash('sha256').update(text).digest('hex');
    expect(await f.repo.save(request, { specification: text })).toMatchObject({ ok: true, value: { revision: { definitions: { specification: text } } } });
  });
  it('rejects malformed UTF-16 declarations before PostgreSQL JSON conversion', async () => {
    const f = fixture(); const request = input(); request.attributes.specification!.provenance.actor_id = '\ud800';
    expect(await f.repo.save(request, { specification: definition })).toEqual({ ok: false, error: { code: 'P4_COMPARABILITY_INVALID' } });
    expect(f.calls).toEqual([]);
  });
  it.each(['P4_NOT_FOUND', 'P4_STORAGE_PERMISSION', 'P4_STORAGE_INTEGRITY'] as const)('preserves purchase read failure %s without writing', async code => {
    const f = fixture(); f.purchases.get.mockResolvedValue({ ok: false, error: { code } });
    expect(await f.repo.save(input(), { specification: definition })).toEqual({ ok: false, error: { code } });
    expect(f.calls).toEqual([]);
  });
  it.each([
    ['42501', 'P4_STORAGE_PERMISSION'], ['23514', 'P4_STORAGE_INTEGRITY'], ['23503', 'P4_STORAGE_INTEGRITY'],
    ['23505', 'P4_COMPARABILITY_CONFLICT'], ['40001', 'P4_STORAGE_BUSY'], ['55P03', 'P4_STORAGE_BUSY'],
    ['22023', 'P4_COMPARABILITY_INVALID'], ['42601', 'P4_STORAGE_FAILURE'], ['25P02', 'P4_STORAGE_FAILURE'],
  ])('sanitizes SQLSTATE %s', async (code, expected) => {
    const f = fixture(); f.fail({ code: 'P2010', meta: { driverAdapterError: { cause: { originalCode: code } } }, message: 'private' });
    expect(await f.repo.save(input(), { specification: definition })).toEqual({ ok: false, error: { code: expected } });
  });
  it.each(['hash', 'binding', 'definition', 'extra', 'verified'])('rejects invalid %s before SQL writes', async problem => {
    const f = fixture(); const request = input(); let definitions: unknown = { specification: definition };
    if (problem === 'hash') request.attributes.specification!.value.sha256 = '0'.repeat(64);
    if (problem === 'binding') request.purchase.version_id = '11111111-1111-4111-8111-111111111111';
    if (problem === 'definition') definitions = {};
    if (problem === 'extra') definitions = { specification: definition, rogue: 'extra' };
    if (problem === 'verified') Object.assign(request.attributes.specification!.provenance, { kind: 'verified' });
    expect(await f.repo.save(request, definitions)).toMatchObject({ ok: false }); expect(f.calls).toEqual([]);
  });
  it.each(['content', 'hash', 'definitions', 'time', 'source', 'extra'])('fails closed on corrupted storage %s', async problem => {
    const f = fixture(); await f.repo.save(input(), { specification: definition });
    f.corrupt(row => {
      if (problem === 'content') row.canonical_content = '{}';
      if (problem === 'hash') row.content_sha256 = '0'.repeat(64);
      if (problem === 'definitions') row.definitions = {};
      if (problem === 'time') row.recorded_at = 'invalid';
      if (problem === 'source') row.source_reference_id = 'invalid';
      if (problem === 'extra') Object.assign(row, { verified: true });
      return row;
    });
    expect(await f.repo.get(id)).toEqual({ ok: false, error: { code: 'P4_STORAGE_INTEGRITY' } });
  });
  it('rolls back a write whose returned receipt fails integrity validation', async () => {
    const f = fixture(); f.corrupt(row => ({ ...row, content_sha256: '0'.repeat(64) }));
    expect(await f.repo.save(input(), { specification: definition })).toMatchObject({ ok: false });
    expect(f.rows()).toEqual([]);
  });
  it('distinguishes absence and rejects invalid revision queries', async () => {
    const f = fixture(); expect(await f.repo.get(id)).toEqual({ ok: true, value: null });
    expect(await f.repo.get(id, 0)).toMatchObject({ ok: false });
    expect(await f.repo.get(id, 1.5)).toMatchObject({ ok: false });
  });
});
