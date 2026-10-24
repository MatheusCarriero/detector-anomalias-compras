import { Socket } from 'node:net';
import { Test } from '@nestjs/testing';
import { PRISMA_CLIENT } from './prisma-client.provider.js';
import { PrismaModule } from './prisma.module.js';
import { PrismaService } from './prisma.service.js';

describe('PrismaService lifecycle', () => {
  let networkAttempts: number;

  beforeEach(() => {
    networkAttempts = 0;
    vi.stubEnv('DATABASE_URL', undefined);
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
      networkAttempts += 1;
      throw new Error('Network access is forbidden in this unit test');
    });
  });

  afterEach(() => {
    try {
      expect(networkAttempts).toBe(0);
    } finally {
      vi.restoreAllMocks();
      vi.unstubAllEnvs();
    }
  });

  it('connects only on initialization and disconnects on close using the overridden provider', async () => {
    const events: string[] = [];
    const client = {
      $connect: async () => {
        events.push('connect');
      },
      $disconnect: async () => {
        events.push('disconnect');
      },
    };
    const module = await Test.createTestingModule({ imports: [PrismaModule] })
      .overrideProvider(PRISMA_CLIENT)
      .useValue(client)
      .compile();

    expect(module.get(PrismaService)).toBeInstanceOf(PrismaService);
    expect(events).toEqual([]);
    try {
      await module.init();
      expect(events).toEqual(['connect']);
    } finally {
      await module.close();
    }
    expect(events).toEqual(['connect', 'disconnect']);
  });

  it('fails safely without runtime configuration when the provider is not overridden', async () => {
    await expect(
      Test.createTestingModule({ imports: [PrismaModule] }).compile(),
    ).rejects.toThrow(/DATABASE_URL/);
  });

  it('redacts connection failures and releases resources without retrying', async () => {
    const events: string[] = [];
    const service = new PrismaService({
      $connect: async () => {
        events.push('connect');
        throw new Error('postgresql://detector_runtime:secret@fixture:5432/db');
      },
      $disconnect: async () => {
        events.push('disconnect');
      },
    });

    await expect(service.onModuleInit()).rejects.toThrow(
      /^Unable to connect Prisma client$/,
    );
    expect(events).toEqual(['connect', 'disconnect']);
  });

  it('does not expose a cleanup failure after a connection failure', async () => {
    const service = new PrismaService({
      $connect: async () => {
        throw new Error('secret-connect');
      },
      $disconnect: async () => {
        throw new Error('secret-disconnect');
      },
    });
    await expect(service.onModuleInit()).rejects.toThrow(
      /^Unable to connect Prisma client$/,
    );
  });

  it('redacts disconnection errors', async () => {
    const service = new PrismaService({
      $connect: async () => {},
      $disconnect: async () => {
        throw new Error('secret-disconnect');
      },
    });
    await expect(service.onModuleDestroy()).rejects.toThrow(
      /^Unable to disconnect Prisma client$/,
    );
  });
});
