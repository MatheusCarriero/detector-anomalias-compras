import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { App } from 'supertest/types.js';
import { AppModule } from './../src/app.module.js';
import { PrismaPg } from '@prisma/adapter-pg';
import { PRISMA_CLIENT } from '../src/prisma/prisma-client.provider.js';

vi.mock('@prisma/adapter-pg', () => ({
  PrismaPg: vi.fn(function () {
    throw new Error('A real adapter must never be constructed in E2E tests');
  }),
}));

describe('AppController (e2e)', () => {
  let app: INestApplication<App>;
  let lifecycle: string[];

  beforeEach(async () => {
    vi.stubEnv('DATABASE_URL', undefined);
    vi.clearAllMocks();
    lifecycle = [];
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(PRISMA_CLIENT)
      .useValue({
        $connect: async () => {
          lifecycle.push('connect');
        },
        $disconnect: async () => {
          lifecycle.push('disconnect');
        },
      })
      .compile();

    app = moduleFixture.createNestApplication();
    await app.init();
    expect(lifecycle).toEqual(['connect']);
  });

  it('/ (GET)', () => {
    return request(app.getHttpServer())
      .get('/')
      .expect(200)
      .expect('Hello World!');
  });

  afterEach(async () => {
    try {
      await app?.close();
      expect(lifecycle).toEqual(['connect', 'disconnect']);
      expect(PrismaPg).not.toHaveBeenCalled();
    } finally {
      vi.unstubAllEnvs();
    }
  });
});
