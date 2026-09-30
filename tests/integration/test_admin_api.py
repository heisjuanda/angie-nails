"""Panel de administración contra el Worker real: sesión, seguridad, citas y bloqueos."""

import time
from urllib.parse import unquote

import httpx
import pytest

import auth
from helpers import booking_payload, slots_of

pytestmark = pytest.mark.integration


def _book(api, day, time_="08:00", **kw) -> str:
    r = api.post("/api/bookings", json=booking_payload(day, time_, **kw))
    assert r.status_code == 201, r.text
    return r.json()["code"]


# --------------------------------------------------------------- sesión

def test_login_happy_path_sets_secure_cookie(server):
    with server.client() as c:
        r = c.post("/api/admin/login", json={"password": server.admin_password})
        assert r.status_code == 200
        cookie = r.headers["set-cookie"]
        assert cookie.startswith(f"{auth.COOKIE_NAME}=")
        for flag in ("HttpOnly", "SameSite=Strict", "Path=/api/admin"):
            assert flag in cookie
        assert c.get("/api/admin/session").json()["authenticated"] is True


def test_wrong_password(server):
    with server.client() as c:
        r = c.post("/api/admin/login", json={"password": "no-es-la-clave"})
        assert r.status_code == 401
        assert "set-cookie" not in r.headers
        assert c.get("/api/admin/session").json()["authenticated"] is False


@pytest.mark.parametrize("body", ["no-json", "[]", ""])
def test_login_malformed_body(server, body):
    with server.client() as c:
        assert c.post("/api/admin/login", content=body, headers={"content-type": "application/json"}).status_code == 400


@pytest.mark.parametrize("origin", [None, "https://evil.example", "http://127.0.0.1:1"])
def test_login_requires_same_origin(server, origin):
    headers = {"origin": origin} if origin else {}
    with httpx.Client(base_url=server.base_url, headers=headers) as c:
        r = c.post("/api/admin/login", json={"password": server.admin_password})
        assert r.status_code == 403
        assert "set-cookie" not in r.headers


def test_logout_ends_session(server):
    with server.admin_client() as c:
        assert c.get("/api/admin/session").json()["authenticated"] is True
        r = c.post("/api/admin/logout")
        assert r.status_code == 200 and "Max-Age=0" in r.headers["set-cookie"]
        assert c.get("/api/admin/session").json()["authenticated"] is False


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/admin/bookings"),
    ("PATCH", "/api/admin/bookings/AC-ABCDE"),
    ("GET", "/api/admin/blocks"),
    ("POST", "/api/admin/blocks"),
    ("DELETE", "/api/admin/blocks/1"),
    ("GET", "/api/admin/lo-que-sea"),
])
def test_admin_routes_require_session(api, method, path):
    assert api.request(method, path, json={} if method in ("POST", "PATCH") else None).status_code == 401


def test_session_endpoint_reports_state_without_401(api):
    r = api.get("/api/admin/session")
    assert r.status_code == 200 and r.json() == {"authenticated": False}


def _cookie_client(server, token: str) -> httpx.Client:
    c = server.client()
    c.cookies.set(auth.COOKIE_NAME, token, domain="127.0.0.1", path="/api/admin")
    return c


def test_forged_or_expired_cookies_rejected(server):
    valid = auth.create_token(server.session_secret, server.admin_password)
    cases = {
        "expirada": auth.create_token(server.session_secret, server.admin_password, now=time.time() - auth.SESSION_TTL_S - 10),
        "otro secreto": auth.create_token("secreto-adivinado", server.admin_password),
        "otra clave": auth.create_token(server.session_secret, "clave-vieja"),
        "firma alterada": valid[:-3] + "abc",
        "basura": "hola.mundo",
    }
    for label, token in cases.items():
        with _cookie_client(server, token) as c:
            assert c.get("/api/admin/session").json()["authenticated"] is False, label
    # Control: un token bien firmado sí entra (el mecanismo es la cookie firmada).
    with _cookie_client(server, valid) as c:
        assert c.get("/api/admin/session").json()["authenticated"] is True


