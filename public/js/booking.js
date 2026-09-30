/* AC Luxury Aesthetics — reserva en tres pasos. */
(() => {
  const DOW = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
  const DOW_LONG = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
  const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const CATEGORY_LABEL = { unas: "Uñas", cejas: "Cejas", pestanas: "Pestañas" };
  const mobile = window.matchMedia("(max-width: 700px)");

  const form = document.querySelector("[data-booking]");
  if (!form) return;
  const q = (sel) => form.querySelector(sel);

  const ui = {
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
  };

  const state = {
    config: null,
    dates: [],            // todas las fechas de la ventana de reserva (YYYY-MM-DD)
    page: 0,
    serviceId: null,
    date: null,
    time: null,
    slots: new Map(),     // serviceId → Map(fecha → slots[])
    loading: false,
    turnstileId: null,
    turnstileToken: null,
    submitting: false,
  };

  /* ----------------------------------------------------------- utilidades */
  const parseDate = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d); };
  const isoDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const formatDateLong = (iso) => { const d = parseDate(iso); return `${DOW_LONG[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`; };
  const formatTime = (hhmm) => {
    const [h, m] = hhmm.split(":").map(Number);
    return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "a. m." : "p. m."}`;
  };
  const pageSize = () => (mobile.matches ? 5 : 7);
  const service = () => state.config?.services.find((s) => s.id === state.serviceId);
  const daySlots = (iso) => state.slots.get(state.serviceId)?.get(iso);

  function h(tag, attrs = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k === "disabled") node.disabled = Boolean(v);
      else if (v !== null && v !== undefined) node.setAttribute(k, v);
    }
    for (const c of [].concat(children)) node.append(c);
    return node;
  }

  /* ------------------------------------------------------------ paso 1 */
  function renderServices() {
    ui.services.replaceChildren(...state.config.services.map((s) => {
      const input = h("input", { type: "radio", name: "service_id", value: s.id });
      input.addEventListener("change", () => selectService(s.id));
      return h("label", { class: "service-option" }, [
        input,
        h("span", { class: "radio", "aria-hidden": "true" }),
        h("span", {}, [
          h("span", { class: "service-option-name", text: s.name }),
          h("span", { class: "service-option-cat", text: CATEGORY_LABEL[s.category] ?? s.category }),
        ]),
      ]);
    }));
  }

  async function selectService(id, { scroll = false } = {}) {
    state.serviceId = id;
    const radio = ui.services.querySelector(`input[value="${CSS.escape(id)}"]`);
    if (radio) radio.checked = true;
    clearError("service_id");
    state.time = null;
    renderSummary();
    if (scroll) document.getElementById("agendar").scrollIntoView();
    await loadAvailability();
  }

  /* ------------------------------------------------------------ paso 2 */
  async function loadAvailability({ force = false } = {}) {
    const id = state.serviceId;
    if (!id) return;
    if (!force && state.slots.has(id)) { afterAvailability(); return; }

    state.loading = true;
    renderTimes();
    try {
      const params = new URLSearchParams({ service: id, from: state.dates[0], days: String(state.dates.length) });
      const res = await fetch(`/api/availability?${params}`);
      if (!res.ok) throw new Error(`availability ${res.status}`);
      const data = await res.json();
      state.slots.set(id, new Map(data.days.map((d) => [d.date, d.slots])));
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

  /* ----------------------------------------------------------- resumen */
  function renderSummary() {
    const s = service();
    const set = (key, value) => { form.querySelector(`[data-sum="${key}"]`).textContent = value || "—"; };
    set("service", s?.name);
    set("date", state.date && formatDateLong(state.date));
    set("time", state.time && formatTime(state.time));
    set("price", s?.price_label);
  }

  /* --------------------------------------------------------- Turnstile */
  function initTurnstile() {
    const siteKey = state.config.turnstile_site_key;
    if (!siteKey) return;
    window.onTurnstileLoad = () => {
      state.turnstileId = window.turnstile.render(ui.turnstile, {
        sitekey: siteKey,
        language: "es",
        theme: "light",
        appearance: "interaction-only",
        callback: (token) => { state.turnstileToken = token; },
        "expired-callback": () => { state.turnstileToken = null; },
        "error-callback": () => { state.turnstileToken = null; },
      });
    };
    const script = document.createElement("script");
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=onTurnstileLoad";
    script.async = true;
    document.head.append(script);
  }

  function resetTurnstile() {
    state.turnstileToken = null;
    if (window.turnstile && state.turnstileId !== null) window.turnstile.reset(state.turnstileId);
  }

  /* ----------------------------------------------------------- errores */
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

  function setMessage(msg) {
    ui.message.textContent = msg || "";
    ui.message.hidden = !msg;
  }

  function clientValidate() {
    const errors = {};
    if (!state.serviceId) errors.service_id = "Elige un servicio.";
    if (!state.date || !state.time) errors.time = "Elige una fecha y una hora.";
    const text = (name) => form.elements[name].value.trim();
    if (text("name").length < 2) errors.name = "Escribe tu nombre.";
    const digits = text("phone").replace(/\D/g, "").replace(/^57(?=3\d{9}$)/, "");
    if (!/^3\d{9}$/.test(digits)) errors.phone = "Escribe un celular válido, p. ej. 300 000 0000.";
    if (text("neighborhood").length < 2) errors.neighborhood = "Escribe tu barrio.";
    if (text("address").length < 5) errors.address = "Escribe tu dirección.";
    return errors;
  }

  /* ------------------------------------------------------------ enviar */
  async function onSubmit(event) {
    event.preventDefault();
    if (state.submitting) return;
    ["service_id", "time", "name", "phone", "neighborhood", "address"].forEach(clearError);
    setMessage("");

    const errors = clientValidate();
    if (Object.keys(errors).length) {
      Object.entries(errors).forEach(([f, m]) => showError(f, m));
      const first = form.querySelector(".field-error:not([hidden])");
      first?.closest("fieldset, .field")?.scrollIntoView({ block: "center" });
      return;
    }
    if (state.config.turnstile_site_key && !state.turnstileToken) {
      setMessage("Estamos verificando la conexión, intenta de nuevo en unos segundos.");
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
      neighborhood: form.elements.neighborhood.value,
      address: form.elements.address.value,
      notes: form.elements.notes.value,
      turnstile_token: state.turnstileToken,
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
      setMessage(data.error || "No pudimos agendar la cita. Intenta de nuevo.");
    } catch (err) {
      console.error(err);
      setMessage("Sin conexión. Revisa tu internet e intenta de nuevo.");
    } finally {
      state.submitting = false;
      ui.submit.disabled = false;
      resetTurnstile();
    }
  }

  function showSuccess(data) {
    form.querySelector("[data-success-code]").textContent = data.code;
    form.querySelector("[data-success-link]").href = data.whatsapp_url;
    ui.summary.hidden = true;
    ui.success.hidden = false;
    ui.success.focus();
    state.slots.delete(state.serviceId); // el horario reservado ya no está libre
  }

  function resetForNewBooking() {
    ["name", "phone", "neighborhood", "address", "notes"].forEach((n) => { form.elements[n].value = ""; });
    state.time = null;
    ui.success.hidden = true;
    ui.summary.hidden = false;
    renderSummary();
    loadAvailability();
    document.getElementById("agendar").scrollIntoView();
  }

  /* ------------------------------------------------------------- init */
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
    initTurnstile();

    ui.prev.addEventListener("click", () => { state.page -= 1; renderDates(); });
    ui.next.addEventListener("click", () => { state.page += 1; renderDates(); });
    mobile.addEventListener("change", () => {
      if (state.date) state.page = Math.floor(state.dates.indexOf(state.date) / pageSize());
      renderDates();
    });
    form.addEventListener("submit", onSubmit);
    form.querySelector("[data-new-booking]").addEventListener("click", resetForNewBooking);
    ["name", "phone", "neighborhood", "address"].forEach((n) => form.elements[n].addEventListener("input", () => clearError(n)));

    // Botones "Agendar Uñas / Cejas / Pestañas" de la sección de servicios.
    document.addEventListener("click", (e) => {
      const link = e.target.closest("[data-book-category]");
      if (!link) return;
      e.preventDefault();
      const cat = link.dataset.bookCategory;
      if (service()?.category === cat) { document.getElementById("agendar").scrollIntoView(); return; }
      const firstOfCat = state.config.services.find((s) => s.category === cat);
      if (firstOfCat) selectService(firstOfCat.id, { scroll: true });
    });
  }

  init();
})();
