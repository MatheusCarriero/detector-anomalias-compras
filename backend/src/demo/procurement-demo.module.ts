import { Module } from '@nestjs/common';
import { ProcurementDemoController } from './procurement-demo.controller.js';
import { ProcurementDemoService } from './procurement-demo.service.js';

@Module({ controllers: [ProcurementDemoController], providers: [ProcurementDemoService] })
export class ProcurementDemoModule {}
