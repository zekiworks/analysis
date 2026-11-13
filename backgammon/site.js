'use strict';

/* Every page: the Dark / Light switch, with one memory for the whole site: the choice is kept in localStorage ("theme")
   and applied by a line in each page's <head> before it renders, as data-theme="light" or "dark" on <html>; without
   JavaScript the page stays dark. */
(function setupTheme() {
  const control = document.querySelector('.theme-switch');
  if (!control) return;
  const buttons = control.querySelectorAll('button');
  const show = () => {
    const light = document.documentElement.dataset.theme === 'light';
    buttons.forEach(button => button.setAttribute('aria-pressed', String((button.dataset.themeChoice === 'light') === light)));
  };
  control.hidden = false;
  show();
  control.addEventListener('click', event => {
    const choice = event.target.closest('button')?.dataset.themeChoice;
    if (!choice) return;
    // Always named, light or dark: the suite strip (suite-bar.css) follows data-theme, and without it the reader's system.
    document.documentElement.dataset.theme = choice === 'light' ? 'light' : 'dark';
    try {
      localStorage.setItem('theme', choice);
    } catch (error) {
      /* Storage may be unavailable; the choice then lasts for this page view. */
    }
    show();
  });
})();

/* Every page: More options in the top bar opens the page export (the colour theme has its own keys beside it). Escape
   closes it and gives the focus back to its key; a click outside it or the focus leaving it closes it too. The page
   export closes it first, so the PNG shows the page without the open menu (this listener runs before png.js's). */
(function moreOptions() {
  const toggle = document.querySelector('[data-more-toggle]');
  if (!toggle) return;
  const menu = toggle.parentElement;
  const pop = document.getElementById(toggle.getAttribute('aria-controls'));
  const set = open => {
    toggle.setAttribute('aria-expanded', String(open));
    pop.hidden = !open;
  };
  toggle.addEventListener('click', () => set(pop.hidden));
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || pop.hidden) return;
    const inside = menu.contains(document.activeElement) || document.activeElement === document.body;
    set(false);
    if (inside) toggle.focus();
  });
  menu.addEventListener('focusout', event => {
    if (!pop.hidden && event.relatedTarget && !menu.contains(event.relatedTarget)) set(false);
  });
  document.addEventListener('click', event => {
    if (!pop.hidden && !menu.contains(event.target)) set(false);
  });
  const pagePng = pop.querySelector('[data-page-png]');
  if (pagePng) pagePng.addEventListener('click', () => { set(false); toggle.focus(); });
})();

/* If the tab row is ever wider than the window (it wraps on a phone), the current tab starts in the middle of the row,
   and a tab that takes the keyboard focus is brought fully into view. */
