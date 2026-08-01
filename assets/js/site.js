// Three jobs only: remember the reader's theme choice, shade the nav on scroll,
// and make sure the service worker from the 2021 build is gone.
(function () {
  'use strict';

  var root = document.documentElement;

  // --- theme ------------------------------------------------------------- //
  var stored = null;
  try { stored = localStorage.getItem('theme'); } catch (e) { /* private mode */ }
  if (stored === 'dark' || stored === 'light') {
    root.setAttribute('data-theme', stored);
  }

  function currentTheme() {
    var explicit = root.getAttribute('data-theme');
    if (explicit) { return explicit; }
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  var toggle = document.querySelector('.theme-toggle');
  if (toggle) {
    // The control is markup-hidden until this runs, so it is never a dead
    // button for readers without JavaScript.
    toggle.hidden = false;

    var label = function () {
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      toggle.textContent = next === 'dark' ? 'Dark' : 'Light';
      toggle.setAttribute('aria-label', 'Switch to ' + next + ' theme');
    };
    label();

    toggle.addEventListener('click', function () {
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) { /* ignore */ }
      label();
    });
  }

  // --- nav shadow on scroll --------------------------------------------- //
  var nav = document.querySelector('.nav');
  if (nav) {
    var sync = function () {
      nav.setAttribute('data-scrolled', String(window.scrollY > 8));
    };
    sync();
    window.addEventListener('scroll', sync, { passive: true });
  }

  // --- remove the old service worker ------------------------------------ //
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then(function (registrations) {
      registrations.forEach(function (registration) { registration.unregister(); });
    }).catch(function () { /* nothing to do */ });
  }
})();