def test_writes_without_origin_are_rejected_even_with_session(server):
    with server.admin_client() as c:
        r = c.post("/api/admin/blocks", json={"date": "2030-01-01", "all_day": True}, headers={"origin": "https://evil.example"})
        assert r.status_code == 403
        del c.headers["origin"]
        assert c.post("/api/admin/blocks", json={"date": "2030-01-01", "all_day": True}).status_code == 403
        assert c.get("/api/admin/session").json()["authenticated"] is True  # las lecturas no necesitan Origin


def test_rejected_requests_keep_connection_usable(api):
    """Regresión: responder 401/403/404 sin leer el cuerpo rompía la conexión keep-alive."""
    for _ in range(3):
        assert api.post("/api/admin/blocks", json={"date": "2030-01-01"}).status_code == 401
        assert api.post("/api/admin/blocks", json={"x": 1}, headers={"origin": "https://evil.example"}).status_code == 403
        assert api.post("/api/nada", json={"x": 1}).status_code == 404
    assert api.get("/api/config").status_code == 200


def test_brute_force_lockout(strict_server):
    with strict_server.client() as c:
        for _ in range(auth.MAX_FAILED_LOGINS):
            assert c.post("/api/admin/login", json={"password": "intento"}).status_code == 401
        # Aun con la clave correcta, queda bloqueado durante la ventana.
        r = c.post("/api/admin/login", json={"password": strict_server.admin_password})
        assert r.status_code == 429
    # Emula que pasó la ventana de bloqueo.
    strict_server.sql("UPDATE login_attempts SET attempted_at = datetime('now', '-1 hour')")
    with strict_server.client() as c:
        assert c.post("/api/admin/login", json={"password": strict_server.admin_password}).status_code == 200
    assert strict_server.sql("SELECT COUNT(*) AS n FROM login_attempts")[0]["n"] == 0  # éxito limpia intentos


# ---------------------------------------------------------------- citas

def test_list_bookings_and_filters(api, admin, free_day):
    a = _book(api, free_day, "08:00", name="Primera Clienta")
    b = _book(api, free_day, "11:00", service="lifting", name="Segunda Clienta")
    params = {"from": free_day.isoformat(), "to": free_day.isoformat()}

    r = admin.get("/api/admin/bookings", params=params)
    assert r.status_code == 200
    items = r.json()["bookings"]
    assert [x["code"] for x in items] == [a, b]            # ordenadas por hora
    first = items[0]
    assert first["start"] == "08:00" and first["start_label"] == "8:00 a. m."
    assert first["phone"] == "573001234567"
    assert first["status"] == "pending" and first["expired"] is False
    assert first["whatsapp_url"].startswith("https://wa.me/573001234567?text=")

    admin.patch(f"/api/admin/bookings/{b}", json={"status": "confirmed"})
    only_confirmed = admin.get("/api/admin/bookings", params={**params, "status": "confirmed"}).json()["bookings"]
    assert [x["code"] for x in only_confirmed] == [b]


@pytest.mark.parametrize("params", [
    {"status": "borrada"},
    {"from": "2026-10-10", "to": "2026-10-01"},
    {"from": "2026-01-01", "to": "2026-12-31"},   # > 120 días
    {"from": "mañana"},
])
def test_list_bookings_bad_params(admin, params):
    assert admin.get("/api/admin/bookings", params=params).status_code == 400


