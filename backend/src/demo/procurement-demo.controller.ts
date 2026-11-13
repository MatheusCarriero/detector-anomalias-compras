import { BadRequestException, Controller, Get, Header, HttpCode, Inject, Post, Req } from '@nestjs/common';
import type { Request } from 'express';
import { ProcurementDemoService } from './procurement-demo.service.js';

@Controller('demo/procurement-v2')
export class ProcurementDemoController {
  constructor(@Inject(ProcurementDemoService) private readonly demo: ProcurementDemoService) {}

  @Get('operations')
  @Header('Cache-Control', 'no-store')
  operations(@Req() request: Request) {
    if (Object.keys(request.query).length || request.headers['content-encoding'] !== undefined
      || request.headers['transfer-encoding'] !== undefined
      || Number(request.headers['content-length'] ?? 0) !== 0 || request.body !== undefined) {
      throw new BadRequestException('PROCUREMENT_INVALID_REQUEST');
    }
    return this.demo.catalog();
  }

  @Post('prepare')
  @HttpCode(200)
  @Header('Cache-Control', 'no-store')
  prepare(@Req() request: Request) {
    if (Object.keys(request.query).length || request.headers['content-encoding'] !== undefined
      || !/^application\/json(?:\s*;|$)/i.test(request.headers['content-type'] ?? '')) {
      throw new BadRequestException('PROCUREMENT_INVALID_REQUEST');
    }
    return this.demo.prepare(request.body as unknown);
  }
}
