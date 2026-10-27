import { isDeepStrictEqual } from 'node:util';
import { catalogContract as contract } from './catalog-contract.js';
import { canonicalExpression } from './catalog-expression.js';
import type { CatalogCheck } from './catalog-types.js';
import { diagnosticError } from './diagnostics.mjs';

type Row = Record<string, unknown>;
function rows(value: unknown): Row[] {
  if (!Array.isArray(value) || value.some((x) => !x || typeof x !== 'object' || Array.isArray(x))) {
    throw diagnosticError('CATALOG_RESULT_SHAPE');
  }
  return value as Row[];
}
function requireTrue(row: Row, keys: string[], code: string) {
  if (keys.some((key) => row[key] !== true)) throw diagnosticError(code);
}
function exact(actual: Row[], expected: object[], code: string, normalize = (row: Row) => row) {
  const canonical = (items: Row[]) => items.map((item) => JSON.stringify(Object.fromEntries(
    Object.entries(item).sort(([a], [b]) => a.localeCompare(b)),
  ))).sort();
  // Compare the complete projection; duplicate, missing and extra objects fail.
  if (!isDeepStrictEqual(canonical(actual.map(normalize)), canonical(expected as Row[]))) throw diagnosticError(code);
}
function flags(sql: string, code: string, keys: string[]): CatalogCheck {
  return { sql, code, validate(value) {
    const result = rows(value);
    if (result.length !== 1) throw diagnosticError('CATALOG_RESULT_SHAPE');
    requireTrue(result[0], keys, code);
  } };
}
const expression = (value: unknown) => {
  if (value === null) return null;
  if (typeof value !== 'string') throw diagnosticError('CATALOG_RESULT_SHAPE');
  return canonicalExpression(value);
};
const columnsOf = (alias: string, keys: string, relation: string) =>
  `ARRAY(SELECT a.attname::text FROM pg_catalog.unnest(${alias}.${keys}) WITH ORDINALITY key_column(num, pos)
    JOIN pg_catalog.pg_attribute a ON a.attrelid=${relation} AND a.attnum=key_column.num ORDER BY key_column.pos)`;

const roles = flags(`SELECT
  NOT pg_catalog.has_parameter_privilege(current_user,'session_replication_role','SET') AND
    NOT pg_catalog.has_parameter_privilege(current_user,'session_replication_role','SET WITH GRANT OPTION') AND
    pg_catalog.current_setting('session_replication_role')='origin' AS triggers_protected,
  NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles r WHERE r.rolname<>current_user AND
    (pg_catalog.pg_has_role(current_user,r.oid,'MEMBER') OR pg_catalog.pg_has_role(current_user,r.oid,'USAGE')
     OR pg_catalog.pg_has_role(current_user,r.oid,'SET'))) AS no_memberships,
  NOT EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r ON r.oid=m.member
    WHERE r.rolname=current_user AND m.admin_option) AS no_role_admin,
  pg_catalog.has_database_privilege(current_user,d.oid,'CONNECT') AND
    NOT pg_catalog.has_database_privilege(current_user,d.oid,'CREATE') AND
    NOT pg_catalog.has_database_privilege(current_user,d.oid,'CONNECT WITH GRANT OPTION') AND
    NOT pg_catalog.has_database_privilege(current_user,d.oid,'TEMP WITH GRANT OPTION') AND
    NOT pg_catalog.pg_has_role(current_user,d.datdba,'MEMBER') AS database_safe,
  NOT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace n WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
    AND pg_catalog.has_schema_privilege(current_user,n.oid,'CREATE')) AS no_schema_create,
  EXISTS (SELECT 1 FROM pg_catalog.pg_namespace n WHERE n.nspname='app'
    AND NOT pg_catalog.pg_has_role(current_user,n.nspowner,'MEMBER')
    AND NOT pg_catalog.has_schema_privilege(current_user,n.oid,'USAGE WITH GRANT OPTION')
    AND NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE(n.nspacl,pg_catalog.acldefault('n',n.nspowner))) a
      WHERE a.grantee=0)) AS schema_safe
 FROM pg_catalog.pg_database d WHERE d.datname=pg_catalog.current_database()`,
 'CATALOG_ROLES', ['triggers_protected', 'no_memberships', 'no_role_admin', 'database_safe', 'no_schema_create', 'schema_safe']);

