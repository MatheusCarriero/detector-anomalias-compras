import { Test } from '@nestjs/testing';
import type { NestExpressApplication } from '@nestjs/platform-express';
import { EventEmitter } from 'node:events';
import { runInNewContext } from 'node:vm';
import request from 'supertest';
import { DemoModule } from '../src/demo/demo.module.js';
import { configurePurchaseProxyErrors } from '../src/demo/purchase-proxy.controller.js';
import { PURCHASE_CATALOG } from '../src/purchases/purchase-catalog.js';

const upstream = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('node:http', async importOriginal => ({ ...await importOriginal<typeof import('node:http')>(), request: upstream.request }));
vi.mock('@prisma/adapter-pg', () => { throw new Error('Database import forbidden'); });
vi.mock('pg', () => { throw new Error('Database import forbidden'); });
vi.mock('node:child_process', () => ({
  execFile: () => { throw new Error('Python execution forbidden'); },
  spawn: () => { throw new Error('Python execution forbidden'); },
}));

const key = '11111111-1111-4111-8111-111111111111';
const id = '22222222-2222-4222-8222-222222222222';
const payload = { contract: 'p4-purchase/1.0', origin: 'manual', idempotency_key: key, purchase: {
  supplier_id: 'sup-obra', product_id: 'prod-cimento', department_id: 'dep-obras', quantity: 3,
  unit_price: '0.10', currency: 'BRL', purchase_date: '2026-01-01', payment_days: 30,
} };
const receipt = { id, idempotency_key: key, recorded_at: '2026-11-18T15:00:00.000Z', revision_no: 1,
  purchase: { supplier: PURCHASE_CATALOG.suppliers[0], product: PURCHASE_CATALOG.products[0], department: PURCHASE_CATALOG.departments[0],
    quantity: 3, unit_price: '0.10', total: '0.30', currency: 'BRL', purchase_date: '2026-01-01', payment_days: 30 },
  analysis: { status: 'unavailable', reason: 'manual_source_incompatible_with_procurement_v2' } };

