import concurrent.futures
from datetime import date, timedelta
from urllib.parse import unquote

import httpx
import pytest

import availability
import config
from helpers import booking_payload, slots_of

pytestmark = pytest.mark.integration


def _next_weekday(weekday: int):
    today = availability.now_local().date()
    d = today + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


#  config

def test_config_shape(api):
    r = api.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert {c["id"] for c in data["categories"]} == {"unas", "cejas", "pestanas"}
    assert len(data["services"]) == len(config.SERVICES)
    assert all(s["price_label"] == "$ X" for s in data["services"])
    assert 6 not in data["open_weekdays"]
    assert data["turnstile_site_key"]
    first, last = availability.booking_window(availability.now_local().date())
    assert data["window"] == {"first": first.isoformat(), "last": last.isoformat()}


def test_api_responses_are_not_cached(api):
    assert api.get("/api/availability", params={"service": "lifting"}).headers["cache-control"] == "no-store"


#  availability

def test_availability_happy_path(api):
    r = api.get("/api/availability", params={"service": "semipermanente", "days": 7})
    assert r.status_code == 200
    days = r.json()["days"]
    assert len(days) == 7
    for d in days:
        weekday = date.fromisoformat(d["date"]).weekday()
        if config.BUSINESS_HOURS.get(weekday):
            assert d["slots"], d["date"]
            assert d["slots"][0]["time"] == config.HORA_INICIO_X
        else:
            assert d["slots"] == []


def test_sunday_has_no_slots(api):
    sunday = _next_weekday(6)
    r = api.get("/api/availability", params={"service": "lifting", "from": sunday.isoformat(), "days": 1})
    assert r.json()["days"][0]["slots"] == []


def test_availability_clamps_past_and_long_ranges(api):
    today = availability.now_local().date()
    r = api.get("/api/availability", params={"service": "lifting", "from": "2020-01-01", "days": 999})
    days = r.json()["days"]
    assert days[0]["date"] == today.isoformat()
    assert len(days) == config.BOOKING_WINDOW_DAYS


@pytest.mark.parametrize("params", [
    {"service": "no-existe"},
    {},
    {"service": "lifting", "from": "ayer"},
    {"service": "lifting", "days": "muchos"},
])
def test_availability_bad_params(api, params):
    assert api.get("/api/availability", params=params).status_code == 400


#  booking

