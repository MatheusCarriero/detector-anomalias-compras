import { BadRequestException, Controller, HttpCode, Inject, Post, Req } from '@nestjs/common';
import type { Request } from 'express';
import { InvoiceDemoService } from './invoice-demo.service.js';

@Controller('demo/invoice-runs')
export class InvoiceDemoController {
  constructor(@Inject(InvoiceDemoService) private readonly demo: InvoiceDemoService) {}

  @Post()
  @HttpCode(200)
  run(@Req() request: Request) {
    const body: unknown = request.body;
    const contentType = request.headers['content-type'];
    const hasBody = request.headers['transfer-encoding'] !== undefined
      || Number(request.headers['content-length'] ?? 0) > 0;
    if (Object.keys(request.query).length
      || request.headers['content-encoding'] !== undefined
      || (contentType !== undefined && !/^application\/json(?:\s*;|$)/i.test(contentType))
      || (hasBody && contentType === undefined)
      || (body !== undefined && (body === null || typeof body !== 'object'
        || Array.isArray(body) || Object.keys(body).length !== 0))) {
      throw new BadRequestException('DEMO_INPUT_NOT_ALLOWED');
    }
    return this.demo.run();
  }
}
