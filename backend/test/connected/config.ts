import { diagnosticCode, diagnosticError } from './diagnostics.mjs';

const required = [
  'DB_TEST_CONFIRM', 'DB_TEST_HOST', 'DB_TEST_PORT', 'DB_TEST_DATABASE',
  'DB_TEST_RUNTIME', 'DB_TEST_RUNTIME_URL', 'DB_TEST_TLS', 'DB_TEST_OPERATION',
];

export function readConnectedTarget(env: NodeJS.ProcessEnv) {
  try {
    if (required.some((key) => !env[key])) throw diagnosticError('CONFIG_MISSING');
    for (const [key, value] of Object.entries(env)) {
      const upper = key.toUpperCase();
      if (value && (
        (upper.startsWith('DB_TEST_') && !required.includes(key)) ||
        /^(PG.*|DATABASE_URL|DIRECT_URL|SHADOW_DATABASE_URL|NODE_OPTIONS|NODE_DEBUG|NODE_DEBUG_NATIVE|NODE_TLS_REJECT_UNAUTHORIZED|DEBUG|CI)$/.test(upper)
      )) throw diagnosticError('CONFIG_CONFLICT');
    }
    const host = env.DB_TEST_HOST!;
    const database = env.DB_TEST_DATABASE!;
    const runtimeUrl = env.DB_TEST_RUNTIME_URL!;
    const portText = env.DB_TEST_PORT!;
    if (
      env.DB_TEST_CONFIRM !== 'synthetic-only' ||
      env.DB_TEST_OPERATION !== 'identity-read-only' ||
      env.DB_TEST_TLS !== 'local-plaintext' ||
      env.DB_TEST_RUNTIME !== 'detector_runtime' ||
      !['127.0.0.1', '[::1]'].includes(host) ||
      !/^[1-9][0-9]{0,4}$/.test(portText) || Number(portText) > 65535 ||
      !/^synthetic_[a-z0-9_]+$/.test(database) || database.length > 63
    ) throw diagnosticError('CONFIG_TARGET');
    const url = new URL(runtimeUrl);
    const password = decodeURIComponent(url.password);
    if (
      !['postgres:', 'postgresql:'].includes(url.protocol) ||
      url.hostname !== host || url.port !== portText ||
      decodeURIComponent(url.pathname) !== `/${database}` ||
      decodeURIComponent(url.username) !== 'detector_runtime' ||
      !password || Array.from(runtimeUrl + password).some((character) =>
        character.charCodeAt(0) <= 32 || character.charCodeAt(0) === 127) ||
      url.search || url.hash
    ) throw diagnosticError('CONFIG_URL');
    return Object.freeze({
      host, port: Number(portText), database, runtimeUrl,
      runtimeRole: 'detector_runtime' as const,
      operation: 'identity-read-only' as const,
      tls: 'local-plaintext' as const,
    });
  } catch (error) {
    // Never attach URL, password, parser message or cause.
    throw diagnosticError(diagnosticCode(error, 'CONFIG_URL'));
  }
}

export type ConnectedTarget = ReturnType<typeof readConnectedTarget>;

export function selectConnectedSuite(group: string) {
  if (group !== 'identity-permissions') {
    throw diagnosticError('SUITE_REFUSED');
  }
  return 'test/connected/identity-permissions/*.integration.test.ts';
}

export function connectedTestOptions(env: NodeJS.ProcessEnv) {
  readConnectedTarget(env);
  if (env.CONNECTED_TEST_RUNNER !== 'bounded-v1') {
    throw diagnosticError('RUNNER_REQUIRED');
  }
  return {
    include: [selectConnectedSuite('identity-permissions')],
    pool: 'threads' as const, maxWorkers: 1, fileParallelism: false,
    retry: 0, passWithNoTests: false, testTimeout: 15000, hookTimeout: 5000,
  };
}
