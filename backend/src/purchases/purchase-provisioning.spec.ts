import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { provisionP4, P4_COMPARABILITY_MIGRATIONS, type ProvisionClient } from './purchase-provisioning.js';

// This fake models returned rows and transaction rollback, not PostgreSQL SQL
// evaluation. Real ACLs, locks and deferred triggers require connected approval.
const identity = { session_user: 'detector_migrator', current_user: 'detector_migrator',
  database: 'synthetic_detector_anomalias_compras_test', host: '127.0.0.1', port: 5432,
  version: 180006, read_only: 'off', owner: 'detector_migrator', restricted: true, plaintext: true };
const permissions = { runtime_restricted: true, runtime_schema_safe: true, schema_safe: true, tables_safe: true,
  table_count_safe: true, functions_safe: true, allowlist_safe: true, allowlist_complete: true, readers_safe: true };
const migrations = [
  { migration_name: '20261020000100_first_increment', checksum: '4bc2d19996d1adc10ab05a68eeb17b78153e3725c8d0bcb1c6781fc88848311f', complete: true, rolled_back: false },
  { migration_name: '20261116000100_p4_read_interfaces', checksum: 'c63333bbd5a025c64b51ab60fb2ac02b4c8c5df90dd7843c54361f48ad6291aa', complete: true, rolled_back: false },
];
const crlfChecksums = [
  'ebfcc92cf1258415e73cd797849a79639e94db08fbbe155c578788421021db81',
  '0efa7e202c95866b47ee017a009e4285c22df8f54a4c7b51abe25e8659a486a3',
  '83afd98b5d3f109839a1a65a95db0860fad25b7f0f1b4aaf59302f49e391bd71',
];
const empty = () => ({ user: null as Record<string, any> | null, currency: null as Record<string, any> | null,
  sources: [] as Record<string, any>[], entities: [] as Record<string, any>[], identities: [] as Record<string, any>[] });
function fixture() {
  let db = empty(); let before = empty(); let sequence = 0;
  const newId = () => `00000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}`;
  const calls: { sql: string; values: unknown[] }[] = [];
  const who = { ...identity }; const grants = { ...permissions }; const applied = structuredClone(migrations);
  const failures = new Map<string, unknown>(); let orphan = false; let badContext = false;
  const client: ProvisionClient = { query: async (sql, values = []) => {
    calls.push({ sql, values: structuredClone(values) });
    const tag = /\/\* p4:([^ ]+) \*\//.exec(sql)?.[1] ?? sql;
    if (failures.has(tag)) throw failures.get(tag);
    const [a, b, c, d, e, f, g] = values;
    let rows: Record<string, any>[] = [];
    switch (tag) {
      case 'identity': rows = [who]; break;
      case 'permissions': rows = [grants]; break;
      case 'migrations': rows = applied; break;
      case 'user-read': rows = db.user ? [db.user] : []; break;
      case 'user-create':
        db.user = { id: newId(), display_name: a, auth_issuer: b, auth_subject: c,
          is_active: true, department_id: null, email: null }; rows = [db.user]; break;
      case 'currency-read': rows = db.currency ? [db.currency] : []; break;
      case 'currency-create': db.currency = { id: newId(), code: a, name: b }; rows = [db.currency]; break;
      case 'bootstrap-evidence': rows = db.sources.filter(s => s.kind === b && s.key === c); break;
      case 'observe': {
        const source = { id: newId(), namespace: a, kind: b, actor: c, version: d, key: e,
          content_hash: f, original_content: JSON.parse(g as string), valid: true };
        db.sources.push(source); rows = [{ id: source.id }]; break;
      }
      case 'entity-read': rows = db.entities.filter(x => x.kind === b && x.key === c).map(x => {
        const source = db.sources.find(s => s.id === x.source)!;
        const mapped = db.identities.find(i => i.entity_id === x.entity_id);
        return { ...x, identity_id: mapped?.id, original_content: source.original_content,
          content_hash: source.content_hash, valid: x.valid && !!mapped?.resolved };
      }); break;
      case 'orphans': rows = [{ conflict: orphan }]; break;
      case 'register': {
        const row = { id: newId(), namespace: a, kind: b, key: c, actor: d, resolved: false };
        db.identities.push(row); rows = [{ id: row.id }]; break;
      }
      case 'write-supplier': case 'write-department': {
        const source = db.sources.find(s => s.id === c)!;
        const row = { entity_id: newId(), version_id: newId(), revision_no: 1,
          kind: source.kind, key: source.key, payload: JSON.parse(a as string), projection: JSON.parse(a as string), source: c, valid: true };
        db.entities.push(row); rows = [row]; break;
      }
      case 'resolve': {
        const mapped = db.identities.find(i => i.id === a)!;
        mapped.entity_id = b ?? c; mapped.resolved = true; break;
      }
      case 'context': {
        const mapping = (kind: string) => db.entities.filter(x => x.kind === kind)
          .map(x => ({ source_id: x.key, id: x.entity_id })).sort((x, y) => x.source_id < y.source_id ? -1 : 1);
        rows = [{ result: badContext ? {} : { contract: 'p4-storage/1.0', catalog_version: 'p4-catalog/1.0',
          actor: { id: db.user!.id, issuer: 'p4-demo', subject: 'manual-purchase-service' },
          currency: { id: db.currency!.id, code: 'BRL' }, suppliers: mapping('supplier'), departments: mapping('department') } }]; break;
      }
      case 'BEGIN ISOLATION LEVEL READ COMMITTED': before = structuredClone(db); break;
      case 'ROLLBACK': db = before; break;
      case 'COMMIT': case 'SET CONSTRAINTS ALL IMMEDIATE': break;
      default:
        if (!sql.startsWith('SET LOCAL ') && !sql.startsWith('LOCK TABLE ')) throw new Error('Unexpected SQL in fake');
    }
    return { rows: structuredClone(rows) };
  } };
  return { client, calls, who, grants, applied, failures, get db() { return db; },
    orphan: () => { orphan = true; }, badContext: () => { badContext = true; } };
}

