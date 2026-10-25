import { Socket } from 'node:net';
import { syntheticEnvironment } from './fixtures.js';

const fake = vi.hoisted(() => ({
  connect: vi.fn(), disconnect: vi.fn(), query: vi.fn(), execute: vi.fn(),
  transaction: vi.fn(), adapter: vi.fn(), client: vi.fn(),
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
      body({ $executeRaw: fake.execute, $queryRaw: fake.query }));
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
    await expect(inspectRuntimeIdentity()).rejects.toThrow(/^DB_TEST: identity inspection failed$/);
    expect(fake.query).toHaveBeenCalledOnce();
    expect(fake.disconnect).toHaveBeenCalledOnce();
    expect(process.env.DATABASE_URL).toBeUndefined();
  });
  it('reports cleanup failure rather than success', async () => {
    fake.disconnect.mockRejectedValue(new Error('secret'));
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toThrow(/^DB_TEST: resource cleanup failed$/);
    await expect(inspectRuntimeIdentity()).rejects.toThrow(/^DB_TEST: harness unusable after cleanup failure$/);
    expect(fake.connect).toHaveBeenCalledOnce();
  });
  it('closes after failed initialization and preserves the original sanitized failure', async () => {
    fake.connect.mockRejectedValue(new Error('secret'));
    fake.disconnect.mockRejectedValue(new Error('other-secret'));
    const { inspectRuntimeIdentity } = await import('./harness.js');
    await expect(inspectRuntimeIdentity()).rejects.toThrow(/^DB_TEST: identity inspection failed$/);
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
      await expect(inspectRuntimeIdentity()).rejects.toThrow(/^DB_TEST: concurrent harness use refused$/);
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
    expect(String(await result)).toBe('Error: DB_TEST: resource cleanup failed');
    expect(process.env.DATABASE_URL).toBeUndefined();
    expect(process.env.PGSSLMODE).toBeUndefined();
    await expect(inspectRuntimeIdentity()).rejects.toThrow(/^DB_TEST: harness unusable after cleanup failure$/);
    expect(fake.connect).toHaveBeenCalledOnce();
  });
});
