import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { PURCHASE_CATALOG } from '../purchases/purchase-catalog.js';

type FormEvent = { target: ElementStub; preventDefault: () => void };
type Listener = (event: FormEvent) => void | Promise<void>;

// Minimal real-markup DOM; all HTTP/storage simulated, HTML insertion forbidden.
class ElementStub {
  value = '';
  hidden = false;
  disabled = false;
  focused = false;
  private text = '';
  children: ElementStub[] = [];
  attributes = new Map<string, string>();
  listeners = new Map<string, Listener[]>();
  constructor(readonly id = '') {}
  get textContent(): string { return this.text + this.children.map((child) => child.textContent).join(' '); }
  set textContent(value: string) { this.text = value; this.children = []; }
  set innerHTML(_value: string) { throw new Error('Unsafe HTML insertion'); }
  setAttribute(key: string, value: string) { this.attributes.set(key, value); }
  removeAttribute(key: string) { this.attributes.delete(key); }
  addEventListener(name: string, listener: Listener) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
  }
  appendChild(child: ElementStub) { this.children.push(child); return child; }
  append(...children: ElementStub[]) { this.children.push(...children); }
  replaceChildren(...children: ElementStub[]) { this.text = ''; this.children = children; }
  focus() { this.focused = true; }
  emit(name: string, event: FormEvent) { return Promise.all((this.listeners.get(name) ?? []).map(listener => Promise.resolve(listener(event)))); }
}

const fields = ['supplier', 'product', 'department', 'quantity', 'unit-price', 'payment-days', 'date'];
const valid = {
  supplier: 'sup-obra', product: 'prod-cimento', department: 'dep-obras',
  quantity: '3', 'unit-price': '0,10', 'payment-days': '30', date: '2026-11-03',
};

const key = '11111111-1111-4111-8111-111111111111';
const storageKey = 'p4-purchase/1.0:submission';
const catalog = { contract: 'p4-purchase/1.0', currency: 'BRL', catalog: PURCHASE_CATALOG };
const response = (data: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => data });
async function flush() { for (let i = 0; i < 20; i++) await Promise.resolve(); }
function savedReceipt() {
  return { id: '22222222-2222-4222-8222-222222222222', idempotency_key: key,
    recorded_at: '2026-11-18T15:00:00.000Z', revision_no: 1, purchase: {
      supplier: PURCHASE_CATALOG.suppliers[0], product: PURCHASE_CATALOG.products[0], department: PURCHASE_CATALOG.departments[0],
      quantity: 3, unit_price: '0.10', total: '0.30', currency: 'BRL', purchase_date: valid.date, payment_days: 30,
    }, analysis: { status: 'unavailable', reason: 'manual_source_incompatible_with_procurement_v2' } };
}
function setup(storage = new Map<string, string>(), initial: unknown = catalog) {
  const html = readFileSync(new URL('./public/index.html', import.meta.url), 'utf8');
  const ids = [...html.matchAll(/id="([^"]+)"/g)].map(m => m[1]);
  const elements = Object.fromEntries(ids.map((id) => [id, new ElementStub(id)]));
  elements['purchase-summary'].hidden = true;
  elements['purchase-prepare'].disabled = true;
  for (const name of ['supplier', 'product', 'department']) {
    const placeholder = new ElementStub();
    placeholder.textContent = 'Selecione';
    elements[`purchase-${name}`].appendChild(placeholder);
  }
  const fetch = vi.fn().mockResolvedValueOnce(response(initial));
  const sessionStorage = { getItem: (k: string) => storage.get(k) ?? null,
    setItem: vi.fn((k: string, v: string) => { storage.set(k, v); }),
    removeItem: vi.fn((k: string) => { storage.delete(k); }) };
  const context = {
    document: {
      getElementById: (id: string) => {
        if (!Object.hasOwn(elements, id)) throw new Error(`Unexpected DOM access: ${id}`);
        return elements[id];
      },
      createElement: () => new ElementStub(),
    },
    fetch, Date, Intl, AbortController, setTimeout, clearTimeout, URLSearchParams,
    crypto: { randomUUID: vi.fn(() => key) }, sessionStorage,
    get localStorage(): never { throw new Error('Persistence forbidden'); },
    get XMLHttpRequest(): never { throw new Error('Network forbidden'); },
  };
  runInNewContext(readFileSync(new URL('./public/purchase.js', import.meta.url), 'utf8'), context);
  function edit(field: string, value: string, eventName = 'input') {
    const element = elements[`purchase-${field}`];
    element.value = value;
    const event = { target: element, preventDefault: vi.fn() };
    void element.emit(eventName, event);
    void elements['purchase-form'].emit(eventName, event);
  }
  function fill(values: Record<string, string> = valid) {
    Object.entries(values).forEach(([name, value]) => edit(name, value, 'change'));
  }
  function submit() {
    const preventDefault = vi.fn();
    void elements['purchase-form'].emit('submit', { target: elements['purchase-form'], preventDefault });
    expect(preventDefault).toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledTimes(1); // Catalog only; preparing never writes.
  }
  return { elements, fetch, edit, fill, submit, storage, sessionStorage,
    click: (id: string) => elements[id].emit('click', { target: elements[id], preventDefault: vi.fn() }) };
}

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-11-18T15:00:00Z')); });
afterEach(() => vi.useRealTimers());

