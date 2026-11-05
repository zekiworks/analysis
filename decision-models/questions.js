'use strict';

/* The Every question page (questions/): filters on question ID, book page, topic and difficulty over the rows the page
   holds (sitebuild/questions.py every_question), and the matching rows shown data-rows at a time. The filters and the
   rows shown live in the URL (?id=, ?book-page=, ?topic=, ?difficulty=, ?list-page=), so a view can be shared and
   survives a reload. Without this script every row shows. */
(() => {
  const box = document.getElementById('questions');
  const form = box.querySelector('[data-q-filters]');
  const fields = [...form.querySelectorAll('[data-filter]')];
  const rows = [...box.querySelectorAll('tbody tr')];
  const pagers = [...box.querySelectorAll('[data-q-pager]')];
  const count = box.querySelector('[data-q-count]');
  const size = Number(box.dataset.rows) || 100;
  const integer = value => value.toLocaleString('en-US');
  let listPage = 1;

  const ROW_FIELD = { id: 'id', 'book-page': 'page', topic: 'topic', difficulty: 'difficulty' };
  const chosen = () => fields.map(field => [field.dataset.filter, field.value.trim()]).filter(([, value]) => value);
  const matches = (row, filters) => filters.every(([key, value]) => row.dataset[ROW_FIELD[key]] === value);

  function readUrl() {
    const params = new URLSearchParams(window.location.search);
    for (const field of fields) {
      const value = params.get(field.dataset.filter) || '';
      /* A topic or difficulty the list does not hold reads as no filter. */
      field.value = field.tagName === 'SELECT' && ![...field.options].some(option => option.value === value) ? '' : value;
    }
    listPage = Math.max(1, Math.floor(Number(params.get('list-page'))) || 1);
  }

  function writeUrl() {
    const params = new URLSearchParams(window.location.search);
    for (const field of fields) params.delete(field.dataset.filter);
    params.delete('list-page');
    for (const [key, value] of chosen()) params.set(key, value);
    if (listPage > 1) params.set('list-page', String(listPage));
    const query = params.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
  }

  function render() {
    const filters = chosen();
    const shown = rows.filter(row => matches(row, filters));
    const pages = Math.max(1, Math.ceil(shown.length / size));
    listPage = Math.min(listPage, pages);
    const first = (listPage - 1) * size;
    const visible = new Set(shown.slice(first, first + size));
    for (const row of rows) row.hidden = !visible.has(row);
    const of = filters.length ? `${integer(shown.length)} of ${integer(rows.length)} questions match` : `${integer(rows.length)} questions`;
    count.textContent = shown.length
      ? `${of}. Showing ${integer(first + 1)} to ${integer(first + visible.size)}.`
      : 'No question matches these filters.';
    for (const pager of pagers) {
      pager.hidden = pages === 1;
      pager.querySelector('[data-q-where]').textContent = `Rows ${integer(first + 1)} to ${integer(first + visible.size)} of ${integer(shown.length)}`;
      pager.querySelector('[data-step="-1"]').setAttribute('aria-disabled', String(listPage === 1));
      pager.querySelector('[data-step="1"]').setAttribute('aria-disabled', String(listPage === pages));
    }
    form.querySelector('[data-q-reset]').setAttribute('aria-disabled', String(!filters.length && listPage === 1));
  }

  function update() {
    render();
    writeUrl();
  }

  form.addEventListener('submit', event => event.preventDefault());
  form.addEventListener('input', () => {
    listPage = 1;
    update();
  });
  form.querySelector('[data-q-reset]').addEventListener('click', () => {
    for (const field of fields) field.value = '';
    listPage = 1;
    update();
  });
  for (const pager of pagers) {
    pager.addEventListener('click', event => {
      const key = event.target.closest('[data-step]');
      if (!key || key.getAttribute('aria-disabled') === 'true') return;
      listPage += Number(key.dataset.step);
      update();
      /* From the lower keys, back to the top of the list. */
      if (pager.hasAttribute('data-q-bottom')) pagers[0].scrollIntoView({ block: 'start' });
    });
  }

  readUrl();
  form.hidden = false;
  box.querySelector('[data-q-note]').hidden = false;
  render();
  writeUrl();
})();
