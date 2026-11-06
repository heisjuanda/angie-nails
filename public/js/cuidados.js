/* AC Luxury Aesthetics — Selector de pestañas para /cuidados */
import { setupScrollAffordance } from './scroll-affordance.js';

(function () {
  function initCuidados() {
    const wrap = document.querySelector('.cuidados-tabs-wrap');
    const nav = document.querySelector('.cuidados-tabs-nav');
    const tabs = document.querySelectorAll('[data-tab-target]');
    const panels = {
      unas: document.getElementById('panel-unas'),
      mirada: document.getElementById('panel-mirada'),
      retoque: document.getElementById('panel-retoque')
    };

    if (!tabs.length) return;

    const hint = document.querySelector('[data-cuidados-swipe-hint]');
    const updateScrollState = setupScrollAffordance({ wrap, nav, hint, threshold: 8 });

    function selectTab(targetId) {
      tabs.forEach((tab) => {
        const isMatch = tab.dataset.tabTarget === targetId;
        tab.classList.toggle('is-active', isMatch);
        tab.setAttribute('aria-selected', String(isMatch));
        if (isMatch && nav) {
          tab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        }
      });

      Object.entries(panels).forEach(([key, panel]) => {
        if (panel) {
          if (key === targetId) {
            panel.removeAttribute('hidden');
            panel.hidden = false;
          } else {
            panel.setAttribute('hidden', '');
            panel.hidden = true;
          }
        }
      });

      if (updateScrollState) {
        requestAnimationFrame(updateScrollState);
      }
    }

    tabs.forEach((tab) => {
      tab.addEventListener('click', (e) => {
        e.preventDefault();
        const target = tab.dataset.tabTarget;
        if (target) selectTab(target);
      });
    });

    const hash = window.location.hash.replace('#', '');
    if (['unas', 'mirada', 'retoque'].includes(hash)) {
      selectTab(hash);
    }

    const yearEl = document.querySelector('[data-year]');
    if (yearEl) {
      yearEl.textContent = new Date().getFullYear();
    }
  }

  function initAsyncStylesheets() {
    const switchMedia = (link) => {
      if (link && link.media !== "all") link.media = "all";
    };
    document.querySelectorAll("link[data-async-css]").forEach((link) => {
      link.addEventListener("load", () => switchMedia(link));
      if (link.sheet) switchMedia(link);
      setTimeout(() => switchMedia(link), 1500);
    });
  }

  initAsyncStylesheets();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCuidados);
  } else {
    initCuidados();
  }
})();