it.each([201, 200])('ends the sending presentation after confirmed HTTP %s without enabling a duplicate', async code => {
  const s = setup(); await flush(); s.fill(); s.submit();
  let finish!: (value: unknown) => void;
  s.fetch.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = s.click('purchase-save');
  expect(s.elements['purchase-save'].textContent).toBe('Cadastrando...');
  expect(s.elements['purchase-save'].attributes.get('aria-busy')).toBe('true');
  expect(s.elements['purchase-save'].disabled).toBe(true);
  await s.click('purchase-save'); expect(s.fetch).toHaveBeenCalledTimes(2);
  const stored = s.storage.get(storageKey);
  finish(response({ contract: 'p4-purchase/1.0', outcome: code === 201 ? 'created' : 'replay', purchase: savedReceipt() }, code));
  await pending;
  expect(s.elements['purchase-form'].attributes.get('aria-busy')).toBe('false');
  expect(s.elements['purchase-save'].attributes.get('aria-busy')).toBe('false');
  expect(s.elements['purchase-save'].attributes.get('data-state')).toBe('confirmed');
  expect(s.elements['purchase-save'].textContent).toBe('Compra cadastrada');
  expect(s.elements['purchase-save'].disabled).toBe(true);
  expect(s.elements['purchase-status'].textContent).toContain('Compra cadastrada com sucesso');
  expect(s.elements['purchase-receipt'].textContent).toContain(savedReceipt().id);
  expect(s.elements['purchase-receipt'].textContent).toContain('0,30');
  expect(s.elements['purchase-new'].attributes.get('data-primary')).toBe('true');
  expect(s.elements['purchase-new'].focused).toBe(true);
  expect(s.storage.get(storageKey)).toBe(stored);
  await s.click('purchase-save'); expect(s.fetch).toHaveBeenCalledTimes(2);
  await s.click('purchase-new');
  expect(s.elements['purchase-save'].textContent).toBe('Cadastrar compra');
  expect(s.elements['purchase-new'].attributes.get('data-primary')).toBe('false');
});

it.each(['conflict', 'validation', 'unavailable', 'network', 'invalid-response'])('ends loading for %s but retains the pending submission', async kind => {
  const s = setup(); await flush(); s.fill(); s.submit();
  if (kind === 'network') s.fetch.mockRejectedValueOnce(new Error('offline'));
  else if (kind === 'invalid-response') s.fetch.mockResolvedValueOnce(response({ contract: 'wrong' }, 201));
  else s.fetch.mockResolvedValueOnce(response({}, kind === 'conflict' ? 409 : kind === 'validation' ? 400 : 503));
  await s.click('purchase-save');
  expect(s.elements['purchase-save'].attributes.get('aria-busy')).toBe('false');
  expect(s.elements['purchase-save'].textContent).toBe('Cadastro não confirmado');
  expect(s.elements['purchase-save'].disabled).toBe(true);
  expect(s.elements['purchase-new'].disabled).toBe(true);
  expect(s.elements['purchase-new'].attributes.get('data-primary')).toBe('false');
  expect(s.elements['purchase-retry'].disabled).toBe(false);
  expect(s.elements['purchase-status'].attributes.get('data-state')).toBe('error');
  expect(s.storage.get(storageKey)).toContain(key);
  expect(s.fetch).toHaveBeenCalledTimes(2);
});

