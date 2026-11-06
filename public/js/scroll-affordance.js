/**
 * AC Luxury Aesthetics — Utilidad centralizada de Affordance de Scroll Horizontal
 *
 * Gestiona los gradientes laterales (.can-scroll-left / .can-scroll-right)
 * y la visibilidad del botón de pista ("Desliza ->") cuando el contenido
 * desborda horizontalmente la pantalla (típicamente en móviles).
 *
 * @param {Object} options
 * @param {HTMLElement} options.wrap Contenedor exterior con overflow relativo y gradientes
 * @param {HTMLElement} options.nav Elemento con scroll horizontal
 * @param {HTMLElement} [options.hint] Elemento de texto/ícono "Desliza"
 * @param {number} [options.threshold=8] Píxeles de holgura para activar el scroll
 * @returns {Function} Función para forzar la actualización manual del estado
 */
export function setupScrollAffordance({ wrap, nav, hint, threshold = 8 }) {
  if (!wrap || !nav) return () => { };

  let ticking = false;

  function update() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      ticking = false;
      const { scrollLeft, scrollWidth, clientWidth } = nav;
      const maxScroll = Math.round(scrollWidth - clientWidth);
      const hasOverflow = maxScroll > threshold;
      const canScrollRight = hasOverflow && Math.round(scrollLeft) < maxScroll - threshold;
      const canScrollLeft = hasOverflow && Math.round(scrollLeft) > threshold;

      wrap.classList.toggle('can-scroll-right', canScrollRight);
      wrap.classList.toggle('can-scroll-left', canScrollLeft);

      if (hint) {
        hint.hidden = !canScrollRight;
        hint.classList.toggle('is-visible', canScrollRight);
      }
    });
  }

  nav.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update, { passive: true });
  requestAnimationFrame(update);

  return update;
}
