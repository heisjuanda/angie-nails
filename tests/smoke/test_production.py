"""Pruebas de humo contra el sitio publicado. No crean citas ni bloqueos.

Correr con:  npm run test:smoke   (o: uv run pytest -m smoke)
URL por defecto: https://ac-luxury-aesthetics.heisjuanda.workers.dev  (cambiar con PROD_URL)
"""

import os
import time
from pathlib import Path

import httpx
import pytest

from helpers import booking_payload

pytestmark = pytest.mark.smoke

BASE = os.environ.get("PROD_URL", "https://ac-luxury-aesthetics.heisjuanda.workers.dev").rstrip("/")
SECRETS = Path(__file__).resolve().parents[2] / ".secrets.production.local"


def _prod_secret(name: str) -> str:
    if not SECRETS.exists():
        pytest.skip("No existe .secrets.production.local")
    values = dict(line.strip().split("=", 1) for line in SECRETS.read_text().splitlines() if "=" in line)
    return values[name]


@pytest.fixture
def client():
    with httpx.Client(base_url=BASE, headers={"origin": BASE}, timeout=30, follow_redirects=True) as c:
        yield c


def test_home_is_up_with_security_headers(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Reserva en tres pasos" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["strict-transport-security"].startswith("max-age=")


def test_config_uses_real_turnstile_key(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    key = r.json()["turnstile_site_key"]
    assert key.startswith("0x") and not key.startswith("1x0000")
    import config
    assert r.json()["whatsapp"] == config.WHATSAPP


def test_availability_responds_fast(client):
    t0 = time.time()
    r = client.get("/api/availability", params={"service": "semipermanente", "days": 7})
    assert r.status_code == 200 and len(r.json()["days"]) == 7
    assert time.time() - t0 < 10


def test_fake_turnstile_token_is_rejected(client):
    from datetime import date, timedelta
    r = client.post("/api/bookings", json=booking_payload(date.today() + timedelta(days=3), "08:00"))
    assert r.status_code == 403


def test_admin_login_session_and_logout(client):
    assert client.get("/api/admin/session").json() == {"authenticated": False}
    r = client.post("/api/admin/login", json={"password": _prod_secret("ADMIN_PASSWORD")})
    assert r.status_code == 200, r.text
    cookie = r.headers["set-cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert client.get("/api/admin/session").json() == {"authenticated": True}
    assert client.get("/api/admin/bookings").status_code == 200
    assert client.get("/api/admin/blocks").status_code == 200
    assert client.post("/api/admin/logout").status_code == 200
    assert client.get("/api/admin/session").json() == {"authenticated": False}


def test_admin_rejects_cross_origin(client):
    r = client.post("/api/admin/login", json={"password": "x"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_admin_page_and_404(client):
    assert 'content="noindex, nofollow"' in client.get("/admin/").text
    r = client.get("/pagina-que-no-existe")
    assert r.status_code == 404 and "no existe" in r.text


def test_page_renders_in_browser_with_real_turnstile():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE + "/", wait_until="load")
        page.wait_for_selector(".service-option")
        page.wait_for_selector("[data-services-grid] .service-card")
        page.wait_for_selector("[data-turnstile] iframe, [data-turnstile] input[name=cf-turnstile-response]",
                               state="attached", timeout=20000)
        assert errors == []
        browser.close()
