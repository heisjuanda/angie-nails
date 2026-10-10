import time
from datetime import timedelta
from urllib.parse import unquote

import httpx
import pytest

import auth
import availability
import mfa
from helpers import booking_payload, expire_booking, slots_of

pytestmark = pytest.mark.integration


def _book(api, day, time_="08:00", **kw) -> str:
    r = api.post("/api/bookings", json=booking_payload(day, time_, **kw))
    assert r.status_code == 201, r.text
    return r.json()["code"]


def _seed_bookings(server, day, n: int, prefix: str = "AC-PG") -> None:
    values = ", ".join(
        f"('{prefix}{i:03d}', 'semipermanente', 'Semipermanente', 'unas', 1000, 90, "
        f"'{day.isoformat()}', {480 + i * 30}, {570 + i * 30}, {615 + i * 30}, "
        f"'Clienta {i}', '573000000{i}', 'Barrio', 'Dir', '', 'pending')"
        for i in range(n)
    )
    server.sql(
        "INSERT INTO bookings (code, service_id, service_name, category, price, duration_min, "
        "date, start_min, end_min, busy_until_min, customer_name, phone, neighborhood, address, "
        "notes, status) VALUES " + values
    )


#  sesión

def test_login_requires_mfa_when_enabled(server):
    with server.client() as c:
        r = c.post("/api/admin/login", json={"password": server.admin_password})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "mfa_required": True}
        cookie = r.headers["set-cookie"]
        assert cookie.startswith(f"{auth.MFA_COOKIE_NAME}=")
        assert r.headers["x-content-type-options"] == "nosniff"
        for flag in ("HttpOnly", "SameSite=Strict", "Path=/api/admin", f"Max-Age={auth.MFA_TTL_S}"):
            assert flag in cookie
        assert f"{auth.COOKIE_NAME}=" not in cookie
        assert c.get("/api/admin/session").json()["authenticated"] is False


def test_mfa_happy_path_sets_session_cookie(server):
    with server.client() as c:
        c.post("/api/admin/login", json={"password": server.admin_password})
        r = c.post("/api/admin/mfa", json={"code": mfa.current_code(server.totp_secret)})
        assert r.status_code == 200
        cookies = r.headers.get_list("set-cookie")
        assert r.headers["x-content-type-options"] == "nosniff"
        assert any(ck.startswith(f"{auth.COOKIE_NAME}=") for ck in cookies)
        assert any(ck.startswith(f"{auth.MFA_COOKIE_NAME}=;") and "Max-Age=0" in ck for ck in cookies)
        assert c.get("/api/admin/session").json()["authenticated"] is True


def test_login_without_totp_secret_sets_session_directly(strict_server):
    with strict_server.client() as c:
        r = c.post("/api/admin/login", json={"password": strict_server.admin_password})
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        assert r.headers["set-cookie"].startswith(f"{auth.COOKIE_NAME}=")
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


#  segundo factor

def test_mfa_wrong_code_rejected(server):
    with server.client() as c:
        c.post("/api/admin/login", json={"password": server.admin_password})
        r = c.post("/api/admin/mfa", json={"code": "000000"})
        assert r.status_code == 401
        assert r.json()["step"] == "code"
        assert c.get("/api/admin/session").json()["authenticated"] is False


def test_mfa_requires_ticket(server):
    with server.client() as c:
        r = c.post("/api/admin/mfa", json={"code": mfa.current_code(server.totp_secret)})
        assert r.status_code == 401
        assert r.json()["step"] == "password"


def test_mfa_ticket_expires(server):
    ticket = auth.create_mfa_ticket(server.session_secret, server.admin_password,
                                    now=time.time() - auth.MFA_TTL_S - 10)
    c = server.client()
    c.cookies.set(auth.MFA_COOKIE_NAME, ticket, domain="127.0.0.1", path="/api/admin")
    r = c.post("/api/admin/mfa", json={"code": mfa.current_code(server.totp_secret)})
    assert r.status_code == 401


def test_mfa_requires_same_origin(server):
    with httpx.Client(base_url=server.base_url, headers={"origin": "https://evil.example"}) as c:
        assert c.post("/api/admin/mfa", json={"code": "123456"}).status_code == 403


def test_mfa_malformed_body(server):
    with server.client() as c:
        c.post("/api/admin/login", json={"password": server.admin_password})
        assert c.post("/api/admin/mfa", content="no-json",
                      headers={"content-type": "application/json"}).status_code == 400


