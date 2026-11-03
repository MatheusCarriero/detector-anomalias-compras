import { Test } from '@nestjs/testing';
import type { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { InvoiceDemoModule } from '../src/demo/invoice-demo.module.js';

type Completion = (error: Error | null, stdout: string, stderr: string) => void;
const processMock = vi.hoisted(() => ({ execFile: vi.fn(), kill: vi.fn() }));
vi.mock('node:child_process', () => ({ execFile: processMock.execFile }));
vi.mock('@prisma/adapter-pg', () => {
  throw new Error('Page tests must not import PostgreSQL');
});
vi.mock('pg', () => {
  throw new Error('Page tests must not import the PostgreSQL driver');
});

// Invented transport values; no Python process or scientific artifact is used.
const response = {
  contract: 'invoice-demo/1.0', origin: 'synthetic', source_reconciled: false,
  model_sha256: 'c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b',
  score_kind: 'negative_score_samples', score_direction: 'higher_is_more_anomalous',
  rows: [
    { id: 'demo-001', score: 0.8, rank: 1 },
    { id: 'demo-002', score: 0.4, rank: 2 },
    { id: 'demo-003', score: 0.1, rank: 3 },
  ],
};

describe('Invoice demo page (offline E2E)', () => {
  let app: NestExpressApplication;

  beforeEach(async () => {
    vi.stubEnv('DATABASE_URL', undefined);
    processMock.execFile.mockReset().mockImplementation(() => {
      throw new Error('Unexpected Python launch while serving the page');
    });
    processMock.kill.mockReset().mockReturnValue(true);
    const fixture = await Test.createTestingModule({ imports: [InvoiceDemoModule] }).compile();
    app = fixture.createNestApplication<NestExpressApplication>({ logger: false });
    app.useBodyParser('json', { limit: '1kb', inflate: false });
    await app.init();
  });

  afterEach(async () => {
    try {
      await app?.close();
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it('serves a Portuguese page with local assets and no inference on GET', async () => {
    const page = await request(app.getHttpServer()).get('/').expect(200);
    expect(page.headers['content-type']).toMatch(/^text\/html/);
    expect(page.text).toMatch(/<html[^>]+lang="pt-BR"/);
    expect(page.text).toContain('Executar análise');
    expect(page.text).toContain('source_reconciled=false');
    expect(page.text).toContain('/demo/assets/style.css');
    expect(page.text).toContain('/demo/assets/app.js');
    expect(page.text).not.toMatch(/<script(?![^>]*\bsrc=)[^>]*>/i);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it('restricts document scripts to same-origin and disables caching/sniffing', async () => {
    const page = await request(app.getHttpServer()).get('/').expect(200);
    expect(page.headers['cache-control']).toContain('no-store');
    expect(page.headers['x-content-type-options']).toBe('nosniff');
    expect(page.headers['content-security-policy']).toContain("script-src 'self'");
    expect(page.headers['content-security-policy']).not.toMatch(/unsafe-inline|unsafe-eval/);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it.each([
    ['/demo/assets/style.css', /^text\/css/],
    ['/demo/assets/app.js', /^(text|application)\/javascript/],
  ])('serves only the expected local asset %s', async (path, contentType) => {
    const asset = await request(app.getHttpServer()).get(path as string).expect(200);
    expect(asset.headers['content-type']).toMatch(contentType as RegExp);
    expect(asset.headers['cache-control']).toContain('no-store');
    expect(asset.headers['x-content-type-options']).toBe('nosniff');
    expect(asset.text.length).toBeGreaterThan(0);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it.each([
    '/demo/assets/unknown.js',
    '/demo/assets/package.json',
    '/demo/assets/%2e%2e%2f%2e%2e%2fpackage.json',
    '/demo/assets/%2e%2e%5c%2e%2e%5cpackage.json',
    '/ml/models/isolation_forest.joblib',
  ])('does not expose arbitrary files at %s', async (path) => {
    await request(app.getHttpServer()).get(path).expect(404);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it('preserves the explicit POST contract after the page and assets are requested', async () => {
    await request(app.getHttpServer()).get('/').expect(200);
    await request(app.getHttpServer()).get('/demo/assets/app.js').expect(200);
    expect(processMock.execFile).not.toHaveBeenCalled();
    processMock.execFile.mockImplementation((
      _file: string, _args: string[], _options: unknown, complete: Completion,
    ) => {
      queueMicrotask(() => complete(null, JSON.stringify(response), ''));
      return { kill: processMock.kill };
    });
    await request(app.getHttpServer()).post('/demo/invoice-runs').expect(200, response);
    expect(processMock.execFile).toHaveBeenCalledOnce();
  });
});
