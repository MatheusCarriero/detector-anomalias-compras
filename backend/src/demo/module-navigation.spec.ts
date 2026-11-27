import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

function setup(pathname = '/', hash = '') {
  const ids = ['overview', 'invoice', 'purchases', 'history', 'procurement'];
  const elements = Object.fromEntries([...ids.map(n => `navigation-${n}`), 'overview', 'invoice-screen', 'compras', 'historico', 'screen-title', 'sidebar', 'menu-toggle'].map(id => {
    const attributes = new Map<string, string>();
    const listeners = new Map<string, (e?: unknown) => void>();
    return [id, { hidden: false, textContent: '', attributes, listeners, focus: vi.fn(),
      setAttribute: (k: string, v: string) => attributes.set(k, v),
      removeAttribute: (k: string) => attributes.delete(k),
      getAttribute: (k: string) => attributes.get(k),
      addEventListener: (k: string, fn: () => void) => listeners.set(k, fn) }];
  }));
  const location = { pathname, hash };
  const listeners = new Map<string, (e?: unknown) => void>();
  const events: unknown[] = [];
  const fetch = vi.fn(() => { throw new Error('Navigation cannot initiate requests'); });
  runInNewContext(readFileSync(new URL('./public/navigation.js', import.meta.url), 'utf8'), {
    document: { getElementById: (id: string) => elements[id],
      addEventListener: (k: string, fn: () => void) => listeners.set(k, fn),
      dispatchEvent: (e: unknown) => events.push(e) },
    window: { location, addEventListener: (k: string, fn: () => void) => listeners.set(k, fn),
      matchMedia: () => ({ matches: true, addEventListener: vi.fn() }) },
    CustomEvent: class { constructor(public type: string, public options: unknown) {} }, fetch,
    get sessionStorage(): never { throw new Error('Navigation cannot change purchase submissions'); },
  });
  return { elements, location, listeners, fetch, events };
}

it.each([['', 'overview'], ['#visao-geral', 'overview'], ['#invoice', 'invoice'], ['#interpretacao', 'invoice'], ['#compras', 'purchases'], ['#historico', 'history'], ['#unknown', 'overview']])('opens the requested screen %s', (hash, active) => {
  const s = setup('/', hash);
  expect(s.elements[`navigation-${active}`].attributes.get('aria-current')).toBe('page');
  const screen = { overview: 'overview', invoice: 'invoice-screen', purchases: 'compras', history: 'historico' }[active]!;
  for (const id of ['overview', 'invoice-screen', 'compras', 'historico']) expect(s.elements[id].hidden).toBe(id !== screen);
  expect(s.fetch).not.toHaveBeenCalled();
});

it('switches screens without replacing their state, and supports back/forward', () => {
  const s = setup(); const formScreen = s.elements.compras;
  formScreen.textContent = 'pending submission';
  for (const hash of ['#compras', '#historico', '#invoice', '#compras']) {
    s.location.hash = hash; s.listeners.get('hashchange')!();
  }
  expect(s.elements.compras).toBe(formScreen);
  expect(formScreen.textContent).toBe('pending submission');
  expect(s.elements.compras.hidden).toBe(false);
  expect(formScreen.focus).toHaveBeenCalled();
  expect(s.fetch).not.toHaveBeenCalled();
});

it.each(['/demo/procurement-v2', '/demo/procurement-v2/'])('marks the independent historical page %s', path => {
  const s = setup(path);
  expect(s.elements['navigation-procurement'].attributes.get('aria-current')).toBe('page');
  expect(s.elements['screen-title'].textContent).toBe('Análise histórica');
});

it('opens the mobile menu and returns focus on Escape', () => {
  const s = setup(); const toggle = s.elements['menu-toggle'];
  expect(s.elements.sidebar.hidden).toBe(true);
  toggle.listeners.get('click')!();
  expect(toggle.attributes.get('aria-expanded')).toBe('true');
  expect(s.elements.sidebar.hidden).toBe(false);
  expect(s.elements['navigation-overview'].focus).toHaveBeenCalled();
  s.listeners.get('keydown')!({ key: 'Escape' });
  expect(s.elements.sidebar.hidden).toBe(true);
  expect(toggle.focus).toHaveBeenCalled();
});

it('announces the overview after deferred scripts are ready, without running analysis', () => {
  const s = setup(); s.listeners.get('DOMContentLoaded')!();
  expect(s.events).toContainEqual({ type: 'dashboard:view', options: { detail: { view: 'overview' } } });
  expect(s.fetch).not.toHaveBeenCalled();
});

it('keeps the current screen when using the skip link', () => {
  const s = setup('/', '#invoice');
  s.location.hash = '#conteudo'; s.listeners.get('hashchange')!();
  expect(s.elements['invoice-screen'].hidden).toBe(false);
  expect(s.elements.overview.hidden).toBe(true);
});
it('closes the mobile menu when choosing the already active screen', () => {
  const s = setup('/', '#compras');
  s.elements['menu-toggle'].listeners.get('click')!();
  s.elements['navigation-purchases'].listeners.get('click')!();
  expect(s.elements.sidebar.hidden).toBe(true);
  expect(s.elements.compras.focus).toHaveBeenCalled();
});
