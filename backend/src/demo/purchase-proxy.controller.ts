import { All, Controller, Inject, Req, Res, UseFilters } from '@nestjs/common';
import type { Request, Response, NextFunction } from 'express';
import type { NestExpressApplication } from '@nestjs/platform-express';
import { PurchaseHttpError, PurchaseHttpFilter } from '../purchases/purchase-http.js';
import { PurchaseProxy } from './purchase-proxy.js';

/** Register immediately after the demo JSON parser: parser errors occur before
 * controller filters. Keep Invoice/V2 handling unchanged and discard raw input. */
export function configurePurchaseProxyErrors(app: NestExpressApplication) {
  app.use((error: unknown, request: Request, response: Response, next: NextFunction) => {
    if (!request.path.startsWith('/demo/p4/')) { next(error); return; }
    const status = error && typeof error === 'object' ? (error as { status?: unknown }).status : undefined;
    const safe = new PurchaseHttpError(status === 400 ? 'P4_INVALID_REQUEST' : status === 413 ? 'P4_PAYLOAD_TOO_LARGE'
      : status === 415 ? 'P4_UNSUPPORTED_MEDIA' : 'P4_INTERNAL_ERROR');
    const body = safe.getResponse() as { contract: string; error: { code: string; message: string } };
    if (status === 413) body.error.message = 'O corpo da requisição excede o limite de 1 KiB do demonstrador.';
    response.set({ 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    response.status(safe.getStatus()).json(body);
  });
}

@Controller('demo/p4')
@UseFilters(PurchaseHttpFilter)
export class PurchaseProxyController {
  constructor(@Inject(PurchaseProxy) private readonly proxy: PurchaseProxy) {}

  @All(['catalog', 'purchases', 'purchases/by-key/:key', 'purchases/:id'])
  async forward(@Req() request: Request, @Res() response: Response) {
    response.set({ 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
    const result = await this.proxy.forward(request);
    response.status(result.status).json(result.body);
  }
}
