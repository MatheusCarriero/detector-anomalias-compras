import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { PURCHASE_CATALOG } from './purchase-catalog.js';

// Administrative, opt-in entry point. Never registered in a Nest module or HTTP
// endpoint. No driver, environment lookup, connection or side effect on import.
export interface ProvisionClient {
  query(text: string, values?: unknown[]): Promise<{ rows: Record<string, unknown>[] }>;
}

export const P4_MIGRATIONS = Object.freeze([
  { name: '20261020000100_first_increment', hash: '4bc2d19996d1adc10ab05a68eeb17b78153e3725c8d0bcb1c6781fc88848311f' },
  { name: '20261116000100_p4_read_interfaces', hash: 'c63333bbd5a025c64b51ab60fb2ac02b4c8c5df90dd7843c54361f48ad6291aa' },
]);
export const P4_COMPARABILITY_MIGRATIONS = Object.freeze([...P4_MIGRATIONS,
  { name: '20261119000100_p4_comparability', hash: '35955a7de1374ba2971ff55f2082ddd6923d3fa9f2b6690ca220b03cb4eae95d' },
]);
export type ProvisionProfile = 'p4-v1' | 'comparability-v1' | 'p4-api-comparability-v1';
const namespace = PURCHASE_CATALOG.version;
const contract = 'p4-provision/1.0';
const actorState = { display_name: 'Serviço técnico P4 — catálogo sintético', email: null,
  auth_issuer: 'p4-demo', auth_subject: 'manual-purchase-service', is_active: true, department_id: null };
const currencyState = { code: 'BRL', name: 'Real brasileiro' };
type Kind = 'supplier' | 'department';
type Mapping = { source_id: string; id: string; created: boolean };
type Code = 'TARGET' | 'MIGRATIONS' | 'PERMISSION' | 'CONFLICT' | 'INTEGRITY' | 'DATABASE'
  | 'ROLLBACK_UNCONFIRMED' | 'COMMIT_UNKNOWN';
class ProvisionError extends Error {
  constructor(readonly code: Code) { super(`P4_PROVISION_${code}`); }
}
function requireValue(value: unknown, code: Code = 'INTEGRITY'): asserts value {
  if (!value) throw new ProvisionError(code);
}
function uuid(value: unknown): value is string {
  return typeof value === 'string' && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(value);
}
function single(rows: Record<string, unknown>[]) {
  requireValue(rows.length === 1); return rows[0];
}
function id(rows: Record<string, unknown>[]) {
  const value = single(rows).id; requireValue(uuid(value)); return value;
}
function original(kind: string, sourceId: string, state: object, databaseId?: string) {
  return { contract, catalog_version: namespace, origin: PURCHASE_CATALOG.origin,
    kind, source_id: sourceId, state, ...(databaseId ? { database_id: databaseId } : {}) };
}
function hash(value: object) { return createHash('sha256').update(JSON.stringify(value), 'utf8').digest('hex'); }

