import { Module } from '@nestjs/common';
import { InvoiceDemoModule } from './invoice-demo.module.js';
import { ProcurementDemoModule } from './procurement-demo.module.js';

// Local demonstration only: neither module imports the database application.
@Module({ imports: [InvoiceDemoModule, ProcurementDemoModule] })
export class DemoModule {}
