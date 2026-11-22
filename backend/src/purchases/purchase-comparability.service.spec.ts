import { Socket } from 'node:net';
import { comparabilityFixture } from '../../test/purchase-comparability.fixture.js';
import { PurchaseComparabilityService } from './purchase-comparability.service.js';
import { PurchaseComparabilityRepository } from './purchase-comparability.repository.js';
import { PurchaseStatisticsService } from './purchase-statistics.service.js';
import { PrismaService } from '../prisma/prisma.service.js';

vi.mock('@prisma/adapter-pg', () => ({ PrismaPg: class { constructor() { throw new Error('Real database forbidden'); } } }));
vi.mock('./statistics/price-analysis.js', () => { throw new Error('Statistics forbidden'); });
let f: ReturnType<typeof comparabilityFixture>;
let service: PurchaseComparabilityService;
let networkAttempts = 0;
beforeEach(() => {
  networkAttempts = 0;
  vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => { networkAttempts++; throw new Error('Network forbidden'); });
  f = comparabilityFixture();
  const prisma = new PrismaService(f.client);
  service = new PurchaseComparabilityService(new PurchaseComparabilityRepository(prisma, f.purchases), new PurchaseStatisticsService(f.purchases));
});
afterEach(() => { expect(networkAttempts).toBe(0); vi.restoreAllMocks(); });

it('exposes receipt evidence and missing metadata without evaluating statistics', async () => {
  const result = await service.status(f.id);
  expect(result.metadata_status).toBe('absent');
  expect(result.receipt_eligibility.evidence.version_id).toBe(f.receipt.version_id);
  expect(result.receipt_eligibility.status).toBe('unavailable');
  expect(result.receipt_eligibility.recorded.total).toBe('0.30');
});
it('creates, replays and retrieves a revision with real validators and unchanged input', async () => {
  const before = structuredClone(f.body);
  expect((await service.create(f.id, f.body)).outcome).toBe('created');
  expect((await service.create(f.id, f.body)).outcome).toBe('replay');
  const current = await service.revision(f.id, 'current');
  expect(current).toEqual(await service.revision(f.id, '1'));
  expect(current.revision?.validation.status).toBe('incomplete');
  expect(current.revision?.validation.diagnostics).toContainEqual({ category: 'unverified', code: 'verification_required', field: 'currency' });
  expect((await service.status(f.id)).receipt_eligibility.status).toBe('unavailable');
  expect((await service.revision(f.id, '2')).outcome).toBe('absent');
  expect(f.body).toEqual(before);
});
it.each([null, [], {}, { metadata: {}, definitions: {}, verifications: [] }])('refuses malformed HTTP envelope %#', async body => {
  await expect(service.create(f.id, body)).rejects.toMatchObject({ status: 400 });
  expect(f.query).not.toHaveBeenCalled();
});
it.each(['bad', '', '77777777-7777-4777-8777-777777777777\n'])('refuses invalid route UUID %s', async id => {
  await expect(service.status(id)).rejects.toMatchObject({ status: 400 });
});
it.each(['0', '-1', '01', '1.5', '2147483648', '1e2', '1\n'])('refuses invalid revision %s', async revision => {
  await expect(service.revision(f.id, revision)).rejects.toMatchObject({ status: 400 });
});
it.each(['version_id', 'content_sha256', 'id'] as const)('rejects mismatched receipt %s', async field => {
  f.body.metadata.purchase[field] = field === 'content_sha256' ? '0'.repeat(64) : 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  await expect(service.create(f.id, f.body)).rejects.toMatchObject({ status: 400 });
  expect(f.query).not.toHaveBeenCalled();
});
it('rejects self-verification and unsupported versions without SQL', async () => {
  f.body.metadata.attributes.currency.provenance.kind = 'verified';
  await expect(service.create(f.id, f.body)).rejects.toMatchObject({ status: 400 });
  f.body.metadata.contract = 'unsupported';
  await expect(service.create(f.id, f.body)).rejects.toMatchObject({ status: 400 });
  expect(f.query).not.toHaveBeenCalled();
});
it('returns a conflict without replacing the original revision', async () => {
  await service.create(f.id, f.body);
  f.body.metadata.attributes.currency.provenance.actor_id = 'changed';
  await expect(service.create(f.id, f.body)).rejects.toMatchObject({ status: 409 });
  expect((await service.revision(f.id, '1')).revision?.validation.content.attributes.currency?.provenance.actor_id).toBe('fixture');
});
it.each([['42501', 503], ['23514', 500], ['23503', 500], ['55P03', 503], ['unknown', 503]])('sanitizes SQL failure %s', async (code, status) => {
  f.fail({ code, message: 'private-database-secret' });
  await expect(service.create(f.id, f.body)).rejects.toMatchObject({ status });
});
it('keeps missing purchases and storage failures distinct from unavailability', async () => {
  f.purchases.get.mockResolvedValue({ ok: false, error: { code: 'P4_NOT_FOUND' } });
  await expect(service.status(f.id)).rejects.toMatchObject({ status: 404 });
  f.purchases.get.mockRejectedValue(new Error('private'));
  await expect(service.status(f.id)).rejects.toMatchObject({ status: 503 });
});