async function preflight(client: ProvisionClient, profile: ProvisionProfile) {
  const extended = profile !== 'p4-v1';
  const expectedMigrations = extended ? P4_COMPARABILITY_MIGRATIONS : P4_MIGRATIONS;
  const who = single((await client.query(`/* p4:identity */ SELECT session_user::text AS session_user,
    current_user::text AS current_user, pg_catalog.current_database() AS database,
    pg_catalog.host(pg_catalog.inet_server_addr()) AS host, pg_catalog.inet_server_port() AS port,
    pg_catalog.current_setting('server_version_num')::integer AS version,
    pg_catalog.current_setting('transaction_read_only') AS read_only,
    pg_catalog.pg_get_userbyid(n.nspowner) AS owner,
    NOT (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls OR r.rolreplication) AS restricted,
    NOT EXISTS (SELECT 1 FROM pg_catalog.pg_stat_ssl WHERE pid=pg_catalog.pg_backend_pid() AND ssl) AS plaintext
    FROM pg_catalog.pg_namespace n JOIN pg_catalog.pg_roles r ON r.rolname=current_user WHERE n.nspname='app'`)).rows);
  requireValue(who.session_user === 'detector_migrator' && who.current_user === 'detector_migrator'
    && who.database === (profile === 'comparability-v1' ? 'synthetic_p4_comparability_test' : 'synthetic_detector_anomalias_compras_test') && who.host === '127.0.0.1'
    && who.port === 5432 && typeof who.version === 'number' && who.version >= 180000 && who.version < 190000
    && who.owner === 'detector_migrator' && who.restricted === true && who.plaintext === true
    && who.read_only === 'off', 'TARGET');
  const migrations = (await client.query(`/* p4:migrations */ SELECT migration_name,checksum,
    rolled_back_at IS NOT NULL AS rolled_back,
    finished_at IS NOT NULL AND rolled_back_at IS NULL AND applied_steps_count=1 AS complete
    FROM app._prisma_migrations ORDER BY migration_name`)).rows;
  // Prisma retains resolved attempts. Their old checksums are historical, not
  // approvals of the current SQL. An unresolved failure must never be filtered
  // out merely because another attempt of the same migration succeeded.
  requireValue(migrations.every(row => expectedMigrations.some(m => m.name === row.migration_name)
    && typeof row.rolled_back === 'boolean'
    && (!row.rolled_back || row.complete === false)), 'MIGRATIONS');
  const applied = migrations.filter(row => row.rolled_back === false);
  requireValue(applied.length === expectedMigrations.length && expectedMigrations.every(m => {
    const matches = applied.filter(row => row.migration_name === m.name);
    return matches.length === 1 && matches[0].checksum === m.hash && matches[0].complete === true;
  }), 'MIGRATIONS');
  const permission = single((await client.query(`/* p4:permissions */ SELECT
    NOT (r.rolsuper OR r.rolcreaterole OR r.rolcreatedb OR r.rolbypassrls OR r.rolreplication)
      AND NOT pg_catalog.pg_has_role(r.oid,n.nspowner,'MEMBER')
      AND NOT pg_catalog.pg_has_role(r.oid,n.nspowner,'SET') AS runtime_restricted,
    pg_catalog.has_schema_privilege(r.oid,n.oid,'USAGE') AND NOT EXISTS (
      SELECT 1 FROM pg_catalog.pg_namespace s WHERE s.nspname !~ '^pg_' AND s.nspname<>'information_schema'
      AND pg_catalog.has_schema_privilege(r.oid,s.oid,'CREATE')) AS runtime_schema_safe,
    NOT EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE(n.nspacl,pg_catalog.acldefault('n',n.nspowner))) a
      WHERE a.privilege_type='CREATE' AND a.grantee<>n.nspowner)
      AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles x WHERE x.oid<>n.nspowner AND NOT x.rolsuper
        AND (pg_catalog.has_schema_privilege(x.oid,n.oid,'CREATE') OR pg_catalog.pg_has_role(x.oid,n.nspowner,'SET'))) AS schema_safe,
    NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class c WHERE c.relnamespace=n.oid AND c.relkind IN ('r','p','v','m','f','S')
      AND (c.relowner<>n.nspowner OR c.relkind<>'r' OR EXISTS (
        SELECT 1 FROM pg_catalog.unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER','MAINTAIN']) p
        WHERE pg_catalog.has_table_privilege(r.oid,c.oid,p)) OR EXISTS (
        SELECT 1 FROM pg_catalog.unnest(ARRAY['SELECT','INSERT','UPDATE','REFERENCES']) p
        WHERE pg_catalog.has_any_column_privilege(r.oid,c.oid,p)))) AS tables_safe,
    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_class c WHERE c.relnamespace=n.oid AND c.relkind='r'
      AND c.relname<>'_prisma_migrations')=$2::integer AS table_count_safe,
    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc p WHERE p.pronamespace=n.oid)=$3::integer
      AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.pronamespace=n.oid AND
        (p.proowner<>n.nspowner OR NOT pg_catalog.has_function_privilege(current_user,p.oid,'EXECUTE') OR EXISTS (
          SELECT 1 FROM pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
          WHERE a.grantee=0 AND a.privilege_type='EXECUTE'))) AS functions_safe,
    NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.pronamespace=n.oid AND
      pg_catalog.has_function_privilege(r.oid,p.oid,'EXECUTE') IS DISTINCT FROM
      (p.oid::regprocedure::text=ANY($1::text[]))) AS allowlist_safe,
    (SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc p WHERE p.pronamespace=n.oid
      AND p.oid::regprocedure::text=ANY($1::text[]))=pg_catalog.cardinality($1::text[]) AS allowlist_complete,
    NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.pronamespace=n.oid AND p.proname LIKE 'p4_v1_%'
      AND (p.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, app, pg_temp']::text[] OR p.provolatile<>'s'
        OR p.prosecdef IS DISTINCT FROM (p.proname<>'p4_v1_checked_receipt'))) AS readers_safe,
    $2::integer=11 OR ((SELECT pg_catalog.count(*) FROM pg_catalog.pg_proc p
      WHERE p.pronamespace=n.oid AND p.proname LIKE 'p4_cmp_%')=10 AND NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p WHERE p.pronamespace=n.oid AND p.proname LIKE 'p4_cmp_%'
          AND (p.proconfig IS DISTINCT FROM ARRAY['search_path=pg_catalog, app, pg_temp']::text[]
            OR p.prosecdef IS DISTINCT FROM (p.proname IN ('p4_cmp_read','p4_cmp_write'))
            OR EXISTS (SELECT 1 FROM pg_catalog.aclexplode(COALESCE(p.proacl,pg_catalog.acldefault('f',p.proowner))) a
              WHERE a.grantee<>p.proowner AND (a.grantee<>r.oid OR p.proname NOT IN ('p4_cmp_read','p4_cmp_write')))))) AS comparability_safe
    FROM pg_catalog.pg_namespace n CROSS JOIN pg_catalog.pg_roles r
    WHERE n.nspname='app' AND r.rolname='detector_runtime'`, [[
    'app.write_supplier(uuid,uuid,jsonb,uuid,uuid,text,text)', 'app.write_department(uuid,uuid,jsonb,uuid,uuid,text,text)',
    'app.write_purchase_order_line(uuid,uuid,jsonb,uuid,uuid,uuid,uuid,uuid,text,text)',
    'app.register_source_identity(text,text,text,uuid)', 'app.resolve_source_identity(uuid,uuid,uuid,uuid,uuid)',
    'app.observe_source(text,text,uuid,uuid,text,text,text,text,jsonb,text)', 'app.capture_line(uuid,uuid)', 'app.seal_snapshot(uuid,uuid)',
    'app.p4_v1_context()', 'app.p4_v1_receipt_by_key(uuid)', 'app.p4_v1_receipt_by_id(uuid)',
    'app.p4_v1_history(integer,timestamp with time zone,uuid)',
    ...(extended ? ['app.p4_cmp_write(text,jsonb)', 'app.p4_cmp_read(uuid,integer)'] : []),
  ], extended ? 13 : 11, extended ? 41 : 31])).rows);
  const keys = ['runtime_restricted', 'runtime_schema_safe', 'schema_safe', 'tables_safe', 'table_count_safe',
    'functions_safe', 'allowlist_safe', 'allowlist_complete', 'readers_safe'];
  if (extended) keys.push('comparability_safe');
  requireValue(keys.every(key => permission[key] === true), 'PERMISSION');
}

