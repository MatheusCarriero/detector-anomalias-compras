import { Module } from '@nestjs/common';
import { ProcurementDemoController } from './procurement-demo.controller.js';
import { ProcurementDemoService } from './procurement-demo.service.js';
import { ProcurementDemoPageController } from './procurement-demo-page.controller.js';

@Module({ controllers: [ProcurementDemoController, ProcurementDemoPageController], providers: [ProcurementDemoService] })
export class ProcurementDemoModule {}
