import assert from "node:assert/strict";
import test from "node:test";
import { connect, fixture, inTransaction, readTestTarget, rejectsSQL, waitForBlocked, writeLine } from "./helpers.mjs";

readTestTarget();

test("capture has exactly one root, existing contexts and a reproducible sealed hash", async () => {
  await inTransaction(async (client, data) => {
    const snapshot = (await client.query("SELECT app.capture_line($1,$2) AS id",
      [data.line.entity_id, data.actor])).rows[0].id;
    assert.deepEqual((await client.query(
      "SELECT role FROM app.snapshot_members WHERE snapshot_id=$1 ORDER BY role", [snapshot],
    )).rows.map((r) => r.role), ["department_context", "root", "supplier_context"]);
    const expected = (await client.query("SELECT app.snapshot_digest($1) AS hash", [snapshot])).rows[0].hash;
    await rejectsSQL(client,
      "UPDATE app.decision_snapshots SET status='sealed',content_hash=$2 WHERE id=$1",
      [snapshot, expected], "23514");
    const actual = (await client.query("SELECT app.seal_snapshot($1,$2) AS hash",
      [snapshot, data.actor])).rows[0].hash;
    assert.equal(actual, expected);
    assert.match(actual, /^[a-f0-9]{64}$/);
    for (const sql of [
      "UPDATE app.decision_snapshots SET status='draft',sealed_at=NULL,content_hash=NULL WHERE id=$1",
      "DELETE FROM app.snapshot_members WHERE snapshot_id=$1",
      "UPDATE app.snapshot_members SET role='supplier_context' WHERE snapshot_id=$1",
    ]) await rejectsSQL(client, sql, [snapshot], "55000");
    await rejectsSQL(client, "SELECT app.seal_snapshot($1,$2)", [snapshot, data.actor], "55000");
  });
});

test("missing or conflicting context, invalid root and wrong isolation are rejected", async () => {
  await inTransaction(async (client, data) => {
    const id = (await client.query("SELECT app.capture_line($1,$2) AS id",
      [data.line.entity_id, data.actor])).rows[0].id;
    await rejectsSQL(client,
      "INSERT INTO app.snapshot_members(snapshot_id,record_version_id,purchase_line_owner_id,role) VALUES ($1,$2,$3,'root')",
      [id, data.line.version_id, data.line.entity_id], "23505");
    await rejectsSQL(client,
      "UPDATE app.decision_snapshots SET root_record_version_id=$2 WHERE id=$1",
      [id, data.supplier.version_id], "23514");
    await client.query("DELETE FROM app.snapshot_members WHERE snapshot_id=$1 AND role='supplier_context'", [id]);
    await rejectsSQL(client, "SELECT app.seal_snapshot($1,$2)", [id, data.actor], "23514");
  });
  const client = await connect();
  try {
    await client.query("BEGIN ISOLATION LEVEL REPEATABLE READ");
    await assert.rejects(client.query("SELECT app.capture_line(gen_random_uuid(),gen_random_uuid())"),
      (error) => error.code === "25001");
  } finally { await client.query("ROLLBACK"); await client.end(); }
});

test("a line without supplier or department yields only the root member", async () => {
  await inTransaction(async (client, data) => {
    const line = await writeLine(client, { actor: data.actor, state: { description: "SYNTHETIC standalone" } });
    const id = (await client.query("SELECT app.capture_line($1,$2) AS id",
      [line.entity_id, data.actor])).rows[0].id;
    assert.equal((await client.query(
      "SELECT count(*)::int AS n FROM app.snapshot_members WHERE snapshot_id=$1", [id])).rows[0].n, 1);
    await client.query("SELECT app.seal_snapshot($1,$2)", [id, data.actor]);
  });
});