const relations: CatalogCheck = {
  code: 'CATALOG_RELATIONS',
  sql: `SELECT c.relname::text AS name, c.relkind::text AS kind,
    c.relowner=n.nspowner AND NOT pg_catalog.pg_has_role(current_user,c.relowner,'MEMBER') AS owner_safe,
    c.relpersistence='p' AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity
      AND NOT c.relispartition AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_inherits i
        WHERE i.inhrelid=c.oid OR i.inhparent=c.oid) AS structure_safe,
    NOT EXISTS (SELECT 1 FROM pg_catalog.unnest(ARRAY['INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN',
      'SELECT WITH GRANT OPTION']) p WHERE pg_catalog.has_table_privilege(current_user,c.oid,p))
      AND NOT EXISTS (SELECT 1 FROM pg_catalog.unnest(ARRAY['INSERT','UPDATE','REFERENCES','SELECT WITH GRANT OPTION']) p
        WHERE pg_catalog.has_any_column_privilege(current_user,c.oid,p)) AS privileges_safe,
    NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE(c.relacl,pg_catalog.acldefault('r',c.relowner))) a WHERE a.grantee=0)
      AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_attribute a CROSS JOIN LATERAL pg_catalog.aclexplode(a.attacl) acl
        WHERE a.attrelid=c.oid AND acl.grantee=0) AS public_safe
    FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='app' AND c.relkind IN ('r','p','v','m','f','S')`,
  validate(value) {
    const result = rows(value);
    for (const row of result) {
      requireTrue(row, ['owner_safe', 'structure_safe', 'privileges_safe', 'public_safe'], 'CATALOG_RELATIONS');
      if (row.kind !== 'r') throw diagnosticError('CATALOG_RELATIONS');
    }
    exact(result.filter((r) => r.name !== '_prisma_migrations').map((r) => ({ name: r.name })),
      contract.tables.map((name) => ({ name })), 'CATALOG_RELATIONS');
    if (result.filter((r) => r.name === '_prisma_migrations').length > 1) throw diagnosticError('CATALOG_RELATIONS');
  },
};

const functions: CatalogCheck = {
  code: 'CATALOG_FUNCTIONS',
  sql: `SELECT p.proname::text AS name,
    ARRAY(SELECT pg_catalog.format_type(t,NULL) FROM pg_catalog.unnest(p.proargtypes) WITH ORDINALITY a(t,pos) ORDER BY pos) AS args,
    ARRAY(SELECT p.proargnames[pos]::text FROM pg_catalog.generate_series(1,p.pronargs) pos ORDER BY pos) AS input_names,
    ARRAY(SELECT COALESCE(p.proargmodes[pos]::text,'i') FROM pg_catalog.generate_series(1,p.pronargs) pos ORDER BY pos) AS input_modes,
    p.pronargdefaults::int AS defaults, pg_catalog.format_type(p.prorettype,NULL) AS result,
    ARRAY(SELECT p.proargnames[pos]::text FROM pg_catalog.generate_subscripts(p.proallargtypes,1) pos
      WHERE p.proargmodes[pos] IN ('o','b','t') ORDER BY pos) AS output_names,
    ARRAY(SELECT pg_catalog.format_type(p.proallargtypes[pos],NULL) FROM pg_catalog.generate_subscripts(p.proallargtypes,1) pos
      WHERE p.proargmodes[pos] IN ('o','b','t') ORDER BY pos) AS output_types,
    ARRAY(SELECT p.proargmodes[pos]::text FROM pg_catalog.generate_subscripts(p.proallargtypes,1) pos
      WHERE p.proargmodes[pos] IN ('o','b','t') ORDER BY pos) AS output_modes,
    pg_catalog.pg_get_expr(p.proargdefaults,0) AS defaults_expression,
    p.proretset AS returns_set, l.lanname::text AS language, p.prosecdef AS definer, p.provolatile::text AS volatility,
    p.proconfig AS config, p.prosrc AS body, pg_catalog.has_function_privilege(current_user,p.oid,'EXECUTE') AS executable,
    p.proowner=n.nspowner AND NOT pg_catalog.pg_has_role(current_user,p.proowner,'MEMBER') AS owner_safe,
    p.prokind='f' AND p.proparallel='u' AND NOT p.proleakproof AND NOT p.proisstrict AS properties_safe,
    NOT pg_catalog.has_function_privilege(current_user,p.oid,'EXECUTE WITH GRANT OPTION') AND
      NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
        WHERE a.grantee=0 AND a.privilege_type='EXECUTE') AS grants_safe
    FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
    JOIN pg_catalog.pg_language l ON l.oid=p.prolang WHERE n.nspname='app'`,
  validate(value) {
    exact(rows(value), contract.functions, 'CATALOG_FUNCTIONS', (row) => {
      requireTrue(row, ['owner_safe', 'properties_safe', 'grants_safe'], 'CATALOG_FUNCTIONS');
      const { owner_safe: _owner, properties_safe: _properties, grants_safe: _grants, ...rest } = row;
      if (typeof rest.body !== 'string' || !Array.isArray(rest.config) || rest.config.some((x) => typeof x !== 'string')) {
        throw diagnosticError('CATALOG_RESULT_SHAPE');
      }
      // PostgreSQL canonicalizes GUC names and list spacing. Do not normalize SQL bodies internally.
      rest.body = rest.body.replaceAll('\r\n', '\n').trim();
      rest.config = [...rest.config].sort((a, b) => a < b ? -1 : a > b ? 1 : 0);
      return rest;
    });
  },
};

