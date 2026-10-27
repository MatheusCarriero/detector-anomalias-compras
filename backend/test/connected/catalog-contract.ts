import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { diagnosticError } from './diagnostics.mjs';

// Parse only the reviewed, pinned migration grammar. Never execute its SQL.
// A migration change requires an explicit contract review, not automatic acceptance.
const bytes = readFileSync(new URL('../../../prisma/migrations/20261020000100_first_increment/migration.sql', import.meta.url));
const sql = bytes.toString('utf8').replaceAll('\r\n', '\n');
// Git checkouts may use either LF or CRLF; pin the canonical LF content.
export const migrationHash = createHash('sha256').update(sql).digest('hex');
if (migrationHash !== '4bc2d19996d1adc10ab05a68eeb17b78153e3725c8d0bcb1c6781fc88848311f') {
  throw diagnosticError('CATALOG_CONTRACT');
}
const quotedNames = (text: string) => text.split(',').map((x) => x.trim().replaceAll('"', ''));
const pgType = (type: string) => type.toLowerCase()
  .replace('timestamptz(3)', 'timestamp(3) with time zone')
  .replace('timestamptz', 'timestamp with time zone')
  .replace('varchar', 'character varying').replace('decimal', 'numeric');

type Constraint = {
  table: string; name: string; kind: string; columns: string[];
  foreign_table: string | null; foreign_columns: string[];
  on_delete: string; on_update: string; deferrable: boolean; deferred: boolean;
  expression: string | null;
};
type Index = { table: string; name: string; columns: string[]; unique: boolean; primary: boolean; predicate: string | null };
type Trigger = { table: string; name: string; function_name: string; type: number; deferrable: boolean; deferred: boolean; args_hex: string };

const tables: string[] = [];
const columns: { table: string; name: string; type: string; not_null: boolean; default_expression: string | null }[] = [];
const constraints: Constraint[] = [];
const indexes: Index[] = [];
for (const match of sql.matchAll(/CREATE TABLE "(\w+)" \(([\s\S]*?)\n\);/g)) {
  const [, table, body] = match;
  tables.push(table);
  for (const field of body.matchAll(/^    "(\w+)" ([A-Z]+(?:\(\d+(?:,\d+)?\))?)([^\n]*?)(?:,)?$/gm)) {
    columns.push({ table, name: field[1], type: pgType(field[2]), not_null: field[3].includes('NOT NULL'),
      default_expression: field[3].match(/DEFAULT (.*)/)?.[1] ?? null });
  }
  const pk = /CONSTRAINT "(\w+)" PRIMARY KEY \(([^)]+)\)/.exec(body);
  if (!pk) throw diagnosticError('CATALOG_CONTRACT');
  constraints.push({ table, name: pk[1], kind: 'p', columns: quotedNames(pk[2]), foreign_table: null,
    foreign_columns: [], on_delete: ' ', on_update: ' ', deferrable: false, deferred: false, expression: null });
  indexes.push({ table, name: pk[1], columns: quotedNames(pk[2]), unique: true, primary: true, predicate: null });
}
for (const match of sql.matchAll(/ALTER TABLE "(\w+)" ADD CONSTRAINT "(\w+)" FOREIGN KEY \(([^)]+)\) REFERENCES "(\w+)"\(([^)]+)\) ON DELETE (NO ACTION|RESTRICT) ON UPDATE (NO ACTION|RESTRICT);/g)) {
  const [, table, name, keys, target, targetKeys, del, upd] = match;
  const deferred = sql.includes(`ALTER CONSTRAINT ${name} DEFERRABLE INITIALLY DEFERRED`);
  constraints.push({ table, name, kind: 'f', columns: quotedNames(keys), foreign_table: target,
    foreign_columns: quotedNames(targetKeys), on_delete: del === 'RESTRICT' ? 'r' : 'a',
    on_update: upd === 'RESTRICT' ? 'r' : 'a', deferrable: deferred, deferred, expression: null });
}
for (const match of sql.matchAll(/ALTER TABLE app\.(\w+) ADD CONSTRAINT (\w+)\s+CHECK \(([\s\S]*?)\);/g)) {
  constraints.push({ table: match[1], name: match[2], kind: 'c', columns: [], foreign_table: null,
    foreign_columns: [], on_delete: ' ', on_update: ' ', deferrable: false, deferred: false, expression: match[3] });
}
for (const match of sql.matchAll(/CREATE (UNIQUE )?INDEX "?(\w+)"? ON (?:app\.)?"?(\w+)"?\(([^)]+)\)(?:\s+WHERE ([^;]+))?;/g)) {
  indexes.push({ table: match[3], name: match[2], columns: quotedNames(match[4]), unique: !!match[1], primary: false, predicate: match[5] ?? null });
}