for (const [operation, sql] of [
  ["DELETE member", "DELETE FROM app.snapshot_members WHERE snapshot_id=$1 AND role='supplier_context'"],
  ["UPDATE member", "UPDATE app.snapshot_members SET record_version_id=record_version_id WHERE snapshot_id=$1 AND role='supplier_context'"],
  ["INSERT member", "INSERT INTO app.snapshot_members(snapshot_id,record_version_id,supplier_owner_id,role) SELECT snapshot_id,record_version_id,supplier_owner_id,role FROM app.snapshot_members WHERE snapshot_id=$1 AND role='supplier_context'"],
  ["UPDATE root", "UPDATE app.decision_snapshots SET root_record_version_id=root_record_version_id WHERE id=$1"],
]) test(`seal preceding ${operation} serializes and rejects mutation of sealed evidence`, async () => {
  const first = await connect();
  const second = await connect();
  let pending;
  try {
    await first.query("BEGIN");
    const data = await fixture(first);
    const id = (await first.query("SELECT app.capture_line($1,$2) AS id",
      [data.line.entity_id, data.actor])).rows[0].id;
    await first.query("COMMIT");
    await first.query("BEGIN");
    const firstPid = (await first.query("SELECT pg_backend_pid() AS pid")).rows[0].pid;
    const secondPid = (await second.query("SELECT pg_backend_pid() AS pid")).rows[0].pid;
    await first.query("SELECT app.seal_snapshot($1,$2)", [id, data.actor]);
    pending = second.query(sql, [id]).then(
      () => ({ code: "unexpected_success" }), (error) => ({ code: error.code }));
    await waitForBlocked(first, secondPid, firstPid);
    await first.query("COMMIT");
    assert.equal((await pending).code, "55000");
  } finally {
    await first.query("ROLLBACK").catch(() => {});
    if (pending) await pending;
    await first.end(); await second.end();
  }
});

for (const operation of ["INSERT", "UPDATE", "DELETE", "ROOT"]) {
  test(`${operation} preceding seal is observed after the parent's lock is acquired`, async () => {
    const first = await connect();
    const second = await connect();
    let pending;
    try {
      await first.query("BEGIN");
      const data = await fixture(first);
      await first.query("SELECT * FROM app.write_supplier($1,$2,'{\"name\":\"SYNTHETIC context revision\"}',$3)",
        [data.supplier.entity_id, data.supplier.version_id, data.actor]);
      const other = await writeLine(first, { actor: data.actor, supplier: data.supplier.entity_id,
        department: data.department.entity_id, currency: data.currency });
      const id = (await first.query("SELECT app.capture_line($1,$2) AS id",
        [data.line.entity_id, data.actor])).rows[0].id;
      if (operation === "INSERT") {
        await first.query("DELETE FROM app.snapshot_members WHERE snapshot_id=$1 AND role='supplier_context'", [id]);
      }
      await first.query("COMMIT");
      await first.query("BEGIN");
      if (operation === "INSERT") {
        await first.query(`INSERT INTO app.snapshot_members(snapshot_id,record_version_id,supplier_owner_id,role)
          VALUES ($1,$2,$3,'supplier_context')`, [id, data.supplier.version_id, data.supplier.entity_id]);
      } else if (operation === "UPDATE") {
        await first.query("UPDATE app.snapshot_members SET record_version_id=$2 WHERE snapshot_id=$1 AND role='supplier_context'",
          [id, data.supplier.version_id]);
      } else if (operation === "DELETE") {
        await first.query("DELETE FROM app.snapshot_members WHERE snapshot_id=$1 AND role='supplier_context'", [id]);
      } else {
        await first.query("DELETE FROM app.snapshot_members WHERE snapshot_id=$1 AND role='root'", [id]);
        await first.query(`INSERT INTO app.snapshot_members(snapshot_id,record_version_id,purchase_line_owner_id,role)
          VALUES ($1,$2,$3,'root')`, [id, other.version_id, other.entity_id]);
        await first.query("UPDATE app.decision_snapshots SET root_record_version_id=$2 WHERE id=$1", [id, other.version_id]);
      }
      const firstPid = (await first.query("SELECT pg_backend_pid() AS pid")).rows[0].pid;
      const secondPid = (await second.query("SELECT pg_backend_pid() AS pid")).rows[0].pid;
      pending = second.query("SELECT app.seal_snapshot($1,$2) AS hash", [id, data.actor]).then(
        (result) => ({ hash: result.rows[0].hash }), (error) => ({ code: error.code }));
      await waitForBlocked(first, secondPid, firstPid);
      await first.query("COMMIT");
      const result = await pending;
      const stored = (await first.query(`SELECT status,content_hash,root_record_version_id,
        app.snapshot_digest(id) AS actual_hash FROM app.decision_snapshots WHERE id=$1`, [id])).rows[0];
      if (operation === "DELETE") {
        assert.equal(result.code, "23514");
        assert.equal(stored.status, "draft");
        assert.equal(stored.content_hash, null);
        assert.equal((await first.query("SELECT count(*)::int AS n FROM app.audit_events WHERE snapshot_id=$1 AND operation='seal'",
          [id])).rows[0].n, 0);
      } else {
        assert.match(result.hash, /^[a-f0-9]{64}$/);
        assert.equal(stored.content_hash, result.hash);
        assert.equal(stored.actual_hash, result.hash);
        assert.equal(stored.status, "sealed");
        assert.equal(stored.root_record_version_id, operation === "ROOT" ? other.version_id : data.line.version_id);
      }
    } finally {
      await first.query("ROLLBACK").catch(() => {});
      if (pending) await pending;
      await first.end(); await second.end();
    }
  });
}

