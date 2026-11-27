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
vi.mock('node:child_process', () => { throw new Error('Model execution forbidden'); });
let app: NestExpressApplication;
let f: ReturnType<typeof comparabilityFixture>;
const get = (path: string) => request(app.getHttpServer()).get(path).set('Host', '127.0.0.1:3002');
beforeEach(async () => {
  vi.clearAllMocks(); f = comparabilityFixture();
  const module = await Test.createTestingModule({ imports: [PurchaseModule] })
    .overrideProvider(PRISMA_CLIENT).useValue(f.client).overrideProvider(PurchaseRepository).useValue(f.purchases).compile();
  app = module.createNestApplication<NestExpressApplication>({ logger: false, bodyParser: false });
  configurePurchaseHttp(app); await app.init();
});
afterEach(async () => { await app.close(); expect(PrismaPg).not.toHaveBeenCalled(); });
it('serves a receipt-bound unavailable diagnosis using only read functions', async () => {
  const r = await get(`/p4/purchases/${f.id}/price-analysis`).expect(200);
  expect(r.body.contract).toBe('p4-price-review/1.0');
  expect(r.body.purchase.content_sha256).toBe(f.receipt.content_sha256);
  expect(r.body.history).toBe('not_assessed'); expect(r.body.status).toBe('unavailable');
  expect(r.body).not.toHaveProperty('median_unit_price');
  expect(r.headers['cache-control']).toBe('no-store');
  expect(f.query.mock.calls.every(([sql]) => sql.sql.startsWith('SET ') || sql.sql.includes('p4_cmp_read'))).toBe(true);
});
it('demonstrates canonical synthetic arithmetic without any receipt or SQL query', async () => {
  const r = await get('/p4/price-analysis/simulation').expect(200);
  expect(r.body).toMatchObject({ mode: 'simulation', unit_price: '60.00', median_unit_price: '50.000', percent_difference: '20.000000', references: 30 });
  expect(r.body).not.toHaveProperty('purchase'); expect(f.query).not.toHaveBeenCalled(); expect(f.purchases.get).not.toHaveBeenCalled();
});
it.each([['P4_NOT_FOUND', 404], ['P4_STORAGE_PERMISSION', 503], ['P4_STORAGE_INTEGRITY', 500]] as const)('preserves technical HTTP errors %s', async (code, status) => {
  f.purchases.get.mockResolvedValue({ ok: false, error: { code } });
  const r = await get(`/p4/purchases/${f.id}/price-analysis`).expect(status);
  expect(r.body).not.toHaveProperty('status'); expect(r.body.error).toBeDefined();
});
it('sanitizes thrown exceptions and forbids query parameters, body and foreign origin', async () => {
  const path = `/p4/purchases/${f.id}/price-analysis`;
  await get(path + '?verified=true').expect(400);
  await get('/p4/price-analysis/simulation?price=100').expect(400);
  await get(path).set('Origin', 'https://external.test').expect(403);
  await get(path).send({ verified: true }).expect(400);
  await get('/p4/purchases/not-uuid/price-analysis').expect(400);
  expect(f.query).not.toHaveBeenCalled();
  f.purchases.get.mockRejectedValue(new Error('postgresql://SECRET'));
  const r = await get(path).expect(503); expect(r.text).not.toContain('SECRET');
});
it('exposes no POST for review or simulation', async () => {
  for (const path of [`/p4/purchases/${f.id}/price-analysis`, '/p4/price-analysis/simulation']) {
    await request(app.getHttpServer()).post(path).set('Host', '127.0.0.1:3002').set('X-P4-Local', 'p4-purchase/1.0').send({}).expect(404);
  }
  expect(f.query).not.toHaveBeenCalled();
});

it('accepts only a price for hypothetical GET, never writing or looking up receipts', async()=>{
 const r=await get('/p4/price-analysis/hypothetical?unit_price=25.00').expect(200);
 expect(r.body).toMatchObject({contract:'p4-hypothetical-price/1.0',result:{unit_price:'25.00',percent_difference:'-50.000000'}});
 for(const query of ['', '?unit_price=0.00','?unit_price=25.00&unit_price=60.00','?unit_price=25.00&product=prod-cimento','?unit_price=1000000.01']) await get('/p4/price-analysis/hypothetical'+query).expect(400);
 await get('/p4/price-analysis/hypothetical?unit_price=25.00').set('Origin','https://evil.test').expect(403);
 await request(app.getHttpServer()).post('/p4/price-analysis/hypothetical').set('Host','127.0.0.1:3002').send({unit_price:'25.00'}).expect(404);
 expect(f.query).not.toHaveBeenCalled();expect(f.purchases.get).not.toHaveBeenCalled();
});
