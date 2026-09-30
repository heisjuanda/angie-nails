"""Pruebas en navegador real (Microsoft Edge vía Playwright) contra el Worker local.

Emulan lo que hacen la clienta y Angélica: reservar desde el celular,
equivocarse en el formulario, perder un horario por una reserva simultánea,
entrar al panel, confirmar, cancelar y bloquear días.
"""

import re
import time

import pytest

import messages
from helpers import booking_payload

pytestmark = pytest.mark.e2e

sync_api = pytest.importorskip("playwright.sync_api")
MOBILE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True, "device_scale_factor": 2}
DESKTOP = {"viewport": {"width": 1366, "height": 900}}


@pytest.fixture(scope="session")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="msedge")
        except Exception as e:  # pragma: no cover
            pytest.skip(f"Microsoft Edge no disponible: {e}")
        yield b
        b.close()


class Page:
    """Envoltura que registra errores de JavaScript y respuestas HTTP >= 400 por separado."""

    def __init__(self, browser, base_url, **ctx):
        self.context = browser.new_context(base_url=base_url, **ctx)
        self.page = self.context.new_page()
        self.errors: list[str] = []          # excepciones y console.error de la app
        self.http_errors: list[str] = []     # respuestas >= 400 (algunas son esperadas)
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", self._on_console)
        self.page.on("response", lambda r: r.status >= 400 and self.http_errors.append(f"{r.status} {r.url}"))

    def _on_console(self, msg):
        # El navegador anota cada respuesta 4xx como "Failed to load resource"; eso se revisa en http_errors.
        if msg.type == "error" and not msg.text.startswith("Failed to load resource"):
            self.errors.append(msg.text)

    def close(self):
        self.context.close()


@pytest.fixture
def mobile(browser, server):
    p = Page(browser, server.base_url, **MOBILE)
    yield p
    p.close()


@pytest.fixture
def desktop(browser, server):
    p = Page(browser, server.base_url, **DESKTOP)
    yield p
    p.close()


def open_booking(page):
    page.goto("/", wait_until="load")
    page.locator("#agendar").scroll_into_view_if_needed()
    page.wait_for_selector(".service-option")


def pick(page, day, time, service_name):
    page.locator("label.service-option", has_text=service_name).click()
    page.wait_for_selector(".time-btn")  # espera a que cargue la disponibilidad
    label = messages.format_date_es(day)
    for _ in range(6):   # avanza semanas hasta ver el día
        btn = page.locator(f".date-btn[aria-label^='{label}']")
        if btn.count():
            btn.click()
            break
        page.click("[data-date-next]")
    else:
        pytest.fail(f"No se encontró el día {label} en el calendario")
    page.locator(f".time-btn[aria-label='{messages.format_time_es(time)}']").click()


def fill_customer(page, name="Clienta Navegador"):
    page.fill("input[name=name]", name)
    page.fill("input[name=phone]", "311 222 3344")
    page.fill("input[name=neighborhood]", "El Peñón")
    page.fill("input[name=address]", "Avenida 4 Oeste # 2-10 apto 301")


