import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { readConnectedTarget, selectConnectedSuite } from '../test/connected/config.ts';
import { diagnosticCode, diagnosticError, parseDiagnostic } from '../test/connected/diagnostics.mjs';

const backend = fileURLToPath(new URL('../', import.meta.url));
const vitest = fileURLToPath(new URL('../node_modules/vitest/vitest.mjs', import.meta.url));

export async function runConnectedTests(args, env) {
  let phase = 'SUITE_REFUSED';
  try {
    if (args.length !== 1) throw diagnosticError('SUITE_REFUSED');
    selectConnectedSuite(args[0]);
    phase = 'CONFIG_TARGET';
    const target = readConnectedTarget(env);
    selectConnectedSuite(args[0], target.operation);
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
    phase = 'CHILD_SPAWN';
    return await new Promise((resolve) => {
      // A single thread worker lives inside this owned Node process, not a fork tree.
      const child = spawn(process.execPath, [vitest, 'run', '--config', 'vitest.config.connected.ts'], {
        cwd: backend, env: childEnv, shell: false, stdio: ['ignore', 'ignore', 'pipe'], windowsHide: true,
      });
      let timedOut = false;
      let settled = false;
      let confirmation;
      let deadline;
      let lastStage;
      let line = '';
      let oversized = false;
      const failures = new Set();
      // Consume stderr without forwarding it. Retain only fixed protocol codes;
      // cap each line so raw driver output cannot grow an unbounded buffer.
      child.stderr.on('data', (chunk) => {
        if (settled) return;
        for (const character of chunk.toString('utf8')) {
          if (character === '\n') {
            const diagnostic = oversized ? undefined : parseDiagnostic(line);
            if (diagnostic?.kind === 'stage') lastStage = diagnostic.code;
            if (diagnostic?.kind === 'failure') failures.add(diagnostic.code);
            line = ''; oversized = false;
          } else if (line.length < 128 && !oversized) {
            line += character;
          } else { line = ''; oversized = true; }
        }
      });
      child.stderr.on('error', () => { failures.add('CHILD_EXIT'); });
      const finish = (code, reason) => {
        if (settled) return;
        settled = true;
        clearTimeout(deadline);
        clearTimeout(confirmation);
        process.removeListener('SIGINT', interrupt);
        process.removeListener('SIGTERM', interrupt);
        child.stderr.destroy();
        if (reason) failures.add(reason);
        if (code !== 0) {
          if (failures.size) {
            for (const failure of failures) {
              const includeStage = lastStage && ['CHILD_TIMEOUT', 'CHILD_SIGNAL',
                'CHILD_TERMINATION_UNCONFIRMED'].includes(failure);
              console.error(`DB_TEST: ${failure}${includeStage ? `; last_stage=${lastStage}` : ''}`);
            }
          } else {
            console.error(lastStage
              ? `DB_TEST: CHILD_EXIT; last_stage=${lastStage}`
              : 'DB_TEST: CHILD_BOOTSTRAP');
          }
        }
        resolve(code);
      };
      const stop = (reason) => {
        if (timedOut) return;
        timedOut = true;
        failures.add(reason);
        clearTimeout(deadline);
        // A forced stop is failure; it is never evidence of graceful rollback/cleanup.
        confirmation = setTimeout(() => {
          child.unref();
          finish(1, 'CHILD_TERMINATION_UNCONFIRMED');
        }, 5000);
        try { child.kill('SIGKILL'); }
        catch { /* The confirmation deadline reports the unconfirmed termination. */ }
      };
      const interrupt = () => stop('CHILD_SIGNAL');
      deadline = setTimeout(() => stop('CHILD_TIMEOUT'), 45000);
      process.on('SIGINT', interrupt);
      process.on('SIGTERM', interrupt);
      child.once('error', () => { if (!timedOut) finish(1, 'CHILD_SPAWN'); });
      child.once('close', (code, signal) => {
        finish(!timedOut && !failures.size && code === 0 && signal === null ? 0 : 1,
          !timedOut && signal !== null ? 'CHILD_SIGNAL' : undefined);
      });
    });
  } catch (error) {
    console.error(`DB_TEST: ${diagnosticCode(error, phase)}`);
    return 1;
  }
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  const result = await runConnectedTests(process.argv.slice(2), process.env);
  console.log(result === 0
    ? 'DB_TEST: selected read-only checks completed'
    : 'DB_TEST: refused or failed; no success/cleanup claim. Review configuration and controlled diagnostics.');
  process.exitCode = result;
}
