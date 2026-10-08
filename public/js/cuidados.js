/* AC Luxury Aesthetics — Selector de pestañas para /cuidados */
(function () {
  function initCuidados() {
    const tabs = document.querySelectorAll('[data-tab-target]');
    const panels = {
      unas: document.getElementById('panel-unas'),
      mirada: document.getElementById('panel-mirada'),
      retoque: document.getElementById('panel-retoque')
    };

    if (!tabs.length) return;

    function selectTab(targetId) {
      tabs.forEach((tab) => {
        const isMatch = tab.dataset.tabTarget === targetId;
        tab.classList.toggle('is-active', isMatch);
        tab.setAttribute('aria-selected', String(isMatch));
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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCuidados);
  } else {
    initCuidados();
  }
})();
