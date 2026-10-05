import re
import time
import urllib.parse

import pytest

import config
import messages
import mfa
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
    def __init__(self, browser, base_url, **ctx):
        self.context = browser.new_context(base_url=base_url, **ctx)
        self.page = self.context.new_page()
        self.errors: list[str] = []
        self.http_errors: list[str] = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("console", self._on_console)
        self.page.on("response", lambda r: r.status >= 400 and self.http_errors.append(f"{r.status} {r.url}"))

    def _on_console(self, msg):
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
    page.wait_for_selector(".time-btn")
    label = messages.format_date_es(day)
    for _ in range(6):
        btn = page.locator(f".date-btn[aria-label^='{label}']")
        if btn.count():
            btn.click()
            break
        page.click("[data-date-next]")
    else:
        pytest.fail(f"No se encontró el día {label} en el calendario")
    page.locator(f".time-btn[aria-label='{messages.format_time_es(time)}']").click()


def fill_customer(page, name="Clienta Navegador", phone="311 222 3344"):
    page.fill("input[name=name]", name)
    page.fill("input[name=phone]", phone)
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


def admin_login(page, password, totp_secret=None):
    page.goto("/admin/", wait_until="load")
    page.fill("input[name=password]", password)
    page.click("[data-login-form] button[type=submit]")
    if totp_secret:
        page.wait_for_selector("[data-mfa-field]:not([hidden])")
        page.fill("input[name=code]", mfa.current_code(totp_secret))
        page.click("[data-login-form] button[type=submit]")
    page.wait_for_selector("[data-view=app]:not([hidden])")


# Un número por clienta, para que el enlace de WhatsApp del panel sea comprobable.
PHONES = {"Paola Ríos": "300 111 0001", "Camila Díaz": "300 111 0002"}


#  clienta

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
    # Con la verificación funcionando no debe aparecer ningún aviso.
    assert page.locator("[data-ts-notice]").is_hidden()


def test_booking_says_so_when_turnstile_script_is_blocked(mobile, server, free_day):
    """Un adblocker que corta el script de Cloudflare no puede dejar el botón muerto."""
    page = mobile.page
    page.route("https://challenges.cloudflare.com/**", lambda route: route.abort())
    open_booking(page)
    pick(page, free_day, "08:00", "Semipermanente")
    fill_customer(page)

    # 1. El fallo se anuncia en vez de dejar el formulario en silencio.
    notice = page.locator("[data-ts-notice]")
    notice.wait_for(state="visible", timeout=25_000)
    assert "bloqueó" in page.text_content("[data-ts-notice-text]")
    assert page.locator("[data-ts-retry]").is_visible()

    # 2. Hay salida: WhatsApp con el resumen ya escrito y los datos que la clienta llenó.
    href = page.get_attribute("[data-ts-whatsapp]", "href")
    assert href.startswith("https://wa.me/")
    resumen = urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlparse(href).query)["text"][0])
    assert "Semipermanente" in resumen and "El Peñón" in resumen and "Avenida 4 Oeste" in resumen

    # 3. El submit explica, y no se crea ninguna cita: el servidor sigue exigiendo Turnstile.
    before = server.sql("SELECT COUNT(*) AS n FROM bookings")[0]["n"]
    page.click("[data-submit]")
    msg = page.locator("[data-form-message]")
    msg.wait_for(state="visible")
    assert "bloqueó" in msg.text_content()
    assert server.sql("SELECT COUNT(*) AS n FROM bookings")[0]["n"] == before

    # 4. Reintentar vuelve a intentarlo de verdad (y avisa de nuevo si sigue sin funcionar).
    page.click("[data-ts-retry]")
    notice.wait_for(state="visible", timeout=25_000)
    assert page.locator("[data-ts-whatsapp]").is_visible()


def test_booking_again_rotates_the_key(mobile, server, free_day):
    page = mobile.page
    open_booking(page)
    pick(page, free_day, "08:00", "Semipermanente")
    fill_customer(page)
    wait_turnstile(page)
    page.click("[data-submit]")
    page.wait_for_selector("[data-success]:not([hidden])")
    first = page.text_content("[data-success-code]")

    page.click("[data-new-booking]")
    page.wait_for_selector("[data-success]", state="hidden")
    pick(page, free_day, "11:00", "Polygel")
    fill_customer(page, phone="322 555 6677")
    wait_turnstile(page)
    page.click("[data-submit]")
    page.wait_for_selector("[data-success]:not([hidden])")
    second = page.text_content("[data-success-code]")

    assert re.fullmatch(r"AC-[A-Z0-9]{5}", first)
    assert re.fullmatch(r"AC-[A-Z0-9]{5}", second)
    assert first != second
    rows = server.sql(f"SELECT COUNT(*) AS n FROM bookings WHERE date = '{free_day.isoformat()}'")
    assert rows[0]["n"] == 2
    assert page.locator("[data-ts-notice]").is_hidden()


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