it('distinguishes a lookup from sending, then highlights the confirmed next action', async () => {
  const s = setup(); await flush(); s.fill(); s.submit();
  s.fetch.mockRejectedValueOnce(new Error('offline')); await s.click('purchase-save');
  let finish!: (value: unknown) => void;
  s.fetch.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = s.click('purchase-check');
  expect(s.elements['purchase-check'].textContent).toBe('Consultando...');
  expect(s.elements['purchase-save'].textContent).not.toBe('Cadastrando...');
  finish(response({ contract: 'p4-purchase/1.0', purchase: savedReceipt() })); await pending;
  expect(s.elements['purchase-check'].attributes.get('aria-busy')).toBe('false');
  expect(s.elements['purchase-new'].focused).toBe(true);
});

it('overrides the inherited wait cursor only for P4 controls, reserving it for active requests', () => {
  const css = readFileSync(new URL('./public/style.css', import.meta.url), 'utf8');
  expect(css).toMatch(/#purchase-prepare:disabled, #purchase-save:disabled\s*\{[^}]*cursor: not-allowed/);
  expect(css).toMatch(/#purchase-save\[data-state="confirmed"\]\s*\{[^}]*cursor: default/);
  expect(css).toMatch(/#purchase-save\[aria-busy="true"\][^{]*\{[^}]*cursor: wait/);
});

it('loads a server catalog but never submits on page load', async () => {
  const s = setup(); await flush();
  expect(s.fetch).toHaveBeenCalledOnce();
  expect(s.fetch.mock.calls[0][0]).toBe('/demo/p4/catalog');
  expect(s.elements['purchase-save'].disabled).toBe(true);
});

it('persists the key and exact payload before POST and displays a confirmed receipt', async () => {
  const s = setup(); await flush(); s.fill(); s.submit();
  s.fetch.mockImplementationOnce(async (_url: string, init: { body: string }) => {
    expect(s.storage.get(storageKey)).toContain(init.body);
    return response({ contract: 'p4-purchase/1.0', outcome: 'created', purchase: savedReceipt() }, 201);
  });
  await s.click('purchase-save');
  const [url, init] = s.fetch.mock.calls[1];
  expect(url).toBe('/demo/p4/purchases');
  expect(init.headers['X-P4-Local']).toBe('p4-purchase/1.0');
  expect(JSON.parse(init.body).purchase.unit_price).toBe('0.10');
  expect(JSON.parse(init.body).idempotency_key).toBe(key);
  expect(s.elements['purchase-receipt'].textContent).toContain(savedReceipt().id);
  expect(s.elements['purchase-receipt'].textContent).toContain('0,30');
  expect(s.elements['purchase-save'].disabled).toBe(true);
  expect(s.elements['purchase-new'].disabled).toBe(false);
});

it('keeps an uncertain request through reload; 404 does not authorize a fresh key', async () => {
  const s = setup(); await flush(); s.fill(); s.submit();
  s.fetch.mockRejectedValueOnce(new Error('secret network')); await s.click('purchase-save');
  const sent = s.fetch.mock.calls[1][1].body;
  expect(s.elements['purchase-new'].disabled).toBe(true);
  expect(s.elements['purchase-quantity'].disabled).toBe(true);
  const restored = setup(s.storage); await flush();
  expect(restored.fetch).toHaveBeenCalledOnce(); // No automatic POST or retry.
  restored.fetch.mockResolvedValueOnce(response({ error: { code: 'P4_NOT_FOUND' } }, 404));
  await restored.click('purchase-check');
  expect(restored.elements['purchase-new'].disabled).toBe(true);
  restored.fetch.mockResolvedValueOnce(response({ contract: 'p4-purchase/1.0', outcome: 'replay', purchase: savedReceipt() }));
  await restored.click('purchase-retry');
  expect(restored.fetch.mock.calls[2][1].body).toBe(sent);
  expect(restored.elements['purchase-receipt'].textContent).toContain(savedReceipt().id);
});

it('does not generate another key on conflict or accept a mismatched lookup receipt', async () => {
  const s = setup(); await flush(); s.fill(); s.submit();
  s.fetch.mockResolvedValueOnce(response({ error: { code: 'P4_IDEMPOTENCY_CONFLICT', message: 'secret' } }, 409));
  await s.click('purchase-save');
  expect(s.elements['purchase-status'].textContent).toMatch(/conflito/i);
  const other = savedReceipt(); other.purchase.quantity = 4; other.purchase.total = '0.40';
  s.fetch.mockResolvedValueOnce(response({ contract: 'p4-purchase/1.0', purchase: other }));
  await s.click('purchase-check');
  expect(s.elements['purchase-new'].disabled).toBe(true);
  expect(s.elements['purchase-receipt'].textContent).not.toContain(other.id);
  expect(s.storage.get(storageKey)).toContain(key);
});

it('blocks double click, editing and new submission during an unresolved POST', async () => {
  const s = setup(); await flush(); s.fill(); s.submit();
  let finish!: (value: unknown) => void;
  s.fetch.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = s.click('purchase-save'); await s.click('purchase-save'); await s.click('purchase-new');
  expect(s.fetch).toHaveBeenCalledTimes(2);
  finish(response({ contract: 'p4-purchase/1.0', outcome: 'created', purchase: savedReceipt() }, 201));
  await pending;
});

it('blocks writes if session storage cannot preserve the submission', async () => {
  const s = setup(); await flush(); s.fill(); s.submit();
  s.sessionStorage.setItem.mockImplementation(() => { throw new Error('quota'); });
  await s.click('purchase-save'); expect(s.fetch).toHaveBeenCalledOnce();
});

it('keeps invalid success responses uncertain and sanitizes server errors', async () => {
  const s = setup(); await flush(); s.fill(); s.submit();
  s.fetch.mockResolvedValueOnce(response({ contract: 'wrong', message: '<script>secret</script>' }, 201));
  await s.click('purchase-save');
  expect(s.elements['purchase-new'].disabled).toBe(true);
  expect(s.elements['purchase-status'].textContent).not.toMatch(/script|secret/);
});

it('loads paginated history, avoids duplicate rows and preserves content on failure', async () => {
  const s = setup(); await flush(); const receipt = savedReceipt();
  const cursor = { recorded_at: receipt.recorded_at, id: receipt.id };
  s.fetch.mockResolvedValueOnce(response({ contract: 'p4-purchase/1.0', items: [receipt], next_cursor: cursor }));
  await s.click('purchase-history-load');
  expect(s.elements['purchase-history-rows'].children).toHaveLength(1);
  s.fetch.mockRejectedValueOnce(new Error('secret')); await s.click('purchase-history-more');
  expect(s.elements['purchase-history-rows'].children).toHaveLength(1);
  s.fetch.mockResolvedValueOnce(response({ contract: 'p4-purchase/1.0', items: [receipt], next_cursor: null }));
  await s.click('purchase-history-more');
  expect(s.fetch.mock.calls[3][0]).toContain('after_id=' + receipt.id);
  expect(s.elements['purchase-history-rows'].children).toHaveLength(1);
});

it('refuses an unavailable catalog and never uses a hardcoded fallback', async () => {
  const s = setup(new Map(), { error: 'unavailable' }); await flush();
  expect(s.elements['purchase-prepare'].disabled).toBe(true);
  expect(s.elements['purchase-save'].disabled).toBe(true);
});

it('times out a POST without discarding its key or sending a second request', async () => {
  const s = setup(); await flush(); s.fill(); s.submit();
  s.fetch.mockImplementationOnce((_url: string, options: { signal: AbortSignal }) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('aborted secret')));
  }));
  const pending = s.click('purchase-save');
  await vi.advanceTimersByTimeAsync(20_000); await pending;
  expect(s.fetch).toHaveBeenCalledTimes(2);
  expect(s.storage.get(storageKey)).toContain(key);
  expect(s.elements['purchase-retry'].disabled).toBe(false);
  expect(s.elements['purchase-new'].disabled).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
});

