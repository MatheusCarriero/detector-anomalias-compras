import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { catalog, prepared, runResult, preparationRequest } from '../../test/fixtures/procurement-demo.js';

class ElementStub {
  textContent = '';
  hidden = false;
  disabled = false;
  className = '';
  children: ElementStub[] = [];
  attributes = new Map<string, string>();
  listeners = new Map<string, () => unknown>();
  set innerHTML(_value: string) { throw new Error('HTML insertion forbidden'); }
  setAttribute(name: string, value: string) { this.attributes.set(name, value); }
  addEventListener(name: string, fn: () => unknown) { this.listeners.set(name, fn); }
  replaceChildren(...children: ElementStub[]) { this.children = children; }
  append(...children: ElementStub[]) { this.children.push(...children); }
  click() { return Promise.resolve(this.listeners.get('click')?.()); }
}
const response = (data: unknown, status = 200) => ({ ok: status === 200, status, json: async () => data });
const text = (e: ElementStub): string => e.textContent + e.children.map(text).join(' ');
async function flush() { for (let i = 0; i < 12; i++) await Promise.resolve(); }
function setup(initial: unknown = catalog(), status = 200) {
  const html = readFileSync(new URL('./public/procurement/index.html', import.meta.url), 'utf8');
  // Real markup supplies the IDs: a selector typo cannot pass against a fabricated DOM.
  const elements = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1], new ElementStub()]));
  const fetch = vi.fn().mockResolvedValueOnce(response(initial, status));
  runInNewContext(readFileSync(new URL('./public/procurement/app.js', import.meta.url), 'utf8'), {
    document: { getElementById: (id: string) => elements[id], createElement: () => new ElementStub() },
    fetch, AbortController, setTimeout, clearTimeout,
    get localStorage(): never { throw new Error('Persistence forbidden'); },
    get sessionStorage(): never { throw new Error('Persistence forbidden'); },
  });
  return { elements, fetch, select: (index: number) => elements['operation-list'].children[index].click(),
    prepare: () => elements['prepare-button'].click(), run: () => elements['analyze-button'].click() };
}
beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it('loads only the catalog; selection and ineligible clicks never trigger inference', async () => {
  const s = setup(); await flush();
  expect(s.fetch).toHaveBeenCalledOnce();
  expect(s.fetch.mock.calls[0][0]).toBe('/demo/procurement-v2/operations');
  expect(s.elements['operation-list'].children).toHaveLength(7);
  await s.select(2); await s.run();
  expect(s.fetch).toHaveBeenCalledOnce();
  expect(s.elements['analyze-button'].disabled).toBe(true);
  expect(s.elements['operation-identity'].textContent).toContain('PO-2025-40702');
});

it('prepares only the catalog identity and renders five features, including zero, before enabling IA', async () => {
  const s = setup(); await flush(); await s.select(0);
  s.fetch.mockResolvedValueOnce(response(prepared())); await s.prepare();
  const [url, options] = s.fetch.mock.calls[1];
  expect(url).toBe('/demo/procurement-v2/prepare');
  expect(options.method).toBe('POST');
  expect(JSON.parse(options.body)).toEqual(preparationRequest());
  expect(s.elements['feature-rows'].children).toHaveLength(5);
  expect(s.elements['feature-rows'].children[2].children[1].textContent).toBe('0');
  expect(s.elements['analyze-button'].disabled).toBe(false);
  expect(s.elements['preparation-badge'].attributes.get('data-state')).toBe('eligible');
  expect(s.elements['action-status'].attributes.get('data-state')).toBe('success');
  expect(s.elements['history-window'].textContent).toContain('2024-10-25');
  expect(s.elements['reference-rows'].children).toHaveLength(4);
  expect(s.elements['scored-result'].hidden).toBe(true);
});

it('keeps insufficient history distinct from errors and never runs an unavailable operation', async () => {
  const s = setup(); await flush(); await s.select(6);
  s.fetch.mockResolvedValueOnce(response(prepared(true))); await s.prepare(); await s.run();
  expect(s.fetch).toHaveBeenCalledTimes(2);
  expect(s.elements['unavailable-note'].hidden).toBe(false);
  expect(s.elements['preparation-badge'].attributes.get('data-state')).toBe('unavailable');
  expect(text(s.elements['unavailable-reasons'])).toContain('20');
  expect(text(s.elements['history-support'])).toContain('17');
  expect(s.elements['analyze-button'].disabled).toBe(true);
  expect(s.elements['scored-result'].hidden).toBe(true);
});

