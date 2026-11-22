import { preparePurchase } from './purchase-contract.js';
import type { PurchaseRecord, PurchaseRepository, RepositoryResult } from './purchase-repository.js';
import { PurchaseStatisticsService } from './purchase-statistics.service.js';

vi.mock('./statistics/price-analysis.js', () => { throw new Error('Statistical executor forbidden'); });
vi.mock('./purchase-repository.js', () => { throw new Error('Only the injected repository mock is permitted'); });
vi.mock('pg', () => { throw new Error('Database forbidden'); });
vi.mock('@prisma/adapter-pg', () => { throw new Error('Database adapter forbidden'); });
vi.mock('node:net', () => { throw new Error('Network forbidden'); });
vi.mock('node:child_process', () => { throw new Error('Model execution forbidden'); });

function receipt(): PurchaseRecord {
  const prepared = preparePurchase({ contract: 'p4-purchase/1.0', origin: 'manual',
    idempotency_key: '935af6ba-e660-40dc-a268-b13a158599cc', purchase: {
      supplier_id: 'sup-base', product_id: 'prod-tubo', department_id: 'dep-obras', quantity: 2,
      unit_price: '25.75', currency: 'BRL', purchase_date: '2026-11-03', payment_days: 30,
    } }, new Date('2026-11-15T15:00:00.000Z'));
  if (!prepared.ok) throw new Error('Invalid synthetic fixture');
  return { id: '77777777-7777-4777-8777-777777777777', version_id: '88888888-8888-4888-8888-888888888888',
    revision_no: 1, recorded_at: '2026-11-15T15:00:00.000Z', source_reference_id: '66666666-6666-4666-8666-666666666666',
    source: prepared.value.source, purchase: prepared.value.original_content.purchase,
    content_sha256: prepared.value.content_sha256, analysis: prepared.value.analysis };
}

describe('PurchaseStatisticsService with an injected read-only mock', () => {
  function setup() {
    const repository = { get: vi.fn<PurchaseRepository['get']>(), list: vi.fn(), create: vi.fn() };
    return { repository, service: new PurchaseStatisticsService(repository) };
  }

  it('does nothing during construction and reads only the requested purchase', async () => {
    const { repository, service } = setup();
    expect(repository.get).not.toHaveBeenCalled();
    const input = receipt();
    const before = structuredClone(input);
    repository.get.mockResolvedValue({ ok: true, value: input });
    const result = await service.getEligibility(input.id);
    expect(repository.get).toHaveBeenCalledExactlyOnceWith(input.id);
    expect(result).toMatchObject({ ok: true, value: { status: 'unavailable', evidence: { id: input.id } } });
    expect(repository.list).not.toHaveBeenCalled();
    expect(repository.create).not.toHaveBeenCalled();
    expect(input).toEqual(before);
  });

  it.each([
    'P4_STORAGE_FAILURE', 'P4_STORAGE_PERMISSION', 'P4_STORAGE_INTEGRITY', 'P4_STORAGE_BUSY',
    'P4_REFERENCE_UNAVAILABLE', 'P4_NOT_FOUND', 'P4_INVALID_QUERY',
  ] as const)('preserves %s as an error, never statistical unavailability', async code => {
    const { repository, service } = setup();
    repository.get.mockResolvedValue({ ok: false, error: { code } });
    expect(await service.getEligibility(receipt().id)).toEqual({ ok: false, error: { code } });
    expect(repository.get).toHaveBeenCalledTimes(1);
    expect(repository.list).not.toHaveBeenCalled();
    expect(repository.create).not.toHaveBeenCalled();
  });

  it('delegates identifier validation to the repository without transforming the input', async () => {
    const { repository, service } = setup();
    repository.get.mockResolvedValue({ ok: false, error: { code: 'P4_INVALID_QUERY' } });
    const invalid = { id: 'not-a-uuid' };
    expect(await service.getEligibility(invalid)).toEqual({ ok: false, error: { code: 'P4_INVALID_QUERY' } });
    expect(repository.get).toHaveBeenCalledExactlyOnceWith(invalid);
  });

  it.each([new Error('private-driver-message'), 'private-url', null])('sanitizes unexpected thrown failures without retry', async error => {
    const { repository, service } = setup();
    repository.get.mockRejectedValue(error);
    expect(await service.getEligibility(receipt().id)).toEqual({ ok: false, error: { code: 'P4_STORAGE_FAILURE' } });
    expect(repository.get).toHaveBeenCalledTimes(1);
  });

  it('does not forward extra technical error details', async () => {
    const { repository, service } = setup();
    const failure = { ok: false as const, error: { code: 'P4_STORAGE_PERMISSION' as const, detail: 'private' } };
    repository.get.mockResolvedValue(failure);
    expect(await service.getEligibility(receipt().id)).toEqual({ ok: false, error: { code: 'P4_STORAGE_PERMISSION' } });
  });

  it('is deterministic and retains no mutable result between reads', async () => {
    const { repository, service } = setup();
    const record: RepositoryResult<PurchaseRecord> = { ok: true, value: receipt() };
    repository.get.mockResolvedValue(record);
    const first = await service.getEligibility(record.value.id);
    const second = await service.getEligibility(record.value.id);
    expect(first).toEqual(second);
    expect(first).not.toBe(second);
    if (!first.ok) throw new Error('Expected successful diagnostics');
    first.value.diagnostics.pop();
    expect(await service.getEligibility(record.value.id)).toEqual(second);
  });
});
