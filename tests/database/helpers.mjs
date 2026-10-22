import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";

// Pure gate: no driver import, connection, file read or DATABASE_URL fallback.
export function readTestTarget(env = process.env) {
  const required = [
    "DB_TEST_HOST", "DB_TEST_PORT", "DB_TEST_DATABASE", "DB_TEST_MIGRATOR",
    "DB_TEST_RUNTIME", "DB_TEST_MIGRATION_URL", "DB_TEST_RUNTIME_URL",
  ];
  if (env.DB_TEST_CONFIRM !== "synthetic-only" || required.some((key) => !env[key])) {
    throw new Error("DB_TEST: explicit synthetic target and separate roles required");
  }
  if (!["localhost", "127.0.0.1", "[::1]"].includes(env.DB_TEST_HOST) ||
      !/^[1-9][0-9]{0,4}$/.test(env.DB_TEST_PORT) || Number(env.DB_TEST_PORT) > 65535 ||
      !/^synthetic_[a-z0-9_]+$/.test(env.DB_TEST_DATABASE) ||
      env.DB_TEST_MIGRATOR === env.DB_TEST_RUNTIME) {
    throw new Error("DB_TEST: target must be local, dedicated and use distinct roles");
  }
  const urls = {};
  for (const [kind, user, value] of [
    ["migration", env.DB_TEST_MIGRATOR, env.DB_TEST_MIGRATION_URL],
    ["runtime", env.DB_TEST_RUNTIME, env.DB_TEST_RUNTIME_URL],
  ]) {
    let url;
    try { url = new URL(value); } catch { throw new Error("DB_TEST: invalid URL"); }
    if (!["postgres:", "postgresql:"].includes(url.protocol) ||
        url.hostname !== env.DB_TEST_HOST || url.port !== env.DB_TEST_PORT ||
        decodeURIComponent(url.pathname) !== `/${env.DB_TEST_DATABASE}` ||
        decodeURIComponent(url.username) !== user || url.hash || url.search) {
      throw new Error("DB_TEST: URL differs from the explicitly identified target");
    }
    urls[kind] = value;
  }
  return { ...urls, database: env.DB_TEST_DATABASE, runtimeRole: env.DB_TEST_RUNTIME };
}

export async function connect(kind = "migration") {
  const target = readTestTarget();
  assert.ok(["migration", "runtime"].includes(kind));
  const { Client } = await import("pg");
  const client = new Client({
    connectionString: target[kind], application_name: "synthetic_db_contract",
    connectionTimeoutMillis: 3000, statement_timeout: 6000, lock_timeout: 4000,
  });
  try {
    await client.connect();
    const { rows: [actual] } = await client.query(
      "SELECT current_database() AS name, current_setting('server_version_num')::int AS version");
    assert.equal(actual.name, target.database);
    assert.ok(actual.version >= 180000 && actual.version < 190000);
    return client;
  } catch (error) {
    await client.end().catch(() => {});
    // Do not include a connection URL/password in error output.
    throw new Error(`DB_TEST connection/preflight failed (${error.code ?? "precondition"})`);
  }
}

export async function fixture(client) {
  const actor = randomUUID();
  await client.query(
    "INSERT INTO app.users(id, display_name) VALUES ($1, 'SYNTHETIC reviewer')", [actor]);
  await client.query(
    "INSERT INTO app.currencies(code, name) VALUES ('XTS', 'SYNTHETIC test currency') ON CONFLICT (code) DO NOTHING");
  const { rows: [currency] } = await client.query(
    "SELECT id, name FROM app.currencies WHERE code = 'XTS'");
  assert.equal(currency.name, "SYNTHETIC test currency");
  const supplier = (await client.query(
    "SELECT * FROM app.write_supplier(NULL, NULL, $1, $2)",
    [JSON.stringify({ name: "SYNTHETIC supplier", country_code: "ZZ", status: null, tier: null }), actor],
  )).rows[0];
  const department = (await client.query(
    "SELECT * FROM app.write_department(NULL, NULL, $1, $2)",
    [JSON.stringify({ name: "SYNTHETIC department", code: null }), actor],
  )).rows[0];
  const line = await writeLine(client, {
    actor, supplier: supplier.entity_id, department: department.entity_id, currency: currency.id,
  });
  return { actor, currency: currency.id, supplier, department, line };
}

export async function writeLine(client, {
  actor, id = null, expected = null, supplier = null, department = null, currency = null,
  state = { description: "SYNTHETIC line", po_date: "2026-10-01", quantity: "2", unit_price: "3", amount: "6" },
}) {
  return (await client.query(
    "SELECT * FROM app.write_purchase_order_line($1,$2,$3,$4,$5,$6,$7)",
    [id, expected, JSON.stringify(state), supplier, department, currency, actor],
  )).rows[0];
}

export async function inTransaction(body) {
  const client = await connect();
  try {
    await client.query("BEGIN ISOLATION LEVEL READ COMMITTED");
    const data = await fixture(client);
    await body(client, data);
    // ROLLBACK alone would not exercise deferred invariants.
    await client.query("SET CONSTRAINTS ALL IMMEDIATE");
  } finally {
    await client.query("ROLLBACK").catch(() => {});
    await client.end();
  }
}

export async function rejectsSQL(client, sql, params, sqlstate) {
  await client.query("SAVEPOINT invalid_case");
  try {
    await assert.rejects(async () => {
      await client.query(sql, params);
      await client.query("SET CONSTRAINTS ALL IMMEDIATE");
    }, (error) => error.code === sqlstate);
  } finally {
    await client.query("ROLLBACK TO SAVEPOINT invalid_case");
    await client.query("RELEASE SAVEPOINT invalid_case");
  }
}

// Poll a real observable lock, not a timing assumption.
export async function waitForBlocked(observer, blockedPid, blockerPid) {
  const deadline = Date.now() + 2500;
  while (Date.now() < deadline) {
    const { rows: [row] } = await observer.query(
      "SELECT $1::int = ANY(pg_blocking_pids($2::int)) AS blocked", [blockerPid, blockedPid]);
    if (row.blocked) return;
    await delay(20);
  }
  assert.fail("Expected PostgreSQL lock was not observed");
}
