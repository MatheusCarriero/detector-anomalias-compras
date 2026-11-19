import { Controller, Get, Inject, Param, Post, Req, Res, UseGuards } from '@nestjs/common';
import type { Request, Response } from 'express';
import { PURCHASE_CONTRACT } from './purchase-contract.js';
import { PURCHASE_CATALOG } from './purchase-catalog.js';
import { PurchaseRepository } from './purchase-repository.js';
import type { PurchaseRecord } from './purchase-repository.js';
import { PurchaseHttpError, PurchaseLocalGuard, purchaseValue } from './purchase-http.js';

function publicPurchase(record: PurchaseRecord) {
  const p = record.purchase;
  return { id: record.id, idempotency_key: record.source.source_id, recorded_at: record.recorded_at, revision_no: record.revision_no,
    purchase: {
      supplier: { id: p.supplier.id, name: p.supplier.name },
      product: { id: p.product.id, name: p.product.name, unit: p.product.unit },
      department: { id: p.department.id, name: p.department.name },
      quantity: p.quantity, unit_price: p.unit_price, total: p.total, currency: p.currency,
      purchase_date: p.purchase_date, payment_days: p.payment_days,
    }, analysis: { status: record.analysis.status, reason: record.analysis.reason,
      explanation: 'Compras manuais em BRL não possuem compatibilidade científica comprovada com a Procurement V2.' },
  };
}
function noQuery(request: Request) {
  if (Object.keys(request.query).length) throw new PurchaseHttpError('P4_INVALID_REQUEST');
}

@Controller('p4')
@UseGuards(PurchaseLocalGuard)
export class PurchaseController {
  constructor(@Inject(PurchaseRepository) private readonly repository: PurchaseRepository) {}

  @Get('catalog')
  catalog(@Req() request: Request) {
    noQuery(request);
    return { contract: PURCHASE_CONTRACT, currency: 'BRL', catalog: PURCHASE_CATALOG };
  }

  @Post('purchases')
  async create(@Req() request: Request, @Res({ passthrough: true }) response: Response) {
    noQuery(request);
    const result = purchaseValue(await this.repository.create(request.body as unknown));
    response.status(result.outcome === 'created' ? 201 : 200);
    return { contract: PURCHASE_CONTRACT, outcome: result.outcome, purchase: publicPurchase(result.purchase) };
  }

  @Get('purchases/by-key/:key')
  async byKey(@Param('key') key: string, @Req() request: Request) {
    noQuery(request);
    return { contract: PURCHASE_CONTRACT, purchase: publicPurchase(purchaseValue(await this.repository.getByKey(key))) };
  }

  @Get('purchases/:id')
  async byId(@Param('id') id: string, @Req() request: Request) {
    noQuery(request);
    return { contract: PURCHASE_CONTRACT, purchase: publicPurchase(purchaseValue(await this.repository.get(id))) };
  }

  @Get('purchases')
  async history(@Req() request: Request) {
    const query = request.query;
    const limit = query.limit;
    if (Object.keys(query).some(key => !['limit', 'after_recorded_at', 'after_id'].includes(key)) ||
      Object.values(query).some(value => typeof value !== 'string') ||
      (limit !== undefined && (typeof limit !== 'string' || limit.length > 3 || !/^(?:[1-9][0-9]?|100)$/.test(limit))) ||
      ((query.after_recorded_at === undefined) !== (query.after_id === undefined))) {
      throw new PurchaseHttpError('P4_INVALID_REQUEST');
    }
    const result = purchaseValue(await this.repository.list({
      ...(limit !== undefined ? { limit: Number(limit) } : {}),
      ...(query.after_id !== undefined ? { after: { recorded_at: query.after_recorded_at as string, id: query.after_id as string } } : {}),
    }));
    return { contract: PURCHASE_CONTRACT, items: result.items.map(publicPurchase), next_cursor: result.next_cursor };
  }
}
