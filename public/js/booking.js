/* AC Luxury Aesthetics — reserva en tres pasos. */
(() => {
  const DOW = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  const DOW_LONG = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
  const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const CATEGORY_LABEL = { unas: "Uñas", cejas: "Cejas", pestanas: "Pestañas", combos: "Combos" };
  const mobile = window.matchMedia("(max-width: 700px)");

  const TS = { OFF: "off", LOADING: "loading", READY: "ready", BROKEN: "broken" };
  const TS_SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=onTurnstileLoad";
  const TS_TIMEOUT_MS = 12000;
  const TS_MAX_RETRIES = 2;
  const TS_MSG = {
    loading: "Verificando tu conexión, un momento…",
    needToken: "Completa la verificación de seguridad para confirmar tu cita.",
    expired: "Tu verificación expiró. Tócala para continuar.",
    broken: "Tu navegador bloqueó la verificación de seguridad. Reactívala y vuelve a intentar.",
    noKey: "La verificación de seguridad no está disponible ahora. Te agendo por WhatsApp.",
  };

  const form = document.querySelector("[data-booking]");
  if (!form) return;
  const q = (sel) => form.querySelector(sel);

  const ui = {
    categories: q("[data-service-categories]"),
    catHint: form.querySelector("[data-cat-swipe-hint]"),
    catWrap: form.querySelector(".service-categories-wrap"),
    services: q("[data-service-options]"),
    strip: q("[data-date-strip]"),
    prev: q("[data-date-prev]"),
    next: q("[data-date-next]"),
    times: q("[data-time-grid]"),
    submit: q("[data-submit]"),
    message: q("[data-form-message]"),
    summary: q("[data-summary]"),
    success: q("[data-success]"),
    turnstile: q("[data-turnstile]"),
    notice: q("[data-ts-notice]"),
    noticeText: q("[data-ts-notice-text]"),
    retry: q("[data-ts-retry]"),
    whatsapp: q("[data-ts-whatsapp]"),
  };

  const state = {
    config: null,
    dates: [],
    page: 0,
    category: null,
    serviceId: null,
    date: null,
    time: null,
    slots: new Map(),
    loading: false,
    tsStatus: TS.OFF,
    tsId: null,
    tsToken: null,
    tsTimer: null,
    tsRetries: 0,
    submitting: false,
    formToken: null,
  };

  /*  utilidades */
  const parseDate = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
  const isoDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const formatDateLong = (iso) => { const d = parseDate(iso); return `${DOW_LONG[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
  const formatTime = (hhmm) => {
    const [h, m] = hhmm.split(":").map(Number);
    return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "a. m." : "p. m."}`;
  };
  const formatDuration = (min) => {
    if (!min) return "";
    const h = Math.floor(min / 60);
    const m = min % 60;
    if (h > 0 && m > 0) return `${h} h ${m} min`;
    if (h > 0) return `${h} h`;
    return `${m} min`;
  };
  const pageSize = () => (mobile.matches ? 5 : 7);
  const service = () => state.config?.services.find((s) => s.id === state.serviceId);
  const CACHE_TTL_MS = 60000;
  const daySlots = (iso) => state.slots.get(state.serviceId)?.days?.get(iso);

  function h(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k === "disabled") node.disabled = Boolean(v);
      else if (k === "hidden") { if (v) node.hidden = true; }
      else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v);
    }
    for (const c of [].concat(children)) node.append(c);
    return node;
  }

  function setCategory(catId) {
    state.category = catId;
    if (ui.categories) {
      ui.categories.querySelectorAll(".service-cat-btn").forEach((btn) => {
        const active = btn.dataset.cat === catId;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", String(active));
        if (active) {
          btn.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
        }
      });
    }
    if (ui.services) {
      ui.services.querySelectorAll(".service-option").forEach((opt) => {
        opt.hidden = opt.dataset.category !== catId;
      });
    }
  }

  function updateCategoryScrollState() {
    if (!ui.categories || ui.categories.clientWidth <= 0) return;
    const { scrollLeft, scrollWidth, clientWidth } = ui.categories;
    const maxScroll = Math.round(scrollWidth - clientWidth);
    const hasOverflow = maxScroll > 12;
    const canScrollRight = hasOverflow && Math.round(scrollLeft) < maxScroll - 12;
    const canScrollLeft = hasOverflow && Math.round(scrollLeft) > 12;

    const wrap = ui.catWrap || ui.categories.closest(".service-categories-wrap");
    if (wrap) {
      wrap.classList.toggle("can-scroll-right", canScrollRight);
      wrap.classList.toggle("can-scroll-left", canScrollLeft);
    }
    const hint = ui.catHint || form.querySelector("[data-cat-swipe-hint]");
    if (hint) {
      hint.hidden = !canScrollRight;
      hint.classList.toggle("is-visible", canScrollRight);
    }
  }

  const CAT_ICONS = {
    combos: '<svg class="icon icon-cat" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z"/><path d="M19 2l.8 2.2L22 5l-2.2.8L19 8l-.8-2.2L16 5l2.2-.8z"/></svg>',
    unas: '<svg class="icon icon-cat" viewBox="0 0 24 24" aria-hidden="true"><rect x="10" y="3" width="4" height="6.5" rx="1"/><rect x="6" y="9.5" width="12" height="11.5" rx="2.5"/><path d="M9.5 13.5v4"/></svg>',
    cejas: '<svg class="icon icon-cat" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11c3.5-5 9.5-6 18-2.5" stroke-width="2.2" stroke-linecap="round"/><path d="M5 17c2.5-2.5 5-3.5 7-3.5s4.5 1 7 3.5"/></svg>',
    pestanas: '<svg class="icon icon-cat" viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 11c2.5 4 14.5 4 17 0"/><path d="M5.5 13.5l-2 3M9 14.5l-1 3.5M12 14.8v3.7M15 14.5l1 3.5M18.5 13.5l2 3"/></svg>',
  };

  function renderCatIcon(catId) {
    const raw = CAT_ICONS[catId];
    if (!raw) return null;
    const t = document.createElement("template");
    t.innerHTML = raw;
    return t.content.firstElementChild;
  }

  function renderCategories() {
    if (!ui.categories || !state.config?.categories) return;
    ui.categories.replaceChildren(...state.config.categories.map((cat) => {
      const count = state.config.services.filter((s) => s.category === cat.id).length;
      const isActive = cat.id === state.category;
      const icon = renderCatIcon(cat.id);
      const children = [];
      if (icon) children.push(icon);
      children.push(
        h("span", { text: cat.name }),
        h("span", { class: "service-cat-count", text: `(${count})` })
      );
      const btn = h("button", {
        class: `service-cat-btn${isActive ? " is-active" : ""}`,
        type: "button",
        role: "tab",
        "aria-selected": String(isActive),
        "data-cat": cat.id,
      }, children);
      btn.addEventListener("click", () => setCategory(cat.id));
      return btn;
    }));
    requestAnimationFrame(updateCategoryScrollState);
  }

  function renderServices() {
    if (!state.category && state.config?.categories?.length) {
      state.category = state.config.categories[0].id;
    }
    renderCategories();
    ui.services.replaceChildren(...state.config.services.map((s) => {
      const input = h("input", { type: "radio", name: "service_id", value: s.id });
      input.addEventListener("change", () => selectService(s.id));
      const durationText = s.duration ? formatDuration(s.duration) : "";
      const metaChildren = [
        h("span", { class: "service-option-cat", text: CATEGORY_LABEL[s.category] ?? s.category }),
      ];
      if (durationText) {
        metaChildren.push(
          h("span", { class: "service-option-dot", text: "·" }),
          h("span", { class: "service-option-duration", text: durationText })
        );
      }
      return h("label", {
        class: "service-option",
        "data-category": s.category,
        hidden: s.category !== state.category,
      }, [
        input,
        h("span", { class: "radio", "aria-hidden": "true" }),
        h("span", {}, [
          h("span", { class: "service-option-name", text: s.name }),
          h("span", { class: "service-option-meta" }, metaChildren),
        ]),
      ]);
    }));
  }

  async function selectService(id, { scroll = false } = {}) {
    state.serviceId = id;
    const s = state.config?.services.find((x) => x.id === id);
    if (s && s.category !== state.category) {
      setCategory(s.category);
    }
    const radio = ui.services.querySelector(`input[value="${CSS.escape(id)}"]`);
    if (radio) radio.checked = true;
    clearError("service_id");
    state.time = null;
    renderSummary();
    if (scroll) document.getElementById("agendar").scrollIntoView();
    await loadAvailability();
  }

  async function loadAvailability({ force = false } = {}) {
    const id = state.serviceId;
    if (!id) return;
    const cached = state.slots.get(id);
    if (!force && cached && (Date.now() - cached.time < CACHE_TTL_MS)) {
      afterAvailability();
      return;
    }

    state.loading = true;
    renderTimes();
    try {
      const params = new URLSearchParams({ service: id, from: state.dates[0], days: String(state.dates.length) });
      const res = await fetch(`/api/availability?${params}`);
      if (!res.ok) throw new Error(`availability ${res.status}`);
      const data = await res.json();
      state.slots.set(id, { time: Date.now(), days: new Map(data.days.map((d) => [d.date, d.slots])) });
    } catch (err) {
      console.error(err);
      state.loading = false;
      ui.times.replaceChildren(h("p", { class: "muted", text: "No pudimos cargar los horarios. Intenta de nuevo en un momento." }));
      return;
    }
    state.loading = false;
    if (state.serviceId === id) afterAvailability();
  }

  function afterAvailability() {
    // Si la fecha elegida ya no tiene cupos, pasa a la primera con disponibilidad.
    if (!state.date || !hasAvailability(state.date)) {
      state.date = state.dates.find(hasAvailability) ?? null;
      if (state.date) state.page = Math.floor(state.dates.indexOf(state.date) / pageSize());
    }
    if (state.time && !daySlots(state.date)?.some((s) => s.time === state.time && s.available)) state.time = null;
    renderDates();
    renderTimes();
    renderSummary();
  }

  function isOpenDay(iso) {
    return state.config.open_weekdays.includes((parseDate(iso).getDay() + 6) % 7); // 0 = lunes
  }

  function hasAvailability(iso) {
    const slots = daySlots(iso);
    return slots ? slots.some((s) => s.available) : isOpenDay(iso);
  }

  function renderDates() {
    const size = pageSize();
    const pages = Math.ceil(state.dates.length / size);
    state.page = Math.min(Math.max(0, state.page), pages - 1);
    const visible = state.dates.slice(state.page * size, state.page * size + size);

    ui.strip.style.gridTemplateColumns = `repeat(${size}, minmax(0, 1fr))`;
    ui.strip.replaceChildren(...visible.map((iso) => {
      const d = parseDate(iso);
      const disabled = !hasAvailability(iso);
      const btn = h("button", {
        type: "button",
        class: "date-btn",
        "aria-pressed": String(iso === state.date),
        "aria-label": `${formatDateLong(iso)}${disabled ? ", sin horarios" : ""}`,
        disabled,
      }, [
        h("span", { class: "dow", text: DOW[d.getDay()] }),
        h("span", { class: "day", text: String(d.getDate()) }),
        h("span", { class: "mon", text: MONTHS[d.getMonth()] }),
      ]);
      btn.addEventListener("click", () => {
        state.date = iso;
        state.time = null;
        renderDates();
        renderTimes();
        renderSummary();
      });
      return btn;
    }));
    ui.prev.disabled = state.page === 0;
    ui.next.disabled = state.page >= pages - 1;
  }

  function renderTimes() {
    if (!state.serviceId) {
      ui.times.replaceChildren(h("p", { class: "muted", text: "Elige primero un servicio." }));
      return;
    }
    if (state.loading) {
      ui.times.replaceChildren(h("p", { class: "muted", text: "Buscando horarios disponibles…" }));
      return;
    }
    const slots = state.date ? daySlots(state.date) : null;
    if (!slots || !slots.length || !slots.some((s) => s.available)) {
      ui.times.replaceChildren(h("p", { class: "muted", text: state.date ? "No hay horarios disponibles este día." : "No hay horarios disponibles en las próximas semanas. Escríbenos por WhatsApp." }));
      return;
    }
    ui.times.replaceChildren(...slots.map((s) => {
      const btn = h("button", {
        type: "button",
        class: "time-btn",
        "aria-pressed": String(s.time === state.time),
        "aria-label": `${formatTime(s.time)}${s.available ? "" : ", no disponible"}`,
        disabled: !s.available,
        text: formatTime(s.time),
      });
      btn.addEventListener("click", () => {
        state.time = s.time;
        clearError("time");
        renderTimes();
        renderSummary();
      });
      return btn;
    }));
  }

  function renderSummary() {
    const s = service();
    const set = (key, value) => { form.querySelector(`[data-sum="${key}"]`).textContent = value || "—"; };
    set("service", s?.name);
    set("date", state.date && formatDateLong(state.date));
    set("time", state.time && formatTime(state.time));
    set("price", s?.price_label);
  }

  function initTurnstile() {
    const siteKey = state.config.turnstile_site_key;
    if (!siteKey) {
      // Sin clave pública no hay token que obtener, y el Worker rechaza igual.
      state.tsStatus = TS.OFF;
      showNotice(TS_MSG.noKey);
      return;
    }
    window.onTurnstileLoad = () => {
      // El script puede cargarse y llegar sin `turnstile` (bloqueador parcial).
      if (typeof window.turnstile?.render !== "function") return failTurnstile("neutered");
      clearTimeout(state.tsTimer);
      try {
        state.tsId = window.turnstile.render(ui.turnstile, {
          sitekey: siteKey,
          language: "es",
          theme: "light",
          appearance: "interaction-only",
          callback: (token) => { state.tsToken = token; ui.notice.hidden = true; },
          "expired-callback": () => {
            // El widget sigue vivo: solo hay que volver a tocarlo.
            state.tsToken = null;
            showNotice(TS_MSG.expired);
            nudgeWidget();
          },
          "error-callback": () => { state.tsToken = null; failTurnstile("widget-error"); },
        });
        state.tsStatus = TS.READY;
      } catch (err) {
        console.error(err);
        failTurnstile("render-error");
      }
    };
    loadTurnstileScript();
  }

  function loadTurnstileScript() {
    state.tsStatus = TS.LOADING;
    clearTimeout(state.tsTimer);
    // Red lenta o DNS bloqueado: el onerror no siempre salta, así que hay plazo.
    state.tsTimer = setTimeout(() => failTurnstile("timeout"), TS_TIMEOUT_MS);
    const script = document.createElement("script");
    script.src = `${TS_SRC}&ts=${Date.now()}`;
    script.async = true;
    script.onerror = () => failTurnstile("blocked");
    document.head.append(script);
  }

  function failTurnstile(reason) {
    clearTimeout(state.tsTimer);
    if (state.tsStatus === TS.BROKEN) return;
    state.tsStatus = TS.BROKEN;
    state.tsToken = null;
    console.warn("Verificación de seguridad no disponible:", reason);
    showNotice(TS_MSG.broken, { retry: state.tsRetries < TS_MAX_RETRIES });
  }

  function nudgeWidget() {
    if (state.tsId === null || typeof window.turnstile?.reset !== "function") return;
    try { window.turnstile.reset(state.tsId); } catch (err) { console.warn(err); }
  }

  function retryTurnstile() {
    if (state.tsRetries >= TS_MAX_RETRIES) return;
    state.tsRetries += 1;
    state.tsToken = null;
    if (state.tsId !== null && typeof window.turnstile?.remove === "function") {
      try { window.turnstile.remove(state.tsId); } catch (err) { console.warn(err); }
    }
    state.tsId = null;
    ui.turnstile.replaceChildren();
    ui.notice.hidden = true;
    setMessage("");
    loadTurnstileScript();
  }

  function showNotice(text, { retry = false } = {}) {
    ui.noticeText.textContent = text;
    ui.retry.hidden = !retry;
    ui.whatsapp.href = whatsappSummaryUrl();
    ui.notice.hidden = false;
  }

  function newFormToken() {
    const bytes = new Uint8Array(16);
    window.crypto.getRandomValues(bytes);
    return [...bytes].map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  function showError(field, msg) {
    const node = form.querySelector(`[data-error="${field}"]`);
    if (node) { node.textContent = msg; node.hidden = false; }
    const input = form.elements[field];
    if (input && input.setAttribute) input.setAttribute("aria-invalid", "true");
  }

  function clearError(field) {
    const node = form.querySelector(`[data-error="${field}"]`);
    if (node) { node.hidden = true; node.textContent = ""; }
    const input = form.elements[field];
    if (input && input.removeAttribute) input.removeAttribute("aria-invalid");
  }

  function setMessage(msg, { link = null } = {}) {
    ui.message.replaceChildren();
    if (!msg) { ui.message.hidden = true; return; }
    ui.message.append(msg);
    if (link) ui.message.append(h("a", { href: link, target: "_blank", rel: "noopener", text: "Escríbenos por WhatsApp \u2192\uFE0E" }));
    ui.message.hidden = false;
  }

  function clientValidate() {
    const errors = {};
    if (!state.serviceId) errors.service_id = "Elige un servicio.";
    if (!state.date || !state.time) errors.time = "Elige una fecha y una hora.";
    const text = (name) => form.elements[name].value.trim();
    if (text("name").length < 2) errors.name = "Escribe tu nombre.";
    const digits = text("phone").replace(/\D/g, "").replace(/^57(?=3\d{9}$)/, "");
    if (!/^3\d{9}$/.test(digits)) errors.phone = "Escribe un celular válido, p. ej. 300 000 0000.";
    return errors;
  }

  function gateCheck() {
    if (state.tsStatus === TS.OFF) return { blocked: true, text: TS_MSG.noKey };
    if (state.tsStatus === TS.LOADING) return { blocked: true, text: TS_MSG.loading };
    if (state.tsToken) return { blocked: false };
    if (state.tsStatus === TS.READY) return { blocked: true, text: TS_MSG.needToken, nudge: true };
    return { blocked: true, text: TS_MSG.broken, retry: state.tsRetries < TS_MAX_RETRIES };
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (state.submitting) return;
    ["service_id", "time", "name", "phone"].forEach(clearError);
    setMessage("");

    const errors = clientValidate();
    if (Object.keys(errors).length) {
      Object.entries(errors).forEach(([f, m]) => showError(f, m));
      const first = form.querySelector(".field-error:not([hidden])");
      first?.closest("fieldset, .field")?.scrollIntoView({ block: "center" });
      return;
    }
    // Toda rama bloqueada dice qué pasó y deja una salida: nunca un callejón sin salida.
    const gate = gateCheck();
    if (gate.blocked) {
      setMessage(gate.text);
      showNotice(gate.text, { retry: gate.retry });
      if (gate.nudge) nudgeWidget();
      return;
    }

    state.submitting = true;
    ui.submit.disabled = true;
    const payload = {
      service_id: state.serviceId,
      date: state.date,
      time: state.time,
      name: form.elements.name.value,
      phone: form.elements.phone.value,
      notes: form.elements.notes.value,
      turnstile_token: state.tsToken,
      form_token: state.formToken,
    };

    try {
      const res = await fetch("/api/bookings", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (res.status === 201) return showSuccess(data);
      if (res.status === 422 && data.fields) Object.entries(data.fields).forEach(([f, m]) => showError(f, m));
      if (res.status === 409) {
        state.time = null;
        await loadAvailability({ force: true });
      }
      setMessage(data.error || "No pudimos agendar la cita. Intenta de nuevo.", { link: data.whatsapp_url });
    } catch (err) {
      console.error(err);
      setMessage("Sin conexión. Revisa tu internet e intenta de nuevo.");
    } finally {
      state.submitting = false;
      ui.submit.disabled = false;
      state.tsToken = null;
      if (state.tsStatus === TS.READY) nudgeWidget();
    }
  }

  function whatsappSummaryUrl() {
    const number = state.config?.whatsapp;
    if (!number) return "#";
    const s = service();
    const val = (name) => form.elements[name]?.value.trim();
    const lines = ["Hola Angélica ✨ Quiero agendar una cita:", ""];
    if (s) lines.push(`• Servicio: ${s.name}`);
    if (state.date) lines.push(`• Fecha: ${formatDateLong(state.date)}`);
    if (state.time) lines.push(`• Hora: ${formatTime(state.time)}`);
    if (val("name")) lines.push(`• Nombre: ${val("name")}`);
    if (val("notes")) lines.push(`• Notas: ${val("notes")}`);
    lines.push("", "¿Me confirmas, por favor?");
    return `https://wa.me/${number}?text=${encodeURIComponent(lines.join("\n"))}`;
  }

  function showSuccess(data) {
    form.classList.add("is-booked");
    form.querySelector("[data-success-code]").textContent = data.code;
    form.querySelector("[data-success-link]").href = data.whatsapp_url;

    const s = service();
    const sName = data.summary?.service || s?.name || "Servicio en estudio";
    const dText = data.summary?.date && data.summary?.time
      ? `${data.summary.date} · ${data.summary.time}`
      : (state.date && state.time ? `${formatDateLong(state.date)} · ${formatTime(state.time)}` : "");
    const cName = form.elements.name?.value?.trim() || "";

    const sEl = form.querySelector("[data-success-service]");
    const dtEl = form.querySelector("[data-success-datetime]");
    const nEl = form.querySelector("[data-success-client]");
    const nWrap = form.querySelector("[data-success-client-wrap]");

    if (sEl) sEl.textContent = sName;
    if (dtEl) dtEl.textContent = dText || "Horario confirmado";
    if (nEl) nEl.textContent = cName || "Clienta";
    if (nWrap) nWrap.hidden = !cName;

    const calBtn = form.querySelector("[data-success-gcal]");
    if (calBtn && state.date && state.time) {
      try {
        const [h, m] = state.time.split(":").map(Number);
        const dur = s?.duration || 60;
        const start = new Date(`${state.date}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`);
        const end = new Date(start.getTime() + dur * 60000);
        const pad = (n) => String(n).padStart(2, "0");
        const fmtG = (d) => `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}T${pad(d.getHours())}${pad(d.getMinutes())}00`;
        const locStr = data.location ? `${data.location.address}, ${data.location.neighborhood}, Cali` : "La Flora, Cali";
        const detailsStr = `Cita confirmada en AC Luxury Aesthetics.\nCódigo: ${data.code}\nServicio: ${sName}\nHorario: ${dText}\nDirección: ${locStr}\n\nGuía de Cuidados: https://angienails.com/cuidados`;
        calBtn.href = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(`Cita: ${sName} · AC Luxury Aesthetics`)}&dates=${fmtG(start)}/${fmtG(end)}&details=${encodeURIComponent(detailsStr)}&location=${encodeURIComponent(locStr)}`;
        calBtn.hidden = false;
      } catch (e) {
        calBtn.hidden = true;
      }
    }

    if (data.location) {
      const locBox = form.querySelector("[data-success-location]");
      if (locBox) {
        const addrEl = form.querySelector("[data-success-address]");
        const refEl = form.querySelector("[data-success-ref]");
        const mapsLink = form.querySelector("[data-success-maps]");
        const wazeLink = form.querySelector("[data-success-waze]");
        if (addrEl) addrEl.textContent = data.location.address;
        if (refEl) refEl.textContent = `${data.location.neighborhood} · ${data.location.reference}`;
        if (mapsLink && data.location.maps_url) mapsLink.href = data.location.maps_url;
        if (wazeLink && data.location.waze_url) wazeLink.href = data.location.waze_url;
        locBox.hidden = false;
      }
    }
    ui.summary.hidden = true;
    ui.success.hidden = false;
    ui.success.focus();
    state.slots.delete(state.serviceId);
    document.getElementById("agendar")?.scrollIntoView({ behavior: "smooth" });
  }

  function resetForNewBooking() {
    form.classList.remove("is-booked");
    ["name", "phone", "notes"].forEach((n) => { form.elements[n].value = ""; });
    state.time = null;
    state.formToken = newFormToken();
    const locBox = form.querySelector("[data-success-location]");
    if (locBox) locBox.hidden = true;
    ui.success.hidden = true;
    ui.summary.hidden = false;
    renderSummary();
    loadAvailability();
    document.getElementById("agendar").scrollIntoView({ behavior: "smooth" });
  }

  async function init() {
    try {
      state.config = await window.acConfig;
    } catch (err) {
      console.error(err);
      ui.services.replaceChildren(h("p", { class: "muted", text: "No pudimos cargar la agenda. Recarga la página o escríbenos por WhatsApp." }));
      return;
    }

    const first = parseDate(state.config.window.first);
    const last = parseDate(state.config.window.last);
    for (let d = new Date(first); d <= last; d.setDate(d.getDate() + 1)) state.dates.push(isoDate(d));

    renderServices();
    renderDates();
    renderTimes();
    renderSummary();
    state.formToken = newFormToken();
    initTurnstile();

    ui.prev.addEventListener("click", () => { state.page -= 1; renderDates(); });
    ui.next.addEventListener("click", () => { state.page += 1; renderDates(); });
    if (ui.categories) {
      ui.categories.addEventListener("scroll", updateCategoryScrollState, { passive: true });
      if ("ResizeObserver" in window) {
        new ResizeObserver(updateCategoryScrollState).observe(ui.categories);
      }
      window.addEventListener("resize", updateCategoryScrollState, { passive: true });
      if (document.fonts?.ready) {
        document.fonts.ready.then(updateCategoryScrollState);
      }
    }
    mobile.addEventListener("change", () => {
      if (state.date) state.page = Math.floor(state.dates.indexOf(state.date) / pageSize());
      renderDates();
    });
    form.addEventListener("submit", onSubmit);
    form.querySelector("[data-new-booking]").addEventListener("click", resetForNewBooking);
    const copyBtn = form.querySelector("[data-copy-code]");
    if (copyBtn) {
      copyBtn.addEventListener("click", async () => {
        const codeEl = form.querySelector("[data-success-code]");
        const code = codeEl?.textContent?.trim();
        if (!code) return;
        const statusEl = copyBtn.querySelector("[data-copy-status]");
        const copyIcon = copyBtn.querySelector(".icon-copy");
        const checkIcon = copyBtn.querySelector(".icon-check");

        const showCopied = () => {
          if (statusEl) statusEl.textContent = "¡Copiado!";
          copyBtn.classList.add("is-copied");
          if (copyIcon) copyIcon.hidden = true;
          if (checkIcon) checkIcon.hidden = false;
          setTimeout(() => {
            if (statusEl) statusEl.textContent = "Copiar";
            copyBtn.classList.remove("is-copied");
            if (copyIcon) copyIcon.hidden = false;
            if (checkIcon) checkIcon.hidden = true;
          }, 2200);
        };

        try {
          if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(code);
            showCopied();
          } else {
            throw new Error("Clipboard API unavailable");
          }
        } catch {
          const ta = document.createElement("textarea");
          ta.value = code;
          ta.style.position = "fixed";
          ta.style.opacity = "0";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          document.body.removeChild(ta);
          showCopied();
        }
      });
    }
    ui.retry.addEventListener("click", retryTurnstile);
    ["name", "phone"].forEach((n) => form.elements[n].addEventListener("input", () => {
      clearError(n);
      // El enlace de salida lleva los datos que ya escribió.
      if (!ui.notice.hidden) ui.whatsapp.href = whatsappSummaryUrl();
    }));

    document.addEventListener("click", (e) => {
      const link = e.target.closest("[data-book-category]");
      if (!link) return;
      e.preventDefault();
      const cat = link.dataset.bookCategory;
      if (service()?.category === cat) { document.getElementById("agendar").scrollIntoView(); return; }
      const firstOfCat = state.config.services.find((s) => s.category === cat);
      if (firstOfCat) selectService(firstOfCat.id, { scroll: true });
    });

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && state.serviceId) {
        state.slots.clear();
        loadAvailability({ force: true });
      }
    });
  }

  init();
})();
