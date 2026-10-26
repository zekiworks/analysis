'use strict';

/* Every page: the Dark / Light switch, with one memory for the whole site: the choice is kept in localStorage ("theme")
   and applied by a line in each page's <head> before it renders; without JavaScript the page stays dark. */
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
    else delete document.documentElement.dataset.theme;
    try {
      localStorage.setItem('theme', choice);
    } catch (error) {
      /* Storage may be unavailable; the choice then lasts for this page view. */
    }
    show();
  });
})();

/* Every page: More options in the top bar opens the colour theme and the page export. Escape closes it and gives the
   focus back to its key; a click outside it or the focus leaving it closes it too. The page export closes it first, so
   the PNG shows the page without the open menu (this listener runs before png.js's). */
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

/* On a phone the navigation bar scrolls sideways; a link that takes the keyboard focus is brought fully into view. */
(function keepFocusedLinkInView() {
  const bar = document.querySelector('.nav ul');
  if (!bar) return;
  bar.addEventListener('focusin', event => event.target.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
})();
