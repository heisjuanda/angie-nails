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
    return el("article", { class: "service-card" }, [
      el("header", { class: "service-card-head" }, [
        el("h3", { class: "service-card-title", text: cat.name }),
        el("span", { class: "service-card-num", text: String(i + 1).padStart(2, "0") }),
      ]),
      el("ul", { class: "service-list" }, items.map((s) =>
        el("li", {}, [el("span", { text: s.name }), el("span", { text: s.price_label })])
      )),
      button,
    ]);
  }));

  // Cobertura y recargo
  const coverage = config.coverage.length ? config.coverage.join(", ") : "Cali";
  $("[data-coverage]").textContent =
    `Cobertura: ${coverage}` + (config.travel_fee_label ? ` · Recargo de domicilio: ${config.travel_fee_label}` : " · Recargo de domicilio: X");
  const list = $("[data-coverage-list]");
  config.coverage.forEach((b) => list.append(el("option", { value: b })));

  // WhatsApp del pie de página
  $$("[data-whatsapp-link]").forEach((a) => { a.href = `https://wa.me/${config.whatsapp}`; });
}

document.addEventListener("DOMContentLoaded", () => {
  initNav();
  initPortfolio();
  initServices();
  $$("[data-year]").forEach((n) => { n.textContent = new Date().getFullYear(); });
});
