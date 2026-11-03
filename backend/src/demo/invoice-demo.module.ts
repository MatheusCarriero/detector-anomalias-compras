import { Module } from '@nestjs/common';
import { InvoiceDemoController } from './invoice-demo.controller.js';
import { InvoiceDemoService } from './invoice-demo.service.js';

// Independent of AppModule: starting this demo must never initialize Prisma.
@Module({ controllers: [InvoiceDemoController], providers: [InvoiceDemoService] })
export class InvoiceDemoModule {}
