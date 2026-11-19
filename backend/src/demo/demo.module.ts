import { Module } from '@nestjs/common';
import { InvoiceDemoModule } from './invoice-demo.module.js';
import { ProcurementDemoModule } from './procurement-demo.module.js';
import { PurchaseProxyController } from './purchase-proxy.controller.js';
import { PurchaseProxy } from './purchase-proxy.js';

// Local demonstration only: neither module imports the database application.
@Module({ imports: [InvoiceDemoModule, ProcurementDemoModule],
  controllers: [PurchaseProxyController], providers: [PurchaseProxy] })
export class DemoModule {}
