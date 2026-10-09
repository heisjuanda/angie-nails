import { setupScrollAffordance } from './scroll-affordance.js';

(function () {
  function initFaq() {
    const wrap = document.querySelector('.faq-nav-wrap');
    const nav = document.querySelector('.faq-nav-chips');
    const hint = document.querySelector('[data-faq-swipe-hint]');
    if (wrap && nav) {
      setupScrollAffordance({ wrap, nav, hint, threshold: 8 });
    }

    function checkHashTarget() {
      const hash = window.location.hash.slice(1);
      if (!hash) return;
      const targetEl = document.getElementById(hash);
      if (!targetEl) return;

      if (targetEl.tagName === 'DETAILS') {
        targetEl.open = true;
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } else if (targetEl.classList.contains('faq-group')) {
        targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }

    window.addEventListener('hashchange', checkHashTarget);
    if (document.readyState === 'complete') {
      checkHashTarget();
    } else {
      window.addEventListener('load', checkHashTarget);
    }

    const yearEl = document.querySelector('[data-year]');
    if (yearEl) {
      yearEl.textContent = new Date().getFullYear();
    }
  }

  function initAsyncStylesheets() {
    const switchMedia = (link) => {
      if (link && link.media !== 'all') link.media = 'all';
    };
    document.querySelectorAll('link[data-async-css]').forEach((link) => {
      link.addEventListener('load', () => switchMedia(link));
      if (link.sheet) switchMedia(link);
      setTimeout(() => switchMedia(link), 1500);
    });
  }

  initAsyncStylesheets();

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFaq);
  } else {
    initFaq();
  }
})();
