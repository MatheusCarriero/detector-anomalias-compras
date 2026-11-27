import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import net from 'node:net';
import { fileURLToPath } from 'node:url';
import { provisionConfig, runProvision } from '../src/purchases/purchase-provision-cli.js';

const env = { P4_PROVISION_CONFIRM: 'synthetic-p4-catalog/1.0', P4_PROVISION_TLS: 'local-plaintext',
  P4_PROVISION_URL: 'postgresql://detector_migrator:fixture-secret@127.0.0.1:5432/synthetic_detector_anomalias_compras_test' };
const args = ['--execute-synthetic-p4'];
const apiEnv = { ...env, P4_PROVISION_PROFILE: 'p4-api-comparability-v1',
  P4_PROVISION_CONFIRM: 'synthetic-p4-api-comparability-catalog/1.0' };
const file = fileURLToPath(new URL('../src/purchases/purchase-provision-cli.ts', import.meta.url));
function dependencies() {
  const bytes = Buffer.from('synthetic migration fixture');
  const migrations = [{ name: 'fixture', hash: createHash('sha256').update(bytes).digest('hex') }];
  const provisionP4 = vi.fn().mockResolvedValue({ contract: 'p4-provision/1.0' });
  const client = { connect: vi.fn().mockResolvedValue(undefined), end: vi.fn().mockResolvedValue(undefined), on: vi.fn(),
    query: vi.fn().mockResolvedValue({ rows: [] }) };
  return { client, provisionP4, loadCore: vi.fn().mockResolvedValue({ provisionP4, P4_MIGRATIONS: migrations }),
    createClient: vi.fn().mockResolvedValue(client), readMigration: vi.fn().mockResolvedValue(bytes), nodeVersion: '24.20.0' };
}

