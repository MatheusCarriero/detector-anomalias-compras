import { readPriceReview, readHypotheticalPrice, validCandidatePrice } from '../purchases/purchase-price-review.contract.js';
import { Injectable } from '@nestjs/common';
import type { OnModuleDestroy } from '@nestjs/common';
import type { Request } from 'express';
import { request as httpRequest } from 'node:http';
import type { ClientRequest, IncomingMessage } from 'node:http';
import { PURCHASE_CONTRACT, preparePurchase } from '../purchases/purchase-contract.js';
import { PURCHASE_CATALOG } from '../purchases/purchase-catalog.js';
import { checkLocalPurchaseRequest, PurchaseHttpError } from '../purchases/purchase-http.js';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const key = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const unavailable = () => new PurchaseHttpError('P4_SERVICE_UNAVAILABLE');
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw unavailable();
  return value as Record<string, unknown>;
}
function matches(value: unknown, pattern: RegExp): value is string {
  return typeof value === 'string' && pattern.exec(value)?.[0] === value;
}
function timestamp(value: unknown): value is string {
  return matches(value, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/) &&
    Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value;
}

/** Explicit route allowlist; no request-supplied target, URL or forwarded headers. */
function route(request: Request) {
  if (request.headers.host !== '127.0.0.1:3001' ||
    (request.headers.origin !== undefined && request.headers.origin !== 'http://127.0.0.1:3001')) {
    throw new PurchaseHttpError('P4_LOCAL_ONLY');
  }
  // Reuse the API's peer/method/media/CSRF checks at the demo's own origin.
  // This synthetic view does not mutate Express or forward incoming credentials.
  checkLocalPurchaseRequest({ method: request.method, body: request.body, socket: request.socket,
    headers: { ...request.headers, host: '127.0.0.1:3002',
      ...(request.headers.origin === undefined ? {} : { origin: 'http://127.0.0.1:3002' }) },
  } as Request);
  const url = new URL(request.originalUrl, 'http://127.0.0.1:3001');
  const path = url.pathname;
  const invalid = () => new PurchaseHttpError('P4_INVALID_REQUEST');
  if (url.origin !== 'http://127.0.0.1:3001' || url.hash) throw invalid();
  if (request.method === 'POST') {
    if (path !== '/demo/p4/purchases' || url.search) throw invalid();
    if (!preparePurchase(request.body as unknown, new Date()).ok) throw invalid();
    const body = JSON.stringify(request.body);
    if (Buffer.byteLength(body) > 4096) throw new PurchaseHttpError('P4_PAYLOAD_TOO_LARGE');
    return { method: 'POST', path: '/p4/purchases', body };
  }
  if (path === '/demo/p4/purchases') {
    const query = url.searchParams;
    const keys = [...query.keys()];
    if (new Set(keys).size !== keys.length || keys.some(k => !['limit', 'after_recorded_at', 'after_id'].includes(k))) throw invalid();
    const limit = query.get('limit') ?? '20';
    if (!matches(limit, /^(?:[1-9][0-9]?|100)$/)) throw invalid();
    const after = query.get('after_recorded_at'); const id = query.get('after_id');
    if ((after === null) !== (id === null) || (after !== null && (!timestamp(after) || !matches(id, uuid)))) throw invalid();
    const params = new URLSearchParams({ limit });
    if (after !== null && id !== null) { params.set('after_recorded_at', after); params.set('after_id', id); }
    return { method: 'GET', path: `/p4/purchases?${params}` };
  }
  if (path === '/demo/p4/price-analysis/hypothetical') {
    const price = url.searchParams.get('unit_price');
    if ([...url.searchParams.keys()].join(',') !== 'unit_price' || !validCandidatePrice(price)) throw invalid();
    return { method: 'GET', path: `/p4/price-analysis/hypothetical?unit_price=${price}` };
  }
  if (url.search) throw invalid();
  if (path === '/demo/p4/price-analysis/simulation') return { method: 'GET', path: '/p4/price-analysis/simulation' };
  const review = /^\/demo\/p4\/purchases\/([^/]+)\/price-analysis$/.exec(path);
  if (review && matches(review[1], uuid)) return { method: 'GET', path: `/p4/purchases/${review[1]}/price-analysis` };
  if (path === '/demo/p4/catalog') return { method: 'GET', path: '/p4/catalog' };
  const byKey = /^\/demo\/p4\/purchases\/by-key\/([^/]+)$/.exec(path);
  const byId = /^\/demo\/p4\/purchases\/([^/]+)$/.exec(path);
  if (byKey && matches(byKey[1], key)) return { method: 'GET', path: `/p4/purchases/by-key/${byKey[1]}` };
  if (byId && matches(byId[1], uuid)) return { method: 'GET', path: `/p4/purchases/${byId[1]}` };
  throw invalid();
}

