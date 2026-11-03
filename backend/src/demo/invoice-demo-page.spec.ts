import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

type Listener = () => void | Promise<void>;

// Minimal DOM surface used by the page. HTML insertion is deliberately forbidden.
class ElementStub {
  textContent = '';
  hidden = false;
  disabled = false;
  children: ElementStub[] = [];
  attributes = new Map<string, string>();
  listeners = new Map<string, Listener>();

  set innerHTML(_value: string) { throw new Error('Unsafe HTML insertion'); }
  setAttribute(name: string, value: string) { this.attributes.set(name, value); }
  removeAttribute(name: string) { this.attributes.delete(name); }
  addEventListener(name: string, listener: Listener) { this.listeners.set(name, listener); }
  replaceChildren(...children: ElementStub[]) { this.children = children; }
  appendChild(child: ElementStub) { this.children.push(child); return child; }
  append(...children: ElementStub[]) { this.children.push(...children); }
  click() { return Promise.resolve(this.listeners.get('click')?.()); }
}

function fixture() {
  return {
    contract: 'invoice-demo/1.0', origin: 'synthetic', source_reconciled: false,
    model_sha256: 'c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b',
    score_kind: 'negative_score_samples', score_direction: 'higher_is_more_anomalous',
    rows: [
      { id: 'demo-002', score: 0.8, rank: 1 },
      { id: 'demo-001', score: 0.2, rank: 2 },
      { id: 'demo-003', score: 0.2, rank: 3 },
    ],
  };
}

function setup() {
  const ids = ['run-button', 'run-status', 'results-panel', 'empty-state',
    'ranking-container', 'ranking-rows', 'result-details', 'model-hash', 'execution-time'];
  const elements = Object.fromEntries(ids.map((id) => [id, new ElementStub()]));
  elements['run-button'].disabled = true;
  elements['ranking-container'].hidden = true;
  elements['result-details'].hidden = true;
  const fetch = vi.fn();
  const context = {
    document: {
      getElementById: (id: string) => elements[id],
      createElement: () => new ElementStub(),
    },
    fetch, AbortController, DOMException, setTimeout, clearTimeout, Date, Intl,
    get localStorage(): never { throw new Error('Persistence forbidden'); },
    get sessionStorage(): never { throw new Error('Persistence forbidden'); },
  };
  runInNewContext(readFileSync(new URL('./public/app.js', import.meta.url), 'utf8'), context);
  return { elements, fetch, click: () => elements['run-button'].click() };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-03T13:05:06.000Z'));
});
afterEach(() => vi.useRealTimers());

it('starts idle without inference, persistence or a fetch on page load', () => {
  const { elements, fetch } = setup();
  expect(fetch).not.toHaveBeenCalled();
  expect(elements['run-button'].disabled).toBe(false);
  expect(elements['ranking-container'].hidden).toBe(true);
  expect(elements['result-details'].hidden).toBe(true);
});

it('posts no input, blocks repeated clicks and renders the returned ranking as text', async () => {
  const { elements, fetch, click } = setup();
  let complete!: (value: unknown) => void;
  fetch.mockReturnValue(new Promise((resolve) => { complete = resolve; }));
  const first = click();
  expect(elements['run-button'].disabled).toBe(true);
  expect(elements['results-panel'].attributes.get('aria-busy')).toBe('true');
  expect(elements['run-status'].textContent.length).toBeGreaterThan(0);
  await click();
  expect(fetch).toHaveBeenCalledOnce();
  expect(fetch.mock.calls[0][0]).toBe('/demo/invoice-runs');
  expect(fetch.mock.calls[0][1]).toMatchObject({ method: 'POST' });
  expect(fetch.mock.calls[0][1]).not.toHaveProperty('body');
  complete({ ok: true, status: 200, json: async () => fixture() });
  await first;
  expect(elements['run-button'].disabled).toBe(false);
  expect(elements['results-panel'].attributes.get('aria-busy')).toBe('false');
  expect(elements['ranking-container'].hidden).toBe(false);
  expect(elements['result-details'].hidden).toBe(false);
  const rendered = elements['ranking-rows'].children.map((row) =>
    row.children.map((cell) => cell.textContent));
  expect(rendered.map((row) => row[0])).toEqual(['1', '2', '3']);
  expect(rendered.map((row) => row[1])).toEqual(['demo-002', 'demo-001', 'demo-003']);
  expect(rendered.every((row) => row[2].length > 0)).toBe(true);
  expect(elements['model-hash'].textContent).toBe(fixture().model_sha256);
  expect(elements['execution-time'].textContent).not.toBe('');
  expect(elements['execution-time'].attributes.get('datetime')).toBe('2026-11-03T13:05:06.000Z');
  expect(vi.getTimerCount()).toBe(0);
});

