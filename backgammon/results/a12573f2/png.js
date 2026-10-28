'use strict';

/* PNG exports (Can, 23 Oct 2026): what the page shows, as images that make sense away from the site, to a model too.
   - Every table: "Download PNG" under it. The table as shown (tab, filters, sort, theme) with every column, also those the
     page scrolls sideways, and every row, also those its box scrolls; above it the page and section headings, under it
     the notes that follow it on the page, then in small type the chart convention (B6.5): league, margin where the table
     has one, rows shown and the decisions behind them, filters and sort, results version, theme and address.
   - TEMPORARY (pages.EXPORT_PAGE_PNG): "Export page as PNG" in the top bar: the whole page as shown, its scrolling boxes
     opened to their full height, in parts of at most 16,000 pixels.
   No library: the page is read box by box (background, borders, rounding, inset rules) and line by line (each line of
   text where the browser placed it, in its font and colour); SVG charts and images are drawn as images. Pages add
   their filters through window.pngView() ({ league, filters }) when they have any (bg.js, decisions.js). */

(function png() {
  const LIMIT = 16000;
  const PAD = 16;

  /* --- Reading the page: a list of drawing steps, taken in one go so the page never shows a changed layout. --- */

  const clear = c => !c || c === 'transparent' || /^rgba\(.*,\s*0\)$/.test(c) || /\/\s*0\)$/.test(c);
  const px = v => parseFloat(v) || 0;

  function splitTop(s) {
    const out = [];
    let depth = 0, from = 0;
    for (let i = 0; i < s.length; i++) {
      if (s[i] === '(') depth++;
      else if (s[i] === ')') depth--;
      else if (s[i] === ',' && !depth) { out.push(s.slice(from, i).trim()); from = i + 1; }
    }
    out.push(s.slice(from).trim());
    return out;
  }

  /* The first linear gradient of a background-image: { angle, stops: [[colour, 0..1 or null]] }; a repeating one is
     drawn in its first colour. */
  function gradient(value) {
    const m = value.match(/(repeating-)?linear-gradient\(/);
    if (!m) return null;
    let i = m.index + m[0].length, depth = 0;
    const start = i;
    for (; i < value.length; i++) {
      if (value[i] === '(') depth++;
      else if (value[i] === ')') { if (!depth) break; depth--; }
    }
    const parts = splitTop(value.slice(start, i));
    const SIDES = { 'to top': 0, 'to right': 90, 'to bottom': 180, 'to left': 270 };
    let angle = 180;
    if (parts[0] in SIDES) angle = SIDES[parts.shift()];
    else if (/^-?[\d.]+deg$/.test(parts[0])) angle = parseFloat(parts.shift());
    else if (/^-?[\d.]+turn$/.test(parts[0])) angle = 360 * parseFloat(parts.shift());
    else if (/^to /.test(parts[0])) parts.shift();
    const stops = parts.map(p => {
      const s = p.match(/^(.*?\)|[#\w-]+)(?:\s+(-?[\d.]+)%)?/);
      return s ? [s[1], s[2] === undefined ? null : Number(s[2]) / 100] : null;
    }).filter(Boolean);
    if (!stops.length) return null;
    const rad = angle * Math.PI / 180;
    if (m[1]) return { angle: rad, stops: [[stops[0][0], 0], [stops[0][0], 1]] };
    stops.forEach((s, k) => { if (s[1] === null) s[1] = stops.length === 1 ? 0 : k / (stops.length - 1); });
    return { angle: rad, stops };
  }

  const ALIGN = { right: 'right', end: 'right', '-webkit-right': 'right', center: 'center', '-webkit-center': 'center' };
  const SVG_PROPS = ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity',
    'fill-opacity', 'stroke-opacity', 'font-family', 'font-size', 'font-weight', 'font-style', 'text-anchor',
    'dominant-baseline', 'display', 'visibility', 'paint-order', 'letter-spacing'];

  function fontOf(cs) {
    return `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
  }

  function transform(text, cs) {
    if (cs.textTransform === 'uppercase') return text.toUpperCase();
    if (cs.textTransform === 'lowercase') return text.toLowerCase();
    if (cs.textTransform === 'capitalize') return text.replace(/(^|\s)(\S)/g, (_, a, b) => a + b.toUpperCase());
    return text;
  }

  /* Steps for an element and everything in it, in viewport coordinates. */
  function read(root) {
    const ops = [];
    const range = document.createRange();
    const rectOf = (node, a, b) => { range.setStart(node, a); range.setEnd(node, b); return range.getBoundingClientRect(); };

    function box(el, cs, st) {
      if (cs.visibility === 'hidden') return;
      const rects = cs.display === 'inline' ? [...el.getClientRects()] : [el.getBoundingClientRect()];
      for (const r of rects) {
        if (r.width <= 0 || r.height <= 0) continue;
        const rr = cs.borderTopLeftRadius;
        const rad = Math.min(rr.endsWith('%') ? px(rr) / 100 * Math.min(r.width, r.height) : px(rr), r.width / 2, r.height / 2);
        const at = { x: r.left, y: r.top, w: r.width, h: r.height, rad, clip: st.clip, alpha: st.alpha };
        if (!clear(cs.backgroundColor)) ops.push({ k: 'box', fill: cs.backgroundColor, ...at });
        if (cs.backgroundImage !== 'none') {
          const g = gradient(cs.backgroundImage);
          if (g) ops.push({ k: 'grad', g, ...at });
        }
        if (cs.boxShadow !== 'none') {
          splitTop(cs.boxShadow).filter(s => /\binset\b/.test(s)).forEach(s => {
            const colour = (s.match(/(rgba?\([^)]*\)|color\([^)]*\)|#[0-9a-f]+)/i) || [])[1];
            const [ox = 0, oy = 0, blur = 0, spread = 0] = (s.replace(/(rgba?|color)\([^)]*\)/g, '').match(/-?[\d.]+px/g) || []).map(px);
            if (!colour || clear(colour) || blur) return;
            const strip = (x, y, w, h) => ops.push({ k: 'box', fill: colour, x, y, w, h, rad: 0, clip: st.clip, alpha: st.alpha });
            if (ox > 0) strip(r.left, r.top, ox, r.height);
            if (ox < 0) strip(r.right + ox, r.top, -ox, r.height);
            if (oy > 0) strip(r.left, r.top, r.width, oy);
            if (oy < 0) strip(r.left, r.bottom + oy, r.width, -oy);
            if (!ox && !oy && spread > 0) ops.push({ k: 'ring', colour, lw: spread, ...at, x: r.left + spread / 2, y: r.top + spread / 2, w: r.width - spread, h: r.height - spread });
          });
        }
        const sides = ['Top', 'Right', 'Bottom', 'Left'].map(s => ({
          w: cs[`border${s}Style`] === 'none' || cs[`border${s}Style`] === 'hidden' ? 0 : px(cs[`border${s}Width`]),
          c: cs[`border${s}Color`],
        }));
        const same = sides.every(s => s.w === sides[0].w && s.c === sides[0].c);
        if (rad > 0 && same && sides[0].w > 0 && !clear(sides[0].c)) {
          const lw = sides[0].w;
          ops.push({ k: 'ring', colour: sides[0].c, lw, ...at, x: r.left + lw / 2, y: r.top + lw / 2, w: r.width - lw, h: r.height - lw, rad: Math.max(0, rad - lw / 2) });
        } else {
          const [t, rt, b, l] = sides;
          const strip = (s, x, y, w, h) => { if (s.w > 0 && !clear(s.c)) ops.push({ k: 'box', fill: s.c, x, y, w, h, rad: 0, clip: st.clip, alpha: st.alpha }); };
          strip(t, r.left, r.top, r.width, t.w);
          strip(b, r.left, r.bottom - b.w, r.width, b.w);
          strip(l, r.left, r.top, l.w, r.height);
          strip(rt, r.right - rt.w, r.top, rt.w, r.height);
        }
      }
    }

    function text(node, cs, st) {
      const data = node.data;
      const first = data.search(/\S/);
      if (first < 0 || cs.visibility === 'hidden') return;
      const end = data.trimEnd().length;
      range.setStart(node, first);
      range.setEnd(node, end);
      const lines = [...range.getClientRects()].filter(r => r.width > 0 && r.height > 0);
      if (!lines.length) return;
      // Where each line starts: the first character whose box sits on that line (a binary search per line break).
      const starts = [first];
      const topAt = k => {
        for (let j = k; j < end; j++) {
          const r = rectOf(node, j, j + 1);
          if (r.width > 0 || r.height > 0) return r.top;
        }
        return Infinity;
      };
      // Line boxes may overlap when the line height is tight, so a line is told by its top, half-way to the next one.
      let prev = lines[0].top;
      for (let i = 1; i < lines.length; i++) {
        if (lines[i].top <= prev + 1) continue;
        const cut = (prev + lines[i].top) / 2;
        prev = lines[i].top;
        let lo = starts[starts.length - 1] + 1, hi = end;
        while (lo < hi) {
          const mid = (lo + hi) >> 1;
          if (topAt(mid) > cut) hi = mid; else lo = mid + 1;
        }
        if (lo < end && lo > starts[starts.length - 1]) starts.push(lo);
      }
      starts.push(end);
      const pre = /^(pre|pre-wrap|break-spaces)$/.test(cs.whiteSpace);
      const align = ALIGN[cs.textAlign] || 'left';
      const font = fontOf(cs);
      for (let i = 0; i + 1 < starts.length; i++) {
        const seg = data.slice(starts[i], starts[i + 1]);
        const lead = seg.search(/\S/);
        if (lead < 0) continue;
        const a = starts[i] + lead, z = starts[i] + seg.trimEnd().length;
        const r0 = rectOf(node, a, a + 1), r1 = rectOf(node, z - 1, z);
        let s = data.slice(a, z);
        s = pre ? s.replace(/\t/g, '    ') : s.replace(/\s+/g, ' ');
        ops.push({ k: 'text', text: transform(s, cs), x0: r0.left, x1: Math.max(r1.right, r0.right), top: r0.top, h: r0.height,
          font, colour: cs.color, align, ls: cs.letterSpacing, under: st.under, clip: st.clip, alpha: st.alpha });
      }
    }

    function pseudo(el, cs, which, st) {
      const ps = getComputedStyle(el, which);
      const m = ps.content && ps.content.match(/^"((?:[^"\\]|\\.)*)"$/);
      if (!m || !m[1].trim() || ps.display === 'none' || /absolute|fixed/.test(ps.position) || ps.visibility === 'hidden') return;
      range.selectNodeContents(el);
      const rects = [...range.getClientRects()].filter(r => r.width > 0 && r.height > 0);
      const r = el.getBoundingClientRect();
      const ref = which === '::after' ? rects[rects.length - 1] : rects[0];
      const x = which === '::after' ? (ref ? ref.right : r.right - px(cs.paddingRight)) : r.left + px(cs.borderLeftWidth) + px(cs.paddingLeft);
      ops.push({ k: 'text', text: transform(m[1].replace(/\\(.)/g, '$1'), ps), x0: x, x1: null, top: ref ? ref.top : r.top,
        h: ref ? ref.height : r.height, font: fontOf(ps), colour: ps.color, align: 'left', ls: ps.letterSpacing, under: null,
        clip: st.clip, alpha: st.alpha });
    }

    function control(el, cs, st) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height || cs.visibility === 'hidden') return;
      const type = (el.type || '').toLowerCase();
      if (type === 'checkbox' || type === 'radio') {
        const s = Math.min(r.width, r.height);
        ops.push({ k: 'ring', colour: cs.color, lw: 1, x: r.left + .5, y: r.top + .5, w: s - 1, h: s - 1, rad: type === 'radio' ? s / 2 : 3, clip: st.clip, alpha: st.alpha });
        if (el.checked) ops.push({ k: 'box', fill: cs.accentColor === 'auto' ? cs.color : cs.accentColor, x: r.left + 3, y: r.top + 3, w: s - 6, h: s - 6, rad: type === 'radio' ? s / 2 : 2, clip: st.clip, alpha: st.alpha });
        return;
      }
      const value = el.tagName === 'SELECT' ? (el.selectedOptions[0]?.text || '') : (el.value || el.placeholder || '');
      if (!value) return;
      const left = r.left + px(cs.borderLeftWidth) + px(cs.paddingLeft);
      const size = px(cs.fontSize);
      const right = r.right - px(cs.borderRightWidth) - px(cs.paddingRight) - (el.tagName === 'SELECT' ? size : 0);
      ops.push({ k: 'text', text: value.replace(/\s+/g, ' ').trim(), x0: left, x1: right, top: r.top + (r.height - size * 1.2) / 2,
        h: size * 1.2, font: fontOf(cs), colour: cs.color, align: 'left', ls: cs.letterSpacing, under: null,
        clip: { x1: left, y1: r.top, x2: right, y2: r.bottom }, alpha: st.alpha, fit: false });
      if (el.tagName === 'SELECT') {
        ops.push({ k: 'text', text: '\u25BE', x0: right + size * .2, x1: null, top: r.top + (r.height - size * 1.2) / 2, h: size * 1.2,
          font: fontOf(cs), colour: cs.color, align: 'left', ls: 'normal', under: null, clip: st.clip, alpha: st.alpha });
      }
    }

    function svg(el, cs, st) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height || cs.visibility === 'hidden') return;
      const clone = el.cloneNode(true);
      const from = [el, ...el.querySelectorAll('*')];
      [clone, ...clone.querySelectorAll('*')].forEach((c, i) => {
        const s = getComputedStyle(from[i]);
        SVG_PROPS.forEach(p => c.style.setProperty(p, s.getPropertyValue(p)));
      });
      clone.setAttribute('width', r.width);
      clone.setAttribute('height', r.height);
      clone.style.setProperty('display', 'block');
      ops.push({ k: 'svg', markup: new XMLSerializer().serializeToString(clone), x: r.left, y: r.top, w: r.width, h: r.height,
        clip: st.clip, alpha: st.alpha });
    }

    function walk(el, st) {
      const cs = getComputedStyle(el);
      if (cs.display === 'none') return;
      const alpha = st.alpha * px(cs.opacity === '' ? '1' : cs.opacity);
      if (alpha <= 0) return;
      st = { ...st, alpha };
      box(el, cs, st);
      const tag = el.tagName;
      if (tag === 'svg') { svg(el, cs, st); return; }
      if (tag === 'IMG' || tag === 'CANVAS') {
        const r = el.getBoundingClientRect();
        const ok = tag === 'CANVAS' || (el.complete && el.naturalWidth && new URL(el.currentSrc || el.src, location.href).origin === location.origin);
        if (ok && r.width && r.height && cs.visibility !== 'hidden') ops.push({ k: 'img', el, x: r.left, y: r.top, w: r.width, h: r.height, clip: st.clip, alpha });
        return;
      }
      if (tag === 'SELECT' || tag === 'INPUT' || tag === 'TEXTAREA') { control(el, cs, st); return; }
      if (/^(SCRIPT|STYLE|TEMPLATE|NOSCRIPT|OPTION)$/.test(tag)) return;
      if (/underline/.test(cs.textDecorationLine)) st = { ...st, under: clear(cs.textDecorationColor) ? cs.color : cs.textDecorationColor };
      if (el !== root && (cs.overflowX !== 'visible' || cs.overflowY !== 'visible')) {
        const r = el.getBoundingClientRect();
        const c = { x1: r.left + px(cs.borderLeftWidth), y1: r.top + px(cs.borderTopWidth), x2: r.right - px(cs.borderRightWidth), y2: r.bottom - px(cs.borderBottomWidth) };
        st = { ...st, clip: st.clip ? { x1: Math.max(c.x1, st.clip.x1), y1: Math.max(c.y1, st.clip.y1), x2: Math.min(c.x2, st.clip.x2), y2: Math.min(c.y2, st.clip.y2) } : c };
        if (st.clip.x2 <= st.clip.x1 || st.clip.y2 <= st.clip.y1) return;
      }
      pseudo(el, cs, '::before', st);
      const kids = tag === 'DETAILS' && !el.open ? [el.querySelector(':scope > summary')].filter(Boolean) : el.childNodes;
      for (const n of kids) {
        if (n.nodeType === Node.ELEMENT_NODE) walk(n, st);
        else if (n.nodeType === Node.TEXT_NODE) text(n, cs, st);
      }
      pseudo(el, cs, '::after', st);
    }

    walk(root, { clip: null, alpha: 1, under: null });
    range.detach();
    return ops;
  }

  /* --- Drawing --- */

  async function images(ops) {
    await Promise.all(ops.filter(o => o.k === 'svg').map(o => new Promise(resolve => {
      const url = URL.createObjectURL(new Blob([o.markup], { type: 'image/svg+xml' }));
      const img = new Image();
      img.onload = () => { o.img = img; resolve(); };
      img.onerror = () => resolve();
      img.src = url;
      o.url = url;
    })));
  }

  function draw(ctx, ops, dx, dy) {
    for (const o of ops) {
      ctx.save();
      ctx.globalAlpha = o.alpha;
      if (o.clip) {
        ctx.beginPath();
        ctx.rect(o.clip.x1 + dx, o.clip.y1 + dy, o.clip.x2 - o.clip.x1, o.clip.y2 - o.clip.y1);
        ctx.clip();
      }
      if (o.k === 'box' || o.k === 'grad') {
        if (o.k === 'box') ctx.fillStyle = o.fill;
        else {
          const cx = o.x + dx + o.w / 2, cy = o.y + dy + o.h / 2, sx = Math.sin(o.g.angle), sy = -Math.cos(o.g.angle);
          const half = (Math.abs(o.w * sx) + Math.abs(o.h * sy)) / 2;
          const g = ctx.createLinearGradient(cx - sx * half, cy - sy * half, cx + sx * half, cy + sy * half);
          try { o.g.stops.forEach(([c, p]) => g.addColorStop(Math.min(1, Math.max(0, p)), c)); } catch (e) { ctx.restore(); continue; }
          ctx.fillStyle = g;
        }
        ctx.beginPath();
        if (o.rad > 0) ctx.roundRect(o.x + dx, o.y + dy, o.w, o.h, o.rad); else ctx.rect(o.x + dx, o.y + dy, o.w, o.h);
        ctx.fill();
      } else if (o.k === 'ring') {
        ctx.strokeStyle = o.colour;
        ctx.lineWidth = o.lw;
        ctx.beginPath();
        if (o.rad > 0) ctx.roundRect(o.x + dx, o.y + dy, o.w, o.h, o.rad); else ctx.rect(o.x + dx, o.y + dy, o.w, o.h);
        ctx.stroke();
      } else if (o.k === 'text') {
        ctx.font = o.font;
        ctx.letterSpacing = o.ls === 'normal' ? '0px' : o.ls;
        ctx.fillStyle = o.colour;
        const m = ctx.measureText(o.text);
        const asc = m.fontBoundingBoxAscent, desc = m.fontBoundingBoxDescent;
        const base = o.top + dy + (o.h - asc - desc) / 2 + asc;
        const room = o.x1 === null ? Infinity : o.x1 - o.x0;
        let x = o.x0 + dx, w = m.width;
        if (w > room + 1 && o.fit !== false) w = room + 1;
        else if (Math.abs(w - room) > 1 && room !== Infinity) {
          if (o.align === 'right') x = o.x1 + dx - w;
          else if (o.align === 'center') x = o.x0 + dx + (room - w) / 2;
        }
        ctx.textAlign = 'left';
        ctx.textBaseline = 'alphabetic';
        if (w < m.width) ctx.fillText(o.text, x, base, w); else ctx.fillText(o.text, x, base);
        if (o.under) {
          ctx.fillStyle = o.under;
          ctx.fillRect(x, base + Math.max(1, desc * .35), w, Math.max(1, Math.round(asc / 14)));
        }
      } else if (o.k === 'svg' || o.k === 'img') {
        const img = o.k === 'svg' ? o.img : o.el;
        if (img) ctx.drawImage(img, o.x + dx, o.y + dy, o.w, o.h);
      }
      ctx.restore();
    }
  }

  function wrapLines(ctx, text, width) {
    const out = [];
    let line = '';
    for (const word of text.split(/\s+/).filter(Boolean)) {
      const next = line ? `${line} ${word}` : word;
      if (line && ctx.measureText(next).width > width) { out.push(line); line = word; } else line = next;
    }
    if (line) out.push(line);
    return out;
  }

  /* One image (or several, split at LIMIT pixels): a heading, the region read from the page, notes, then the small-type
     lines. Every block is optional. */
  async function compose({ ops, region, bg, head = [], notes = [], foot = [], pad = PAD, scale = 2, minWidth = 560 }) {
    const root = getComputedStyle(document.documentElement);
    const colour = { text: root.getPropertyValue('--text').trim(), text2: root.getPropertyValue('--text-2').trim(), edge: root.getPropertyValue('--edge').trim() };
    const sans = getComputedStyle(document.body).fontFamily;
    const width = Math.ceil(Math.max(region.w + 2 * pad, minWidth));
    const measure = document.createElement('canvas').getContext('2d');
    const block = (lines, font, size, step, colourOf) => {
      measure.font = `${font} ${size}px ${sans}`;
      const rows = lines.flatMap(l => wrapLines(measure, l, width - 2 * PAD));
      return { rows, font: `${font} ${size}px ${sans}`, step, colour: colourOf, height: rows.length * step };
    };
    const blocks = { head: block(head, '700', 15, 21, colour.text), notes: block(notes, '400', 12.5, 18, colour.text2), foot: block(foot, '400', 11.5, 16, colour.text2) };
    const headH = blocks.head.rows.length ? PAD + blocks.head.height + 6 : pad;
    const notesH = blocks.notes.rows.length ? 10 + blocks.notes.height : 0;
    const footH = blocks.foot.rows.length ? 14 + blocks.foot.height + PAD : pad;
    const height = Math.ceil(headH + region.h + notesH + footH);
    scale = Math.min(scale, 32000 / width);
    await images(ops);
    const slice = Math.floor(Math.min(LIMIT, 2e8 / (width * scale)) / scale);
    const parts = Math.max(1, Math.ceil(height / slice));
    const canvases = [];
    for (let p = 0; p < parts; p++) {
      const top = p * slice, h = Math.min(slice, height - top);
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(width * scale);
      canvas.height = Math.round(h * scale);
      const ctx = canvas.getContext('2d');
      ctx.scale(scale, scale);
      ctx.translate(0, -top);
      ctx.fillStyle = bg;
      ctx.fillRect(0, top, width, h);
      const text = (b, y) => {
        ctx.font = b.font;
        ctx.fillStyle = b.colour;
        ctx.textBaseline = 'alphabetic';
        b.rows.forEach((row, i) => ctx.fillText(row, PAD, y + (i + 1) * b.step - b.step * .3));
      };
      if (blocks.head.rows.length) text(blocks.head, PAD - 2);
      draw(ctx, ops, pad - region.x, headH - region.y);
      let y = headH + region.h;
      if (blocks.notes.rows.length) { text(blocks.notes, y + 6); y += notesH; }
      if (blocks.foot.rows.length) {
        ctx.fillStyle = colour.edge;
        ctx.fillRect(PAD, y + 7, width - 2 * PAD, 1);
        text(blocks.foot, y + 12);
      }
      canvases.push(canvas);
    }
    ops.forEach(o => o.url && URL.revokeObjectURL(o.url));
    return canvases;
  }

  async function save(canvases, name) {
    for (let i = 0; i < canvases.length; i++) {
      const blob = await new Promise(resolve => canvases[i].toBlob(resolve, 'image/png'));
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = canvases.length > 1 ? `${name}-part-${i + 1}-of-${canvases.length}.png` : `${name}.png`;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
      if (i + 1 < canvases.length) await new Promise(resolve => setTimeout(resolve, 400));
    }
  }

  /* --- What the image says about itself --- */

  const slug = s => String(s).toLowerCase().normalize('NFKD').replace(/[^\w.]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60);
  const clean = s => String(s).replace(/\s+/g, ' ').trim();
  const theme = () => (document.documentElement.dataset.theme === 'light' ? 'Light background' : 'Dark background');
  const pageName = () => slug(location.pathname.replace(/^.*?\/backgammon\//, '').replace(/index\.html$/, '')) || 'home';
  const versionLine = () => clean((document.querySelector('.hero .version') || document.querySelector('.footer p:last-child'))?.textContent || '').replace(/\.$/, '');
  const view = () => (typeof window.pngView === 'function' ? window.pngView() : {}) || {};
  const pageTitle = () => clean(document.querySelector('main h1')?.textContent || document.title.replace(/ · Hilde$/, ''));
  /* The site's title and subtitle (pages.TITLE, pages.SUBTITLE), the first header line of every PNG. */
  const siteHead = () => clean(`${document.body.dataset.siteTitle || ''} ${document.body.dataset.siteSubtitle || ''}`);

  function leagueOf(table) {
    const ds = table.closest('[data-league-view]')?.dataset.leagueView || table.dataset.dataset
      || table.querySelector('tbody tr[data-dataset]')?.dataset.dataset
      || (table.closest('[id^="league-"]')?.id.match(/^league-\d+/) || [])[0]
      || (location.pathname.match(/\/models\/([^/]+)\//) || [])[1];
    if (!ds) return view().league || '';
    const pick = document.querySelector(`[data-league-pick="${ds}"]`);
    if (pick) return clean(pick.textContent);
    const m = ds.match(/^league-(\d+)$/);
    return m ? `League ${m[1]}` : ds === 'v1-set' ? 'v1 set' : ds;
  }

  /* The headings the table sits under, outermost first: the nearest heading before it at each level up to its section,
     the selected tab, the summary of a <details> it is in, and a card header (Every decision). */
  function headings(from) {
    const out = [];
    let rank = 7;
    for (let el = from; el && el !== document.body && rank > 2; el = el.parentElement) {
      if (el.getAttribute('role') === 'tabpanel') {
        const tab = document.getElementById(el.getAttribute('aria-labelledby') || '');
        if (tab) out.push(clean(tab.textContent));
      }
      if (el.tagName === 'DETAILS' && el !== from) {
        const s = el.querySelector(':scope > summary');
        if (s) out.push(clean(s.textContent));
      }
      for (let sib = el.previousElementSibling; sib; sib = sib.previousElementSibling) {
        const h = /^H[1-6]$/.test(sib.tagName) ? sib : sib.matches('header, hgroup, .section-head') ? sib.querySelector('h1, h2, h3, h4, h5, h6') : null;
        if (!h) continue;
        const n = Number(h.tagName[1]);
        if (n >= rank || n < 2) continue;
        rank = n;
        const sub = sib.tagName === 'HEADER' && sib.querySelector(':scope > p.small');
        out.push(clean(h.textContent) + (sub ? ` · ${clean(sub.textContent)}` : ''));
        if (n <= 2) break;
      }
    }
    return out.reverse();
  }

  /* The notes printed right after the table (and after the box it sits in, when the table is the box's last thing). */
  function notesAfter(anchor) {
    const out = [];
    for (let el = anchor, up = 0; el && up < 3; el = el.parentElement, up++) {
      let sib = el.nextElementSibling;
      for (; sib && (sib.matches('.table-png') || sib.matches('p.table-note, p.note') || sib.matches('[hidden]')); sib = sib.nextElementSibling) {
        if (sib.matches('p.table-note, p.note') && !sib.hidden) out.push(clean(sib.innerText));
      }
      if (sib) break;
    }
    return out.filter(Boolean);
  }

  function counts(table) {
    const rows = [...table.tBodies].flatMap(b => [...b.rows]);
    const shown = rows.filter(r => r.getClientRects().length);
    const head = table.tHead?.rows[table.tHead.rows.length - 1];
    let decisions = null;
    if (head) {
      const cells = [...head.cells].map(c => clean(c.textContent));
      for (const name of ['Decisions scored', 'Decisions', 'Decisions with a trade-off']) {
        const col = cells.indexOf(name);
        if (col < 0) continue;
        let sum = 0, any = false;
        shown.forEach(r => {
          const cell = r.cells[col];
          const v = cell && parseFloat((cell.firstChild?.textContent || cell.textContent).replace(/[,\s]/g, ''));
          if (Number.isFinite(v)) { sum += v; any = true; }
        });
        if (any) decisions = `${sum.toLocaleString('en')} ${name.toLowerCase()} in these rows`;
        break;
      }
    }
    return { rows: rows.length, shown: shown.length, decisions };
  }

  function sortNote(table) {
    const th = table.querySelector('thead th[aria-sort="ascending"], thead th[aria-sort="descending"]');
    return th ? `sorted by "${clean(th.textContent)}", ${th.getAttribute('aria-sort')}` : "rows in the page's order";
  }

  function anchorOf(el) {
    for (let x = el; x && x !== document.body; x = x.parentElement) {
      for (let s = x; s; s = s.previousElementSibling) if (s.id && /^H[1-6]$/.test(s.tagName)) return s.id;
      if (x.id && x.tagName !== 'MAIN') return x.id;
    }
    return '';
  }

  function backgroundOf(el) {
    for (let x = el; x; x = x.parentElement) {
      const c = getComputedStyle(x).backgroundColor;
      if (!clear(c)) return c;
    }
    return getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() || '#fff';
  }

  /* --- Table PNGs --- */

  async function tablePng(table) {
    const wrap = table.closest('.table-wrap') || table;
    const block = wrap.parentElement?.classList.contains('table-frame') ? wrap.parentElement : wrap;
    table.classList.add('png-capture');
    let ops, region;
    try {
      const rects = [table.getBoundingClientRect(), table.caption?.getBoundingClientRect()].filter(r => r && r.width);
      const x1 = Math.min(...rects.map(r => r.left)), y1 = Math.min(...rects.map(r => r.top));
      region = { x: x1, y: y1, w: Math.max(...rects.map(r => r.right)) - x1, h: Math.max(...rects.map(r => r.bottom)) - y1 };
      ops = read(table);
    } finally {
      table.classList.remove('png-capture');
    }
    const v = view();
    const league = leagueOf(table);
    const margin = table.dataset.margin;
    const c = counts(table);
    const filters = v.filters || [];
    const where = anchorOf(wrap);
    const crumbs = headings(block);
    const head = [siteHead(), [pageTitle(), ...crumbs].filter((s, i, a) => s && s !== document.body.dataset.siteTitle && a.indexOf(s) === i).join(' · ')].filter(Boolean);
    const foot = [
      [league, margin && `margin ${margin}`, `${c.shown === c.rows ? c.shown.toLocaleString('en') : `${c.shown.toLocaleString('en')} of ${c.rows.toLocaleString('en')}`} rows shown`, c.decisions]
        .filter(Boolean).join(' · '),
      `Filters: ${filters.length ? filters.join(' · ') : 'none'} · ${sortNote(table)}`,
      [versionLine(), theme()].filter(Boolean).join(' · '),
      location.origin + location.pathname + location.search + (where ? `#${where}` : ''),
    ];
    const canvases = await compose({ ops, region, bg: backgroundOf(wrap), head, notes: notesAfter(block), foot });
    const what = slug(crumbs.slice(-2).join(' ') || table.caption?.textContent || where || 'table');
    const ds = table.dataset.dataset && !what.startsWith(table.dataset.dataset) ? table.dataset.dataset : '';
    const name = ['backgammon', pageName(), ds, what, margin && slug(margin)].filter(Boolean).join('-');
    await save(canvases, name);
  }

  function addButtons() {
    document.querySelectorAll('.table-wrap:not([data-png])').forEach(wrap => {
      if (!wrap.querySelector('table')) return;
      wrap.dataset.png = '';
      const anchor = wrap.parentElement.classList.contains('table-frame') ? wrap.parentElement : wrap;
      const p = document.createElement('p');
      p.className = 'table-png';
      p.innerHTML = '<button type="button" class="key" data-table-png>Download PNG</button>';
      anchor.after(p);
    });
  }

  document.addEventListener('click', event => {
    const b = event.target.closest('[data-table-png]');
    if (!b) return;
    const anchor = b.closest('.table-png').previousElementSibling;
    const table = anchor && anchor.querySelector('table');
    if (table) run(b, () => tablePng(table));
  });

  async function run(button, job) {
    if (button.getAttribute('aria-busy') === 'true') return;
    button.setAttribute('aria-busy', 'true');
    try {
      await job();
    } catch (error) {
      console.warn('PNG export failed:', error);
    } finally {
      button.removeAttribute('aria-busy');
    }
  }

  addButtons();
  let pending = false;
  new MutationObserver(() => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; addButtons(); });
  }).observe(document.body, { childList: true, subtree: true });

  /* --- TEMPORARY (pages.EXPORT_PAGE_PNG): the whole page --- */

  async function pagePng() {
    const doc = document.documentElement;
    const sx = scrollX, sy = scrollY;
    const wraps = [...document.querySelectorAll('.table-wrap')].map(w => [w, w.scrollLeft]);
    doc.classList.add('png-page');
    let ops, region;
    try {
      // Scroll boxes start at their left edge, so a first column held in view never overlaps the columns drawn after it.
      wraps.forEach(([w]) => { w.scrollLeft = 0; });
      const top = doc.getBoundingClientRect();
      region = { x: top.left, y: top.top, w: doc.clientWidth, h: doc.scrollHeight };
      ops = read(document.body);
    } finally {
      doc.classList.remove('png-page');
      wraps.forEach(([w, left]) => { w.scrollLeft = left; });
      scrollTo(sx, sy);
    }
    const filters = view().filters || [];
    const foot = [
      `${pageTitle()} · the page as shown at ${doc.clientWidth} px wide · ${theme()}`,
      `Filters: ${filters.length ? filters.join(' · ') : 'none'}`,
      versionLine(),
      location.href,
    ];
    const bg = backgroundOf(document.body);
    const canvases = await compose({ ops, region, bg, head: [siteHead()].filter(Boolean), foot, pad: 0, minWidth: 0, scale: doc.clientWidth <= 800 ? 2 : 1.5 });
    await save(canvases, `backgammon-page-${pageName()}-${theme().split(' ')[0].toLowerCase()}-${doc.clientWidth}px`);
  }

  const pageButton = document.querySelector('[data-page-png]');
  if (pageButton) {
    pageButton.hidden = false;
    pageButton.addEventListener('click', () => run(pageButton, pagePng));
  }
})();
