/* AC Luxury Aesthetics — Selector de pestañas para /cuidados */
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

    let scrollTicking = false;
    function updateScrollState() {
      if (scrollTicking) return;
      scrollTicking = true;
      requestAnimationFrame(() => {
        scrollTicking = false;
        if (!nav || !wrap) return;
        const { scrollLeft, scrollWidth, clientWidth } = nav;
        const maxScroll = Math.round(scrollWidth - clientWidth);
        const hasOverflow = maxScroll > 8;
        const canScrollRight = hasOverflow && Math.round(scrollLeft) < maxScroll - 8;
        const canScrollLeft = hasOverflow && Math.round(scrollLeft) > 8;
        wrap.classList.toggle('can-scroll-right', canScrollRight);
        wrap.classList.toggle('can-scroll-left', canScrollLeft);

        if (hint) {
          hint.hidden = !canScrollRight;
          hint.classList.toggle('is-visible', canScrollRight);
        }
      });
    }

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

      requestAnimationFrame(updateScrollState);
    }

    tabs.forEach((tab) => {
      tab.addEventListener('click', (e) => {
        e.preventDefault();
        const target = tab.dataset.tabTarget;
        if (target) selectTab(target);
      });
    });

    if (nav) {
      nav.addEventListener('scroll', updateScrollState, { passive: true });
      window.addEventListener('resize', updateScrollState, { passive: true });
      requestAnimationFrame(updateScrollState);
    }

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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCuidados);
  } else {
    initCuidados();
  }
})();
