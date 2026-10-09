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
  const state = { status: "", range: "upcoming", page: 1, total: 0, perPage: 0, bookings: [], refreshTimer: null, services: [], hours: {}, slotStep: 30, configLoaded: false, editing: null, editingBooking: null };

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
  const toMin = (hhmm) => { const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; };
  const toHhmm = (min) => `${pad(Math.floor(min / 60))}:${pad(min % 60)}`;
  const timeLabel = (hhmm) => { const h = Math.floor(toMin(hhmm) / 60); const m = toMin(hhmm) % 60; return `${(h % 12) || 12}:${pad(m)} ${h < 12 ? "a. m." : "p. m."}`; };

  /*  API */
  class ApiError extends Error {
    constructor(status, message, data) { super(message); this.status = status; this.data = data; }
  }

  async function api(path, { method = "GET", body } = {}) {
    const res = await fetch(`/api/admin${path}`, {
      method,
      credentials: "same-origin",
      headers: body ? { "content-type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && path !== "/login" && path !== "/mfa") { showLogin(); throw new ApiError(401, data.error); }
    if (!res.ok) throw new ApiError(res.status, data.error || "Algo salió mal. Intenta de nuevo.", data);
    return data;
  }

  async function loadSiteConfig() {
    if (state.configLoaded) return;
    try {
      const res = await fetch("/api/config", { credentials: "same-origin" });
      if (!res.ok) return;
      const data = await res.json();
      state.services = data.services || [];
      state.hours = data.hours || {};
      state.slotStep = data.slot_step_min || 30;
      state.configLoaded = true;
    } catch { /* se reintenta al abrir el editor */ }
  }

  /*  vistas */
  function showLogin() {
    clearInterval(state.refreshTimer);
    $("[data-view=app]").hidden = true;
    $("[data-view=login]").hidden = false;
    resetLoginForm();
    $("[data-login-form] input[name=password]").focus();
  }

  function resetLoginForm() {
    const form = $("[data-login-form]");
    const mfaField = form.querySelector("[data-mfa-field]");
    if (!mfaField) return;
    mfaField.hidden = true;
    form.elements.password.disabled = false;
    form.elements.code.value = "";
    form.querySelector("button[type=submit]").textContent = "Entrar";
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
    if (link) node.append(h("a", { href: link, target: "_blank", rel: "noopener", text: "Abrir WhatsApp \u2192\uFE0E" }));
    node.classList.toggle("is-error", error);
    node.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.hidden = true; }, link ? 20000 : 6000);
  }

  /*  agenda */
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
    const params = new URLSearchParams({ from: iso(from), to: iso(to), page: String(state.page) });
    if (state.status) params.set("status", state.status);
    const agenda = $("[data-agenda]");
    if (!quiet) agenda.replaceChildren(h("p", { class: "muted", text: "Cargando agenda…" }));
    try {
      const data = await api(`/bookings?${params}`);
      state.bookings = data.bookings;
      state.total = data.total;
      state.perPage = data.per_page;
      const pages = Math.max(1, Math.ceil(state.total / state.perPage));
      if (state.total > 0 && state.page > pages) {
        state.page = pages;
        return loadAgenda({ quiet });
      }
      renderAgenda();
      renderPagination();
      renderStats(data.stats);
    } catch (err) {
      if (err.status !== 401) {
        agenda.replaceChildren(h("p", { class: "agenda-empty", text: err.message }));
        hidePagination();
      }
    }
  }

  function hidePagination() {
    const node = $("[data-pagination]");
    node.hidden = true;
    node.replaceChildren();
  }

  function renderPagination() {
    const pages = Math.ceil(state.total / state.perPage);
    if (!state.perPage || !Number.isFinite(pages) || pages < 2) {
      hidePagination();
      return;
    }
    const node = $("[data-pagination]");
    const prev = h("button", { type: "button", class: "btn btn-outline btn-sm", "data-page": state.page - 1, text: "\u2190\uFE0E Anterior" });
    const next = h("button", { type: "button", class: "btn btn-outline btn-sm", "data-page": state.page + 1, text: "Siguiente \u2192\uFE0E" });
    prev.disabled = state.page <= 1;
    next.disabled = state.page >= pages;
    node.replaceChildren(
      prev,
      h("span", { class: "pagination-info", text: `Página ${state.page} de ${pages}` }),
      next,
    );
    node.hidden = false;
  }

  function renderStats(summary) {
    const s = summary || { pending: 0, today: 0, confirmed: 0 };
    const cards = [
      [s.pending, "Por confirmar"],
      [s.today, "Hoy"],
      [s.confirmed, "Confirmadas"],
    ];
    $("[data-stats]").replaceChildren(...cards.map(([n, label]) =>
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
    if (!b.expired && (b.status === "pending" || b.status === "confirmed")) {
      const edit = h("button", { type: "button", class: "btn btn-outline", "data-action": "edit", text: "Editar" });
      edit.addEventListener("click", () => openEdit(b));
      actions.unshift(edit);
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

  /*  editar cita: horario y servicio */
  function setEditMessage(msg) {
    const node = $("[data-edit-message]");
    node.textContent = msg || "";
    node.hidden = !msg;
  }

  function closeEdit() {
    $("[data-edit-modal]").hidden = true;
    state.editing = null;
    state.editingBooking = null;
  }

  function timeOptions(dateStr) {
    if (!dateStr) return [];
    const todayIso = iso(new Date());
    if (dateStr < todayIso) return [];
    const spans = state.hours[String(parseDate(dateStr).getDay())] || [];
    const isToday = dateStr === todayIso;
    const now = new Date();
    const nowMin = isToday ? (now.getHours() * 60 + now.getMinutes()) : -1;
    const times = [];
    for (const [open, close] of spans) {
      for (let t = toMin(open); t < toMin(close); t += state.slotStep) {
        if (!isToday || t > nowMin) times.push(toHhmm(t));
      }
    }
    return times;
  }

  function updateEditTimes(dateStr, preferredTime = null) {
    const form = $("[data-edit-form]");
    const timeSelect = form.elements.time;
    const times = timeOptions(dateStr);
    if (!times.length) {
      timeSelect.replaceChildren(h("option", { value: "", text: "Sin horarios disponibles", disabled: true, selected: true }));
      timeSelect.value = "";
      return;
    }
    const hasPreferred = preferredTime && times.includes(preferredTime);
    const targetValue = hasPreferred ? preferredTime : (times.includes(timeSelect.value) ? timeSelect.value : "");
    const options = times.map((t) => h("option", { value: t, text: timeLabel(t) }));
    if (!targetValue) {
      options.unshift(h("option", { value: "", text: "Elige un horario", disabled: true, selected: true }));
    }
    timeSelect.replaceChildren(...options);
    timeSelect.value = targetValue;
  }

  async function openEdit(b) {
    if (!state.configLoaded) await loadSiteConfig();
    state.editing = b.code;
    state.editingBooking = b;
    const form = $("[data-edit-form]");
    $("[data-edit-customer]").textContent = `${b.customer_name} · ${phoneLabel(b.phone)}`;
    $("[data-edit-when]").textContent = `${b.date_label} · ${b.start_label}`;
    const service = form.elements.service_id;
    service.replaceChildren(...state.services.map((s) =>
      h("option", { value: s.id, text: `${s.name} · ${s.price_label}` })));
    service.value = b.service_id;

    const todayIso = iso(new Date());
    const dateInput = form.elements.date;
    dateInput.min = todayIso;
    dateInput.max = iso(addDays(new Date(), 120));
    dateInput.value = b.date >= todayIso ? b.date : todayIso;

    updateEditTimes(dateInput.value, b.start);
    setEditMessage("");
    $("[data-edit-modal]").hidden = false;
  }

  async function onEditSubmit(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const dateVal = form.elements.date.value;
    const timeVal = form.elements.time.value;
    const serviceVal = form.elements.service_id.value;

    if (!dateVal) {
      setEditMessage("Elige una fecha válida.");
      return;
    }
    if (!timeVal) {
      setEditMessage("Elige un horario válido.");
      return;
    }

    const submit = form.querySelector("button[type=submit]");
    submit.disabled = true;
    try {
      await api(`/bookings/${encodeURIComponent(state.editing)}`, {
        method: "PATCH",
        body: {
          date: dateVal,
          time: timeVal,
          service_id: serviceVal,
        },
      });
      closeEdit();
      toast("Cita actualizada.");
      await loadAgenda({ quiet: true });
    } catch (err) {
      if (err.status !== 401) setEditMessage(err.message);
    } finally {
      submit.disabled = false;
    }
  }

  /*  bloqueos */
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

  /*  init */
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
    loadSiteConfig();

    $("[data-login-form]").addEventListener("submit", async (e) => {
      e.preventDefault();
      const form = e.currentTarget;
      const mfaField = form.querySelector("[data-mfa-field]");
      const input = form.elements.password;
      const codeInput = form.elements.code;
      const err = $("[data-login-error]");
      err.hidden = true;
      try {
        if (mfaField && !mfaField.hidden) {
          await api("/mfa", { method: "POST", body: { code: codeInput.value } });
        } else {
          const res = await api("/login", { method: "POST", body: { password: input.value } });
          if (res.mfa_required && mfaField) {
            mfaField.hidden = false;
            input.disabled = true;
            form.querySelector("button[type=submit]").textContent = "Verificar";
            codeInput.focus();
            return;
          }
        }
        input.value = "";
        if (codeInput) codeInput.value = "";
        showApp();
      } catch (ex) {
        // Ticket de MFA vencido o ausente: volver a pedir la contraseña.
        if (ex.status === 401 && ex.data?.step === "password") showLogin();
        err.textContent = ex.message;
        err.hidden = false;
        if (mfaField && !mfaField.hidden) {
          codeInput.value = "";
          codeInput.select();
        } else {
          input.select();
        }
      }
    });

    $("[data-logout]").addEventListener("click", async () => {
      await api("/logout", { method: "POST" }).catch(() => { });
      showLogin();
    });

    $("[data-range]").addEventListener("change", (e) => { state.range = e.target.value; state.page = 1; loadAgenda(); });
    $$("[data-status-filters] [data-status]").forEach((chip) => chip.addEventListener("click", () => {
      state.status = chip.dataset.status;
      state.page = 1;
      $$("[data-status-filters] [data-status]").forEach((c) => {
        c.classList.toggle("is-active", c === chip);
        c.setAttribute("aria-pressed", String(c === chip));
      });
      loadAgenda();
    }));
    $("[data-refresh]").addEventListener("click", () => loadAgenda());
    $("[data-pagination]").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-page]");
      if (!btn || btn.disabled) return;
      state.page = Number(btn.dataset.page);
      loadAgenda();
    });

    const blockForm = $("[data-block-form]");
    blockForm.elements.date.value = iso(new Date());
    blockForm.elements.all_day.addEventListener("change", syncTimeFields);
    blockForm.addEventListener("submit", onBlockSubmit);
    syncTimeFields();

    $("[data-edit-cancel]").addEventListener("click", closeEdit);
    $("[data-edit-form]").addEventListener("submit", onEditSubmit);
    const editDateInput = $("[data-edit-form] input[name=date]");
    const onEditDateChange = () => {
      const b = state.editingBooking;
      updateEditTimes(editDateInput.value, b ? b.start : null);
    };
    editDateInput.addEventListener("change", onEditDateChange);
    editDateInput.addEventListener("input", onEditDateChange);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("[data-edit-modal]").hidden) closeEdit();
    });

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
