import { Controller, Get, Inject, Param, Post, Req, Res, UseGuards } from '@nestjs/common';
import type { Request, Response } from 'express';
import { PurchaseHttpError, PurchaseLocalGuard } from './purchase-http.js';
import { PurchaseComparabilityService } from './purchase-comparability.service.js';

function noQuery(request: Request) {
  if (Object.keys(request.query).length) throw new PurchaseHttpError('P4_INVALID_REQUEST');
}

@Controller('p4/purchases/:id/comparability')
@UseGuards(PurchaseLocalGuard)
export class PurchaseComparabilityController {
  constructor(@Inject(PurchaseComparabilityService) private readonly service: PurchaseComparabilityService) {}

  @Get()
  status(@Param('id') id: string, @Req() request: Request) {
    noQuery(request); return this.service.status(id);
  }

  @Get('revisions/:revision')
  revision(@Param('id') id: string, @Param('revision') revision: string, @Req() request: Request) {
    noQuery(request); return this.service.revision(id, revision);
  }

  @Post('revisions')
  async create(@Param('id') id: string, @Req() request: Request, @Res({ passthrough: true }) response: Response) {
    noQuery(request);
    const result = await this.service.create(id, request.body as unknown);
    response.status(result.outcome === 'created' ? 201 : 200);
    return result;
  }
}