def wait_js(page, expression: str, timeout: float = 20):
    """Como wait_for_function, pero sin eval: la CSP del sitio lo bloquea (a propósito)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if page.evaluate(expression):
            return
        page.wait_for_timeout(200)
    pytest.fail(f"Timeout esperando: {expression}")


def wait_turnstile(page):
    wait_js(page, "document.querySelector('[name=cf-turnstile-response]')?.value?.length > 0")


def admin_login(page, password):
    page.goto("/admin/", wait_until="load")
    page.fill("input[name=password]", password)
    page.click("[data-login-form] button[type=submit]")
    page.wait_for_selector("[data-view=app]:not([hidden])")


# --------------------------------------------------------------- clienta

def test_customer_books_from_phone(mobile, server, free_day):
    page = mobile.page
    open_booking(page)
    pick(page, free_day, "08:00", "Semipermanente")
    fill_customer(page)
    assert page.text_content("[data-sum=service]") == "Semipermanente"
    assert page.text_content("[data-sum=time]") == "8:00 a. m."
    wait_turnstile(page)
    page.click("[data-submit]")
    page.wait_for_selector("[data-success]:not([hidden])")

    code = page.text_content("[data-success-code]")
    assert re.fullmatch(r"AC-[A-Z0-9]{5}", code)
    href = page.get_attribute("[data-success-link]", "href")
    assert href.startswith("https://wa.me/") and code in href
    row = server.sql(f"SELECT customer_name, phone, status FROM bookings WHERE code = '{code}'")[0]
    assert row == {"customer_name": "Clienta Navegador", "phone": "573112223344", "status": "pending"}
    assert mobile.errors == [] and mobile.http_errors == []


def test_form_errors_are_shown_without_calling_api(mobile):
    page = mobile.page
    open_booking(page)
    requests = []
    page.on("request", lambda r: "/api/bookings" in r.url and requests.append(r))
    page.click("[data-submit]")
    visible = page.locator(".field-error:not([hidden])")
    assert visible.count() >= 5
    page.fill("input[name=phone]", "123")
    page.click("[data-submit]")
    assert "celular válido" in page.text_content("[data-error=phone]")
    assert requests == []


def test_slot_taken_meanwhile_shows_message_and_refreshes(desktop, server, free_day):
    page = desktop.page
    open_booking(page)
    pick(page, free_day, "10:00", "Polygel")
    fill_customer(page)
    wait_turnstile(page)

    # Otra persona reserva ese mismo horario mientras la clienta llena el formulario.
    import httpx
    r = httpx.post(f"{server.base_url}/api/bookings", json=booking_payload(free_day, "10:00", service="polygel"))
    assert r.status_code == 201

    page.click("[data-submit]")
    msg = page.locator("[data-form-message]")
    msg.wait_for(state="visible")
    assert "ya no está disponible" in msg.text_content()
    page.wait_for_selector(".time-btn[aria-label='10:00 a. m., no disponible']")
    assert page.text_content("[data-sum=time]") == "—"
    assert desktop.errors == []
    assert [e.split()[0] for e in desktop.http_errors] == ["409"]


def test_book_category_button_preselects_service(desktop):
    page = desktop.page
    page.goto("/", wait_until="load")
    page.click("[data-book-category=pestanas]")
    wait_js(page, "document.querySelector('[data-sum=service]').textContent !== '—'")
    assert page.text_content("[data-sum=service]") == "Extensiones pelo a pelo"


@pytest.mark.parametrize("path", ["/", "/admin/"])
def test_no_horizontal_overflow_on_phone(mobile, path):
    mobile.page.goto(path, wait_until="load")
    mobile.page.wait_for_timeout(500)
    assert mobile.page.evaluate("document.documentElement.scrollWidth") <= 390
    assert mobile.errors == [] and mobile.http_errors == []


def test_portfolio_filter(desktop):
    page = desktop.page
    page.goto("/", wait_until="load")
    page.click("[data-filter=cejas]")
    visible = page.locator(".portfolio-item:visible")
    assert visible.count() == 2
    assert all(v.get_attribute("data-category") == "cejas" for v in visible.all())
    page.click("[data-filter=todo]")
    assert page.locator(".portfolio-item:visible").count() == 8


# ------------------------------------------------------------- Angélica

def test_admin_wrong_password(desktop):
    page = desktop.page
    page.goto("/admin/", wait_until="load")
    page.fill("input[name=password]", "equivocada")
    page.click("[data-login-form] button[type=submit]")
    err = page.locator("[data-login-error]")
    err.wait_for(state="visible")
    assert "incorrecta" in err.text_content()
    assert page.locator("[data-view=app]").is_hidden()


def test_admin_confirms_and_cancels_bookings(desktop, server, free_day):
    import httpx
    codes = []
    for t, name in (("08:00", "Paola Ríos"), ("11:00", "Camila Díaz")):
        r = httpx.post(f"{server.base_url}/api/bookings", json=booking_payload(free_day, t, name=name))
        codes.append(r.json()["code"])

    page = desktop.page
    admin_login(page, server.admin_password)
    card = page.locator(f".booking-card[data-code='{codes[0]}']")
    card.wait_for()
    assert "Paola Ríos" in card.text_content() and "Pendiente" in card.text_content()

    # Confirmar → aviso con enlace de WhatsApp hacia la clienta.
    card.locator("[data-action=confirmed]").click()
    toast = page.locator("[data-toast]")
    toast.wait_for(state="visible")
    assert "confirmada" in toast.text_content()
    assert toast.locator("a").get_attribute("href").startswith("https://wa.me/573001234567")
    page.wait_for_selector(f".booking-card[data-code='{codes[0]}'] .badge-confirmed")

    # Cancelar exige doble toque.
    cancel = page.locator(f".booking-card[data-code='{codes[1]}'] [data-action=cancelled]")
    cancel.click()
    assert "Seguro" in cancel.text_content()
    assert server.sql(f"SELECT status FROM bookings WHERE code = '{codes[1]}'")[0]["status"] == "pending"
    cancel.click()
    page.wait_for_selector(f".booking-card[data-code='{codes[1]}'] .badge-cancelled")
    assert server.sql(f"SELECT status FROM bookings WHERE code = '{codes[1]}'")[0]["status"] == "cancelled"

    # Filtro por estado.
    page.click("[data-status=confirmed]")
    page.wait_for_selector(f".booking-card[data-code='{codes[0]}'] .badge-confirmed")
    assert page.locator(f".booking-card[data-code='{codes[1]}']").count() == 0
    assert desktop.errors == []


def test_admin_blocks_day_and_customer_sees_it_closed(browser, server, free_day):
    admin = Page(browser, server.base_url, **MOBILE)
    customer = Page(browser, server.base_url, **DESKTOP)
    try:
        page = admin.page
        admin_login(page, server.admin_password)
        page.click("[data-tab=bloqueos]")
        page.fill("[data-block-form] input[name=date]", free_day.isoformat())
        page.fill("[data-block-form] input[name=reason]", "Vacaciones")
        page.click("[data-block-form] button[type=submit]")
        page.wait_for_selector("[data-block-message]:has-text('bloqueado')")
        item = page.locator(".block-item", has_text="Vacaciones")
        item.wait_for()

        c = customer.page
        open_booking(c)
        c.locator("label.service-option", has_text="Henna").click()
        label = messages.format_date_es(free_day)
        for _ in range(6):
            btn = c.locator(f".date-btn[aria-label^='{label}']")
            if btn.count():
                break
            c.click("[data-date-next]")
        c.wait_for_selector(f".date-btn[aria-label='{label}, sin horarios']")
        assert c.locator(f".date-btn[aria-label^='{label}']").is_disabled()

        # Quitar el bloqueo.
        item.locator("button").click()
        item.wait_for(state="detached")
        assert server.sql(f"SELECT COUNT(*) AS n FROM blocked_slots WHERE date = '{free_day.isoformat()}'")[0]["n"] == 0
        assert admin.errors == [] and customer.errors == []
    finally:
        admin.close()
        customer.close()


def test_admin_session_survives_reload_and_logout(desktop, server):
    page = desktop.page
    admin_login(page, server.admin_password)
    page.reload(wait_until="load")
    page.wait_for_selector("[data-view=app]:not([hidden])")
    page.click("[data-logout]")
    page.wait_for_selector("[data-view=login]:not([hidden])")
    page.reload(wait_until="load")
    page.wait_for_selector("[data-view=login]:not([hidden])")
    cookies = [c for c in desktop.context.cookies() if c["name"] == "ac_admin"]
    assert cookies == [] or cookies[0]["value"] == ""