def test_booking_happy_path_and_travel_buffer(api, free_day):
    r = api.post("/api/bookings", json=booking_payload(free_day, "08:00"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["code"].startswith("AC-") and len(body["code"]) == 8
    assert body["summary"]["time"] == "8:00 a. m."
    assert body["summary"]["price"] == "$ X"
    text = unquote(body["whatsapp_url"])
    assert body["whatsapp_url"].startswith(f"https://wa.me/{config.WHATSAPP}?text=")
    assert body["code"] in text and "Semipermanente" in text and "San Fernando" in text

    # 08:00 + 90 min + 45 de traslado = ocupado hasta 10:15.
    slots = slots_of(api, free_day)
    assert not any(slots[t] for t in ["08:00", "08:30", "09:00", "09:30", "10:00"])
    assert slots["10:30"]

    # Mismo horario y un horario dentro del traslado → 409.
    assert api.post("/api/bookings", json=booking_payload(free_day, "08:00")).status_code == 409
    assert api.post("/api/bookings", json=booking_payload(free_day, "10:00")).status_code == 409
    # Justo después del traslado → se puede.
    assert api.post("/api/bookings", json=booking_payload(free_day, "10:30")).status_code == 201
    # La nueva cita de 10:30 ocupa hasta 12:45, así que 12:00 ya no se ofrece.
    assert not slots_of(api, free_day)["12:00"]


def test_concurrent_bookings_same_slot_only_one_wins(server, free_day):
    payload = booking_payload(free_day, "14:00", service="lifting")

    def book(_):
        with httpx.Client(base_url=server.base_url, timeout=60) as c:
            return c.post("/api/bookings", json=payload).status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(book, range(8)))
    assert codes.count(201) == 1, codes
    assert codes.count(409) == 7, codes
    rows = server.sql(f"SELECT COUNT(*) AS n FROM bookings WHERE date = '{free_day.isoformat()}' AND start_min = 840")
    assert rows[0]["n"] == 1


def test_validation_errors_are_reported_per_field(api):
    r = api.post("/api/bookings", json={"turnstile_token": "t", "service_id": "x", "phone": "123"})
    assert r.status_code == 422
    fields = r.json()["fields"]
    assert set(fields) >= {"service_id", "date", "time", "name", "phone", "neighborhood", "address"}


@pytest.mark.parametrize("override", [
    {"phone": "6023334455"},
    {"phone": "+1 415 555 0000"},
    {"name": "A"},
    {"address": "x"},
    {"time": "8:00"},
    {"time": "25:00"},
    {"date": "2026-02-30"},
    {"service_id": "botox"},
])
def test_single_invalid_field(api, override):
    day = next(iter(_future_open_day()))
    r = api.post("/api/bookings", json=booking_payload(day, **override))
    assert r.status_code == 422, r.text
    assert len(r.json()["fields"]) == 1


def _future_open_day():
    today = availability.now_local().date()
    d = today + timedelta(days=2)
    while not config.BUSINESS_HOURS.get(d.weekday()):
        d += timedelta(days=1)
    yield d


@pytest.mark.parametrize("label,day_offset,time", [
    ("pasado", -1, "08:00"),
    ("fuera de ventana", config.BOOKING_WINDOW_DAYS + 3, "08:00"),
    ("fuera de grilla", None, "08:15"),
    ("después del cierre", None, "17:00"),
    ("antes de abrir", None, "06:00"),
])
def test_unbookable_slots_are_rejected(api, label, day_offset, time):
    today = availability.now_local().date()
    day = today + timedelta(days=day_offset) if day_offset is not None else next(_future_open_day())
    r = api.post("/api/bookings", json=booking_payload(day, time))
    assert r.status_code == 409, f"{label}: {r.text}"


def test_sunday_booking_rejected(api):
    assert api.post("/api/bookings", json=booking_payload(_next_weekday(6), "10:00")).status_code == 409


@pytest.mark.parametrize("body,headers", [
    ("no es json", {"content-type": "application/json"}),
    ("[1, 2, 3]", {"content-type": "application/json"}),
    ("", {}),
])
def test_malformed_bodies(api, body, headers):
    assert api.post("/api/bookings", content=body, headers=headers).status_code == 400


@pytest.mark.parametrize("token", [None, "", "x" * 5000, 12345])
def test_missing_or_invalid_turnstile_token(api, token):
    payload = booking_payload(next(_future_open_day()), turnstile_token=token)
    assert api.post("/api/bookings", json=payload).status_code == 403


def test_turnstile_rejection_blocks_booking(strict_server):
    with strict_server.client() as c:
        r = c.post("/api/bookings", json=booking_payload(next(_future_open_day()), "08:00"))
        assert r.status_code == 403
    assert strict_server.sql("SELECT COUNT(*) AS n FROM bookings")[0]["n"] == 0


def test_booking_data_is_stored_normalized(server, api, free_day):
    payload = booking_payload(free_day, "09:00", name="  Ana   María  ", phone="+57 (310) 555-1234",
                              notes="<script>alert(1)</script> diseño francés")
    code = api.post("/api/bookings", json=payload).json()["code"]
    row = server.sql(f"SELECT customer_name, phone, notes, status, busy_until_min FROM bookings WHERE code = '{code}'")[0]
    assert row["customer_name"] == "Ana María"
    assert row["phone"] == "573105551234"
    assert row["notes"] == "<script>alert(1)</script> diseño francés"
    assert row["status"] == "pending"
    assert row["busy_until_min"] == 9 * 60 + config.DURACION_X + config.TRAVEL_BUFFER_MIN


#  comportamientos

def test_unconfirmed_pending_booking_expires_and_frees_slot(server, api, admin, free_day):
    first = api.post("/api/bookings", json=booking_payload(free_day, "08:00")).json()["code"]
    assert not slots_of(api, free_day)["08:00"]

    server.sql(f"UPDATE bookings SET created_at = datetime('now', '-{config.PENDING_TTL_HOURS + 1} hours') WHERE code = '{first}'")
    assert slots_of(api, free_day)["08:00"]

    listed = {b["code"]: b for b in admin.get("/api/admin/bookings", params={"from": free_day.isoformat(), "to": free_day.isoformat()}).json()["bookings"]}
    assert listed[first]["expired"] is True

    second = api.post("/api/bookings", json=booking_payload(free_day, "08:00", name="Segunda Clienta"))
    assert second.status_code == 201
    r = admin.patch(f"/api/admin/bookings/{first}", json={"status": "confirmed"})
    assert r.status_code == 409
    assert admin.patch(f"/api/admin/bookings/{second.json()['code']}", json={"status": "confirmed"}).status_code == 200


def test_expired_pending_can_still_be_confirmed_if_slot_free(server, api, admin, free_day):
    code = api.post("/api/bookings", json=booking_payload(free_day, "15:00", service="henna")).json()["code"]
    server.sql(f"UPDATE bookings SET created_at = datetime('now', '-{config.PENDING_TTL_HOURS + 2} hours') WHERE code = '{code}'")
    r = admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"})
    assert r.status_code == 200
    assert not slots_of(api, free_day, "henna")["15:00"]  # confirmada vuelve a ocupar


#  rutas

@pytest.mark.parametrize("method,path", [
    ("GET", "/api/nada"),
    ("GET", "/api/bookings"),
    ("DELETE", "/api/bookings"),
    ("POST", "/api/config"),
])
def test_unknown_routes_404(api, method, path):
    r = api.request(method, path)
    assert r.status_code == 404
    assert r.json()["error"]


def test_static_site_and_security_headers(api):
    r = api.get("/")
    assert r.status_code == 200
    assert "Reserva en tres pasos" in r.text
    csp = r.headers.get("content-security-policy", "")
    assert "default-src 'self'" in csp and "challenges.cloudflare.com" in csp
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_static_404_page(api):
    r = api.get("/no-existe")
    assert r.status_code == 404
    assert "no existe" in r.text


def test_admin_page_is_noindex(api):
    r = api.get("/admin/")
    assert r.status_code == 200
    assert 'content="noindex, nofollow"' in r.text


def test_internal_files_are_not_published(api):
    assert api.get("/img/portafolio/LEEME.md").status_code == 404
