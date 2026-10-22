import assert from "node:assert/strict";
import test from "node:test";
import { connect, fixture, readTestTarget, rejectsSQL } from "./helpers.mjs";

readTestTarget();

test("actual runtime role cannot bypass routines or modify evidence", async () => {
  const owner = await connect();
  const runtime = await connect("runtime");
  try {
    await owner.query("BEGIN");
    const data = await fixture(owner);
    await owner.query("COMMIT");
    const { rows: [role] } = await runtime.query(
      "SELECT rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=current_user");
    assert.deepEqual(role, { rolsuper: false, rolcreaterole: false, rolcreatedb: false, rolbypassrls: false });
    assert.equal((await runtime.query(
      "SELECT pg_has_role(current_user,nspowner,'MEMBER') AS owns FROM pg_namespace WHERE nspname='app'",
    )).rows[0].owns, false);
    assert.deepEqual((await runtime.query(`SELECT
      has_schema_privilege(current_user,'app','USAGE') AS usage,
      has_schema_privilege(current_user,'app','CREATE') AS create`)).rows[0], { usage: true, create: false });
    const relations = (await runtime.query(`SELECT c.relname,
      pg_has_role(current_user,c.relowner,'MEMBER') AS owns,
      has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER') AS writes,
      has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE') AS column_writes
      FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='app' AND c.relkind IN ('r','p')`)).rows;
    assert.ok(relations.length >= 11);
    for (const relation of relations) {
      assert.equal(relation.owns, false, relation.relname);
      assert.equal(relation.writes, false, relation.relname);
      assert.equal(relation.column_writes, false, relation.relname);
    }
    const publicInterfaces = ["capture_line", "observe_source", "register_source_identity",
      "resolve_source_identity", "seal_snapshot", "write_department", "write_purchase_order_line", "write_supplier"];
    const routines = (await runtime.query(`SELECT p.proname,
      pg_has_role(current_user,p.proowner,'MEMBER') AS owns,
      has_function_privilege(current_user,p.oid,'EXECUTE') AS executable
      FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='app'`)).rows;
    assert.deepEqual(routines.filter((r) => r.executable).map((r) => r.proname).sort(), publicInterfaces);
    for (const routine of routines) assert.equal(routine.owns, false, routine.proname);
    await runtime.query("BEGIN");
    for (const sql of [
      "UPDATE app.purchase_order_lines SET description='bypass' WHERE id=$1",
      "UPDATE app.purchase_order_lines SET current_version_id=current_version_id WHERE id=$1",
      "INSERT INTO app.source_references(source_namespace,source_entity_kind) VALUES ('synthetic','supplier')",
      "INSERT INTO app.decision_snapshots(root_record_version_id,actor_user_id,knowledge_cutoff_at,captured_at) VALUES (gen_random_uuid(),gen_random_uuid(),now(),now())",
      "DELETE FROM app.record_versions WHERE purchase_line_owner_id=$1",
      "TRUNCATE app.audit_events",
      "ALTER TABLE app.audit_events DISABLE TRIGGER ALL",
      "SELECT app.internal_write_record('supplier',NULL,NULL,'{}',NULL,NULL,NULL,NULL,NULL,NULL,NULL)",
    ]) await rejectsSQL(runtime, sql, sql.includes("$1") ? [data.line.entity_id] : [], "42501");
    const result = await runtime.query("SELECT * FROM app.write_supplier(NULL,NULL,'{\"name\":\"SYNTHETIC runtime\"}',$1)", [data.actor]);
    assert.equal(result.rows[0].revision_no, 1);
    const snapshot = (await runtime.query("SELECT app.capture_line($1,$2) AS id",
      [data.line.entity_id, data.actor])).rows[0].id;
    const sealed = (await runtime.query("SELECT app.seal_snapshot($1,$2) AS hash", [snapshot, data.actor])).rows[0].hash;
    assert.match(sealed, /^[a-f0-9]{64}$/);
    await runtime.query("SET CONSTRAINTS ALL IMMEDIATE");
  } finally {
    await runtime.query("ROLLBACK").catch(() => {});
    await owner.query("ROLLBACK").catch(() => {});
    await runtime.end(); await owner.end();
  }
});
