import { EventEmitter } from 'node:events';
import type { Request } from 'express';
import { Socket } from 'node:net';
import { PurchaseProxy } from './purchase-proxy.js';
import { PURCHASE_CATALOG } from '../purchases/purchase-catalog.js';

const transport = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('node:http', () => ({ request: transport.request }));
const key = '11111111-1111-4111-8111-111111111111';
const body = { contract: 'p4-purchase/1.0', origin: 'manual', idempotency_key: key, purchase: {
  supplier_id: 'sup-obra', product_id: 'prod-cimento', department_id: 'dep-obras', quantity: 3,
  unit_price: '0.10', currency: 'BRL', purchase_date: '2026-01-01', payment_days: 30,
} };
const catalog = { contract: 'p4-purchase/1.0', currency: 'BRL', catalog: PURCHASE_CATALOG };
function incoming(method = 'GET', path = '/demo/p4/catalog', data?: unknown) {
  return { method, originalUrl: path, socket: { remoteAddress: '127.0.0.1' },
    headers: { host: '127.0.0.1:3001', ...(method === 'POST' ? {
      'x-p4-local': 'p4-purchase/1.0', 'content-type': 'application/json',
    } : {}) }, body: data } as Request;
}
function setup() {
  const req = Object.assign(new EventEmitter(), { end: vi.fn(), destroy: vi.fn() });
  const res = Object.assign(new EventEmitter(), { statusCode: 200, headers: { 'content-type': 'application/json' }, destroy: vi.fn() });
  transport.request.mockReturnValue(req);
  const proxy = new PurchaseProxy();
  function respond(data: unknown = catalog, status = 200) {
    res.statusCode = status;
    transport.request.mock.calls.at(-1)![1](res);
    res.emit('data', Buffer.from(JSON.stringify(data))); res.emit('end');
  }
  return { proxy, req, res, respond };
}
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-11-18T15:00:00Z'));
  transport.request.mockReset();
  vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => { throw new Error('Network forbidden'); });
});
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

it('forwards only to fixed loopback without client credentials, origin, redirects or proxy environment', async () => {
  const s = setup(); const req = incoming();
  req.headers.origin = 'http://127.0.0.1:3001'; req.headers.cookie = 'secret'; req.headers.authorization = 'secret';
  const pending = s.proxy.forward(req); s.respond();
  expect(await pending).toEqual({ status: 200, body: catalog });
  const options = transport.request.mock.calls[0][0];
  expect(options).toMatchObject({ hostname: '127.0.0.1', port: 3002, method: 'GET', path: '/p4/catalog', agent: false });
  expect(JSON.stringify(options)).not.toMatch(/secret|origin|cookie|authorization/i);
  expect(s.req.end).toHaveBeenCalledOnce();
});

