import { EventEmitter } from 'node:events';
import { Socket } from 'node:net';
import { spawn } from 'node:child_process';
import { PassThrough } from 'node:stream';
import { syntheticEnvironment } from './fixtures.js';

vi.mock('node:child_process', () => ({ spawn: vi.fn() }));

describe('connected runner protections (offline)', () => {
  let child: EventEmitter & { kill: ReturnType<typeof vi.fn>; unref: ReturnType<typeof vi.fn>; stderr: PassThrough };
  let log: ReturnType<typeof vi.spyOn>;
  let networkAttempts = 0;
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    child = Object.assign(new EventEmitter(), { kill: vi.fn(() => true), unref: vi.fn(), stderr: new PassThrough() });
    log = vi.spyOn(console, 'error').mockImplementation(() => {});
    networkAttempts = 0;
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
      networkAttempts += 1;
      throw new Error('Offline network guard');
    });
  });
  afterEach(() => {
    try { expect(networkAttempts).toBe(0); }
    finally { vi.useRealTimers(); vi.restoreAllMocks(); }
  });

  it('reports a fixed configuration category without spawning or exposing configuration', async () => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    expect(await runConnectedTests(['identity-permissions'], {})).toBe(1);
    expect(log).toHaveBeenCalledWith('DB_TEST: CONFIG_MISSING');
    expect(spawn).not.toHaveBeenCalled();
  });
  it.each([
    ['catalog-permissions', 'identity-read-only'], ['identity-permissions', 'catalog-read-only'],
  ])('refuses mismatched suite %s and operation %s before spawning', async (group, operation) => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    expect(await runConnectedTests([group], { ...syntheticEnvironment, DB_TEST_OPERATION: operation })).toBe(1);
    expect(spawn).not.toHaveBeenCalled();
    expect(log).toHaveBeenCalledWith('DB_TEST: SUITE_REFUSED');
  });
  it('passes only the explicitly chosen catalog operation to the bounded child', async () => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    const result = runConnectedTests(['catalog-permissions'], { ...syntheticEnvironment, DB_TEST_OPERATION: 'catalog-read-only' });
    expect(spawn).toHaveBeenCalledOnce();
    expect(vi.mocked(spawn).mock.calls[0][2]?.env?.DB_TEST_OPERATION).toBe('catalog-read-only');
    child.stderr.write('DB_TEST_DIAGNOSTIC_V1 failure CATALOG_FUNCTIONS\n');
    child.stderr.write('driver leaked secret_catalog\n');
    child.emit('close', 1, null);
    expect(await result).toBe(1);
    expect(log.mock.calls).toEqual([['DB_TEST: CATALOG_FUNCTIONS']]);
  });
  it('reports only allowlisted child diagnostics, including a secondary cleanup failure', async () => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    const result = runConnectedTests(['identity-permissions'], syntheticEnvironment);
    child.stderr.write(`driver error ${syntheticEnvironment.DB_TEST_RUNTIME_URL}\n    at secret-file:99\n`);
    child.stderr.write('DB_TEST_DIAGNOSTIC_V1 stage MODULE_');
    child.stderr.write('INIT\nDB_TEST_DIAGNOSTIC_V1 failure MODULE_INIT\n');
    child.stderr.write('DB_TEST_DIAGNOSTIC_V1 failure RESOURCE_CLEANUP_HOOK\n');
    child.emit('close', 1, null);
    expect(await result).toBe(1);
    expect(log.mock.calls).toEqual([
      ['DB_TEST: MODULE_INIT'], ['DB_TEST: RESOURCE_CLEANUP_HOOK'],
    ]);
  });
  it('rejects oversized/malformed output and reports the last known safe stage', async () => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    const result = runConnectedTests(['identity-permissions'], syntheticEnvironment);
    child.stderr.write('DB_TEST_DIAGNOSTIC_V1 stage IDENTITY_QUERY\n');
    child.stderr.write(`${'X'.repeat(2048)}DB_TEST_DIAGNOSTIC_V1 failure MODULE_INIT\n`);
    child.stderr.write('DB_TEST_DIAGNOSTIC_V1 failure password=secret\n');
    child.stderr.write('DB_TEST_DIAGNOSTIC_V1 failure MODULE_INIT secret\n');
    child.emit('close', 1, null);
    expect(await result).toBe(1);
    expect(log.mock.calls).toEqual([['DB_TEST: CHILD_EXIT; last_stage=IDENTITY_QUERY']]);
  });
  it('identifies bootstrap failure when the child emits no diagnostic frame', async () => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    const result = runConnectedTests(['identity-permissions'], syntheticEnvironment);
    child.stderr.write(`Error: ${syntheticEnvironment.DB_TEST_RUNTIME_URL}`);
    child.emit('close', 1, null);
    expect(await result).toBe(1);
    expect(log).toHaveBeenCalledWith('DB_TEST: CHILD_BOOTSTRAP');
  });
  it('does not accept zero exit code after a reported failure', async () => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    const result = runConnectedTests(['identity-permissions'], syntheticEnvironment);
    child.stderr.write('DB_TEST_DIAGNOSTIC_V1 failure IDENTITY_SCHEMA\n');
    child.emit('close', 0, null);
    expect(await result).toBe(1);
  });

  it('does not spawn a process during import', async () => {
    await import('../../scripts/run-connected-tests.mjs');
    expect(spawn).not.toHaveBeenCalled();
  });
  it.each([{}, { DATABASE_URL: syntheticEnvironment.DB_TEST_RUNTIME_URL }])(
    'rejects invalid environment before spawning', async (env) => {
      const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
      expect(await runConnectedTests(['identity-permissions'], env)).toBe(1);
      expect(spawn).not.toHaveBeenCalled();
    },
  );
  it.each(['NODE_DEBUG', 'NODE_DEBUG_NATIVE'])('refuses %s before passing credentials to spawn', async (key) => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    expect(await runConnectedTests(['identity-permissions'], { ...syntheticEnvironment, [key]: 'child_process' })).toBe(1);
    expect(spawn).not.toHaveBeenCalled();
  });
  it.each([[], ['sql-contracts'], ['concurrency'], ['identity-permissions', '--anything']].map((args) => ({ args })))(
    'refuses unsupported stages and argument injection (case %#)', async ({ args }) => {
      const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
      expect(await runConnectedTests(args, syntheticEnvironment)).toBe(1);
      expect(spawn).not.toHaveBeenCalled();
    },
  );
  it('runs a fixed Node/Vitest command with an allowlisted child environment and no raw output', async () => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    const result = runConnectedTests(['identity-permissions'], {
      ...syntheticEnvironment, Path: 'fixture-path', SystemRoot: 'fixture-system',
      UNRELATED_SECRET: 'never-inherit', npm_lifecycle_script: 'never-run',
    });
    expect(spawn).toHaveBeenCalledOnce();
    const [binary, args, options] = vi.mocked(spawn).mock.calls[0]!;
    expect(binary).toBe(process.execPath);
    expect(args).toEqual([expect.stringMatching(/vitest[\\/]vitest\.mjs$/),
      'run', '--config', 'vitest.config.connected.ts']);
    expect(options).toMatchObject({ shell: false, stdio: ['ignore', 'ignore', 'pipe'], windowsHide: true });
    expect(options?.env?.UNRELATED_SECRET).toBeUndefined();
    expect(options?.env?.npm_lifecycle_script).toBeUndefined();
    expect(options?.env?.DATABASE_URL).toBeUndefined();
    expect(options?.env?.DB_TEST_RUNTIME_URL).toBe(syntheticEnvironment.DB_TEST_RUNTIME_URL);
    child.emit('close', 0, null);
    expect(await result).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });
  it('does not report success after a failed child', async () => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    const result = runConnectedTests(['identity-permissions'], syntheticEnvironment);
    child.emit('close', 1, null);
    expect(await result).toBe(1);
  });
  it('kills only its own direct child at the deadline and never reports a late success', async () => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    const result = runConnectedTests(['identity-permissions'], syntheticEnvironment);
    child.stderr.write('DB_TEST_DIAGNOSTIC_V1 stage TRANSACTION_START\n');
    await vi.advanceTimersByTimeAsync(45000);
    expect(child.kill).toHaveBeenCalledExactlyOnceWith('SIGKILL');
    child.emit('close', 0, null);
    expect(await result).toBe(1);
    expect(log).toHaveBeenCalledWith('DB_TEST: CHILD_TIMEOUT; last_stage=TRANSACTION_START');
  });
  it('sanitizes spawn failure', async () => {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    const result = runConnectedTests(['identity-permissions'], syntheticEnvironment);
    child.emit('error', new Error(syntheticEnvironment.DB_TEST_RUNTIME_URL));
    expect(await result).toBe(1);
    expect(vi.getTimerCount()).toBe(0);
  });
  it.each([true, false])('bounds termination confirmation even when kill returns %s and close never arrives', async (killed) => {
    child.kill.mockReturnValue(killed);
    const log = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    let result: number | undefined;
    void runConnectedTests(['identity-permissions'], syntheticEnvironment).then((code) => { result = code; });
    await vi.advanceTimersByTimeAsync(50000);
    expect(result).toBe(1);
    expect(child.unref).toHaveBeenCalledOnce();
    expect(log).toHaveBeenCalledWith('DB_TEST: CHILD_TERMINATION_UNCONFIRMED');
    expect(child.stderr.destroyed).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
  it.each(['SIGINT', 'SIGTERM'])('stops its own child on %s and removes signal handlers', async (signal) => {
    const on = vi.spyOn(process, 'on');
    const listenersBefore = process.listenerCount(signal);
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    const result = runConnectedTests(['identity-permissions'], syntheticEnvironment);
    const registered = on.mock.calls.find(([event]) => event === signal);
    expect(registered).toBeDefined();
    (registered![1] as () => void)();
    expect(child.kill).toHaveBeenCalledExactlyOnceWith('SIGKILL');
    child.emit('close', 0, null);
    expect(await result).toBe(1);
    expect(process.listenerCount(signal)).toBe(listenersBefore);
    expect(vi.getTimerCount()).toBe(0);
  });
});