describe('P4 provisioning CLI guards (offline)', () => {
  it('requires the new API profile confirmation and checks all three files before invoking its transaction', async () => {
    expect(provisionConfig(args, apiEnv)).toMatchObject({ host: '127.0.0.1', port: 5432,
      database: 'synthetic_detector_anomalias_compras_test', user: 'detector_migrator', ssl: false });
    const d = dependencies(); const core = await d.loadCore();
    d.loadCore.mockResolvedValue({ ...core, P4_COMPARABILITY_MIGRATIONS: Array.from({ length: 3 }, (_, i) => ({ ...core.P4_MIGRATIONS[0], name: `fixture-${i}` })) });
    expect((await runProvision(args, apiEnv, d)).ok).toBe(true);
    expect(d.readMigration.mock.calls.map(call => call[0])).toEqual(['fixture-0', 'fixture-1', 'fixture-2']);
    expect(d.provisionP4).toHaveBeenCalledExactlyOnceWith(d.client, 'p4-api-comparability-v1');
    expect(d.client.end).toHaveBeenCalledTimes(1);
  });
  it.each([undefined, '', 'synthetic-p4-catalog/1.0', 'synthetic-p4-comparability-catalog/1.0'])
  ('rejects absent or legacy confirmation for the API profile (%#)', async confirmation => {
    const d = dependencies();
    expect(await runProvision(args, { ...apiEnv, P4_PROVISION_CONFIRM: confirmation }, d)).toEqual({ ok: false, code: 'CONFIG_REQUIRED' });
    expect(d.loadCore).not.toHaveBeenCalled(); expect(d.createClient).not.toHaveBeenCalled();
  });
  it.each([undefined, 'p4-v1', 'comparability-v1'])('does not reuse the new confirmation in an old/default profile (%#)', async profile => {
    const d = dependencies();
    expect((await runProvision(args, { ...apiEnv, P4_PROVISION_PROFILE: profile }, d)).ok).toBe(false);
    expect(d.createClient).not.toHaveBeenCalled();
  });
  it.each([
    env.P4_PROVISION_URL.replace('synthetic_detector_anomalias_compras_test', 'synthetic_p4_comparability_test'),
    env.P4_PROVISION_URL.replace('detector_migrator:', 'detector_runtime:'),
    env.P4_PROVISION_URL.replace('127.0.0.1', 'localhost'), env.P4_PROVISION_URL.replace('5432', '5433'),
  ])('rejects altered API provisioning connection coordinates (%#)', async url => {
    const d = dependencies();
    expect(await runProvision(args, { ...apiEnv, P4_PROVISION_URL: url }, d)).toEqual({ ok: false, code: 'CONFIG_URL' });
    expect(d.createClient).not.toHaveBeenCalled();
  });
  it.each(['missing', 'two-files', 'bad-third-checksum'])('rejects invalid local API migration artifacts before constructing a client: %s', async scenario => {
    const d = dependencies(); const core = await d.loadCore();
    if (scenario !== 'missing') d.loadCore.mockResolvedValue({ ...core, P4_COMPARABILITY_MIGRATIONS:
      Array.from({ length: scenario === 'two-files' ? 2 : 3 }, (_, i) => ({ ...core.P4_MIGRATIONS[0], name: `fixture-${i}` })) });
    if (scenario === 'bad-third-checksum') d.readMigration.mockResolvedValueOnce(Buffer.from('synthetic migration fixture'))
      .mockResolvedValueOnce(Buffer.from('synthetic migration fixture')).mockResolvedValueOnce(Buffer.from('changed'));
    expect(await runProvision(args, apiEnv, d)).toEqual({ ok: false, code: 'LOCAL_ARTIFACT' });
    expect(d.createClient).not.toHaveBeenCalled();
  });
  it('requires a distinct profile, target and confirmation for comparability provisioning', async () => {
    const cfg = { ...env, P4_PROVISION_PROFILE: 'comparability-v1', P4_PROVISION_CONFIRM: 'synthetic-p4-comparability-catalog/1.0',
      P4_PROVISION_URL: env.P4_PROVISION_URL.replace('synthetic_detector_anomalias_compras_test', 'synthetic_p4_comparability_test') };
    expect(provisionConfig(args, cfg).database).toBe('synthetic_p4_comparability_test');
    for (const [key, value] of [['P4_PROVISION_PROFILE', undefined], ['P4_PROVISION_PROFILE', 'unknown'],
      ['P4_PROVISION_CONFIRM', env.P4_PROVISION_CONFIRM], ['P4_PROVISION_URL', env.P4_PROVISION_URL]] as const) {
      const d = dependencies(); expect((await runProvision(args, { ...cfg, [key]: value }, d)).ok).toBe(false);
      expect(d.client.connect).not.toHaveBeenCalled();
    }
    const d = dependencies(); const core = await d.loadCore();
    d.loadCore.mockResolvedValue({ ...core, P4_COMPARABILITY_MIGRATIONS: Array.from({ length: 3 }, (_, i) => ({ ...core.P4_MIGRATIONS[0], name: `fixture-${i}` })) });
    expect((await runProvision(args, cfg, d)).ok).toBe(true);
    expect(d.readMigration).toHaveBeenCalledTimes(3); expect(d.provisionP4).toHaveBeenCalledExactlyOnceWith(d.client, 'comparability-v1');
    const bad = dependencies();
    expect(await runProvision(args, cfg, bad)).toEqual({ ok: false, code: 'LOCAL_ARTIFACT' });
    expect(bad.client.connect).not.toHaveBeenCalled();
  });
  beforeEach(() => {
    vi.spyOn(net.Socket.prototype, 'connect').mockImplementation(() => { throw new Error('Network forbidden in offline tests'); });
  });
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

  it('imports without a connection and rejects accidental CLI invocation', () => {
    const child = spawnSync(process.execPath, [file], { encoding: 'utf8', timeout: 5000 });
    expect(child.status).toBe(1);
    expect(JSON.parse(child.stdout)).toEqual({ ok: false, code: 'OPT_IN_REQUIRED' });
    expect(child.stderr).toBe('');
  });
  it('requires opt-in before loading application or driver code', async () => {
    const d = dependencies();
    expect(await runProvision([], env, d)).toEqual({ ok: false, code: 'OPT_IN_REQUIRED' });
    expect(d.loadCore).not.toHaveBeenCalled(); expect(d.createClient).not.toHaveBeenCalled();
  });
  it('supplies only explicit fixed connection options, with bounded timeouts', () => {
    const config = provisionConfig(args, env);
    expect(config).toMatchObject({ host: '127.0.0.1', port: 5432, user: 'detector_migrator',
      database: 'synthetic_detector_anomalias_compras_test', ssl: false, password: 'fixture-secret',
      connectionTimeoutMillis: 3000, statement_timeout: 5000, query_timeout: 8000, idle_in_transaction_session_timeout: 8000 });
    expect('connectionString' in config).toBe(false);
  });
  it.each(['P4_PROVISION_CONFIRM', 'P4_PROVISION_TLS', 'P4_PROVISION_URL'])('refuses missing %s', async key => {
    const values = { ...env }; delete values[key as keyof typeof env]; const d = dependencies();
    expect((await runProvision(args, values, d)).ok).toBe(false); expect(d.createClient).not.toHaveBeenCalled();
  });
  it.each([undefined, '', 'true', 'synthetic-p4-catalog/1.0 ', 'synthetic-only'])
  ('requires the exact confirmation before loading code or constructing a connection (%#)', async confirmation => {
    const d = dependencies();
    expect(await runProvision(args, { ...env, P4_PROVISION_CONFIRM: confirmation }, d))
      .toEqual({ ok: false, code: 'CONFIG_REQUIRED' });
    expect(d.loadCore).not.toHaveBeenCalled(); expect(d.createClient).not.toHaveBeenCalled();
    expect(d.client.connect).not.toHaveBeenCalled(); expect(d.provisionP4).not.toHaveBeenCalled();
  });
  it.each(['PGHOST', 'PGPASSWORD', 'PGOPTIONS', 'DATABASE_URL', 'DB_TEST_RUNTIME_URL', 'CI', 'NODE_OPTIONS', 'DEBUG', 'P4_PROVISION_EXTRA'])
  ('refuses ambiguous inherited configuration %s', async key => {
    const d = dependencies();
    expect(await runProvision(args, { ...env, [key]: 'secret' }, d)).toEqual({ ok: false, code: 'CONFIG_CONFLICT' });
    expect(d.createClient).not.toHaveBeenCalled();
  });
  it.each([
    'not a URL', env.P4_PROVISION_URL.replace('127.0.0.1', 'localhost'), env.P4_PROVISION_URL.replace('5432', '5433'),
    env.P4_PROVISION_URL.replace('detector_migrator:', 'postgres:'), env.P4_PROVISION_URL.replace('detector_migrator:', 'detector_runtime:'),
    env.P4_PROVISION_URL.replace('synthetic_detector_anomalias_compras_test', 'production'),
    env.P4_PROVISION_URL + '?schema=app', env.P4_PROVISION_URL + '#fragment',
    env.P4_PROVISION_URL.replace('fixture-secret', ''), env.P4_PROVISION_URL.replace('fixture-secret', '%00'),
  ])('refuses a changed endpoint or URL shape without connecting (%#)', async url => {
    const d = dependencies(); const result = await runProvision(args, { ...env, P4_PROVISION_URL: url }, d);
    expect(result).toEqual({ ok: false, code: 'CONFIG_URL' }); expect(d.createClient).not.toHaveBeenCalled();
    expect(JSON.stringify(result)).not.toContain('fixture-secret');
  });
  it('checks local migration bytes before driver construction', async () => {
    const d = dependencies(); d.readMigration.mockResolvedValue(Buffer.from('changed'));
    expect(await runProvision(args, env, d)).toEqual({ ok: false, code: 'LOCAL_ARTIFACT' });
    expect(d.createClient).not.toHaveBeenCalled();
  });
  it('accepts only the same migration content across LF and CRLF checkouts', async () => {
    const d = dependencies(); const body = 'synthetic\nmigration\n';
    d.loadCore.mockResolvedValue({ provisionP4: d.provisionP4,
      P4_MIGRATIONS: [{ name: 'fixture', hash: createHash('sha256').update(body).digest('hex') }] });
    d.readMigration.mockResolvedValue(Buffer.from(body.replaceAll('\n', '\r\n')));
    expect((await runProvision(args, env, d)).ok).toBe(true);
    d.readMigration.mockResolvedValue(Buffer.from(body + '-- changed'));
    expect(await runProvision(args, env, d)).toEqual({ ok: false, code: 'LOCAL_ARTIFACT' });
    expect(d.client.connect).toHaveBeenCalledTimes(1);
  });
  it('refuses missing build artifacts and sanitizes their filesystem errors', async () => {
    const d = dependencies(); d.loadCore.mockRejectedValue(new Error('secret local path'));
    expect(await runProvision(args, env, d)).toEqual({ ok: false, code: 'LOCAL_ARTIFACT' });
    expect(d.createClient).not.toHaveBeenCalled();
  });
  it('refuses an unsupported Node version before loading the driver', async () => {
    const d = dependencies(); d.nodeVersion = '22.0.0';
    expect(await runProvision(args, env, d)).toEqual({ ok: false, code: 'NODE_VERSION' });
    expect(d.createClient).not.toHaveBeenCalled();
  });
  it('runs the prepared transaction once and closes its administrative connection', async () => {
    const d = dependencies(); expect(await runProvision(args, env, d)).toEqual({ ok: true, value: { contract: 'p4-provision/1.0' } });
    expect(d.client.connect).toHaveBeenCalledTimes(1); expect(d.provisionP4).toHaveBeenCalledExactlyOnceWith(d.client);
    expect(d.client.end).toHaveBeenCalledTimes(1);
  });
  it('closes on authentication failure without revealing driver diagnostics', async () => {
    const d = dependencies(); d.client.connect.mockRejectedValue(new Error(env.P4_PROVISION_URL));
    expect(await runProvision(args, env, d)).toEqual({ ok: false, code: 'CONNECT' });
    expect(d.provisionP4).not.toHaveBeenCalled(); expect(d.client.end).toHaveBeenCalledTimes(1);
  });
  it('preserves only allowlisted failure codes from the transaction', async () => {
    const d = dependencies(); d.provisionP4.mockRejectedValue(new Error('P4_PROVISION_CONFLICT'));
    expect(await runProvision(args, env, d)).toEqual({ ok: false, code: 'CONFLICT' });
    d.provisionP4.mockRejectedValue(new Error('P4_PROVISION_SECRET password'));
    expect(await runProvision(args, env, d)).toEqual({ ok: false, code: 'DATABASE' });
  });
  it('does not report a failed disconnect as a successful rollback', async () => {
    const d = dependencies(); d.client.end.mockRejectedValue(new Error('secret'));
    expect(await runProvision(args, env, d)).toEqual({ ok: false, code: 'DISCONNECT', transaction: 'committed' });
  });
  it('bounds a stalled disconnect and preserves the commit outcome', async () => {
    vi.useFakeTimers(); const d = dependencies(); d.client.end.mockImplementation(() => new Promise(() => {}));
    const result = runProvision(args, env, d); await vi.advanceTimersByTimeAsync(3001);
    expect(await result).toEqual({ ok: false, code: 'DISCONNECT', transaction: 'committed' });
  });
  it('consumes asynchronous driver errors without exposing them or claiming success', async () => {
    const d = dependencies(); d.client.connect.mockImplementation(async () => { d.client.on.mock.calls[0][1](new Error('secret')); });
    expect(await runProvision(args, env, d)).toEqual({ ok: false, code: 'CONNECT' });
    expect(d.provisionP4).not.toHaveBeenCalled();
  });
});
