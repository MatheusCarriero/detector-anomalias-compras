import { Socket } from 'node:net';
import { syntheticEnvironment } from './fixtures.js';
import { catalogChecks } from './catalog-checks.js';
import { syntheticCatalog } from './catalog-fixtures.js';

const fake = vi.hoisted(() => ({
  connect: vi.fn(), disconnect: vi.fn(), query: vi.fn(), execute: vi.fn(),
  transaction: vi.fn(), adapter: vi.fn(), client: vi.fn(),
  write: vi.fn(), catalog: vi.fn(),
}));
vi.mock('node:fs', async (importOriginal) => ({
  ...await importOriginal<typeof import('node:fs')>(), writeSync: fake.write,
}));
vi.mock('@prisma/adapter-pg', () => ({ PrismaPg: class { constructor(...args: unknown[]) { fake.adapter(...args); } } }));
vi.mock('../../generated/prisma/client.js', () => ({ PrismaClient: class {
  constructor() { fake.client(); }
  $connect = fake.connect;
  $disconnect = fake.disconnect;
  $transaction = fake.transaction;
} }));

const identity = {
  database: 'synthetic_stage0_fixture', session_user: 'detector_runtime',
  current_user: 'detector_runtime', server_version: 180000,
  server_address: '127.0.0.1', server_port: 5432,
  search_path: 'app,pg_catalog', schema_usage: true, schema_create: false,
  superuser: false, create_db: false, create_role: false,
  replication: false, bypass_rls: false, tls: false,
};

