import { Test } from '@nestjs/testing';
import type { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { InvoiceDemoModule } from '../src/demo/invoice-demo.module.js';

type Completion = (error: Error | null, stdout: string, stderr: string) => void;
const processMock = vi.hoisted(() => ({ execFile: vi.fn(), kill: vi.fn() }));

vi.mock('node:child_process', () => ({ execFile: processMock.execFile }));
vi.mock('@prisma/adapter-pg', () => {
  throw new Error('The demo must not import the PostgreSQL adapter');
});
vi.mock('pg', () => {
  throw new Error('The demo must not import the PostgreSQL driver');
});

// Invented scores: this suite never runs Python or reads a model.
const response = {
  contract: 'invoice-demo/1.0',
  origin: 'synthetic',
  source_reconciled: false,
  model_sha256:
    'c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b',
  score_kind: 'negative_score_samples',
  score_direction: 'higher_is_more_anomalous',
  rows: [
    { id: 'demo-002', score: 0.8, rank: 1 },
    { id: 'demo-001', score: 0.2, rank: 2 },
    { id: 'demo-003', score: 0.2, rank: 3 },
  ],
};

describe('Invoice demo API (offline E2E)', () => {
  let app: NestExpressApplication;

  beforeEach(async () => {
    vi.stubEnv('DATABASE_URL', undefined);
    processMock.execFile.mockReset();
    processMock.kill.mockReset().mockReturnValue(true);
    processMock.execFile.mockImplementation(
      (_file: string, _args: string[], _options: unknown, complete: Completion) => {
        queueMicrotask(() => complete(null, JSON.stringify(response), ''));
        return { kill: processMock.kill };
      },
    );
    const fixture = await Test.createTestingModule({
      imports: [InvoiceDemoModule],
    }).compile();
    app = fixture.createNestApplication<NestExpressApplication>({ logger: false });
    app.useBodyParser('json', { limit: '1kb', inflate: false });
    await app.init();
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  afterEach(async () => {
    try {
      await app?.close();
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it('returns the validated ranking for an empty JSON body', async () => {
    await request(app.getHttpServer())
      .post('/demo/invoice-runs')
      .send({})
      .expect(200, response);
    expect(processMock.execFile).toHaveBeenCalledOnce();
  });

  it('accepts a request without a body', async () => {
    await request(app.getHttpServer())
      .post('/demo/invoice-runs')
      .expect(200, response);
    expect(processMock.execFile).toHaveBeenCalledOnce();
  });

  it.each([
    { model_path: 'untrusted.joblib' },
    { input: 'other.json' },
    { rows: [] },
    { is_fraud: [1] },
    [],
  ])('rejects external input %j before starting Python', async (body) => {
    await request(app.getHttpServer())
      .post('/demo/invoice-runs')
      .send(body)
      .expect(400);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it.each(['"external data"', 'null'])(
    'rejects a raw JSON scalar %s before starting Python',
    async (body) => {
      await request(app.getHttpServer())
        .post('/demo/invoice-runs')
        .set('Content-Type', 'application/json')
        .send(body)
        .expect(400);
      expect(processMock.execFile).not.toHaveBeenCalled();
    },
  );

  it('rejects query parameters', async () => {
    await request(app.getHttpServer())
      .post('/demo/invoice-runs?model=other.joblib')
      .send({})
      .expect(400);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it('rejects text input', async () => {
    await request(app.getHttpServer())
      .post('/demo/invoice-runs')
      .set('Content-Type', 'text/plain')
      .send('external data')
      .expect(400);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it('rejects uploads without reading a model file', async () => {
    await request(app.getHttpServer())
      .post('/demo/invoice-runs')
      .attach('model', Buffer.from('synthetic bytes'), 'untrusted.joblib')
      .expect(400);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it('rejects a content-encoding even when the body is empty JSON', async () => {
    await request(app.getHttpServer())
      .post('/demo/invoice-runs')
      .set('Content-Encoding', 'identity')
      .send({})
      .expect(400);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it('rejects JSON larger than 1kb before starting Python', async () => {
    await request(app.getHttpServer())
      .post('/demo/invoice-runs')
      .send({ unexpected: 'x'.repeat(1024) })
      .expect(413);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it('rejects gzip encoding before attempting decompression or starting Python', async () => {
    await request(app.getHttpServer())
      .post('/demo/invoice-runs')
      .set('Content-Type', 'application/json')
      .set('Content-Encoding', 'gzip')
      // Not a gzip stream: rejection must precede any attempt to decode it.
      .send('{}')
      .expect(415);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it('does not score on GET', async () => {
    await request(app.getHttpServer()).get('/demo/invoice-runs').expect(404);
    expect(processMock.execFile).not.toHaveBeenCalled();
  });

  it.each([
    { name: 'nonzero exit', error: { code: 1 }, status: 502 },
    { name: 'missing executable', error: { code: 'ENOENT' }, status: 503 },
    { name: 'timeout', error: { killed: true }, status: 504 },
  ])('sanitizes $name errors', async ({ error, status }) => {
    processMock.execFile.mockImplementation(
      (_file: string, _args: string[], _options: unknown, complete: Completion) => {
        queueMicrotask(() =>
          complete(
            Object.assign(new Error('private path and credentials'), error),
            'private stdout',
            'private stderr',
          ),
        );
        return { kill: processMock.kill };
      },
    );
    const result = await request(app.getHttpServer())
      .post('/demo/invoice-runs')
      .expect(status);
    expect(result.text).not.toMatch(/private|credentials|stdout|stderr/);
    expect(processMock.execFile).toHaveBeenCalledOnce();
  });

  it('rejects invalid runner output without disclosing it', async () => {
    processMock.execFile.mockImplementation(
      (_file: string, _args: string[], _options: unknown, complete: Completion) => {
        queueMicrotask(() => complete(null, '{private invalid output', ''));
        return { kill: processMock.kill };
      },
    );
    const result = await request(app.getHttpServer())
      .post('/demo/invoice-runs')
      .expect(502);
    expect(result.text).not.toContain('private');
  });

  it('refuses simultaneous runs until the pending process finishes', async () => {
    let finish!: Completion;
    let started!: () => void;
    const processStarted = new Promise<void>((resolve) => {
      started = resolve;
    });
    processMock.execFile.mockImplementation(
      (_file: string, _args: string[], _options: unknown, complete: Completion) => {
        finish = complete;
        started();
        return { kill: processMock.kill };
      },
    );
    const first = request(app.getHttpServer())
      .post('/demo/invoice-runs')
      .then((result) => result);
    await processStarted;
    try {
      await request(app.getHttpServer())
        .post('/demo/invoice-runs')
        .expect(409);
      expect(processMock.execFile).toHaveBeenCalledOnce();
    } finally {
      finish(null, JSON.stringify(response), '');
    }
    const result = await first;
    expect(result.status).toBe(200);
    expect(result.body).toEqual(response);
  });
});
