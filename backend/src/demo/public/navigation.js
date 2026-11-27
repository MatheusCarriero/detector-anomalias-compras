/* global document, window, CustomEvent */
(() => {
  const views = {
    overview: ['overview', 'Visão geral'], purchases: ['compras', 'Nova compra'],
    history: ['historico', 'Histórico de compras'], invoice: ['invoice-screen', 'Análise de faturas'],
    procurement: [null, 'Análise histórica'],
  };
  const sidebar = document.getElementById('sidebar');
  const toggle = document.getElementById('menu-toggle');
  let current = 'overview';
  const mobile = window.matchMedia('(max-width: 900px)');
  function menu(open) {
    sidebar.hidden = mobile.matches && !open;
    toggle.setAttribute('aria-expanded', String(mobile.matches && open));
  }
  function update(focus = false) {
    const hash = window.location.hash;
    const active = /^\/demo\/procurement-v2\/?$/.test(window.location.pathname) ? 'procurement'
      : hash === '#compras' ? 'purchases' : hash === '#historico' ? 'history'
      : ['#invoice', '#interpretacao'].includes(hash) ? 'invoice' : hash === '#conteudo' ? current : 'overview';
    current = active;
    for (const [key, [id]] of Object.entries(views)) {
      const link = document.getElementById(`navigation-${key}`);
      if (key === active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
      const section = id && document.getElementById(id);
      if (section) section.hidden = key !== active;
    }
    document.getElementById('screen-title').textContent = views[active][1];
    menu(false);
    if (focus) document.getElementById(views[active][0] ?? 'conteudo')?.focus();
    document.dispatchEvent(new CustomEvent('dashboard:view', { detail: { view: active } }));
  }
  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    menu(open);
    if (open) document.getElementById(`navigation-${current}`).focus();
  });
  for (const key of Object.keys(views)) {
    document.getElementById(`navigation-${key}`).addEventListener('click', event => {
      if (key === current) { event?.preventDefault(); update(true); }
    });
  }
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
      menu(false); toggle.focus();
    }
  });
  mobile.addEventListener('change', () => menu(false));
  // Hide only: the form, pending payload and receipt stay mounted across views.
  window.addEventListener('hashchange', () => update(true));
  document.addEventListener('DOMContentLoaded', () => update());
  update();
})();