def test_mfa_throttled(server):
    server.sql("DELETE FROM mfa_attempts")
    with server.client() as c:
        c.post("/api/admin/login", json={"password": server.admin_password})
        for _ in range(auth.MFA_MAX_ATTEMPTS):
            assert c.post("/api/admin/mfa", json={"code": "000000"}).status_code == 401
        r = c.post("/api/admin/mfa", json={"code": mfa.current_code(server.totp_secret)})
        assert r.status_code == 429
    server.sql("UPDATE mfa_attempts SET attempted_at = datetime('now', '-1 hour')")
    with server.client() as c:
        c.post("/api/admin/login", json={"password": server.admin_password})
        assert c.post("/api/admin/mfa", json={"code": mfa.current_code(server.totp_secret)}).status_code == 200
    assert server.sql("SELECT COUNT(*) AS n FROM mfa_attempts")[0]["n"] == 0  # éxito limpia intentos


def test_logout_ends_session(server):
    with server.admin_client() as c:
        assert c.get("/api/admin/session").json()["authenticated"] is True
        r = c.post("/api/admin/logout")
        assert r.status_code == 200
        cookies = r.headers.get_list("set-cookie")
        assert any(ck.startswith(f"{auth.COOKIE_NAME}=;") and "Max-Age=0" in ck for ck in cookies)
        assert any(ck.startswith(f"{auth.MFA_COOKIE_NAME}=;") and "Max-Age=0" in ck for ck in cookies)
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
        "firma válida sin sesión en el servidor": auth.create_token(server.session_secret, server.admin_password),
    }
    for label, token in cases.items():
        with _cookie_client(server, token) as c:
            assert c.get("/api/admin/session").json()["authenticated"] is False, label
    claims = auth.token_claims(valid)
    server.sql(f"INSERT INTO admin_sessions (sid, exp) VALUES ('{claims['sid']}', {claims['exp']})")
    with _cookie_client(server, valid) as c:
        assert c.get("/api/admin/session").json()["authenticated"] is True


def test_logout_invalidates_token_on_server(server):
    """Regresión: el token sobrevive al logout si no se borra del servidor."""
    with server.client() as c:
        r = c.post("/api/admin/login", json={"password": server.admin_password})
        assert r.status_code == 200, r.text
        if r.json().get("mfa_required"):
            r = c.post("/api/admin/mfa", json={"code": mfa.current_code(server.totp_secret)})
            assert r.status_code == 200, r.text
        cookies = r.headers.get_list("set-cookie")
        session_cookie = next(ck for ck in cookies if ck.startswith(f"{auth.COOKIE_NAME}="))
        token = unquote(session_cookie.split("=", 1)[1].split(";")[0])
        assert c.get("/api/admin/session").json()["authenticated"] is True
        assert c.post("/api/admin/logout").status_code == 200
    with _cookie_client(server, token) as c:
        assert c.get("/api/admin/session").json()["authenticated"] is False


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
        r = c.post("/api/admin/login", json={"password": strict_server.admin_password})
        assert r.status_code == 429
    strict_server.sql("UPDATE login_attempts SET attempted_at = datetime('now', '-1 hour')")
    with strict_server.client() as c:
        assert c.post("/api/admin/login", json={"password": strict_server.admin_password}).status_code == 200
    assert strict_server.sql("SELECT COUNT(*) AS n FROM login_attempts")[0]["n"] == 0  # éxito limpia intentos


#  citas

def test_cancelling_every_booking_frees_the_whole_day(api, admin, server, free_day):
    # Citas seguidas de 90 min llenan el día (08:00–18:00), sin traslado.
    times = ("08:00", "09:30", "11:00", "12:30", "14:00", "15:30", "17:00")
    codes = [_book(api, free_day, t) for t in times]
    assert len([s for s, a in slots_of(api, free_day).items() if a]) == 0

    for code in codes:
        r = admin.patch(f"/api/admin/bookings/{code}", json={"status": "cancelled"})
        assert r.status_code == 200, r.text
        assert r.json()["booking"]["status"] == "cancelled"

    rows = server.sql(f"SELECT status FROM bookings WHERE date = '{free_day.isoformat()}'")
    assert {row["status"] for row in rows} == {"cancelled"}
    assert len([s for s, a in slots_of(api, free_day).items() if a]) == len(slots_of(api, free_day))


