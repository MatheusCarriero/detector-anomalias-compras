import assert from "node:assert/strict";
import test from "node:test";
import { connect, inTransaction, readTestTarget, rejectsSQL } from "./helpers.mjs";

readTestTarget(); // Fail closed before any connection when not explicitly configured.

test("catalog contains exactly eleven app domain tables and real constraints", async () => {
  const client = await connect();
  try {
    const tables = (await client.query(
      "SELECT tablename FROM pg_tables WHERE schemaname='app' AND tablename <> '_prisma_migrations' ORDER BY tablename",
    )).rows.map((row) => row.tablename);
    assert.deepEqual(tables, ["audit_events", "currencies", "decision_snapshots", "departments",
      "purchase_order_lines", "record_versions", "snapshot_members", "source_identities",
      "source_references", "suppliers", "users"]);
    const { rows: numeric } = await client.query(
      "SELECT column_name, numeric_precision AS p, numeric_scale AS s FROM information_schema.columns WHERE table_schema='app' AND table_name='purchase_order_lines' AND data_type='numeric' ORDER BY column_name");
    assert.deepEqual(numeric, [
      { column_name: "amount", p: 24, s: 6 }, { column_name: "quantity", p: 20, s: 6 },
      { column_name: "unit_price", p: 24, s: 8 },
    ]);
    const { rows: deferred } = await client.query(
      "SELECT conname FROM pg_constraint WHERE connamespace='app'::regnamespace AND condeferrable AND contype='f' ORDER BY conname");
    assert.deepEqual(deferred.map((row) => row.conname), [
      "decision_snapshots_root_fk", "departments_head_fk", "purchase_order_lines_head_fk", "suppliers_head_fk",
    ]);
    assert.equal((await client.query(
      "SELECT count(*)::int AS n FROM pg_constraint WHERE connamespace='app'::regnamespace AND contype='f' AND confdeltype IN ('c','n')",
    )).rows[0].n, 0);
    const { rows: [uuid] } = await client.query("SELECT gen_random_uuid()::text AS id");
    assert.match(uuid.id, /^[0-9a-f-]{14}4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  } finally { await client.end(); }
});

test("canonical identity, typed resolution and reference scope remain consistent", async () => {
  await inTransaction(async (client, data) => {
    const identity = (await client.query(
      "SELECT app.register_source_identity('synthetic','supplier','line-001',$1) AS id", [data.actor],
    )).rows[0].id;
    await rejectsSQL(client,
      "SELECT app.register_source_identity('synthetic','supplier','line-001',$1)", [data.actor], "23505");
    await client.query("SELECT app.resolve_source_identity($1,$2,NULL,NULL,$3)",
      [identity, data.supplier.entity_id, data.actor]);
    await rejectsSQL(client,
      "UPDATE app.source_identities SET supplier_id=NULL,resolved_at=NULL WHERE id=$1", [identity], "55000");
    await rejectsSQL(client,
      "INSERT INTO app.source_references(source_identity_id,source_namespace,source_entity_kind) VALUES ($1,'wrong','supplier')",
      [identity], "23503");
    await rejectsSQL(client,
      "INSERT INTO app.source_identities(source_namespace,source_entity_kind,source_id,supplier_id,department_id,resolved_at) VALUES ('synthetic','supplier','bad-owner',$1,$2,now())",
      [data.supplier.entity_id, data.department.entity_id], "23514");
  });
});
