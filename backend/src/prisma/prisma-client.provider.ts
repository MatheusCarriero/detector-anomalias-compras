import { PrismaPg } from '@prisma/adapter-pg';
import { PrismaClient } from '../../generated/prisma/client.js';

export const PRISMA_CLIENT = Symbol('PRISMA_CLIENT');
export type PrismaLifecycleClient = Pick<
  PrismaClient,
  '$connect' | '$disconnect'
>;

function readConnectionConfig(connectionString: string | undefined) {
  try {
    if (!connectionString) throw new Error();
    const url = new URL(connectionString);
    const user = decodeURIComponent(url.username);
    const password = decodeURIComponent(url.password);
    const host = decodeURIComponent(url.hostname).replace(/^\[(.*)\]$/, '$1');
    const database = decodeURIComponent(url.pathname.slice(1));
    const port = Number(url.port);
    const parameters = [...url.searchParams.entries()];

    if (
      !['postgres:', 'postgresql:'].includes(url.protocol) ||
      user !== 'detector_runtime' ||
      !password ||
      !host ||
      !database ||
      Array.from(user + password + host + database).some(
        (character) => character.charCodeAt(0) < 32,
      ) ||
      host.includes('/') ||
      database.includes('/') ||
      !Number.isInteger(port) ||
      port < 1 ||
      port > 65535 ||
      url.hash ||
      parameters.length > 1 ||
      parameters.some(([key, value]) => key !== 'schema' || value !== 'app')
    ) {
      throw new Error();
    }

    // Explicit fields avoid a second URL parser and PG* identity fallbacks.
    return {
      user,
      password,
      host,
      port,
      database,
      options: '-c search_path=app,pg_catalog',
    };
  } catch {
    // URL/driver errors may contain the supplied credential. Never propagate them.
    throw new Error(
      'Invalid DATABASE_URL: explicit PostgreSQL host, port, database, password and detector_runtime user required (schema app)',
    );
  }
}

export function createPrismaClient(
  connectionString = process.env.DATABASE_URL,
): PrismaClient {
  const config = readConnectionConfig(connectionString);
  try {
    const adapter = new PrismaPg(config, { schema: 'app' });
    return new PrismaClient({ adapter });
  } catch {
    throw new Error('Unable to initialize Prisma client');
  }
}
