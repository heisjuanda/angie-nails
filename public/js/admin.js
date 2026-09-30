/* AC Luxury Aesthetics — panel de administración. */
(() => {
  const DOW = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
  const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const ACTIONS = {
    pending: [["confirmed", "Confirmar", "btn-dark"], ["cancelled", "Cancelar", "btn-danger"]],
    confirmed: [["completed", "Completada", "btn-outline"], ["cancelled", "Cancelar", "btn-danger"]],
  };
  const DONE_MSG = {
    confirmed: "Cita confirmada. Envíale la confirmación por WhatsApp:",
    cancelled: "Cita cancelada. Avísale a la clienta:",
    completed: "Cita marcada como completada.",
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const state = { status: "", range: "upcoming", bookings: [], refreshTimer: null };

  function h(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v);
    }
    for (const c of [].concat(children)) if (c !== null && c !== undefined) node.append(c);
    return node;
  }

  const pad = (n) => String(n).padStart(2, "0");
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
  const parseDate = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
  const dateLabel = (s) => { const d = parseDate(s); const t = `${DOW[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; return t[0].toUpperCase() + t.slice(1); };
  const phoneLabel = (p) => p.replace(/^57(\d{3})(\d{3})(\d{4})$/, "$1 $2 $3");

  /* ---------------------------------------------------------------- API */
  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  async function api(path, { method = "GET", body } = {}) {
    const res = await fetch(`/api/admin${path}`, {
      method,
      credentials: "same-origin",
      headers: body ? { "content-type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && path !== "/login") { showLogin(); throw new ApiError(401, data.error); }
    if (!res.ok) throw new ApiError(res.status, data.error || "Algo salió mal. Intenta de nuevo.");
    return data;
  }

  /* -------------------------------------------------------------- vistas */
  function showLogin() {
    clearInterval(state.refreshTimer);
    $("[data-view=app]").hidden = true;
    $("[data-view=login]").hidden = false;
    $("[data-login-form] input[name=password]").focus();
  }

  function showApp() {
    $("[data-view=login]").hidden = true;
    $("[data-view=app]").hidden = false;
    loadAgenda();
    loadBlocks();
    clearInterval(state.refreshTimer);
    state.refreshTimer = setInterval(() => { if (!document.hidden) loadAgenda({ quiet: true }); }, 60000);
  }

  function toast(message, { link, error = false } = {}) {
    const node = $("[data-toast]");
    node.replaceChildren(h("span", { text: message }));
    if (link) node.append(h("a", { href: link, target: "_blank", rel: "noopener", text: "Abrir WhatsApp →" }));
    node.classList.toggle("is-error", error);
    node.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.hidden = true; }, link ? 20000 : 6000);
  }

  /* ------------------------------------------------------------- agenda */
  function rangeDates() {
    const today = new Date();
    switch (state.range) {
      case "today": return [today, today];
      case "week": return [today, addDays(today, 6)];
      case "past": return [addDays(today, -30), addDays(today, -1)];
      default: return [today, addDays(today, 30)];
    }
  }

  async function loadAgenda({ quiet = false } = {}) {
    const [from, to] = rangeDates();
    const params = new URLSearchParams({ from: iso(from), to: iso(to) });
    if (state.status) params.set("status", state.status);
    const agenda = $("[data-agenda]");
    if (!quiet) agenda.replaceChildren(h("p", { class: "muted", text: "Cargando agenda…" }));
    try {
      const data = await api(`/bookings?${params}`);
      state.bookings = data.bookings;
      renderAgenda();
      if (!state.status) renderStats(data.bookings);
    } catch (err) {
      if (err.status !== 401) agenda.replaceChildren(h("p", { class: "agenda-empty", text: err.message }));
    }
  }

  function renderStats(bookings) {
    const today = iso(new Date());
    const active = (b) => !b.expired && (b.status === "pending" || b.status === "confirmed");
    const stats = [
      [bookings.filter((b) => b.status === "pending" && !b.expired).length, "Por confirmar"],
      [bookings.filter((b) => b.date === today && active(b)).length, "Hoy"],
      [bookings.filter((b) => b.status === "confirmed").length, "Confirmadas"],
    ];
    $("[data-stats]").replaceChildren(...stats.map(([n, label]) =>
      h("div", { class: "stat" }, [h("span", { class: "stat-value", text: String(n) }), h("span", { class: "stat-label", text: label })])
    ));
  }

  function renderAgenda() {
    const agenda = $("[data-agenda]");
    if (!state.bookings.length) {
      agenda.replaceChildren(h("p", { class: "agenda-empty", text: "No hay citas en este periodo." }));
      return;
    }
    const byDate = new Map();
    for (const b of state.bookings) {
      if (!byDate.has(b.date)) byDate.set(b.date, []);
      byDate.get(b.date).push(b);
    }
    agenda.replaceChildren(...[...byDate].map(([date, items]) =>
      h("section", { class: "day" }, [
        h("h2", { class: "day-title", text: dateLabel(date) }),
        h("div", { class: "day-list" }, items.map(bookingCard)),
      ])
    ));
  }

  function bookingCard(b) {
    const status = b.expired ? "expired" : b.status;
    const badge = h("span", { class: `badge badge-${b.status}`, text: b.status_label });
    const actions = (b.expired ? [] : ACTIONS[b.status] || []).map(([to, label, cls]) => {
      const btn = h("button", { type: "button", class: `btn ${cls}`, "data-action": to, text: label });
      btn.addEventListener("click", () => onAction(b, to, btn, label));
      return btn;
    });
    if (b.expired) {
      // Una pendiente vencida aún se puede confirmar si el horario sigue libre.
      const btn = h("button", { type: "button", class: "btn btn-outline", "data-action": "confirmed", text: "Confirmar" });
      btn.addEventListener("click", () => onAction(b, "confirmed", btn, "Confirmar"));
      actions.push(btn);
    }
    actions.push(h("a", { class: "btn btn-outline", href: b.whatsapp_url, target: "_blank", rel: "noopener", text: "WhatsApp" }));

    return h("article", { class: `booking-card is-${status}`, "data-code": b.code }, [
      h("div", { class: "booking-time" }, [b.start_label, h("small", { text: `hasta ${b.end}` })]),
      h("div", {}, [
        h("p", { class: "booking-service" }, [
          b.service_name, badge,
          b.expired ? h("span", { class: "badge badge-expired", text: "Vencida" }) : null,
        ]),
        h("p", { class: "booking-meta" }, [
          `${b.customer_name} · `,
          h("a", { href: `tel:+${b.phone}`, text: phoneLabel(b.phone) }),
        ]),
        h("p", { class: "booking-meta", text: `${b.neighborhood} · ${b.address}` }),
        b.notes ? h("p", { class: "booking-notes", text: `“${b.notes}”` }) : null,
        h("p", { class: "booking-code", text: `${b.code} · ${b.price_label}` }),
      ]),
      h("div", { class: "booking-actions" }, actions),
    ]);
  }

  async function onAction(b, to, btn, label) {
    // Cancelar pide un segundo toque para evitar errores.
    if (to === "cancelled" && !btn.classList.contains("is-armed")) {
      btn.classList.add("is-armed");
      btn.textContent = "¿Seguro? Toca otra vez";
      setTimeout(() => { btn.classList.remove("is-armed"); btn.textContent = label; }, 4000);
      return;
    }
    btn.disabled = true;
    try {
      const { booking } = await api(`/bookings/${encodeURIComponent(b.code)}`, { method: "PATCH", body: { status: to } });
      toast(DONE_MSG[to], { link: to === "completed" ? null : booking.whatsapp_url });
      await loadAgenda({ quiet: true });
    } catch (err) {
      if (err.status !== 401) toast(err.message, { error: true });
      btn.disabled = false;
      if (err.status === 409) loadAgenda({ quiet: true });
    }
  }

  /* ----------------------------------------------------------- bloqueos */
  async function loadBlocks() {
    const list = $("[data-blocks]");
    try {
      const { blocks } = await api("/blocks");
      if (!blocks.length) {
        list.replaceChildren(h("li", { class: "agenda-empty", text: "No hay bloqueos próximos." }));
        return;
      }
      list.replaceChildren(...blocks.map((b) => {
        const del = h("button", { type: "button", class: "btn btn-danger btn-sm", text: "Quitar" });
        del.addEventListener("click", async () => {
          del.disabled = true;
          try { await api(`/blocks/${b.id}`, { method: "DELETE" }); loadBlocks(); }
          catch (err) { del.disabled = false; setBlockMessage(err.message); }
        });
        return h("li", { class: "block-item", "data-block-id": String(b.id) }, [
          h("div", {}, [
            h("strong", { text: dateLabel(b.date) }),
            h("p", { class: "muted", text: (b.all_day ? "Todo el día" : `${b.start} – ${b.end}`) + (b.reason ? ` · ${b.reason}` : "") }),
          ]),
          del,
        ]);
      }));
    } catch (err) {
      if (err.status !== 401) list.replaceChildren(h("li", { class: "agenda-empty", text: err.message }));
    }
  }

  function setBlockMessage(msg, ok = false) {
    const node = $("[data-block-message]");
    node.textContent = msg || "";
    node.hidden = !msg;
    node.style.color = ok ? "var(--ink)" : "";
  }

  function syncTimeFields() {
    const allDay = $("[data-block-form] input[name=all_day]").checked;
    $$("[data-time-field]").forEach((f) => { f.hidden = allDay; });
  }

  async function onBlockSubmit(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = {
      date: form.elements.date.value,
      all_day: form.elements.all_day.checked,
      start: form.elements.start.value,
      end: form.elements.end.value,
      reason: form.elements.reason.value,
    };
    if (!body.date) { setBlockMessage("Elige una fecha."); return; }
    const submit = form.querySelector("button[type=submit]");
    submit.disabled = true;
    try {
      const res = await api("/blocks", { method: "POST", body });
      const warn = res.overlapping_bookings
        ? ` Ojo: hay ${res.overlapping_bookings} cita(s) activa(s) en ese horario; no se cancelan solas.`
        : "";
      setBlockMessage(`Horario bloqueado.${warn}`, !warn);
      form.elements.reason.value = "";
      loadBlocks();
    } catch (err) {
      if (err.status !== 401) setBlockMessage(err.message);
    } finally {
      submit.disabled = false;
    }
  }

  /* --------------------------------------------------------------- init */
  function initTabs() {
    $$("[data-tab]").forEach((tab) => tab.addEventListener("click", () => {
      $$("[data-tab]").forEach((t) => {
        const active = t === tab;
        t.classList.toggle("is-active", active);
        t.setAttribute("aria-selected", String(active));
      });
      $$("[data-panel]").forEach((p) => { p.hidden = p.dataset.panel !== tab.dataset.tab; });
    }));
  }

  async function init() {
    initTabs();

    $("[data-login-form]").addEventListener("submit", async (e) => {
      e.preventDefault();
      const input = e.currentTarget.elements.password;
      const err = $("[data-login-error]");
      err.hidden = true;
      try {
        await api("/login", { method: "POST", body: { password: input.value } });
        input.value = "";
        showApp();
      } catch (ex) {
        err.textContent = ex.message;
        err.hidden = false;
        input.select();
      }
    });

    $("[data-logout]").addEventListener("click", async () => {
      await api("/logout", { method: "POST" }).catch(() => {});
      showLogin();
    });

    $("[data-range]").addEventListener("change", (e) => { state.range = e.target.value; loadAgenda(); });
    $$("[data-status-filters] [data-status]").forEach((chip) => chip.addEventListener("click", () => {
      state.status = chip.dataset.status;
      $$("[data-status-filters] [data-status]").forEach((c) => {
        c.classList.toggle("is-active", c === chip);
        c.setAttribute("aria-pressed", String(c === chip));
      });
      loadAgenda();
    }));
    $("[data-refresh]").addEventListener("click", () => loadAgenda());

    const blockForm = $("[data-block-form]");
    blockForm.elements.date.value = iso(new Date());
    blockForm.elements.all_day.addEventListener("change", syncTimeFields);
    blockForm.addEventListener("submit", onBlockSubmit);
    syncTimeFields();

    try {
      const { authenticated } = await api("/session");
      if (authenticated) showApp();
      else showLogin();
    } catch {
      showLogin();
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
