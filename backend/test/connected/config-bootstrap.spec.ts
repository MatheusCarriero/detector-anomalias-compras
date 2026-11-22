import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// Real Vitest configuration + collection, NEVER execution of test callbacks.
// A preload blocks sockets in the controller and every thread worker as a
// second boundary. Only synthetic credentials enter these short-lived children.
it.each(['comparability-read-only', 'p4-comparability-write'])(
  'collects %s with the real restricted configuration, without globals or network', operation => {
    const temporary = mkdtempSync(join(tmpdir(), 'p4-config-offline-'));
    const guard = join(temporary, 'guard.mjs');
    writeFileSync(guard, `import { Socket, Server } from 'node:net';
      import { writeSync } from 'node:fs';
      let attempts = 0;
      const refuse = () => { attempts++; throw Error('OFFLINE_NETWORK_FORBIDDEN'); };
      Socket.prototype.connect = refuse; Server.prototype.listen = refuse;
      process.on('exit', () => {
        writeSync(2, attempts ? 'OFFLINE_NETWORK_ATTEMPT\\n' : 'OFFLINE_GUARD_OK\\n');
      });`);
    const env: NodeJS.ProcessEnv = {};
    for (const [key, value] of Object.entries(process.env)) {
      if (/^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|TMPDIR|HOME|USERPROFILE|LOCALAPPDATA|APPDATA)$/i.test(key)) env[key] = value;
    }
    Object.assign(env, {
      DB_TEST_CONFIRM: 'synthetic-only', DB_TEST_HOST: '127.0.0.1', DB_TEST_PORT: '5432',
      DB_TEST_DATABASE: 'synthetic_p4_comparability_test', DB_TEST_RUNTIME: 'detector_runtime',
      DB_TEST_RUNTIME_URL: 'postgresql://detector_runtime:FAKE@127.0.0.1:5432/synthetic_p4_comparability_test',
      DB_TEST_TLS: 'local-plaintext', DB_TEST_OPERATION: operation, CONNECTED_TEST_RUNNER: 'bounded-v1',
      ...(operation.endsWith('write') ? { DB_TEST_WRITE_CONFIRM: 'p4-comparability/1.0:disposable-only' } : {}),
    });
    const preload = pathToFileURL(guard).href;
    const script = `
      console.error = () => {}; console.warn = () => {};
      const { createVitest } = await import('vitest/node');
      let ctx;
      try {
        ctx = await createVitest('test', { config: 'vitest.config.connected.ts', watch: false,
          execArgv: ['--import', ${JSON.stringify(preload)}] });
        await ctx.collect();
        const files = ctx.state.getFiles();
        const errors = [...ctx.state.getUnhandledErrors(), ...files.flatMap(f => f.result?.errors ?? [])];
        console.log(JSON.stringify({ files: files.length, tests: files.reduce((n,f)=>n+f.tasks.length,0),
          errors: errors.length, missingIt: errors.some(e=>e.name==='ReferenceError' && e.message==='it is not defined'),
          globals: ctx.config.globals }));
      } catch { console.log(JSON.stringify({ bootstrapFailure: true })); process.exitCode = 1; }
      finally { await ctx?.close(); }
    `;
    try {
      const child = spawnSync(process.execPath, ['--import', preload, '--input-type=module', '--eval', script], {
        cwd: fileURLToPath(new URL('../../', import.meta.url)), env, encoding: 'utf8', timeout: 20000,
        maxBuffer: 256 * 1024, windowsHide: true, shell: false,
      });
      // Never print raw stderr or a driver/configuration stack in a failed assertion.
      const json = child.stdout.split(/\r?\n/).find(line => line.startsWith('{'));
      expect(json ? JSON.parse(json) : { missingResult: true }).toEqual({ files: 1, tests: 1, errors: 0, missingIt: false, globals: false });
      expect(child.status).toBe(0);
      expect(child.stderr.includes('OFFLINE_GUARD_OK')).toBe(true);
      expect(child.stderr.includes('OFFLINE_NETWORK_ATTEMPT')).toBe(false);
      expect(child.stderr.includes('MODULE_INIT')).toBe(false);
    } finally {
      // Only the freshly allocated owned directory; never the shared temp root.
      rmSync(temporary, { recursive: true, force: true });
    }
  }, 30000,
);
