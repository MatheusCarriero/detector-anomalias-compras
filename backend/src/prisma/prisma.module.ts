import { Module } from '@nestjs/common';
import { createPrismaClient, PRISMA_CLIENT } from './prisma-client.provider.js';
import { PrismaService } from './prisma.service.js';

@Module({
  providers: [
    { provide: PRISMA_CLIENT, useFactory: createPrismaClient },
    PrismaService,
  ],
  exports: [PrismaService],
})
export class PrismaModule {}
