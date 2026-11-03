import type { ExecFileException, ExecFileOptionsWithStringEncoding } from 'node:child_process';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { InvoiceDemoService } from './invoice-demo.service.js';
import { MODEL_SHA256 } from './invoice-demo-response.js';

const processMock = vi.hoisted(() => ({
  execFile: vi.fn(), kill: vi.fn(), end: vi.fn(),
}));
vi.mock('node:child_process', () => ({ execFile: processMock.execFile }));

type Done = (error: ExecFileException | null, stdout: string, stderr: string) => void;
let done: Done;
let service: InvoiceDemoService;
const response = {
  contract: 'invoice-demo/1.0', origin: 'synthetic', source_reconciled: false,
  model_sha256: MODEL_SHA256, score_kind: 'negative_score_samples',
  score_direction: 'higher_is_more_anomalous',
  rows: [
    { id: 'demo-002', score: 0.8, rank: 1 },
    { id: 'demo-001', score: 0.2, rank: 2 },
    { id: 'demo-003', score: 0.2, rank: 3 },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  processMock.execFile.mockImplementation((
    _file: string, _args: string[], _options: ExecFileOptionsWithStringEncoding, callback: Done,
  ) => {
    done = callback;
    return { kill: processMock.kill, stdin: { end: processMock.end } };
  });
  service = new InvoiceDemoService();
});
afterEach(() => vi.unstubAllEnvs());

it('uses only fixed isolated Python/runner paths, bounded output and no secret environment', async () => {
  vi.stubEnv('DATABASE_URL', 'private-database');
  vi.stubEnv('PYTHONPATH', 'untrusted-python');
  vi.stubEnv('SECRET_TOKEN', 'private-token');
  const pending = service.run();
  const root = fileURLToPath(new URL('../../../', import.meta.url));
  expect(processMock.execFile).toHaveBeenCalledWith(
    join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
    ['-I', '-B', join(root, 'ml/scripts/invoice_demo_runner.py')],
    expect.objectContaining({
      cwd: root, shell: false, windowsHide: true, encoding: 'utf8',
      timeout: 30_000, maxBuffer: 65_536, killSignal: 'SIGKILL',
    }), expect.any(Function),
  );
  const options = processMock.execFile.mock.calls[0][2] as ExecFileOptionsWithStringEncoding;
  expect(options.env).not.toHaveProperty('DATABASE_URL');
  expect(options.env).not.toHaveProperty('PYTHONPATH');
  expect(options.env).not.toHaveProperty('SECRET_TOKEN');
  expect(processMock.end).toHaveBeenCalledOnce();
  done(null, JSON.stringify(response), '');
  await expect(pending).resolves.toEqual(response);
});

it('rejects concurrent work until the child callback completes, then releases the lock', async () => {
  const first = service.run();
  await expect(service.run()).rejects.toMatchObject({ status: 409 });
  expect(processMock.execFile).toHaveBeenCalledOnce();
  done(null, JSON.stringify(response), '');
  await first;
  const second = service.run();
  done(null, JSON.stringify(response), '');
  await second;
  expect(processMock.execFile).toHaveBeenCalledTimes(2);
});

it.each([
  [{ code: 'ENOENT' }, 503, 'DEMO_EXECUTOR_UNAVAILABLE'],
  [{ code: 1 }, 502, 'DEMO_EXECUTION_FAILED'],
  [{ killed: true, signal: 'SIGKILL' as const }, 504, 'DEMO_TIMEOUT'],
  [{ code: 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER', killed: true }, 502, 'DEMO_OUTPUT_LIMIT'],
])('sanitizes subprocess failures without retries: %j', async (fields, status, code) => {
  const pending = service.run();
  done(Object.assign(new Error('password private path driver stack'), fields), 'private stdout', 'private stderr');
  await expect(pending).rejects.toMatchObject({ status, message: code });
  expect(processMock.execFile).toHaveBeenCalledOnce();
  const retry = service.run();
  done(null, JSON.stringify(response), '');
  await retry;
});

it.each(['private stdout', '{}', JSON.stringify({ ...response, model_sha256: 'f'.repeat(64) })])(
  'rejects invalid output before responding', async (stdout) => {
    const pending = service.run();
    done(null, stdout, '');
    await expect(pending).rejects.toMatchObject({ status: 502, message: 'DEMO_INVALID_RESPONSE' });
  },
);

it('does not expose stderr even on a successful exit', async () => {
  const pending = service.run();
  done(null, JSON.stringify(response), 'private warning');
  await expect(pending).rejects.toMatchObject({ status: 502, message: 'DEMO_EXECUTION_FAILED' });
});

it('sanitizes synchronous spawn failures and releases the lock', async () => {
  processMock.execFile.mockImplementationOnce(() => { throw new Error('private path'); });
  await expect(service.run()).rejects.toMatchObject({ status: 503, message: 'DEMO_EXECUTOR_UNAVAILABLE' });
  const pending = service.run();
  done(null, JSON.stringify(response), '');
  await pending;
});

it('kills active work during shutdown and waits for callback before completing', async () => {
  const pending = service.run().catch((error: unknown) => error);
  let closed = false;
  const closing = service.onModuleDestroy().then(() => { closed = true; });
  await Promise.resolve();
  expect(processMock.kill).toHaveBeenCalledWith('SIGKILL');
  expect(closed).toBe(false);
  await expect(service.run()).rejects.toMatchObject({ status: 503 });
  done(Object.assign(new Error('private'), { killed: true }), '', 'private');
  expect(await pending).toMatchObject({ status: 503, message: 'DEMO_STOPPING' });
  await closing;
  expect(closed).toBe(true);
});

it('closes an idle service without spawning Python and refuses new work', async () => {
  await service.onModuleDestroy();
  expect(processMock.execFile).not.toHaveBeenCalled();
  await expect(service.run()).rejects.toMatchObject({ status: 503 });
});
