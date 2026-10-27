import { canonicalExpression } from './catalog-expression.js';

describe('catalog CHECK comparison (offline, no SQL execution)', () => {
  it.each([
    ["x IN ('a','b')", "(x = ANY (ARRAY['a'::text, 'b'::text]))"],
    ["amount::text NOT IN ('NaN','Infinity')", "((amount)::text <> ALL (ARRAY['NaN'::text, 'Infinity'::text]))"],
    ["btrim(name) <> '' AND (code IS NULL OR code ~ '^[A-Z]{3}$')",
      "((btrim(name) <> ''::text) AND ((code IS NULL) OR ((code)::text ~ '^[A-Z]{3}$'::text)))"],
    ['revision_no>0 AND ((revision_no=1) = (supersedes_version_id IS NULL))',
      '((revision_no > 0) AND ((revision_no = 1) = (supersedes_version_id IS NULL)))'],
    ['a = b IS NULL', '(a = b) IS NULL'],
  ])('accepts only known PostgreSQL deparser equivalents (%#)', (source, catalog) => {
    expect(canonicalExpression(source)).toEqual(canonicalExpression(catalog));
  });
  it.each([
    ['a AND (b OR c)', '(a AND b) OR c'],
    ['amount::text <> x', 'amount <> x'],
    ['a > b', 'a >= b'], ['a IS NULL', 'a IS NOT NULL'],
    ["x IN ('a','b')", "x IN ('a','c')"],
    ["name = 'a b'", "name = 'ab'"],
    ['a = b IS NULL', 'a = (b IS NULL)'],
    ["a = b IN ('x')", "(a = b) IN ('x')"],
  ])('does not erase meaningful expression differences (%#)', (a, b) => {
    expect(canonicalExpression(a)).not.toEqual(canonicalExpression(b));
  });
  it.each(['', 'x; SELECT 1', 'x -- comment', 'x OR', 'weird(x) OVER ()'])('refuses unsupported syntax: %s', (source) => {
    expect(() => canonicalExpression(source)).toThrow(/DB_TEST/);
  });
});
