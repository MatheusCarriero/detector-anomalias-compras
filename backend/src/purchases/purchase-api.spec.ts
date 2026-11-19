import { Socket } from 'node:net';
import { validatePurchaseApiEnvironment, startPurchaseApi } from './purchase-api.js';

const factory = vi.hoisted(() => ({ create: vi.fn() }));
vi.mock('@nestjs/core', () => ({ NestFactory: factory }));
vi.mock('@prisma/adapter-pg', () => ({ PrismaPg: class { constructor() { throw new Error('Real adapter forbidden'); } } }));
const valid = {
  P4_API_CONFIRM: 'local-synthetic-p4/1.0', P4_API_TLS: 'local-plaintext',
  DATABASE_URL: 'postgresql://detector_runtime:FAKE@127.0.0.1:5432/synthetic_detector_anomalias_compras_test',
};
let attempts = 0;
beforeEach(() => {
  vi.clearAllMocks(); attempts = 0;
  vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => { attempts++; throw new Error('Offline network guard'); });
});
afterEach(() => { expect(attempts).toBe(0); vi.restoreAllMocks(); vi.unstubAllEnvs(); });

it('requires explicit local activation with the exact runtime database identity', () => {
  expect(() => validatePurchaseApiEnvironment(valid)).not.toThrow();
  for (const key of Object.keys(valid)) expect(() => validatePurchaseApiEnvironment({ ...valid, [key]: '' })).toThrow('P4_API_CONFIG');
});
it.each([
  ['P4_API_CONFIRM', 'yes'], ['P4_API_TLS', 'require'], ['CI', 'true'], ['PGSSLMODE', 'disable'],
  ['P4_API_UNKNOWN', 'yes'], ['DB_TEST_RUNTIME_URL', 'secret'], ['P4_PROVISION_URL', 'secret'],
  ['NODE_OPTIONS', '--import=secret'], ['NODE_DEBUG', '*'], ['PGUSER', 'postgres'], ['DIRECT_URL', 'secret'],
])('refuses conflicting or unsafe environment %s', (key, value) => {
  expect(() => validatePurchaseApiEnvironment({ ...valid, [key]: value })).toThrow('P4_API_CONFIG');
});
it.each([
  valid.DATABASE_URL.replace('detector_runtime', 'detector_migrator'), valid.DATABASE_URL.replace('127.0.0.1', 'localhost'),
  valid.DATABASE_URL.replace('5432', '5433'), valid.DATABASE_URL.replace('_test', '_other'),
  `${valid.DATABASE_URL}?schema=app`, `${valid.DATABASE_URL}#secret`, valid.DATABASE_URL.replace(':FAKE', ''),
  valid.DATABASE_URL.replace('FAKE', '%00'), ` ${valid.DATABASE_URL}`, 'private-url',
])('sanitizes invalid connection configuration %#', url => {
  let failure: unknown;
  try { validatePurchaseApiEnvironment({ ...valid, DATABASE_URL: url }); } catch (error) { failure = error; }
  expect(failure).toBeInstanceOf(Error); expect(String(failure)).toBe('Error: P4_API_CONFIG');
  expect(failure).not.toHaveProperty('cause');
});

function environment() {
  for (const key of Object.keys(process.env)) if (/^(PG.*|P4_.*|DB_TEST_.*|DATABASE_URL|DIRECT_URL|SHADOW_DATABASE_URL|NODE_OPTIONS|NODE_DEBUG.*|NODE_TLS_REJECT_UNAUTHORIZED|DEBUG|CI)$/i.test(key)) vi.stubEnv(key, undefined);
  for (const [key, value] of Object.entries(valid)) vi.stubEnv(key, value);
}
function appDouble() {
  const http = { disable: vi.fn(), set: vi.fn() };
  return { use: vi.fn(), useBodyParser: vi.fn(), useGlobalFilters: vi.fn(),
    getHttpAdapter: () => ({ getInstance: () => http }),
    enableShutdownHooks: vi.fn(), listen: vi.fn(), close: vi.fn().mockResolvedValue(undefined), http };
}
it('refuses startup before Nest and before any driver without valid config', async () => {
  environment(); vi.stubEnv('P4_API_CONFIRM', undefined);
  await expect(startPurchaseApi()).rejects.toThrow('P4_API_CONFIG');
  expect(factory.create).not.toHaveBeenCalled();
});
it('binds only the fixed loopback endpoint without inheriting PORT or importing the demos', async () => {
  environment(); vi.stubEnv('PORT', '0'); const app = appDouble();
  factory.create.mockResolvedValue(app);
  await startPurchaseApi();
  expect(factory.create).toHaveBeenCalledWith(expect.any(Function), { logger: false, abortOnError: false, bodyParser: false });
  expect(app.listen).toHaveBeenCalledExactlyOnceWith(3002, '127.0.0.1');
  expect(app.http.set).toHaveBeenCalledWith('trust proxy', false);
  expect(app.useBodyParser).toHaveBeenCalledWith('json', { limit: '4kb', inflate: false });
  expect(app.enableShutdownHooks).toHaveBeenCalledOnce();
});
it('closes resources and sanitizes failed HTTP startup without retry', async () => {
  environment(); const app = appDouble(); app.listen.mockRejectedValue(new Error('postgresql://private'));
  factory.create.mockResolvedValue(app);
  await expect(startPurchaseApi()).rejects.toThrow('P4_API_START_FAILED');
  expect(app.close).toHaveBeenCalledOnce(); expect(app.listen).toHaveBeenCalledOnce();
});
it('sanitizes a rejected Nest initialization without retrying construction', async () => {
  environment(); factory.create.mockRejectedValue(new Error('private driver stack'));
  await expect(startPurchaseApi()).rejects.toThrow('P4_API_START_FAILED');
  expect(factory.create).toHaveBeenCalledOnce();
});
