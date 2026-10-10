/* AC Luxury Aesthetics — menú, portafolio y servicios. */

/**
 * Portafolio. Para agregar una foto: guárdala en /img/portafolio/ y pon su ruta
 * en `src`. Mientras `src` sea null se muestra un recuadro de reemplazo.
 * category: "unas" | "cejas" | "pestanas"
 */
const PORTFOLIO = [
  { src: null, title: "Set acrílico", category: "unas" },
  { src: null, title: "Semipermanente", category: "unas" },
  { src: null, title: "Nail art", category: "unas" },
  { src: null, title: "Polygel", category: "unas" },
  { src: null, title: "Diseño de cejas", category: "cejas" },
  { src: null, title: "Laminado", category: "cejas" },
  { src: null, title: "Volumen", category: "pestanas" },
  { src: null, title: "Lifting", category: "pestanas" },
];

const CATEGORY_LABEL = { unas: "Uñas", cejas: "Cejas", pestanas: "Pestañas" };

// Configuración compartida con booking.js (servicios, precios, WhatsApp…).
window.acConfig = fetch("/api/config").then((r) => {
  if (!r.ok) throw new Error(`config ${r.status}`);
  return r.json();
});

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value);
  }
  for (const child of [].concat(children)) node.append(child);
  return node;
}

/* ----------------------------------------------------------------- menú */
function initNav() {
  const toggle = $("[data-nav-toggle]");
  const nav = $("[data-nav]");
  const setOpen = (open) => {
    nav.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    $(".sr-only", toggle).textContent = open ? "Cerrar menú" : "Abrir menú";
  };
  toggle.addEventListener("click", () => setOpen(!nav.classList.contains("is-open")));
  nav.addEventListener("click", (e) => { if (e.target.closest("a")) setOpen(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
}

/* ----------------------------------------------------------- portafolio */
const PHOTO_ICON = '<svg class="icon ph-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="4.5" width="17" height="15" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M20.5 16l-5-5-8.5 8.5"/></svg>';

function initPortfolio() {
  const grid = $("[data-portfolio-grid]");
  PORTFOLIO.forEach((item, i) => {
    const media = el("div", { class: `ph tone-${(i % 4) + 1}` });
    if (item.src) {
      media.append(el("img", { src: item.src, alt: `${item.title} · ${CATEGORY_LABEL[item.category]}`, loading: "lazy" }));
    } else {
      media.innerHTML = PHOTO_ICON;
    }
    grid.append(el("li", { class: "portfolio-item", "data-category": item.category }, [
      media,
      el("p", { class: "portfolio-caption" }, [
        el("span", { text: item.src ? item.title : `[${item.title}]` }),
        el("span", { text: CATEGORY_LABEL[item.category] }),
      ]),
    ]));
  });

  const buttons = $$("[data-portfolio-filters] [data-filter]");
  buttons.forEach((btn) => btn.addEventListener("click", () => {
    const filter = btn.dataset.filter;
    buttons.forEach((b) => {
      const active = b === btn;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-pressed", String(active));
    });
    $$(".portfolio-item", grid).forEach((it) => {
      it.hidden = filter !== "todo" && it.dataset.category !== filter;
    });
  }));
}

/* ------------------------------------------------------------ servicios */
async function initServices() {
  const grid = $("[data-services-grid]");
  let config;
  try {
    config = await window.acConfig;
  } catch {
    grid.innerHTML = '<p class="services-loading">No pudimos cargar los servicios. Recarga la página.</p>';
    return;
  }

  grid.replaceChildren(...config.categories.map((cat, i) => {
    const items = config.services.filter((s) => s.category === cat.id);
    const button = el("a", { class: "btn btn-outline btn-block", href: "#agendar", "data-book-category": cat.id, text: `Agendar ${cat.name}` });
    const cardChildren = [
      el("header", { class: "service-card-head" }, [
        el("h3", { class: "service-card-title", text: cat.name }),
        el("span", { class: "service-card-num", text: String(i + 1).padStart(2, "0") }),
      ]),
    ];
    if (cat.id === "combos") {
      cardChildren.push(
        el("p", {
          class: "service-card-sub",
          text: "Elige qué servicio de uñas, cejas o pestañas incluir en tu combinación al agendar.",
        })
      );
    }
    cardChildren.push(
      el("ul", { class: "service-list" }, items.map((s) =>
        el("li", {}, [el("span", { text: s.name }), el("span", { text: s.price_label })])
      )),
      button,
    );
    return el("article", { class: "service-card" }, cardChildren);
  }));

  // WhatsApp del pie de página
  $$("[data-whatsapp-link]").forEach((a) => { a.href = `https://wa.me/${config.whatsapp}`; });
}

/*  barra flotante móvil */
function initStickyBookingBar() {
  const bar = $("[data-mobile-sticky-bar]");
  const bookingSection = document.getElementById("agendar");
  const heroSection = document.getElementById("inicio");
  if (!bar || !bookingSection) return;

  let isBookingVisible = false;
  let isHeroVisible = true;

  const update = () => {
    const shouldHide = isBookingVisible || isHeroVisible;
    bar.classList.toggle("is-hidden", shouldHide);
  };

  if ("IntersectionObserver" in window) {
    const bookingObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          isBookingVisible = e.isIntersecting;
          update();
        });
      },
      { threshold: 0.08 }
    );

    const heroObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          isHeroVisible = e.isIntersecting;
          update();
        });
      },
      { threshold: 0.3 }
    );

    bookingObserver.observe(bookingSection);
    if (heroSection) heroObserver.observe(heroSection);
  } else {
    let ticking = false;
    window.addEventListener("scroll", () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        ticking = false;
        const rect = bookingSection.getBoundingClientRect();
        const inBooking = rect.top < window.innerHeight && rect.bottom > 0;
        bar.classList.toggle("is-hidden", inBooking || window.scrollY < 120);
      });
    }, { passive: true });
  }
}

/*  mapa diferido */
function initLazyMap() {
  const iframe = document.querySelector(".map-container iframe[data-src]");
  if (!iframe) return;

  const loadIframe = () => {
    if (iframe.dataset.src) {
      iframe.src = iframe.dataset.src;
      iframe.removeAttribute("data-src");
    }
  };

  if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          loadIframe();
          observer.disconnect();
        }
      });
    }, { rootMargin: "400px 0px" });
    observer.observe(iframe);
  } else {
    loadIframe();
  }
}

/*  fuentes / css diferido */
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

document.addEventListener("DOMContentLoaded", () => {
  initNav();
  initPortfolio();
  initServices();
  initStickyBookingBar();
  initLazyMap();
  $$("[data-year]").forEach((n) => { n.textContent = new Date().getFullYear(); });
});
