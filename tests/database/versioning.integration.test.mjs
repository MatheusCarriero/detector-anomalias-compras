import assert from "node:assert/strict";
import test from "node:test";
import { connect, fixture, inTransaction, readTestTarget, rejectsSQL, waitForBlocked, writeLine } from "./helpers.mjs";

readTestTarget();

test("revision atomically advances head, projection and audit with real deferred checks", async () => {
  await inTransaction(async (client, data) => {
    assert.equal(data.line.revision_no, 1);
    const next = await writeLine(client, {
      actor: data.actor, id: data.line.entity_id, expected: data.line.version_id,
      currency: data.currency, state: { description: "SYNTHETIC revised", amount: "9.125" },
    });
    assert.equal(next.revision_no, 2);
    await client.query("SET CONSTRAINTS ALL IMMEDIATE");
    const { rows: [row] } = await client.query(
      "SELECT l.description,l.amount::text,l.current_version_id,v.supersedes_version_id,a.before_version_id FROM app.purchase_order_lines l JOIN app.record_versions v ON v.id=l.current_version_id JOIN app.audit_events a ON a.after_version_id=v.id WHERE l.id=$1",
      [data.line.entity_id]);
    assert.deepEqual(row, {
      description: "SYNTHETIC revised", amount: "9.125000", current_version_id: next.version_id,
      supersedes_version_id: data.line.version_id, before_version_id: data.line.version_id,
    });
    await rejectsSQL(client, "SELECT * FROM app.write_purchase_order_line($1,$2,'{}',NULL,NULL,NULL,$3)",
      [data.line.entity_id, data.line.version_id, data.actor], "40001");
  });
});

test("malformed chains, foreign heads and divergence cannot commit", async () => {
  await inTransaction(async (client, data) => {
    for (const [sql, values, code] of [
      ["UPDATE app.purchase_order_lines SET description='tampered' WHERE id=$1", [data.line.entity_id], "23514"],
      ["UPDATE app.purchase_order_lines SET current_version_id=$2 WHERE id=$1",
        [data.line.entity_id, data.supplier.version_id], "23503"],
      ["UPDATE app.record_versions SET payload='{}' WHERE id=$1", [data.line.version_id], "55000"],
      ["DELETE FROM app.record_versions WHERE id=$1", [data.line.version_id], "55000"],
      ["DELETE FROM app.audit_events WHERE after_version_id=$1", [data.line.version_id], "55000"],
      ["INSERT INTO app.record_versions(purchase_line_owner_id,revision_no,payload,actor_user_id) VALUES ($1,1,'{}',$2)",
        [data.line.entity_id, data.actor], "23514"],
      ["INSERT INTO app.record_versions(purchase_line_owner_id,revision_no,payload,actor_user_id) VALUES ($1,2,'{}',$2)",
        [data.line.entity_id, data.actor], "23514"],
      ["INSERT INTO app.record_versions(purchase_line_owner_id,revision_no,supersedes_version_id,payload,actor_user_id) VALUES ($1,2,$2,'{}',$3)",
        [data.line.entity_id, data.supplier.version_id, data.actor], "23514"],
      ["INSERT INTO app.record_versions(purchase_line_owner_id,revision_no,supersedes_version_id,payload,actor_user_id) VALUES ($1,3,$2,'{}',$3)",
        [data.line.entity_id, data.line.version_id, data.actor], "23514"],
    ]) await rejectsSQL(client, sql, values, code);

    // Identical business state isolates the terminal-head invariant from payload mismatch.
    await writeLine(client, { actor: data.actor, id: data.line.entity_id, expected: data.line.version_id,
      supplier: data.supplier.entity_id, department: data.department.entity_id, currency: data.currency });
    await rejectsSQL(client, "UPDATE app.purchase_order_lines SET current_version_id=$2 WHERE id=$1",
      [data.line.entity_id, data.line.version_id], "23514");
  });
});

test("numeric and temporal inputs are rejected before lossy coercion", async () => {
  await inTransaction(async (client, data) => {
    for (const state of [
      { amount: "1.0000001" }, { quantity: "0.0000001" }, { unit_price: "0.000000001" },
      { amount: "1000000000000000000" }, { amount: "NaN" }, { amount: "Infinity" },
      { amount: 1.25 }, { po_date: "2026-02-30" }, { unknown_field: "do not ignore" },
    ]) {
      await rejectsSQL(client,
        "SELECT * FROM app.write_purchase_order_line(NULL,NULL,$1,NULL,NULL,$2,$3)",
        [JSON.stringify(state), data.currency, data.actor], "22023");
    }
    await rejectsSQL(client,
      "SELECT * FROM app.write_purchase_order_line(NULL,NULL,'{\"amount\":\"1\"}',NULL,NULL,NULL,$1)",
      [data.actor], "23514");
    for (const instant of ["2026-10-01T12:00:00", "2026-10-01T12:00:00.0001Z"]) {
      await rejectsSQL(client,
        "SELECT * FROM app.write_supplier(NULL,NULL,'{\"name\":\"SYNTHETIC\"}',$1,NULL,$2,NULL)",
        [data.actor, instant], "22023");
    }
  });
});