it('confirms a lost response by key without another POST and clears only after an explicit new purchase', async () => {
  const s = setup(); await flush(); s.fill(); s.submit();
  s.fetch.mockRejectedValueOnce(new Error('offline')); await s.click('purchase-save');
  s.fetch.mockResolvedValueOnce(response({ contract: 'p4-purchase/1.0', purchase: savedReceipt() }));
  await s.click('purchase-check');
  expect(s.fetch.mock.calls[2][0]).toBe('/demo/p4/purchases/by-key/' + key);
  expect(s.elements['purchase-new'].disabled).toBe(false);
  await s.click('purchase-new');
  expect(s.storage.size).toBe(0); expect(s.elements['purchase-quantity'].disabled).toBe(false);
  expect(s.elements['purchase-save'].disabled).toBe(true);
  expect(s.fetch).toHaveBeenCalledTimes(3);
});

it.each(['not-json', JSON.stringify({ version: 1, request: { idempotency_key: key } })])('never erases or submits a corrupt pending session: %s', async encoded => {
  const storage = new Map([[storageKey, encoded]]); const s = setup(storage); await flush();
  expect(s.storage.get(storageKey)).toBe(encoded);
  expect(s.elements['purchase-prepare'].disabled).toBe(true);
  await s.click('purchase-save'); expect(s.fetch).toHaveBeenCalledOnce();
});

