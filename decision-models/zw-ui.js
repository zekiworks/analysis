/* zw-ui.js: the shared UI kit of the Zeki Works bench sites (markup: zw_ui.py; contract: zw-ui.md). Copied byte for
   byte (sha256) into every site; never edit a copy. Base: logic's kit-form draft (bus #4885) of the Logic & Math site,
   completed by turkce against the kit contract (Ümit #4862); v2 with the three ports' asks (#4918, #4923, Reading's),
   v2.1 with shared cost calculations and panels loaded on first show (logic #4931).
   Modules, each a no-op when its markup is absent: keys (filter rows, Measure keys and Chart / Table keys: the URL
   state), lists (tier/rank, Top N with its Show all button, pinned reference rows, sub-rows, empty lines, legends),
   panels (a panel outside the default view fetched from its fragment file on first show), filter bar (the phone's
   Filters button, its count and the scope summary), header (its height, the current tab in view), cost labels (a
   cost's calculation, one per distinct text), details (a row's details box, one per setup), tips (a head's
   explanation). Each module acts inside its own .zw-block, one init per block (two blocks on a page each keep their
   own state and address parameters), never on the rest of the page; the links marked data-zw-keep anywhere carry
   every block's view. No site names, labels or measures in here: every word comes from the page.
   Without this script the default panel, every other panel's link to its own page, every row, box and calculation
   show (zw-ui.css acts under html.zw-js). */
