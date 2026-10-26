import { Socket } from 'node:net';
import { connectedTestOptions, readConnectedTarget, selectConnectedSuite } from './config.js';
import { syntheticEnvironment as valid } from './fixtures.js';

describe('connected test configuration (offline)', () => {
  let attempts = 0;
  beforeEach(() => {
    attempts = 0;
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
      attempts += 1;
      throw new Error('Offline network guard');
    });
  });
  afterEach(() => {
    expect(attempts).toBe(0);
    vi.restoreAllMocks();
  });

  it('accepts an explicit matching synthetic runtime target', () => {
    expect(readConnectedTarget(valid)).toMatchObject({
      host: '127.0.0.1', port: 5432,
      database: 'synthetic_stage0_fixture', runtimeRole: 'detector_runtime',
      operation: 'identity-read-only', tls: 'local-plaintext',
    });
  });
  it.each(Object.keys(valid))('requires %s without a fallback', (key) => {
    const env: NodeJS.ProcessEnv = { ...valid };
    delete env[key];
    expect(() => readConnectedTarget(env)).toThrow(/DB_TEST/);
  });
  it.each([
    ['DB_TEST_CONFIRM', 'yes'], ['DB_TEST_HOST', 'localhost'],
    ['DB_TEST_HOST', 'production.example'], ['DB_TEST_PORT', '0'],
    ['DB_TEST_PORT', '65536'], ['DB_TEST_PORT', '05432'],
    ['DB_TEST_DATABASE', 'production'], ['DB_TEST_DATABASE', 'synthetic_'],
    ['DB_TEST_DATABASE', `synthetic_${'a'.repeat(60)}`],
    ['DB_TEST_RUNTIME', 'postgres'], ['DB_TEST_RUNTIME', 'detector_migrator'],
    ['DB_TEST_TLS', 'no-verify'], ['DB_TEST_TLS', ''],
    ['DB_TEST_OPERATION', 'contracts'], ['DB_TEST_OPERATION', 'concurrency'],
    ['DATABASE_URL', valid.DB_TEST_RUNTIME_URL],
    ['DB_TEST_MIGRATION_URL', 'must-not-be-inherited'],
    ['DB_TEST_UNRECOGNIZED', 'typo'], ['PGOPTIONS', '-c role=postgres'],
    ['PGSSLMODE', 'no-verify'], ['PGSERVICE', 'production'],
    ['NODE_OPTIONS', '--import=unexpected.mjs'], ['NODE_TLS_REJECT_UNAUTHORIZED', '0'],
    ['CI', 'true'], ['DEBUG', '*'], ['NODE_DEBUG', 'child_process'], ['NODE_DEBUG_NATIVE', '*'],
  ])('rejects unsafe setting %s (case %#)', (key, value) => {
    expect(() => readConnectedTarget({ ...valid, [key]: value })).toThrow(/DB_TEST/);
  });
  it.each([
    'not-a-url', valid.DB_TEST_RUNTIME_URL.replace('postgresql:', 'https:'),
    valid.DB_TEST_RUNTIME_URL.replace(':FAKE-password', ''),
    valid.DB_TEST_RUNTIME_URL.replace('FAKE-password', '%invalid'),
    valid.DB_TEST_RUNTIME_URL.replace('FAKE-password', '%00'),
    valid.DB_TEST_RUNTIME_URL.replace('detector_runtime:', 'postgres:'),
    valid.DB_TEST_RUNTIME_URL.replace('5432', '5433'),
    valid.DB_TEST_RUNTIME_URL.replace('127.0.0.1', '127.0.0.2'),
    valid.DB_TEST_RUNTIME_URL.replace('synthetic_stage0_fixture', 'synthetic_other'),
    `${valid.DB_TEST_RUNTIME_URL}?schema=app`, `${valid.DB_TEST_RUNTIME_URL}?options=anything`,
    `${valid.DB_TEST_RUNTIME_URL}#fragment`, `\n${valid.DB_TEST_RUNTIME_URL}`,
  ])('rejects an invalid URL without leaking it (case %#)', (url) => {
    let caught: unknown;
    try { readConnectedTarget({ ...valid, DB_TEST_RUNTIME_URL: url }); }
    catch (error) { caught = error; }
    expect(caught).toBeInstanceOf(Error);
    expect(String(caught)).toMatch(/DB_TEST/);
    expect(String(caught)).not.toContain('FAKE-password');
    expect(String(caught)).not.toContain(url);
    expect(caught).not.toHaveProperty('cause');
  });
  it('accepts literal IPv6 loopback without DNS', () => {
    expect(readConnectedTarget({ ...valid, DB_TEST_HOST: '[::1]',
      DB_TEST_RUNTIME_URL: valid.DB_TEST_RUNTIME_URL.replace('127.0.0.1', '[::1]'),
    })).toMatchObject({ host: '[::1]' });
  });
  it.each([
    ['CONFIG_MISSING', { ...valid, DB_TEST_HOST: undefined }],
    ['CONFIG_CONFLICT', { ...valid, PGPASSWORD: 'private-sentinel' }],
    ['CONFIG_TARGET', { ...valid, DB_TEST_OPERATION: 'private-sentinel' }],
    ['CONFIG_URL', { ...valid, DB_TEST_RUNTIME_URL: 'private-sentinel' }],
  ])('identifies %s without reporting supplied values', (code, env) => {
    let caught: unknown;
    try { readConnectedTarget(env); } catch (error) { caught = error; }
    expect(caught).toMatchObject({ diagnosticCode: code });
    expect(String(caught)).not.toContain('private-sentinel');
    expect(caught).not.toHaveProperty('cause');
  });
  it('distinguishes absent bounded runner from an unapproved suite', () => {
    let runner: unknown;
    let suite: unknown;
    try { connectedTestOptions(valid); } catch (error) { runner = error; }
    try { selectConnectedSuite('sql-contracts'); } catch (error) { suite = error; }
    expect(runner).toMatchObject({ diagnosticCode: 'RUNNER_REQUIRED' });
    expect(suite).toMatchObject({ diagnosticCode: 'SUITE_REFUSED' });
  });
});
