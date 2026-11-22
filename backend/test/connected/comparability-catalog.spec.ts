import { comparabilityCatalogContract as contract, comparabilityCatalogChecks as checks, comparabilityMigrationHash } from './comparability-catalog.js';
import { catalogContract, migrationHash, p4MigrationHash } from './catalog-contract.js';
import { catalogChecks } from './catalog-checks.js';
import { syntheticCatalog } from './catalog-fixtures.js';
import { canonicalExpression } from './catalog-expression.js';
import { Socket } from 'node:net';

// Synthetic pg_get_expr representations derived from PostgreSQL 18.6 semantics;
// these are not captured database results. Keep them independent of the parser.
const deparsedChecks = [
  ['p4_cmp_definitions_check', `((kind = ANY (ARRAY['specification'::text, 'packaging'::text, 'price_basis'::text, 'delivery'::text, 'quantity_pricing'::text]))
    AND (length(definition_id) >= 1) AND (length(definition_id) <= 200)
    AND (length(definition_version) >= 1) AND (length(definition_version) <= 200)
    AND (jsonb_typeof(declared_value) = 'object'::text)
    AND (octet_length(original_text) >= 1) AND (octet_length(original_text) <= 16000)
    AND (text_sha256 = encode(sha256(convert_to(original_text, 'UTF8'::name)), 'hex'::text)))`],
  ['p4_cmp_content_check', `((purchase_hash ~ '^[0-9a-f]{64}$'::text)
    AND (octet_length(canonical_content) >= 1) AND (octet_length(canonical_content) <= 65536)
    AND (jsonb_typeof(definitions) = 'object'::text)
    AND (content_sha256 = encode(sha256(convert_to(canonical_content, 'UTF8'::name)), 'hex'::text))
    AND isfinite(recorded_at))`],
] as const;

describe('comparability catalog profile (synthetic projections, no PostgreSQL)', () => {
  let networkAttempts = 0;
  beforeEach(() => {
    networkAttempts = 0;
    vi.spyOn(Socket.prototype, 'connect').mockImplementation(() => {
      networkAttempts++; throw new Error('Offline network guard');
    });
  });
  afterEach(() => { expect(networkAttempts).toBe(0); vi.restoreAllMocks(); });
  it('pins the complementary migration and preserves both earlier hashes and contracts', () => {
    expect(comparabilityMigrationHash).toBe('35955a7de1374ba2971ff55f2082ddd6923d3fa9f2b6690ca220b03cb4eae95d');
    expect(migrationHash).toBe('4bc2d19996d1adc10ab05a68eeb17b78153e3725c8d0bcb1c6781fc88848311f');
    expect(p4MigrationHash).toBe('c63333bbd5a025c64b51ab60fb2ac02b4c8c5df90dd7843c54361f48ad6291aa');
    expect(catalogContract.tables).toHaveLength(11); expect(contract.tables).toHaveLength(13);
    expect(contract.functions).toHaveLength(41); expect(contract.triggers).toHaveLength(34);
    expect(contract.functions.filter(f => f.executable)).toHaveLength(14);
    for (const key of ['columns', 'constraints', 'indexes', 'functions', 'triggers'] as const) {
      expect(contract[key].slice(0, catalogContract[key].length)).toEqual(catalogContract[key]);
    }
  });
  it.each(checks)('validates complete simulated $code metadata', c => {
    expect(() => c.validate(syntheticCatalog(contract)[c.code])).not.toThrow();
  });
  it.each(deparsedChecks)('accepts the PG18 encoding cast in the complete %s CHECK', (name, expression) => {
    const rows = syntheticCatalog(contract).CATALOG_CONSTRAINTS;
    rows.find(row => row.name === name)!.expression = expression;
    expect(() => checks.find(c => c.code === 'CATALOG_CONSTRAINTS')!.validate(rows)).not.toThrow();
  });
  it.each([
    ["'UTF8'::name", "'LATIN1'::name"], ["'hex'::text", "'base64'::text"],
    ['sha256(', 'md5('], ['<= 16000', '<= 16001'], [' AND ', ' OR '],
  ])('continues rejecting meaningful CHECK changes (%#)', (from, to) => {
    const rows = syntheticCatalog(contract).CATALOG_CONSTRAINTS;
    rows.find(row => row.name === deparsedChecks[0][0])!.expression = deparsedChecks[0][1].replace(from, to);
    expect(() => checks.find(c => c.code === 'CATALOG_CONSTRAINTS')!.validate(rows))
      .toThrow('DB_TEST: CATALOG_CONSTRAINTS');
  });
  it('does not silently accept the old profile as the new one or vice versa', () => {
    expect(() => checks[1].validate(syntheticCatalog().CATALOG_RELATIONS)).toThrow('CATALOG_RELATIONS');
    expect(() => catalogChecks[1].validate(syntheticCatalog(contract).CATALOG_RELATIONS)).toThrow('CATALOG_RELATIONS');
  });
  it.each([
    ['CATALOG_RELATIONS', 'name', 'p4_comparability_revisions', 'privileges_safe', false],
    ['CATALOG_FUNCTIONS', 'name', 'p4_cmp_pack', 'executable', true],
    ['CATALOG_FUNCTIONS', 'name', 'p4_cmp_write', 'definer', false],
    ['CATALOG_FUNCTIONS', 'name', 'p4_cmp_write', 'grants_safe', false],
    ['CATALOG_FUNCTIONS', 'name', 'p4_cmp_read', 'config', ['search_path=public, app']],
    ['CATALOG_FUNCTIONS', 'name', 'p4_cmp_write', 'body', 'BEGIN RETURN NULL; END'],
    ['CATALOG_CONSTRAINTS', 'name', 'p4_cmp_version_fk', 'columns', ['purchase_id']],
    ['CATALOG_CONSTRAINTS', 'name', 'p4_cmp_previous_fk', 'on_delete', 'c'],
    ['CATALOG_INDEXES', 'name', 'p4_cmp_purchase_revision_key', 'unique', false],
    ['CATALOG_TRIGGERS', 'table', 'p4_comparability_revisions', 'properties_safe', false],
  ])('rejects changed %s %s=%s (%#)', (code, selector, name, field, value) => {
    const rows = syntheticCatalog(contract)[String(code)];
    rows.find(r => r[String(selector)] === name)![String(field)] = value;
    expect(() => checks.find(c => c.code === code)!.validate(rows)).toThrow(/DB_TEST/);
  });
  it('accepts PostgreSQL deparsing of BETWEEN and integer subtraction without losing bounds', () => {
    expect(canonicalExpression('length(definition_id) BETWEEN 1 AND 200 AND revision=previous_revision+1'))
      .toBe(canonicalExpression('(length(definition_id)>=1 AND length(definition_id)<=200) AND revision=(previous_revision + 1)'));
    expect(canonicalExpression('previous_revision=revision-1')).toBe(canonicalExpression('previous_revision = (revision - 1)'));
    expect(canonicalExpression('revision-1')).not.toBe(canonicalExpression('revision+1'));
    expect(canonicalExpression('length(definition_id) BETWEEN 1 AND 200')).not.toBe(canonicalExpression('length(definition_id) BETWEEN 0 AND 200'));
  });
});
