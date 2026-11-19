import { Socket } from 'node:net';
import type { ArgumentsHost } from '@nestjs/common';
import type { Request } from 'express';
import { checkLocalPurchaseRequest, PurchaseHttpError, PurchaseHttpFilter, purchaseValue } from './purchase-http.js';
import type { RepositoryResult } from './purchase-repository.js';

function req(headers: Request['headers'] = {}, address: string | undefined = '127.0.0.1', method = 'POST') {
  return { socket: { remoteAddress: address }, method, headers: {
    host: '127.0.0.1:3002', 'x-p4-local': 'p4-purchase/1.0', 'content-type': 'application/json', ...headers,
  } } as unknown as Request;
}
let attempts = 0;
beforeEach(() => {
  attempts = 0;
  vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => { attempts++; throw new Error('Offline network guard'); });
});
afterEach(() => { expect(attempts).toBe(0); vi.restoreAllMocks(); });
it.each(['127.0.0.1', '::1', '::ffff:127.0.0.1'])('accepts only a direct loopback peer: %s', address => {
  expect(() => checkLocalPurchaseRequest(req({}, address))).not.toThrow();
});
it.each(['10.0.0.1', '127.0.0.2', '::ffff:192.168.0.1', 'example.test', ''])('refuses peer %s despite a valid Host or spoofed request IP', address => {
  const request = Object.assign(req({}, address), { ip: '127.0.0.1' });
  expect(() => checkLocalPurchaseRequest(request)).toThrow(PurchaseHttpError);
});
it('refuses a missing peer instead of trusting headers', () => {
  const request = req(); delete (request.socket as { remoteAddress?: string }).remoteAddress;
  expect(() => checkLocalPurchaseRequest(request)).toThrow(PurchaseHttpError);
});
it.each(['HEAD', 'PUT', 'DELETE', 'OPTIONS', 'PATCH'])('does not permit method %s on the controller', method => {
  expect(() => checkLocalPurchaseRequest(req({}, '127.0.0.1', method))).toThrow(PurchaseHttpError);
});
it.each([
  { host: '127.0.0.1:3002.evil' }, { origin: ['http://127.0.0.1:3002', 'https://evil'] },
  { 'x-p4-local': ['p4-purchase/1.0', 'extra'] }, { 'content-type': 'application/json; charset=latin1' },
  { 'content-type': 'application/json; extra=x' }, { 'content-encoding': 'identity' },
  { 'forwarded': '' }, { 'x-forwarded-proto': 'http' },
])('refuses ambiguous headers %#', headers => {
  expect(() => checkLocalPurchaseRequest(req(headers as Request['headers']))).toThrow(PurchaseHttpError);
});
it('maps only known public storage/validation categories, without raw SQL information', () => {
  const cases = [
    ['P4_INVALID_QUANTITY', 400], ['P4_INVALID_CURRENCY', 400], ['P4_INVALID_QUERY', 400],
    ['P4_IDEMPOTENCY_CONFLICT', 409], ['P4_NOT_FOUND', 404], ['P4_REFERENCE_UNAVAILABLE', 503],
    ['P4_STORAGE_PERMISSION', 503], ['P4_STORAGE_BUSY', 503], ['P4_STORAGE_FAILURE', 503],
    ['P4_STORAGE_INTEGRITY', 500], ['P4_INVALID_CLOCK', 500], ['P4_INVALID_IDEMPOTENCY_RECORD', 500], ['P4_VALIDATION_FAILED', 500],
  ] as const;
  for (const [code, status] of cases) {
    let failure: unknown;
    try { purchaseValue({ ok: false, error: { code } }); } catch (error) { failure = error; }
    expect(failure).toBeInstanceOf(PurchaseHttpError);
    expect((failure as PurchaseHttpError).getStatus()).toBe(status);
  }
  expect(() => purchaseValue({ ok: false, error: { code: 'postgresql://private' } } as unknown as RepositoryResult<never>)).toThrow(PurchaseHttpError);
});
it('sanitizes unexpected exceptions and parser errors without logging their messages or bodies', () => {
  const json = vi.fn(); const response = { status: vi.fn().mockReturnValue({ json }) };
  const host = { switchToHttp: () => ({ getResponse: () => response }) } as unknown as ArgumentsHost;
  for (const error of [new Error('postgresql://private'), Object.assign(new Error('secret JSON body'), { status: 400 }),
    Object.assign(new Error('secret JSON body'), { status: 413 }), Object.assign(new Error('secret JSON body'), { status: 415 })]) {
    new PurchaseHttpFilter().catch(error, host);
  }
  expect(response.status.mock.calls.map(([code]) => code)).toEqual([500, 400, 413, 415]);
  expect(JSON.stringify(json.mock.calls)).not.toMatch(/private|secret|stack|postgresql/);
});