/** Whitelist public receipts; never relay internal/unknown fields from upstream. */
function receipt(value: unknown) {
  const r = object(value); const p = object(r.purchase); const analysis = object(r.analysis);
  if (!matches(r.id, uuid) || !matches(r.idempotency_key, key) || !timestamp(r.recorded_at) || r.revision_no !== 1 ||
    analysis.status !== 'unavailable' || analysis.reason !== 'manual_source_incompatible_with_procurement_v2') throw unavailable();
  const prepared = preparePurchase({ contract: PURCHASE_CONTRACT, origin: 'manual', idempotency_key: r.idempotency_key, purchase: {
    supplier_id: object(p.supplier).id, product_id: object(p.product).id, department_id: object(p.department).id,
    quantity: p.quantity, unit_price: p.unit_price, currency: p.currency, purchase_date: p.purchase_date, payment_days: p.payment_days,
  } }, new Date(r.recorded_at));
  if (!prepared.ok) throw unavailable();
  const expected = prepared.value.original_content.purchase;
  if (p.total !== expected.total || p.unit_price !== expected.unit_price ||
    object(p.supplier).name !== expected.supplier.name || object(p.product).name !== expected.product.name ||
    object(p.product).unit !== expected.product.unit || object(p.department).name !== expected.department.name) throw unavailable();
  return { id: r.id, idempotency_key: r.idempotency_key, recorded_at: r.recorded_at, revision_no: 1,
    purchase: expected, analysis: { status: 'unavailable', reason: 'manual_source_incompatible_with_procurement_v2',
      explanation: 'Compras manuais em BRL não possuem compatibilidade científica comprovada com a Procurement V2.' } };
}
function responseBody(value: unknown, status: number, target: ReturnType<typeof route>) {
  const data = object(value);
  if (status === 200 && target.method === 'GET' && target.path.startsWith('/p4/price-analysis/hypothetical?')) {
    const price = new URL(target.path, 'http://127.0.0.1').searchParams.get('unit_price')!;
    const result = readHypotheticalPrice(data, price);
    if (!result) throw unavailable();
    return result;
  }
  if (status === 200 && target.method === 'GET' && (target.path.endsWith('/price-analysis') || target.path === '/p4/price-analysis/simulation')) {
    const result = readPriceReview(data, target.path === '/p4/price-analysis/simulation' ? 'simulation' : target.path.split('/')[3]);
    if (!result) throw unavailable();
    return result;
  }
  if (data.contract !== PURCHASE_CONTRACT) throw unavailable();
  if (status !== 200 && status !== 201) {
    const code = object(data.error).code;
    for (const allowed of ['P4_INVALID_REQUEST', 'P4_LOCAL_ONLY', 'P4_NOT_FOUND', 'P4_IDEMPOTENCY_CONFLICT',
      'P4_PAYLOAD_TOO_LARGE', 'P4_UNSUPPORTED_MEDIA', 'P4_SERVICE_BUSY', 'P4_INTERNAL_ERROR'] as const) {
      const error = new PurchaseHttpError(allowed);
      if (code === allowed && status === error.getStatus()) throw error;
    }
    throw unavailable();
  }
  if (target.method === 'GET' && status !== 200) throw unavailable();
  if (target.path === '/p4/catalog') {
    if (data.currency !== 'BRL' || JSON.stringify(data.catalog) !== JSON.stringify(PURCHASE_CATALOG)) throw unavailable();
    return { contract: PURCHASE_CONTRACT, currency: 'BRL', catalog: PURCHASE_CATALOG };
  }
  if (target.path.startsWith('/p4/purchases?')) {
    const limit = Number(new URL(target.path, 'http://127.0.0.1').searchParams.get('limit'));
    if (!Array.isArray(data.items) || data.items.length > limit) throw unavailable();
    const items = data.items.map(receipt);
    if (new Set(items.map(r => r.id)).size !== items.length) throw unavailable();
    let next = null;
    if (data.next_cursor !== null) {
      const cursor = object(data.next_cursor); const last = items.at(-1);
      if (!last || cursor.id !== last.id || cursor.recorded_at !== last.recorded_at) throw unavailable();
      next = { id: last.id, recorded_at: last.recorded_at };
    }
    return { contract: PURCHASE_CONTRACT, items, next_cursor: next };
  }
  const purchase = receipt(data.purchase);
  if (target.method === 'POST') {
    if (data.outcome !== (status === 201 ? 'created' : 'replay')) throw unavailable();
    const sent = preparePurchase(JSON.parse(target.body!), new Date());
    if (!sent.ok || sent.value.source.source_id !== purchase.idempotency_key ||
      JSON.stringify(sent.value.original_content.purchase) !== JSON.stringify(purchase.purchase)) throw unavailable();
    return { contract: PURCHASE_CONTRACT, outcome: data.outcome, purchase };
  }
  const identifier = target.path.split('/').at(-1);
  if (target.path.includes('/by-key/') ? purchase.idempotency_key !== identifier : purchase.id !== identifier) throw unavailable();
  return { contract: PURCHASE_CONTRACT, purchase };
}

