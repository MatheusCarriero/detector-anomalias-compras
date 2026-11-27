import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { PURCHASE_CATALOG } from './purchase-catalog.js';
import { checkPurchaseIdempotency, preparePurchase } from './purchase-contract.js';

vi.mock('node:child_process', () => { throw new Error('Purchase validation must not execute models or subprocesses'); });
vi.mock('pg', () => { throw new Error('Purchase validation must not import a database driver'); });
vi.mock('@prisma/adapter-pg', () => { throw new Error('Purchase validation must not import a database adapter'); });

const now = new Date('2026-11-15T15:00:00.000Z');
const key = '935af6ba-e660-40dc-a268-b13a158599cc';
function request() {
  return {
    contract: 'p4-purchase/1.0', origin: 'manual', idempotency_key: key,
    purchase: {
      supplier_id: 'sup-obra', product_id: 'prod-cimento', department_id: 'dep-obras',
      quantity: 3, unit_price: '0.10', currency: 'BRL', purchase_date: '2026-11-03', payment_days: 30,
    },
  };
}
function prepared(input: unknown = request(), instant = now) {
  const result = preparePurchase(input, instant);
  if (!result.ok) throw new Error(JSON.stringify(result.error));
  return result.value;
}
function rejected(input: unknown, code: string, instant = now) {
  const result = preparePurchase(input, instant);
  expect(result.ok).toBe(false);
  if (result.ok) throw new Error('Expected refusal');
  expect(result.error.code).toBe(code);
  return result;
}

