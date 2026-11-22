import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { catalogContract, parseFunctions } from './catalog-contract.js';
import { buildCatalogChecks } from './catalog-checks.js';
import { diagnosticError } from './diagnostics.mjs';

// Separate, pinned profile; the 11-table contract remains available unchanged.
const sql = readFileSync(new URL('../../../prisma/migrations/20261119000100_p4_comparability/migration.sql', import.meta.url), 'utf8').replaceAll('\r\n', '\n');
export const comparabilityMigrationHash = createHash('sha256').update(sql).digest('hex');
if (comparabilityMigrationHash !== '35955a7de1374ba2971ff55f2082ddd6923d3fa9f2b6690ca220b03cb4eae95d') throw diagnosticError('CATALOG_CONTRACT');
const contract = structuredClone(catalogContract);
const names = (value: string) => value.split(',').map(v => v.trim());
// Commas in keys/calls/strings are not column separators. Only this pinned DDL
// grammar is accepted, and it is parsed as text: no SQL is executed here.
function clauses(body: string) {
  const result: string[] = []; let depth = 0; let quoted = false; let start = 0;
  for (let i = 0; i < body.length; i++) {
    const c = body[i];
    if (c === "'") { if (quoted && body[i + 1] === "'") { i++; continue; } quoted = !quoted; }
    if (quoted) continue;
    if (c === '(') depth++; if (c === ')') depth--;
    if (c === ',' && depth === 0) { result.push(body.slice(start, i).trim()); start = i + 1; }
  }
  result.push(body.slice(start).trim());
  if (quoted || depth !== 0) throw diagnosticError('CATALOG_CONTRACT');
  return result;
}
for (const match of sql.matchAll(/CREATE TABLE app\.(\w+) \(([\s\S]*?)\n\);/g)) {
  const [, table, body] = match; contract.tables.push(table);
  for (const clause of clauses(body)) {
    if (!clause.startsWith('CONSTRAINT ')) {
      const field = /^(\w+) (text|jsonb|uuid|integer|timestamptz\(3\))( NOT NULL)?(?: DEFAULT (.*))?$/.exec(clause);
      if (!field) throw diagnosticError('CATALOG_CONTRACT');
      contract.columns.push({ table, name: field[1], type: field[2].replace('timestamptz(3)', 'timestamp(3) with time zone'),
        not_null: !!field[3], default_expression: field[4] ?? null });
      continue;
    }
    const constraint = /^CONSTRAINT (\w+) (PRIMARY KEY|UNIQUE|FOREIGN KEY|CHECK) \(([\s\S]*)$/.exec(clause);
    if (!constraint) throw diagnosticError('CATALOG_CONTRACT');
    const [, name, kind, rest] = constraint;
    const row: typeof contract.constraints[number] = { table, name, kind: '', columns: [], foreign_table: null,
      foreign_columns: [], on_delete: ' ', on_update: ' ', deferrable: false, deferred: false, expression: null };
    if (kind === 'CHECK') { row.kind = 'c'; row.expression = rest.slice(0, -1); }
    else if (kind === 'FOREIGN KEY') {
      const fk = /^([^)]+)\)\s+REFERENCES app\.(\w+)\(([^)]+)\) ON DELETE RESTRICT ON UPDATE RESTRICT$/.exec(rest);
      if (!fk) throw diagnosticError('CATALOG_CONTRACT');
      Object.assign(row, { kind: 'f', columns: names(fk[1]), foreign_table: fk[2], foreign_columns: names(fk[3]), on_delete: 'r', on_update: 'r' });
    } else {
      row.kind = kind === 'PRIMARY KEY' ? 'p' : 'u'; row.columns = names(rest.slice(0, -1));
      contract.indexes.push({ table, name, columns: row.columns, unique: true, primary: row.kind === 'p', predicate: null });
    }
    contract.constraints.push(row);
  }
}
for (const m of sql.matchAll(/CREATE INDEX (\w+) ON app\.(\w+)\(([^)]+)\);/g)) {
  contract.indexes.push({ table: m[2], name: m[1], columns: names(m[3]), unique: false, primary: false, predicate: null });
}
for (const table of ['p4_comparability_definitions', 'p4_comparability_revisions']) {
  for (const [name, type] of [['immutable_rows', 27], ['preserve_table', 34]] as const) {
    contract.triggers.push({ table, name, type, function_name: 'deny_mutation', deferrable: false, deferred: false, args_hex: '' });
  }
}
const functions = parseFunctions(sql, new Set(['p4_cmp_write(text,jsonb)', 'p4_cmp_read(uuid,integer)']), true);
if (functions.length !== 10 || functions.filter(f => f.executable).length !== 2
  || contract.tables.length !== 13 || contract.columns.length !== catalogContract.columns.length + 20
  || contract.constraints.length !== catalogContract.constraints.length + 14 || contract.indexes.length !== 60) throw diagnosticError('CATALOG_CONTRACT');
contract.functions.push(...functions);
export const comparabilityCatalogContract = contract;
export const comparabilityCatalogChecks = buildCatalogChecks(contract);