const columns: CatalogCheck = {
  code: 'CATALOG_COLUMNS',
  sql: `SELECT c.relname::text AS table, a.attname::text AS name,
    pg_catalog.format_type(a.atttypid,a.atttypmod) AS type, a.attnotnull AS not_null,
    pg_catalog.pg_get_expr(d.adbin,d.adrelid) AS default_expression,
    NOT a.attisdropped AND a.attidentity='' AND a.attgenerated='' AND a.attislocal AND a.attinhcount=0
      AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint k WHERE k.conrelid=c.oid AND k.contype='n'
        AND a.attnum=ANY(k.conkey) AND (NOT k.convalidated OR NOT k.conenforced)) AS properties_safe
    FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
    WHERE n.nspname='app' AND c.relkind='r' AND c.relname<>'_prisma_migrations' AND a.attnum>0`,
  validate(value) {
    const normalize = (row: Row) => ({ ...row, default_expression: expression(row.default_expression) });
    exact(rows(value).map((row) => {
      requireTrue(row, ['properties_safe'], 'CATALOG_COLUMNS');
      const { properties_safe: _safe, ...rest } = row;
      return normalize(rest);
    }), contract.columns.map(normalize), 'CATALOG_COLUMNS');
  },
};

const constraints: CatalogCheck = {
  code: 'CATALOG_CONSTRAINTS',
  sql: `SELECT c.relname::text AS table, k.conname::text AS name, k.contype::text AS kind,
    CASE WHEN k.contype='c' THEN ARRAY[]::text[] ELSE ${columnsOf('k', 'conkey', 'k.conrelid')} END AS columns,
    f.relname::text AS foreign_table, ${columnsOf('k', 'confkey', 'k.confrelid')} AS foreign_columns,
    k.confdeltype::text AS on_delete, k.confupdtype::text AS on_update,
    k.condeferrable AS deferrable, k.condeferred AS deferred, pg_catalog.pg_get_expr(k.conbin,k.conrelid) AS expression,
    k.convalidated AND k.conenforced AND k.conislocal AND k.coninhcount=0 AND (k.contype<>'c' OR NOT k.connoinherit) AND NOT k.conperiod
      AND (k.contype<>'f' OR (k.confmatchtype='s' AND fn.nspname='app'
        AND (SELECT pg_catalog.count(*) FROM pg_catalog.pg_trigger t WHERE t.tgconstraint=k.oid AND t.tgisinternal)=4
        AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_trigger t WHERE t.tgconstraint=k.oid AND t.tgenabled<>'O'))) AS properties_safe
    FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    LEFT JOIN pg_catalog.pg_class f ON f.oid=k.confrelid LEFT JOIN pg_catalog.pg_namespace fn ON fn.oid=f.relnamespace
    WHERE n.nspname='app' AND c.relname<>'_prisma_migrations' AND k.contype NOT IN ('n','t')`,
  validate(value) {
    const normalize = (r: Row) => ({ ...r, expression: expression(r.expression) });
    exact(rows(value).map((r) => {
      requireTrue(r, ['properties_safe'], 'CATALOG_CONSTRAINTS');
      const { properties_safe: _safe, ...rest } = r;
      return normalize(rest);
    }), contract.constraints.map(normalize), 'CATALOG_CONSTRAINTS');
  },
};

const indexes: CatalogCheck = {
  code: 'CATALOG_INDEXES',
  sql: `SELECT c.relname::text AS table, ic.relname::text AS name, ${columnsOf('i', 'indkey', 'i.indrelid')} AS columns,
    i.indisunique AS unique, i.indisprimary AS primary, pg_catalog.pg_get_expr(i.indpred,i.indrelid) AS predicate,
    i.indisvalid AND i.indisready AND i.indislive AND i.indimmediate AND NOT i.indnullsnotdistinct
      AND i.indexprs IS NULL AND i.indnkeyatts=i.indnatts AND am.amname='btree'
      AND NOT EXISTS (SELECT 1 FROM pg_catalog.unnest(i.indoption) opt WHERE opt<>0)
      AND NOT EXISTS (SELECT 1 FROM pg_catalog.unnest(i.indclass) oc JOIN pg_catalog.pg_opclass op ON op.oid=oc
        JOIN pg_catalog.pg_namespace ns ON ns.oid=op.opcnamespace WHERE NOT op.opcdefault OR ns.nspname<>'pg_catalog')
      AND NOT EXISTS (SELECT 1 FROM pg_catalog.unnest(i.indcollation) WITH ORDINALITY co(oid,pos)
        JOIN pg_catalog.unnest(i.indkey) WITH ORDINALITY ak(num,pos) USING(pos)
        JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=ak.num WHERE co.oid<>a.attcollation) AS properties_safe
    FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_class ic ON ic.oid=i.indexrelid
    JOIN pg_catalog.pg_am am ON am.oid=ic.relam WHERE n.nspname='app' AND c.relname<>'_prisma_migrations'`,
  validate(value) {
    const normalize = (r: Row) => ({ ...r, predicate: expression(r.predicate) });
    exact(rows(value).map((r) => {
      requireTrue(r, ['properties_safe'], 'CATALOG_INDEXES');
      const { properties_safe: _safe, ...rest } = r;
      return normalize(rest);
    }), contract.indexes.map(normalize), 'CATALOG_INDEXES');
  },
};