test("failed write rolls back projection, version and audit together", async () => {
  await inTransaction(async (client, data) => {
    const stateSQL = `SELECT to_jsonb(l) AS projection,
      (SELECT count(*) FROM app.record_versions) AS versions,
      (SELECT count(*) FROM app.audit_events) AS events FROM app.purchase_order_lines l WHERE id=$1`;
    const before = (await client.query(stateSQL, [data.line.entity_id])).rows[0];
    // Test-only fault injection, rolled back with this transaction. The failure occurs
    // only after the new version AND operational projection have both been written.
    await client.query(`CREATE FUNCTION pg_temp.reject_synthetic_audit() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
        IF NEW.operation='revise' THEN
          IF NOT EXISTS(SELECT 1 FROM app.purchase_order_lines l JOIN app.record_versions v
            ON v.id=l.current_version_id WHERE v.id=NEW.after_version_id AND v.revision_no=2) THEN
            RAISE EXCEPTION 'Fault injection did not reach the updated projection' USING ERRCODE='22000';
          END IF;
          RAISE EXCEPTION 'SYNTHETIC audit failure after projection write' USING ERRCODE='P0001';
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER synthetic_audit_failure BEFORE INSERT ON app.audit_events
      FOR EACH ROW EXECUTE FUNCTION pg_temp.reject_synthetic_audit()`);
    await rejectsSQL(client,
      "SELECT * FROM app.write_purchase_order_line($1,$2,'{\"description\":\"SYNTHETIC must rollback\"}',NULL,NULL,NULL,$3)",
      [data.line.entity_id, data.line.version_id, data.actor], "P0001");
    assert.deepEqual((await client.query(stateSQL, [data.line.entity_id])).rows[0], before);
  });
});

test("different owners can advance independently while another writer holds its lock", async () => {
  const first = await connect();
  const second = await connect();
  try {
    await first.query("BEGIN");
    const data = await fixture(first);
    const other = await writeLine(first, { actor: data.actor, state: { description: "SYNTHETIC independent" } });
    await first.query("COMMIT");
    await first.query("BEGIN");
    await writeLine(first, { actor: data.actor, id: data.line.entity_id,
      expected: data.line.version_id, currency: data.currency });
    // Must finish before the first transaction releases its different owner.
    const result = await writeLine(second, { actor: data.actor, id: other.entity_id,
      expected: other.version_id, state: { description: "SYNTHETIC independent revision" } });
    assert.equal(result.revision_no, 2);
    await first.query("COMMIT");
  } finally {
    await first.query("ROLLBACK").catch(() => {});
    await first.end(); await second.end();
  }
});

test("two real sessions cannot create two successors of the same head", async () => {
  const first = await connect();
  const second = await connect();
  let pending;
  try {
    await first.query("BEGIN");
    const data = await fixture(first);
    await first.query("COMMIT"); // Synthetic fixtures remain in the dedicated database.
    await first.query("BEGIN");
    const firstPid = (await first.query("SELECT pg_backend_pid() AS pid")).rows[0].pid;
    const secondPid = (await second.query("SELECT pg_backend_pid() AS pid")).rows[0].pid;
    await writeLine(first, { actor: data.actor, id: data.line.entity_id,
      expected: data.line.version_id, currency: data.currency });
    pending = writeLine(second, { actor: data.actor, id: data.line.entity_id,
      expected: data.line.version_id, currency: data.currency }).then(
        () => ({ code: "unexpected_success" }), (error) => ({ code: error.code }));
    await waitForBlocked(first, secondPid, firstPid);
    await first.query("COMMIT");
    assert.equal((await pending).code, "40001");
    assert.equal((await first.query(
      "SELECT count(*)::int AS n FROM app.record_versions WHERE purchase_line_owner_id=$1",
      [data.line.entity_id])).rows[0].n, 2);
  } finally {
    await first.query("ROLLBACK").catch(() => {});
    if (pending) await pending;
    await first.end();
    await second.end();
  }
});