def test_booking_lifecycle(api, admin, free_day):
    code = _book(api, free_day, "09:00", name="Laura Gómez")

    r = admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"})
    assert r.status_code == 200
    booking = r.json()["booking"]
    assert booking["status"] == "confirmed" and booking["status_label"] == "Confirmada"
    msg = unquote(booking["whatsapp_url"])
    assert "Hola Laura" in msg and "Te confirmo" in msg and code in msg

    # Transiciones inválidas desde "confirmada".
    for bad in ("pending", "confirmed", "nada", None):
        assert admin.patch(f"/api/admin/bookings/{code}", json={"status": bad}).status_code == 422

    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "completed"}).status_code == 200
    # Estado final: ya no se mueve.
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "cancelled"}).status_code == 422


def test_cancel_frees_the_slot(api, admin, free_day):
    code = _book(api, free_day, "13:00", service="volumen")
    assert not slots_of(api, free_day, "volumen")["13:00"]
    r = admin.patch(f"/api/admin/bookings/{code}", json={"status": "cancelled"})
    assert r.status_code == 200
    assert "no puedo atender" in unquote(r.json()["booking"]["whatsapp_url"])
    assert slots_of(api, free_day, "volumen")["13:00"]
    # Una cancelada no se puede reactivar.
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"}).status_code == 422


@pytest.mark.parametrize("code,status", [("AC-ZZZZZ", 404), ("no-es-codigo", 404), ("AC-zzzzz", 404)])
def test_update_unknown_booking(admin, code, status):
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"}).status_code == status


def test_update_booking_malformed_body(admin):
    assert admin.patch("/api/admin/bookings/AC-ZZZZZ", content="x", headers={"content-type": "application/json"}).status_code == 400


# -------------------------------------------------------------- bloqueos

def test_all_day_block_closes_day_and_can_be_removed(api, admin, free_day):
    r = admin.post("/api/admin/blocks", json={"date": free_day.isoformat(), "all_day": True, "reason": "Viaje"})
    assert r.status_code == 201
    block_id = r.json()["id"]
    assert r.json()["overlapping_bookings"] == 0
    assert not any(slots_of(api, free_day).values())
    assert api.post("/api/bookings", json=booking_payload(free_day, "10:00")).status_code == 409

    listed = admin.get("/api/admin/blocks", params={"from": free_day.isoformat(), "to": free_day.isoformat()}).json()["blocks"]
    assert listed == [{"id": block_id, "date": free_day.isoformat(), "start": "00:00", "end": "24:00", "all_day": True, "reason": "Viaje"}]

    assert admin.delete(f"/api/admin/blocks/{block_id}").status_code == 200
    assert any(slots_of(api, free_day).values())
    assert admin.delete(f"/api/admin/blocks/{block_id}").status_code == 404   # ya no existe


def test_partial_block_only_affects_its_range(api, admin, free_day):
    r = admin.post("/api/admin/blocks", json={"date": free_day.isoformat(), "start": "12:00", "end": "14:00"})
    assert r.status_code == 201
    slots = slots_of(api, free_day)                     # servicio de 90 min + 45 de traslado
    assert slots["08:00"] and slots["09:30"]            # 09:30 + 135 = 11:45 → antes del bloqueo
    assert not slots["10:00"]                           # 10:00 + 135 = 12:15 → invade el bloqueo
    assert not slots["13:00"]
    assert slots["14:00"]


def test_block_over_existing_booking_warns(api, admin, free_day):
    _book(api, free_day, "09:00")
    r = admin.post("/api/admin/blocks", json={"date": free_day.isoformat(), "start": "09:00", "end": "10:00"})
    assert r.status_code == 201
    assert r.json()["overlapping_bookings"] == 1


@pytest.mark.parametrize("body", [
    {"date": "2026-13-01", "all_day": True},
    {"date": "2026-10-05", "start": "14:00", "end": "12:00"},
    {"date": "2026-10-05"},
])
def test_invalid_blocks(admin, body):
    assert admin.post("/api/admin/blocks", json=body).status_code == 422


@pytest.mark.parametrize("block_id", ["abc", "-1", "999999"])
def test_delete_unknown_block(admin, block_id):
    assert admin.delete(f"/api/admin/blocks/{block_id}").status_code == 404