it('renders catalog strings as text, without injecting HTML', async () => {
  const malicious = structuredClone(catalog); Object.assign(malicious.catalog.suppliers[0], { name: '<img src=x onerror=alert(1)>' });
  const s = setup(new Map(), malicious); await flush();
  expect(s.elements['purchase-supplier'].textContent).toContain('<img src=x');
  // ElementStub throws if any innerHTML assignment is attempted.
});

it('uses Sao Paulo calendar boundaries and allows retroactive dates', async () => {
  vi.setSystemTime(new Date('2026-11-19T01:00:00Z'));
  const s = setup(); await flush(); s.fill({ ...valid, date: '2026-11-19' }); s.submit();
  expect(s.elements['purchase-date'].attributes.get('aria-invalid')).toBe('true');
  s.edit('date', '2026-11-18'); s.submit(); expect(s.elements['purchase-summary'].hidden).toBe(false);
});

it('serializes history requests and refuses a repeated pagination cursor', async () => {
  const s = setup(); await flush(); const r = savedReceipt(); const cursor = { recorded_at: r.recorded_at, id: r.id };
  let resolve!: (value: unknown) => void;
  s.fetch.mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  const pending = s.click('purchase-history-load'); await s.click('purchase-history-load');
  expect(s.fetch).toHaveBeenCalledTimes(2);
  resolve(response({ contract: 'p4-purchase/1.0', items: [r], next_cursor: cursor })); await pending;
  s.fetch.mockResolvedValueOnce(response({ contract: 'p4-purchase/1.0', items: [r], next_cursor: cursor }));
  await s.click('purchase-history-more');
  expect(s.elements['purchase-history-status'].textContent).toMatch(/preservados/);
  expect(s.elements['purchase-history-rows'].children).toHaveLength(1);
});

it('initializes only the server synthetic catalog without scoring or POST', async () => {
  const { elements, fetch } = setup();
  await flush();
  expect(fetch).toHaveBeenCalledOnce();
  expect(elements['purchase-summary'].hidden).toBe(true);
  expect(elements['purchase-prepare'].disabled).toBe(false);
  for (const name of ['supplier', 'product', 'department']) {
    const options = elements[`purchase-${name}`].children;
    expect(options.filter((option) => option.value).length).toBeGreaterThanOrEqual(3);
    expect(new Set(options.map((option) => option.value)).size).toBe(options.length);
  }
});

it('requires all fields and focuses the first invalid field', async () => {
  const { elements, submit } = setup();
  await flush();
  submit();
  for (const field of fields) {
    expect(elements[`purchase-${field}`].attributes.get('aria-invalid')).toBe('true');
    expect(elements[`purchase-${field}-error`].textContent.length).toBeGreaterThan(0);
  }
  expect(elements['purchase-supplier'].focused).toBe(true);
  expect(elements['purchase-summary'].hidden).toBe(true);
});