async function observe(client: ProvisionClient, kind: string, key: string, value: object, actor: string) {
  return id((await client.query(`/* p4:observe */ SELECT app.observe_source($1::text,$2::text,$3::uuid,
    NULL::uuid,$4::text,$5::text,NULL::text,$6::text,$7::jsonb,NULL::text) AS id`,
  [namespace, kind, actor, contract, key, hash(value), JSON.stringify(value)])).rows);
}
async function bootstrapEvidence(client: ProvisionClient, kind: string, key: string, value: object, actor: string) {
  const rows = (await client.query(`/* p4:bootstrap-evidence */ SELECT r.id,r.original_content,r.content_hash,
    r.source_identity_id IS NULL AND r.source_version=$4 AND r.locator IS NULL AND r.available_at IS NULL
      AND r.availability_status='unverified' AND (SELECT pg_catalog.count(*) FROM app.audit_events a
        WHERE a.source_reference_id=r.id AND a.operation='source_observe' AND a.actor_user_id=$5::uuid)=1 AS valid
    FROM app.source_references r WHERE r.source_namespace=$1 AND r.source_entity_kind=$2 AND r.source_record_key=$3`,
  [namespace, kind, key, contract, actor])).rows;
  if (!rows.length) { await observe(client, kind, key, value, actor); return; }
  requireValue(rows.length === 1 && uuid(rows[0].id) && rows[0].valid === true
    && rows[0].content_hash === hash(value) && isDeepStrictEqual(rows[0].original_content, value), 'CONFLICT');
}

