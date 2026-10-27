import { diagnosticError } from './diagnostics.mjs';

type Expr = string | Expr[];

// Only the expression subset used by this migration. This never evaluates SQL.
// Unsupported syntax fails closed; parentheses are parsed, never blindly removed.
export function canonicalExpression(source: string): string {
  const fail = (): never => { throw diagnosticError('CATALOG_DEFINITION'); };
  if (typeof source !== 'string' || source.length > 20000) return fail();
  const tokens: string[] = [];
  const lexer = /\s+|'(?:[^']|'')*'|"(?:[^"]|"")*"|[a-zA-Z_][a-zA-Z_0-9.]*|[0-9]+|::|<>|>=|<=|[=~><(),[\]]/gy;
  let offset = 0;
  while (offset < source.length) {
    lexer.lastIndex = offset;
    const match = lexer.exec(source);
    if (!match) return fail();
    offset = lexer.lastIndex;
    if (!/^\s+$/.test(match[0])) tokens.push(match[0]);
  }
  let at = 0;
  const peek = () => tokens[at]?.toUpperCase();
  const take = (token: string) => { if (peek() !== token) fail(); at++; };
  function list(end: string): Expr[] {
    const values: Expr[] = [];
    do { values.push(expression(0)); if (peek() !== ',') break; at++; } while (at < tokens.length);
    take(end);
    return values;
  }
  function expression(min: number): Expr {
    let left: Expr;
    const token = tokens[at++];
    if (!token) return fail();
    if (token === '(') { left = expression(0); take(')'); }
    else if (token.startsWith("'")) left = `literal:${token}`;
    else if (/^[0-9]+$/.test(token)) left = `number:${token}`;
    else if (/^(?:[a-zA-Z_][\w.]*|"[a-zA-Z_][\w]*")$/.test(token)) {
      const name = token.replaceAll('"', '').replace(/^pg_catalog\./, '').toLowerCase();
      if (name === 'array' && peek() === '[') { at++; left = ['array', ...list(']')]; }
      else if (peek() === '(') {
        at++;
        const args = peek() === ')' ? (at++, []) : list(')');
        left = [`call:${name}`, ...args];
      }
      else left = `id:${name}`;
    } else return fail();
    while (at < tokens.length) {
      const op = peek()!;
      // PostgreSQL 18, table 4.2 (supported subset only):
      // https://www.postgresql.org/docs/18/sql-syntax-lexical.html#SQL-PRECEDENCE
      const power = op === 'OR' ? 1 : op === 'AND' ? 2 : op === 'IS' ? 4 :
        ['=', '<>', '>', '<', '>=', '<='].includes(op) ? 5 :
        ['IN', 'NOT'].includes(op) ? 6 : op === '~' ? 7 : op === '::' ? 8 : -1;
      if (power < min) break;
      at++;
      if (op === '::') {
        take('TEXT');
        // PostgreSQL adds text casts to text literals and these varchar fields.
        if (!(typeof left === 'string' && (left.startsWith('literal:') ||
          ['id:code', 'id:country_code', 'id:content_hash'].includes(left)))) left = ['text', left];
      } else if (op === 'IS') {
        const not = peek() === 'NOT'; if (not) at++;
        take('NULL'); left = [not ? 'not-null' : 'null', left];
      } else if (op === 'IN' || op === 'NOT') {
        if (op === 'NOT') take('IN');
        take('('); left = [op === 'NOT' ? 'not-in' : 'in', left, ...list(')')];
      } else if ((op === '=' && peek() === 'ANY') || (op === '<>' && peek() === 'ALL')) {
        at++; take('('); const array = expression(0); take(')');
        if (!Array.isArray(array) || array[0] !== 'array') return fail();
        left = [op === '=' ? 'in' : 'not-in', left, ...array.slice(1)];
      } else {
        const right = expression(power + 1);
        const operands = (value: Expr) => Array.isArray(value) && value[0] === op ? value.slice(1) : [value];
        left = ['AND', 'OR'].includes(op) ? [op, ...operands(left), ...operands(right)] : [op, left, right];
      }
    }
    return left;
  }
  const result = expression(0);
  if (at !== tokens.length) return fail();
  return JSON.stringify(result);
}
