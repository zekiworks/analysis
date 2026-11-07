/* The logic & math site's script: the view bar's group (after tb-next site.js setupViewBar), the cost unit (tb-next
   setupCostUnit), the Dark / Light switch (tb-next setupTheme, unchanged) and the question index's filters. Every page
   works without it (the Decision copy of each part shows, costs read per 1,000 questions). */

/* The view bar's group from ?models= (all, decision or chat; missing or unknown means decision, the default). Each
   element whose data-models lists other groups only is hidden; the group's key is marked; the test and measure keys
   (data-keep-group) keep the group and open the top of their page. Any key that looks active opens Home in its
   default state (the bar's data-home). --view-bar-h holds the sticky header's height. */
(function setupViewBar() {
  const asked = (new URLSearchParams(window.location.search).get('models') ?? '').replace(/[^a-z]+$/i, '');
  const group = ['all', 'decision', 'chat'].includes(asked) ? asked : 'decision';
  document.documentElement.dataset.modelsView = group;
  document.querySelectorAll('[data-models]').forEach(element => {
    element.hidden = !element.dataset.models.split(/\s+/).includes(group);
  });
  const bar = document.querySelector('.vbar');
  if (!bar) return;
  bar.querySelectorAll('a[data-view-group]').forEach(link => {
    if (link.dataset.viewGroup === group) link.setAttribute('aria-current', 'true');
    else link.removeAttribute('aria-current');
  });
  document.querySelectorAll('a[data-keep-group]').forEach(link => {
    const [path, fragment] = link.getAttribute('href').split('#');
    link.setAttribute('href', `${path.split('?')[0]}?models=${group}${fragment ? `#${fragment}` : ''}`);
  });
  bar.addEventListener('click', event => {
    const link = event.target.closest('a.vkey');
    if (link && link.hasAttribute('aria-current')) link.href = bar.dataset.home;
  });
  const head = document.querySelector('.head-sticky') ?? bar;
  const measure = () => document.documentElement.style.setProperty('--view-bar-h', `${head.offsetHeight}px`);
  measure();
  if ('ResizeObserver' in window) new ResizeObserver(measure).observe(head);
})();

/* The cost unit, one choice for the whole site (tb-next site.js setupCostUnit): ?cost-unit= or localStorage. */
(function setupCostUnit() {
  const root = document.documentElement;
  const unit = () => (root.dataset.costUnit === '1m' ? '1m' : '1k');
  const press = () => document.querySelectorAll('[data-cost-unit-choice]').forEach(key => {
    key.setAttribute('aria-pressed', String(key.dataset.costUnitChoice === unit()));
  });
  const keep = value => {
    try {
      localStorage.setItem('costUnit', value);
    } catch (error) {
      /* Storage may be unavailable; the address still carries the choice. */
    }
  };
  const asked = new URLSearchParams(window.location.search).get('cost-unit');
  if (asked === '1k' || asked === '1m') {
    if (asked === '1m') root.dataset.costUnit = '1m';
    else delete root.dataset.costUnit;
    keep(asked);
  }
  press();
  document.addEventListener('click', event => {
    const key = event.target.closest('[data-cost-unit-choice]');
    if (!key || key.dataset.costUnitChoice === unit()) return;
    const value = key.dataset.costUnitChoice;
    if (value === '1m') root.dataset.costUnit = '1m';
    else delete root.dataset.costUnit;
    keep(value);
    const url = new URL(window.location.href);
    url.searchParams.set('cost-unit', value);
    history.replaceState(history.state, '', url);
    press();
  });
})();

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
    if (choice === 'light') document.documentElement.dataset.theme = 'light';
    else document.documentElement.dataset.theme = 'dark';
    try {
      localStorage.setItem('theme', choice);
    } catch (error) {
      /* Storage may be unavailable; the choice then lasts for this page view. */
    }
    show();
  });
})();

/* Every question: filter the rows by ID, source, topic, English text status and a run's outcome; the filters live in the
   address (?source=aker&run=0&outcome=wrong) so a view can be shared. */
(function setupQuestionFilters() {
  const form = document.querySelector('[data-q-filters]');
  if (!form) return;
  const rows = Array.from(document.querySelectorAll('table.q-index tbody tr'));
  const fields = Object.fromEntries(Array.from(form.querySelectorAll('[data-filter]')).map(field => [field.dataset.filter, field]));
  const counter = document.querySelector('[data-q-count]');
  const runCount = fields.run ? fields.run.options.length - 1 : 0;
  const params = new URLSearchParams(window.location.search);
  for (const [name, field] of Object.entries(fields)) {
    const value = params.get(name);
    if (value !== null) field.value = value;
  }
  const apply = () => {
    const wanted = Object.fromEntries(Object.entries(fields).map(([name, field]) => [name, field.value.trim()]));
    const id = wanted.id.toLowerCase();
    let shown = 0;
    for (const row of rows) {
      let keep = (!id || row.dataset.id.toLowerCase().includes(id))
        && (!wanted.source || row.dataset.source === wanted.source)
        && (!wanted.topic || row.dataset.topic === wanted.topic)
        && (!wanted.en || row.dataset.en === wanted.en);
      if (keep && wanted.outcome) {
        if (wanted.run) keep = row.dataset['r' + wanted.run] === wanted.outcome;
        else {
          keep = false;
          for (let index = 0; index < runCount; index++) if (row.dataset['r' + index] === wanted.outcome) { keep = true; break; }
        }
      }
      row.hidden = !keep;
      shown += keep;
    }
    counter.textContent = `${shown.toLocaleString('en')} of ${rows.length.toLocaleString('en')} questions`;
    const url = new URL(window.location.href);
    for (const [name, value] of Object.entries(wanted)) {
      if (value) url.searchParams.set(name, value);
      else url.searchParams.delete(name);
    }
    history.replaceState(history.state, '', url);
  };
  form.addEventListener('input', apply);
  form.addEventListener('change', apply);
  form.addEventListener('submit', event => event.preventDefault());
  form.querySelector('[data-q-reset]').addEventListener('click', () => {
    for (const field of Object.values(fields)) field.value = '';
    apply();
  });
  form.hidden = false;
  document.querySelector('[data-q-note]').hidden = false;
  apply();
})();