(function keepNavLinksInView() {
  const bar = document.querySelector('.site-tabs ul');
  if (!bar) return;
  const current = bar.querySelector('[aria-current]');
  if (current && bar.scrollWidth > bar.clientWidth) {
    const a = current.getBoundingClientRect(), b = bar.getBoundingClientRect();
    bar.scrollLeft += a.left - b.left - (b.width - a.width) / 2;
  }
  bar.addEventListener('focusin', event => event.target.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
})();

/* Every page: the cost unit, one choice for the whole site, as on the sibling site: costs per 1,000 decisions or per 1M
   decisions. The choice comes from ?cost-unit= (1k or 1m), else localStorage ("costUnit"), and sits in
   <html data-cost-unit>, which a line in each page's <head> sets before it renders; site.css shows the chosen unit. The
   page carries each cost per 1,000 decisions as printed (a stored value); the per-1M text is written here from the
   cost's data-usd (per 1,000 decisions), so the page itself holds no number that is not in a data file: the values, a
   cost chart's axis ticks (data-tick: whole dollars) and the tooltips of its rows (li[data-usd]). Without JavaScript
   costs read per 1,000 decisions. */
(function setupCostUnit() {
  const root = document.documentElement;
  const unit = () => (root.dataset.costUnit === '1m' ? '1m' : '1k');
  const perMillion = (usd, tick) => {
    const v = Number(usd) * 1000;
    return `$${v.toLocaleString('en-US', tick || v >= 100 ? { maximumFractionDigits: v < 1 ? 2 : 0 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };
  document.querySelectorAll('.cost-1m[data-usd]').forEach(el => {
    el.textContent = `${el.dataset.prefix || ''}${perMillion(el.dataset.usd, el.hasAttribute('data-tick'))}`;
  });
  // A cost row's tooltip names its cost in the chosen unit.
  const tips = () => document.querySelectorAll('li.hbar[data-usd]').forEach(li => {
    if (!li.dataset.tip1k) li.dataset.tip1k = li.title;
    li.title = unit() === '1m'
      ? li.dataset.tip1k.replace(/\$[\d.,]+ per 1,000 decisions/, `${perMillion(li.dataset.usd, false)} per 1M decisions`)
      : li.dataset.tip1k;
  });
  tips();
  const press = () => document.querySelectorAll('[data-cost-unit-choice]').forEach(key => {
    key.setAttribute('aria-pressed', String(key.dataset.costUnitChoice === unit()));
  });
  const keep = choice => {
    try {
      localStorage.setItem('costUnit', choice);
    } catch (error) {
      /* Storage may be unavailable; the address still carries the choice. */
    }
  };
  const asked = new URLSearchParams(location.search).get('cost-unit');
  if (asked === '1k' || asked === '1m') {
    if (asked === '1m') root.dataset.costUnit = '1m'; else delete root.dataset.costUnit;
    keep(asked);
  }
  press();
  document.addEventListener('click', event => {
    const key = event.target.closest('[data-cost-unit-choice]');
    if (!key || key.dataset.costUnitChoice === unit()) return;
    const choice = key.dataset.costUnitChoice;
    if (choice === '1m') root.dataset.costUnit = '1m'; else delete root.dataset.costUnit;
    keep(choice);
    const url = new URL(location.href);
    url.searchParams.set('cost-unit', choice);
    history.replaceState(history.state, '', url);
    press();
    tips();
  });
})();

/* Every page: the sticky header (the suite strip and the site's bar with its tabs, Ümit #2901). Its height is kept in
   --view-bar-h, so links to a part of a page land below it. */
(function setupViewBar() {
  const bar = document.querySelector('.site-header');
  if (!bar) return;
  const measure = () => document.documentElement.style.setProperty('--view-bar-h', `${bar.offsetHeight}px`);
  measure();
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(bar);
})();

/* A model's details box (Ümit #2904, as Clocktower Bench's; tap on a phone, Ümit via Zeki #5462): every row with
   data-box (the home leaderboard, "Did they improve?", the Repeat checks) holds its setup's box (.hl-box, shown in its
   row without script); no separate Details key or row sits under the model. With a mouse it shows while the pointer
   is on the row or its box (150 ms of grace after leaving both, so the pointer can cross a corner into the box; another
   row takes over at once) and a click on the name follows its link; with the keyboard while the focus is in the row
   (the model's name, then the box's links). It stands beside its row where the window has room, right of the score
   column (else right of the name column), from the row's top (from its bottom upwards near the window's foot), so it
   never covers another row's name (HoverCheck, Zeki #3146); else under the row. On a touch screen a tap on the model's
   name (or elsewhere on its row) opens it in place of the name's link, as a popover at the name: under it, else over
   it, capped and scrolling inside where it fits neither way, always within the window's width; a second tap, a tap
   outside it or Escape closes it and the focus goes back to the name. A tap on the box's text does nothing (no row
   link is followed); its links work. Escape closes a box opened by hover or focus too. The listeners sit on the
   document, so rows that are sorted, filtered, moved or written again keep working; a box whose row a filter or tab
   hides closes. On a touch screen a tap on a chart's mark shows its tooltip (the SVG <title>, a bar row's title) in
   the same kind of popover, which a touch screen would never show. */
(function modelBoxes() {
  let open = null, pinned = false, atName = false, quiet = false, leaving = 0;
  let pointer = 'mouse', pointing = false, keyed = false;  // pointing: the last input was a press, not a key
  let tip = null, tipFor = null;
  const boxOf = tr => document.getElementById(tr.dataset.box);
  const nameOf = tr => tr.querySelector('.model-name') || tr;
  const rowOf = el => (el instanceof Element ? el.closest('tr[data-box]') : null);
  const shown = el => el.getClientRects().length > 0;
  const headerBottom = () => document.querySelector('.site-header')?.getBoundingClientRect().bottom || 0;
  // A popover at r (its anchor's rectangle): under it, else over it; capped to the larger side where neither fits.
  // False where the anchor has left the window (the caller closes it).
  const atAnchor = (box, r) => {
    const vw = document.documentElement.clientWidth, top = headerBottom() + 4, bottom = innerHeight - 8;
    if (r.bottom <= top - 4 || r.top >= innerHeight) return false;
    box.style.maxHeight = '';
    const width = box.offsetWidth, height = box.offsetHeight;
    box.style.left = `${Math.max(8, Math.min(r.left, vw - width - 8))}px`;
    const roomBelow = bottom - r.bottom - 6, roomAbove = r.top - 6 - top;
    if (height <= roomBelow) box.style.top = `${r.bottom + 6}px`;
    else if (height <= roomAbove) box.style.top = `${r.top - 6 - height}px`;
    else if (roomBelow >= roomAbove) {
      box.style.maxHeight = `${Math.max(roomBelow, 80)}px`;
      box.style.top = `${r.bottom + 6}px`;
    } else {
      box.style.maxHeight = `${roomAbove}px`;
      box.style.top = `${top}px`;
    }
    return true;
  };
  const place = () => {
    if (tip && !atAnchor(tip, tipFor.getBoundingClientRect())) hideTip();
    if (!open) return;
    const box = boxOf(open);
    if (!shown(open)) { hide(false); return; }  // a filter or tab has hidden its row
    const vw = document.documentElement.clientWidth;  // the visible width, even where something overflows the page
    const width = Math.min(380, vw - 16);
    box.style.width = `${width}px`;
    if (atName) {
      if (!atAnchor(box, nameOf(open).getBoundingClientRect())) hide(false);
      return;
    }
    box.style.maxHeight = '';
    let height = box.offsetHeight;
    const row = open.getBoundingClientRect(), cell = nameOf(open).closest('td, th').getBoundingClientRect();
    const score = (open.cells[2] || open.cells[open.cells.length - 1]).getBoundingClientRect();
    const header = headerBottom();
    const bottom = innerHeight - 8;
    const side = vw - 8 - score.right >= width ? score.right : vw - 8 - cell.right >= width ? cell.right : null;
    if (side !== null) {
      // Beside the row: from its top, else ending at its bottom; where neither fits, within the window as near the
      // row as it goes, capped to the window under the header (scrolling inside).
      box.style.left = `${side}px`;
      const top = header + 4;
      if (height > bottom - top) { height = Math.max(bottom - top, 80); box.style.maxHeight = `${height}px`; }
      box.style.top = `${row.top >= top && row.top + height <= bottom ? row.top
        : row.bottom - height >= top && row.bottom <= bottom ? row.bottom - height
        : Math.min(Math.max(row.top, top), bottom - height)}px`;
      return;
    }
    box.style.left = `${Math.max(8, Math.min(cell.left, vw - width - 8))}px`;
    // Under the row if it fits (no gap: the pointer moves from the row into its box without leaving the row), else
    // above it; else capped to the larger side (120 px at least), else the window under the header.
    const roomBelow = bottom - row.bottom, roomAbove = row.top - header - 4;
    if (height <= roomBelow) box.style.top = `${row.bottom}px`;
    else if (height <= roomAbove) box.style.top = `${row.top - height}px`;
    else if (Math.max(roomBelow, roomAbove) >= 120) {
      box.style.maxHeight = `${Math.max(roomBelow, roomAbove)}px`;
      box.style.top = `${roomBelow >= roomAbove ? row.bottom : row.top - roomAbove}px`;
    } else {
      box.style.maxHeight = `${Math.max(bottom - header - 4, 80)}px`;
      box.style.top = `${header + 4}px`;
    }
  };
  // back: the focus returns to the name (without scrolling to it), unless it has gone elsewhere since.
  function hide(back) {
    if (!open) return;
    const tr = open, name = nameOf(tr);
    boxOf(tr)?.classList.remove('open');
    tr.classList.remove('hl-open');
    if (name !== tr) name.setAttribute('aria-expanded', 'false');
    open = null;
    pinned = false;
    atName = false;
    const active = document.activeElement;
    if (back && shown(name) && (!active || active === document.body || tr.contains(active))) {
      quiet = true;
      name.focus({ preventScroll: true });
      quiet = false;
    }
  }
  // A box or tooltip with its own click listener: WebKit (iOS) moves a tap on text that does not take clicks to a
  // clickable element nearby (a sort header, another row's name); one that does keeps the tap.
  const tappable = new WeakSet();
  const keepTaps = el => { if (!tappable.has(el)) { el.addEventListener('click', () => {}); tappable.add(el); } };
  const show = (tr, pin, byTouch) => {
    if (open !== tr) hide(false);
    const box = boxOf(tr);
    if (!box) return;
    open = tr;
    pinned = pin;
    atName = byTouch;
    tr.classList.add('hl-open');
    const name = nameOf(tr);
    if (name !== tr) name.setAttribute('aria-expanded', 'true');
    keepTaps(box);
    box.classList.add('open');
    place();
  };
  function hideTip() {
    if (!tip) return;
    tip.remove();
    tip = tipFor = null;
  }
  // The chart mark under a tap that has a tooltip: an SVG element with its own <title> (not the chart's), a bar row's title.
  const titled = el => {
    if (!(el instanceof Element)) return null;
    const bar = el.closest('li.hbar[title]');
    if (bar) return bar;
    for (let e = el; e && e.tagName.toLowerCase() !== 'svg' && e.closest('svg'); e = e.parentElement) {
      if (e.querySelector(':scope > title')) return e;
    }
    return null;
  };
  // The tooltip's text, then the mark's own link (a bar row's model page), which the tap opened the tooltip in place of.
  const showTip = mark => {
    hideTip();
    tip = document.createElement('div');
    tip.className = 'hl-box chart-tip open';
    tip.setAttribute('role', 'group');
    const text = document.createElement('p');
    text.textContent = (mark.matches('li') ? mark.title : mark.querySelector(':scope > title').textContent).trim();
    tip.append(text);
    const link = mark.querySelector('a[href]') || mark.closest('a[href]');
    if (link) {
      const a = document.createElement('a');
      a.href = link.href;
      a.textContent = `${link.textContent.trim()} \u2192`;
      const p = document.createElement('p');
      p.append(a);
      tip.append(p);
    }
    document.body.append(tip);
    keepTaps(tip);
    tipFor = mark;
    if (!atAnchor(tip, mark.getBoundingClientRect())) hideTip();
  };
  // Keyboard focus in the open row (its name or its box) keeps the box: the pointer leaving the row or entering another
  // row does not take it away until the focus leaves the row, Escape, a second tap or a click outside. Focus that a
  // press of the pointer gives (pointing: until the next key; a tap's focus comes after its pointerup) neither opens a
  // box nor holds one: the press itself decides.
  const held = () => !!open && keyed && open.contains(document.activeElement);
  let down = null;
  document.addEventListener('pointerdown', event => {
    pointing = true;
    pointer = event.pointerType || 'mouse';
    down = { x: event.clientX, y: event.clientY };
  }, true);
  document.addEventListener('keydown', () => { pointing = false; }, true);
  // A tap (not a drag) on a touch screen: a chart mark's tooltip opens or closes, and a tap outside closes what is open,
  // here and not on click, as WebKit sends no click for a tap on an SVG mark or plain text.
  document.addEventListener('pointerup', event => {
    if (event.pointerType === 'mouse' || !down || Math.hypot(event.clientX - down.x, event.clientY - down.y) > 10) return;
    const mark = titled(event.target);
    if (mark) {
      hide(false);
      if (tipFor === mark) hideTip(); else showTip(mark);
      return;
    }
    if (tip && !tip.contains(event.target)) hideTip();
    if (open && pinned && !open.contains(event.target)) hide(true);
  }, true);
  const stay = () => { clearTimeout(leaving); leaving = 0; };
  document.addEventListener('pointerover', event => {
    const tr = rowOf(event.target);
    if (event.pointerType !== 'mouse' || !tr || tr.contains(event.relatedTarget)) return;
    stay();
    if (!pinned && !held()) show(tr, false, false);
  });
  document.addEventListener('pointerout', event => {
    const tr = rowOf(event.target);
    if (event.pointerType !== 'mouse' || !tr || tr !== open || tr.contains(event.relatedTarget) || pinned || held()) return;
    stay();
    leaving = setTimeout(() => { leaving = 0; if (open === tr && !pinned && !held()) hide(false); }, 150);
  });
  document.addEventListener('focusin', event => {
    const tr = rowOf(event.target);
    if (!tr) return;
    keyed = !pointing;
    if (keyed && open !== tr && !quiet) show(tr, false, false);
  });
  document.addEventListener('focusout', event => {
    const tr = rowOf(event.target);
    if (tr && open === tr && !pinned && !tr.contains(event.relatedTarget)) hide(false);
  });
  // Before the page's other click handlers (capture): a prevented click is left alone by tables.js's row links.
  document.addEventListener('click', event => {
    const touched = pointer !== 'mouse' && event.detail !== 0;
    if (touched && titled(event.target)) {
      event.preventDefault();  // the tooltip (pointerup) in place of the mark's link, which the tooltip holds
      return;
    }
    if (tip && !tip.contains(event.target)) hideTip();
    const tr = rowOf(event.target);
    if (tr && touched && boxOf(tr)) {
      const control = event.target.closest('a, button, select, input, label, summary');
      if (boxOf(tr).contains(event.target)) {
        if (!control) event.preventDefault();
        return;
      }
      if (!control || control.classList.contains('model-name')) {
        event.preventDefault();  // the tap opens the box; the name's own link is in the box
        if (open === tr && pinned) hide(true); else show(tr, true, true);
        return;
      }
    }
    if (open && !open.contains(event.target)) hide(pinned);
  }, true);
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    hideTip();
    if (open) hide(pinned || open.contains(document.activeElement));
  });
  // The table's own sideways scroll moves the name too; a scroll inside the box itself does not move it.
  addEventListener('scroll', event => {
    if (open && event.target instanceof Node && boxOf(open)?.contains(event.target)) return;
    place();
  }, { passive: true, capture: true });
  addEventListener('resize', place);
  // The page moving under an open box (a table loaded or a font arriving above it) moves the box with its row.
  if ('ResizeObserver' in window) new ResizeObserver(() => { if (open || tip) place(); }).observe(document.body);
})();
