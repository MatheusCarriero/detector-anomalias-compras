import { spawn } from 'node:child_process';
import { Socket } from 'node:net';
import { syntheticEnvironment } from './fixtures.js';

vi.mock('node:child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:child_process')>();
  return { ...actual, spawn: vi.fn(actual.spawn) };
});

it('transports safe diagnostics from a real worker, suppressing raw output without running Vitest or a driver', async () => {
  const actual = await vi.importActual<typeof import('node:child_process')>('node:child_process');
  const log = vi.spyOn(console, 'error').mockImplementation(() => {});
  const socket = vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
    throw new Error('Offline network guard');
  });
  let exitCode: number | null | undefined;
  let fixtureOutput = '';
  const diagnosticsUrl = new URL('./diagnostics.mjs', import.meta.url).href;
  // Replace only the child workload. Never launch the connected Vitest command.
  const workload = `
    import { Worker } from 'node:worker_threads';
    import { Socket } from 'node:net';
    let attempts = 0;
    Socket.prototype.connect = () => { attempts++; throw new Error('No network'); };
    const worker = new Worker(${JSON.stringify(`
      import { Socket } from 'node:net';
      import { parentPort } from 'node:worker_threads';
      import { writeSync } from 'node:fs';
      let attempts = 0;
      Socket.prototype.connect = () => { attempts++; throw new Error('No network'); };
      import(${JSON.stringify(diagnosticsUrl)}).then(({ reportDiagnostic }) => {
        reportDiagnostic('stage', 'IDENTITY_QUERY');
        writeSync(2, 'raw driver password-canary stack-canary');
        reportDiagnostic('failure', 'IDENTITY_QUERY');
        reportDiagnostic('failure', 'RESOURCE_CLEANUP_HOOK');
        parentPort.postMessage(attempts);
      });
    `)}, { eval: true });
    let workerAttempts;
    worker.on('message', (count) => { workerAttempts = count; });
    worker.on('exit', (code) => {
      process.exitCode = code === 0 && attempts === 0 && workerAttempts === 0 ? 1 : 97;
    });
  `;
  vi.mocked(spawn).mockImplementation((_binary, _args, options) => {
    const child = actual.spawn(process.execPath, ['--input-type=module', '--eval', workload], options!);
    child.on('exit', (code) => { exitCode = code; });
    child.stderr?.on('data', (chunk: Buffer) => { fixtureOutput += chunk.toString('utf8'); });
    return child;
  });
  try {
    const { runConnectedTests } = await import('../../scripts/run-connected-tests.mjs');
    expect(await runConnectedTests(['identity-permissions'], syntheticEnvironment)).toBe(1);
    expect(exitCode).toBe(1); // Both subprocess/worker guards observed zero socket attempts.
    expect(fixtureOutput).toContain('DB_TEST_DIAGNOSTIC_V1 failure IDENTITY_QUERY');
    expect(log.mock.calls).toEqual([
      ['DB_TEST: IDENTITY_QUERY'], ['DB_TEST: RESOURCE_CLEANUP_HOOK'],
    ]);
    expect(socket).not.toHaveBeenCalled();
  } finally { vi.restoreAllMocks(); }
}, 15000);