def test_cancelling_a_confirmed_booking_frees_the_slot(api, admin, free_day):
    code = _book(api, free_day, "08:00")
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"}).status_code == 200
    assert slots_of(api, free_day)["08:00"] is False
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "cancelled"}).status_code == 200
    assert slots_of(api, free_day)["08:00"] is True


def test_completing_a_booking_frees_the_slot(api, admin, free_day):
    code = _book(api, free_day, "08:00")
    admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"})
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "completed"}).status_code == 200
    assert slots_of(api, free_day)["08:00"] is True


def test_pending_of_a_future_booking_survives_within_ttl_and_expires_after(server, api, admin, free_day):
    code = _book(api, free_day, "08:00")
    server.sql(f"UPDATE bookings SET created_at = datetime('now', '-13 hours') WHERE code = '{code}'")

    items = admin.get(
        "/api/admin/bookings", params={"from": free_day.isoformat(), "to": free_day.isoformat()}
    ).json()["bookings"]
    assert items[0]["code"] == code
    assert items[0]["expired"] is False, "la pendiente venció antes de cumplir las 24 h de TTL"
    assert slots_of(api, free_day)["08:00"] is False

    expire_booking(server, code)
    items_after = admin.get(
        "/api/admin/bookings", params={"from": free_day.isoformat(), "to": free_day.isoformat()}
    ).json()["bookings"]
    assert items_after[0]["code"] == code
    assert items_after[0]["expired"] is True, "la pendiente futura no venció tras superar PENDING_TTL_HOURS"
    assert slots_of(api, free_day)["08:00"] is True


def test_pending_stops_blocking_once_the_appointment_has_passed(server, api, admin, free_day):
    code = _book(api, free_day, "08:00")
    assert slots_of(api, free_day)["08:00"] is False

    # La hora de la cita ya pasó (ayer), pero fue creada hace apenas 1 hora (< PENDING_TTL_HOURS):
    # igual debe figurar como vencida de inmediato y no permitir confirmarse.
    ayer = (availability.now_local().date() - timedelta(days=1)).isoformat()
    server.sql(
        f"UPDATE bookings SET date = '{ayer}', created_at = datetime('now', '-1 hours') WHERE code = '{code}'"
    )

    items = admin.get("/api/admin/bookings", params={"from": ayer, "to": ayer}).json()["bookings"]
    mine = next(b for b in items if b["code"] == code)
    assert mine["expired"] is True

    r = admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"})
    assert r.status_code == 422
    assert "ya pasó" in r.json()["error"]


def test_list_bookings_and_filters(api, admin, free_day):
    a = _book(api, free_day, "08:00", name="Primera Clienta", phone="300 123 4567")
    b = _book(api, free_day, "11:00", service="lifting", name="Segunda Clienta")
    params = {"from": free_day.isoformat(), "to": free_day.isoformat()}

    r = admin.get("/api/admin/bookings", params=params)
    assert r.status_code == 200
    items = r.json()["bookings"]
    assert [x["code"] for x in items] == [a, b]
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
    {"from": "2026-01-01", "to": "2026-12-31"},
    {"from": "mañana"},
])
def test_list_bookings_bad_params(admin, params):
    assert admin.get("/api/admin/bookings", params=params).status_code == 400


def test_list_bookings_pagination(server, admin, free_day):
    _seed_bookings(server, free_day, 5)
    params = {"from": free_day.isoformat(), "to": free_day.isoformat()}

    whole = admin.get("/api/admin/bookings", params=params).json()
    assert whole["total"] == 5
    # 25 = PAGE_SIZE de admin_api
    assert whole["page"] == 1 and whole["per_page"] == 25
    assert [b["code"] for b in whole["bookings"]] == [f"AC-PG{i:03d}" for i in range(5)]

    p1 = admin.get("/api/admin/bookings", params={**params, "per_page": 2, "page": 1}).json()
    assert (p1["total"], p1["page"], p1["per_page"]) == (5, 1, 2)
    assert [b["code"] for b in p1["bookings"]] == ["AC-PG000", "AC-PG001"]

    p2 = admin.get("/api/admin/bookings", params={**params, "per_page": 2, "page": 2}).json()
    assert [b["code"] for b in p2["bookings"]] == ["AC-PG002", "AC-PG003"]

    p3 = admin.get("/api/admin/bookings", params={**params, "per_page": 2, "page": 3}).json()
    assert [b["code"] for b in p3["bookings"]] == ["AC-PG004"]

    p4 = admin.get("/api/admin/bookings", params={**params, "per_page": 2, "page": 4}).json()
    assert p4["bookings"] == [] and p4["total"] == 5

    clamped = admin.get("/api/admin/bookings", params={**params, "per_page": 5000}).json()
    assert clamped["per_page"] == 500

    server.sql("UPDATE bookings SET status = 'confirmed' WHERE code = 'AC-PG000'")
    filtered = admin.get(
        "/api/admin/bookings", params={**params, "status": "pending", "per_page": 2, "page": 1}
    ).json()
    assert filtered["total"] == 4
    assert [b["code"] for b in filtered["bookings"]] == ["AC-PG001", "AC-PG002"]


