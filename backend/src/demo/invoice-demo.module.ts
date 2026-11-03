import { Module } from '@nestjs/common';
import { InvoiceDemoController } from './invoice-demo.controller.js';
import { InvoiceDemoService } from './invoice-demo.service.js';
import { InvoiceDemoPageController } from './invoice-demo-page.controller.js';

// Independent of AppModule: starting this demo must never initialize Prisma.
@Module({ controllers: [InvoiceDemoController, InvoiceDemoPageController], providers: [InvoiceDemoService] })
export class InvoiceDemoModule {}