describe('P4 manual purchase contract (no persistence or model)', () => {
  it('prepares exact SQL scalar state and preserves additional commercial fields as source evidence', () => {
    const value = prepared();
    expect(value.contract).toBe('p4-purchase/1.0');
    expect(value.state).toEqual({
      description: 'Cimento CP II · saco de 50 kg', po_date: '2026-11-03',
      quantity: '3', unit_price: '0.10', amount: '0.30',
    });
    expect(value.references).toEqual({
      catalog_namespace: 'p4-catalog/1.0', supplier_source_id: 'sup-obra',
      department_source_id: 'dep-obras', currency_code: 'BRL',
    });
    expect(value.source).toEqual({
      source_namespace: 'p4-manual/1.0', source_entity_kind: 'purchase_order_line', source_id: key,
    });
    expect(value.original_content).toEqual({
      contract: 'p4-purchase/1.0', origin: 'manual',
      catalog_version: 'p4-catalog/1.0', catalog_origin: 'synthetic',
      purchase: {
        supplier: { id: 'sup-obra', name: 'Obra Exemplo — materiais de construção' },
        product: { id: 'prod-cimento', name: 'Cimento CP II · saco de 50 kg', unit: 'saco de 50 kg' },
        department: { id: 'dep-obras', name: 'Obras' }, quantity: 3,
        unit_price: '0.10', total: '0.30', currency: 'BRL', purchase_date: '2026-11-03', payment_days: 30,
      },
    });
    expect(value.validated_at).toBe('2026-11-15T15:00:00.000Z');
    for (const field of ['recorded_at', 'id', 'score']) expect(value).not.toHaveProperty(field);
    expect(JSON.parse(JSON.stringify(value))).toEqual(value);
    expect(value.content_sha256).toBe(createHash('sha256').update(JSON.stringify(value.original_content)).digest('hex'));
  });
  it.each([
    [3, '0.10', '0.10', '0.30'], [7, '19.99', '19.99', '139.93'],
    [1, '0.01', '0.01', '0.01'], [2, '1.2', '1.20', '2.40'],
    [1_000_000, '1000000', '1000000.00', '1000000000000.00'],
  ])('calculates %i × %s without floating-point rounding', (quantity, unit_price, canonical, total) => {
    const input = request(); Object.assign(input.purchase, { quantity, unit_price });
    expect(prepared(input).state).toMatchObject({ quantity: String(quantity), unit_price: canonical, amount: total });
  });
  it.each(Object.keys(request()))('requires root field %s', (name) => {
    const input = request() as Record<string, unknown>; delete input[name]; rejected(input, 'P4_INVALID_STRUCTURE');
  });
  it.each(Object.keys(request().purchase))('requires purchase field %s', (name) => {
    const input = request(); delete (input.purchase as Record<string, unknown>)[name]; rejected(input, 'P4_INVALID_STRUCTURE');
  });
  it.each([null, undefined, [], 'text', 1, true, new Date(), Object.create(request())])('rejects non-JSON records (%s)', (input) => {
    rejected(input, 'P4_INVALID_STRUCTURE');
  });
  it('rejects accessors without evaluating them or exposing their content', () => {
    const input = request(); const getter = vi.fn(() => { throw new Error('secret'); });
    Object.defineProperty(input.purchase, 'unit_price', { get: getter, enumerable: true });
    expect(JSON.stringify(rejected(input, 'P4_INVALID_STRUCTURE'))).not.toContain('secret');
    expect(getter).not.toHaveBeenCalled();
  });
  it.each(['total', 'features', 'score', 'analysis', 'recorded_at', 'actor_user_id', 'model_path', '__proto__'])('rejects injected field %s', (name) => {
    const input = request(); Object.defineProperty(input.purchase, name, { value: 'sensitive', enumerable: true });
    expect(JSON.stringify(rejected(input, 'P4_INVALID_STRUCTURE'))).not.toContain('sensitive');
  });
  it('rejects original_content supplied by callers', () => {
    rejected({ ...request(), original_content: {} }, 'P4_INVALID_STRUCTURE');
  });
  it.each([null, [], 'purchase'])('rejects an invalid nested purchase %s', (purchase) => {
    rejected({ ...request(), purchase }, 'P4_INVALID_STRUCTURE');
  });
  it('sanitizes unexpected validation exceptions without returning messages or stack traces', () => {
    const hostile = new Proxy({}, { getPrototypeOf() { throw new Error('secret/path/credential'); } });
    expect(preparePurchase(hostile, now)).toEqual({ ok: false, error: { code: 'P4_VALIDATION_FAILED', field: 'request' } });
  });
  it.each(['p4-purchase/2.0', 'procurement-demo/1.0', '', null])('rejects incompatible contract %s', (contract) => {
    rejected({ ...request(), contract }, 'P4_UNSUPPORTED_CONTRACT');
  });
  it.each(['synthetic', 'procurement-spend', '', null])('rejects nonmanual origin %s', (origin) => {
    rejected({ ...request(), origin }, 'P4_INVALID_ORIGIN');
  });
  it.each(['USD', 'brl', '', null])('rejects unsupported currency %s', (currency) => {
    const input = request(); Object.assign(input.purchase, { currency }); rejected(input, 'P4_INVALID_CURRENCY');
  });
  it.each(['supplier_id', 'product_id', 'department_id'])('rejects unknown %s', (field) => {
    for (const value of ['SUP-016', 'constructor', '__proto__', '', null, { id: 'sup-obra' }]) {
      const input = request(); Object.assign(input.purchase, { [field]: value }); rejected(input, 'P4_UNAUTHORIZED_CATALOG_ENTRY');
    }
  });
  it.each([0, -1, 1.5, 1_000_001, NaN, Infinity, '3', true, null])('rejects invalid quantity %s', (quantity) => {
    const input = request(); Object.assign(input.purchase, { quantity }); rejected(input, 'P4_INVALID_QUANTITY');
  });
  it.each([0.1, '0', '-1', '1.001', '1e2', '1,20', '1,000.00', ' 1.00', '01', '+1', 'NaN', 'Infinity', '1000000.01', '1.00\n', null])('rejects invalid price %s', (unit_price) => {
    const input = request(); Object.assign(input.purchase, { unit_price }); rejected(input, 'P4_INVALID_UNIT_PRICE');
  });
  it.each([-1, 3651, 1.2, NaN, Infinity, '30', false, null])('rejects invalid payment term %s', (payment_days) => {
    const input = request(); Object.assign(input.purchase, { payment_days }); rejected(input, 'P4_INVALID_PAYMENT_DAYS');
  });
  it.each([0, 3650])('accepts payment boundary %i', (payment_days) => {
    const input = request(); input.purchase.payment_days = payment_days;
    expect(prepared(input).original_content.purchase.payment_days).toBe(payment_days);
  });
  it.each(['2024-02-29', '2000-02-29', '0001-01-01', '2026-11-15'])('accepts retroactive/today date %s without inventing past availability', (purchase_date) => {
    const input = request(); input.purchase.purchase_date = purchase_date;
    expect(prepared(input).state.po_date).toBe(purchase_date);
    expect(prepared(input).validated_at).toBe(now.toISOString());
  });
  it.each(['2025-02-29', '1900-02-29', '2026-04-31', '0000-01-01', '2026-00-01', '2026-01-00', '2026-13-01', '15/11/2026', '2026-11-15T00:00:00Z', '2026-11-15\n', '', null])('rejects invalid civil date %s', (purchase_date) => {
    const input = request(); Object.assign(input.purchase, { purchase_date }); rejected(input, 'P4_INVALID_PURCHASE_DATE');
  });
  it('uses the Sao Paulo commercial day at midnight rather than UTC or machine timezone', () => {
    const input = request(); input.purchase.purchase_date = '2026-11-15';
    rejected(input, 'P4_FUTURE_PURCHASE_DATE', new Date('2026-11-15T02:59:59.999Z'));
    expect(preparePurchase(input, new Date('2026-11-15T03:00:00.000Z')).ok).toBe(true);
    input.purchase.purchase_date = '2026-11-16'; rejected(input, 'P4_FUTURE_PURCHASE_DATE');
  });
  it.each([new Date(NaN), new Date('0000-01-01T00:00:00Z'), new Date('+010000-01-01T00:00:00Z')])('refuses invalid server clock (%s)', (instant) => {
    rejected(request(), 'P4_INVALID_CLOCK', instant);
  });
  it.each(['', 'manual-1', '00000000-0000-0000-0000-000000000000', '935af6ba-e660-50dc-a268-b13a158599cc', `${key} `, `${key}\n`, null, 1])('rejects invalid idempotency key %s', (idempotency_key) => {
    rejected({ ...request(), idempotency_key }, 'P4_INVALID_IDEMPOTENCY_KEY');
  });
  it('normalizes UUID case and price precision for a replay even on a later day', () => {
    const first = request(); first.purchase.unit_price = '1'; const value = prepared(first);
    const receipt = { ...value.source, content_sha256: value.content_sha256 };
    const retry = request(); retry.idempotency_key = key.toUpperCase(); retry.purchase.unit_price = '1.00';
    const candidate = prepared(retry, new Date('2026-11-16T12:00:00Z'));
    expect(checkPurchaseIdempotency(candidate, receipt)).toEqual({ ok: true, outcome: 'replay' });
    expect(checkPurchaseIdempotency(candidate, null)).toEqual({ ok: true, outcome: 'new' });
  });
  it.each([
    ['quantity', 4], ['unit_price', '0.11'], ['supplier_id', 'sup-base'],
    ['product_id', 'prod-tijolo'], ['department_id', 'dep-manutencao'],
    ['purchase_date', '2026-11-04'], ['payment_days', 31],
  ])('reports same-key content conflict for %s', (field, different) => {
    const value = prepared(); const receipt = { ...value.source, content_sha256: value.content_sha256 };
    const input = request(); Object.assign(input.purchase, { [field]: different });
    expect(checkPurchaseIdempotency(prepared(input), receipt)).toEqual({ ok: false, error: { code: 'P4_IDEMPOTENCY_CONFLICT', field: 'idempotency_key' } });
  });
  it.each([
    {}, { source_namespace: 'procurement-spend' }, { source_id: '5a602c29-349b-4532-91a0-497d1dc51142' },
    { source_entity_kind: 'supplier' }, { content_sha256: 'not-a-hash' },
  ])('refuses inconsistent stored identity without fallback (%s)', (override) => {
    const value = prepared();
    const receipt = Object.keys(override).length ? { ...value.source, content_sha256: value.content_sha256, ...override } : {};
    expect(checkPurchaseIdempotency(value, receipt)).toEqual({ ok: false, error: { code: 'P4_INVALID_IDEMPOTENCY_RECORD', field: 'idempotency_key' } });
  });
  it('does not deduplicate equal purchases with different submission keys', () => {
    const a = prepared(); const b = prepared({ ...request(), idempotency_key: '5a602c29-349b-4532-91a0-497d1dc51142' });
    expect(a.source.source_id).not.toBe(b.source.source_id); expect(a.content_sha256).toBe(b.content_sha256);
    expect(checkPurchaseIdempotency(b, null)).toEqual({ ok: true, outcome: 'new' });
  });
  it('does not interpret an omitted lookup result as an absent submission', () => {
    expect(checkPurchaseIdempotency(prepared(), undefined)).toEqual({ ok: false, error: { code: 'P4_INVALID_IDEMPOTENCY_RECORD', field: 'idempotency_key' } });
  });
  it('ignores JSON property order when identifying the same content', () => {
    const input = request();
    input.purchase = Object.fromEntries(Object.entries(input.purchase).reverse()) as typeof input.purchase;
    const reordered = Object.fromEntries(Object.entries(input).reverse());
    expect(prepared(reordered)).toEqual(prepared());
  });
  it('is deterministic, does not mutate inputs and protects catalog, evidence, SQL state and analysis policy', () => {
    const input = request(); const before = structuredClone(input); const a = prepared(input);
    expect(a).toEqual(prepared(input)); expect(input).toEqual(before);
    expect(Reflect.set(a.state, 'amount', '9')).toBe(false);
    expect(Reflect.set(a.original_content.purchase.product, 'unit', 'different')).toBe(false);
    expect(Reflect.set(PURCHASE_CATALOG.products[0], 'name', 'different')).toBe(false);
    expect(Reflect.set(a.analysis, 'status', 'pending')).toBe(false);
    expect(a.analysis).toEqual({ status: 'unavailable', reason: 'manual_source_incompatible_with_procurement_v2' });
  });
  it('accepts precisely the stable IDs and labels loaded by the P4 form from the API catalog', async () => {
    type Element = { value: string; textContent: string; children: Element[]; appendChild: (child: Element) => void;
      replaceChildren: (...children: Element[]) => void; setAttribute: () => void; addEventListener: () => void };
    const elements = new Map<string, Element>();
    function element(): Element { return { value: '', textContent: '', children: [], appendChild(child) { this.children.push(child); },
      replaceChildren(...children) { this.children = children; }, setAttribute() {}, addEventListener() {} }; }
    const document = { addEventListener() {}, getElementById(id: string) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); }, createElement: element };
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ contract: 'p4-purchase/1.0', currency: 'BRL', catalog: PURCHASE_CATALOG }) });
    runInNewContext(readFileSync(new URL('../demo/public/purchase.js', import.meta.url), 'utf8'), {
      window: { addEventListener() {} }, document, fetch, AbortController, setTimeout, clearTimeout, sessionStorage: { getItem: () => null },
    });
    for (let i = 0; i < 12; i++) await Promise.resolve();
    expect(fetch).toHaveBeenCalledOnce(); expect(fetch.mock.calls[0][0]).toBe('/demo/p4/catalog');
    for (const [field, entries] of [['supplier', PURCHASE_CATALOG.suppliers], ['product', PURCHASE_CATALOG.products], ['department', PURCHASE_CATALOG.departments]] as const) {
      expect(elements.get(`purchase-${field}`)?.children.filter(e => e.value).map(({ value, textContent }) => ({ id: value, name: textContent })))
        .toEqual(entries.map(({ id, name }) => ({ id, name })));
    }
  });
});