describe('P4 same-origin proxy and page (offline HTTP; upstream API simulated)', () => {
  let app: NestExpressApplication;
  let reply: { status: number; body: unknown };
  const calls: { path: string; body: string | undefined }[] = [];
  beforeEach(async () => {
    calls.length = 0; upstream.request.mockReset();
    reply = { status: 200, body: { contract: 'p4-purchase/1.0', currency: 'BRL', catalog: PURCHASE_CATALOG } };
    upstream.request.mockImplementation((options: { hostname: string; port: number; path: string }, callback: (res: unknown) => void) => {
      expect(options.hostname).toBe('127.0.0.1'); expect(options.port).toBe(3002);
      const req = Object.assign(new EventEmitter(), { destroy: vi.fn(), end: (body?: string) => {
        calls.push({ path: options.path, body });
        queueMicrotask(() => {
          const res = Object.assign(new EventEmitter(), { statusCode: reply.status, headers: { 'content-type': 'application/json' }, destroy: vi.fn() });
          callback(res); res.emit('data', Buffer.from(JSON.stringify(reply.body))); res.emit('end');
        });
      } });
      return req;
    });
    const fixture = await Test.createTestingModule({ imports: [DemoModule] }).compile();
    app = fixture.createNestApplication<NestExpressApplication>({ logger: false });
    app.useBodyParser('json', { limit: '1kb', inflate: false });
    configurePurchaseProxyErrors(app);
    await app.init();
  });
  afterEach(async () => { await app?.close(); });
  const local = { Host: '127.0.0.1:3001', Origin: 'http://127.0.0.1:3001', 'X-P4-Local': 'p4-purchase/1.0' };
  const get = (path: string) => request(app.getHttpServer()).get(path).set(local);
  const post = (data: object = payload) => request(app.getHttpServer()).post('/demo/p4/purchases').set(local).send(data);

  it('serves Invoice/P4 and V2 pages without database imports, Python or API writes', async () => {
    const page = await get('/').expect(200);
    for (const element of ['purchase-form', 'purchase-save', 'purchase-check', 'purchase-history-rows', 'run-button']) expect(page.text).toContain(`id="${element}"`);
    expect(page.headers['content-security-policy']).toContain("connect-src 'self'");
    await get('/demo/procurement-v2').expect(200);
    await get('/demo/assets/purchase.js').expect(200);
    expect(upstream.request).not.toHaveBeenCalled();
  });
  it('runs the actual form JavaScript through HTTP and the proxy with a simulated API', async () => {
    class Element {
      value = ''; hidden = false; disabled = false; private text = ''; children: Element[] = [];
      listeners = new Map<string, (event: { preventDefault(): void }) => unknown>();
      get textContent(): string { return this.text + this.children.map(e => e.textContent).join(' '); }
      set textContent(v: string) { this.text = v; this.children = []; }
      set innerHTML(_v: string) { throw new Error('Unsafe HTML'); }
      setAttribute() {} removeAttribute() {} focus() {}
      addEventListener(name: string, fn: (event: { preventDefault(): void }) => unknown) { this.listeners.set(name, fn); }
      replaceChildren(...nodes: Element[]) { this.text = ''; this.children = nodes; }
      appendChild(node: Element) { this.children.push(node); }
      async emit(name: string) { await this.listeners.get(name)?.({ preventDefault() {} }); }
    }
    const page = await get('/').expect(200);
    const script = await get('/demo/assets/purchase.js').expect(200);
    const elements = Object.fromEntries([...page.text.matchAll(/id="([^"]+)"/g)].map(m => [m[1], new Element()]));
    const storage = new Map<string, string>();
    const fetch = vi.fn(async (url: string, options: { method: string; body?: string; headers: Record<string, string> }) => {
      const r = options.method === 'POST'
        ? await request(app.getHttpServer()).post(url).set(local).set(options.headers).send(options.body!)
        : await get(url);
      return { status: r.status, ok: r.status >= 200 && r.status < 300, json: async () => r.body as unknown };
    });
    runInNewContext(script.text, { document: { getElementById: (name: string) => elements[name], createElement: () => new Element() },
      fetch, Date, Intl, URLSearchParams, AbortController, setTimeout, clearTimeout,
      crypto: { randomUUID: () => key }, sessionStorage: { getItem: (k: string) => storage.get(k) ?? null,
        setItem: (k: string, v: string) => storage.set(k, v), removeItem: (k: string) => storage.delete(k) } });
    await vi.waitFor(() => expect(elements['purchase-prepare'].disabled).toBe(false));
    expect(fetch).toHaveBeenCalledOnce();
    for (const [field, value] of Object.entries({ supplier: 'sup-obra', product: 'prod-cimento', department: 'dep-obras',
      quantity: '3', 'unit-price': '0,10', date: '2026-01-01', 'payment-days': '30' })) elements[`purchase-${field}`].value = value;
    await elements['purchase-form'].emit('submit');
    reply = { status: 201, body: { contract: payload.contract, outcome: 'created', purchase: receipt } };
    await elements['purchase-save'].emit('click');
    expect(elements['purchase-receipt'].textContent).toContain(id);
    expect(elements['purchase-receipt'].textContent).toContain('0,30');
    reply = { status: 200, body: { contract: payload.contract, items: [receipt], next_cursor: null } };
    await elements['purchase-history-load'].emit('click');
    expect(elements['purchase-history-rows'].children).toHaveLength(1);
    expect(elements['purchase-history-rows'].textContent).toContain(id);
    expect(calls.filter(c => c.body !== undefined)).toHaveLength(1); // Simulated POST only.
  });
  it('forwards catalog without enabling CORS or relaying cookies', async () => {
    const r = await get('/demo/p4/catalog').set('Cookie', 'private=secret').expect(200);
    expect(r.body.catalog).toEqual(PURCHASE_CATALOG);
    expect(r.headers['access-control-allow-origin']).toBeUndefined();
    expect(r.headers['cache-control']).toBe('no-store');
    expect(upstream.request.mock.calls[0][0].headers).toEqual({ Accept: 'application/json' });
  });
  it('preserves 201, 200 replay, 409 conflict and 200 lookup with no retries', async () => {
    reply = { status: 201, body: { contract: payload.contract, outcome: 'created', purchase: receipt } };
    const created = await post().expect(201); expect(created.body.purchase.purchase.total).toBe('0.30');
    reply = { status: 200, body: { contract: payload.contract, outcome: 'replay', purchase: receipt } };
    await post().expect(200);
    expect(calls[0].body).toBe(calls[1].body);
    reply = { status: 409, body: { contract: payload.contract, error: { code: 'P4_IDEMPOTENCY_CONFLICT', message: 'secret SQL' } } };
    const conflict = await post({ ...payload, purchase: { ...payload.purchase, quantity: 4 } }).expect(409);
    expect(conflict.text).not.toContain('secret');
    reply = { status: 200, body: { contract: payload.contract, purchase: receipt } };
    const read = await get(`/demo/p4/purchases/by-key/${key}`).expect(200);
    expect(read.body.purchase).toEqual(created.body.purchase); expect(calls).toHaveLength(4);
  });
  it('forwards only bounded pagination, and allows receipt by ID', async () => {
    reply = { status: 200, body: { contract: payload.contract, items: [receipt], next_cursor: null } };
    const r = await get('/demo/p4/purchases?limit=20&after_recorded_at=2026-11-18T15%3A00%3A00.000Z&after_id=' + id).expect(200);
    expect(r.body.items[0].id).toBe(id);
    expect(calls[0].path).toContain('after_recorded_at=2026-11-18T15%3A00%3A00.000Z');
    reply = { status: 200, body: { contract: payload.contract, purchase: receipt } };
    await get(`/demo/p4/purchases/${id}`).expect(200);
  });
  it.each([
    ['Origin', 'http://evil'], ['Host', 'localhost:3001'], ['Sec-Fetch-Site', 'cross-site'], ['X-Forwarded-Host', 'evil'],
  ])('rejects unsafe %s before any upstream request', async (header, value) => {
    await get('/demo/p4/catalog').set(header, value).expect(403); expect(calls).toHaveLength(0);
  });
  it('requires JSON and local write header; refuses preflight and alternate methods', async () => {
    await request(app.getHttpServer()).post('/demo/p4/purchases').set('Host', local.Host).send(payload).expect(403);
    await request(app.getHttpServer()).post('/demo/p4/purchases').set(local).type('form').send('a=1').expect(415);
    await request(app.getHttpServer()).options('/demo/p4/purchases').set(local).expect(405);
    await request(app.getHttpServer()).delete('/demo/p4/purchases').set(local).expect(405);
    expect(calls).toHaveLength(0);
  });
  it('rejects invalid input, pagination and arbitrary upstream targets', async () => {
    await post({ ...payload, purchase: { ...payload.purchase, currency: 'USD' } }).expect(400);
    await get('/demo/p4/purchases?limit=1&limit=2').expect(400);
    await get('/demo/p4/catalog?url=http://evil').expect(400);
    await get('/demo/p4/arbitrary').expect(404);
    expect(calls).toHaveLength(0);
  });
  it('bounds parser input and sanitizes unavailable upstream', async () => {
    const large = await post({ ...payload, data: 'x'.repeat(1500) }).expect(413);
    expect(large.body.error.code).toBe('P4_PAYLOAD_TOO_LARGE');
    expect(large.body.error.message).toContain('1 KiB');
    reply = { status: 500, body: { message: 'secret SQL' } };
    const r = await get('/demo/p4/catalog').expect(503);
    expect(r.text).not.toContain('secret'); expect(calls).toHaveLength(1);
  });
  it('sanitizes malformed JSON before controller dispatch without forwarding it', async () => {
    const r = await request(app.getHttpServer()).post('/demo/p4/purchases').set(local)
      .type('json').send('{"x":secret}').expect(400);
    expect(r.text).not.toContain('secret');
    expect(r.body.error.code).toBe('P4_INVALID_REQUEST');
    expect(r.headers['cache-control']).toBe('no-store');
    expect(calls).toHaveLength(0);
  });
  it.each(['/demo/invoice-runs', '/demo/procurement-v2/prepare'])('does not install P4 parser responses on %s', async path => {
    const r = await request(app.getHttpServer()).post(path).type('json').send('{').expect(400);
    expect(r.body.contract).toBeUndefined(); expect(calls).toHaveLength(0);
  });
  it.each(['total', 'key', 'analysis', 'catalog'])('refuses a corrupt receipt (%s) rather than confirming a purchase', async kind => {
    const changed = structuredClone(receipt);
    if (kind === 'total') changed.purchase.total = '0.31';
    if (kind === 'key') changed.idempotency_key = id;
    if (kind === 'analysis') changed.analysis.status = 'scored';
    if (kind === 'catalog') Object.assign(changed.purchase.product, { name: 'other source' });
    reply = { status: 201, body: { contract: payload.contract, outcome: 'created', purchase: changed } };
    await post().expect(503);
  });
});