it.each([
  ['POST', '/demo/p4/catalog'], ['DELETE', '/demo/p4/purchases'], ['GET', '/demo/p4/unknown'],
  ['GET', '/demo/p4/purchases?url=http://evil'], ['GET', '/demo/p4/purchases?limit=2&limit=3'],
  ['GET', '/demo/p4/purchases?after_id=' + key], ['GET', '/demo/p4/purchases?limit=101'],
  ['GET', '/demo/p4/purchases/by-key/not-a-uuid'], ['GET', '/demo/p4/catalog?x=1'],
])('rejects unauthorized route %s %s before network', async (method, path) => {
  const s = setup(); await expect(s.proxy.forward(incoming(method, path))).rejects.toThrow();
  expect(transport.request).not.toHaveBeenCalled();
});
it.each([
  ['host', 'evil:3001'], ['origin', 'http://localhost:3001'], ['origin', 'http://evil'],
  ['sec-fetch-site', 'cross-site'], ['x-forwarded-for', '127.0.0.1'], ['forwarded', 'for=127.0.0.1'],
])('rejects %s=%s', async (header, value) => {
  const s = setup(); const req = incoming(); req.headers[header] = value;
  await expect(s.proxy.forward(req)).rejects.toThrow(); expect(transport.request).not.toHaveBeenCalled();
});
it('rejects non-loopback callers and POSTs without the local header or valid contract', async () => {
  const s = setup(); const external = incoming(); Object.assign(external.socket, { remoteAddress: '10.0.0.1' });
  await expect(s.proxy.forward(external)).rejects.toThrow();
  const post = incoming('POST', '/demo/p4/purchases', body); delete post.headers['x-p4-local'];
  await expect(s.proxy.forward(post)).rejects.toThrow();
  await expect(s.proxy.forward(incoming('POST', '/demo/p4/purchases', { ...body, total: '1' }))).rejects.toThrow();
  expect(transport.request).not.toHaveBeenCalled();
});
it('preserves the exact POST and idempotency key, sanitizes conflict messages', async () => {
  const s = setup(); const pending = s.proxy.forward(incoming('POST', '/demo/p4/purchases', body));
  expect(s.req.end).toHaveBeenCalledWith(JSON.stringify(body));
  expect(transport.request.mock.calls[0][0].headers['X-P4-Local']).toBe('p4-purchase/1.0');
  s.respond({ contract: 'p4-purchase/1.0', error: { code: 'P4_IDEMPOTENCY_CONFLICT', message: 'password secret SQL' } }, 409);
  await expect(pending).rejects.toMatchObject({ status: 409 });
});
it.each([302, 500, 503])('does not redirect or retry HTTP %s and never relays raw errors', async status => {
  const s = setup(); const pending = s.proxy.forward(incoming()); s.respond({ message: 'secret SQL stack' }, status);
  await expect(pending).rejects.toMatchObject({ status: 503 }); expect(transport.request).toHaveBeenCalledOnce();
});
it('bounds wall time, closes the request, and does not retry uncertain writes', async () => {
  const s = setup(); const pending = s.proxy.forward(incoming('POST', '/demo/p4/purchases', body));
  const assertion = expect(pending).rejects.toMatchObject({ status: 503 });
  await vi.advanceTimersByTimeAsync(15_000); await assertion;
  expect(s.req.destroy).toHaveBeenCalledOnce(); expect(transport.request).toHaveBeenCalledOnce();
});
it.each(['error', 'aborted'])('sanitizes response %s and cleans resources', async event => {
  const s = setup(); const pending = s.proxy.forward(incoming()); transport.request.mock.calls[0][1](s.res);
  s.res.emit(event, new Error('credentials')); await expect(pending).rejects.toMatchObject({ status: 503 });
  expect(s.req.destroy).toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
});
it('rejects oversized/invalid responses and handles request failure', async () => {
  const s = setup(); const pending = s.proxy.forward(incoming()); transport.request.mock.calls[0][1](s.res);
  s.res.emit('data', Buffer.alloc(256 * 1024 + 1)); await expect(pending).rejects.toThrow();
  const next = s.proxy.forward(incoming()); s.req.emit('error', new Error('secret'));
  await expect(next).rejects.toThrow(); expect(vi.getTimerCount()).toBe(0);
});
it('shutdown cancels pending requests and forbids new work', async () => {
  const s = setup(); const pending = s.proxy.forward(incoming()); s.proxy.onModuleDestroy();
  await expect(pending).rejects.toThrow(); await expect(s.proxy.forward(incoming())).rejects.toThrow();
  expect(transport.request).toHaveBeenCalledOnce(); expect(vi.getTimerCount()).toBe(0);
});

it('bounds concurrent proxy requests without queuing or opening extra connections', async () => {
  const s = setup();
  const pending = Array.from({ length: 8 }, () => s.proxy.forward(incoming()));
  const assertions = pending.map(p => expect(p).rejects.toThrow());
  await expect(s.proxy.forward(incoming())).rejects.toThrow();
  expect(transport.request).toHaveBeenCalledTimes(8);
  s.proxy.onModuleDestroy(); await Promise.all(assertions);
  expect(vi.getTimerCount()).toBe(0);
});

it('sanitizes synchronous transport errors and invalid JSON without leaking messages', async () => {
  const s = setup(); transport.request.mockImplementationOnce(() => { throw new Error('postgres://secret'); });
  await expect(s.proxy.forward(incoming())).rejects.toMatchObject({ status: 503,
    response: { error: { code: 'P4_SERVICE_UNAVAILABLE' } } });
  const pending = s.proxy.forward(incoming()); transport.request.mock.calls.at(-1)![1](s.res);
  s.res.emit('data', Buffer.from('{not json')); s.res.emit('end');
  await expect(pending).rejects.toMatchObject({ status: 503, response: { error: { code: 'P4_SERVICE_UNAVAILABLE' } } });
  expect(vi.getTimerCount()).toBe(0);
});