it.each([400, 409, 502, 503, 504, 500])('handles HTTP %s without exposing the server body', async (status) => {
  const { elements, fetch, click } = setup();
  const json = vi.fn(async () => ({ message: 'private driver credentials' }));
  fetch.mockResolvedValue({ ok: false, status, json });
  await click();
  expect(json).not.toHaveBeenCalled();
  expect(elements['run-status'].textContent).not.toMatch(/private|credentials|driver/);
  expect(elements['run-status'].textContent.length).toBeGreaterThan(10);
  expect(elements['ranking-container'].hidden).toBe(true);
  expect(elements['run-button'].disabled).toBe(false);
  expect(vi.getTimerCount()).toBe(0);
});

it('handles network errors without leaking their original message', async () => {
  const { elements, fetch, click } = setup();
  fetch.mockRejectedValue(new Error('private network credentials'));
  await click();
  expect(elements['run-status'].textContent).not.toMatch(/private|credentials/);
  expect(elements['run-button'].disabled).toBe(false);
  expect(elements['ranking-container'].hidden).toBe(true);
});

it('handles malformed JSON and permits another explicit attempt', async () => {
  const { elements, fetch, click } = setup();
  fetch.mockResolvedValue({ ok: true, status: 200, json: () => { throw new Error('private JSON'); } });
  await click();
  expect(elements['run-status'].textContent).not.toContain('private');
  expect(elements['run-button'].disabled).toBe(false);
  expect(elements['ranking-container'].hidden).toBe(true);
  fetch.mockResolvedValue({ ok: true, status: 200, json: async () => fixture() });
  await click();
  expect(elements['ranking-container'].hidden).toBe(false);
});

it.each([
  () => ({ ...fixture(), origin: 'test' }),
  () => ({ ...fixture(), source_reconciled: true }),
  () => ({ ...fixture(), score_kind: 'fraud_probability' }),
  () => ({ ...fixture(), model_sha256: '<img src=x onerror=alert(1)>' }),
  () => ({ ...fixture(), rows: [] }),
  () => ({ ...fixture(), rows: [{ id: 'demo-002', score: 0.8, rank: 2 }, ...fixture().rows.slice(1)] }),
  () => ({ ...fixture(), rows: [{ id: 'demo-001', score: 0.8, rank: 1 }, ...fixture().rows.slice(1)] }),
  () => ({ ...fixture(), rows: [{ id: 'demo-002', score: 0.1, rank: 1 }, ...fixture().rows.slice(1)] }),
  () => ({ ...fixture(), rows: [{ id: 'demo-002', score: Infinity, rank: 1 }, ...fixture().rows.slice(1)] }),
  () => ({ ...fixture(), rows: [{ id: '<script>private</script>', score: 0.8, rank: 1 }, ...fixture().rows.slice(1)] }),
])('refuses incompatible or unsafe response data without inserting HTML', async (invalid) => {
  const { elements, fetch, click } = setup();
  fetch.mockResolvedValue({ ok: true, status: 200, json: async () => invalid() });
  await click();
  expect(elements['ranking-container'].hidden).toBe(true);
  expect(elements['result-details'].hidden).toBe(true);
  expect(elements['ranking-rows'].children).toHaveLength(0);
  expect(elements['run-status'].textContent).not.toContain('private');
  expect(elements['run-button'].disabled).toBe(false);
});

it('clears previous results when a new explicit run fails, without creating history', async () => {
  const { elements, fetch, click } = setup();
  fetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => fixture() });
  await click();
  expect(elements['ranking-rows'].children).toHaveLength(3);
  fetch.mockRejectedValueOnce(new Error('offline'));
  await click();
  expect(elements['ranking-rows'].children).toHaveLength(0);
  expect(elements['ranking-container'].hidden).toBe(true);
  expect(elements['result-details'].hidden).toBe(true);
});

it('aborts a stalled HTTP request after 35 seconds and releases the button', async () => {
  const { elements, fetch, click } = setup();
  fetch.mockImplementation((_url: string, options: { signal: AbortSignal }) =>
    new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new DOMException('private timeout', 'AbortError')));
    }));
  const pending = click();
  await vi.advanceTimersByTimeAsync(35_000);
  await pending;
  expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
  expect(elements['run-button'].disabled).toBe(false);
  expect(elements['run-status'].textContent).not.toContain('private');
  expect(elements['ranking-container'].hidden).toBe(true);
  expect(vi.getTimerCount()).toBe(0);
});