// The first lazy Nest import can exceed Vitest's default 5s on Windows.
describe('Nest connected harness, with mocked driver and blocked network', { timeout: 20000 }, () => {
  let networkAttempts = 0;
  beforeEach(() => {
    vi.resetModules();
    vi.resetAllMocks();
    networkAttempts = 0;
    // Test fixtures replace any ambient database settings, without reading secrets.
    for (const key of Object.keys(process.env)) {
      if (/^(PG.*|DB_TEST_.*|DATABASE_URL|DIRECT_URL|SHADOW_DATABASE_URL|NODE_OPTIONS|NODE_DEBUG|NODE_DEBUG_NATIVE|NODE_TLS_REJECT_UNAUTHORIZED|DEBUG|CI)$/i.test(key)) vi.stubEnv(key, undefined);
    }
    for (const [key, value] of Object.entries(syntheticEnvironment)) vi.stubEnv(key, value);
    vi.stubEnv('CONNECTED_TEST_RUNNER', 'bounded-v1');
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
      networkAttempts += 1;
      throw new Error('Offline network guard');
    });
    fake.query.mockResolvedValue([identity]);
    fake.transaction.mockImplementation(async (body: (tx: unknown) => unknown) =>
      body({ $executeRaw: fake.execute, $queryRaw: fake.query, $queryRawUnsafe: fake.catalog }));
  });
  afterEach(() => {
    try { expect(networkAttempts).toBe(0); }
    finally { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllEnvs(); }
  });

  it('imports without constructing any adapter or starting the lifecycle', async () => {
    await import('./harness.js');
    expect(fake.adapter).not.toHaveBeenCalled();
    expect(fake.connect).not.toHaveBeenCalled();
  });
  it('requires a separately selected catalog operation before constructing the adapter', async () => {
    const { inspectRuntimeCatalog } = await import('./harness.js');
    await expect(inspectRuntimeCatalog()).rejects.toMatchObject({ diagnosticCode: 'SUITE_REFUSED' });
    expect(fake.adapter).not.toHaveBeenCalled();
    expect(fake.catalog).not.toHaveBeenCalled();
  });
  it('validates identity before catalogs within the same bounded read-only transaction', async () => {
    vi.stubEnv('DB_TEST_OPERATION', 'catalog-read-only');
    const fixture = syntheticCatalog();
    fake.catalog.mockImplementation(async (sql: string) => {
      const check = catalogChecks.find((c) => c.sql === sql);
      if (!check) throw new Error('Unexpected SQL');
      expect(fake.query).toHaveBeenCalledOnce();
      expect(fake.execute.mock.calls[0][0].join('')).toBe('SET TRANSACTION READ ONLY');
      return fixture[check.code];
    });
    const { inspectRuntimeCatalog } = await import('./harness.js');
    await expect(inspectRuntimeCatalog()).resolves.toMatchObject({ runtimeRole: 'detector_runtime' });
    expect(fake.transaction).toHaveBeenCalledExactlyOnceWith(expect.any(Function), {
      isolationLevel: 'ReadCommitted', maxWait: 3000, timeout: 10000,
    });
    expect(fake.catalog.mock.calls.map(([sql]) => sql)).toEqual(catalogChecks.map((c) => c.sql));
    expect(fake.disconnect).toHaveBeenCalledOnce();
    expect(process.env.DATABASE_URL).toBeUndefined();
    expect(process.env.PGSSLMODE).toBeUndefined();
  });
  it('never inspects catalogs after a failed identity comparison', async () => {
    vi.stubEnv('DB_TEST_OPERATION', 'catalog-read-only');
    fake.query.mockResolvedValue([{ ...identity, current_user: 'postgres' }]);
    const { inspectRuntimeCatalog } = await import('./harness.js');
    await expect(inspectRuntimeCatalog()).rejects.toMatchObject({ diagnosticCode: 'IDENTITY_USER' });
    expect(fake.catalog).not.toHaveBeenCalled();
    expect(fake.disconnect).toHaveBeenCalledOnce();
  });
  it.each(catalogChecks)('sanitizes catalog query failures at $code, closes and does not continue', async (check) => {
    vi.stubEnv('DB_TEST_OPERATION', 'catalog-read-only');
    const fixture = syntheticCatalog();
    fake.catalog.mockImplementation(async (sql: string) => {
      const current = catalogChecks.find((c) => c.sql === sql)!;
      if (current.code === check.code) throw new Error(`${syntheticEnvironment.DB_TEST_RUNTIME_URL} secret_catalog`);
      return fixture[current.code];
    });
    const { inspectRuntimeCatalog } = await import('./harness.js');
    await expect(inspectRuntimeCatalog()).rejects.toMatchObject({ diagnosticCode: check.code });
    expect(fake.catalog).toHaveBeenCalledTimes(catalogChecks.indexOf(check) + 1);
    expect(fake.disconnect).toHaveBeenCalledOnce();
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame)).join('');
    expect(frames).not.toMatch(/secret_catalog|FAKE-password|synthetic_stage0_fixture/);
    expect(frames).toContain('failure TX_ERROR_UNKNOWN');
    expect(frames).not.toContain('stage HARNESS_OK');
  });
  it('rejects invalid catalog metadata and restores the environment', async () => {
    vi.stubEnv('DB_TEST_OPERATION', 'catalog-read-only');
    fake.catalog.mockResolvedValue([{ ...syntheticCatalog().CATALOG_ROLES[0], no_memberships: false }]);
    const { inspectRuntimeCatalog } = await import('./harness.js');
    await expect(inspectRuntimeCatalog()).rejects.toMatchObject({ diagnosticCode: 'CATALOG_ROLES' });
    expect(fake.catalog).toHaveBeenCalledOnce();
    expect(fake.disconnect).toHaveBeenCalledOnce();
    expect(process.env.DATABASE_URL).toBeUndefined();
    expect(process.env.PGSSLMODE).toBeUndefined();
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame)).join('');
    expect(frames).not.toContain('failure TX_ERROR_UNKNOWN');
  });
  it('does not treat a catalog SQL syntax error as a legitimate permission rejection', async () => {
    vi.stubEnv('DB_TEST_OPERATION', 'catalog-read-only');
    fake.catalog.mockRejectedValue({ code: 'P2010', meta: { driverAdapterError: {
      cause: { kind: 'postgres', originalCode: '42601', message: 'PRIVATE_QUERY_SENTINEL' },
    } } });
    const { inspectRuntimeCatalog } = await import('./harness.js');
    await expect(inspectRuntimeCatalog()).rejects.toMatchObject({ diagnosticCode: 'CATALOG_ROLES' });
    expect(fake.catalog).toHaveBeenCalledOnce();
    expect(fake.disconnect).toHaveBeenCalledOnce();
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame)).join('');
    expect(frames).toContain('failure TX_ERROR_SQL_SYNTAX');
    expect(frames).not.toMatch(/PRIVATE_QUERY_SENTINEL|stage HARNESS_OK/);
  });
  it.each([false, true])('reports default ACL refusal without inventing a transaction error (cleanup failure: %s)', async (cleanupFails) => {
    vi.stubEnv('DB_TEST_OPERATION', 'catalog-read-only');
    const fixture = syntheticCatalog();
    fixture.CATALOG_DEFAULT_ACL[0].functions_safe = false;
    fake.catalog.mockImplementation(async (sql: string) => fixture[catalogChecks.find((c) => c.sql === sql)!.code]);
    if (cleanupFails) fake.disconnect.mockRejectedValue(new Error('PRIVATE_CLEANUP_SENTINEL'));
    const { inspectRuntimeCatalog } = await import('./harness.js');
    await expect(inspectRuntimeCatalog()).rejects.toMatchObject({ diagnosticCode: 'CATALOG_DEFAULT_ACL_FUNCTIONS' });
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame)).join('');
    expect(frames).toContain('failure CATALOG_DEFAULT_ACL_FUNCTIONS');
    expect(frames).not.toMatch(/failure TX_ERROR_|stage HARNESS_OK|PRIVATE_|FAKE-password/);
    expect(frames.includes('failure RESOURCE_CLEANUP_HOOK')).toBe(cleanupFails);
    expect(fake.transaction).toHaveBeenCalledOnce();
    expect(fake.disconnect).toHaveBeenCalledOnce();
    expect(process.env.DATABASE_URL).toBeUndefined();
    expect(process.env.PGSSLMODE).toBeUndefined();
    if (cleanupFails) await expect(inspectRuntimeCatalog()).rejects.toMatchObject({ diagnosticCode: 'HARNESS_UNUSABLE' });
  });
  it('does not let a spoofed diagnostic field hide an unknown query failure', async () => {
    vi.stubEnv('DB_TEST_OPERATION', 'catalog-read-only');
    fake.catalog.mockRejectedValue(Object.assign(new Error('PRIVATE_SENTINEL'), {
      diagnosticCode: 'CATALOG_DEFAULT_ACL_FUNCTIONS',
    }));
    const { inspectRuntimeCatalog } = await import('./harness.js');
    await expect(inspectRuntimeCatalog()).rejects.toMatchObject({ diagnosticCode: 'CATALOG_ROLES' });
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame)).join('');
    expect(frames).toContain('failure TX_ERROR_UNKNOWN');
    expect(frames).not.toMatch(/failure CATALOG_DEFAULT_ACL_FUNCTIONS|PRIVATE_|stage HARNESS_OK/);
  });
  it('rejects missing configuration before constructing the Nest provider', async () => {
    vi.stubEnv('DB_TEST_CONFIRM', undefined);
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toThrow(/DB_TEST/);
    expect(fake.adapter).not.toHaveBeenCalled();
  });
  it('rejects direct use without the bounded runner before creating the adapter', async () => {
    vi.stubEnv('CONNECTED_TEST_RUNNER', undefined);
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toThrow(/DB_TEST/);
    expect(fake.adapter).not.toHaveBeenCalled();
  });
  it('uses the real Nest module/provider lifecycle with a read-only bounded transaction', async () => {
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).resolves.toMatchObject({
      database: 'synthetic_stage0_fixture', runtimeRole: 'detector_runtime',
    });
    expect(fake.connect).toHaveBeenCalledOnce();
    expect(fake.disconnect).toHaveBeenCalledOnce();
    expect(fake.transaction).toHaveBeenCalledExactlyOnceWith(expect.any(Function), {
      isolationLevel: 'ReadCommitted', maxWait: 3000, timeout: 10000,
    });
    const statements = fake.execute.mock.calls.map(([strings]) => strings.join('?'));
    expect(statements).toEqual([
      'SET TRANSACTION READ ONLY',
      "SET LOCAL statement_timeout = '5s'",
      "SET LOCAL lock_timeout = '2s'",
      "SET LOCAL idle_in_transaction_session_timeout = '5s'",
    ]);
    expect(fake.query).toHaveBeenCalledOnce();
    expect(process.env.DATABASE_URL).toBeUndefined();
    expect(process.env.PGSSLMODE).toBeUndefined();
  });
  it.each([
    { target: '127.0.0.1', address: '127.0.0.1', cast: '127.0.0.1/32' },
    { target: '[::1]', address: '::1', cast: '::1/128' },
  ])('requests host-only PostgreSQL text for $target, preserving strict equality', async ({ target, address, cast }) => {
    vi.stubEnv('DB_TEST_HOST', target);
    vi.stubEnv('DB_TEST_RUNTIME_URL', syntheticEnvironment.DB_TEST_RUNTIME_URL.replace('127.0.0.1', target));
    // Documented PostgreSQL 18 semantics, not a live SQL execution:
    // https://www.postgresql.org/docs/18/functions-net.html
    // inet::text includes the mask; host(inet) returns only the address.
    fake.query.mockImplementation(async (strings: TemplateStringsArray) => {
      const sql = strings.join('?');
      if (sql.includes('pg_catalog.inet_server_addr()::text AS server_address')) {
        return [{ ...identity, server_address: cast }];
      }
      if (sql.includes('pg_catalog.host(pg_catalog.inet_server_addr()) AS server_address')) {
        return [{ ...identity, server_address: address }];
      }
      throw new Error('Unexpected address projection in offline fixture');
    });
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).resolves.toMatchObject({ runtimeRole: 'detector_runtime' });
    expect(fake.query).toHaveBeenCalledOnce();
    expect(fake.disconnect).toHaveBeenCalledOnce();
  });
  it.each([
    ['server_address', null, 'IDENTITY_ADDRESS_TYPE'],
    ['server_address', undefined, 'IDENTITY_ADDRESS_TYPE'],
    ['server_address', 2130706433, 'IDENTITY_ADDRESS_TYPE'],
    ['server_address', ['127.0.0.1'], 'IDENTITY_ADDRESS_TYPE'],
    ['server_address', '127.0.0.1/32', 'IDENTITY_ADDRESS_VALUE'],
    ['server_address', '127.0.0.1 ', 'IDENTITY_ADDRESS_VALUE'],
    ['server_address', '127.0.0.2', 'IDENTITY_ADDRESS_VALUE'],
    ['server_address', '::ffff:127.0.0.1', 'IDENTITY_ADDRESS_VALUE'],
    ['server_address', 'localhost', 'IDENTITY_ADDRESS_VALUE'],
    ['server_port', null, 'IDENTITY_PORT_TYPE'],
    ['server_port', undefined, 'IDENTITY_PORT_TYPE'],
    ['server_port', '5432', 'IDENTITY_PORT_TYPE'],
    ['server_port', 5432n, 'IDENTITY_PORT_TYPE'],
    ['server_port', true, 'IDENTITY_PORT_TYPE'],
    ['server_port', NaN, 'IDENTITY_PORT_VALUE'],
    ['server_port', Infinity, 'IDENTITY_PORT_VALUE'],
    ['server_port', 5432.5, 'IDENTITY_PORT_VALUE'],
    ['server_port', 0, 'IDENTITY_PORT_VALUE'],
    ['server_port', 65536, 'IDENTITY_PORT_VALUE'],
    ['server_port', 5433, 'IDENTITY_PORT_VALUE'],
  ])('rejects incompatible endpoint types or values without coercion (case %#)', async (key, value, code) => {
    fake.query.mockResolvedValue([{ ...identity, [key]: value }]);
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: code });
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame).trimStart()).join('');
    expect(frames).toContain(`DB_TEST_DIAGNOSTIC_V1 failure ${code}\n`);
    expect(frames).not.toMatch(/127\.0\.0\.|543[23]|FAKE-password|synthetic_stage0_fixture/);
    expect(fake.disconnect).toHaveBeenCalledOnce();
    expect(process.env.DATABASE_URL).toBeUndefined();
    expect(process.env.PGSSLMODE).toBeUndefined();
  });
  it.each([
    ['database', 'another_database'], ['session_user', 'postgres'],
    ['current_user', 'detector_migrator'], ['server_version', 170000],
    ['server_address', '10.0.0.1'], ['server_port', 5433],
    ['search_path', 'public'], ['schema_usage', false], ['schema_create', true],
    ['superuser', true], ['create_db', true], ['create_role', true],
    ['replication', true], ['bypass_rls', true], ['tls', true],
  ])('rejects effective identity mismatch in %s and closes the module', async (key, value) => {
    fake.query.mockResolvedValue([{ ...identity, [key]: value }]);
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toThrow(/DB_TEST/);
    expect(fake.disconnect).toHaveBeenCalledOnce();
  });
  it('redacts driver errors, closes resources and does not retry', async () => {
    fake.query.mockRejectedValue(new Error(syntheticEnvironment.DB_TEST_RUNTIME_URL));
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'IDENTITY_QUERY' });
    expect(fake.query).toHaveBeenCalledOnce();
    expect(fake.disconnect).toHaveBeenCalledOnce();
    expect(process.env.DATABASE_URL).toBeUndefined();
  });
  it('reports cleanup failure rather than success', async () => {
    fake.disconnect.mockRejectedValue(new Error('secret'));
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'RESOURCE_CLEANUP_HOOK' });
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'HARNESS_UNUSABLE' });
    expect(fake.connect).toHaveBeenCalledOnce();
  });
  it('closes after failed initialization and preserves the original sanitized failure', async () => {
    fake.connect.mockRejectedValue(new Error('secret'));
    fake.disconnect.mockRejectedValue(new Error('other-secret'));
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'MODULE_INIT' });
    expect(fake.query).not.toHaveBeenCalled();
    expect(fake.disconnect).toHaveBeenCalled();
  });
  it('refuses overlapping invocations before constructing another client', async () => {
    let release!: () => void;
    fake.connect.mockImplementation(() => new Promise<void>((resolve) => { release = resolve; }));
    const { inspectRuntimeIdentity } = await import('./harness.js');
    const first = inspectRuntimeIdentity();
    await vi.waitFor(() => expect(fake.connect).toHaveBeenCalledOnce());
    try {
      await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'HARNESS_BUSY' });
      expect(fake.client).toHaveBeenCalledOnce();
    } finally { release(); }
    await expect(first).resolves.toMatchObject({ runtimeRole: 'detector_runtime' });
    expect(fake.disconnect).toHaveBeenCalledOnce();
  });
  it('bounds a pending cleanup and prevents reuse without claiming the resource closed', async () => {
    fake.query.mockImplementation(async () => { vi.useFakeTimers(); return [identity]; });
    fake.disconnect.mockImplementation(() => new Promise<void>(() => {}));
    const { inspectRuntimeIdentity } = await import('./harness.js');
    const result = inspectRuntimeIdentity().catch((error: unknown) => error);
    await vi.waitFor(() => expect(fake.disconnect).toHaveBeenCalledOnce());
    await vi.advanceTimersByTimeAsync(3000);
    expect(await result).toMatchObject({ diagnosticCode: 'RESOURCE_CLEANUP_TIMEOUT' });
    expect(process.env.DATABASE_URL).toBeUndefined();
    expect(process.env.PGSSLMODE).toBeUndefined();
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'HARNESS_UNUSABLE' });
    expect(fake.connect).toHaveBeenCalledOnce();
  });

  it.each([
    ['provider', 'MODULE_COMPILE'], ['initialization', 'MODULE_INIT'],
    ['before-callback', 'TRANSACTION_START'], ['read-only', 'READ_ONLY_SETUP'],
    ['timeouts', 'SESSION_TIMEOUT_SETUP'], ['query', 'IDENTITY_QUERY'],
    ['commit', 'TRANSACTION_FINISH'],
  ])('identifies %s failure without exposing the original error', async (point, code) => {
    const secret = new Error(syntheticEnvironment.DB_TEST_RUNTIME_URL);
    secret.stack = 'PRIVATE_STACK_CANARY';
    if (point === 'provider') fake.adapter.mockImplementation(() => { throw secret; });
    if (point === 'initialization') fake.connect.mockRejectedValue(secret);
    if (point === 'before-callback') fake.transaction.mockRejectedValue(secret);
    if (point === 'read-only') fake.execute.mockRejectedValueOnce(secret);
    if (point === 'timeouts') fake.execute.mockResolvedValueOnce(0).mockRejectedValueOnce(secret);
    if (point === 'query') fake.query.mockRejectedValue(secret);
    if (point === 'commit') fake.transaction.mockImplementation(async (body: (tx: unknown) => unknown) => {
      await body({ $executeRaw: fake.execute, $queryRaw: fake.query });
      throw secret;
    });
    const { inspectRuntimeIdentity } = await import('./harness.js');
    const error = await inspectRuntimeIdentity().catch((failure: unknown) => failure);
    expect(error).toMatchObject({ diagnosticCode: code });
    expect(error).not.toHaveProperty('cause');
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame).trimStart());
    expect(frames).toContain(`DB_TEST_DIAGNOSTIC_V1 failure ${code}\n`);
    expect(frames).not.toContain('DB_TEST_DIAGNOSTIC_V1 stage HARNESS_OK\n');
    expect(frames.join('')).not.toMatch(/FAKE-password|postgresql:\/\/|PRIVATE_STACK_CANARY/);
  });

  it.each([
    ['P1001', 'TX_ERROR_UNREACHABLE'], ['P2028', 'TX_ERROR_API'],
    ['PRIVATE_CODE', 'TX_ERROR_UNKNOWN'],
  ])('reports pre-callback location separately from the structured error category (%s)', async (code, category) => {
    fake.transaction.mockRejectedValue(Object.assign(new Error('PRIVATE_URL_AND_STACK'), { code }));
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'TRANSACTION_START' });
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame).trimStart());
    expect(frames).toContain(`DB_TEST_DIAGNOSTIC_V1 failure ${category}\n`);
    expect(frames).not.toContain('DB_TEST_DIAGNOSTIC_V1 stage TRANSACTION_CALLBACK\n');
    expect(frames.join('')).not.toMatch(/PRIVATE_|FAKE-password|postgresql:\/\//);
    expect(fake.execute).not.toHaveBeenCalled();
    expect(fake.query).not.toHaveBeenCalled();
    expect(fake.transaction).toHaveBeenCalledOnce();
    expect(fake.disconnect).toHaveBeenCalledOnce();
  });
  it('marks callback entry and transaction resolution without claiming SQL success early', async () => {
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await inspectRuntimeIdentity();
    const stages = fake.write.mock.calls.map(([, frame]) => String(frame).trim());
    const ordered = ['TRANSACTION_START', 'TRANSACTION_CALLBACK', 'READ_ONLY_SETUP',
      'SESSION_TIMEOUT_SETUP', 'IDENTITY_QUERY', 'TRANSACTION_FINISH', 'TRANSACTION_RESOLVED',
      'IDENTITY_RESULT_SHAPE', 'RESOURCE_CLEANUP', 'HARNESS_OK'];
    const positions = ordered.map((stage) => stages.indexOf(`DB_TEST_DIAGNOSTIC_V1 stage ${stage}`));
    expect(positions.every((position, index) => position >= 0 && (index === 0 || position > positions[index - 1]!))).toBe(true);
  });
  it.each(['read-only', 'commit'])('retains %s location and SQLSTATE category independently', async (point) => {
    const cause = { kind: 'postgres', originalCode: '57014', originalMessage: 'PRIVATE_SENTINEL' };
    if (point === 'read-only') fake.execute.mockRejectedValueOnce({ code: 'P2010', meta: { driverAdapterError: { cause } } });
    else fake.transaction.mockImplementation(async (body: (tx: unknown) => unknown) => {
      await body({ $executeRaw: fake.execute, $queryRaw: fake.query });
      throw { name: 'DriverAdapterError', cause };
    });
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: point === 'read-only' ? 'READ_ONLY_SETUP' : 'TRANSACTION_FINISH' });
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame).trimStart());
    expect(frames).toContain('DB_TEST_DIAGNOSTIC_V1 failure TX_ERROR_CANCELLED\n');
    expect(frames).not.toContain('DB_TEST_DIAGNOSTIC_V1 stage TRANSACTION_RESOLVED\n');
    expect(frames.join('')).not.toContain('PRIVATE_SENTINEL');
    expect(fake.disconnect).toHaveBeenCalledOnce();
  });

  it.each([
    ['database', 'other', 'IDENTITY_DATABASE'],
    ['session_user', 'other', 'IDENTITY_USER'],
    ['current_user', 'other', 'IDENTITY_USER'],
    ['server_address', '10.0.0.1', 'IDENTITY_ADDRESS_VALUE'],
    ['server_port', '5432', 'IDENTITY_PORT_TYPE'],
    ['schema_usage', false, 'IDENTITY_SCHEMA'],
    ['schema_create', true, 'IDENTITY_SCHEMA'],
    ['superuser', true, 'IDENTITY_PRIVILEGES'],
    ['create_db', true, 'IDENTITY_PRIVILEGES'],
    ['create_role', true, 'IDENTITY_PRIVILEGES'],
    ['replication', true, 'IDENTITY_PRIVILEGES'],
    ['bypass_rls', true, 'IDENTITY_PRIVILEGES'],
    ['tls', true, 'IDENTITY_TRANSPORT'],
    ['server_version', '180000', 'IDENTITY_VERSION'],
    ['search_path', 'public', 'IDENTITY_SEARCH_PATH'],
  ])('classifies identity mismatch for %s without leaking returned values', async (key, value, code) => {
    fake.query.mockResolvedValue([{ ...identity, [key]: value, extra: 'PRIVATE_RESULT_CANARY' }]);
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: code });
    expect(fake.write.mock.calls.map(([, frame]) => String(frame).trimStart()).join('')).not.toContain('PRIVATE_RESULT_CANARY');
    expect(fake.disconnect).toHaveBeenCalledOnce();
  });

  it.each([null, {}, [], [null], [identity, identity]])('rejects malformed identity results with a fixed category (%j)', async (rows) => {
    fake.query.mockResolvedValue(rows);
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'IDENTITY_RESULT_SHAPE' });
  });

  it('reports primary and cleanup failures independently without claiming success', async () => {
    fake.query.mockRejectedValue(new Error('PRIVATE_QUERY_CANARY'));
    fake.disconnect.mockRejectedValue(new Error('PRIVATE_CLEANUP_CANARY'));
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'IDENTITY_QUERY' });
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame).trimStart());
    expect(frames).toContain('DB_TEST_DIAGNOSTIC_V1 failure IDENTITY_QUERY\n');
    expect(frames).toContain('DB_TEST_DIAGNOSTIC_V1 failure RESOURCE_CLEANUP_HOOK\n');
    expect(frames.join('')).not.toMatch(/PRIVATE_|HARNESS_OK/);
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'HARNESS_UNUSABLE' });
  });

  it('preserves a pre-callback failure and a failed cleanup as separate diagnostics', async () => {
    fake.transaction.mockRejectedValue({ code: 'P2028', message: 'PRIVATE_TRANSACTION_CANARY' });
    fake.disconnect.mockRejectedValue(new Error('PRIVATE_CLEANUP_CANARY'));
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'TRANSACTION_START' });
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame).trimStart());
    expect(frames).toContain('DB_TEST_DIAGNOSTIC_V1 failure TRANSACTION_START\n');
    expect(frames).toContain('DB_TEST_DIAGNOSTIC_V1 failure TX_ERROR_API\n');
    expect(frames).toContain('DB_TEST_DIAGNOSTIC_V1 failure RESOURCE_CLEANUP_HOOK\n');
    expect(frames.join('')).not.toMatch(/PRIVATE_|HARNESS_OK|TRANSACTION_CALLBACK/);
    expect(fake.execute).not.toHaveBeenCalled();
    expect(fake.transaction).toHaveBeenCalledOnce();
    expect(process.env.DATABASE_URL).toBeUndefined();
    expect(process.env.PGSSLMODE).toBeUndefined();
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'HARNESS_UNUSABLE' });
  });

  it('reports successful cleanup before harness completion', async () => {
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await inspectRuntimeIdentity();
    const frames = fake.write.mock.calls.map(([, frame]) => String(frame).trimStart());
    expect(frames.at(-1)).toBe('DB_TEST_DIAGNOSTIC_V1 stage HARNESS_OK\n');
    expect(frames).toContain('DB_TEST_DIAGNOSTIC_V1 stage RESOURCE_CLEANUP\n');
    expect(frames.some((frame) => frame.includes(' failure '))).toBe(false);
  });

  it('does not ignore a Nest initialization error logged without rejection', async () => {
    fake.connect.mockImplementationOnce(async () => {
      const { Logger } = await import('@nestjs/common');
      Logger.error('PRIVATE_LOG_CANARY');
    });
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toMatchObject({ diagnosticCode: 'MODULE_INIT' });
    expect(fake.query).not.toHaveBeenCalled();
    expect(fake.disconnect).toHaveBeenCalledOnce();
    expect(fake.write.mock.calls.map(([, frame]) => String(frame).trimStart()).join('')).not.toContain('PRIVATE_LOG_CANARY');
  });
});
