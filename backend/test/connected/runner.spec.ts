import { EventEmitter } from 'node:events';
import { Socket } from 'node:net';
import { spawn } from 'node:child_process';
import { syntheticEnvironment } from './fixtures.js';

vi.mock('node:child_process', () => ({ spawn: vi.fn() }));

describe('connected runner protections (offline)', () => {
  let child: EventEmitter & { kill: ReturnType<typeof vi.fn>; unref: ReturnType<typeof vi.fn> };
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    child = Object.assign(new EventEmitter(), { kill: vi.fn(() => true), unref: vi.fn() });
    vi.mocked(spawn).mockReturnValue(child as unknown as ReturnType<typeof spawn>);
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
      throw new Error('Offline network guard');
    });
  });
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

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
    expect(options).toMatchObject({ shell: false, stdio: 'ignore', windowsHide: true });
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
    await vi.advanceTimersByTimeAsync(45000);
    expect(child.kill).toHaveBeenCalledExactlyOnceWith('SIGKILL');
    child.emit('close', 0, null);
    expect(await result).toBe(1);
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
    expect(log).toHaveBeenCalledWith('DB_TEST: child termination not confirmed; manual inspection required');
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
