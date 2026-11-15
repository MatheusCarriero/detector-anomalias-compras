import { EventEmitter } from 'node:events';
import { catalog, failure, packet, preparationRequest, prepared, protocol, runPacket, runResult, inferenceProtocol } from '../../test/fixtures/procurement-demo.js';
import { ProcurementDemoService } from './procurement-demo.service.js';

type Completion = (error: Error | null, stdout: string, stderr: string) => void;
const mock = vi.hoisted(() => ({ execFile: vi.fn() }));
vi.mock('node:child_process', () => ({ execFile: mock.execFile }));

describe('Procurement Python bridge (offline)', () => {
  let service: ProcurementDemoService;
  let complete: Completion;
  let stdin: EventEmitter & { end: ReturnType<typeof vi.fn> };
  let kill: ReturnType<typeof vi.fn>;
  let child: EventEmitter;
  beforeEach(() => {
    service = new ProcurementDemoService();
    stdin = Object.assign(new EventEmitter(), { end: vi.fn() });
    kill = vi.fn().mockReturnValue(true);
    child = new EventEmitter();
    mock.execFile.mockReset().mockImplementation((_file, _args, _options, done: Completion) => {
      complete = (error, stdout, stderr) => { done(error, stdout, stderr); child.emit('close'); };
      return Object.assign(child, { stdin, kill });
    });
  });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllEnvs(); });

  it('uses fixed isolated paths, UTF-8, bounded output and closes stdin', async () => {
    vi.stubEnv('DATABASE_URL', 'private'); vi.stubEnv('PYTHONPATH', 'untrusted');
    const pending = service.catalog();
    const [file, args, options] = mock.execFile.mock.calls[0];
    expect(file).toMatch(/[\\/]\.venv[\\/](Scripts[\\/]python.exe|bin[\\/]python)$/);
    expect(args.slice(0, 4)).toEqual(['-I', '-B', '-X', 'utf8']);
    expect(args[4]).toMatch(/[\\/]ml[\\/]procurement_v2[\\/]demo_runner.py$/);
    expect(options).toMatchObject({ shell: false, windowsHide: true, encoding: 'utf8', maxBuffer: 65536, killSignal: 'SIGKILL' });
    expect(Object.keys(options.env).every(key => ['SystemRoot', 'WINDIR', 'TEMP', 'TMP'].includes(key))).toBe(true);
    const input = stdin.end.mock.calls[0][0] as string;
    expect(Buffer.byteLength(input, 'utf8')).toBeLessThanOrEqual(1024);
    expect(JSON.parse(input)).toEqual({ protocol, action: 'catalog', request: { contract: 'procurement-demo/1.0', source_sha256: preparationRequest().source_sha256 } });
    expect(stdin.end.mock.calls[0][1]).toBe('utf8');
    complete(null, packet(catalog()), '');
    await expect(pending).resolves.toEqual(catalog());
  });
  it.each([false, true])('returns preparation without scoring (unavailable=%s)', async unavailable => {
    const req = preparationRequest(unavailable);
    const pending = service.prepare(req);
    expect(JSON.parse(stdin.end.mock.calls[0][0] as string)).toEqual({ protocol, action: 'prepare', request: req });
    complete(null, packet(prepared(unavailable)), '');
    await expect(pending).resolves.toEqual(prepared(unavailable));
  });
  it('rejects untrusted inputs before spawning', async () => {
    await expect(service.prepare({ ...preparationRequest(), path: 'untrusted' })).rejects.toThrow('PROCUREMENT_INVALID_REQUEST');
    expect(mock.execFile).not.toHaveBeenCalled();
    await expect(service.run({ ...preparationRequest(), features: [1, 2, 3] })).rejects.toThrow('PROCUREMENT_INVALID_REQUEST');
    expect(mock.execFile).not.toHaveBeenCalled();
  });
  it.each([false, true])('runs via the same bounded executor (unavailable=%s)', async unavailable => {
    const req = preparationRequest(unavailable);
    const pending = service.run(req);
    expect(JSON.parse(stdin.end.mock.calls[0][0] as string)).toEqual({ protocol: inferenceProtocol, action: 'run', request: req });
    complete(null, runPacket(runResult(unavailable)), '');
    await expect(pending).resolves.toEqual(runResult(unavailable));
  });
  it('shares a lock between both actions until process completion', async () => {
    const pending = service.catalog();
    await expect(service.prepare(preparationRequest())).rejects.toThrow('PROCUREMENT_BUSY');
    await expect(service.run(preparationRequest())).rejects.toThrow('PROCUREMENT_BUSY');
    expect(mock.execFile).toHaveBeenCalledOnce();
    complete(null, packet(catalog()), ''); await pending;
    const second = service.prepare(preparationRequest());
    complete(null, packet(prepared()), ''); await second;
    expect(mock.execFile).toHaveBeenCalledTimes(2);
  });
  it('times out, kills once and retains the lock until close', async () => {
    vi.useFakeTimers();
    const pending = service.run(preparationRequest());
    const rejected = expect(pending).rejects.toThrow('PROCUREMENT_TIMEOUT');
    await vi.advanceTimersByTimeAsync(30000);
    expect(kill).toHaveBeenCalledExactlyOnceWith('SIGKILL');
    await expect(service.catalog()).rejects.toThrow('PROCUREMENT_TERMINATION_UNCONFIRMED');
    complete(Object.assign(new Error('private'), { signal: 'SIGKILL', killed: true }), '', 'private');
    await rejected;
    expect(vi.getTimerCount()).toBe(0);
  });
  it.each([
    [{ code: 'ENOENT' }, 'PROCUREMENT_EXECUTOR_UNAVAILABLE'],
    [{ code: 'EACCES' }, 'PROCUREMENT_EXECUTOR_UNAVAILABLE'],
    [{ code: 'ERR_CHILD_PROCESS_STDIO_MAXBUFFER', killed: true }, 'PROCUREMENT_OUTPUT_LIMIT'],
    [{ signal: 'SIGTERM', killed: true }, 'PROCUREMENT_UNEXPECTED_EXIT'],
    [{ code: 17 }, 'PROCUREMENT_UNEXPECTED_EXIT'],
  ])('sanitizes process error %j', async (attributes, expected) => {
    const pending = service.catalog();
    complete(Object.assign(new Error('private paths and secrets'), attributes), 'private', 'private');
    await expect(pending).rejects.toThrow(expected);
  });
  it.each([
    [2, failure('invalid_request', 'CLI_REQUEST'), 'PROCUREMENT_INVALID_REQUEST'],
    [1, failure('technical_error', 'CLI_SOURCE_HASH'), 'PROCUREMENT_SOURCE_HASH'],
    [1, packet(catalog()), 'PROCUREMENT_INVALID_RESPONSE'],
    [0, '{private', 'PROCUREMENT_INVALID_RESPONSE'],
    [0, 'x'.repeat(65537), 'PROCUREMENT_OUTPUT_LIMIT'],
  ] as const)('validates CLI exit %s and output', async (code, output, expected) => {
    const pending = service.catalog();
    complete(code ? Object.assign(new Error('private'), { code }) : null, output, '');
    await expect(pending).rejects.toThrow(expected);
  });
  it('does not forward stderr', async () => {
    const pending = service.catalog(); complete(null, packet(catalog()), 'private');
    await expect(pending).rejects.toThrow('PROCUREMENT_EXECUTION_FAILED');
  });
  it('handles synchronous spawn failure and releases the lock', async () => {
    mock.execFile.mockImplementation(() => { throw new Error('private'); });
    await expect(service.catalog()).rejects.toThrow('PROCUREMENT_EXECUTOR_UNAVAILABLE');
    await expect(service.catalog()).rejects.toThrow('PROCUREMENT_EXECUTOR_UNAVAILABLE');
  });
  it.each(['event', 'throw'])('handles stdin failure via %s and waits for close', async mode => {
    if (mode === 'throw') stdin.end.mockImplementation(() => { throw new Error('private'); });
    const pending = service.catalog();
    if (mode === 'event') stdin.emit('error', new Error('private'));
    expect(kill).toHaveBeenCalledWith('SIGKILL');
    await expect(service.catalog()).rejects.toThrow('PROCUREMENT_TERMINATION_UNCONFIRMED');
    complete(Object.assign(new Error('private'), { signal: 'SIGKILL' }), '', '');
    await expect(pending).rejects.toThrow('PROCUREMENT_INPUT_FAILED');
  });
  it('shutdown stops waiting without claiming process closure, refusing new work', async () => {
    const pending = service.catalog();
    const rejected = expect(pending).rejects.toThrow('PROCUREMENT_STOPPING');
    let closed = false;
    const closing = service.onModuleDestroy().then(() => { closed = true; });
    await closing; expect(closed).toBe(true);
    expect(kill).toHaveBeenCalledWith('SIGKILL');
    await expect(service.prepare(preparationRequest())).rejects.toThrow('PROCUREMENT_STOPPING');
    complete(Object.assign(new Error('private'), { signal: 'SIGKILL' }), '', '');
    await rejected; await closing; expect(closed).toBe(true);
  });
  it.each(['false', 'throw', 'true'])('bounds HTTP and shutdown when kill=%s and close is absent', async mode => {
    vi.useFakeTimers();
    if (mode === 'throw') kill.mockImplementation(() => { throw new Error('private kill'); });
    else kill.mockReturnValue(mode === 'true');
    const pending = service.catalog();
    const rejected = expect(pending).rejects.toThrow('PROCUREMENT_TIMEOUT');
    await vi.advanceTimersByTimeAsync(30000);
    await rejected;
    expect(vi.getTimerCount()).toBe(0);
    child.emit('exit', 1); // Exit is not close: inherited pipes may still be open.
    await expect(service.catalog()).rejects.toThrow('PROCUREMENT_TERMINATION_UNCONFIRMED');
    await service.onModuleDestroy(); await service.onModuleDestroy();
    expect(kill).toHaveBeenCalledOnce();
    expect(child.listenerCount('close')).toBe(1); // Only late-cleanup observer remains.
    complete(Object.assign(new Error('private'), { signal: 'SIGKILL' }), '', '');
    expect(child.listenerCount('close')).toBe(0);
    expect(stdin.listenerCount('error')).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });
  it('accepts new work only after late close', async () => {
    vi.useFakeTimers();
    const pending = service.catalog(); const rejected = expect(pending).rejects.toThrow('PROCUREMENT_TIMEOUT');
    await vi.advanceTimersByTimeAsync(30000); await rejected;
    complete(null, packet(catalog()), '');
    const next = service.catalog();
    await expect(service.catalog()).rejects.toThrow('PROCUREMENT_BUSY');
    complete(null, packet(catalog()), ''); await next;
    expect(kill).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });
  it('bounds shutdown before the deadline even when close never arrives', async () => {
    vi.useFakeTimers(); kill.mockReturnValue(false);
    const pending = service.catalog();
    const rejected = expect(pending).rejects.toThrow('PROCUREMENT_STOPPING');
    await service.onModuleDestroy(); await rejected;
    await service.onModuleDestroy();
    stdin.emit('error', new Error('private late stdin'));
    expect(kill).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
    await expect(service.run(preparationRequest())).rejects.toThrow('PROCUREMENT_STOPPING');
    child.emit('close');
    expect(stdin.listenerCount('error')).toBe(0);
    expect(child.listenerCount('close')).toBe(0);
  });
  it('settles a close without a callback and removes only its own listeners', async () => {
    vi.useFakeTimers();
    const otherListener = vi.fn(); stdin.on('error', otherListener);
    const pending = service.catalog();
    const rejected = expect(pending).rejects.toThrow('PROCUREMENT_UNEXPECTED_EXIT');
    child.emit('close'); await rejected;
    expect(stdin.listeners('error')).toEqual([otherListener]);
    expect(child.listenerCount('close')).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });
});
