import { EventEmitter } from 'node:events';
import { Test } from '@nestjs/testing';
import type { NestExpressApplication } from '@nestjs/platform-express';
import request from 'supertest';
import { DemoModule } from '../src/demo/demo.module.js';
import { catalog, failure, packet, preparationRequest, prepared, runPacket, runResult, inferenceProtocol } from './fixtures/procurement-demo.js';

type Completion = (error: Error | null, stdout: string, stderr: string) => void;
const mock = vi.hoisted(() => ({ execFile: vi.fn() }));
vi.mock('node:child_process', () => ({ execFile: mock.execFile }));
vi.mock('@prisma/adapter-pg', () => { throw new Error('Demo must not import PostgreSQL adapter'); });
vi.mock('pg', () => { throw new Error('Demo must not import PostgreSQL driver'); });

describe('Aggregated demo routes, Python mocked and PostgreSQL blocked', () => {
  let app: NestExpressApplication;
  let output: string;
  let exit: number;
  beforeEach(async () => {
    output = packet(catalog()); exit = 0;
    mock.execFile.mockReset().mockImplementation((_file, _args, _options, done: Completion) => {
      const child = new EventEmitter();
      const stdin = Object.assign(new EventEmitter(), { end: vi.fn(() => {
        queueMicrotask(() => {
          done(exit ? Object.assign(new Error('private'), { code: exit }) : null, output, '');
          child.emit('close');
        });
      }) });
      return Object.assign(child, { stdin, kill: vi.fn() });
    });
    const module = await Test.createTestingModule({ imports: [DemoModule] }).compile();
    app = module.createNestApplication<NestExpressApplication>({ logger: false });
    app.useBodyParser('json', { limit: '1kb', inflate: false });
    await app.init();
    expect(mock.execFile).not.toHaveBeenCalled();
  });
  afterEach(async () => { await app?.close(); });
  it('serves the existing Invoice/P4 page without running Python', async () => {
    const response = await request(app.getHttpServer()).get('/').expect(200);
    expect(response.text).toContain('Executar análise');
    await request(app.getHttpServer()).get('/demo/assets/purchase.js').expect(200);
    expect(mock.execFile).not.toHaveBeenCalled();
  });
  it('gets the fixed catalog with no request data', async () => {
    await request(app.getHttpServer()).get('/demo/procurement-v2/operations').expect(200, catalog());
    expect(mock.execFile).toHaveBeenCalledOnce();
  });
  it.each([false, true])('prepares without scoring, unavailable=%s', async unavailable => {
    output = packet(prepared(unavailable));
    await request(app.getHttpServer()).post('/demo/procurement-v2/prepare')
      .send(preparationRequest(unavailable)).expect(200, prepared(unavailable));
  });
  it.each([
    {}, [], { ...preparationRequest(), features: [1, 2, 3, 4, 5] },
    { ...preparationRequest(), path: 'private' },
    { ...preparationRequest(), operation: { ...preparationRequest().operation, occurrence: 2 } },
  ])('rejects input %j without spawning', async body => {
    await request(app.getHttpServer()).post('/demo/procurement-v2/prepare').send(body).expect(400);
    expect(mock.execFile).not.toHaveBeenCalled();
  });
  it('rejects query, GET body, unsupported input and missing body', async () => {
    await request(app.getHttpServer()).get('/demo/procurement-v2/operations?source=other').expect(400);
    await request(app.getHttpServer()).get('/demo/procurement-v2/operations').send({}).expect(400);
    await request(app.getHttpServer()).post('/demo/procurement-v2/prepare?path=other').send(preparationRequest()).expect(400);
    await request(app.getHttpServer()).post('/demo/procurement-v2/prepare').set('Content-Type', 'text/plain').send('external').expect(400);
    await request(app.getHttpServer()).post('/demo/procurement-v2/prepare').expect(400);
    await request(app.getHttpServer()).post('/demo/procurement-v2/prepare').set('Content-Encoding', 'identity').send(preparationRequest()).expect(400);
    expect(mock.execFile).not.toHaveBeenCalled();
  });
  it('rejects invalid JSON, uploads and oversized input', async () => {
    await request(app.getHttpServer()).post('/demo/procurement-v2/prepare').set('Content-Type', 'application/json').send('{').expect(400);
    await request(app.getHttpServer()).post('/demo/procurement-v2/prepare').attach('model', Buffer.from('fake'), 'untrusted.joblib').expect(400);
    await request(app.getHttpServer()).post('/demo/procurement-v2/prepare').send({ data: 'x'.repeat(1024) }).expect(413);
    expect(mock.execFile).not.toHaveBeenCalled();
  });
  it('does not implement GET inference or import routes', async () => {
    await request(app.getHttpServer()).get('/demo/procurement-v2/runs').expect(404);
    await request(app.getHttpServer()).post('/demo/procurement-v2/operations').send({}).expect(404);
    expect(mock.execFile).not.toHaveBeenCalled();
  });
  it.each([false, true])('returns run output without persistence (unavailable=%s)', async unavailable => {
    output = runPacket(runResult(unavailable));
    await request(app.getHttpServer()).post('/demo/procurement-v2/runs')
      .send(preparationRequest(unavailable)).expect(200, runResult(unavailable));
  });
  it('refuses external data, query and content type on runs before Python', async () => {
    await request(app.getHttpServer()).post('/demo/procurement-v2/runs').send({ ...preparationRequest(), features: [1, 2] }).expect(400);
    await request(app.getHttpServer()).post('/demo/procurement-v2/runs?path=x').send(preparationRequest()).expect(400);
    await request(app.getHttpServer()).post('/demo/procurement-v2/runs').set('Content-Type', 'text/plain').send('external').expect(400);
    expect(mock.execFile).not.toHaveBeenCalled();
  });
  it('maps missing model to sanitized 503 without a replacement', async () => {
    output = JSON.stringify({ protocol: inferenceProtocol, status: 'technical_error', error: 'CLI_MODEL_UNAVAILABLE' }); exit = 1;
    const result = await request(app.getHttpServer()).post('/demo/procurement-v2/runs').send(preparationRequest()).expect(503);
    expect(result.body.message).toBe('PROCUREMENT_MODEL_UNAVAILABLE');
    expect(mock.execFile).toHaveBeenCalledOnce();
  });
  it.each([
    [1, failure('technical_error', 'CLI_SOURCE_UNAVAILABLE'), 503],
    [2, failure('invalid_request', 'CLI_REQUEST'), 400],
    [0, '{private secrets and paths', 502],
    [1, packet(catalog()), 502],
  ] as const)('maps exit %s to HTTP %s without disclosing output', async (code, text, status) => {
    output = text; exit = code;
    const response = await request(app.getHttpServer()).get('/demo/procurement-v2/operations').expect(status);
    expect(response.text).not.toMatch(/private|secrets|paths|stack/);
  });
  it('still serves the Invoice POST using its own contract and runner', async () => {
    const invoice = {
      contract: 'invoice-demo/1.0', origin: 'synthetic', source_reconciled: false,
      model_sha256: 'c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b',
      score_kind: 'negative_score_samples', score_direction: 'higher_is_more_anomalous',
      rows: [{ id: 'demo-001', score: 0.8, rank: 1 }, { id: 'demo-002', score: 0.4, rank: 2 }, { id: 'demo-003', score: 0.2, rank: 3 }],
    };
    output = JSON.stringify(invoice);
    await request(app.getHttpServer()).post('/demo/invoice-runs').send({}).expect(200, invoice);
    expect(mock.execFile.mock.calls[0][1].at(-1)).toMatch(/invoice_demo_runner.py$/);
  });
});
