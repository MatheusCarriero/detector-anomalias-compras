import { Inject, Injectable } from '@nestjs/common';
import type { OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { PRISMA_CLIENT } from './prisma-client.provider.js';
import type { PrismaLifecycleClient } from './prisma-client.provider.js';

@Injectable()
export class PrismaService implements OnModuleInit, OnModuleDestroy {
  constructor(
    @Inject(PRISMA_CLIENT) private readonly client: PrismaLifecycleClient,
  ) {}

  async onModuleInit(): Promise<void> {
    try {
      await this.client.$connect();
    } catch {
      // Startup can fail before Nest runs normal shutdown hooks.
      await this.client.$disconnect().catch(() => undefined);
      throw new Error('Unable to connect Prisma client');
    }
  }

  async onModuleDestroy(): Promise<void> {
    try {
      await this.client.$disconnect();
    } catch {
      throw new Error('Unable to disconnect Prisma client');
    }
  }
}
