import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

const root = new URL('../../../', import.meta.url);
const read = (path: string) => readFileSync(new URL(path, root), 'utf8').replaceAll('\r\n', '\n');
const sql = read('prisma/migrations/20261119000100_p4_comparability/migration.sql');
const functions = [...sql.matchAll(/CREATE FUNCTION app\.(\w+)\(([^)]*)\) RETURNS ([\s\S]*?)\nLANGUAGE (\w+)([\s\S]*?) AS \$\$([\s\S]*?)\$\$;/g)];
const body = (name: string) => {
  const found = functions.find(f => f[1] === name);
  if (!found) throw new Error(`Missing SQL contract: ${name}`);
  return found[6];
};

describe('comparability migration: static contracts, never SQL execution', () => {
  it.each([
    ['20261020000100_first_increment', '4bc2d19996d1adc10ab05a68eeb17b78153e3725c8d0bcb1c6781fc88848311f'],
    ['20261116000100_p4_read_interfaces', 'c63333bbd5a025c64b51ab60fb2ac02b4c8c5df90dd7843c54361f48ad6291aa'],
  ])('preserves the approved LF hash of %s', (migration, hash) => {
    expect(createHash('sha256').update(read(`prisma/migrations/${migration}/migration.sql`)).digest('hex')).toBe(hash);
  });

  it('installs tables and grants atomically without changing previous objects/default privileges', () => {
    expect(sql.trim().startsWith('BEGIN;')).toBe(true);
    expect(sql.trim().endsWith('COMMIT;')).toBe(true);
    expect([...sql.matchAll(/CREATE TABLE app\.(\w+)/g)].map(m => m[1])).toEqual([
      'p4_comparability_definitions', 'p4_comparability_revisions',
    ]);
    expect(sql).not.toMatch(/CREATE OR REPLACE|ALTER DEFAULT PRIVILEGES|ALTER TABLE|DROP |CREATE ROLE|GRANT (?:SELECT|INSERT|UPDATE|DELETE)/i);
    expect(sql).not.toMatch(/UPDATE app\.|DELETE FROM app\.|EXECUTE format/i);
  });

  it('allows only the two public function signatures and keeps eight helpers private', () => {
    expect(functions).toHaveLength(10);
    expect(functions.filter(f => f[5].includes('SECURITY DEFINER')).map(f => f[1]).sort()).toEqual(['p4_cmp_read', 'p4_cmp_write']);
    expect(sql.match(/GRANT EXECUTE[\s\S]*?;/g)).toEqual([
      'GRANT EXECUTE ON FUNCTION app.p4_cmp_write(text,jsonb),app.p4_cmp_read(uuid,integer) TO detector_runtime;',
    ]);
    const revokes = sql.slice(sql.indexOf('REVOKE ALL ON FUNCTION'));
    for (const f of functions) {
      expect(f[5]).toContain('SET search_path=pg_catalog,app,pg_temp');
      expect(revokes).toContain(`app.${f[1]}(`);
    }
    expect(revokes).toContain('FROM PUBLIC,detector_runtime;');
    expect(sql).toContain('REVOKE ALL ON TABLE app.p4_comparability_definitions,app.p4_comparability_revisions FROM PUBLIC,detector_runtime;');
  });

  it('checks the owner, schema CREATE, effective defaults and dependency ownership', () => {
    expect(sql).toContain("current_user<>'detector_migrator'");
    expect(sql).toContain("pg_catalog.pg_has_role(r.oid,owner_oid,'SET')");
    expect(sql).toContain("pg_catalog.has_schema_privilege(r.oid,schema_oid,'CREATE')");
    expect(sql).toContain('AND proowner<>owner_oid');
    expect(sql).toContain('acl WHERE grantee<>owner_oid');
    expect(sql).toContain('IF NOT defaults_safe');
  });

  it('serializes on the purchase before checking or inserting any metadata revision', () => {
    const write = body('p4_cmp_write');
    const lock = write.indexOf('FROM app.purchase_order_lines WHERE id=purchase FOR UPDATE');
    expect(lock).toBeGreaterThan(0);
    expect(lock).toBeLessThan(write.indexOf('INTO existing'));
    expect(lock).toBeLessThan(write.indexOf('INTO head'));
    expect(lock).toBeLessThan(write.indexOf('INSERT INTO app.p4_comparability_revisions'));
    expect(write).toContain('PERFORM app.require_read_committed()');
    expect(write).toContain('ORDER BY revision DESC LIMIT 1');
    expect(write).toContain('head.revision+1');
    expect(write).toContain("content#>>'{supersedes,content_sha256}' IS DISTINCT FROM head.content_sha256");
  });

  it('enforces owner/version linkage and predecessor identity/hash with real FKs and uniqueness', () => {
    expect(sql).toContain('UNIQUE (purchase_id,revision)');
    expect(sql).toContain('UNIQUE (previous_id)');
    expect(sql).toContain('FOREIGN KEY (purchase_version_id,purchase_id) REFERENCES app.record_versions(id,purchase_line_owner_id)');
    expect(sql).toContain('FOREIGN KEY (previous_id,purchase_id,previous_revision,previous_hash)');
    expect(sql).toContain('REFERENCES app.p4_comparability_revisions(id,purchase_id,revision,content_sha256)');
    expect(sql).not.toMatch(/ON DELETE (?:CASCADE|SET NULL)|ON UPDATE CASCADE/);
  });

  it.each(['p4_comparability_definitions', 'p4_comparability_revisions'])('preserves %s against update, delete and truncate', table => {
    expect(sql).toContain(`CREATE TRIGGER immutable_rows BEFORE UPDATE OR DELETE ON app.${table}\n  FOR EACH ROW EXECUTE FUNCTION app.deny_mutation()`);
    expect(sql).toContain(`CREATE TRIGGER preserve_table BEFORE TRUNCATE ON app.${table}\n  FOR EACH STATEMENT EXECUTE FUNCTION app.deny_mutation()`);
  });

  it('validates namespace/receipt and accepts declared provenance only, never verified input', () => {
    expect(body('p4_cmp_validate')).toContain("p_content->>'contract'='p4-manual-comparability/1.0'");
    expect(body('p4_cmp_validate')).toContain("prov->>'kind'='declared'");
    expect(body('p4_cmp_validate')).toContain("ARRAY['kind','actor_id','declared_at'],ARRAY['evidence_ref']");
    expect(body('p4_cmp_write')).toContain('app.p4_v1_checked_receipt(purchase)');
    expect(body('p4_cmp_read')).toContain('app.p4_v1_checked_receipt(p_purchase)');
    expect(body('p4_cmp_read')).not.toMatch(/INSERT INTO|FOR UPDATE|UPDATE app\./);
  });

  it('preserves original definitions, canonical content and SHA-256 without upserts that mutate data', () => {
    const write = body('p4_cmp_write');
    expect(write).toContain('p_canonical=app.p4_cmp_canonical(content)');
    expect(write).toContain('ON CONFLICT (kind,definition_id,definition_version) DO NOTHING');
    expect(write).toContain('d.declared_value=v AND d.original_text=p_definitions->>k');
    expect(write).toContain('ORDER BY key COLLATE "C"');
    expect(write).not.toContain('DO UPDATE');
    expect(body('p4_cmp_definitions')).toContain("p_content#>>'{attributes,specification,value,sha256}'");
  });

  it('replays identical snapshots without generating another origin/audit entry', () => {
    const write = body('p4_cmp_write');
    expect(write).toContain('existing.canonical_content<>p_canonical OR existing.definitions<>p_definitions');
    expect(write.indexOf("'outcome','replay'")).toBeLessThan(write.indexOf('app.observe_source('));
    expect(write).toContain("actor:=(app.p4_v1_context()#>>'{actor,id}')::uuid");
    expect(write).toContain("app.observe_source('p4-comparability/1.0','purchase_order_line',actor,NULL");
  });

  it('read receipts check origin/audit, hashes, definitions and revision links', () => {
    const pack = body('p4_cmp_pack');
    for (const expected of ["s.source_namespace='p4-comparability/1.0'", "s.availability_status='unverified'",
      "a.operation='source_observe'", 'a.actor_user_id=r.actor_user_id', 's.available_at IS NULL',
      'r.previous_id::text', 'r.previous_hash', 'r.previous_revision', 's.original_content=', 'd.declared_value=v']) {
      expect(pack).toContain(expected);
    }
    expect(pack).toContain("USING ERRCODE='23514'");
  });
});
