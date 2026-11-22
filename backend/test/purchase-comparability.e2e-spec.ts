import { Test } from '@nestjs/testing';
import type { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { PrismaPg } from '@prisma/adapter-pg';
import { PurchaseModule } from '../src/purchases/purchase.module.js';
import { PurchaseRepository } from '../src/purchases/purchase-repository.js';
import { PRISMA_CLIENT } from '../src/prisma/prisma-client.provider.js';
import { configurePurchaseHttp } from '../src/purchases/purchase-http.js';
import { comparabilityFixture } from './purchase-comparability.fixture.js';

vi.mock('@prisma/adapter-pg', () => ({ PrismaPg: vi.fn(function () { throw new Error('Real PostgreSQL forbidden'); }) }));
vi.mock('../src/purchases/statistics/price-analysis.js', () => { throw new Error('Statistics forbidden'); });
vi.mock('node:child_process', () => { throw new Error('Scientific execution forbidden'); });
let app: NestExpressApplication;
let f: ReturnType<typeof comparabilityFixture>;
let path: string;
beforeEach(async () => {
  vi.clearAllMocks(); f = comparabilityFixture(); path = `/p4/purchases/${f.id}/comparability`;
  const module = await Test.createTestingModule({ imports: [PurchaseModule] })
    .overrideProvider(PRISMA_CLIENT).useValue(f.client)
    .overrideProvider(PurchaseRepository).useValue(f.purchases).compile();
  app = module.createNestApplication<NestExpressApplication>({ logger: false, bodyParser: false });
  configurePurchaseHttp(app); await app.init();
});
afterEach(async () => {
  await app?.close(); expect(PrismaPg).not.toHaveBeenCalled();
  expect(f.client.$connect).toHaveBeenCalledOnce(); expect(f.client.$disconnect).toHaveBeenCalledOnce();
});
const get = (url: string) => request(app.getHttpServer()).get(url).set('Host', '127.0.0.1:3002');
const post = () => request(app.getHttpServer()).post(`${path}/revisions`)
  .set('Host', '127.0.0.1:3002').set('X-P4-Local', 'p4-purchase/1.0');

it('uses real module/services/repository with a mocked SQL boundary for 201/200/409 and reads', async () => {
  const initial = await get(path).expect(200);
  expect(initial.body.metadata_status).toBe('absent');
  expect(initial.body.receipt_eligibility.evidence.content_sha256).toBe(f.receipt.content_sha256);
  const created = await post().send(f.body).expect(201);
  expect(created.body.outcome).toBe('created');
  const replay = await post().send(f.body).expect(200);
  expect(replay.body.revision).toEqual(created.body.revision);
  f.body.metadata.attributes.currency.provenance.actor_id = 'different';
  await post().send(f.body).expect(409);
  const current = await get(`${path}/revisions/current`).expect(200);
  expect(current.body.revision).toEqual(created.body.revision);
  expect((await get(`${path}/revisions/1`).expect(200)).body).toEqual(current.body);
  expect((await get(`${path}/revisions/2`).expect(200)).body.outcome).toBe('absent');
  const status = await get(path).expect(200);
  expect(status.body.current.validation.diagnostics.length).toBe(8);
  expect(status.body.receipt_eligibility.status).toBe('unavailable');
  expect(status.headers['cache-control']).toBe('no-store');
});
it.each([{}, [], { metadata: {}, definitions: {}, verified: true }])('rejects malformed DTO %#', async body => {
  await post().send(body).expect(400); expect(f.query).not.toHaveBeenCalled();
});
it.each(['version_id', 'content_sha256'] as const)('rejects invalid receipt %s before writing', async key => {
  f.body.metadata.purchase[key] = 'invalid';
  await post().send(f.body).expect(400); expect(f.query).not.toHaveBeenCalled();
});
it('rejects external verification', async () => {
  f.body.metadata.attributes.currency.provenance.kind = 'verified';
  await post().send(f.body).expect(400); expect(f.query).not.toHaveBeenCalled();
});
it('distinguishes missing purchases from missing revisions', async () => {
  f.purchases.get.mockResolvedValue({ ok: false, error: { code: 'P4_NOT_FOUND' } });
  await get(path).expect(404); await get(`${path}/revisions/current`).expect(404);
  await post().send(f.body).expect(404);
});
it.each([['42501', 503], ['23514', 500], ['23505', 409], ['55P03', 503]])('sanitizes storage failure %s', async (code, status) => {
  f.fail({ code, message: 'postgresql://SECRET' });
  const response = await post().send(f.body).expect(status as number);
  expect(JSON.stringify(response.body)).not.toContain('SECRET');
});
it('sanitizes unexpected exceptions', async () => {
  f.purchases.get.mockRejectedValue(new Error('private-stack'));
  const response = await get(path).expect(503);
  expect(JSON.stringify(response.body)).not.toContain('private-stack');
});
it('retains Host/Origin/header/body bounds and disallows mutation methods', async () => {
  await post().set('Host', 'external.test').send(f.body).expect(403);
  await post().set('Origin', 'http://external.test').send(f.body).expect(403);
  await post().unset('X-P4-Local').send(f.body).expect(403);
  await post().set('X-Forwarded-For', '127.0.0.1').send(f.body).expect(403);
  await post().send({ extra: 'x'.repeat(5000) }).expect(413);
  await request(app.getHttpServer()).delete(`${path}/revisions/1`).set('Host', '127.0.0.1:3002').expect(404);
  expect(f.query).not.toHaveBeenCalled();
});
it.each(['/revisions/0', '/revisions/2147483648', '?unknown=x', '/revisions/current?unknown=x'])('rejects invalid route/query %s', async suffix => {
  await get(`${path}${suffix}`).expect(400); expect(f.query).not.toHaveBeenCalled();
});
