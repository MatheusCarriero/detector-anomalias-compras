import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

test('compiled Prisma Client imports in Node without a database URL or socket connection', () => {
  const client = new URL('../generated/prisma/client.js', import.meta.url);
  assert.ok(existsSync(client), 'Run npm.cmd run prisma:prepare first');
  const env = { ...process.env };
  delete env.DATABASE_URL;
  const result = spawnSync(process.execPath, ['--input-type=module', '--eval', `
    import assert from 'node:assert/strict';
    import { Socket } from 'node:net';
    Socket.prototype.connect = () => { throw new Error('Socket connection forbidden'); };
    assert.equal(process.env.DATABASE_URL, undefined);
    const { PrismaClient } = await import(${JSON.stringify(client.href)});
    assert.equal(typeof PrismaClient, 'function');
    console.log('PrismaClient import OK; no instance created');
  `], { cwd: fileURLToPath(new URL('../', import.meta.url)), env, encoding: 'utf8', timeout: 15_000 });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /PrismaClient import OK/);
});

test('real client and adapter constructors are compatible without connecting', () => {
  const client = new URL('../generated/prisma/client.js', import.meta.url);
  assert.ok(existsSync(client), 'Run npm.cmd run prisma:prepare first');
  const env = { ...process.env };
  delete env.DATABASE_URL;
  const result = spawnSync(process.execPath, ['--input-type=module', '--eval', `
    import assert from 'node:assert/strict';
    import { Socket } from 'node:net';
    let connectionAttempts = 0;
    Socket.prototype.connect = () => {
      connectionAttempts += 1;
      throw new Error('Socket connection forbidden');
    };
    assert.equal(process.env.DATABASE_URL, undefined);
    const { PrismaPg } = await import('@prisma/adapter-pg');
    const { PrismaClient } = await import(${JSON.stringify(client.href)});
    const adapter = new PrismaPg({
      user: 'detector_runtime', password: 'synthetic-password',
      host: '127.0.0.1', port: 5432, database: 'synthetic_procurement',
      options: '-c search_path=app,pg_catalog',
    }, { schema: 'app' });
    const instance = new PrismaClient({ adapter });
    assert.equal(typeof instance.$connect, 'function');
    await instance.$disconnect();
    assert.equal(connectionAttempts, 0);
    console.log('Constructors compatible; DATABASE_CONNECTION_ATTEMPTS=0');
  `], { cwd: fileURLToPath(new URL('../', import.meta.url)), env, encoding: 'utf8', timeout: 15_000 });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /DATABASE_CONNECTION_ATTEMPTS=0/);
});

test('Prisma 7 preserves endpoint text and decodes int4 as number using an offline pg result', () => {
  const client = new URL('../generated/prisma/client.js', import.meta.url);
  assert.ok(existsSync(client), 'Run npm.cmd run prisma:prepare first');
  const env = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (/^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|TMPDIR|HOME|USERPROFILE|LOCALAPPDATA|APPDATA)$/i.test(key)) env[key] = value;
  }
  const result = spawnSync(process.execPath, ['--input-type=module', '--eval', `
    import assert from 'node:assert/strict';
    import { Socket } from 'node:net';
    let attempts = 0;
    Socket.prototype.connect = () => { attempts++; throw new Error('Socket forbidden'); };
    const { default: pg } = await import('pg');
    const { PrismaPg } = await import('@prisma/adapter-pg');
    const { PrismaClient } = await import(${JSON.stringify(client.href)});
    const pool = new pg.Pool({ user: 'detector_runtime', password: 'synthetic-password',
      host: '127.0.0.1', port: 5432, database: 'synthetic_fixture' });
    pool.connect = async () => { throw new Error('Pool acquisition forbidden'); };
    let address;
    let calls = 0;
    pool.query = async (query) => {
      calls++;
      assert.equal(query.text, "SELECT 'offline endpoint fixture'");
      assert.equal(query.rowMode, 'array');
      // Only pg's real parsers and Prisma's decoder run; no server executes SQL.
      return { command: 'SELECT', rowCount: 1, oid: null,
        fields: [{ name: 'server_address', dataTypeID: 25 }, { name: 'server_port', dataTypeID: 23 }],
        rows: [[query.types.getTypeParser(25, 'text')(address),
          query.types.getTypeParser(23, 'text')('5432')]],
      };
    };
    const instance = new PrismaClient({ adapter: new PrismaPg(pool, { schema: 'app' }) });
    try {
      for (address of ['127.0.0.1/32', '::1/128', '127.0.0.1', '::1']) {
        const rows = await instance.$queryRawUnsafe("SELECT 'offline endpoint fixture'");
        assert.deepEqual(rows, [{ server_address: address, server_port: 5432 }]);
        assert.equal(typeof rows[0].server_address, 'string');
        assert.equal(typeof rows[0].server_port, 'number');
      }
      assert.equal(calls, 4);
    } finally { await instance.$disconnect(); await pool.end(); }
    assert.equal(attempts, 0);
    console.log('Endpoint decoding OK; DATABASE_CONNECTION_ATTEMPTS=0');
  `], { cwd: fileURLToPath(new URL('../', import.meta.url)), env, encoding: 'utf8', timeout: 15_000 });
  assert.equal(result.status, 0, result.stdout + result.stderr);
  assert.match(result.stdout, /Endpoint decoding OK; DATABASE_CONNECTION_ATTEMPTS=0/);
});