const triggers: CatalogCheck = {
  code: 'CATALOG_TRIGGERS',
  sql: `SELECT c.relname::text AS table, t.tgname::text AS name, p.proname::text AS function_name, t.tgtype::int AS type,
    t.tgdeferrable AS deferrable, t.tginitdeferred AS deferred, pg_catalog.encode(t.tgargs,'hex') AS args_hex,
    t.tgenabled='O' AND pn.nspname='app' AND p.pronargs=0 AND t.tgqual IS NULL AND t.tgattr=''::int2vector
      AND t.tgoldtable IS NULL AND t.tgnewtable IS NULL AND t.tgparentid=0 AS properties_safe
    FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
    JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
    WHERE n.nspname='app' AND c.relname<>'_prisma_migrations' AND NOT t.tgisinternal`,
  validate(value) {
    exact(rows(value), contract.triggers, 'CATALOG_TRIGGERS', (r) => {
      requireTrue(r, ['properties_safe'], 'CATALOG_TRIGGERS');
      const { properties_safe: _safe, ...rest } = r;
      return rest;
    });
  },
};

// A per-schema REVOKE cannot cancel PostgreSQL's global PUBLIC EXECUTE default.
// Inspect both scopes, for the owner of app. Other future creator roles need separate review.
const defaultAcl: CatalogCheck = { code: 'CATALOG_DEFAULT_ACL', sql: `SELECT NOT EXISTS (
  SELECT 1 FROM pg_catalog.pg_namespace n CROSS JOIN LATERAL (
    SELECT a.* FROM pg_catalog.aclexplode(COALESCE((SELECT d.defaclacl FROM pg_catalog.pg_default_acl d
      WHERE d.defaclrole=n.nspowner AND d.defaclnamespace=0 AND d.defaclobjtype='f'),
      pg_catalog.acldefault('f',n.nspowner))) a
    UNION ALL SELECT a.* FROM pg_catalog.pg_default_acl d CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) a
      WHERE d.defaclrole=n.nspowner AND d.defaclnamespace=n.oid AND d.defaclobjtype='f'
  ) acl WHERE n.nspname='app' AND acl.privilege_type='EXECUTE' AND
    (acl.grantee=0 OR acl.grantee=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user))
) AS functions_safe,
 NOT EXISTS (
  SELECT 1 FROM pg_catalog.pg_namespace n CROSS JOIN LATERAL (
    SELECT a.* FROM pg_catalog.aclexplode(COALESCE((SELECT d.defaclacl FROM pg_catalog.pg_default_acl d
      WHERE d.defaclrole=n.nspowner AND d.defaclnamespace=0 AND d.defaclobjtype='r'),
      pg_catalog.acldefault('r',n.nspowner))) a
    UNION ALL SELECT a.* FROM pg_catalog.pg_default_acl d CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) a
      WHERE d.defaclrole=n.nspowner AND d.defaclnamespace=n.oid AND d.defaclobjtype='r'
  ) acl WHERE n.nspname='app' AND
    (acl.grantee=0 OR acl.grantee=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user))
    AND (acl.grantee=0 OR acl.privilege_type<>'SELECT' OR acl.is_grantable)
 ) AS tables_safe`, validate(value) {
  const result = rows(value);
  if (result.length !== 1 || typeof result[0].functions_safe !== 'boolean' || typeof result[0].tables_safe !== 'boolean') {
    throw diagnosticError('CATALOG_RESULT_SHAPE');
  }
  const { functions_safe, tables_safe } = result[0];
  if (!functions_safe && !tables_safe) throw diagnosticError('CATALOG_DEFAULT_ACL_BOTH');
  if (!functions_safe) throw diagnosticError('CATALOG_DEFAULT_ACL_FUNCTIONS');
  if (!tables_safe) throw diagnosticError('CATALOG_DEFAULT_ACL_TABLES');
} };

export const catalogChecks: readonly CatalogCheck[] = [roles, relations, functions, columns, constraints, indexes, triggers, defaultAcl];
