'use strict';

/* The Topics page's heat map (topics/): the setup choice above it shows the chosen setups' rows only (sitebuild/topics.py
   heatmap). The choice lives in the URL (?setups=145,199; none means every setup), so a view can be shared and survives a
   reload. Without this script every setup shows. */
(() => {
  const box = document.getElementById('heatmap');
  const choice = box.querySelector('[data-setup-choice]');
  const boxes = [...choice.querySelectorAll('input[type="checkbox"]')];
  const rows = new Map([...box.querySelectorAll('tbody tr[data-run]')].map(row => [row.dataset.run, row]));
  const none = box.querySelector('[data-setup-none]');
  const count = choice.querySelector('[data-setup-count]');

  function readUrl() {
    const picked = new Set((new URLSearchParams(window.location.search).get('setups') || '').split(',').filter(id => rows.has(id)));
    for (const input of boxes) input.checked = !picked.size || picked.has(input.value);
  }

  function writeUrl() {
    const params = new URLSearchParams(window.location.search);
    const picked = boxes.filter(input => input.checked).map(input => input.value);
    if (picked.length && picked.length < boxes.length) params.set('setups', picked.join(','));
    else params.delete('setups');
    const query = params.toString().replace(/%2C/g, ',');
    window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
  }

  function render() {
    let shown = 0;
    for (const input of boxes) {
      rows.get(input.value).hidden = !input.checked;
      if (input.checked) shown++;
    }
    count.textContent = shown === boxes.length ? `(all ${boxes.length} shown)` : `(${shown} of ${boxes.length} shown)`;
    none.hidden = shown > 0;
    box.querySelector('.heatmap-wrap').hidden = shown === 0;
  }

  choice.addEventListener('change', () => {
    render();
    writeUrl();
  });
  choice.addEventListener('click', event => {
    const key = event.target.closest('[data-setups]');
    if (!key) return;
    for (const input of boxes) input.checked = key.dataset.setups === 'all';
    render();
    writeUrl();
  });

  readUrl();
  choice.hidden = false;
  render();
})();
