import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const root = new URL("../../", import.meta.url);
const read = (path) => {
  const file = new URL(path, root);
  assert.ok(existsSync(file), `Missing infrastructure artifact: ${path}`);
  return readFileSync(file, "utf8");
};

// Static scope checks only; SQL behavior is covered by the opt-in integration suite.
test("local dependencies are pinned and installation never applies migrations", () => {
  const pkg = JSON.parse(read("package.json"));
  assert.equal(pkg.private, true);
  assert.equal(pkg.devDependencies.prisma, "7.10.0");
  assert.equal(pkg.dependencies["@prisma/client"], "7.10.0");
  assert.equal(pkg.dependencies["@prisma/adapter-pg"], "7.10.0");
  assert.equal(pkg.dependencies.pg, "8.16.3");
  for (const hook of ["preinstall", "install", "postinstall", "prepare", "pretest"]) {
    assert.equal(pkg.scripts[hook], undefined);
  }
  assert.equal(pkg.scripts["db:validate"], "prisma validate");
  assert.equal(pkg.scripts["db:generate"], "prisma generate");
  assert.equal(pkg.scripts.test, "node --test tests/database/contract.test.mjs");
});

test("Prisma scope is exactly the approved eleven tables in app", () => {
  const schema = read("prisma/schema.prisma");
  const models = [...schema.matchAll(/^model (\w+) \{([\s\S]*?)^\}/gm)];
  assert.equal(models.length, 11);
  const tables = models.map(([, , body]) => {
    assert.match(body, /@@schema\("app"\)/);
    const table = body.match(/@@map\("(\w+)"\)/);
    assert.ok(table);
    return table[1];
  }).sort();
  assert.deepEqual(tables, [
    "audit_events", "currencies", "decision_snapshots", "departments",
    "purchase_order_lines", "record_versions", "snapshot_members",
    "source_identities", "source_references", "suppliers", "users",
  ]);
  assert.match(schema, /provider\s*=\s*"postgresql"/);
  assert.match(schema, /schemas\s*=\s*\["app"\]/);
  assert.doesNotMatch(schema, /relationMode\s*=\s*"prisma"/);
  assert.doesNotMatch(schema, /@db\.(?:Real|DoublePrecision|Timestamp\()/);
  assert.doesNotMatch(schema, /\bFloat\b/);
  assert.match(schema, /@db\.Decimal\(24,\s*6\)/);
  assert.match(schema, /@db\.Decimal\(24,\s*8\)/);
  assert.match(schema, /@db\.Decimal\(20,\s*6\)/);
});

test("configuration has no default database target, seed or shadow database", () => {
  const config = read("prisma.config.ts");
  assert.match(config, /process\.env\.DATABASE_URL/);
  assert.doesNotMatch(config, /postgres(?:ql)?:\/\//);
  assert.doesNotMatch(config, /\b(?:seed|shadowDatabaseUrl|initShadowDb)\s*:/);
});

test("migration guards the Prisma bootstrap namespace and pins app before its DDL", () => {
  const sql = read("prisma/migrations/20261020000100_first_increment/migration.sql");
  const firstTable = sql.indexOf('CREATE TABLE "currencies"');
  assert.ok(firstTable > 0);
  const bootstrap = sql.slice(0, firstTable);
  assert.match(bootstrap, /SET LOCAL search_path\s*=\s*app,\s*pg_catalog;/);
  assert.match(bootstrap, /Unexpected preexisting objects in app/);
  assert.match(bootstrap, /_prisma_migrations/);
  assert.doesNotMatch(bootstrap, /CREATE SCHEMA IF NOT EXISTS/);
});

test("integration gate rejects missing, nonlocal, mismatched or reused credentials before connecting", async () => {
  assert.ok(existsSync(new URL("tests/database/helpers.mjs", root)), "Missing test connection gate");
  const { readTestTarget } = await import("./helpers.mjs");
  const valid = {
    DB_TEST_CONFIRM: "synthetic-only",
    DB_TEST_HOST: "127.0.0.1", DB_TEST_PORT: "5432",
    DB_TEST_DATABASE: "synthetic_procurement", DB_TEST_MIGRATOR: "fixture_owner",
    DB_TEST_RUNTIME: "fixture_app",
    DB_TEST_MIGRATION_URL: "postgresql://fixture_owner:fake@127.0.0.1:5432/synthetic_procurement",
    DB_TEST_RUNTIME_URL: "postgresql://fixture_app:fake@127.0.0.1:5432/synthetic_procurement",
  };
  assert.equal(readTestTarget(valid).database, "synthetic_procurement");
  assert.throws(() => readTestTarget({ DATABASE_URL: valid.DB_TEST_MIGRATION_URL }), /DB_TEST/);
  for (const [key, value] of [
    ["DB_TEST_CONFIRM", ""], ["DB_TEST_HOST", "production.example"],
    ["DB_TEST_DATABASE", "production"], ["DB_TEST_RUNTIME", "fixture_owner"],
    ["DB_TEST_RUNTIME_URL", valid.DB_TEST_MIGRATION_URL],
    ["DB_TEST_RUNTIME_URL", `${valid.DB_TEST_RUNTIME_URL}?host=production.example`],
    ["DB_TEST_RUNTIME_URL", valid.DB_TEST_RUNTIME_URL.replace("5432", "5433")],
    ["DB_TEST_RUNTIME_URL", valid.DB_TEST_RUNTIME_URL.replace("synthetic_procurement", "other")],
  ]) {
    assert.throws(() => readTestTarget({ ...valid, [key]: value }), /DB_TEST/);
  }
});
