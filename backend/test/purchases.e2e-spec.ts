import { Test } from '@nestjs/testing';
import type { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { PrismaPg } from '@prisma/adapter-pg';
import { Prisma } from '../generated/prisma/client.js';
import { PRISMA_CLIENT } from '../src/prisma/prisma-client.provider.js';
import { PurchaseModule } from '../src/purchases/purchase.module.js';
import { configurePurchaseHttp } from '../src/purchases/purchase-http.js';
import { PURCHASE_CATALOG } from '../src/purchases/purchase-catalog.js';
import { preparePurchase } from '../src/purchases/purchase-contract.js';

vi.mock('@prisma/adapter-pg', () => ({ PrismaPg: vi.fn(function () { throw new Error('Real PostgreSQL forbidden'); }) }));
vi.mock('node:child_process', () => { throw new Error('Scientific execution forbidden'); });
const key = '935af6ba-e660-40dc-a268-b13a158599cc';
const ids = { actor: '11111111-1111-4111-8111-111111111111', supplier: '22222222-2222-4222-8222-222222222222',
  department: '33333333-3333-4333-8333-333333333333', currency: '44444444-4444-4444-8444-444444444444',
  identity: '55555555-5555-4555-8555-555555555555', reference: '66666666-6666-4666-8666-666666666666',
  line: '77777777-7777-4777-8777-777777777777', version: '88888888-8888-4888-8888-888888888888' };
function input() { return { contract: 'p4-purchase/1.0', origin: 'manual', idempotency_key: key, purchase: {
  supplier_id: 'sup-obra', product_id: 'prod-cimento', department_id: 'dep-obras', quantity: 3,
  unit_price: '0.10', currency: 'BRL', purchase_date: '2026-11-03', payment_days: 30,
} }; }
function fixtureReceipt() {
  const prepared = preparePurchase(input(), new Date('2026-11-18T15:00:00Z'));
  if (!prepared.ok) throw new Error('Invalid fixture');
  return { id: ids.line, version_id: ids.version, revision_no: 1, recorded_at: '2026-11-18T15:00:00.000Z',
    source_reference_id: ids.reference, source_identity_id: null,
    source_namespace: 'p4-manual/1.0', source_entity_kind: 'purchase_order_line', source_id: key,
    reference_namespace: 'p4-manual/1.0', reference_kind: 'purchase_order_line',
    source_version: 'p4-purchase/1.0', source_record_key: key, content_hash: prepared.value.content_sha256,
    original_content: prepared.value.original_content, payload_schema: 1, state: prepared.value.state,
    currency_code: 'BRL', supplier_matches: true, department_matches: true };
}
const wrapped = (result: unknown) => [{ result }];
const envelope = (receipt: unknown) => wrapped({ contract: 'p4-storage/1.0', status: receipt ? 'found' : 'absent', receipt });

// SQL boundary double only. It does not certify real PostgreSQL transactions.
describe('P4 HTTP with real contracts/repository and mocked Prisma client', () => {
  let app: NestExpressApplication;
  let committed: boolean;
  let corrupt: boolean;
  let fail: { code?: string; message: string } | undefined;
  let queries: { sql: string; values: unknown[] }[];
  let connect: ReturnType<typeof vi.fn>;
  let disconnect: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    vi.clearAllMocks(); committed = false; corrupt = false; fail = undefined; queries = [];
    connect = vi.fn(); disconnect = vi.fn();
    const module = await Test.createTestingModule({ imports: [PurchaseModule] }).overrideProvider(PRISMA_CLIENT).useValue({
      $connect: connect, $disconnect: disconnect,
      $transaction: async (work: (tx: unknown) => Promise<unknown>) => {
        let pending = false;
        const execute = async (query: Prisma.Sql) => {
          const sql = query.sql.replace(/\s+/g, ' ').trim(); queries.push({ sql, values: query.values });
          if (fail) throw fail;
          const row = corrupt ? { ...fixtureReceipt(), revision_no: 2 } : fixtureReceipt();
          if (sql.startsWith('SET ')) return 0;
          if (sql.includes('p4_v1_receipt_by_key')) return envelope(committed && query.values[0] === key ? row : null);
          if (sql.includes('p4_v1_receipt_by_id')) return envelope((committed || pending) && query.values[0] === ids.line ? row : null);
          if (sql.includes('p4_v1_history')) return wrapped({ contract: 'p4-storage/1.0',
            items: committed && query.values[1] === null ? [row] : [],
            next_cursor: committed && query.values[1] === null && query.values[0] === 1 ? { recorded_at: row.recorded_at, id: ids.line } : null });
          if (sql.includes('p4_v1_context')) return wrapped({ contract: 'p4-storage/1.0', catalog_version: PURCHASE_CATALOG.version,
            actor: { id: ids.actor, issuer: 'p4-demo', subject: 'manual-purchase-service' }, currency: { id: ids.currency, code: 'BRL' },
            suppliers: [...PURCHASE_CATALOG.suppliers].sort((a, b) => a.id.localeCompare(b.id)).map((s, i) => ({ source_id: s.id, id: i === 2 ? ids.supplier : `22222222-2222-4222-8222-22222222222${i}` })),
            departments: [...PURCHASE_CATALOG.departments].sort((a, b) => a.id.localeCompare(b.id)).map((d, i) => ({ source_id: d.id, id: i === 2 ? ids.department : `33333333-3333-4333-8333-33333333333${i}` })) });
          if (sql.includes('register_source_identity')) return [{ id: ids.identity }];
          if (sql.includes('observe_source')) return [{ id: ids.reference }];
          if (sql.includes('write_purchase_order_line')) { pending = true; return [{ entity_id: ids.line, version_id: ids.version, revision_no: 1 }]; }
          if (sql.includes('resolve_source_identity')) return [{ resolved: 1 }];
          throw new Error('Unexpected fixture SQL');
        };
        const result = await work({ $queryRaw: execute, $executeRaw: execute });
        if (pending) committed = true;
        return result;
      },
    }).compile();
    app = module.createNestApplication<NestExpressApplication>({ logger: false, bodyParser: false });
    configurePurchaseHttp(app); await app.init();
  });
  afterEach(async () => {
    await app?.close(); expect(connect).toHaveBeenCalledOnce(); expect(disconnect).toHaveBeenCalledOnce();
    expect(PrismaPg).not.toHaveBeenCalled();
  });
  function get(path: string) { return request(app.getHttpServer()).get(path).set('Host', '127.0.0.1:3002'); }
  function post(path = '/p4/purchases') { return request(app.getHttpServer()).post(path).set('Host', '127.0.0.1:3002').set('X-P4-Local', 'p4-purchase/1.0'); }

  it('serves only the server catalog, with no SQL or technical user identity exposed', async () => {
    const response = await get('/p4/catalog').expect(200);
    expect(response.body).toEqual({ contract: 'p4-purchase/1.0', currency: 'BRL', catalog: PURCHASE_CATALOG });
    expect(response.headers['cache-control']).toBe('no-store'); expect(queries).toHaveLength(0);
    expect(response.text).not.toMatch(/manual-purchase-service|auth_subject/);
  });
  it('creates an exact BRL receipt then replays it and rejects conflicting content', async () => {
    const created = await post().send(input()).expect(201);
    expect(created.body).toMatchObject({ contract: 'p4-purchase/1.0', outcome: 'created', purchase: {
      id: ids.line, idempotency_key: key, recorded_at: '2026-11-18T15:00:00.000Z', revision_no: 1,
      purchase: { quantity: 3, unit_price: '0.10', total: '0.30', currency: 'BRL', purchase_date: '2026-11-03' },
      analysis: { status: 'unavailable', reason: 'manual_source_incompatible_with_procurement_v2' },
    } });
    expect(created.body.purchase).not.toHaveProperty('version_id'); expect(created.body.purchase).not.toHaveProperty('source_reference_id');
    const replay = await post().send(input()).expect(200);
    expect(replay.body.outcome).toBe('replay'); expect(replay.body.purchase).toEqual(created.body.purchase);
    await post().send({ ...input(), purchase: { ...input().purchase, quantity: 4 } }).expect(409);
    expect(queries.filter(q => q.sql.includes('app.write_purchase_order_line'))).toHaveLength(1);
  });
  it('reads by UUID/key and passes an exact bounded keyset cursor to the existing reader', async () => {
    committed = true;
    const byId = await get(`/p4/purchases/${ids.line}`).expect(200);
    const byKey = await get(`/p4/purchases/by-key/${key.toUpperCase()}`).expect(200);
    expect(byKey.body).toEqual(byId.body);
    const page = await get('/p4/purchases?limit=1').expect(200);
    expect(page.body.items).toEqual([byId.body.purchase]);
    const cursor = page.body.next_cursor;
    const next = await get('/p4/purchases').query({ limit: '1', after_recorded_at: cursor.recorded_at, after_id: cursor.id }).expect(200);
    expect(next.body.items).toEqual([]);
    expect(queries.at(-1)?.values).toEqual([1, cursor.recorded_at, cursor.id]);
    expect(queries.every(q => q.sql.startsWith('SET ') || q.sql.startsWith('SELECT app.p4_v1_'))).toBe(true);
  });
  it('distinguishes absent receipts, invalid IDs and empty history', async () => {
    await get(`/p4/purchases/${ids.line}`).expect(404);
    await get(`/p4/purchases/by-key/${key}`).expect(404);
    await get('/p4/purchases/not-a-uuid').expect(400);
    await get('/p4/purchases/by-key/not-a-uuid').expect(400);
    expect((await get('/p4/purchases').expect(200)).body).toEqual({ contract: 'p4-purchase/1.0', items: [], next_cursor: null });
  });
  it.each([
    {}, [], { ...input(), contract: 'wrong' }, { ...input(), origin: 'import' },
    { ...input(), actor: 'postgres' }, { ...input(), idempotency_key: 'invalid' },
    ...[
      { supplier_id: 'other' }, { department_id: 'other' }, { product_id: 'other' }, { quantity: 0 }, { quantity: 1.5 },
      { quantity: '3' }, { unit_price: 0.1 }, { unit_price: '0.001' }, { unit_price: '-1' }, { unit_price: 'Infinity' },
      { unit_price: '1000000.01' }, { currency: 'USD' }, { payment_days: -1 }, { payment_days: 3651 },
      { purchase_date: '2026-02-30' }, { purchase_date: '9999-12-31' }, { total: '0.30' }, { analysis: 'eligible' },
    ].map(purchase => ({ ...input(), purchase: { ...input().purchase, ...purchase } })),
  ])('refuses invalid manual input %# before any SQL', async body => {
    const response = await post().send(body).expect(400);
    expect(response.body.error.code).toBe('P4_INVALID_REQUEST');
    expect(queries).toHaveLength(0); expect(committed).toBe(false);
  });
  it.each([
    '?limit=0', '?limit=101', '?limit=01', '?limit=1.5', '?limit=', '?limit=1&limit=2', '?limit=1%0A',
    '?limit[gt]=1', '?unknown=1', '?after_id=x', '?after_recorded_at=2026-11-18',
    '?after_id=bad&after_recorded_at=bad', '?after_id=&after_recorded_at=',
  ])('rejects malformed history query %s before SQL', async query => {
    await get(`/p4/purchases${query}`).expect(400); expect(queries).toHaveLength(0);
  });
  it('refuses query fields outside history and bodies on GET', async () => {
    await get('/p4/catalog?limit=1').expect(400);
    await get(`/p4/purchases/${ids.line}?key=other`).expect(400);
    await get(`/p4/purchases/by-key/${key}?actor=other`).expect(400);
    await post('/p4/purchases?ignore=true').send(input()).expect(400);
    await get('/p4/catalog').send({}).expect(400);
    expect(queries).toHaveLength(0);
  });
  it.each([
    ['Host', 'evil.example:3002'], ['Host', '127.0.0.1:3000'], ['Host', 'localhost:3002'],
    ['Origin', 'https://evil.example'], ['Origin', 'null'], ['Origin', 'http://127.0.0.1:3001'],
    ['Sec-Fetch-Site', 'cross-site'], ['Sec-Fetch-Site', 'same-site'], ['X-Forwarded-For', '127.0.0.1'],
    ['X-Forwarded-Host', '127.0.0.1:3002'], ['Forwarded', 'for=127.0.0.1'], ['X-Real-IP', '127.0.0.1'],
  ])('blocks untrusted browser/proxy header %s = %s', async (header, value) => {
    const response = await post().set(header, value).send(input()).expect(403);
    expect(response.body.error.code).toBe('P4_LOCAL_ONLY'); expect(queries).toHaveLength(0);
  });
  it('requires the local write header, rejects preflight, and never enables CORS', async () => {
    await post().unset('X-P4-Local').send(input()).expect(403);
    const preflight = await request(app.getHttpServer()).options('/p4/purchases')
      .set('Host', '127.0.0.1:3002').set('Origin', 'https://evil.example')
      .set('Access-Control-Request-Method', 'POST').set('Access-Control-Request-Headers', 'x-p4-local,content-type');
    expect(preflight.status).not.toBe(200); expect(preflight.headers['access-control-allow-origin']).toBeUndefined();
    expect(queries).toHaveLength(0);
  });
  it('accepts same-origin JSON without treating the technical actor as a human identity', async () => {
    const result = await post().set('Origin', 'http://127.0.0.1:3002').set('Sec-Fetch-Site', 'same-origin').send(input()).expect(201);
    expect(result.text).not.toContain('manual-purchase-service');
    expect(result.body.purchase.analysis.explanation).toContain('BRL');
    expect(result.body.purchase.analysis).not.toHaveProperty('score');
  });
  it('sanitizes parser failures and rejects uploads, compression, unsupported media and missing body', async () => {
    const malformed = await post().set('Content-Type', 'application/json').send('{"private-sentinel":').expect(400);
    expect(malformed.text).not.toMatch(/private-sentinel|SyntaxError|stack/);
    await post().send({ value: 'x'.repeat(4096) }).expect(413);
    await post().set('Content-Type', 'text/plain').send('private-sentinel').expect(415);
    await post().attach('file', Buffer.from('fake'), 'untrusted.csv').expect(415);
    await post().set('Content-Encoding', 'gzip').send(input()).expect(415);
    await post().set('Content-Type', 'application/json').expect(400);
    expect(queries).toHaveLength(0);
  });
  it.each([
    ['42501', 503, 'P4_SERVICE_UNAVAILABLE'], ['23514', 500, 'P4_INTERNAL_ERROR'],
    ['55P03', 503, 'P4_SERVICE_BUSY'], ['42601', 503, 'P4_SERVICE_UNAVAILABLE'],
    ['25P02', 503, 'P4_SERVICE_UNAVAILABLE'], ['P2028', 503, 'P4_SERVICE_UNAVAILABLE'],
  ])('sanitizes storage failure %s to HTTP %s', async (code, status, httpCode) => {
    fail = { code, message: 'postgresql://private:secret/schema/path' };
    const response = await post().send(input()).expect(status);
    expect(response.body.error.code).toBe(httpCode);
    expect(response.text).not.toMatch(/postgresql|secret|schema|stack|P2028|42501/); expect(committed).toBe(false);
  });
  it('does not expose corrupt receipts or turn them into missing purchases', async () => {
    committed = true; corrupt = true;
    await get(`/p4/purchases/${ids.line}`).expect(500);
    await get(`/p4/purchases/by-key/${key}`).expect(500);
    await get('/p4/purchases').expect(500);
  });
  it('does not expose UI, ML inference, update, delete or arbitrary endpoints', async () => {
    for (const path of ['/', '/demo/invoice-runs', '/demo/procurement-v2/runs', '/p4/purchases/analyze']) {
      const result = await post(path).send(input()); expect(result.status).toBe(404);
      expect(result.text).not.toContain(`Cannot POST ${path}`);
    }
    await request(app.getHttpServer()).delete(`/p4/purchases/${ids.line}`).set('Host', '127.0.0.1:3002').expect(404);
    expect(queries).toHaveLength(0);
  });
});
