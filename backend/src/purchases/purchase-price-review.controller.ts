import { Controller, Get, Inject, Param, Req, UseGuards } from '@nestjs/common';
import type { Request } from 'express';
import { PurchaseLocalGuard, PurchaseHttpError } from './purchase-http.js';
import { PurchasePriceReviewService } from './purchase-price-review.service.js';

@Controller('p4')
@UseGuards(PurchaseLocalGuard)
export class PurchasePriceReviewController {
  constructor(@Inject(PurchasePriceReviewService) private readonly service: PurchasePriceReviewService) {}
  @Get('purchases/:id/price-analysis')
  review(@Param('id') id: string, @Req() request: Request) {
    if (Object.keys(request.query).length) throw new PurchaseHttpError('P4_INVALID_REQUEST');
    return this.service.review(id);
  }
  @Get('price-analysis/hypothetical')
  hypothetical(@Req() request: Request) {
    if (Object.keys(request.query).join(',') !== 'unit_price') throw new PurchaseHttpError('P4_INVALID_REQUEST');
    return this.service.hypothetical(request.query.unit_price);
  }
  @Get('price-analysis/simulation')
  simulation(@Req() request: Request) {
    if (Object.keys(request.query).length) throw new PurchaseHttpError('P4_INVALID_REQUEST');
    return this.service.simulation();
  }
}
