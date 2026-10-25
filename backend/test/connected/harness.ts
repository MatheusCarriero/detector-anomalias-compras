import type { TestingModule } from '@nestjs/testing';
import type { PrismaClient } from '../../generated/prisma/client.js';
import { connectedTestOptions, readConnectedTarget } from './config.js';

let active = false;
let unusable = false;

async function closeModule(module: TestingModule) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      module.close(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error('cleanup timeout')), 3000);
      }),
    ]);
  } finally { clearTimeout(timer); }
}

// Importing this module does not construct a driver or open a Nest context.
// Only the separately invoked connected runner may call this in a real environment.
export async function inspectRuntimeIdentity() {
  if (unusable) throw new Error('DB_TEST: harness unusable after cleanup failure');
  if (active) throw new Error('DB_TEST: concurrent harness use refused');
  connectedTestOptions(process.env);
  const target = readConnectedTarget(process.env);
  active = true;
  let module: TestingModule | undefined;
  let failed = false;
  let lifecycleError = false;
  let identity: { database: string; runtimeRole: string; serverVersion: number } | undefined;
  // These were absent/empty at the gate. Restore even after failed startup.
  const previousUrl = process.env.DATABASE_URL;
  const previousTls = process.env.PGSSLMODE;
  try {
    process.env.DATABASE_URL = target.runtimeUrl;
    // Deliberate, explicitly acknowledged loopback-only policy; never inherited.
    process.env.PGSSLMODE = 'disable';
    const { Test } = await import('@nestjs/testing');
    const { AppModule } = await import('../../src/app.module.js');
    const { PrismaModule } = await import('../../src/prisma/prisma.module.js');
    const { PRISMA_CLIENT } = await import('../../src/prisma/prisma-client.provider.js');
    module = await Test.createTestingModule({ imports: [AppModule] })
      .setLogger({
        log() {}, warn() {},
        // Nest 12 logs rejected destruction hooks instead of rejecting close().
        // Treat that as failure and never forward the original log/stack.
        error() { lifecycleError = true; },
      }).compile();
    await module.init();
    const client = module.select(PrismaModule).get<PrismaClient>(PRISMA_CLIENT, { strict: true });
    const rows = await client.$transaction(async (tx) => {
      await tx.$executeRaw`SET TRANSACTION READ ONLY`;
      await tx.$executeRaw`SET LOCAL statement_timeout = '5s'`;
      await tx.$executeRaw`SET LOCAL lock_timeout = '2s'`;
      await tx.$executeRaw`SET LOCAL idle_in_transaction_session_timeout = '5s'`;
      return tx.$queryRaw<Record<string, unknown>[]>`
        SELECT current_database() AS database, session_user::text AS session_user,
          current_user::text AS current_user,
          current_setting('server_version_num')::int AS server_version,
          inet_server_addr()::text AS server_address, inet_server_port() AS server_port,
          current_setting('search_path') AS search_path,
          has_schema_privilege(current_user, 'app', 'USAGE') AS schema_usage,
          has_schema_privilege(current_user, 'app', 'CREATE') AS schema_create,
          r.rolsuper AS superuser, r.rolcreatedb AS create_db, r.rolcreaterole AS create_role,
          r.rolreplication AS replication, r.rolbypassrls AS bypass_rls, s.ssl AS tls
        FROM pg_catalog.pg_roles r
        JOIN pg_catalog.pg_stat_ssl s ON s.pid = pg_backend_pid()
        WHERE r.rolname = current_user`;
    }, { isolationLevel: 'ReadCommitted', maxWait: 3000, timeout: 10000 });
    const row = rows[0];
    const expected = {
      database: target.database, session_user: target.runtimeRole, current_user: target.runtimeRole,
      server_address: target.host === '[::1]' ? '::1' : target.host, server_port: target.port,
      schema_usage: true, schema_create: false, superuser: false, create_db: false,
      create_role: false, replication: false, bypass_rls: false, tls: false,
    };
    if (rows.length !== 1 || !row ||
      Object.entries(expected).some(([key, value]) => row[key] !== value) ||
      typeof row.server_version !== 'number' || row.server_version < 180000 || row.server_version >= 190000 ||
      typeof row.search_path !== 'string' || row.search_path.replaceAll(' ', '') !== 'app,pg_catalog'
    ) throw new Error('identity mismatch');
    identity = { database: target.database, runtimeRole: target.runtimeRole, serverVersion: row.server_version };
  } catch {
    failed = true;
  }
  let cleanupFailed = false;
  try { if (module) await closeModule(module); }
  catch { cleanupFailed = true; }
  if (previousUrl === undefined) delete process.env.DATABASE_URL;
  else process.env.DATABASE_URL = previousUrl;
  if (previousTls === undefined) delete process.env.PGSSLMODE;
  else process.env.PGSSLMODE = previousTls;
  active = false;
  unusable = cleanupFailed || lifecycleError;
  if (failed || !identity) throw new Error('DB_TEST: identity inspection failed');
  if (unusable) throw new Error('DB_TEST: resource cleanup failed');
  return identity;
}