async function entity(client: ProvisionClient, kind: Kind, entry: { id: string; name: string }, actor: string) {
  const state = kind === 'supplier' ? { name: entry.name, country_code: null, status: null, tier: null }
    : { name: entry.name, code: null };
  const value = original(kind, entry.id, state);
  // All identifiers below are chosen from these two literals, never external data.
  const table = kind === 'supplier' ? 'suppliers' : 'departments';
  const ownerColumn = kind === 'supplier' ? 'supplier_owner_id' : 'department_owner_id';
  const idColumn = kind === 'supplier' ? 'supplier_id' : 'department_id';
  const otherOwner = kind === 'supplier' ? 'department_owner_id' : 'supplier_owner_id';
  const otherId = kind === 'supplier' ? 'department_id' : 'supplier_id';
  const projection = kind === 'supplier'
    ? "pg_catalog.jsonb_build_object('name',e.name,'country_code',e.country_code,'status',e.status,'tier',e.tier)"
    : "pg_catalog.jsonb_build_object('name',e.name,'code',e.code)";
  const read = async () => (await client.query(`/* p4:entity-read */ SELECT i.id AS identity_id,e.id AS entity_id,
    v.id AS version_id,v.payload,${projection} AS projection,r.original_content,r.content_hash,
    i.resolved_at IS NOT NULL AND i.${otherId} IS NULL AND i.purchase_order_line_id IS NULL
      AND (SELECT pg_catalog.count(*) FROM app.source_identities x WHERE x.${idColumn}=e.id)=1
      AND v.${ownerColumn}=e.id AND v.${otherOwner} IS NULL AND v.purchase_line_owner_id IS NULL
      AND v.revision_no=1 AND v.supersedes_version_id IS NULL AND v.payload_schema=1 AND v.actor_user_id=$4::uuid
      AND v.supplier_id IS NULL AND v.department_id IS NULL AND v.currency_id IS NULL
      AND v.effective_from IS NULL AND v.effective_to IS NULL
      AND (SELECT pg_catalog.count(*) FROM app.record_versions x WHERE x.${ownerColumn}=e.id)=1
      AND r.source_namespace=$1 AND r.source_entity_kind=$2 AND r.source_record_key=$3
      AND r.source_identity_id IS NULL AND r.source_version=$5 AND r.locator IS NULL AND r.available_at IS NULL
      AND r.availability_status='unverified'
      AND (SELECT pg_catalog.count(*) FROM app.source_references x WHERE x.source_namespace=$1
        AND x.source_entity_kind=$2 AND x.source_record_key=$3)=1
      AND (SELECT pg_catalog.count(*) FROM app.audit_events a WHERE a.after_version_id=v.id
        AND a.operation='create' AND a.before_version_id IS NULL AND a.actor_user_id=$4::uuid)=1
      AND (SELECT pg_catalog.count(*) FROM app.audit_events a WHERE a.source_identity_id=i.id
        AND a.operation='identity_register' AND a.actor_user_id=$4::uuid)=1
      AND (SELECT pg_catalog.count(*) FROM app.audit_events a WHERE a.source_identity_id=i.id
        AND a.operation='identity_resolve' AND a.actor_user_id=$4::uuid)=1
      AND (SELECT pg_catalog.count(*) FROM app.audit_events a WHERE a.source_reference_id=r.id
        AND a.operation='source_observe' AND a.actor_user_id=$4::uuid)=1 AS valid
    FROM app.source_identities i LEFT JOIN app.${table} e ON e.id=i.${idColumn}
    LEFT JOIN app.record_versions v ON v.id=e.current_version_id
    LEFT JOIN app.source_references r ON r.id=v.source_reference_id
    WHERE i.source_namespace=$1 AND i.source_entity_kind=$2 AND i.source_id=$3`,
  [namespace, kind, entry.id, actor, contract])).rows;
  let rows = await read(); const created = rows.length === 0;
  let written: Record<string, unknown> | undefined;
  let identity: string | undefined;
  if (created) {
    // Never adopt a same-name entity, or an orphan source, by guesswork.
    const conflicts = (await client.query(`/* p4:orphans */ SELECT EXISTS (SELECT 1 FROM app.${table} WHERE name=$1)
      OR EXISTS (SELECT 1 FROM app.source_references WHERE source_namespace=$2 AND source_entity_kind=$3
        AND source_record_key=$4) AS conflict`, [entry.name, namespace, kind, entry.id])).rows;
    requireValue(single(conflicts).conflict === false, 'CONFLICT');
    identity = id((await client.query(`/* p4:register */ SELECT app.register_source_identity($1::text,$2::text,$3::text,$4::uuid) AS id`,
      [namespace, kind, entry.id, actor])).rows);
    const source = await observe(client, kind, entry.id, value, actor);
    written = single((await client.query(`/* p4:write-${kind} */ SELECT * FROM app.write_${kind}(
      NULL::uuid,NULL::uuid,$1::jsonb,$2::uuid,$3::uuid,NULL::text,NULL::text)`, [JSON.stringify(state), actor, source])).rows);
    requireValue(uuid(written.entity_id) && uuid(written.version_id) && written.revision_no === 1);
    await client.query(`/* p4:resolve */ SELECT app.resolve_source_identity($1::uuid,$2::uuid,$3::uuid,NULL::uuid,$4::uuid)`,
      [identity, kind === 'supplier' ? written.entity_id : null, kind === 'department' ? written.entity_id : null, actor]);
    rows = await read();
  }
  const row = single(rows);
  requireValue(uuid(row.identity_id) && uuid(row.entity_id) && uuid(row.version_id) && row.valid === true
    && isDeepStrictEqual(row.payload, state) && isDeepStrictEqual(row.projection, state)
    && isDeepStrictEqual(row.original_content, value) && row.content_hash === hash(value), 'CONFLICT');
  requireValue(!written || (row.identity_id === identity && row.entity_id === written.entity_id && row.version_id === written.version_id));
  return { source_id: entry.id, id: row.entity_id, created };
}