it('calculates currency in cents and prepares a complete summary without a score', async () => {
  const { elements, fill, submit } = setup();
  await flush();
  fill();
  expect(elements['purchase-total'].textContent).toMatch(/0,30/);
  submit();
  expect(elements['purchase-summary'].hidden).toBe(false);
  const summary = elements['purchase-summary-values'].textContent;
  for (const field of ['supplier', 'product', 'department']) {
    const option = elements[`purchase-${field}`].children.find((item) => item.value === valid[field as keyof typeof valid]);
    expect(option).toBeDefined();
    expect(summary).toContain(option!.textContent);
  }
  expect(summary).toMatch(/0,10/);
  expect(summary).toMatch(/0,30/);
  expect(summary).toMatch(/03\/11\/2026/);
  expect(summary).toContain('30');
  expect(summary).not.toMatch(/score|probabilidade|%|baixo risco|alto risco/i);
});

it.each(['0.10', '0,10', '10', '10.5', '10,50'])('accepts supported price notation: %s', async (price) => {
  const { elements, fill, submit } = setup();
  await flush();
  fill({ ...valid, 'unit-price': price });
  submit();
  expect(elements['purchase-summary'].hidden).toBe(false);
});

it.each([
  ...['', 'unknown', '<img src=x onerror=alert(1)>'].flatMap((value) =>
    ['supplier', 'product', 'department'].map((field) => [field, value])),
  ...['0', '-1', '1.5', '1,5', '1e3', 'Infinity', 'NaN', '1000001', '9007199254740993', ''].map((value) => ['quantity', value]),
  ...['0', '-1', '0.001', '1,234', '1.000,00', '1e2', 'NaN', 'Infinity', '1000000.01', ''].map((value) => ['unit-price', value]),
  ...['-1', '1.5', '1e2', '3651', 'NaN', ''].map((value) => ['payment-days', value]),
  ...['', '2025-02-29', '2026-02-30', '2026-13-01', '2026-04-31', '0000-01-01', '03/11/2026', 'not-a-date', '2030-01-01'].map((value) => ['date', value]),
])('rejects invalid %s=%s without showing a summary', async (field, value) => {
  const { elements, fill, submit } = setup();
  await flush();
  fill({ ...valid, [field]: value });
  submit();
  expect(elements['purchase-summary'].hidden).toBe(true);
  expect(elements[`purchase-${field}`].attributes.get('aria-invalid')).toBe('true');
  expect(elements[`purchase-${field}-error`].textContent.length).toBeGreaterThan(0);
  expect(elements['purchase-status'].textContent).not.toContain('<img');
});

it.each(['2024-02-29', '2000-02-29', '1999-12-31'])('accepts valid retrospective date %s without inventing an approval date', async (date) => {
  const { elements, fill, submit } = setup();
  await flush();
  fill({ ...valid, date });
  submit();
  expect(elements['purchase-summary'].hidden).toBe(false);
});

it('accepts boundary values including payment at sight and computes a finite exact total', async () => {
  const { elements, fill, submit } = setup();
  await flush();
  fill({ ...valid, quantity: '1000000', 'unit-price': '1000000.00', 'payment-days': '0' });
  submit();
  expect(elements['purchase-summary'].hidden).toBe(false);
  expect(elements['purchase-total'].textContent).toMatch(/1\.000\.000\.000\.000,00/);
  expect(elements['purchase-summary-values'].textContent).toMatch(/vista/i);
});

it('invalidates the previous summary and clears a stale total after an invalid edit', async () => {
  const { elements, fill, edit, submit } = setup();
  await flush();
  fill();
  submit();
  expect(elements['purchase-summary'].hidden).toBe(false);
  edit('quantity', 'invalid');
  expect(elements['purchase-summary'].hidden).toBe(true);
  expect(elements['purchase-total'].textContent).not.toContain('0,30');
  submit();
  expect(elements['purchase-summary'].hidden).toBe(true);
});

it('recovers from validation errors and updates product units without submitting to the API', async () => {
  const { elements, fill, edit, submit, fetch } = setup();
  await flush();
  submit();
  fill();
  edit('product', 'prod-tijolo', 'change');
  submit();
  expect(elements['purchase-summary'].hidden).toBe(false);
  expect(elements['purchase-unit'].textContent).toMatch(/unidade/i);
  for (const field of fields) {
    expect(elements[`purchase-${field}`].attributes.get('aria-invalid')).not.toBe('true');
    expect(elements[`purchase-${field}-error`].textContent).toBe('');
  }
  expect(fetch).toHaveBeenCalledOnce();
});
