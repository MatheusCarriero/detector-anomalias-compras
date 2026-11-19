import { Inject, Injectable } from '@nestjs/common';
import type { OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { PRISMA_CLIENT } from './prisma-client.provider.js';
import type { PrismaLifecycleClient } from './prisma-client.provider.js';
import { Prisma } from '../../generated/prisma/client.js';

export type DatabaseTransaction = Pick<Prisma.TransactionClient, '$queryRaw' | '$executeRaw'>;
type TransactionClient = PrismaLifecycleClient & {
  $transaction?: <T>(work: (tx: DatabaseTransaction) => Promise<T>, options: {
    isolationLevel: 'ReadCommitted'; maxWait: number; timeout: number;
  }) => Promise<T>;
};

@Injectable()
export class PrismaService implements OnModuleInit, OnModuleDestroy {
  constructor(
    @Inject(PRISMA_CLIENT) private readonly client: TransactionClient,
  ) {}

  // Reuses the lifecycle-managed client. No pool, connection or retry is created
  // here. Raw errors stay inside the repository boundary for safe classification.
  async transaction<T>(work: (tx: DatabaseTransaction) => Promise<T>, access: 'read' | 'write'): Promise<T> {
    if (!this.client.$transaction) throw new Error('Transaction client unavailable');
    if (access !== 'read' && access !== 'write') throw new Error('Invalid transaction access');
    return this.client.$transaction(async (tx) => {
      if (access === 'read') await tx.$executeRaw(Prisma.sql`SET TRANSACTION READ ONLY`);
      await tx.$executeRaw(Prisma.sql`SET LOCAL statement_timeout = '5s'`);
      await tx.$executeRaw(Prisma.sql`SET LOCAL lock_timeout = '2s'`);
      return work(tx);
    }, { isolationLevel: 'ReadCommitted', maxWait: 2000, timeout: 10000 });
  }

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
