import { catalogContract } from './catalog-contract.js';
import { canonicalExpression } from './catalog-expression.js';

describe('pinned migration catalog contract (offline)', () => {
  it('describes the approved eleven domain tables and money/temporal types', () => {
    expect(catalogContract.tables).toHaveLength(11);
    expect(catalogContract.columns).toContainEqual({ table: 'purchase_order_lines', name: 'amount', type: 'numeric(24,6)', not_null: false, default_expression: null });
    expect(catalogContract.columns).toContainEqual({ table: 'record_versions', name: 'recorded_at', type: 'timestamp(3) with time zone', not_null: true, default_expression: 'CURRENT_TIMESTAMP' });
  });
  it('preserves composite deferred FKs, partial indexes and CHECK logic', () => {
    expect(catalogContract.constraints.filter((x) => x.deferrable).map((x) => x.name).sort()).toEqual([
      'decision_snapshots_root_fk', 'departments_head_fk', 'purchase_order_lines_head_fk', 'suppliers_head_fk',
    ]);
    expect(catalogContract.constraints.find((x) => x.name === 'snapshot_members_supplier_fk')).toMatchObject({
      columns: ['record_version_id', 'supplier_owner_id'], foreign_table: 'record_versions',
      foreign_columns: ['id', 'supplier_owner_id'], on_delete: 'r', on_update: 'r',
    });
    expect(catalogContract.indexes.filter((x) => x.predicate !== null)).toHaveLength(3);
    for (const check of catalogContract.constraints.filter((x) => x.kind === 'c')) {
      expect(canonicalExpression(check.expression!)).toBeTypeOf('string');
    }
  });
  it('retains exact full signatures, bodies and definer/search_path properties', () => {
    expect(catalogContract.functions.find((x) => x.name === 'write_supplier')).toMatchObject({
      args: ['uuid', 'uuid', 'jsonb', 'uuid', 'uuid', 'text', 'text'], defaults: 3,
      definer: true, language: 'sql', volatility: 'v', result: 'record', returns_set: true,
    });
    expect(catalogContract.functions.filter((x) => x.executable)).toHaveLength(8);
    expect(catalogContract.functions.every((x) => x.body.length > 20)).toBe(true);
    expect(catalogContract.triggers.find((x) => x.name === 'record_versions_consistency')).toMatchObject({
      table: 'record_versions', function_name: 'check_version_deferred', deferrable: true, deferred: true, type: 5,
    });
    expect(catalogContract.triggers.filter((x) => x.name === 'preserve_table')).toHaveLength(11);
  });
});