// Real Prisma transaction manager + adapter; only the pg I/O boundary is replaced.
// A failure here must never cause an actual pool/socket connection.
for (const scenario of [
  { point: 'acquire', kind: 'unreachable', category: 'TX_ERROR_UNREACHABLE', callback: false,
    events: ['acquire'] },
  { point: 'begin', kind: 'cancelled', category: 'TX_ERROR_CANCELLED', callback: false,
    events: ['acquire', 'begin', 'release'] },
  { point: 'isolation', kind: 'cancelled', category: 'TX_ERROR_CANCELLED', callback: false,
    events: ['acquire', 'begin', 'isolation', 'release'] },
  { point: 'read-only', kind: 'cancelled', category: 'TX_ERROR_CANCELLED', callback: true,
    events: ['acquire', 'begin', 'isolation', 'callback', 'read-only', 'rollback', 'release'] },
  { point: 'query', kind: 'syntax', category: 'TX_ERROR_SQL_SYNTAX', callback: true,
    events: ['acquire', 'begin', 'isolation', 'callback', 'read-only', 'query', 'rollback', 'release'] },
  { point: 'commit', kind: 'closed', category: 'TX_ERROR_CONNECTION_CLOSED', callback: true,
    events: ['acquire', 'begin', 'isolation', 'callback', 'read-only', 'query', 'commit', 'release'] },
  { point: 'acquire', kind: 'unknown', category: 'TX_ERROR_UNKNOWN', callback: false,
    events: ['acquire'] },
  { point: 'late-acquire', category: 'TX_ERROR_API', callback: false,
    events: ['acquire', 'begin', 'isolation', 'rollback', 'release'] },
  { point: 'validation', callback: true,
    events: ['acquire', 'begin', 'isolation', 'callback', 'read-only', 'query', 'rollback', 'release'] },
]) {
  test(`offline transaction boundary: ${scenario.point}/${scenario.kind ?? (scenario.point === 'validation' ? 'local-refusal' : 'deadline')}`, () => {
    const client = new URL('../generated/prisma/client.js', import.meta.url);
    assert.ok(existsSync(client), 'Run npm.cmd run prisma:prepare first');
    const env = {};
    for (const [key, value] of Object.entries(process.env)) {
      if (/^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|TMPDIR|HOME|USERPROFILE|LOCALAPPDATA|APPDATA)$/i.test(key)) env[key] = value;
    }
    const result = spawnSync(process.execPath, ['--input-type=module', '--eval', `
      import assert from 'node:assert/strict';
      import { Socket } from 'node:net';
      import { EventEmitter } from 'node:events';
      let attempts = 0;
      Socket.prototype.connect = () => { attempts++; throw new Error('Socket forbidden'); };
      const { default: pg } = await import('pg');
      const { PrismaPg } = await import('@prisma/adapter-pg');
      const { PrismaClient } = await import(${JSON.stringify(client.href)});
      const { transactionErrorCategory, diagnosticError, isDiagnosticError } = await import('./test/connected/diagnostics.mjs');
      const validationError = diagnosticError('CATALOG_DEFAULT_ACL_FUNCTIONS');
      const scenario = ${JSON.stringify(scenario)};
      const events = [];
      const pool = new pg.Pool({ user: 'detector_runtime', password: 'synthetic-password',
        host: '127.0.0.1', port: 5432, database: 'synthetic_fixture' });
      const conn = new EventEmitter();
      const privateError = Object.assign(new Error('PRIVATE_DRIVER_SENTINEL'),
        scenario.kind === 'unreachable' ? { code: 'ECONNREFUSED', syscall: 'connect', errno: -1 } :
        scenario.kind === 'closed' ? { code: 'ECONNRESET', syscall: 'read', errno: -1 } :
        scenario.kind === 'cancelled' ? { code: '57014', severity: 'ERROR' } :
        scenario.kind === 'syntax' ? { code: '42601', severity: 'ERROR' } : {});
      privateError.stack = 'PRIVATE_STACK_SENTINEL';
      let released;
      const releaseCompleted = new Promise(resolve => { released = resolve; });
      conn.release = () => { events.push('release'); released(); };
      conn.query = async (query) => {
        const point = query.text === 'BEGIN' ? 'begin' :
          query.text === 'SET TRANSACTION ISOLATION LEVEL READ COMMITTED' ? 'isolation' :
          query.text === 'SET TRANSACTION READ ONLY' ? 'read-only' :
          query.text === 'SELECT 1' ? 'query' :
          query.text === 'COMMIT' ? 'commit' : query.text === 'ROLLBACK' ? 'rollback' : 'unexpected';
        assert.notEqual(point, 'unexpected');
        events.push(point);
        if (point === scenario.point) throw privateError;
        return { fields: [], rows: [], rowCount: 0 };
      };
      let resumeAcquisition;
      const pendingAcquisition = new Promise(resolve => { resumeAcquisition = resolve; });
      pool.connect = async () => {
        events.push('acquire');
        if (scenario.point === 'acquire') throw privateError;
        if (scenario.point === 'late-acquire') await pendingAcquisition;
        return conn;
      };
      const instance = new PrismaClient({ adapter: new PrismaPg(pool, { schema: 'app' }) });
      // Prisma unrefs its timer. Keep this isolated fixture alive until it fires.
      const keepAlive = setTimeout(() => {}, 10_000);
      try {
        await instance.$connect();
        assert.deepEqual(events, [], '$connect initializes the pool but does not prove acquisition');
        const error = await instance.$transaction(async tx => {
          events.push('callback');
          await tx.$executeRawUnsafe('SET TRANSACTION READ ONLY');
          await tx.$executeRawUnsafe('SELECT 1');
          if (scenario.point === 'validation') throw validationError;
        }, { isolationLevel: 'ReadCommitted', maxWait: scenario.point === 'late-acquire' ? 50 : 3000,
          timeout: 10000 }).then(() => { throw new Error('Expected fixture failure'); }, error => error);
        if (scenario.point === 'validation') {
          assert.equal(error, validationError, 'Prisma must preserve the local error identity');
          assert.equal(isDiagnosticError(error), true);
        } else {
          assert.equal(isDiagnosticError(error), false);
          assert.equal(transactionErrorCategory(error), scenario.category);
        }
        assert.equal(events.includes('callback'), scenario.callback);
        if (scenario.point === 'late-acquire') {
          assert.equal(error.code, 'P2028');
          assert.deepEqual(events, ['acquire']);
          resumeAcquisition();
          await releaseCompleted;
        }
        assert.deepEqual(events, scenario.events);
      } finally {
        clearTimeout(keepAlive);
        resumeAcquisition();
        await instance.$disconnect();
        await pool.end();
      }
      assert.equal(attempts, 0);
      console.log('Transaction fixture OK; DATABASE_CONNECTION_ATTEMPTS=0');
    `], { cwd: fileURLToPath(new URL('../', import.meta.url)), env, encoding: 'utf8', timeout: 20_000 });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, /Transaction fixture OK; DATABASE_CONNECTION_ATTEMPTS=0/);
    assert.doesNotMatch(result.stdout + result.stderr, /PRIVATE_|postgresql:\/\//);
  });
}
