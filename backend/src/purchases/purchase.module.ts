import { PurchasePriceReviewController } from './purchase-price-review.controller.js';
import { PurchasePriceReviewService } from './purchase-price-review.service.js';
import { Module } from '@nestjs/common';
import { PrismaModule } from '../prisma/prisma.module.js';
import { PrismaService } from '../prisma/prisma.service.js';
import { PurchaseController } from './purchase.controller.js';
import { PurchaseRepository } from './purchase-repository.js';
import { PurchaseLocalGuard } from './purchase-http.js';
import { PurchaseComparabilityRepository } from './purchase-comparability.repository.js';
import { PurchaseStatisticsService } from './purchase-statistics.service.js';
import { PurchaseComparabilityService } from './purchase-comparability.service.js';
import { PurchaseComparabilityController } from './purchase-comparability.controller.js';

// Deliberately absent from AppModule and DemoModule. Only p4-main starts this API.
@Module({
  imports: [PrismaModule], controllers: [PurchaseController, PurchaseComparabilityController, PurchasePriceReviewController],
  providers: [PurchaseLocalGuard, {
    provide: PurchasePriceReviewService, inject: [PurchaseComparabilityService],
    useFactory: (comparability: PurchaseComparabilityService) => new PurchasePriceReviewService(comparability),
  }, {
    provide: PurchaseRepository, inject: [PrismaService],
    useFactory: (prisma: PrismaService) => new PurchaseRepository(prisma, {
      technicalUser: { issuer: 'p4-demo', subject: 'manual-purchase-service' },
    }),
  }, {
    provide: PurchaseComparabilityRepository, inject: [PrismaService, PurchaseRepository],
    useFactory: (prisma: PrismaService, purchases: PurchaseRepository) => new PurchaseComparabilityRepository(prisma, purchases),
  }, {
    provide: PurchaseStatisticsService, inject: [PurchaseRepository],
    useFactory: (purchases: PurchaseRepository) => new PurchaseStatisticsService(purchases),
  }, {
    provide: PurchaseComparabilityService, inject: [PurchaseComparabilityRepository, PurchaseStatisticsService],
    useFactory: (repository: PurchaseComparabilityRepository, statistics: PurchaseStatisticsService) =>
      new PurchaseComparabilityService(repository, statistics),
  }],
})
export class PurchaseModule {}
