import { catalogContract as contract } from './catalog-contract.js';

// Artificial catalog projections only; no environment, model or dataset access.
// The successful default ACL projection assumes separately hardened global defaults.
// It is not the state guaranteed by applying the migration alone.
export function syntheticCatalog(): Record<string, Record<string, unknown>[]> {
  return structuredClone({
    CATALOG_ROLES: [{ triggers_protected: true, no_memberships: true, no_role_admin: true,
      database_safe: true, no_schema_create: true, schema_safe: true }],
    CATALOG_RELATIONS: contract.tables.map((name) => ({ name, kind: 'r', owner_safe: true,
      structure_safe: true, privileges_safe: true, public_safe: true })),
    CATALOG_FUNCTIONS: contract.functions.map((f) => ({ ...f, owner_safe: true, properties_safe: true, grants_safe: true })),
    CATALOG_COLUMNS: contract.columns.map((c) => ({ ...c, properties_safe: true })),
    CATALOG_CONSTRAINTS: contract.constraints.map((c) => ({ ...c, properties_safe: true })),
    CATALOG_INDEXES: contract.indexes.map((i) => ({ ...i, properties_safe: true })),
    CATALOG_TRIGGERS: contract.triggers.map((t) => ({ ...t, properties_safe: true })),
    CATALOG_DEFAULT_ACL: [{ functions_safe: true, tables_safe: true }],
  });
}
