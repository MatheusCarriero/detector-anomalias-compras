import { Socket } from 'node:net';
import { catalogChecks } from './catalog-checks.js';
import { syntheticCatalog } from './catalog-fixtures.js';
import { canonicalExpression } from './catalog-expression.js';

describe('catalog inspections with synthetic projections and blocked sockets', () => {
  let attempts = 0;
  beforeEach(() => {
    attempts = 0;
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
      attempts++; throw new Error('Offline network guard');
    });
  });
  afterEach(() => { expect(attempts).toBe(0); vi.restoreAllMocks(); });
  it.each(catalogChecks)('accepts the complete approved projection: $code', (check) => {
    expect(() => check.validate(syntheticCatalog()[check.code])).not.toThrow();
  });
  it.each(catalogChecks)('rejects empty/malformed/duplicated results: $code', (check) => {
    const result = syntheticCatalog()[check.code];
    for (const value of [null, {}, [null], [], [...result, result[0]]]) {
      expect(() => check.validate(value)).toThrow(/DB_TEST: CATALOG_/);
    }
  });
  it.each(catalogChecks)('rejects every false permission/property flag: $code', (check) => {
    const fixture = syntheticCatalog()[check.code];
    for (const [i, row] of fixture.entries()) {
      for (const [key, value] of Object.entries(row)) {
        if (value === true && (key.endsWith('_safe') || key.startsWith('no_') || key === 'triggers_protected')) {
          for (const invalid of [false, null, 'true', 1]) {
            const broken = structuredClone(fixture); broken[i][key] = invalid;
            const expected = check.code === 'CATALOG_DEFAULT_ACL' && invalid !== false
              ? 'CATALOG_RESULT_SHAPE' : check.code;
            expect(() => check.validate(broken)).toThrow(`DB_TEST: ${expected}`);
          }
        }
      }
    }
  });
  it.each([
    ['CATALOG_FUNCTIONS', 'write_supplier', 'args', ['uuid']],
    ['CATALOG_FUNCTIONS', 'capture_line', 'input_names', ['wrong_name', 'actor']],
    ['CATALOG_FUNCTIONS', 'write_supplier', 'output_types', ['text', 'uuid', 'integer']],
    ['CATALOG_FUNCTIONS', 'write_supplier', 'output_modes', ['o', 'o', 'o']],
    ['CATALOG_FUNCTIONS', 'write_supplier', 'defaults_expression', 'NULL::text'],
    ['CATALOG_FUNCTIONS', 'write_supplier', 'definer', false],
    ['CATALOG_FUNCTIONS', 'write_supplier', 'executable', false],
    ['CATALOG_FUNCTIONS', 'internal_write_record', 'executable', true],
    ['CATALOG_FUNCTIONS', 'write_supplier', 'config', ['search_path=public, app']],
    ['CATALOG_FUNCTIONS', 'write_supplier', 'body', 'SELECT secret_sentinel'],
    ['CATALOG_CONSTRAINTS', 'departments_head_fk', 'deferred', false],
    ['CATALOG_CONSTRAINTS', 'snapshot_members_supplier_fk', 'foreign_columns', ['id', 'department_owner_id']],
    ['CATALOG_CONSTRAINTS', 'record_versions_chain_check', 'expression', 'revision_no > 0 OR ((revision_no = 1) = (supersedes_version_id IS NULL))'],
    ['CATALOG_INDEXES', 'snapshot_members_supplier_once', 'predicate', 'supplier_owner_id IS NULL'],
    ['CATALOG_INDEXES', 'snapshot_members_supplier_once', 'unique', false],
    ['CATALOG_TRIGGERS', 'record_versions_consistency', 'type', 21],
    ['CATALOG_TRIGGERS', 'record_versions_consistency', 'deferred', false],
    ['CATALOG_TRIGGERS', 'record_versions_consistency', 'function_name', 'deny_mutation'],
    ['CATALOG_TRIGGERS', 'suppliers_projection', 'args_hex', '00'],
    ['CATALOG_COLUMNS', 'amount', 'type', 'double precision'],
    ['CATALOG_COLUMNS', 'recorded_at', 'not_null', false],
  ])('rejects contract drift in %s/%s/%s', (code, name, field, invalid) => {
    const fixture = syntheticCatalog()[code as string];
    const row = fixture.find((r) => r.name === name)!;
    row[field as string] = invalid;
    const check = catalogChecks.find((c) => c.code === code)!;
    let caught: unknown;
    try { check.validate(fixture); } catch (error) { caught = error; }
    expect(caught).toMatchObject({ diagnosticCode: code });
    expect(String(caught)).not.toContain('secret_sentinel');
    expect(caught).not.toHaveProperty('cause');
  });
  it('rejects an added overload even when its name is authorized', () => {
    const fixture = syntheticCatalog().CATALOG_FUNCTIONS;
    fixture.push({ ...fixture.find((r) => r.name === 'write_supplier')!, args: ['text'] });
    expect(() => catalogChecks[2].validate(fixture)).toThrow('CATALOG_FUNCTIONS');
  });
  it('accepts PostgreSQL default casts and zero-argument defaults', () => {
    expect(canonicalExpression('gen_random_uuid()')).toBe(canonicalExpression('pg_catalog.gen_random_uuid()'));
    const fixture = syntheticCatalog().CATALOG_COLUMNS;
    fixture.filter((r) => typeof r.default_expression === 'string' && r.default_expression.startsWith("'"))
      .forEach((r) => { r.default_expression += '::text'; });
    expect(() => catalogChecks[3].validate(fixture)).not.toThrow();
  });
  it('does not erase whitespace inside function literals', () => {
    const fixture = syntheticCatalog().CATALOG_FUNCTIONS;
    fixture[0].body = String(fixture[0].body).replace('Immutable evidence', 'Immutable  evidence');
    expect(() => catalogChecks[2].validate(fixture)).toThrow('CATALOG_FUNCTIONS');
  });
  it('uses only fixed catalog SELECTs, never business tables or callable app functions', () => {
    for (const check of catalogChecks) {
      expect(check.sql.trim()).toMatch(/^SELECT\b/);
      expect(check.sql).not.toMatch(/;|\b(?:INSERT|UPDATE|DELETE|TRUNCATE|CALL|SET|CREATE|ALTER|DROP)\s+(?:app\.|TABLE|ROLE)|\b(?:FROM|JOIN)\s+app\./i);
      expect(check.sql).not.toMatch(/\bapp\.\w+\s*\(/i);
      expect(check.sql).not.toMatch(/(?<![.\w])(?:unnest|generate_subscripts|current_database)\(/);
    }
  });
  it('keeps the outer constraint alias visible in ordered key projections', () => {
    const query = catalogChecks.find((c) => c.code === 'CATALOG_CONSTRAINTS')!.sql;
    expect(query).toContain('a.attrelid=k.conrelid AND a.attnum=key_column.num');
    expect(query).toContain('a.attrelid=k.confrelid AND a.attnum=key_column.num');
    expect(query).not.toMatch(/WITH ORDINALITY k\(/);
  });
  // Expected projections based on PostgreSQL 18 semantics, not SQL execution:
  // https://www.postgresql.org/docs/18/sql-alterdefaultprivileges.html
  // https://www.postgresql.org/docs/18/catalog-pg-default-acl.html
  it.each([
    ['built-in global PUBLIC EXECUTE after only a schema REVOKE', false, true, 'FUNCTIONS'],
    ['existing-function REVOKE with unchanged future defaults', false, true, 'FUNCTIONS'],
    ['global EXECUTE granted directly to runtime', false, true, 'FUNCTIONS'],
    ['schema EXECUTE grant added to restricted global defaults', false, true, 'FUNCTIONS'],
    ['table DML granted to runtime', true, false, 'TABLES'],
    ['table SELECT WITH GRANT OPTION granted to runtime', true, false, 'TABLES'],
    ['table SELECT granted to PUBLIC', true, false, 'TABLES'],
    ['unsafe function and table defaults', false, false, 'BOTH'],
  ])('rejects the synthetic projection for %s with a specific safe category', (_, functions_safe, tables_safe, suffix) => {
    const check = catalogChecks.find((c) => c.code === 'CATALOG_DEFAULT_ACL')!;
    expect(() => check.validate([{ functions_safe, tables_safe }]))
      .toThrow(`DB_TEST: CATALOG_DEFAULT_ACL_${suffix}`);
  });
  it.each([
    [{ tables_safe: true }], [{ functions_safe: true }],
    [{ functions_safe: false, tables_safe: 'PRIVATE_SENTINEL' }],
  ])('rejects incomplete or nonboolean ACL projections before drawing a privilege conclusion (%#)', (row) => {
    const check = catalogChecks.find((c) => c.code === 'CATALOG_DEFAULT_ACL')!;
    expect(() => check.validate([row])).toThrow('DB_TEST: CATALOG_RESULT_SHAPE');
  });
  it('inspects creator-scoped global defaults and additive schema grants, including hard-wired fallback', () => {
    const query = catalogChecks.find((c) => c.code === 'CATALOG_DEFAULT_ACL')!.sql;
    for (const type of ['f', 'r']) {
      expect(query).toContain(`d.defaclrole=n.nspowner AND d.defaclnamespace=0 AND d.defaclobjtype='${type}'`);
      expect(query).toContain(`pg_catalog.acldefault('${type}',n.nspowner)`);
      expect(query).toContain(`d.defaclrole=n.nspowner AND d.defaclnamespace=n.oid AND d.defaclobjtype='${type}'`);
    }
    expect(query.match(/UNION ALL/g)).toHaveLength(2);
    expect(query).toContain("acl.privilege_type<>'SELECT' OR acl.is_grantable");
    expect(query).toContain("acl.grantee=0 OR acl.grantee=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user)");
  });
});
