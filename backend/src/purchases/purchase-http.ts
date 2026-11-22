import { Catch, HttpException, Injectable } from '@nestjs/common';
import type { ArgumentsHost, CanActivate, ExceptionFilter, ExecutionContext } from '@nestjs/common';
import type { NestExpressApplication } from '@nestjs/platform-express';
import type { Request, Response, NextFunction } from 'express';
import { PURCHASE_CONTRACT } from './purchase-contract.js';
import type { RepositoryResult } from './purchase-repository.js';

export const P4_HTTP_HOST = '127.0.0.1';
export const P4_HTTP_PORT = 3002;
const authority = `${P4_HTTP_HOST}:${P4_HTTP_PORT}`;
const origin = `http://${authority}`;
const messages = {
  P4_INVALID_REQUEST: [400, 'Requisição inválida. Confira os campos, identificadores e paginação.'],
  P4_LOCAL_ONLY: [403, 'Esta API está disponível exclusivamente no ambiente local autorizado.'],
  P4_NOT_FOUND: [404, 'Compra não encontrada.'],
  P4_ROUTE_NOT_FOUND: [404, 'Rota não encontrada.'],
  P4_METHOD_NOT_ALLOWED: [405, 'Método não permitido.'],
  P4_IDEMPOTENCY_CONFLICT: [409, 'A chave de idempotência já está associada a outro conteúdo.'],
  P4_COMPARABILITY_INVALID: [400, 'Metadados inválidos ou incompatíveis com o recibo da compra.'],
  P4_COMPARABILITY_CONFLICT: [409, 'Revisão ou definição conflitante. Consulte a revisão antes de reenviar.'],
  P4_PAYLOAD_TOO_LARGE: [413, 'O corpo da requisição excede o limite de 4 KiB.'],
  P4_UNSUPPORTED_MEDIA: [415, 'Envie somente JSON UTF-8 sem compressão.'],
  P4_SERVICE_UNAVAILABLE: [503, 'Serviço indisponível. Se enviou uma compra, consulte a mesma chave antes de tentar novamente.'],
  P4_SERVICE_BUSY: [503, 'Operação não confirmada. Consulte a mesma chave antes de tentar novamente.'],
  P4_INTERNAL_ERROR: [500, 'Não foi possível confirmar a operação. Consulte a mesma chave antes de tentar novamente.'],
} as const;
type HttpCode = keyof typeof messages;
export class PurchaseHttpError extends HttpException {
  constructor(code: HttpCode) {
    const [status, message] = messages[code];
    super({ contract: PURCHASE_CONTRACT, error: { code, message } }, status);
  }
}

const invalid = new Set([
  'P4_INVALID_STRUCTURE', 'P4_UNSUPPORTED_CONTRACT', 'P4_INVALID_ORIGIN', 'P4_INVALID_IDEMPOTENCY_KEY',
  'P4_UNAUTHORIZED_CATALOG_ENTRY', 'P4_INVALID_CURRENCY', 'P4_INVALID_QUANTITY', 'P4_INVALID_UNIT_PRICE',
  'P4_INVALID_PAYMENT_DAYS', 'P4_INVALID_PURCHASE_DATE', 'P4_FUTURE_PURCHASE_DATE', 'P4_INVALID_QUERY',
]);
export function purchaseValue<T>(result: RepositoryResult<T>): T {
  if (result.ok) return result.value;
  const code = result.error.code;
  if (invalid.has(code)) throw new PurchaseHttpError('P4_INVALID_REQUEST');
  if (code === 'P4_IDEMPOTENCY_CONFLICT' || code === 'P4_NOT_FOUND') throw new PurchaseHttpError(code);
  if (code === 'P4_STORAGE_BUSY') throw new PurchaseHttpError('P4_SERVICE_BUSY');
  if (['P4_STORAGE_FAILURE', 'P4_STORAGE_PERMISSION', 'P4_REFERENCE_UNAVAILABLE'].includes(code)) {
    throw new PurchaseHttpError('P4_SERVICE_UNAVAILABLE');
  }
  throw new PurchaseHttpError('P4_INTERNAL_ERROR');
}

/** Loopback is a deployment boundary, not human authentication. Never trust proxy headers. */
export function checkLocalPurchaseRequest(request: Request): void {
  if (!['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(request.socket.remoteAddress ?? '') ||
    request.headers.host !== authority ||
    (request.headers.origin !== undefined && request.headers.origin !== origin) ||
    (request.headers['sec-fetch-site'] !== undefined && !['same-origin', 'none'].includes(String(request.headers['sec-fetch-site']))) ||
    Object.keys(request.headers).some(key => /^(forwarded|x-forwarded-.*|x-real-ip)$/i.test(key))) {
    throw new PurchaseHttpError('P4_LOCAL_ONLY');
  }
  if (!['GET', 'POST'].includes(request.method)) throw new PurchaseHttpError('P4_METHOD_NOT_ALLOWED');
  if (request.method === 'POST') {
    // A cross-origin browser cannot set this header without an allowed preflight.
    // It is public and is deliberately NOT a password or authentication token.
    if (request.headers['x-p4-local'] !== PURCHASE_CONTRACT) throw new PurchaseHttpError('P4_LOCAL_ONLY');
    const type = request.headers['content-type'];
    if (typeof type !== 'string' || !/^application\/json(?:\s*;\s*charset=utf-8)?$/i.test(type) ||
      request.headers['content-encoding'] !== undefined) throw new PurchaseHttpError('P4_UNSUPPORTED_MEDIA');
  } else if (request.headers['content-encoding'] !== undefined || request.headers['transfer-encoding'] !== undefined ||
    Number(request.headers['content-length'] ?? 0) !== 0 || request.body !== undefined) {
    throw new PurchaseHttpError('P4_INVALID_REQUEST');
  }
}

@Injectable()
export class PurchaseLocalGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    checkLocalPurchaseRequest(context.switchToHttp().getRequest<Request>()); return true;
  }
}

@Catch()
export class PurchaseHttpFilter implements ExceptionFilter {
  catch(error: unknown, host: ArgumentsHost) {
    let safe: PurchaseHttpError;
    if (error instanceof PurchaseHttpError) safe = error;
    else {
      // Discard exception bodies/messages, including body-parser input and SQL errors.
      const status = error instanceof HttpException ? error.getStatus() :
        error && typeof error === 'object' ? (error as { status?: unknown }).status : undefined;
      const code: HttpCode = status === 400 ? 'P4_INVALID_REQUEST' : status === 413 ? 'P4_PAYLOAD_TOO_LARGE'
        : status === 415 ? 'P4_UNSUPPORTED_MEDIA' : status === 404 ? 'P4_ROUTE_NOT_FOUND' : 'P4_INTERNAL_ERROR';
      safe = new PurchaseHttpError(code);
    }
    host.switchToHttp().getResponse<Response>().status(safe.getStatus()).json(safe.getResponse());
  }
}

export function configurePurchaseHttp(app: NestExpressApplication): void {
  const express = app.getHttpAdapter().getInstance() as { disable(key: string): void; set(key: string, value: unknown): void };
  express.disable('x-powered-by'); express.set('trust proxy', false);
  app.use((_request: Request, response: Response, next: NextFunction) => {
    response.setHeader('Cache-Control', 'no-store'); response.setHeader('X-Content-Type-Options', 'nosniff'); next();
  });
  app.useBodyParser('json', { limit: '4kb', inflate: false });
  app.useGlobalFilters(new PurchaseHttpFilter());
  // No CORS or cookie/session middleware. The P4.8B UI is a separate increment.
}