const allowed = new Set([
  'write_supplier(uuid,uuid,jsonb,uuid,uuid,text,text)',
  'write_department(uuid,uuid,jsonb,uuid,uuid,text,text)',
  'write_purchase_order_line(uuid,uuid,jsonb,uuid,uuid,uuid,uuid,uuid,text,text)',
  'register_source_identity(text,text,text,uuid)', 'resolve_source_identity(uuid,uuid,uuid,uuid,uuid)',
  'observe_source(text,text,uuid,uuid,text,text,text,text,jsonb,text)',
  'capture_line(uuid,uuid)', 'seal_snapshot(uuid,uuid)',
]);
const functions = Array.from(sql.matchAll(/CREATE FUNCTION app\.(\w+)\(([\s\S]*?)\)\s+RETURNS ([\s\S]*?)\s+LANGUAGE (sql|plpgsql)([\s\S]*?)\s+AS \$\$([\s\S]*?)\$\$;/g), (match) => {
  const [, name, parameters, result, language, options, body] = match;
  const args = parameters.trim() ? parameters.split(',').map((arg) => pgType(arg.trim().split(/\s+/)[1])) : [];
  return { name, args, defaults: (parameters.match(/DEFAULT/g) ?? []).length,
    input_names: parameters.trim() ? parameters.split(',').map((arg) => arg.trim().split(/\s+/)[0]) : [],
    input_modes: args.map(() => 'i'),
    output_names: result.startsWith('TABLE(') ? ['entity_id', 'version_id', 'revision_no'] : [],
    output_types: result.startsWith('TABLE(') ? ['uuid', 'uuid', 'integer'] : [],
    output_modes: result.startsWith('TABLE(') ? ['t', 't', 't'] : [],
    defaults_expression: parameters.includes('DEFAULT') ? parameters.split(',').filter((arg) => arg.includes('DEFAULT'))
      .map((arg) => `NULL::${pgType(arg.trim().split(/\s+/)[1])}`).join(', ') : null,
    result: result.startsWith('TABLE(') ? 'record' : pgType(result.trim()),
    returns_set: result.startsWith('TABLE('), language, definer: options.includes('SECURITY DEFINER'),
    volatility: options.includes('IMMUTABLE') ? 'i' : options.includes('STABLE') ? 's' : 'v',
    config: name === 'snapshot_digest' ? ['DateStyle=ISO, YMD', 'TimeZone=UTC', 'search_path=pg_catalog, app'] : ['search_path=pg_catalog, app'],
    body: body.trim(), executable: allowed.has(`${name}(${args.join(',')})`) };
});

const triggers: Trigger[] = [];
for (const match of sql.matchAll(/^CREATE (CONSTRAINT )?TRIGGER (\w+) (BEFORE|AFTER) ([A-Z ]+) ON app\.(\w+)\s+([\s\S]*?)EXECUTE FUNCTION app\.(\w+)\(([^)]*)\);/gm)) {
  const [, , name, timing, events, table, options, fn, args] = match;
  const type = (options.includes('FOR EACH ROW') ? 1 : 0) + (timing === 'BEFORE' ? 2 : 0)
    + (events.includes('INSERT') ? 4 : 0) + (events.includes('DELETE') ? 8 : 0)
    + (events.includes('UPDATE') ? 16 : 0) + (events.includes('TRUNCATE') ? 32 : 0);
  triggers.push({ table, name, function_name: fn, type, deferrable: options.includes('DEFERRABLE'),
    deferred: options.includes('INITIALLY DEFERRED'),
    args_hex: Buffer.from(args ? args.split(',').map((arg) => `${arg.trim().slice(1, -1)}\0`).join('') : '').toString('hex') });
}
const generatedTriggers: [string[], string, number][] = [
  [['record_versions', 'source_references', 'audit_events'], 'immutable_rows', 27],
  [['currencies', 'suppliers', 'departments', 'purchase_order_lines', 'source_identities', 'decision_snapshots'], 'preserve_rows', 11],
  [tables, 'preserve_table', 34],
];
for (const [owners, name, type] of generatedTriggers) {
  for (const table of owners) triggers.push({ table, name, type, function_name: 'deny_mutation', deferrable: false, deferred: false, args_hex: '' });
}
export const catalogContract = { tables, columns, constraints, indexes, functions, triggers };
if (tables.length !== 11 || constraints.filter((x) => x.kind === 'f').length !== 32 ||
  constraints.filter((x) => x.kind === 'c').length !== 13 || indexes.length !== 52 ||
  functions.length !== 26 || functions.filter((x) => x.executable).length !== 8 || triggers.length !== 30) {
  throw diagnosticError('CATALOG_CONTRACT');
}
