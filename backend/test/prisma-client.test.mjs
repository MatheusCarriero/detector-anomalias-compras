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