(function () {
  'use strict';
  const root = document.documentElement;
  root.classList.add('zw-js');
  /* --- header: its height and the current tab in view (site.js:83-89 setupHeader, 188-192) ----------------------- */
  const head = document.querySelector('.zw-head');
  if (head) {
    const measure = () => root.style.setProperty('--zw-head-h', `${head.offsetHeight}px`);
    measure();
    if ('ResizeObserver' in window) new ResizeObserver(measure).observe(head);
    const current = head.querySelector('.zw-nav a[aria-current]');
    const strip = current?.closest('ul');
    if (strip) {
      const past = current.getBoundingClientRect().right - strip.getBoundingClientRect().right;
      if (past > 0) strip.scrollLeft += past + 12;
    }
  }

  /* --- blocks: every .zw-block on the page (zw_ui.results) runs on its own: its keys, lists, panels, boxes and
     address parameters (prefixed with its data-zw-prefix, where a page has more than one block) act on it alone.
     window.zwUi is the first block's (state(), set()); zwUi.blocks[id] each block's. A page without a block keeps the
     header module and a zwUi with an empty state. --------------------------------------------------------------- */
  const blocks = [...document.querySelectorAll('.zw-block')];
  const apis = (blocks.length ? blocks : [document.createElement('div')]).map(host => initBlock(host));
  window.zwUi = Object.assign(apis[0], { blocks: Object.fromEntries(blocks.map((block, i) => [block.id, apis[i]])) });

  function initBlock(host) {
    // The address parameters of this block: 'models', or with a prefix ('b2-') 'b2-models'.
    const prefix = host.dataset.zwPrefix || '';

    /* The filter rows' parameters, in their fixed order (measure, view and top are never filter rows). */
    const ORDER = ['part', 'models', 'class', 'setups'];
    const state = {};
    const params = {};   // name -> {def, any, keys: [button], rows: [row]}

    /* --- keys: filter rows, Measure keys, Chart / Table keys (site.js:16-80 setupModels, 111-193 setupLeaderboard) --- */
    const keyRows = [...host.querySelectorAll('.zw-row[data-zw-param]')];

    // The filter rows in the fixed order Part · Models · Class · Rows, whatever order the markup has; other children of
    // the block keep their places.
    host.querySelectorAll('.zw-filters').forEach(block => {
      const own = [...block.children].filter(el => el.matches('.zw-row[data-zw-param]'));
      const rank = row => { const i = ORDER.indexOf(row.dataset.zwParam); return i < 0 ? ORDER.length : i; };
      const sorted = [...own].sort((a, b) => rank(a) - rank(b));
      const marks = own.map(row => { const mark = document.createComment(''); row.replaceWith(mark); return mark; });
      marks.forEach((mark, i) => mark.replaceWith(sorted[i]));
    });

    keyRows.forEach(row => {
      const name = row.dataset.zwParam;
      const keys = [...row.querySelectorAll('button[data-zw-value]')];
      const p = params[name] ??= { def: row.dataset.zwDefault ?? keys[0]?.dataset.zwValue, any: row.dataset.zwAny ?? null, keys: [], rows: [] };
      p.keys.push(...keys);
      p.rows.push(row);
    });
    // Top N: the lists that cut their rows (data-zw-top) share one parameter, 'top', set by their Show all buttons: N
    // (the block's data-zw-top, else the first such list's: the default) or 'all'.
    const firstTop = host.dataset.zwTop || host.querySelector('.zw-list[data-zw-top]')?.dataset.zwTop;
    if (firstTop) params.top = { def: firstTop, any: null, keys: [], rows: [] };
    const names = Object.keys(params);
    // The state read from the address (this block's parameters; a value with no key: the default). On load, and again
    // whenever the address changes under the page (Back, Forward, a typed or followed fragment: follow() below).
    const parts = value => String(value ?? '').split(',');
    const offered = (name, value) => (params[name].any !== null || !String(value).includes(','))
      && parts(value).every(v => params[name].keys.some(k => k.dataset.zwValue === v));
    const fromAddress = () => {
      const url = new URLSearchParams(window.location.search);
      names.forEach(name => {
        const asked = url.get(prefix + name);
        if (name === 'top') { state.top = asked === 'all' ? 'all' : firstTop; return; }
        const known = asked !== null && offered(name, asked);
        state[name] = known ? [...new Set(parts(asked))].join(',') : params[name].def;
      });
    };
    fromAddress();
    const scopedNames = names.filter(n => n !== 'top');

    // An element with data-<param> belongs to the listed values of that parameter (space-separated); the row's any-value
    // (data-zw-any, e.g. 'all') matches every element; a state of two values matches an element of either. fits: the
    // element and every ancestor inside the block match (with one override).
    const matches = (el, name, value) => {
      const own = el.getAttribute(`data-${name}`);
      if (own === null || value === params[name].any) return true;
      const listed = own.split(/\s+/);
      return parts(value).some(v => listed.includes(v));
    };
    const fits = (el, name, value) => {
      for (let node = el; node && node !== host.parentElement; node = node.parentElement) {
        if (!scopedNames.every(n => matches(node, n, n === name ? value : state[n]))) return false;
      }
      return true;
    };
    const scoped = scopedNames.length ? scopedNames.map(n => `[data-${n}]`).join(',') : null;

    // The links that keep the view (data-zw-keep: every parameter, or the listed ones), site.js:56-59 keepGroup. Each
    // carries every kept value explicitly, so another page with other defaults opens the same view; the link's own path,
    // other parameters and #fragment stay as written. Every such link on the page now, on each change (so a panel inserted
    // later has its links kept too), and again as a link is followed (capture phase: a link a site adds at any time).
    const keepOne = link => {
      // From the link's current address: another block's values stay, this block's are set again.
      const [front, fragment] = link.getAttribute('href').split('#');
      const [path, query] = front.split('?');
      const search = new URLSearchParams(query || '');
      const only = (link.dataset.zwKeep || '').split(/\s+/).filter(Boolean);
      names.filter(n => !only.length || only.includes(n)).forEach(n => search.set(prefix + n, state[n]));
      const text = search.toString().replace(/%2C/g, ',');
      link.setAttribute('href', `${path}${text ? `?${text}` : ''}${fragment !== undefined ? `#${fragment}` : ''}`);
    };
    const keep = () => document.querySelectorAll('a[data-zw-keep][href]').forEach(keepOne);
    // Another block's change (a panel it inserted brings new links): this block's values go on them too.
    document.addEventListener('zw-change', event => { if (event.target !== host) keep(); });
    ['click', 'auxclick'].forEach(type => document.addEventListener(type, event => {
      const link = event.target.closest?.('a[data-zw-keep][href]');
      if (link) keepOne(link);
    }, true));

    // data-zw-when: an element (a note) shown only in a filter state, 'param=v1,v2' and 'param!=v' joined by ';'
    // (zw_ui.when_holds), with no any-value override: 'class!=all' shows only while a class is chosen.
    const whenHolds = when => when.split(';').map(part => part.trim()).filter(Boolean).every(condition => {
      const negated = condition.includes('!=');
      const [name, listed] = condition.split(negated ? '!=' : '=');
      if (listed === undefined) return true;
      const inside = listed.split(',').map(v => v.trim()).some(v => parts(state[name.trim()]).includes(v));
      return inside !== negated;
    });

    const apply = write => {
      names.forEach(name => params[name].keys.forEach(k => k.setAttribute('aria-pressed', String(parts(state[name]).includes(k.dataset.zwValue)))));
      if (scoped) host.querySelectorAll(scoped).forEach(el => {
        if (el.closest('.zw-row')) return;
        el.classList.toggle('zw-away', !scopedNames.every(n => matches(el, n, state[n])));
      });
      host.querySelectorAll('[data-zw-when]').forEach(el => el.classList.toggle('zw-away', !whenHolds(el.dataset.zwWhen)));
      // A key of a data-zw-hide-empty row with no table row or bar in view for it goes out of view (site.js:152-158);
      // the any-value and the chosen keys always stay, so a second tap can clear them. A view with no rows at all (a
      // panel that is not measured) hides none, so the row does not collapse to All.
      const rows = [...host.querySelectorAll('table.zw-table > tbody > tr:not(.zw-sub):not(.zw-group-head):not([data-zw-pinned]), ol.zw-bars > li:not(.zw-group-head):not([data-zw-pinned])')];
      keyRows.filter(row => 'zwHideEmpty' in row.dataset).forEach(row => {
        const name = row.dataset.zwParam;
        const any = params[name].any;
        const viewHasRows = any !== null && rows.some(tr => fits(tr, name, any));
        row.querySelectorAll('button[data-zw-value]').forEach(k => {
          const v = k.dataset.zwValue;
          k.hidden = viewHasRows && v !== any && !parts(state[name]).includes(v) && !rows.some(tr => fits(tr, name, v));
        });
      });
      table();
      keep();
      filterBar();
      panels.load();
      if (write) {  // the address holds every value that is not the page's default (site.js:161-168)
        const next = new URL(window.location.href);
        // In one order (the filter rows', then measure, view, top), after the page's other parameters.
        names.forEach(n => next.searchParams.delete(prefix + n));
        names.forEach(n => { if (state[n] !== params[n].def) next.searchParams.set(prefix + n, state[n]); });
        next.search = next.searchParams.toString().replace(/%2C/g, ',');
        try { history.replaceState(history.state, '', next); } catch (e) { /* file:// in some browsers: the view still changes */ }
      }
      // On the block, bubbling to the document (event.target: the block).
      host.dispatchEvent(new CustomEvent('zw-change', { bubbles: true, detail: { ...state } }));
    };

    // A tap on a key selects it (only it, where two were chosen); a second tap on the selected key clears its row: to the
    // any-value (All) where the row has one (Models, Class: site.js:41-55, Ümit #3923, backgammon #3925), else to the
    // default (Part, Rows, the Measure back to the main measure, #4660; the view).
    names.forEach(name => params[name].keys.forEach(k => k.addEventListener('click', () => {
      const v = k.dataset.zwValue;
      state[name] = state[name] === v ? (params[name].any ?? params[name].def) : v;
      apply(true);
    })));
    // The Show all button: every long list's rows, and back to the Top N. On closing the button stays where it was on
    // screen while the rows above it fold away, so the page does not jump under the finger (v2.5; Ümit #6070, jevgammon
    // #6168); opening leaves the page where it is, the new rows below the top N. A row's 'N other settings' key
    // (Reading's Leaderboard expander): its sub-rows open under it and close again. Both by delegation, so the rows of a
    // panel loaded later work the same.
    host.addEventListener('click', event => {
      const button = event.target.closest('.zw-showall');
      if (button) {
        const closing = state.top === 'all';
        const before = button.getBoundingClientRect().top;
        state.top = closing ? firstTop : 'all';
        apply(true);
        if (closing) window.scrollBy({ top: button.getBoundingClientRect().top - before, behavior: 'instant' });
        return;
      }
      const more = event.target.closest('.zw-more[aria-controls]');
      if (more) {
        const open = more.getAttribute('aria-expanded') !== 'true';
        more.setAttribute('aria-expanded', String(open));
        more.getAttribute('aria-controls').split(/\s+/).forEach(id => document.getElementById(id)?.classList.toggle('zw-sub-closed', !open));
      }
    });

    /* --- lists: tier/rank, Top N, empty lines, Show all, legends (site.js:138-151); a pinned row (a program, a
       baseline: data-zw-pinned) shows while its filters hold, never ranked, counted or cut; a list in groups (a heading
       row data-zw-group-head, rows data-zw-group) ranks and cuts each group on its own, a heading with none of its
       rows in view going with them. One list for two Rows choices (zw_ui Bench.one_list: data-zw-flat, the choice it
       also shows): for that choice its sub-rows show flat among the rows, all of them in that choice's order
       (data-zw-flat-order), ranked and tiered by that choice's tiers (data-zw-flat-tier, data-zw-flat-untiered); for the
       other choice the rows come back in their own order, each sub-row under its row behind its expander. ---------- */
    const groupOf = el => el.dataset.zwGroup ?? (el.dataset.zwOf ? document.getElementById(el.dataset.zwOf)?.dataset.zwGroup : undefined) ?? '';
    const flatten = (list, holder, flat) => {
      holder.zwNested ??= [...holder.children];
      if (flat === !!holder.zwFlat) return;
      holder.zwFlat = flat;
      if (!flat) { holder.append(...holder.zwNested); return; }
      const order = el => (el.dataset.zwFlatOrder === undefined ? 1e9 : Number(el.dataset.zwFlatOrder));
      const heads = new Map(holder.zwNested.filter(el => el.classList.contains('zw-group-head')).map(el => [el.dataset.zwGroupHead, el]));
      const sorted = holder.zwNested.filter(el => !el.classList.contains('zw-group-head'))
        .map((el, i) => [el, i]).sort((a, b) => order(a[0]) - order(b[0]) || a[1] - b[1]).map(([el]) => el);
      const out = [];
      sorted.forEach(el => {
        const g = groupOf(el);
        if (heads.has(g)) { out.push(heads.get(g)); heads.delete(g); }
        out.push(el);
      });
      holder.append(...out, ...heads.values());
    };
    function table() {
      host.querySelectorAll('.zw-list').forEach(list => {
        const tbl = list.querySelector('table.zw-table');
        const holder = tbl ? tbl.tBodies[0] : list.querySelector('ol.zw-bars');
        const flat = list.dataset.zwFlat !== undefined && state.setups === list.dataset.zwFlat;
        if (list.dataset.zwFlat !== undefined && holder) {
          list.classList.toggle('zw-flat-on', flat);
          flatten(list, holder, flat);
        }
        const all = holder ? [...holder.children] : [];
        const heads = all.filter(item => item.classList.contains('zw-group-head'));
        const subs = all.filter(item => item.classList.contains('zw-sub'));
        const items = all.filter(item => !item.classList.contains('zw-group-head') && !('zwPinned' in item.dataset)
          && (flat || !item.classList.contains('zw-sub')));
        const shown = items.filter(item => !item.classList.contains('zw-away'));
        const groups = new Map();
        shown.forEach(item => { const g = groupOf(item); if (!groups.has(g)) groups.set(g, []); groups.get(g).push(item); });
        // Ranks 1, 2, 3 without repeats over the rows in view (Zeki #4630); tiers where the table names their parameters;
        // a chart that shows them (ol.zw-ranked) the same way.
        const ranked = tbl || list.querySelector('ol.zw-bars.zw-ranked');
        if (ranked) {
          const by = (ranked.dataset.zwTierBy || '').split(/\s+/).filter(Boolean);
          const key = by.map(n => state[n] ?? '').join('.');
          all.forEach(item => item.classList.remove('zw-tier-start'));
          // A sub-row under its row has no rank of its own.
          if (!flat) subs.forEach(sub => { const cell = sub.querySelector(':scope > .zw-rank'); if (cell) cell.textContent = ''; });
          // A row out of view has no rank either (as zw_ui writes it), so its digits never depend on an earlier view.
          items.filter(item => item.classList.contains('zw-away')).forEach(item => {
            const cell = item.querySelector(':scope > .zw-rank');
            if (cell) cell.textContent = '';
          });
          groups.forEach(group => {
            let last = null, place = 0;
            group.forEach(tr => {
              const cell = tr.querySelector(':scope > .zw-rank');
              if (!cell) return;
              if (flat ? 'zwFlatUntiered' in tr.dataset : 'zwUntiered' in tr.dataset) { cell.textContent = '–'; return; }
              place += 1;
              if (!by.length) { cell.textContent = String(place); return; }
              const mark = ((flat ? tr.dataset.zwFlatTier : tr.dataset.zwTier) || '').split(/\s+/).find(item => item.startsWith(`${key}=`));
              const tier = mark ? mark.slice(key.length + 1) : '–';
              cell.textContent = tier;
              if (last !== null && tier !== last) tr.classList.add('zw-tier-start');
              last = tier;
            });
          });
        }
        const n = parseInt(list.dataset.zwTop, 10) || 0;
        const top = state.top === 'all' ? Infinity : n || Infinity;
        items.forEach(item => item.classList.remove('zw-cut'));
        groups.forEach(group => group.slice(top).forEach(item => item.classList.add('zw-cut')));
        heads.forEach(head => head.classList.toggle('zw-away', !groups.has(head.dataset.zwGroupHead)));
        // A sub-row under its row goes with it (out of view or past the Top N).
        if (tbl && !flat) subs.forEach(sub => {
          const of = document.getElementById(sub.dataset.zwOf);
          // (Out of view it already is: it carries its row's filters.)
          sub.classList.toggle('zw-cut', !!of && of.classList.contains('zw-cut'));
        });
        const empty = list.querySelector('.zw-empty');
        if (empty) empty.classList.toggle('zw-away', shown.length > 0);
        const button = list.querySelector('.zw-showall');
        if (button) {
          const open = state.top === 'all';
          button.classList.toggle('zw-away', !n || ![...groups.values()].some(group => group.length > n));
          button.setAttribute('aria-expanded', String(open));
          button.textContent = (open ? button.dataset.zwTextTop : button.dataset.zwTextAll).replace('{n}', (open ? n : shown.length).toLocaleString('en-US'));
        }
        // The legend lists only the series with a bar in view (Ümit #4862 item 6).
        const legend = list.querySelector('.zw-legend');
        if (legend) {
          const pinned = [...list.querySelectorAll('[data-zw-pinned]:not(.zw-away)')];
          const series = new Set([...shown.filter(item => !item.classList.contains('zw-cut')), ...pinned].map(item => item.dataset.zwSeries));
          legend.querySelectorAll('[data-zw-series]').forEach(entry => entry.classList.toggle('zw-away', !series.has(entry.dataset.zwSeries)));
          // One list for two Rows choices: the entries in the order their series first come in the list as it stands.
          if (list.dataset.zwFlat !== undefined && holder) {
            const first = [...new Set(all.map(item => item.dataset.zwSeries).filter(Boolean))];
            const entries = [...legend.querySelectorAll(':scope > [data-zw-series]')];
            entries.sort((a, b) => first.indexOf(a.dataset.zwSeries) - first.indexOf(b.dataset.zwSeries));
            legend.prepend(...entries);
          }
        }
      });
    }

    /* --- filter bar: the phone's Filters button (job8-look's key, logic's count badge) and the scope summary --------- */
    const toggles = [...host.querySelectorAll('.zw-filters-toggle[aria-controls]')];
    toggles.forEach(button => {
      const block = document.getElementById(button.getAttribute('aria-controls'));
      if (!block) return;
      block.classList.add('zw-foldable');
      button.addEventListener('click', () => {
        const open = button.getAttribute('aria-expanded') !== 'true';
        button.setAttribute('aria-expanded', String(open));
        block.classList.toggle('zw-filters-open', open);
        if (open) block.scrollIntoView({ block: 'nearest' });
      });
    });
    // The count of filter rows (inside the block) set away from their default, the badge hidden at 0; the summary: each
    // filter row's pressed key, its data-zw-summary if it has one ('' says nothing), joined by ' · '.
    function filterBar() {
      toggles.forEach(button => {
        const block = document.getElementById(button.getAttribute('aria-controls'));
        if (!block) return;
        const filterRows = [...block.querySelectorAll('.zw-row[data-zw-param]')];
        const active = new Set(filterRows.map(r => r.dataset.zwParam).filter(n => state[n] !== params[n].def)).size;
        const badge = button.querySelector('.zw-filter-count');
        if (badge) {
          badge.hidden = active === 0;
          (badge.querySelector('[data-zw-n]') || badge).textContent = String(active);
        }
        const summary = button.closest('.zw-filterbar')?.querySelector('.zw-summary');
        if (summary) {
          summary.textContent = filterRows.flatMap(row => [...row.querySelectorAll('button[aria-pressed="true"]')]
            .map(key => key.dataset.zwSummary ?? key.textContent.trim())).filter(Boolean).join(' \u00b7 ');
        }
      });
    }

    /* --- cost labels: a cost's calculation, written once per distinct text (zw_ui.Calcs: div.zw-calc-body in .zw-calcs)
       and opened from every cell that shows it (a.zw-calc-key, its link to the text without the script) by a tap, Enter
       or Space, in a box under the label; a second tap, a tap outside or Escape closes it; one at a time. It closes the
       row's details box unless the label is in that box. A cost cell written without results() (details.zw-calc) opens
       in place, as a details element does. ------------------------------------------------------------------------------ */
    const calcs = (() => {
      let key = null;
      const bodyOf = k => document.getElementById(k.getAttribute('aria-controls'));
      const place = () => {
        if (!key) return;
        const body = bodyOf(key);
        const label = key.getBoundingClientRect();
        const vw = root.clientWidth;
        const width = Math.min(320, vw - 16);
        body.style.width = `${width}px`;
        body.style.left = `${Math.max(8, Math.min(label.right - width, vw - width - 8))}px`;
        const height = body.offsetHeight;
        const below = label.bottom + 4 + height <= innerHeight - 8;
        body.style.top = `${below || label.top - height - 4 < 0 ? label.bottom + 4 : label.top - height - 4}px`;
      };
      const close = () => {
        if (!key) return;
        bodyOf(key)?.classList.remove('zw-open');
        key.setAttribute('aria-expanded', 'false');
        key = null;
      };
      const open = k => {
        close();
        const body = bodyOf(k);
        if (!body) return;
        if (!k.closest('.zw-box')) details.hide();
        key = k;
        k.setAttribute('aria-expanded', 'true');
        body.classList.add('zw-open');
        place();
      };
      const toggle = k => { if (key === k) close(); else open(k); };
      // A label is written as a plain link to its text (the page stays small); here it becomes a button for it.
      const prep = scope => scope.querySelectorAll('a.zw-calc-key:not([aria-controls])').forEach(k => {
        k.setAttribute('role', 'button');
        k.setAttribute('aria-expanded', 'false');
        k.setAttribute('aria-controls', k.getAttribute('href').slice(1));
      });
      prep(host);
      host.addEventListener('click', event => {
        const k = event.target.closest('a.zw-calc-key');
        if (!k) return;
        event.preventDefault();
        toggle(k);
      });
      host.addEventListener('keydown', event => {  // a link drawn as a button answers Space too
        const k = event.target.closest?.('a.zw-calc-key');
        if (!k || event.key !== ' ') return;
        event.preventDefault();
        toggle(k);
      });
      document.addEventListener('click', event => {
        if (key && !key.contains(event.target) && !bodyOf(key)?.contains(event.target)) close();
      });
      document.addEventListener('keydown', event => {
        if (event.key !== 'Escape' || !key) return;
        const k = key;
        const inside = k === document.activeElement || bodyOf(k)?.contains(document.activeElement);
        close();
        if (inside) k.focus();
      });
      addEventListener('scroll', place, { passive: true });
      addEventListener('resize', place);
      return { close, prep, isOpen: () => key !== null };
    })();

    /* --- details: a row's details box (site.js leaderboardDetails, after backgammon bg.js) -----------------------------
       A tap on the model's name or anywhere else on its row opens the box (in place of the name's link); a second tap,
       Escape, a tap outside or the focus leaving the row closes it. No Details button sits under the name (v2.4, Ümit
       via Zeki #5462). A mouse pointing at the row shows it while it stays there, and a click on the row away from a
       link holds it open; a mouse click on a link follows the link. The keyboard shows it while the focus is in the row
       (the name, then the box's links); focus beats the pointer, and Escape returns the focus to the name. */
    const details = (() => {
      let open = null, pinned = false, pointer = 'mouse';
      // Focus that a press of the pointer gives neither opens a box nor holds one; keyboard focus in the open row keeps
      // it while the pointer moves elsewhere.
      let pointing = false, keyed = false, quiet = false;
      const held = () => !!open && keyed && open.contains(document.activeElement);
      const boxOf = row => document.getElementById(row.dataset.zwBox);
      const place = () => {  // under the row, above it near the window's bottom, within the width (site.js:207-229)
        if (!open) return;
        const box = boxOf(open), row = open.getBoundingClientRect();
        const cell = (open.querySelector('.zw-model') || open).getBoundingClientRect();
        const vw = root.clientWidth;
        const width = Math.min(400, vw - 16);
        box.style.width = `${width}px`;
        box.style.left = `${Math.max(8, Math.min(cell.left, vw - width - 8))}px`;
        box.style.maxHeight = '';
        const height = box.offsetHeight;
        const top = head ? head.getBoundingClientRect().bottom : (document.querySelector('.site-header')?.getBoundingClientRect().bottom || 0);
        const bottom = innerHeight - 8;
        const roomBelow = bottom - row.bottom, roomAbove = row.top - top - 4;
        if (height <= roomBelow) box.style.top = `${row.bottom}px`;
        else if (height <= roomAbove) box.style.top = `${row.top - height}px`;
        else if (Math.max(roomBelow, roomAbove) >= 120) {
          box.style.maxHeight = `${Math.max(roomBelow, roomAbove)}px`;
          box.style.top = `${roomBelow >= roomAbove ? row.bottom : row.top - roomAbove}px`;
        } else {
          box.style.maxHeight = `${Math.max(bottom - top - 4, 80)}px`;
          box.style.top = `${top + 4}px`;
        }
      };
      // A box is shared by every row of its setup (zw_ui.Boxes): the one that opens it takes it into its model cell (so
      // the focus order, a click inside it and Escape treat it as the row's). On top of it go the row's helper values
      // with their heads' labels and units (zw-row-lines; shown below 600 px, where those columns are out of the table),
      // made from the row's own cells, except a column kept on the phone; they go when the box closes. A box written in
      // its row (zw_ui.details_box with phone_lines) already holds them.
      let lines = null;
      const helperLines = row => {
        const box = boxOf(row);
        const heads = row.closest('table')?.tHead?.rows[0]?.cells;
        if (!heads || box.querySelector(':scope > .zw-box-phone')) return null;
        const out = document.createElement('div');
        out.className = 'zw-row-lines';
        [...row.cells].forEach((cell, index) => {
          const th = heads[index];
          if (!cell.classList.contains('zw-help') || cell.classList.contains('zw-keep-phone') || !th?.dataset.zwLabel) return;
          const line = document.createElement('div');
          line.className = 'zw-box-phone';
          line.append(`${th.dataset.zwLabel}: `);
          const cost = cell.querySelector('.zw-cost');
          if (cost) {
            // 'Cost: $1.647 per 1,000 q · List price': the amount with its unit, then its label, each kept whole, so the
            // line wraps only between them and only where they do not fit.
            const amount = document.createElement('span');
            amount.className = 'zw-nowrap';
            amount.append(...[...(cost.querySelector('.zw-cost-num')?.childNodes ?? [])].map(node => node.cloneNode(true)));
            if (th.dataset.zwUnit) amount.insertAdjacentHTML('beforeend', ` ${th.dataset.zwUnit}`);
            line.append(amount);
            const label = cost.querySelector(':scope > .zw-calc, :scope > .zw-calc-key, :scope > .zw-cost-label');
            if (label) line.append(' \u00b7 ', label.cloneNode(true));
          } else {
            line.append(...[...cell.childNodes].map(node => node.cloneNode(true)));
            if (th.dataset.zwUnit) line.insertAdjacentHTML('beforeend', ` ${th.dataset.zwUnit}`);
          }
          out.append(line);
        });
        return out.childElementCount ? out : null;
      };
      const hide = () => {
        if (!open) return;
        boxOf(open)?.classList.remove('zw-open');
        open.classList.remove('zw-open');
        lines?.remove();
        lines = null;
        open = null;
        pinned = false;
      };
      // How the open box was opened: 'mouse' (hover or click), 'touch' or 'key'. A touch-opened box closed by a tap on
      // blank space outside, and any box Escape closes (but one a mouse opened with the focus elsewhere), give the focus
      // back to its name, without scrolling (v2.5, logic #6159); a tap on another control keeps that control's focus.
      let how = null;
      const CONTROL = 'a, button, input, select, textarea, summary, label, [tabindex]';
      const focusName = row => {
        const name = row?.querySelector('.zw-name');
        if (!name) return;
        quiet = true;
        name.focus({ preventScroll: true });
        quiet = false;
      };
      const show = (row, pin, by) => {
        if (open !== row) hide();
        const box = boxOf(row);
        if (!box) return;
        if (pin) calcs.close();
        if (open !== row) {
          const cell = row.querySelector('.zw-model') || row.firstElementChild;
          if (box.parentElement !== cell) cell.append(box);
          lines = helperLines(row);
          if (lines) box.prepend(lines);
        }
        open = row;
        pinned = pin;
        how = by;
        row.classList.add('zw-open');
        box.classList.add('zw-open');
        place();
      };
      const toggle = (row, by) => { if (open === row && pinned) hide(); else show(row, true, by); };
      document.addEventListener('pointerdown', event => { pointer = event.pointerType || 'mouse'; pointing = true; }, true);
      const released = () => setTimeout(() => { pointing = false; });
      document.addEventListener('pointerup', released, true);
      document.addEventListener('pointercancel', released, true);
      // The rows of a part of the block (all of it at start, a panel when it loads) get their listeners.
      const adopt = scope => scope.querySelectorAll('[data-zw-box]').forEach(row => {
        if (row.dataset.zwAdopted) return;
        row.dataset.zwAdopted = '';
        row.addEventListener('pointerenter', event => {
          if (event.pointerType === 'mouse' && !pinned && !held() && !calcs.isOpen()) show(row, false, 'mouse');
        });
        row.addEventListener('pointerleave', event => {
          if (event.pointerType === 'mouse' && !pinned && open === row && !held()) hide();
        });
        row.addEventListener('focusin', () => {
          keyed = !pointing;
          if (keyed && open !== row && !quiet) show(row, false, 'key');
        });
        row.addEventListener('focusout', event => {
          if (open === row && !pinned && !row.contains(event.relatedTarget)) hide();
        });
        row.addEventListener('click', event => {
          const box = boxOf(row);
          // the box's links, a cost label
          if (box?.contains(event.target) || event.target.closest('.zw-calc, .zw-calc-key')) return;
          const control = event.target.closest('a, button, input, select, textarea, summary, label');
          if (control) {
            if (control.tagName !== 'A' || pointer === 'mouse' || event.detail === 0) return;  // mouse or keyboard: the link
            event.preventDefault();  // a tap on the name opens the box in place of its link
          }
          toggle(row, pointer === 'mouse' ? 'mouse' : 'touch');
        });
      });
      adopt(host);
      // WebKit (Safari on iPhone and iPad) sends a click for a tap on a plain element only when something below <body>
      // listens for clicks (logic #5525): the page's <main> gets an empty listener, so a tap outside the row closes it.
      host.closest('main')?.addEventListener('click', () => {});
      document.addEventListener('click', event => {
        // A click on a cost label's open calculation, which floats outside the row, keeps the box.
        if (!open || open.contains(event.target) || event.target.closest('.zw-calc-body')) return;
        const row = open, back = how === 'touch' && !event.target.closest(CONTROL);
        hide();
        if (back) focusName(row);
      });
      document.addEventListener('focusin', event => { if (open && pinned && !open.contains(event.target)) hide(); });
      document.addEventListener('keydown', event => {  // site.js leaderboardDetails
        if (event.key !== 'Escape' || !open) return;
        const row = open, back = how !== 'mouse' || open.contains(document.activeElement);
        hide();
        if (back) focusName(row);
      });
      addEventListener('scroll', place, { passive: true });
      addEventListener('resize', place);
      document.addEventListener('zw-change', () => {  // a row the new view hides takes its box with it (site.js:289)
        // (A closed sub-row shows in a list's flat view: zw-flat-on.)
        const closed = open && open.classList.contains('zw-sub-closed') && !open.closest('.zw-flat-on');
        if (open && (open.closest('.zw-away') || open.classList.contains('zw-cut') || closed)) hide();
      });
      // A row's sub-rows closing take an open box of theirs with them.
      document.addEventListener('click', event => {
        if (open && event.target.closest('.zw-more') && open.classList.contains('zw-sub-closed')) hide();
      });
      return { hide, adopt };
    })();

    /* --- tips: a head's explanation (Tier: what a tier is) opens by hover and keyboard focus (zw-ui.css) and by a tap or
       Enter on its key; a second tap, a tap outside or Escape closes it (Escape also while it shows by hover or focus).
       A second tap or click closes it for good while the pointer stays, quiet as after Escape, so a touch screen's
       lingering hover and the key's focus do not keep it showing (toolbench #6777, Zeki #6785); opening lifts the quiet,
       and the pointer or the focus leaving lifts it too, so hover and keyboard focus work as before. */
    host.addEventListener('click', event => {
      const key = event.target.closest('.zw-tip-key');
      if (!key) return;
      const opening = key.getAttribute('aria-expanded') !== 'true';
      key.setAttribute('aria-expanded', String(opening));
      key.closest('.zw-tip').toggleAttribute('data-zw-quiet', !opening);
    });
    host.addEventListener('pointerout', event => {
      const tip = event.target.closest?.('.zw-tip');
      if (tip && !tip.contains(event.relatedTarget)) tip.removeAttribute('data-zw-quiet');
    });
    host.addEventListener('focusout', event => event.target.closest?.('.zw-tip')?.removeAttribute('data-zw-quiet'));
    document.addEventListener('click', event => host.querySelectorAll('.zw-tip-key[aria-expanded="true"]').forEach(key => {
      if (!key.closest('.zw-tip').contains(event.target)) key.setAttribute('aria-expanded', 'false');
    }));
    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape') return;
      host.querySelectorAll('.zw-tip').forEach(tip => {
        const key = tip.querySelector('.zw-tip-key');
        if (key.getAttribute('aria-expanded') === 'true' || tip.matches(':hover') || key.matches(':focus-visible')) {
          key.setAttribute('aria-expanded', 'false');
          tip.setAttribute('data-zw-quiet', '');
        }
      });
    });

    /* --- wide tables (v2.6): a table with more than two helpers (zw_ui compact_table: .zw-wide around it) wider than
       its box, as Grading's every measure on a tablet, scrolls inside its box, never the page (zw-scrolls), with a shade
       at the right edge while more of it lies to the right (zw-wide-more); it fits again, nothing scrolls, once the box is
       wide enough. A hidden view or panel measures on its first show (ResizeObserver). --------------------------- */
    const wides = (() => {
      const fit = wide => {
        const box = wide.firstElementChild;
        const scrolls = box.scrollWidth > box.clientWidth + 1;
        wide.classList.toggle('zw-scrolls', scrolls);
        wide.classList.toggle('zw-wide-more', scrolls && box.scrollLeft + box.clientWidth < box.scrollWidth - 1);
      };
      // The box's size changes with the window and the table's with its rows and the fonts: either refits.
      const watch = 'ResizeObserver' in window ? new ResizeObserver(entries => entries.forEach(entry => fit(entry.target.closest('.zw-wide')))) : null;
      const adopt = scope => scope.querySelectorAll('.zw-wide').forEach(wide => {
        if (wide.dataset.zwAdopted !== undefined) return;
        wide.dataset.zwAdopted = '';
        wide.firstElementChild.addEventListener('scroll', () => fit(wide), { passive: true });
        if (watch) [wide, wide.querySelector('table')].forEach(node => watch.observe(node));
        else fit(wide);
      });
      if (!watch) addEventListener('resize', () => host.querySelectorAll('.zw-wide').forEach(fit));
      adopt(host);
      return { adopt };
    })();

    /* --- panels: a panel outside the default view (section.zw-panel[data-zw-src]: zw_ui.Fragments wrote it as a stub
       with its head and keys) is fetched from its fragment file the first time it shows (a key, the address on load, a
       fragment such as #cost), and its body goes in as written, with the boxes and calculations its rows refer to that
       the page lacks; aria-busy while it loads; if it fails, a short line with a reload link and the panel's own page.
       Then the filters, ranks, Top N, Details, cost labels and legends apply to it as to the rest; the keys above it do
       not move. ---------------------------------------------------------------------------------------------------- */
    const panels = (() => {
      const fetchPanel = async panel => {
        const body = panel.querySelector(':scope > .zw-lazy-body');
        panel.setAttribute('aria-busy', 'true');
        body?.classList.add('zw-loading');
        try {
          const response = await fetch(new URL(panel.dataset.zwSrc, window.location.href));
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
          const loaded = doc.querySelector('.zw-panel');
          if (!loaded || !body) throw new Error('no panel in the fragment');
          [['zw-boxes', 'zw-box'], ['zw-calcs', 'zw-calc-body']].forEach(([home, item]) => {
            let into = host.querySelector(`:scope > .${home}`);
            doc.querySelectorAll(`.${home} > .${item}`).forEach(node => {
              if (document.getElementById(node.id)) return;
              if (!into) {
                into = document.createElement('div');
                into.className = home;
                host.append(into);
              }
              into.append(document.importNode(node, true));
            });
          });
          body.replaceWith(...[...loaded.children].filter(child => !child.classList.contains('zw-panel-head'))
            .map(child => document.importNode(child, true)));
          panel.removeAttribute('data-zw-src');
          // A link the panel page pointed at the main page (zw_ui Fragments: data-zw-href) gets its own address back.
          host.querySelectorAll('a[data-zw-href]').forEach(a => { a.setAttribute('href', a.dataset.zwHref); a.removeAttribute('data-zw-href'); });
          panel.classList.remove('zw-lazy');
          panel.removeAttribute('aria-busy');
          details.adopt(panel);
          calcs.prep(panel);
          wides.adopt(panel);
          apply(false);
          const target = document.getElementById(decodeURIComponent(window.location.hash.slice(1)));
          if (target && panel.contains(target)) target.scrollIntoView();
        } catch (error) {
          panel.removeAttribute('aria-busy');
          panel.dataset.zwFailed = '';
          body?.classList.remove('zw-loading');
          body?.querySelector('.zw-lazy-failed')?.removeAttribute('hidden');
        }
      };
      const load = () => host.querySelectorAll('.zw-panel[data-zw-src]:not(.zw-away):not([aria-busy]):not([data-zw-failed])')
        .forEach(panel => { fetchPanel(panel); });
      return { load };
    })();

    /* --- a view set from outside: the page's own script (zwUi.set({ measure: 'cost' })), or a fragment the block
       answers to (data-zw-anchors, zw_ui Bench.anchors: '#cost' → the Cost panel), on load and on a later change of the
       fragment alike; a value no key offers is left alone. --------------------------------------------------------------- */
    const setView = values => Object.entries(values || {}).forEach(([name, value]) => {
      if (!params[name]) return;
      if (name === 'top') { state.top = value === 'all' ? 'all' : firstTop; return; }
      if (offered(name, value)) state[name] = String(value);
    });
    let anchors = {};
    try { anchors = JSON.parse(host.dataset.zwAnchors || '{}'); } catch (e) { anchors = {}; }
    const anchored = () => anchors[decodeURIComponent(window.location.hash.slice(1))];
    setView(anchored());
    // The address changed under the page: Back or Forward (popstate, which a same-document traversal fires without a
    // hashchange when the query differs too), a typed or followed fragment (hashchange). The state follows it as on a
    // fresh load: the address's values, then the fragment's (Bench.anchors). Each block reads its own parameters.
    const follow = () => {
      const before = JSON.stringify(state);
      fromAddress();
      setView(anchored());
      if (JSON.stringify(state) === before) return false;
      apply(true);
      return true;
    };
    addEventListener('popstate', follow);
    addEventListener('hashchange', () => {
      follow();
      if (!anchored()) return;
      // Where the fragment names no element of its own, the panel it opened comes into view.
      if (!document.getElementById(decodeURIComponent(window.location.hash.slice(1)))) {
        host.querySelector('.zw-panel:not(.zw-away)')?.scrollIntoView();
      }
    });

    apply(true);  // a pasted or kept link's defaults leave the address
    return { state: () => ({ ...state }), set: values => { setView(values); apply(true); } };
  }
})();