@pytest.mark.parametrize("params", [
    {"from": "2026-01-01", "to": "2026-01-02", "page": "x"},
    {"from": "2026-01-01", "to": "2026-01-02", "per_page": "abc"},
])
def test_list_bookings_bad_pagination(admin, params):
    assert admin.get("/api/admin/bookings", params=params).status_code == 400


def test_stats_are_totals_not_range_filtered(api, admin, server, free_day):
    before = admin.get(
        "/api/admin/bookings", params={"from": "2020-01-01", "to": "2020-01-02"}
    ).json()["stats"]

    pendiente = _book(api, free_day, "08:00")
    confirmada = _book(api, free_day, "11:00")
    admin.patch(f"/api/admin/bookings/{confirmada}", json={"status": "confirmed"})

    r = admin.get("/api/admin/bookings", params={"from": "2020-01-01", "to": "2020-01-02"})
    body = r.json()
    assert body["bookings"] == []
    assert body["stats"]["pending"] == before["pending"] + 1
    assert body["stats"]["confirmed"] == before["confirmed"] + 1

    expire_booking(server, pendiente)
    stats = admin.get(
        "/api/admin/bookings", params={"from": "2020-01-01", "to": "2020-01-02"}
    ).json()["stats"]
    assert stats["pending"] == before["pending"]
    assert stats["confirmed"] == before["confirmed"] + 1


def test_booking_lifecycle(api, admin, free_day):
    code = _book(api, free_day, "09:00", name="Laura Gómez")

    r = admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"})
    assert r.status_code == 200
    booking = r.json()["booking"]
    assert booking["status"] == "confirmed" and booking["status_label"] == "Confirmada"
    msg = unquote(booking["whatsapp_url"])
    assert "Hola Laura" in msg and "Te confirmo" in msg and code in msg

    for bad in ("pending", "confirmed", "nada", None):
        assert admin.patch(f"/api/admin/bookings/{code}", json={"status": bad}).status_code == 422

    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "completed"}).status_code == 200
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "cancelled"}).status_code == 422


def test_cancel_frees_the_slot(api, admin, free_day):
    code = _book(api, free_day, "13:00", service="volumen")
    assert not slots_of(api, free_day, "volumen")["13:00"]
    r = admin.patch(f"/api/admin/bookings/{code}", json={"status": "cancelled"})
    assert r.status_code == 200
    assert "no puedo atender" in unquote(r.json()["booking"]["whatsapp_url"])
    assert slots_of(api, free_day, "volumen")["13:00"]
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"}).status_code == 422


@pytest.mark.parametrize("code,status", [("AC-ZZZZZ", 404), ("no-es-codigo", 404), ("AC-zzzzz", 404)])
def test_update_unknown_booking(admin, code, status):
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"}).status_code == status


def test_update_booking_malformed_body(admin):
    assert admin.patch("/api/admin/bookings/AC-ZZZZZ", content="x", headers={"content-type": "application/json"}).status_code == 400


#  edición de citas: horario, servicio y ubicación (nunca nombre ni teléfono)