for (const kind of ["line", "supplier", "department"]) {
  for (const captureFirst of [false, true]) {
    test(`capture vs ${kind} revision, capture first=${captureFirst}, retains the heads read under lock`, async () => {
      const first = await connect();
      const second = await connect();
      let pending;
      try {
        await first.query("BEGIN");
        const data = await fixture(first);
        await first.query("COMMIT");
        const revise = (client) => kind === "line"
          ? writeLine(client, { actor: data.actor, id: data.line.entity_id, expected: data.line.version_id,
            supplier: data.supplier.entity_id, department: data.department.entity_id, currency: data.currency })
          : client.query(`SELECT * FROM app.write_${kind}($1,$2,$3,$4)`, [
            data[kind].entity_id, data[kind].version_id,
            JSON.stringify({ name: "SYNTHETIC competing context" }), data.actor,
          ]).then((result) => result.rows[0]);
        const capture = (client) => client.query("SELECT app.capture_line($1,$2) AS id",
          [data.line.entity_id, data.actor]).then((result) => result.rows[0]);
        await first.query("BEGIN");
        const held = await (captureFirst ? capture(first) : revise(first));
        const firstPid = (await first.query("SELECT pg_backend_pid() AS pid")).rows[0].pid;
        const secondPid = (await second.query("SELECT pg_backend_pid() AS pid")).rows[0].pid;
        pending = (captureFirst ? revise(second) : capture(second)).then(
          (value) => ({ value }), (error) => ({ code: error.code }));
        await waitForBlocked(first, secondPid, firstPid);
        await first.query("COMMIT");
        const result = await pending;
        assert.equal(result.code, undefined);
        const snapshot = captureFirst ? held.id : result.value.id;
        const role = kind === "line" ? "root" : `${kind}_context`;
        const version = captureFirst ? data[kind].version_id : held.version_id;
        assert.equal((await first.query("SELECT record_version_id FROM app.snapshot_members WHERE snapshot_id=$1 AND role=$2",
          [snapshot, role])).rows[0].record_version_id, version);
        await first.query("SELECT app.seal_snapshot($1,$2)", [snapshot, data.actor]);
      } finally {
        await first.query("ROLLBACK").catch(() => {});
        if (pending) await pending;
        await first.end(); await second.end();
      }
    });
  }
}

test("a new operational revision does not rewrite a snapshot while it is being sealed", async () => {
  const first = await connect();
  const second = await connect();
  try {
    await first.query("BEGIN");
    const data = await fixture(first);
    const snapshot = (await first.query("SELECT app.capture_line($1,$2) AS id",
      [data.line.entity_id, data.actor])).rows[0].id;
    await first.query("COMMIT");
    await first.query("BEGIN");
    const sealed = (await first.query("SELECT app.seal_snapshot($1,$2) AS hash", [snapshot, data.actor])).rows[0].hash;
    const next = await writeLine(second, { actor: data.actor, id: data.line.entity_id,
      expected: data.line.version_id, currency: data.currency });
    assert.equal(next.revision_no, 2);
    await first.query("COMMIT");
    const stored = (await first.query("SELECT root_record_version_id,content_hash,app.snapshot_digest(id) AS actual FROM app.decision_snapshots WHERE id=$1",
      [snapshot])).rows[0];
    assert.deepEqual(stored, { root_record_version_id: data.line.version_id, content_hash: sealed, actual: sealed });
  } finally {
    await first.query("ROLLBACK").catch(() => {});
    await first.end(); await second.end();
  }
});
