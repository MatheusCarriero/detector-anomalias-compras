import { Module } from '@nestjs/common';
import { PrismaModule } from '../prisma/prisma.module.js';
import { PrismaService } from '../prisma/prisma.service.js';
import { PurchaseController } from './purchase.controller.js';
import { PurchaseRepository } from './purchase-repository.js';
import { PurchaseLocalGuard } from './purchase-http.js';

// Deliberately absent from AppModule and DemoModule. Only p4-main starts this API.
@Module({
  imports: [PrismaModule], controllers: [PurchaseController],
  providers: [PurchaseLocalGuard, {
    provide: PurchaseRepository, inject: [PrismaService],
    useFactory: (prisma: PrismaService) => new PurchaseRepository(prisma, {
      technicalUser: { issuer: 'p4-demo', subject: 'manual-purchase-service' },
    }),
  }],
})
export class PurchaseModule {}
