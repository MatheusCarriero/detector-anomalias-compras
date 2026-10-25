import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { readConnectedTarget, selectConnectedSuite } from '../test/connected/config.ts';

const backend = fileURLToPath(new URL('../', import.meta.url));
const vitest = fileURLToPath(new URL('../node_modules/vitest/vitest.mjs', import.meta.url));

export async function runConnectedTests(args, env) {
  try {
    if (args.length !== 1) throw new Error();
    selectConnectedSuite(args[0]);
    const target = readConnectedTarget(env);
    const childEnv = {};
    // Do not inherit owner credentials, debug settings, Node preload hooks or PG*.
    for (const [key, value] of Object.entries(env)) {
      if (/^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|TMPDIR|HOME|USERPROFILE|LOCALAPPDATA|APPDATA)$/i.test(key)) childEnv[key] = value;
    }
    Object.assign(childEnv, {
      DB_TEST_CONFIRM: 'synthetic-only', DB_TEST_HOST: target.host,
      DB_TEST_PORT: String(target.port), DB_TEST_DATABASE: target.database,
      DB_TEST_RUNTIME: target.runtimeRole, DB_TEST_RUNTIME_URL: target.runtimeUrl,
      DB_TEST_TLS: target.tls, DB_TEST_OPERATION: target.operation,
      CONNECTED_TEST_RUNNER: 'bounded-v1',
    });
    return await new Promise((resolve) => {
      // A single thread worker lives inside this owned Node process, not a fork tree.
      const child = spawn(process.execPath, [vitest, 'run', '--config', 'vitest.config.connected.ts'], {
        cwd: backend, env: childEnv, shell: false, stdio: 'ignore', windowsHide: true,
      });
      let timedOut = false;
      let confirmation;
      let deadline;
      const finish = (code) => {
        clearTimeout(deadline);
        clearTimeout(confirmation);
        process.removeListener('SIGINT', stop);
        process.removeListener('SIGTERM', stop);
        resolve(code);
      };
      const stop = () => {
        if (timedOut) return;
        timedOut = true;
        clearTimeout(deadline);
        // A forced stop is failure; it is never evidence of graceful rollback/cleanup.
        confirmation = setTimeout(() => {
          child.unref();
          console.error('DB_TEST: child termination not confirmed; manual inspection required');
          finish(1);
        }, 5000);
        try { child.kill('SIGKILL'); }
        catch { /* The confirmation deadline reports the unconfirmed termination. */ }
      };
      deadline = setTimeout(stop, 45000);
      process.on('SIGINT', stop);
      process.on('SIGTERM', stop);
      child.once('error', () => { if (!timedOut) finish(1); });
      child.once('close', (code, signal) => {
        finish(!timedOut && code === 0 && signal === null ? 0 : 1);
      });
    });
  } catch { return 1; }
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const result = await runConnectedTests(process.argv.slice(2), process.env);
  console.log(result === 0
    ? 'DB_TEST: read-only identity checks completed'
    : 'DB_TEST: refused or failed; no success/cleanup claim. Review configuration and controlled diagnostics.');
  process.exitCode = result;
}