def test_combo_books_end_to_end_without_frontend_changes(desktop, server, free_day):
    page = desktop.page
    page.goto("/", wait_until="load")

    card = page.locator(".service-card", has_text="Combos")
    card.wait_for()
    assert card.locator(".service-list li").count() == len(config.BUNDLES)
    # Los combos se ofrecen primero: es lo que más se vende.
    assert "Combos" in page.locator(".service-card").first.text_content()

    pick(page, free_day, "08:00", "Combo Uñas + Cejas")
    fill_customer(page)
    assert page.text_content("[data-sum=service]") == "Combo Uñas + Cejas"

    wait_turnstile(page)
    page.click("[data-submit]")
    page.wait_for_selector("[data-success]:not([hidden])")

    code = page.text_content("[data-success-code]")
    row = server.sql(f"SELECT service_name, duration_min FROM bookings WHERE code = '{code}'")[0]
    assert row == {"service_name": "Combo Uñas + Cejas", "duration_min": config.DURACION_COMBO_X}
    assert desktop.errors == [] and desktop.http_errors == []


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


#  Angélica

def test_admin_wrong_password(desktop):
    page = desktop.page
    page.goto("/admin/", wait_until="load")
    page.fill("input[name=password]", "equivocada")
    page.click("[data-login-form] button[type=submit]")
    err = page.locator("[data-login-error]")
    err.wait_for(state="visible")
    assert "incorrecta" in err.text_content()
    assert page.locator("[data-view=app]").is_hidden()


def test_admin_wrong_mfa_code(desktop, server):
    page = desktop.page
    page.goto("/admin/", wait_until="load")
    page.fill("input[name=password]", server.admin_password)
    page.click("[data-login-form] button[type=submit]")
    page.wait_for_selector("[data-mfa-field]:not([hidden])")
    page.fill("input[name=code]", "000000")
    page.click("[data-login-form] button[type=submit]")
    err = page.locator("[data-login-error]")
    err.wait_for(state="visible")
    assert "incorrecto" in err.text_content()
    assert page.locator("[data-view=app]").is_hidden()
    assert page.locator("[data-mfa-field]:not([hidden])").count() == 1


def test_admin_confirms_and_cancels_bookings(desktop, server, free_day):
    import httpx
    codes = []
    for t, name in (("08:00", "Paola Ríos"), ("11:00", "Camila Díaz")):
        r = httpx.post(f"{server.base_url}/api/bookings",
                       json=booking_payload(free_day, t, name=name, phone=PHONES[name]))
        codes.append(r.json()["code"])

    page = desktop.page
    admin_login(page, server.admin_password, server.totp_secret)
    card = page.locator(f".booking-card[data-code='{codes[0]}']")
    card.wait_for()
    assert "Paola Ríos" in card.text_content() and "Pendiente" in card.text_content()

    card.locator("[data-action=confirmed]").click()
    toast = page.locator("[data-toast]")
    toast.wait_for(state="visible")
    assert "confirmada" in toast.text_content()
    assert toast.locator("a").get_attribute("href").startswith("https://wa.me/573001110001")
    page.wait_for_selector(f".booking-card[data-code='{codes[0]}'] .badge-confirmed")

    cancel = page.locator(f".booking-card[data-code='{codes[1]}'] [data-action=cancelled]")
    cancel.click()
    assert "Seguro" in cancel.text_content()
    assert server.sql(f"SELECT status FROM bookings WHERE code = '{codes[1]}'")[0]["status"] == "pending"
    cancel.click()
    page.wait_for_selector(f".booking-card[data-code='{codes[1]}'] .badge-cancelled")
    assert server.sql(f"SELECT status FROM bookings WHERE code = '{codes[1]}'")[0]["status"] == "cancelled"

    page.click("[data-status=confirmed]")
    page.wait_for_selector(f".booking-card[data-code='{codes[0]}'] .badge-confirmed")
    assert page.locator(f".booking-card[data-code='{codes[1]}']").count() == 0
    assert desktop.errors == []


def test_admin_blocks_day_and_customer_sees_it_closed(browser, server, free_day):
    admin = Page(browser, server.base_url, **MOBILE)
    customer = Page(browser, server.base_url, **DESKTOP)
    try:
        page = admin.page
        admin_login(page, server.admin_password, server.totp_secret)
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

        item.locator("button").click()
        item.wait_for(state="detached")
        assert server.sql(f"SELECT COUNT(*) AS n FROM blocked_slots WHERE date = '{free_day.isoformat()}'")[0]["n"] == 0
        assert admin.errors == [] and customer.errors == []
    finally:
        admin.close()
        customer.close()


def test_admin_session_survives_reload_and_logout(desktop, server):
    page = desktop.page
    admin_login(page, server.admin_password, server.totp_secret)
    page.reload(wait_until="load")
    page.wait_for_selector("[data-view=app]:not([hidden])")
    page.click("[data-logout]")
    page.wait_for_selector("[data-view=login]:not([hidden])")
    page.reload(wait_until="load")
    page.wait_for_selector("[data-view=login]:not([hidden])")
    for name in ("ac_admin", "ac_admin_mfa"):
        cookies = [c for c in desktop.context.cookies() if c["name"] == name]
        assert cookies == [] or cookies[0]["value"] == ""