@Injectable()
export class PurchaseProxy implements OnModuleDestroy {
  private readonly pending = new Set<() => void>();
  private closed = false;

  async forward(incoming: Request): Promise<{ status: number; body: unknown }> {
    const target = route(incoming);
    if (this.closed || this.pending.size >= 8) throw unavailable();
    return new Promise((resolve, reject) => {
      let request: ClientRequest | undefined; let response: IncomingMessage | undefined;
      let finished = false;
      const finish = (error?: unknown, result?: { status: number; body: unknown }) => {
        if (finished) return;
        finished = true; clearTimeout(timer); this.pending.delete(cancel);
        if (error) { response?.destroy(); request?.destroy(); reject(error instanceof PurchaseHttpError ? error : unavailable()); }
        else resolve(result!);
      };
      const cancel = () => finish(unavailable());
      const timer = setTimeout(cancel, 15_000); // Total deadline, not an inactivity timeout.
      this.pending.add(cancel);
      try {
        request = httpRequest({ protocol: 'http:', hostname: '127.0.0.1', port: 3002, agent: false,
          method: target.method, path: target.path,
          headers: { Accept: 'application/json', ...(target.body === undefined ? {} : {
            'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(target.body), 'X-P4-Local': PURCHASE_CONTRACT,
          }) },
        }, res => {
          response = res;
          if (finished) { res.destroy(); return; }
          const chunks: Buffer[] = []; let size = 0;
          res.on('error', cancel); res.on('aborted', cancel);
          res.on('close', () => { if (!finished) cancel(); });
          res.on('data', (chunk: Buffer) => {
            if (finished) return;
            size += chunk.length;
            if (size > 256 * 1024) { cancel(); return; }
            chunks.push(chunk);
          });
          res.on('end', () => {
            if (finished) return;
            try {
              if (!/^application\/json\b/i.test(String(res.headers['content-type'])) || res.headers['content-encoding']) throw unavailable();
              const status = res.statusCode ?? 503;
              const body = responseBody(JSON.parse(Buffer.concat(chunks).toString('utf8')), status, target);
              finish(undefined, { status, body });
            } catch (error) { finish(error); }
          });
        });
        request.on('error', cancel);
        request.end(target.body);
      } catch { cancel(); }
    });
  }
  onModuleDestroy() { this.closed = true; for (const cancel of this.pending) cancel(); }
}