describe('P4 administrative provisioning (offline)', () => {
  function extended() {
    const f = fixture(); f.who.database = 'synthetic_p4_comparability_test';
    f.applied.push({ migration_name: P4_COMPARABILITY_MIGRATIONS[2].name,
      checksum: P4_COMPARABILITY_MIGRATIONS[2].hash, complete: true, rolled_back: false });
    Object.assign(f.grants, { comparability_safe: true }); return f;
  }
  function apiCatalog() {
    const f = extended(); f.who.database = 'synthetic_detector_anomalias_compras_test'; return f;
  }
  it.each([0, 1, 2])('pins only the LF and full CRLF representations of approved migration %s', index => {
    const migration = P4_COMPARABILITY_MIGRATIONS[index];
    // Read SQL as bytes only; never execute it or consult the database.
    const canonical = readFileSync(new URL(`../../../prisma/migrations/${migration.name}/migration.sql`, import.meta.url), 'utf8').replaceAll('\r\n', '\n');
    expect(canonical).not.toContain('\r');
    expect(createHash('sha256').update(canonical).digest('hex')).toBe(migration.hash);
    expect(createHash('sha256').update(canonical.replaceAll('\n', '\r\n')).digest('hex')).toBe(crlfChecksums[index]);
    expect(migration.crlfHash).toBe(crlfChecksums[index]);
  });
  describe.each(['p4-v1', 'comparability-v1', 'p4-api-comparability-v1'] as const)('checksum compatibility in %s', profile => {
    it.each(['LF', 'CRLF'])('accepts %s, preserves a rolled-back attempt and remains idempotent', async eol => {
        const f = profile === 'p4-v1' ? fixture() : profile === 'comparability-v1' ? extended() : apiCatalog();
        if (eol === 'CRLF') f.applied.forEach((row, i) => { row.checksum = crlfChecksums[i]; });
        f.applied.unshift({ ...f.applied[0], checksum: 'b050777' + '0'.repeat(57), complete: false, rolled_back: true });
        const first = await provisionP4(f.client, profile); const state = structuredClone(f.db); f.calls.length = 0;
        const repeated = await provisionP4(f.client, profile);
        expect(repeated.user).toEqual({ id: first.user.id, created: false });
        expect(repeated.currency).toEqual({ id: first.currency.id, created: false });
        expect(f.db).toEqual(state);
        expect(f.calls.some(c => /INSERT INTO|\/\* p4:(observe|register|resolve|write-)/.test(c.sql))).toBe(false);
    });
  });
  it.each(['missing', 'unfinished', 'unresolved', 'unknown', 'mixed-eol', 'changed-sql'])
  ('still rejects invalid database history with CRLF checksums: %s', async scenario => {
    const f = apiCatalog(); f.applied.forEach((row, i) => { row.checksum = crlfChecksums[i]; });
    f.applied.unshift({ ...f.applied[0], checksum: 'b050777' + '0'.repeat(57), complete: false, rolled_back: true });
    if (scenario === 'missing') f.applied.pop();
    if (scenario === 'unfinished') f.applied[3].complete = false;
    if (scenario === 'unresolved') f.applied[0].rolled_back = false;
    if (scenario === 'unknown') f.applied[3].checksum = 'f'.repeat(64);
    if (scenario === 'mixed-eol' || scenario === 'changed-sql') {
      const body = readFileSync(new URL('../../../prisma/migrations/20261119000100_p4_comparability/migration.sql', import.meta.url), 'utf8').replaceAll('\r\n', '\n');
      const changed = scenario === 'mixed-eol' ? body.replace('\n', '\r\n') : body + '\nSELECT 1;\n';
      f.applied[3].checksum = createHash('sha256').update(changed).digest('hex');
    }
    await expect(provisionP4(f.client, 'p4-api-comparability-v1')).rejects.toThrow('P4_PROVISION_MIGRATIONS');
    expect(f.db).toEqual(empty()); expect(f.calls.at(-1)?.sql).toBe('ROLLBACK');
    expect(f.calls.some(c => /INSERT INTO|^LOCK TABLE/.test(c.sql))).toBe(false);
  });
  it('provisions the API database with three migrations and reuses the same catalog on replay', async () => {
    const f = apiCatalog(); const first = await provisionP4(f.client, 'p4-api-comparability-v1');
    expect(first.user.created && first.currency.created).toBe(true);
    expect(f.db.entities).toHaveLength(6); expect(f.db.identities).toHaveLength(6); expect(f.db.sources).toHaveLength(8);
    const check = f.calls.find(c => c.sql.includes('/* p4:permissions */'))!;
    expect(check.values.slice(1)).toEqual([13, 41]);
    expect(check.values[0]).toHaveLength(14);
    expect(check.values[0]).toEqual(expect.arrayContaining(['app.p4_cmp_write(text,jsonb)', 'app.p4_cmp_read(uuid,integer)']));
    expect(f.calls.at(-2)?.sql).toBe('SET CONSTRAINTS ALL IMMEDIATE'); expect(f.calls.at(-1)?.sql).toBe('COMMIT');
    const before = structuredClone(f.db); f.calls.length = 0;
    const repeated = await provisionP4(f.client, 'p4-api-comparability-v1');
    expect(repeated.user).toEqual({ id: first.user.id, created: false });
    expect(repeated.currency).toEqual({ id: first.currency.id, created: false });
    expect(repeated.suppliers).toEqual(first.suppliers.map(x => ({ ...x, created: false })));
    expect(repeated.departments).toEqual(first.departments.map(x => ({ ...x, created: false })));
    expect(f.db).toEqual(before);
    expect(f.calls.some(c => /INSERT INTO|\/\* p4:(observe|register|resolve|write-)/.test(c.sql))).toBe(false);
  });
  it.each(['two-migrations', 'unfinished', 'unexpected', 'duplicate', 'unresolved'])
  ('rejects invalid API migration history before catalog writes: %s', async scenario => {
    const f = apiCatalog();
    if (scenario === 'two-migrations') f.applied.pop();
    if (scenario === 'unfinished') f.applied[2].complete = false;
    if (scenario === 'unexpected') f.applied.push({ ...f.applied[2], migration_name: 'unknown' });
    if (scenario === 'duplicate') f.applied.push({ ...f.applied[2] });
    if (scenario === 'unresolved') f.applied.unshift({ ...f.applied[0], complete: false });
    await expect(provisionP4(f.client, 'p4-api-comparability-v1')).rejects.toThrow('P4_PROVISION_MIGRATIONS');
    expect(f.db).toEqual(empty()); expect(f.calls.at(-1)?.sql).toBe('ROLLBACK');
    expect(f.calls.some(c => /INSERT INTO|^LOCK TABLE/.test(c.sql))).toBe(false);
  });
  it.each([0, 1, 2])('checks each approved checksum in the API profile: %s', async index => {
    const f = apiCatalog(); f.applied[index].checksum = '0'.repeat(64);
    await expect(provisionP4(f.client, 'p4-api-comparability-v1')).rejects.toThrow('P4_PROVISION_MIGRATIONS');
    expect(f.db).toEqual(empty());
  });
  it.each(['synthetic_p4_comparability_test', 'production'])('rejects a different API provisioning database: %s', async database => {
    const f = apiCatalog(); f.who.database = database;
    await expect(provisionP4(f.client, 'p4-api-comparability-v1')).rejects.toThrow('P4_PROVISION_TARGET');
    expect(f.db).toEqual(empty());
  });
  it.each([...Object.keys(permissions), 'comparability_safe'])('preserves strict API ACL checks: %s', async key => {
    const f = apiCatalog(); Object.assign(f.grants, { [key]: false });
    await expect(provisionP4(f.client, 'p4-api-comparability-v1')).rejects.toThrow('P4_PROVISION_PERMISSION');
    expect(f.db).toEqual(empty()); expect(f.calls.some(c => /INSERT INTO|^LOCK TABLE/.test(c.sql))).toBe(false);
  });
  it.each(['p4-v1', 'comparability-v1'] as const)('does not widen the old profile for the API database with three migrations: %s', async profile => {
    const f = apiCatalog();
    await expect(provisionP4(f.client, profile)).rejects.toThrow(profile === 'p4-v1' ? 'P4_PROVISION_MIGRATIONS' : 'P4_PROVISION_TARGET');
    expect(f.db).toEqual(empty());
  });
  it('preserves rollback and uncertain commit handling in the API profile', async () => {
    const failed = apiCatalog(); failed.failures.set('write-department', { code: '23503' });
    await expect(provisionP4(failed.client, 'p4-api-comparability-v1')).rejects.toThrow('P4_PROVISION_INTEGRITY');
    expect(failed.db).toEqual(empty()); expect(failed.calls.at(-1)?.sql).toBe('ROLLBACK');
    const uncertain = apiCatalog(); uncertain.failures.set('COMMIT', new Error('lost connection'));
    await expect(provisionP4(uncertain.client, 'p4-api-comparability-v1')).rejects.toThrow('P4_PROVISION_COMMIT_UNKNOWN');
    expect(uncertain.calls.filter(c => c.sql === 'COMMIT')).toHaveLength(1);
  });
  it('explicitly provisions the 13-table profile without changing the legacy profile', async () => {
    const f = extended();
    const first = await provisionP4(f.client, 'comparability-v1');
    expect(first.suppliers).toHaveLength(3); expect(first.departments).toHaveLength(3);
    const before = structuredClone(f.db);
    const repeated = await provisionP4(f.client, 'comparability-v1');
    expect(repeated.user.created).toBe(false); expect(f.db).toEqual(before);
    const check = f.calls.find(c => c.sql.includes('/* p4:permissions */'))!;
    expect(check.values.slice(1)).toEqual([13, 41]);
    expect(check.values[0]).toHaveLength(14);
    expect(check.values[0]).toEqual(expect.arrayContaining(['app.p4_cmp_write(text,jsonb)', 'app.p4_cmp_read(uuid,integer)']));
  });
  it('refuses the comparability profile on the existing P4 database before any write', async () => {
    const f = fixture(); await expect(provisionP4(f.client, 'comparability-v1')).rejects.toThrow('P4_PROVISION_TARGET');
    expect(f.db).toEqual(empty());
    expect(f.calls.some(c => /INSERT INTO|^LOCK TABLE/.test(c.sql))).toBe(false);
  });
  it.each(['missing', 'checksum', 'unfinished', 'unexpected', 'duplicate', 'legacy-profile', 'privileges'])
  ('refuses an unsafe extended preflight: %s', async scenario => {
    const f = extended();
    if (scenario === 'missing') f.applied.pop();
    if (scenario === 'checksum') f.applied[2].checksum = '0'.repeat(64);
    if (scenario === 'unfinished') f.applied[2].complete = false;
    if (scenario === 'unexpected') f.applied.push({ ...f.applied[2], migration_name: 'unknown' });
    if (scenario === 'duplicate') f.applied.push({ ...f.applied[2] });
    if (scenario === 'privileges') Object.assign(f.grants, { comparability_safe: false });
    await expect(provisionP4(f.client, scenario === 'legacy-profile' ? 'p4-v1' : 'comparability-v1')).rejects.toThrow(/P4_PROVISION_/);
    expect(f.db).toEqual(empty()); expect(f.calls.some(c => /INSERT INTO|^LOCK TABLE/.test(c.sql))).toBe(false);
  });
  it('still accepts resolved attempts for the extended profile and rejects unresolved ones', async () => {
    const f = extended(); f.applied.unshift({ ...f.applied[2], checksum: 'old', complete: false, rolled_back: true });
    await expect(provisionP4(f.client, 'comparability-v1')).resolves.toHaveProperty('suppliers');
    f.applied[0].rolled_back = false;
    await expect(provisionP4(f.client, 'comparability-v1')).rejects.toThrow('P4_PROVISION_MIGRATIONS');
  });
  it('rolls back on identity refusal before any catalog write', async () => {
    const calls: string[] = [];
    const client: ProvisionClient = { query: async (text) => {
      calls.push(text);
      return { rows: text.includes('session_user') ? [{ session_user: 'postgres' }] : [] };
    } };
    await expect(provisionP4(client)).rejects.toThrow('P4_PROVISION_TARGET');
    expect(calls[0]).toMatch(/^BEGIN/);
    expect(calls.at(-1)).toBe('ROLLBACK');
    expect(calls.some(sql => /INSERT|app\.write_|app\.observe_source|app\.register_source/.test(sql))).toBe(false);
  });

  it('creates exactly the fixed synthetic catalog through audited writers in one transaction', async () => {
    const f = fixture(); const result = await provisionP4(f.client);
    expect(result.namespace).toBe('p4-catalog/1.0');
    expect(result.user.created && result.currency.created).toBe(true);
    expect(result.suppliers.map(x => x.source_id)).toEqual(['sup-obra', 'sup-base', 'sup-estrutura']);
    expect(result.departments.map(x => x.source_id)).toEqual(['dep-obras', 'dep-manutencao', 'dep-almoxarifado']);
    expect(f.db.entities).toHaveLength(6); expect(f.db.identities).toHaveLength(6); expect(f.db.sources).toHaveLength(8);
    expect(f.db.entities.every(x => x.revision_no === 1 && x.valid)).toBe(true);
    expect(f.db.sources.every(x => x.namespace === 'p4-catalog/1.0' && x.original_content.origin === 'synthetic')).toBe(true);
    expect(f.calls.at(-2)?.sql).toBe('SET CONSTRAINTS ALL IMMEDIATE'); expect(f.calls.at(-1)?.sql).toBe('COMMIT');
    expect(f.calls.filter(x => /INSERT INTO app\./.test(x.sql)).map(x => x.sql.match(/INSERT INTO app\.(\w+)/)?.[1]))
      .toEqual(['users', 'currencies']);
    expect(f.calls.filter(x => x.sql.includes('app.write_'))).toHaveLength(6);
    expect(f.calls.filter(x => x.sql.includes('app.observe_source')).every(x => x.sql.includes('NULL::uuid'))).toBe(true);
    expect(f.calls.some(x => /UPDATE |DELETE |GRANT |ALTER |write_purchase|capture_line\(/.test(x.sql) && x.sql.includes('/* p4:write-'))).toBe(false);
  });

  it('reuses all UUIDs and creates no new versions, origins or audit calls on repetition', async () => {
    const f = fixture(); const first = await provisionP4(f.client); const initial = structuredClone(f.db); f.calls.length = 0;
    const second = await provisionP4(f.client);
    expect(second.user).toEqual({ id: first.user.id, created: false });
    expect(second.currency).toEqual({ id: first.currency.id, created: false });
    expect(second.suppliers).toEqual(first.suppliers.map(x => ({ ...x, created: false })));
    expect(second.departments).toEqual(first.departments.map(x => ({ ...x, created: false })));
    expect(f.db).toEqual(initial);
    expect(f.calls.some(x => /INSERT INTO|\/\* p4:(observe|register|resolve|write-)/.test(x.sql))).toBe(false);
  });

  it('acquires the same catalog locks before reading or inserting mutable bootstrap records', async () => {
    const f = fixture(); await provisionP4(f.client);
    const lock = f.calls.findIndex(x => x.sql.startsWith('LOCK TABLE '));
    expect(lock).toBeGreaterThan(f.calls.findIndex(x => x.sql.includes('/* p4:permissions */')));
    expect(lock).toBeLessThan(f.calls.findIndex(x => x.sql.includes('/* p4:user-read */')));
    expect(f.calls[lock].sql).toBe('LOCK TABLE app.currencies,app.users,app.suppliers,app.departments,app.source_identities,app.source_references IN SHARE ROW EXCLUSIVE MODE');
  });
  it('does not write or retry when the catalog lock times out', async () => {
    const f = fixture(); f.failures.set('LOCK TABLE app.currencies,app.users,app.suppliers,app.departments,app.source_identities,app.source_references IN SHARE ROW EXCLUSIVE MODE', { code: '55P03' });
    await expect(provisionP4(f.client)).rejects.toThrow('P4_PROVISION_DATABASE');
    expect(f.db).toEqual(empty()); expect(f.calls.filter(x => x.sql.startsWith('LOCK TABLE'))).toHaveLength(1);
  });
  it.each(Object.keys(identity))('rejects an incompatible server identity: %s', async key => {
    const f = fixture(); Object.assign(f.who, { [key]: null });
    await expect(provisionP4(f.client)).rejects.toThrow('P4_PROVISION_TARGET');
    expect(f.db).toEqual(empty()); expect(f.calls.at(-1)?.sql).toBe('ROLLBACK');
  });
  it.each(Object.keys(permissions))('refuses inadequate permissions before writing: %s', async key => {
    const f = fixture(); Object.assign(f.grants, { [key]: false });
    await expect(provisionP4(f.client)).rejects.toThrow('P4_PROVISION_PERMISSION');
    expect(f.db).toEqual(empty()); expect(f.calls.some(x => /INSERT INTO/.test(x.sql))).toBe(false);
  });
  it.each([false, true])('accepts resolved historical attempts independently of row order (reverse=%s)', async reverse => {
    const f = fixture();
    // Synthetic full checksum: the user supplied only the old checksum prefix.
    f.applied.unshift({ ...f.applied[0], checksum: 'b050777' + '0'.repeat(57), complete: false, rolled_back: true });
    if (reverse) f.applied.reverse();
    expect((await provisionP4(f.client)).suppliers).toHaveLength(3);
    const query = f.calls.find(x => x.sql.includes('/* p4:migrations */'))!.sql;
    expect(query).toContain('rolled_back_at IS NOT NULL AS rolled_back');
    expect(query).toContain('finished_at IS NOT NULL AND rolled_back_at IS NULL AND applied_steps_count=1 AS complete');
    expect(f.calls.at(-1)?.sql).toBe('COMMIT');
  });
  it.each(['unresolved', 'missing-replacement', 'bad-replacement', 'duplicate-applied', 'unknown-applied', 'unknown-reverted', 'invalid-status'])
  ('refuses invalid history even with a resolved attempt: %s', async scenario => {
    const f = fixture();
    f.applied.unshift({ ...f.applied[0], checksum: 'b050777' + '0'.repeat(57), complete: false, rolled_back: true });
    if (scenario === 'unresolved') f.applied[0].rolled_back = false;
    if (scenario === 'missing-replacement') f.applied.splice(1, 1);
    if (scenario === 'bad-replacement') f.applied[1].checksum = 'f'.repeat(64);
    if (scenario === 'duplicate-applied') f.applied.push({ ...f.applied[1] });
    if (scenario === 'unknown-applied') f.applied.push({ ...f.applied[1], migration_name: 'unexpected' });
    if (scenario === 'unknown-reverted') f.applied[0].migration_name = 'unexpected';
    if (scenario === 'invalid-status') Object.assign(f.applied[0], { rolled_back: null });
    await expect(provisionP4(f.client)).rejects.toThrow('P4_PROVISION_MIGRATIONS');
    expect(f.calls.at(-1)?.sql).toBe('ROLLBACK');
    expect(f.calls.some(x => /INSERT INTO|\/\* p4:(observe|register|resolve|write-)/.test(x.sql))).toBe(false);
  });
  it.each(['missing', 'checksum', 'unfinished', 'extra'])('refuses migration history %s', async scenario => {
    const f = fixture();
    if (scenario === 'missing') f.applied.pop();
    if (scenario === 'checksum') f.applied[0].checksum = 'wrong';
    if (scenario === 'unfinished') f.applied[1].complete = false;
    if (scenario === 'extra') f.applied.push({ ...f.applied[1] });
    await expect(provisionP4(f.client)).rejects.toThrow('P4_PROVISION_MIGRATIONS');
    expect(f.db).toEqual(empty());
  });

  it.each(['inactive-user', 'user-name', 'currency-name', 'payload', 'projection', 'unresolved', 'revision-evidence', 'source', 'hash', 'duplicate-source'])
  ('refuses existing incompatible state without changing it: %s', async scenario => {
    const f = fixture(); await provisionP4(f.client);
    switch (scenario) {
      case 'inactive-user': f.db.user!.is_active = false; break;
      case 'user-name': f.db.user!.display_name = 'Unrelated'; break;
      case 'currency-name': f.db.currency!.name = 'Unrelated'; break;
      case 'payload': f.db.entities[0].payload.tier = 'invented'; break;
      case 'projection': f.db.entities[0].projection.name = 'Other'; break;
      case 'unresolved': f.db.identities[0].resolved = false; break;
      case 'revision-evidence': f.db.entities[0].valid = false; break;
      case 'source': f.db.sources[0].original_content.database_id = 'wrong'; break;
      case 'hash': f.db.sources[2].content_hash = 'f'.repeat(64); break;
      case 'duplicate-source': f.db.sources.push({ ...f.db.sources[0] }); break;
    }
    const prior = structuredClone(f.db); f.calls.length = 0;
    await expect(provisionP4(f.client)).rejects.toThrow('P4_PROVISION_CONFLICT');
    expect(f.db).toEqual(prior); expect(f.calls.at(-1)?.sql).toBe('ROLLBACK');
    expect(f.calls.some(x => /INSERT INTO|\/\* p4:(observe|register|resolve|write-)/.test(x.sql))).toBe(false);
  });
  it('refuses adoption of an orphan/same-name record and rolls back bootstrap', async () => {
    const f = fixture(); f.orphan();
    await expect(provisionP4(f.client)).rejects.toThrow('P4_PROVISION_CONFLICT'); expect(f.db).toEqual(empty());
  });
  it.each(['observe', 'register', 'write-supplier', 'write-department', 'resolve', 'SET CONSTRAINTS ALL IMMEDIATE'])
  ('rolls back the complete transaction after a failure in %s', async tag => {
    const f = fixture(); f.failures.set(tag, { code: '23503', message: 'secret URL and driver details' });
    await expect(provisionP4(f.client)).rejects.toThrow(/^P4_PROVISION_INTEGRITY$/);
    expect(f.db).toEqual(empty()); expect(f.calls.at(-1)?.sql).toBe('ROLLBACK');
    expect(f.calls.some(x => x.sql === 'COMMIT')).toBe(false);
  });
  it('checks the final context before committing', async () => {
    const f = fixture(); f.badContext();
    await expect(provisionP4(f.client)).rejects.toThrow('P4_PROVISION_INTEGRITY'); expect(f.db).toEqual(empty());
  });
  it.each([['42501', 'PERMISSION'], ['23505', 'CONFLICT'], ['42601', 'DATABASE'], ['25P02', 'DATABASE'], ['ECONNRESET', 'DATABASE']])
  ('sanitizes SQLSTATE %s as %s without retry', async (code, expected) => {
    const f = fixture(); f.failures.set('register', { code, message: 'secret', stack: 'secret' });
    await expect(provisionP4(f.client)).rejects.toThrow(new RegExp(`^P4_PROVISION_${expected}$`));
    expect(f.calls.filter(x => x.sql.includes('/* p4:register */'))).toHaveLength(1);
  });
  it('does not claim rollback when rollback itself fails', async () => {
    const f = fixture(); f.failures.set('write-supplier', new Error('secret')); f.failures.set('ROLLBACK', new Error('secret'));
    await expect(provisionP4(f.client)).rejects.toThrow(/^P4_PROVISION_ROLLBACK_UNCONFIRMED$/);
  });
  it('reports an unknown commit outcome instead of claiming rollback or retrying', async () => {
    const f = fixture(); f.failures.set('COMMIT', new Error('connection lost'));
    await expect(provisionP4(f.client)).rejects.toThrow(/^P4_PROVISION_COMMIT_UNKNOWN$/);
    expect(f.calls.filter(x => x.sql === 'COMMIT')).toHaveLength(1);
  });
});
