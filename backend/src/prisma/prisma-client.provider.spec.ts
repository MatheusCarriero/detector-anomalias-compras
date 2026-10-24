import { Socket } from 'node:net';
import { PrismaPg } from '@prisma/adapter-pg';
import { PrismaClient } from '../../generated/prisma/client.js';
import { createPrismaClient } from './prisma-client.provider.js';

vi.mock('@prisma/adapter-pg', () => ({ PrismaPg: vi.fn(function () {}) }));
vi.mock('../../generated/prisma/client.js', () => ({
  PrismaClient: vi.fn(function () {}),
}));

// Synthetic credentials only. Neither constructor may open a socket here.
const syntheticUrl =
  'postgresql://detector_runtime:synthetic-password@127.0.0.1:5432/synthetic_procurement';

describe('Prisma client provider', () => {
  let networkAttempts: number;

  beforeEach(() => {
    networkAttempts = 0;
    vi.clearAllMocks();
    vi.stubEnv('DATABASE_URL', undefined);
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
      networkAttempts += 1;
      throw new Error('Network access is forbidden in this unit test');
    });
  });

  afterEach(() => {
    try {
      expect(networkAttempts).toBe(0);
    } finally {
      vi.restoreAllMocks();
      vi.unstubAllEnvs();
    }
  });

  it('wires explicit runtime settings to the adapter and the compiled client without connecting', () => {
    vi.stubEnv('DATABASE_URL', syntheticUrl);
    vi.stubEnv('PGOPTIONS', '-c role=detector_migrator');
    vi.stubEnv('PGUSER', 'detector_migrator');

    const client = createPrismaClient();

    expect(PrismaPg).toHaveBeenCalledExactlyOnceWith(
      {
        user: 'detector_runtime',
        password: 'synthetic-password',
        host: '127.0.0.1',
        port: 5432,
        database: 'synthetic_procurement',
        options: '-c search_path=app,pg_catalog',
      },
      { schema: 'app' },
    );
    const adapter = vi.mocked(PrismaPg).mock.instances[0];
    expect(PrismaClient).toHaveBeenCalledExactlyOnceWith({ adapter });
    expect(client).toBe(vi.mocked(PrismaClient).mock.instances[0]);
  });

  it('accepts the explicit app schema descriptor', () => {
    createPrismaClient(`${syntheticUrl}?schema=app`);
    expect(PrismaPg).toHaveBeenCalledOnce();
  });

  it.each([
    undefined,
    '',
    'not-a-url',
    syntheticUrl.replace('postgresql:', 'https:'),
    syntheticUrl.replace('detector_runtime', 'detector_migrator'),
    syntheticUrl.replace('detector_runtime', 'postgres'),
    syntheticUrl.replace('detector_runtime:synthetic-password@', ''),
    syntheticUrl.replace(':synthetic-password', ''),
    syntheticUrl.replace(':5432', ''),
    syntheticUrl.replace(':5432', ':0'),
    syntheticUrl.replace('/synthetic_procurement', '/'),
    syntheticUrl.replace('synthetic-password', '%invalid'),
    `${syntheticUrl}#ignored`,
    `${syntheticUrl}?schema=public`,
    `${syntheticUrl}?schema=app&schema=app`,
    `${syntheticUrl}?user=detector_migrator`,
    `${syntheticUrl}?host=other.example`,
    `${syntheticUrl}?options=-c%20role%3Ddetector_migrator`,
    `${syntheticUrl}?sslkey=local-file`,
  ])(
    'rejects invalid or overriding configuration before constructing the adapter (case %#)',
    (url) => {
      expect(() => createPrismaClient(url)).toThrow(/DATABASE_URL/);
      expect(PrismaPg).not.toHaveBeenCalled();
      expect(PrismaClient).not.toHaveBeenCalled();
    },
  );

  it('does not expose a rejected URL or password in configuration errors', () => {
    const url = syntheticUrl.replace('detector_runtime', 'detector_migrator');
    expect.assertions(4);
    try {
      createPrismaClient(url);
    } catch (error) {
      expect(error).toBeInstanceOf(Error);
      expect(String(error)).not.toContain(url);
      expect(String(error)).not.toContain('synthetic-password');
      expect(error).not.toHaveProperty('cause');
    }
  });

  it('redacts errors raised while constructing the adapter', () => {
    vi.mocked(PrismaPg).mockImplementationOnce(function () {
      throw new Error(syntheticUrl);
    });
    expect(() => createPrismaClient(syntheticUrl)).toThrow(
      /^Unable to initialize Prisma client$/,
    );
    expect(PrismaClient).not.toHaveBeenCalled();
  });

  it('redacts errors raised while constructing the client', () => {
    vi.mocked(PrismaClient).mockImplementationOnce(function () {
      throw new Error(syntheticUrl);
    });
    expect(() => createPrismaClient(syntheticUrl)).toThrow(
      /^Unable to initialize Prisma client$/,
    );
  });
});