it('renders the API decimal score, historical references and full provenance without converting to risk', async () => {
  const s = setup(); await flush(); await s.select(0);
  s.fetch.mockResolvedValueOnce(response(prepared())); await s.prepare();
  const result = runResult(); result.anomaly_score = 0.1234567890123456;
  s.fetch.mockResolvedValueOnce(response(result)); await s.run();
  expect(s.fetch.mock.calls[2][0]).toBe('/demo/procurement-v2/runs');
  expect(JSON.parse(s.fetch.mock.calls[2][1].body)).toEqual(preparationRequest());
  expect(s.elements['scored-result'].hidden).toBe(false);
  expect(s.elements['anomaly-score'].textContent).toBe('0.1234567890123456');
  expect(text(s.elements['provenance-values'])).toContain(result.model!.model_sha256);
  expect(text(s.elements['provenance-values'])).toContain(result.preparation.source.source_version);
  expect(s.elements['result-operation'].textContent).toContain('PO-2025-27239');
  await s.select(1);
  expect(s.elements['scored-result'].hidden).toBe(true);
  expect(s.elements['anomaly-score'].textContent).toBe('');
  expect(s.elements['analyze-button'].disabled).toBe(true);
  expect(s.elements['feature-rows'].children).toHaveLength(0);
});

it.each(['prepare', 'run'] as const)('ignores stale %s responses, even after selecting A → B → A', async (action) => {
  const s = setup(); await flush(); await s.select(0);
  if (action === 'run') { s.fetch.mockResolvedValueOnce(response(prepared())); await s.prepare(); }
  let complete!: (value: unknown) => void;
  s.fetch.mockReturnValueOnce(new Promise(resolve => { complete = resolve; }));
  const pending = s[action]();
  const calls = s.fetch.mock.calls.length;
  await s[action](); await s.select(1); await s.select(0); await s.prepare();
  expect(s.fetch).toHaveBeenCalledTimes(calls);
  expect(s.elements['analysis-panel'].attributes.get('aria-busy')).toBe('true');
  complete(response(action === 'run' ? runResult() : prepared())); await pending;
  expect(s.elements['history-content'].hidden).toBe(true);
  expect(s.elements['scored-result'].hidden).toBe(true);
  expect(s.elements['analyze-button'].disabled).toBe(true);
  expect(s.elements['prepare-button'].disabled).toBe(false);
  expect(vi.getTimerCount()).toBe(0);
});

it.each([
  () => ({ ...catalog(), source: { ...catalog().source, source_version: '0'.repeat(64) } }),
  () => ({ ...catalog(), operations: catalog().operations.slice(0, 6) }),
  () => ({ ...catalog(), operations: Array(7).fill(catalog().operations[0]) }),
])('refuses incompatible catalogs without constructing selectable operations', async (invalid) => {
  const s = setup(invalid()); await flush();
  expect(s.elements['operation-list'].children).toHaveLength(0);
  expect(s.elements['prepare-button'].disabled).toBe(true);
  expect(s.elements['analyze-button'].disabled).toBe(true);
  expect(s.elements['catalog-retry'].disabled).toBe(false);
  expect(s.elements['catalog-status'].attributes.get('data-state')).toBe('error');
});

it('retries a failed catalog explicitly and safely renders untrusted text without HTML', async () => {
  const s = setup({ message: 'private secrets' }, 503); await flush();
  expect(s.elements['catalog-status'].textContent).not.toContain('private');
  expect(s.elements['catalog-retry'].disabled).toBe(false);
  const c = catalog(); c.operations[0].context.item = '<img src=x onerror=alert(1)>';
  s.fetch.mockResolvedValueOnce(response(c)); await s.elements['catalog-retry'].click(); await s.select(0);
  expect(s.elements['operation-product'].textContent).toBe(c.operations[0].context.item);
  expect(s.fetch).toHaveBeenCalledTimes(2);
});

