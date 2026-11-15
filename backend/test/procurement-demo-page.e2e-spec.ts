import { Test } from '@nestjs/testing';
import type { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { DemoModule } from '../src/demo/demo.module.js';

const processes = vi.hoisted(() => ({ execFile: vi.fn() }));
vi.mock('node:child_process', () => ({ execFile: processes.execFile }));
vi.mock('pg', () => { throw new Error('Page must not import PostgreSQL'); });
vi.mock('@prisma/adapter-pg', () => { throw new Error('Page must not import Prisma adapter'); });

describe('Procurement V2 page and exact asset whitelist', () => {
  let app: NestExpressApplication;
  beforeEach(async () => {
    processes.execFile.mockReset().mockImplementation(() => { throw new Error('Unexpected Python execution'); });
    const module = await Test.createTestingModule({ imports: [DemoModule] }).compile();
    app = module.createNestApplication<NestExpressApplication>({ logger: false });
    await app.init();
  });
  afterEach(async () => { await app?.close(); });
  it('serves a separate Portuguese page, without running Python', async () => {
    const response = await request(app.getHttpServer()).get('/demo/procurement-v2').expect(200);
    expect(response.headers['content-type']).toMatch(/^text\/html/);
    expect(response.text).toContain('lang="pt-BR"');
    expect(response.text).toContain('Consultar histórico');
    expect(response.text).toContain('Analisar com IA');
    expect(response.text).toContain('/demo/procurement-v2/assets/app.js');
    expect(response.text).not.toMatch(/<script(?![^>]*\bsrc=)[^>]*>|https?:\/\/|<iframe/i);
    expect(response.headers['content-security-policy']).toContain("connect-src 'self'");
    expect(response.headers['content-security-policy']).not.toMatch(/unsafe-inline|unsafe-eval/);
    expect(response.headers['cache-control']).toBe('no-store');
    expect(response.headers['x-content-type-options']).toBe('nosniff');
    expect(processes.execFile).not.toHaveBeenCalled();
  });
  it.each([['style.css', /text\/css/], ['app.js', /javascript/]] as const)('serves %s explicitly', async (asset, type) => {
    const response = await request(app.getHttpServer()).get(`/demo/procurement-v2/assets/${asset}`).expect(200);
    expect(response.headers['content-type']).toMatch(type);
    expect(response.headers['cache-control']).toBe('no-store');
    expect(processes.execFile).not.toHaveBeenCalled();
  });
  it.each(['', 'index.html', 'model.joblib', 'metadata.json', 'unknown.js',
    '%2e%2e%2f%2e%2e%2fpackage.json', '%2e%2e%5cpackage.json'])('does not expose asset %s', async asset => {
    await request(app.getHttpServer()).get(`/demo/procurement-v2/assets/${asset}`).expect(404);
    expect(processes.execFile).not.toHaveBeenCalled();
  });
  it('preserves the original Invoice page, P4 and their assets', async () => {
    const response = await request(app.getHttpServer()).get('/').expect(200);
    expect(response.text).toContain('id="purchase-form"');
    expect(response.text).toContain('id="run-button"');
    await request(app.getHttpServer()).get('/demo/assets/purchase.js').expect(200);
    await request(app.getHttpServer()).get('/demo/assets/app.js').expect(200);
    expect(processes.execFile).not.toHaveBeenCalled();
  });
});
