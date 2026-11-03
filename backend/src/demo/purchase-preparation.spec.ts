import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

type FormEvent = { target: ElementStub; preventDefault: () => void };
type Listener = (event: FormEvent) => void;

// Only the DOM used by the form; network, storage and HTML insertion are forbidden.
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
  emit(name: string, event: FormEvent) { this.listeners.get(name)?.forEach((listener) => listener(event)); }
}

const fields = ['supplier', 'product', 'department', 'quantity', 'unit-price', 'payment-days', 'date'];
const valid = {
  supplier: 'sup-obra', product: 'prod-cimento', department: 'dep-obras',
  quantity: '3', 'unit-price': '0,10', 'payment-days': '30', date: '2026-11-03',
};

function setup() {
  const ids = [
    'purchase-form', 'purchase-unit', 'purchase-total', 'purchase-prepare',
    'purchase-status', 'purchase-summary', 'purchase-summary-values',
    ...fields.flatMap((name) => [`purchase-${name}`, `purchase-${name}-error`]),
  ];
  const elements = Object.fromEntries(ids.map((id) => [id, new ElementStub(id)]));
  elements['purchase-summary'].hidden = true;
  elements['purchase-prepare'].disabled = true;
  for (const name of ['supplier', 'product', 'department']) {
    const placeholder = new ElementStub();
    placeholder.textContent = 'Selecione';
    elements[`purchase-${name}`].appendChild(placeholder);
  }
  const fetch = vi.fn(() => { throw new Error('Network forbidden'); });
  const context = {
    document: {
      getElementById: (id: string) => {
        if (!Object.hasOwn(elements, id)) throw new Error(`Unexpected DOM access: ${id}`);
        return elements[id];
      },
      createElement: () => new ElementStub(),
    },
    fetch, Date, Intl,
    get localStorage(): never { throw new Error('Persistence forbidden'); },
    get sessionStorage(): never { throw new Error('Persistence forbidden'); },
    get XMLHttpRequest(): never { throw new Error('Network forbidden'); },
  };
  runInNewContext(readFileSync(new URL('./public/purchase.js', import.meta.url), 'utf8'), context);
  function edit(field: string, value: string, eventName = 'input') {
    const element = elements[`purchase-${field}`];
    element.value = value;
    const event = { target: element, preventDefault: vi.fn() };
    element.emit(eventName, event);
    elements['purchase-form'].emit(eventName, event);
  }
  function fill(values: Record<string, string> = valid) {
    Object.entries(values).forEach(([name, value]) => edit(name, value, 'change'));
  }
  function submit() {
    const preventDefault = vi.fn();
    elements['purchase-form'].emit('submit', { target: elements['purchase-form'], preventDefault });
    expect(preventDefault).toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  }
  return { elements, fetch, edit, fill, submit };
}

it('initializes only the synthetic catalog without fetching, scoring or persistence', () => {
  const { elements, fetch } = setup();
  expect(fetch).not.toHaveBeenCalled();
  expect(elements['purchase-summary'].hidden).toBe(true);
  expect(elements['purchase-prepare'].disabled).toBe(false);
  for (const name of ['supplier', 'product', 'department']) {
    const options = elements[`purchase-${name}`].children;
    expect(options.filter((option) => option.value).length).toBeGreaterThanOrEqual(3);
    expect(new Set(options.map((option) => option.value)).size).toBe(options.length);
  }
});

it('requires all fields and focuses the first invalid field', () => {
  const { elements, submit } = setup();
  submit();
  for (const field of fields) {
    expect(elements[`purchase-${field}`].attributes.get('aria-invalid')).toBe('true');
    expect(elements[`purchase-${field}-error`].textContent.length).toBeGreaterThan(0);
  }
  expect(elements['purchase-supplier'].focused).toBe(true);
  expect(elements['purchase-summary'].hidden).toBe(true);
});

it('calculates currency in cents and prepares a complete summary without a score', () => {
  const { elements, fill, submit } = setup();
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

it.each(['0.10', '0,10', '10', '10.5', '10,50'])('accepts supported price notation: %s', (price) => {
  const { elements, fill, submit } = setup();
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
  ...['', '2025-02-29', '2026-02-30', '2026-13-01', '2026-04-31', '0000-01-01', '03/11/2026', 'not-a-date'].map((value) => ['date', value]),
])('rejects invalid %s=%s without showing a summary', (field, value) => {
  const { elements, fill, submit } = setup();
  fill({ ...valid, [field]: value });
  submit();
  expect(elements['purchase-summary'].hidden).toBe(true);
  expect(elements[`purchase-${field}`].attributes.get('aria-invalid')).toBe('true');
  expect(elements[`purchase-${field}-error`].textContent.length).toBeGreaterThan(0);
  expect(elements['purchase-status'].textContent).not.toContain('<img');
});

it.each(['2024-02-29', '2000-02-29', '2030-01-01', '1999-12-31'])('accepts calendar-valid date %s without inventing an approval date', (date) => {
  const { elements, fill, submit } = setup();
  fill({ ...valid, date });
  submit();
  expect(elements['purchase-summary'].hidden).toBe(false);
});

it('accepts boundary values including payment at sight and computes a finite exact total', () => {
  const { elements, fill, submit } = setup();
  fill({ ...valid, quantity: '1000000', 'unit-price': '1000000.00', 'payment-days': '0' });
  submit();
  expect(elements['purchase-summary'].hidden).toBe(false);
  expect(elements['purchase-total'].textContent).toMatch(/1\.000\.000\.000\.000,00/);
  expect(elements['purchase-summary-values'].textContent).toMatch(/vista/i);
});

it('invalidates the previous summary and clears a stale total after an invalid edit', () => {
  const { elements, fill, edit, submit } = setup();
  fill();
  submit();
  expect(elements['purchase-summary'].hidden).toBe(false);
  edit('quantity', 'invalid');
  expect(elements['purchase-summary'].hidden).toBe(true);
  expect(elements['purchase-total'].textContent).not.toContain('0,30');
  submit();
  expect(elements['purchase-summary'].hidden).toBe(true);
});

it('recovers from validation errors and updates product units without making an API call', () => {
  const { elements, fill, edit, submit, fetch } = setup();
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
  expect(fetch).not.toHaveBeenCalled();
});
