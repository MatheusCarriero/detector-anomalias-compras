import { readFileSync } from 'node:fs';
import { catalogContract, migrationHash, p4MigrationHash } from './catalog-contract.js';
import { PURCHASE_CATALOG } from '../../src/purchases/purchase-catalog.js';

// These checks inspect the SQL artifact; they do NOT execute or simulate PostgreSQL.
// Syntax, effective ACLs, snapshots and transactional behavior need a separate
// authorized connected validation after applying the complementary migration.
const sql = readFileSync(new URL('../../../prisma/migrations/20261116000100_p4_read_interfaces/migration.sql', import.meta.url), 'utf8');
const withoutComments = (text: string) => text.replace(/--[^\r\n]*/g, '');
const compact = (text: string) => withoutComments(text).replace(/\s+/g, ' ').replace(/\s*,\s*/g, ',').trim();
const body = (name: string) => catalogContract.functions.find(fn => fn.name === name)!.body;
const readers = [
  'app.p4_v1_context()', 'app.p4_v1_receipt_by_key(uuid)', 'app.p4_v1_receipt_by_id(uuid)',
  'app.p4_v1_history(integer,timestamptz,uuid)',
];

describe('P4 complementary migration artifact (offline)', () => {
  it('pins both reviewed migrations independently without replacing the original', () => {
    expect(migrationHash).toBe('4bc2d19996d1adc10ab05a68eeb17b78153e3725c8d0bcb1c6781fc88848311f');
    expect(p4MigrationHash).toMatch(/^[a-f0-9]{64}$/);
    expect(p4MigrationHash).not.toBe(migrationHash);
    expect(compact(sql)).toMatch(/^BEGIN;/);
    expect(compact(sql)).toMatch(/COMMIT;$/);
    expect(withoutComments(sql)).not.toMatch(/\b(?:CREATE|ALTER|DROP)\s+(?:TABLE|TRIGGER|INDEX|SCHEMA|ROLE|TYPE)\b/i);
    expect(withoutComments(sql)).not.toMatch(/\b(?:CREATE OR REPLACE|DROP FUNCTION)\b/i);
    expect(catalogContract.tables).toHaveLength(11);
    expect(catalogContract.functions.filter(fn => fn.name.startsWith('p4_'))).toHaveLength(5);
  });

  it('asserts safe effective defaults without changing any creator policy', () => {
    const text = compact(sql);
    expect(text).toContain("pg_catalog.pg_get_userbyid(owner_oid)<>current_user");
    expect(text).toContain("pg_catalog.pg_has_role(runtime_oid,owner_oid,'MEMBER')");
    expect(text).not.toMatch(/ALTER DEFAULT PRIVILEGES/i);
    const preflight = text.slice(0, text.indexOf('CREATE FUNCTION'));
    // NULL global ACL means the built-in PUBLIC EXECUTE default, NOT no grant.
    expect(preflight).toContain("pg_catalog.acldefault('f',owner_oid)");
    expect(preflight).toContain("d.defaclrole=owner_oid AND d.defaclnamespace=0 AND d.defaclobjtype='f'");
    expect(preflight).toContain("d.defaclrole=owner_oid AND d.defaclnamespace=schema_oid AND d.defaclobjtype='f'");
    expect(preflight).toContain('UNION ALL');
    // Require owner EXECUTE too: an empty ACL must not pass vacuously and leave
    // the definer wrappers unable to call their private invoker helper.
    expect(preflight).toContain("COALESCE(pg_catalog.bool_and(a.grantee=owner_oid AND a.privilege_type='EXECUTE'),false)");
    expect(preflight).toContain("IF NOT defaults_safe THEN");
    expect(preflight).toContain("ERRCODE='42501'");
  });

  it('requires a trusted schema including inherited CREATE and SET ROLE capability', () => {
    const preflight = compact(sql).split('CREATE FUNCTION')[0];
    expect(preflight).toContain("pg_catalog.acldefault('n',n.nspowner)");
    expect(preflight).toContain("a.privilege_type='CREATE' AND a.grantee<>owner_oid");
    expect(preflight).toContain('r.oid<>owner_oid AND NOT r.rolsuper');
    expect(preflight).toContain("pg_catalog.has_schema_privilege(r.oid,schema_oid,'CREATE')");
    expect(preflight).toContain("pg_catalog.pg_has_role(r.oid,owner_oid,'SET')");
    expect(preflight).toContain("ERRCODE='42501'");
  });

  it('keeps installation and explicit signature ACLs atomic without table SELECT grants', () => {
    const text = compact(sql);
    expect(text).not.toMatch(/GRANT\s+(?:SELECT|ALL|[\w,]+\s+ON\s+ALL)\b/i);
    const grant = /GRANT EXECUTE ON FUNCTION ([^;]+) TO detector_runtime;/.exec(text);
    expect(grant?.[1]).toBe(readers.join(','));
    expect(text.match(/\bGRANT EXECUTE ON FUNCTION\b/g)).toHaveLength(1);
    expect(text).toContain(`REVOKE ALL ON FUNCTION ${readers[0]},app.p4_v1_checked_receipt(uuid),${readers.slice(1).join(',')} FROM PUBLIC,detector_runtime;`);
    expect(text.lastIndexOf('CREATE FUNCTION')).toBeLessThan(text.indexOf('REVOKE ALL ON FUNCTION'));
    expect(text.indexOf('REVOKE ALL ON FUNCTION')).toBeLessThan(text.indexOf('GRANT EXECUTE ON FUNCTION'));
    expect(text.indexOf('GRANT EXECUTE ON FUNCTION')).toBeLessThan(text.indexOf('COMMIT;'));
  });

  it('keeps all readers read-only, with qualified tables and no dynamic execution', () => {
    for (const fn of catalogContract.functions.filter(fn => fn.name.startsWith('p4_'))) {
      expect(fn).toMatchObject({ language: 'plpgsql', volatility: 's', result: 'jsonb', defaults: 0,
        returns_set: false, config: ['search_path=pg_catalog, app, pg_temp'],
        definer: fn.name !== 'p4_v1_checked_receipt', executable: fn.name !== 'p4_v1_checked_receipt' });
      const text = withoutComments(fn.body).replace(/'(?:[^']|'')*'/g, "''");
      expect(text).not.toMatch(/\b(?:INSERT|UPDATE|DELETE|MERGE|TRUNCATE|EXECUTE|CALL|CREATE|ALTER|DROP)\b/i);
      for (const table of catalogContract.tables) {
        expect(text).not.toMatch(new RegExp(`\\b(?:FROM|JOIN)\\s+${table}\\b`, 'i'));
      }
      expect(text).not.toMatch(/\bapp\.(?:write_\w+|observe_source|register_source_identity|resolve_source_identity|capture_line|seal_snapshot)\s*\(/);
    }
  });

  it('locks catalog labels/units to P4.2 and accepts no arbitrary source namespace or actor', () => {
    const text = body('p4_v1_checked_receipt');
    for (const entry of [...PURCHASE_CATALOG.suppliers, ...PURCHASE_CATALOG.departments]) {
      expect(text).toContain(`('${entry.id}','${entry.name}')`);
      expect(body('p4_v1_context')).toContain(`('${entry.id}','${entry.name}')`);
    }
    for (const entry of PURCHASE_CATALOG.products) {
      expect(text).toContain(`('${entry.id}','${entry.name}','${entry.unit}')`);
    }
    expect(body('p4_v1_context')).toContain("u.auth_issuer='p4-demo' AND u.auth_subject='manual-purchase-service' AND u.is_active");
    expect(text).toContain("reference_row.source_namespace IS DISTINCT FROM 'p4-manual/1.0'");
    expect(text).toContain("reference_row.source_entity_kind IS DISTINCT FROM 'purchase_order_line'");
    expect(text).toContain("reference_row.source_version IS DISTINCT FROM 'p4-purchase/1.0'");
    expect(text).toContain('reference_row.original_content IS DISTINCT FROM expected');
    expect(text).toContain('reference_row.source_record_key IS DISTINCT FROM identity_row.source_id');
    expect(text).toContain('reference_row.source_identity_id IS NOT NULL');
    expect(text).toContain('version_row.payload IS DISTINCT FROM expected');
    expect(text).toContain("AND i.supplier_id=version_row.supplier_id");
    expect(text).toContain("AND i.department_id=version_row.department_id");
  });

  it('checks P4 orphans before returning absence and validates revision one before exposing JSON', () => {
    const checked = body('p4_v1_checked_receipt');
    const key = body('p4_v1_receipt_by_key');
    const history = body('p4_v1_history');
    expect(checked.indexOf("r.source_namespace='p4-manual/1.0'")).toBeLessThan(checked.indexOf('RETURN NULL'));
    expect(key.indexOf('r.source_record_key=p_key::text')).toBeLessThan(key.indexOf("'status','absent'"));
    expect(checked).toContain('v.revision_no=1');
    expect(checked).toContain('count_id<>1');
    expect(checked).toContain('version_row.supersedes_version_id IS NOT NULL');
    expect(checked).toContain("a.operation='create'");
    expect(history).toContain('i.resolved_at IS NULL OR i.purchase_order_line_id IS NULL OR v.id IS NULL');
    expect(history).toContain('AND NOT EXISTS (SELECT 1 FROM app.source_identities i');
    for (const text of [checked, key, history]) expect(text).toContain("ERRCODE='23514'");
  });

  it('rejects future commercial dates against revision registration in the P4 timezone', () => {
    const checked = body('p4_v1_checked_receipt');
    expect(checked).toContain('NOT pg_catalog.isfinite(version_row.recorded_at)');
    const comparison = "app.exact_date(purchase->>'purchase_date') > (version_row.recorded_at AT TIME ZONE 'America/Sao_Paulo')::date";
    expect(checked).toContain(comparison);
    expect(checked.indexOf(comparison)).toBeLessThan(checked.indexOf('RETURN pg_catalog.jsonb_build_object'));
    expect(withoutComments(checked)).not.toMatch(/\b(?:CURRENT_DATE|CURRENT_TIMESTAMP|clock_timestamp|now)\b/i);
    expect(checked).toContain("ERRCODE='23514'");
  });

  it('bounds history with a paired millisecond cursor, stable ordering and one lookahead row', () => {
    const text = body('p4_v1_history');
    expect(text).toContain('p_limit NOT BETWEEN 1 AND 100');
    expect(text).toContain('(p_after_time IS NULL)<>(p_after_id IS NULL)');
    expect(text).toContain('NOT pg_catalog.isfinite(p_after_time)');
    expect(text).toContain("pg_catalog.date_trunc('milliseconds',p_after_time)");
    expect(text).toContain('(v.recorded_at,v.purchase_line_owner_id)<(p_after_time,p_after_id)');
    expect(text).toContain('ORDER BY v.recorded_at DESC,v.purchase_line_owner_id DESC LIMIT p_limit+1');
    expect(text).toContain('receipt:=app.p4_v1_checked_receipt(item.id)');
    expect(text).not.toMatch(/\bOFFSET\b/);
    expect(text).toContain("ERRCODE='22023'");
  });
});