export async function provisionP4(client: ProvisionClient, profile: ProvisionProfile = 'p4-v1') {
  requireValue(profile === 'p4-v1' || profile === 'comparability-v1' || profile === 'p4-api-comparability-v1', 'TARGET');
  let begun = false; let committing = false;
  try {
    await client.query('BEGIN ISOLATION LEVEL READ COMMITTED'); begun = true;
    await client.query("SET LOCAL search_path=pg_catalog; SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='2s'; SET LOCAL idle_in_transaction_session_timeout='8s'");
    await preflight(client, profile);
    // This short administrative bootstrap serializes catalog changes, including
    // callers that do not cooperate with an advisory lock. Never used by HTTP.
    await client.query('LOCK TABLE app.currencies,app.users,app.suppliers,app.departments,app.source_identities,app.source_references IN SHARE ROW EXCLUSIVE MODE');
    const users = (await client.query(`/* p4:user-read */ SELECT id,display_name,email,auth_issuer,auth_subject,is_active,department_id
      FROM app.users WHERE auth_issuer=$1 AND auth_subject=$2`, [actorState.auth_issuer, actorState.auth_subject])).rows;
    const userCreated = users.length === 0;
    if (userCreated) users.push(single((await client.query(`/* p4:user-create */ INSERT INTO app.users
      (display_name,auth_issuer,auth_subject) VALUES($1,$2,$3)
      RETURNING id,display_name,email,auth_issuer,auth_subject,is_active,department_id`,
    [actorState.display_name, actorState.auth_issuer, actorState.auth_subject])).rows));
    const { id: actor, ...userState } = single(users);
    requireValue(uuid(actor) && isDeepStrictEqual(userState, actorState), 'CONFLICT');
    const currencies = (await client.query('/* p4:currency-read */ SELECT id,code,name FROM app.currencies WHERE code=$1', ['BRL'])).rows;
    const currencyCreated = currencies.length === 0;
    if (currencyCreated) currencies.push(single((await client.query(`/* p4:currency-create */ INSERT INTO app.currencies(code,name)
      VALUES($1,$2) RETURNING id,code,name`, [currencyState.code, currencyState.name])).rows));
    const { id: currency, ...moneyState } = single(currencies);
    requireValue(uuid(currency) && isDeepStrictEqual(moneyState, currencyState), 'CONFLICT');
    // Currency/user are not valid typed source_identity owners in this schema.
    // Immutable source observations record their internal IDs; observe_source
    // supplies the allowed source_observe audit event, including session_user.
    await bootstrapEvidence(client, 'user', 'p4-demo/manual-purchase-service', original('user', 'p4-demo/manual-purchase-service', actorState, actor), actor);
    await bootstrapEvidence(client, 'currency', 'BRL', original('currency', 'BRL', currencyState, currency), actor);
    const suppliers: Mapping[] = []; const departments: Mapping[] = [];
    for (const entry of PURCHASE_CATALOG.suppliers) suppliers.push(await entity(client, 'supplier', entry, actor));
    for (const entry of PURCHASE_CATALOG.departments) departments.push(await entity(client, 'department', entry, actor));
    const context = single((await client.query('/* p4:context */ SELECT app.p4_v1_context() AS result')).rows).result;
    const mappings = (items: Mapping[]) => items.map(({ source_id, id }) => ({ source_id, id }))
      .sort((a, b) => a.source_id < b.source_id ? -1 : a.source_id > b.source_id ? 1 : 0);
    requireValue(isDeepStrictEqual(context, { contract: 'p4-storage/1.0', catalog_version: namespace,
      actor: { id: actor, issuer: actorState.auth_issuer, subject: actorState.auth_subject },
      currency: { id: currency, code: 'BRL' }, suppliers: mappings(suppliers), departments: mappings(departments) }));
    await client.query('SET CONSTRAINTS ALL IMMEDIATE');
    committing = true; await client.query('COMMIT'); begun = false;
    return { contract, namespace, user: { id: actor, created: userCreated }, currency: { id: currency, created: currencyCreated }, suppliers, departments };
  } catch (error) {
    if (begun) {
      try { await client.query('ROLLBACK'); }
      catch { throw new ProvisionError(committing ? 'COMMIT_UNKNOWN' : 'ROLLBACK_UNCONFIRMED'); }
    }
    if (committing) throw new ProvisionError('COMMIT_UNKNOWN');
    if (error instanceof ProvisionError) throw error;
    const code = error && typeof error === 'object' && 'code' in error ? error.code : null;
    throw new ProvisionError(code === '42501' ? 'PERMISSION' : code === '23505' ? 'CONFLICT'
      : ['23503', '23514'].includes(String(code)) ? 'INTEGRITY' : 'DATABASE');
  }
}