it.each([
  'PROCUREMENT_MODEL_UNAVAILABLE', 'PROCUREMENT_MODEL_INTEGRITY', 'PROCUREMENT_MODEL_INCOMPATIBLE',
  'PROCUREMENT_TIMEOUT', 'PROCUREMENT_BUSY', 'PROCUREMENT_INVALID_REQUEST', 'PROCUREMENT_EXECUTION_FAILED',
  'private path C:/secrets password=abc',
])('sanitizes %s without showing stale scores', async (code) => {
  const s = setup(); await flush(); await s.select(0);
  s.fetch.mockResolvedValueOnce(response(prepared())); await s.prepare();
  s.fetch.mockResolvedValueOnce(response({ message: code }, 502)); await s.run();
  expect(s.elements['action-status'].textContent.length).toBeGreaterThan(15);
  expect(s.elements['action-status'].textContent).not.toMatch(/private|secrets|password|C:\//);
  expect(s.elements['scored-result'].hidden).toBe(true);
  expect(s.elements['prepare-button'].disabled).toBe(false);
});

it.each([
  () => ({ ...prepared(), operation: { ...prepared().operation, occurrence: 2 } }),
  () => ({ ...prepared(), feature_names: [...prepared().feature_names].reverse() }),
  () => ({ ...prepared(), values: [1, 1, Infinity, 20, 20] }),
  () => ({ ...prepared(), source: { ...prepared().source, origin: 'real' } }),
  () => ({ ...prepared(), context: { ...prepared().context, supplier_id: 'WRONG' } }),
  () => ({ ...prepared(), window: { ...prepared().window, end_exclusive: false } }),
])('rejects incompatible preparation without enabling inference', async (invalid) => {
  const s = setup(); await flush(); await s.select(0);
  s.fetch.mockResolvedValueOnce(response(invalid())); await s.prepare();
  expect(s.elements['analyze-button'].disabled).toBe(true);
  expect(s.elements['history-content'].hidden).toBe(true);
  expect(s.elements['action-status'].textContent).toContain('incompatível');
});

it('rejects score semantics other than statistical anomaly', async () => {
  const s = setup(); await flush(); await s.select(0);
  s.fetch.mockResolvedValueOnce(response(prepared())); await s.prepare();
  s.fetch.mockResolvedValueOnce(response({ ...runResult(), score_semantics: 'probability' })); await s.run();
  expect(s.elements['scored-result'].hidden).toBe(true);
});

it('handles unavailable returned by runs without keeping an earlier eligibility', async () => {
  const s = setup(); await flush(); await s.select(6);
  const p = prepared(); p.operation = prepared(true).operation; p.cutoff_date = p.operation.order_date;
  p.window = prepared(true).window;
  s.fetch.mockResolvedValueOnce(response(p)); await s.prepare();
  s.fetch.mockResolvedValueOnce(response(runResult(true))); await s.run();
  expect(s.elements['unavailable-note'].hidden).toBe(false);
  expect(s.elements['analyze-button'].disabled).toBe(true);
  expect(s.elements['scored-result'].hidden).toBe(true);
});

it.each(['network', 'json'])('handles %s failures with safe messages and no automatic retry', async (kind) => {
  const s = setup(); await flush(); await s.select(0);
  if (kind === 'network') s.fetch.mockRejectedValueOnce(new Error('secret network'));
  else s.fetch.mockResolvedValueOnce({ ok: true, json: () => { throw new Error('secret JSON'); } });
  await s.prepare();
  expect(s.elements['action-status'].textContent).not.toContain('secret');
  expect(s.elements['analyze-button'].disabled).toBe(true);
  expect(s.fetch).toHaveBeenCalledTimes(2);
});

it('aborts at 35 seconds, clears timers and permits only explicit retry', async () => {
  const s = setup(); await flush(); await s.select(0);
  s.fetch.mockImplementationOnce((_url: string, options: { signal: AbortSignal }) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('private timeout')));
  }));
  const pending = s.prepare(); await vi.advanceTimersByTimeAsync(35_000); await pending;
  expect(s.fetch.mock.calls[1][1].signal.aborted).toBe(true);
  expect(s.elements['action-status'].textContent).toContain('tempo');
  expect(s.elements['prepare-button'].disabled).toBe(false);
  expect(vi.getTimerCount()).toBe(0);
});
