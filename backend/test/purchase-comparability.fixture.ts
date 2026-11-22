import { vi } from 'vitest';
import { preparePurchase } from '../src/purchases/purchase-contract.js';
import type { PurchaseRecord, PurchaseRepository } from '../src/purchases/purchase-repository.js';
import type { Prisma } from '../generated/prisma/client.js';
import type { DatabaseTransaction } from '../src/prisma/prisma.service.js';

// Synthetic SQL-boundary double. No driver, database, model or network access.
export function comparabilityFixture() {
  const date = '2026-11-19T15:00:00.000Z';
  const id = '77777777-7777-4777-8777-777777777777';
  const prepared = preparePurchase({ contract: 'p4-purchase/1.0', origin: 'manual',
    idempotency_key: '935af6ba-e660-40dc-a268-b13a158599cc', purchase: {
      supplier_id: 'sup-obra', product_id: 'prod-cimento', department_id: 'dep-obras', quantity: 3,
      unit_price: '0.10', currency: 'BRL', purchase_date: '2026-11-03', payment_days: 30,
    } }, new Date(date));
  if (!prepared.ok) throw new Error('Invalid fixture');
  const receipt: PurchaseRecord = { id, version_id: '88888888-8888-4888-8888-888888888888', revision_no: 1,
    recorded_at: date, source_reference_id: '66666666-6666-4666-8666-666666666666',
    source: prepared.value.source, content_sha256: prepared.value.content_sha256,
    purchase: prepared.value.original_content.purchase, analysis: prepared.value.analysis };
  const purchases = { get: vi.fn<PurchaseRepository['get']>().mockResolvedValue({ ok: true, value: receipt }) };
  const body = { metadata: { contract: 'p4-manual-comparability/1.0',
    id: '99999999-9999-4999-8999-999999999999', revision: 1, supersedes: null,
    purchase: { id, version_id: receipt.version_id, content_sha256: receipt.content_sha256 },
    attributes: { currency: { value: 'BRL', provenance: { kind: 'declared', actor_id: 'fixture', declared_at: date } } },
  }, definitions: {} };
  let stored: Record<string, unknown> | null = null;
  let failure: unknown;
  const query = vi.fn(async (sql: Prisma.Sql) => {
    if (failure) throw failure;
    if (sql.sql.startsWith('SET ')) return 0;
    let outcome = stored ? 'found' : 'absent';
    if (sql.sql.includes('p4_cmp_write')) {
      const text = sql.values[0] as string;
      if (stored && stored.canonical_content !== text) throw { code: '23505' };
      outcome = stored ? 'replay' : 'created';
      // The real repository computes/validates this content hash independently.
      const { createHash } = await import('node:crypto');
      stored = { canonical_content: text, content_sha256: createHash('sha256').update(text).digest('hex'),
        definitions: JSON.parse(sql.values[1] as string), recorded_at: date,
        source_reference_id: receipt.source_reference_id, actor_user_id: '11111111-1111-4111-8111-111111111111' };
    } else if (!sql.sql.includes('p4_cmp_read')) throw new Error('Unexpected SQL');
    const absentRevision = sql.sql.includes('p4_cmp_read') && sql.values[1] !== null && sql.values[1] !== 1;
    return [{ result: { contract: 'p4-comparability-storage/1.0', outcome: absentRevision ? 'absent' : outcome,
      revision: absentRevision ? null : stored } }];
  });
  const client = { $connect: vi.fn(async () => {}), $disconnect: vi.fn(async () => {}),
    $transaction: async <T>(work: (tx: DatabaseTransaction) => Promise<T>): Promise<T> => {
      const before = structuredClone(stored);
      // The double uses ordinary Promises; the repository awaits each call and
      // does not use Prisma's array/batch transaction protocol.
      try { return await work({ $queryRaw: query, $executeRaw: query } as unknown as DatabaseTransaction); }
      catch (error) { stored = before; throw error; }
    } };
  return { id, receipt, body, purchases, client, query, fail: (error: unknown) => { failure = error; } };
}
