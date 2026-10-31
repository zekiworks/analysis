'use strict';

/* Every page: tables come first and answer clicks.
   - Click (or Enter on) a column header to sort by it: ascending, then descending, then the build's order. Numbers sort
     as numbers (the small second line of a cell, such as an interval, is ignored); status words such as "Too few
     decisions" or "N/A" always go last. A header with data-nosort never sorts (Close choices: never ranked). A header
     with data-sort-default is the build's own order (it carries aria-sort at load): its clicks switch between the other
     direction and the build's order, which it marks with its default direction again.
   - Click a row to open what it is about: its data-href, else the first link in the row (a setup's page, a decision,
     a league). Clicks on links, buttons and form fields keep their own meaning; Ctrl/Cmd-click opens a new tab.
   - A link to an anchor inside a closed <details> opens it.
   Works for tables written later by other scripts (Every decision), through one listener on the document. */

(function tables() {
  const SKIP = '.small, .mark, .nm, .status';

  function key(td) {
    if (!td) return null;
    if (td.dataset.v !== undefined) return Number(td.dataset.v);
    let text = '';
    td.childNodes.forEach(n => {
      if (n.nodeType === Node.TEXT_NODE) text += n.textContent;
      else if (n.nodeType === Node.ELEMENT_NODE && !n.matches(SKIP)) text += n.textContent;
    });
    text = text.trim();
    if (!text) {
      const status = td.querySelector('.status');
      return status ? status.textContent.trim().toLowerCase() : null;
    }
    const m = text.replace(/\u2212/g, '-').replace(/[,$%\u00a0]/g, '').match(/^[-+]?\d*\.?\d+(?:e[-+]?\d+)?/i);
    return m ? parseFloat(m[0]) : text.toLowerCase();
  }

  function compare(a, b) {
    if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;
    if (typeof a === 'number' && typeof b === 'number') return a - b;
    if (typeof a === 'number') return -1;
    if (typeof b === 'number') return 1;
    return a.localeCompare(b, 'en', { numeric: true });
  }

  function sortBy(th) {
    const table = th.closest('table');
    const body = table && table.tBodies[0];
    if (!body || body.rows.length < 2 || body.querySelector('td[colspan]')) return;
    const col = Array.prototype.indexOf.call(th.parentNode.children, th);
    const state = th.getAttribute('aria-sort');
    const initial = th.dataset.sortDefault;
    const next = initial ? (state === initial ? (initial === 'descending' ? 'ascending' : 'descending') : 'none')
      : state === 'ascending' ? 'descending' : state === 'descending' ? 'none' : 'ascending';
    th.parentNode.querySelectorAll('th').forEach(h => h.removeAttribute('aria-sort'));
    const rows = Array.from(body.rows);
    rows.forEach((r, i) => { if (r.dataset.order === undefined) r.dataset.order = i; });
    if (next === 'none') {
      // The build's order: a table whose order is a column's default sort shows that column's state again.
      rows.sort((a, b) => a.dataset.order - b.dataset.order);
      const d = th.parentNode.querySelector('[data-sort-default]');
      if (d) d.setAttribute('aria-sort', d.dataset.sortDefault);
    } else {
      th.setAttribute('aria-sort', next);
      const sign = next === 'ascending' ? 1 : -1;
      rows.sort((a, b) => {
        const ka = key(a.cells[col]);
        const kb = key(b.cells[col]);
        if (ka === null || kb === null) return compare(ka, kb);
        return sign * compare(ka, kb) || a.dataset.order - b.dataset.order;
      });
    }
    rows.forEach(r => body.appendChild(r));
  }

  function prepare(root) {
    root.querySelectorAll('thead th:not([tabindex]):not([data-nosort])').forEach(th => {
      th.tabIndex = 0;
      th.title = 'Sort by this column';
    });
  }

  document.addEventListener('click', event => {
    const th = event.target.closest('thead th');
    if (th) { if (!th.hasAttribute('data-nosort')) sortBy(th); return; }
    const row = event.target.closest('tbody tr');
    if (!row || event.target.closest('a, button, select, input, label, summary')) return;
    if (String(window.getSelection())) return;
    const link = row.dataset.href || row.querySelector('a[href]')?.getAttribute('href');
    if (!link) return;
    const url = new URL(link, location.href);
    if (event.ctrlKey || event.metaKey) window.open(url, '_blank');
    else location.href = url;
  });
  document.addEventListener('keydown', event => {
    const th = event.target.closest && event.target.closest('thead th');
    if (th && !th.hasAttribute('data-nosort') && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); sortBy(th); }
  });

  prepare(document);
  let pending = false;
  new MutationObserver(() => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; prepare(document); });
  }).observe(document.body, { childList: true, subtree: true });

  function openTarget() {
    const id = decodeURIComponent(location.hash.slice(1));
    const target = id && document.getElementById(id);
    if (!target) return;
    let d = target.closest('details');
    while (d) { d.open = true; d = d.parentElement.closest('details'); }
    target.scrollIntoView();
  }
  window.addEventListener('hashchange', openTarget);
  openTarget();
})();
