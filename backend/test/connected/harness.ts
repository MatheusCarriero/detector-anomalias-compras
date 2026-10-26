import type { TestingModule } from '@nestjs/testing';
import type { PrismaClient } from '../../generated/prisma/client.js';
import { connectedTestOptions, readConnectedTarget } from './config.js';
import { diagnosticCode, diagnosticError, reportDiagnostic, transactionErrorCategory } from './diagnostics.mjs';

let active = false;
let unusable = false;

async function closeModule(module: TestingModule) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      module.close(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(diagnosticError('RESOURCE_CLEANUP_TIMEOUT')), 3000);
      }),
    ]);
  } finally { clearTimeout(timer); }
}

// Importing this module does not construct a driver or open a Nest context.
// Only the separately invoked connected runner may call this in a real environment.
export async function inspectRuntimeIdentity() {
  let target: ReturnType<typeof readConnectedTarget>;
  try {
    if (unusable) throw diagnosticError('HARNESS_UNUSABLE');
    if (active) throw diagnosticError('HARNESS_BUSY');
    connectedTestOptions(process.env);
    target = readConnectedTarget(process.env);
  } catch (error) {
    const code = diagnosticCode(error, 'CONFIG_TARGET');
    reportDiagnostic('failure', code);
    throw diagnosticError(code);
  }
  active = true;
  let module: TestingModule | undefined;
  let failure: Error | undefined;
  let lifecycleError = false;
  let loggedFailure: string | undefined;
  let closing = false;
  let transactionPending = false;
  let stage = 'MODULE_IMPORT';
  const enter = (code: string) => {
    stage = code;
    reportDiagnostic('stage', code);
  };
  let identity: { database: string; runtimeRole: string; serverVersion: number } | undefined;
  // These were absent/empty at the gate. Restore even after failed startup.
  const previousUrl = process.env.DATABASE_URL;
  const previousTls = process.env.PGSSLMODE;
  try {
    process.env.DATABASE_URL = target.runtimeUrl;
    // Deliberate, explicitly acknowledged loopback-only policy; never inherited.
    process.env.PGSSLMODE = 'disable';
    enter('MODULE_IMPORT');
    const { Test } = await import('@nestjs/testing');
    const { AppModule } = await import('../../src/app.module.js');
    const { PrismaModule } = await import('../../src/prisma/prisma.module.js');
    const { PRISMA_CLIENT } = await import('../../src/prisma/prisma-client.provider.js');
    enter('MODULE_COMPILE');
    module = await Test.createTestingModule({ imports: [AppModule] })
      .setLogger({
        log() {}, warn() {},
        // Nest 12 logs rejected destruction hooks instead of rejecting close().
        // Treat that as failure and never forward the original log/stack.
        error() {
          if (closing) lifecycleError = true;
          else loggedFailure ??= stage;
        },
      }).compile();
    if (loggedFailure) throw diagnosticError(loggedFailure);
    enter('MODULE_INIT');
    await module.init();
    if (loggedFailure) throw diagnosticError(loggedFailure);
    enter('CLIENT_RESOLUTION');
    const client = module.select(PrismaModule).get<PrismaClient>(PRISMA_CLIENT, { strict: true });
    // This boundary includes pool acquisition, BEGIN and isolation setup.
    // Prisma does not expose those as separate public lifecycle callbacks.
    enter('TRANSACTION_START');
    transactionPending = true;
    const rows = await client.$transaction(async (tx) => {
      enter('TRANSACTION_CALLBACK');
      enter('READ_ONLY_SETUP');
      await tx.$executeRaw`SET TRANSACTION READ ONLY`;
      enter('SESSION_TIMEOUT_SETUP');
      await tx.$executeRaw`SET LOCAL statement_timeout = '5s'`;
      await tx.$executeRaw`SET LOCAL lock_timeout = '2s'`;
      await tx.$executeRaw`SET LOCAL idle_in_transaction_session_timeout = '5s'`;
      enter('IDENTITY_QUERY');
      const result = await tx.$queryRaw<Record<string, unknown>[]>`
        SELECT current_database() AS database, session_user::text AS session_user,
          current_user::text AS current_user,
          current_setting('server_version_num')::int AS server_version,
          pg_catalog.host(inet_server_addr()) AS server_address, inet_server_port() AS server_port,
          current_setting('search_path') AS search_path,
          has_schema_privilege(current_user, 'app', 'USAGE') AS schema_usage,
          has_schema_privilege(current_user, 'app', 'CREATE') AS schema_create,
          r.rolsuper AS superuser, r.rolcreatedb AS create_db, r.rolcreaterole AS create_role,
          r.rolreplication AS replication, r.rolbypassrls AS bypass_rls, s.ssl AS tls
        FROM pg_catalog.pg_roles r
        JOIN pg_catalog.pg_stat_ssl s ON s.pid = pg_backend_pid()
        WHERE r.rolname = current_user`;
      enter('TRANSACTION_FINISH');
      return result;
    }, { isolationLevel: 'ReadCommitted', maxWait: 3000, timeout: 10000 });
    transactionPending = false;
    enter('TRANSACTION_RESOLVED');
    if (loggedFailure) throw diagnosticError(loggedFailure);
    enter('IDENTITY_RESULT_SHAPE');
    if (!Array.isArray(rows) || rows.length !== 1 || !rows[0] ||
      typeof rows[0] !== 'object' || Array.isArray(rows[0])) {
      throw diagnosticError('IDENTITY_RESULT_SHAPE');
    }
    const row = rows[0];
    enter('IDENTITY_MISMATCH');
    if (typeof row.server_address !== 'string') throw diagnosticError('IDENTITY_ADDRESS_TYPE');
    if (typeof row.server_port !== 'number') throw diagnosticError('IDENTITY_PORT_TYPE');
    const checks: [string, unknown, string][] = [
      ['database', target.database, 'IDENTITY_DATABASE'],
      ['session_user', target.runtimeRole, 'IDENTITY_USER'],
      ['current_user', target.runtimeRole, 'IDENTITY_USER'],
      ['server_address', target.host === '[::1]' ? '::1' : target.host, 'IDENTITY_ADDRESS_VALUE'],
      ['server_port', target.port, 'IDENTITY_PORT_VALUE'],
      ['schema_usage', true, 'IDENTITY_SCHEMA'], ['schema_create', false, 'IDENTITY_SCHEMA'],
      ['superuser', false, 'IDENTITY_PRIVILEGES'], ['create_db', false, 'IDENTITY_PRIVILEGES'],
      ['create_role', false, 'IDENTITY_PRIVILEGES'], ['replication', false, 'IDENTITY_PRIVILEGES'],
      ['bypass_rls', false, 'IDENTITY_PRIVILEGES'], ['tls', false, 'IDENTITY_TRANSPORT'],
    ];
    for (const [key, expected, code] of checks) {
      if (row[key] !== expected) throw diagnosticError(code);
    }
    if (typeof row.server_version !== 'number' || row.server_version < 180000 || row.server_version >= 190000) {
      throw diagnosticError('IDENTITY_VERSION');
    }
    if (typeof row.search_path !== 'string' || row.search_path.replaceAll(' ', '') !== 'app,pg_catalog') {
      throw diagnosticError('IDENTITY_SEARCH_PATH');
    }
    identity = { database: target.database, runtimeRole: target.runtimeRole, serverVersion: row.server_version };
  } catch (error) {
    const code = diagnosticCode(error, stage);
    reportDiagnostic('failure', code);
    if (transactionPending) reportDiagnostic('failure', transactionErrorCategory(error));
    failure = diagnosticError(code);
  }
  let cleanupFailure: Error | undefined;
  if (module) {
    enter('RESOURCE_CLEANUP');
    closing = true;
    try { await closeModule(module); }
    catch (error) {
      const code = diagnosticCode(error, 'RESOURCE_CLEANUP');
      reportDiagnostic('failure', code);
      cleanupFailure = diagnosticError(code);
    }
    if (lifecycleError) {
      reportDiagnostic('failure', 'RESOURCE_CLEANUP_HOOK');
      cleanupFailure ??= diagnosticError('RESOURCE_CLEANUP_HOOK');
    }
  }
  if (previousUrl === undefined) delete process.env.DATABASE_URL;
  else process.env.DATABASE_URL = previousUrl;
  if (previousTls === undefined) delete process.env.PGSSLMODE;
  else process.env.PGSSLMODE = previousTls;
  active = false;
  unusable = cleanupFailure !== undefined;
  if (failure) throw failure;
  if (cleanupFailure) throw cleanupFailure;
  if (!identity) throw diagnosticError('IDENTITY_RESULT_SHAPE');
  reportDiagnostic('stage', 'HARNESS_OK');
  return identity;
}