def test_edit_moves_the_booking_to_a_new_slot(api, admin, server, free_day):
    code = _book(api, free_day, "08:00")
    r = admin.patch(f"/api/admin/bookings/{code}", json={"time": "11:00"})
    assert r.status_code == 200, r.text
    booking = r.json()["booking"]
    assert booking["start"] == "11:00" and booking["end"] == "12:30"
    assert booking["start_label"] == "11:00 a. m."
    row = server.sql(
        f"SELECT start_min, end_min, busy_until_min FROM bookings WHERE code = '{code}'")[0]
    assert (row["start_min"], row["end_min"], row["busy_until_min"]) == (660, 750, 750)
    # El hueco viejo queda libre y el nuevo ocupado.
    assert slots_of(api, free_day)["08:00"] is True
    assert slots_of(api, free_day)["11:00"] is False


def test_edit_changes_service_duration_and_price(api, admin, server, free_day):
    code = _book(api, free_day, "08:00", service="semipermanente")
    r = admin.patch(f"/api/admin/bookings/{code}", json={"service_id": "combo-triple"})
    assert r.status_code == 200, r.text
    booking = r.json()["booking"]
    assert booking["service_id"] == "combo-triple"
    assert booking["service_name"] == "Combo Triple"
    assert booking["category"] == "combos"
    assert booking["end"] == "11:30"          # 08:00 + 210 min
    row = server.sql(
        f"SELECT service_id, service_name, category, duration_min, end_min, busy_until_min "
        f"FROM bookings WHERE code = '{code}'")[0]
    assert row == {"service_id": "combo-triple", "service_name": "Combo Triple",
                   "category": "combos", "duration_min": 210, "end_min": 690,
                   "busy_until_min": 690}


def test_edit_rejects_name_and_phone_changes(api, admin, server, free_day):
    code = _book(api, free_day, "08:00", name="Paola Ríos", phone="300 111 0001")
    for body in (
        {"customer_name": "Otra Persona"},
        {"phone": "573009999999"},
        {"customer_name": "Otra", "phone": "573009999999", "time": "11:00"},
    ):
        r = admin.patch(f"/api/admin/bookings/{code}", json=body)
        assert r.status_code == 422, body
        assert "nombre" in r.json()["error"] and "teléfono" in r.json()["error"]
    row = server.sql(
        f"SELECT customer_name, phone, start_min FROM bookings WHERE code = '{code}'")[0]
    assert row == {"customer_name": "Paola Ríos", "phone": "573001110001", "start_min": 480}


def test_edit_to_a_taken_slot_conflicts(api, admin, free_day):
    a = _book(api, free_day, "08:00")
    _book(api, free_day, "11:00")
    r = admin.patch(f"/api/admin/bookings/{a}", json={"time": "11:00"})
    assert r.status_code == 409
    assert "ya lo ocupa" in r.json()["error"]


def test_edit_onto_a_blocked_slot_conflicts(api, admin, free_day):
    code = _book(api, free_day, "08:00")
    admin.post("/api/admin/blocks", json={"date": free_day.isoformat(), "start": "11:00", "end": "12:00"})
    r = admin.patch(f"/api/admin/bookings/{code}", json={"time": "11:00"})
    assert r.status_code == 409


def test_edit_rejects_invalid_times(api, admin, server, free_day):
    code = _book(api, free_day, "08:00")
    for time in ("07:00", "18:00", "08:15", "25:00", "8:00", "", None):
        r = admin.patch(f"/api/admin/bookings/{code}", json={"time": time})
        assert r.status_code == 422, time
    row = server.sql(f"SELECT start_min FROM bookings WHERE code = '{code}'")[0]
    assert row["start_min"] == 480


def test_edit_rejects_unknown_service(api, admin, free_day):
    code = _book(api, free_day, "08:00")
    r = admin.patch(f"/api/admin/bookings/{code}", json={"service_id": "no-existe"})
    assert r.status_code == 422


def test_edit_without_changes_is_a_client_error(api, admin, free_day):
    code = _book(api, free_day, "08:00")
    assert admin.patch(f"/api/admin/bookings/{code}", json={}).status_code == 400


def test_edit_rejected_for_closed_bookings(api, admin, free_day):
    # Completada y cancelada son estados terminales: no se editan.
    completada = _book(api, free_day, "08:00", name="Paola Ríos", phone="300 111 0001")
    cancelada = _book(api, free_day, "10:30", name="Camila Díaz", phone="300 111 0002")
    admin.patch(f"/api/admin/bookings/{completada}", json={"status": "confirmed"})
    admin.patch(f"/api/admin/bookings/{completada}", json={"status": "completed"})
    admin.patch(f"/api/admin/bookings/{cancelada}", json={"status": "confirmed"})
    admin.patch(f"/api/admin/bookings/{cancelada}", json={"status": "cancelled"})
    for code in (completada, cancelada):
        r = admin.patch(f"/api/admin/bookings/{code}", json={"time": "11:00"})
        assert r.status_code == 422
        assert "pendientes o confirmadas" in r.json()["error"]


def test_edit_rejected_for_expired_pending(server, api, admin, free_day):
    code = _book(api, free_day, "08:00")
    expire_booking(server, code)
    r = admin.patch(f"/api/admin/bookings/{code}", json={"time": "11:00"})
    assert r.status_code == 422
    assert "venció" in r.json()["error"]


def test_edit_and_confirm_in_one_request(api, admin, free_day):
    code = _book(api, free_day, "08:00")
    r = admin.patch(f"/api/admin/bookings/{code}", json={"time": "11:00", "status": "confirmed"})
    assert r.status_code == 200, r.text
    booking = r.json()["booking"]
    assert booking["start"] == "11:00" and booking["status"] == "confirmed"
    assert slots_of(api, free_day)["11:00"] is False


def test_edit_keeps_the_status_flow_intact(api, admin, free_day):
    """Regresión: editar no altera las transiciones de estado."""
    code = _book(api, free_day, "08:00")
    assert admin.patch(f"/api/admin/bookings/{code}", json={"time": "09:00"}).status_code == 200
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"}).status_code == 200
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "pending"}).status_code == 422
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "completed"}).status_code == 200
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "cancelled"}).status_code == 422


def test_edit_moved_booking_still_blocks_its_new_slot(api, admin, free_day):
    code = _book(api, free_day, "08:00")
    admin.patch(f"/api/admin/bookings/{code}", json={"time": "11:00"})
    # 11:00 + 90 min = ocupado hasta 12:30.
    assert api.post("/api/bookings", json=booking_payload(free_day, "11:00")).status_code == 409
    assert api.post("/api/bookings", json=booking_payload(free_day, "12:00")).status_code == 409
    assert api.post("/api/bookings", json=booking_payload(free_day, "12:30")).status_code == 201


def test_edit_moves_booking_to_a_new_date(api, admin, free_day, _day_pool):
    other_day = next(_day_pool)
    code = _book(api, free_day, "08:00")
    r = admin.patch(f"/api/admin/bookings/{code}", json={"date": other_day.isoformat(), "time": "10:00"})
    assert r.status_code == 200, r.text
    booking = r.json()["booking"]
    assert booking["date"] == other_day.isoformat()
    assert booking["start"] == "10:00"
    # El hueco en free_day queda libre y en other_day ocupado
    assert slots_of(api, free_day)["08:00"] is True
    assert slots_of(api, other_day)["10:00"] is False


def test_edit_rejects_past_date(api, admin, free_day):
    code = _book(api, free_day, "08:00")
    ayer = (availability.now_local().date() - timedelta(days=1)).isoformat()
    r = admin.patch(f"/api/admin/bookings/{code}", json={"date": ayer})
    assert r.status_code == 422
    assert "pasado" in r.json()["error"]


def test_edit_moves_to_occupied_slot_on_new_date_conflicts(api, admin, free_day, _day_pool):
    other_day = next(_day_pool)
    code1 = _book(api, free_day, "08:00")
    _book(api, other_day, "10:00")
    r = admin.patch(f"/api/admin/bookings/{code1}", json={"date": other_day.isoformat(), "time": "10:00"})
    assert r.status_code == 409
    assert "ya lo ocupa" in r.json()["error"]


def test_edit_updates_combo_and_subservices(api, admin, free_day):
    code = _book(api, free_day, "08:00")
    r = admin.patch(
        f"/api/admin/bookings/{code}",
        json={
            "service_id": "combo-unas-pestanas",
            "combo_selections": {"unas": "semipermanente", "pestanas": "lifting"},
        },
    )
    assert r.status_code == 200, r.text
    booking = r.json()["booking"]
    assert booking["service_id"] == "combo-unas-pestanas:semipermanente+lifting"
    assert booking["service_name"] == "Combo Uñas + Pestañas (Semipermanente + Lifting de pestañas)"
    assert booking["end"] == "10:30"


#  bloqueos

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
    slots = slots_of(api, free_day)
    assert slots["08:00"] and slots["09:30"] and slots["10:30"]
    assert not slots["11:00"]
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
