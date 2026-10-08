import concurrent.futures
from datetime import date, timedelta
from urllib.parse import unquote

import httpx
import pytest

import availability
import config
from helpers import TEST_WINDOW_DAYS, booking_payload, expire_booking, form_token, seed_attempts, slots_of

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
    assert {c["id"] for c in data["categories"]} == {"combos", "unas", "cejas", "pestanas"}
    assert len(data["services"]) == len(config.ALL_SERVICES)
    assert all(s["price_label"] == "$ X" for s in data["services"])
    assert 6 not in data["open_weekdays"]
    assert data["turnstile_site_key"]
    # Horario por día en la convención de JS (0 = domingo); el domingo no tiene agenda.
    assert data["hours"] == {
        str((d + 1) % 7): [list(span) for span in spans]
        for d, spans in config.BUSINESS_HOURS.items() if spans
    }
    assert "0" not in data["hours"]
    assert data["slot_step_min"] == config.SLOT_STEP_MIN
    # La ventana la fija el entorno del Worker (TEST_WINDOW_DAYS), no el config local.
    today = availability.now_local().date()
    last = today + timedelta(days=TEST_WINDOW_DAYS - 1)
    assert data["window"] == {"first": today.isoformat(), "last": last.isoformat()}


def test_api_responses_are_not_cached(api):
    r = api.get("/api/availability", params={"service": "lifting"})
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["strict-transport-security"] == "max-age=31536000"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_api_security_headers_on_cookie_responses(api):
    r = api.post("/api/admin/logout")
    assert r.status_code == 200
    assert "set-cookie" in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["strict-transport-security"] == "max-age=31536000"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"


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
    assert len(days) == TEST_WINDOW_DAYS


@pytest.mark.parametrize("params", [
    {"service": "no-existe"},
    {},
    {"service": "lifting", "from": "ayer"},
    {"service": "lifting", "days": "muchos"},
])
def test_availability_bad_params(api, params):
    assert api.get("/api/availability", params=params).status_code == 400


#  booking

def test_booking_happy_path_and_occupies_its_slot(api, free_day):
    r = api.post("/api/bookings", json=booking_payload(free_day, "08:00"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["code"].startswith("AC-") and len(body["code"]) == 8
    assert body["summary"]["time"] == "8:00 a. m."
    assert body["summary"]["price"] == "$ X"
    text = unquote(body["whatsapp_url"])
    assert body["whatsapp_url"].startswith(f"https://wa.me/{config.WHATSAPP}?text=")
    assert body["code"] in text and "Semipermanente" in text

    # 08:00 + 90 min = ocupado hasta 09:30.
    slots = slots_of(api, free_day)
    assert not any(slots[t] for t in ["08:00", "08:30", "09:00"])
    assert slots["09:30"]

    # Mismo horario → 409.
    assert api.post("/api/bookings", json=booking_payload(free_day, "08:00")).status_code == 409
    # Justo después → se puede.
    assert api.post("/api/bookings", json=booking_payload(free_day, "09:30")).status_code == 201
    # La nueva cita de 09:30 ocupa hasta 11:00.
    assert not slots_of(api, free_day)["10:30"]
    assert slots_of(api, free_day)["11:00"]


def test_combo_books_as_one_slot_and_blocks_its_own_duration(api, server, free_day):
    """Un combo es un servicio más: una fila, su duración y su traslado."""
    combo = config.SERVICES_BY_ID["combo-unas-cejas"]
    assert combo["duration"] == config.DURACION_COMBO_X

    r = api.post("/api/bookings", json=booking_payload(free_day, "08:00", service="combo-unas-cejas"))
    assert r.status_code == 201, r.text
    assert r.json()["summary"]["service"] == "Combo Uñas + Cejas"
    assert "Combo Uñas + Cejas" in unquote(r.json()["whatsapp_url"])

    row = server.sql(
        "SELECT service_name, duration_min, start_min, end_min, busy_until_min FROM bookings "
        f"WHERE date = '{free_day.isoformat()}' AND start_min = 480"
    )[0]
    assert row["service_name"] == "Combo Uñas + Cejas"
    assert row["duration_min"] == config.DURACION_COMBO_X
    assert row["end_min"] == 480 + config.DURACION_COMBO_X
    assert row["busy_until_min"] == 480 + config.DURACION_COMBO_X

    # 08:00 + 150 = ocupado hasta 10:30; el primer hueco libre es 10:30.
    slots = slots_of(api, free_day, service="combo-unas-cejas")
    assert not any(slots[t] for t in ["08:00", "08:30", "09:00", "09:30", "10:00"])
    assert slots["10:30"]


def test_long_combo_offers_slots_until_closing_and_blocks_them(api, free_day):
    assert config.SERVICES_BY_ID["combo-triple"]["duration"] == config.DURACION_TRIPLE_X

    slots = slots_of(api, free_day, service="combo-triple")
    assert slots["08:00"]
    assert slots["14:30"]
    assert slots["17:30"]
    assert "18:00" not in slots

    r = api.post("/api/bookings", json=booking_payload(free_day, "14:00", service="combo-triple"))
    assert r.status_code == 201, r.text

    slots = slots_of(api, free_day, service="combo-triple")
    assert not any(slots[t] for t in ["11:00", "12:00", "14:00", "15:00", "16:00", "17:00"])
    assert slots["09:30"]
    assert slots["10:30"]
    assert slots["17:30"]

    simple = slots_of(api, free_day)
    assert simple["11:30"]
    assert simple["12:30"]
    assert not simple["13:00"]


def test_concurrent_bookings_same_slot_only_one_wins(server, free_day):
    """Dos personas compitiendo por el mismo horario: cada una con su propia llave.

    Si compartieran la llave, el servidor las trataría como un reintento del mismo envío y
    las dos obtendrían la misma cita — que es lo correcto para un reintento, pero no
    prueba nada sobre la carrera del horario.
    """

    def book(_):
        payload = booking_payload(free_day, "14:00", service="lifting", form_token=form_token())
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
    assert set(fields) >= {"service_id", "date", "time", "name", "phone"}


@pytest.mark.parametrize("override", [
    {"phone": "6023334455"},
    {"phone": "+1 415 555 0000"},
    {"name": "A"},
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
    ("fuera de ventana", TEST_WINDOW_DAYS + 3, "08:00"),
    ("fuera de grilla", None, "08:15"),
    ("en el cierre", None, "18:00"),
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
    assert row["busy_until_min"] == 9 * 60 + config.DURACION_X


#  idempotencia

def test_resending_the_same_form_returns_the_same_booking(api, server, free_day):
    payload = booking_payload(free_day, "08:00")

    first = api.post("/api/bookings", json=payload)
    assert first.status_code == 201, first.text
    again = api.post("/api/bookings", json=payload)
    assert again.status_code == 201, again.text
    assert again.json() == first.json()

    rows = server.sql(f"SELECT COUNT(*) AS n FROM bookings WHERE date = '{free_day.isoformat()}'")
    assert rows[0]["n"] == 1


def test_replay_happens_before_turnstile_which_is_single_use(api, free_day):
    payload = booking_payload(free_day, "08:00")
    assert api.post("/api/bookings", json=payload).status_code == 201
    assert api.post("/api/bookings", json=payload).status_code == 201


def test_same_key_on_a_different_slot_keeps_the_first_booking(api, server, free_day):
    token = form_token()
    first = api.post("/api/bookings", json=booking_payload(free_day, "08:00", form_token=token))
    second = api.post("/api/bookings", json=booking_payload(free_day, "14:00", form_token=token))
    assert first.status_code == 201 and second.status_code == 201
    assert second.json()["code"] == first.json()["code"]
    assert second.json()["summary"] == first.json()["summary"]
    rows = server.sql(f"SELECT COUNT(*) AS n FROM bookings WHERE date = '{free_day.isoformat()}'")
    assert rows[0]["n"] == 1


def test_distinct_keys_on_the_same_slot_still_collide(api, free_day):
    first = api.post("/api/bookings", json=booking_payload(free_day, "08:00"))
    second = api.post("/api/bookings", json=booking_payload(free_day, "08:00"))
    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.parametrize("bad", ["", "corta", "x" * 65, "con espacio/simbolos$$", None, 12345])
def test_missing_or_malformed_form_token_is_rejected(api, free_day, bad):
    r = api.post("/api/bookings", json=booking_payload(free_day, "08:00", form_token=bad))
    assert r.status_code == 422, (bad, r.text)
    assert "form_token" in r.json()["fields"]


def test_replay_of_a_cancelled_booking_does_not_resurrect_it(api, server, admin, free_day):
    payload = booking_payload(free_day, "08:00")
    created = api.post("/api/bookings", json=payload)
    assert created.status_code == 201
    code = created.json()["code"]
    admin.patch(f"/api/admin/bookings/{code}", json={"status": "cancelled"})

    r = api.post("/api/bookings", json=payload)
    assert r.status_code == 409
    row = server.sql(f"SELECT status FROM bookings WHERE code = '{code}'")[0]
    assert row["status"] == "cancelled"


def test_concurrent_requests_with_one_key_create_one_booking(server, free_day):
    token = form_token()
    times = ["08:00", "11:00", "14:00"]

    def book(t):
        payload = booking_payload(free_day, t, form_token=token)
        with httpx.Client(base_url=server.base_url, timeout=60) as c:
            r = c.post("/api/bookings", json=payload)
            return r.status_code, r.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(times)) as pool:
        results = list(pool.map(book, times))

    assert {status for status, _ in results} == {201}, results
    assert len({body.get("code") for _, body in results}) == 1
    rows = server.sql(f"SELECT COUNT(*) AS n FROM bookings WHERE date = '{free_day.isoformat()}'")
    assert rows[0]["n"] == 1


#  comportamientos

def test_unconfirmed_pending_booking_expires_and_frees_slot(server, api, admin, free_day):
    first = api.post("/api/bookings", json=booking_payload(free_day, "08:00")).json()["code"]
    assert not slots_of(api, free_day)["08:00"]

    expire_booking(server, first)
    assert slots_of(api, free_day)["08:00"]

    ayer = (availability.now_local().date() - timedelta(days=1)).isoformat()
    listed = {b["code"]: b for b in admin.get(
        "/api/admin/bookings", params={"from": ayer, "to": ayer}).json()["bookings"]}
    assert listed[first]["expired"] is True


def test_confirming_a_booking_whose_slot_was_taken_returns_409(server, api, admin, free_day):
    code = api.post("/api/bookings", json=booking_payload(free_day, "08:00")).json()["code"]
    server.sql(
        "INSERT INTO bookings (code, service_id, service_name, category, price, duration_min, "
        "date, start_min, end_min, busy_until_min, customer_name, phone, neighborhood, address) "
        "SELECT 'AC-RIVAL', service_id, service_name, category, price, duration_min, "
        "date, start_min, end_min, busy_until_min, 'Cita Rival', '573009999999', "
        f"'San Fernando', 'Carrera 1 # 2-3' FROM bookings WHERE code = '{code}'"
    )
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"}).status_code == 409

    assert admin.patch("/api/admin/bookings/AC-RIVAL", json={"status": "cancelled"}).status_code == 200
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"}).status_code == 200


def test_expired_pending_can_still_be_confirmed_if_slot_free(server, api, admin, free_day):
    code = api.post("/api/bookings", json=booking_payload(free_day, "15:00", service="henna")).json()["code"]
    expire_booking(server, code)
    assert slots_of(api, free_day, "henna")["15:00"]
    assert admin.patch(f"/api/admin/bookings/{code}", json={"status": "confirmed"}).status_code == 200
    server.sql(f"UPDATE bookings SET date = '{free_day.isoformat()}' WHERE code = '{code}'")
    assert not slots_of(api, free_day, "henna")["15:00"]


#  topes de la agenda
#
# Cada test usa su propio número, como su propia IP (ver conftest._ip_para). La cuota es de
# 8 en 24 h y `booking_attempts` es una tabla compartida por toda la suite, así que un
# número compartido acabaría topado por los reservas de los demás tests.
TEL_DIA = "300 000 0001"
TEL_VENCIDA = "300 000 0002"
TEL_24H = "300 000 0003"
TEL_INTENTOS = "300 000 0004"


def _tel(telefono: str) -> str:
    """Como lo normaliza el servidor, para poder consultar la tabla por teléfono."""
    return "57" + telefono.replace(" ", "")


def test_one_active_booking_per_phone_and_day(api, server, free_day):
    first = api.post("/api/bookings", json=booking_payload(free_day, "08:00", phone=TEL_DIA))
    assert first.status_code == 201, first.text

    second = api.post("/api/bookings", json=booking_payload(free_day, "11:00", phone=TEL_DIA))
    assert second.status_code == 429, second.text
    assert "Ya tienes una cita" in second.json()["error"]
    assert second.json()["whatsapp_url"].startswith("https://wa.me/")
    rows = server.sql(f"SELECT COUNT(*) AS n FROM bookings WHERE date = '{free_day.isoformat()}'")
    assert rows[0]["n"] == 1


def test_expired_pending_does_not_count_towards_the_daily_cap(api, server, free_day):
    first = api.post("/api/bookings", json=booking_payload(free_day, "08:00", phone=TEL_VENCIDA))
    assert first.status_code == 201
    expire_booking(server, first.json()["code"])
    assert api.post("/api/bookings", json=booking_payload(free_day, "11:00", phone=TEL_VENCIDA)).status_code == 201


def test_phone_daily_cap_blocks_the_ninth(server, free_day):
    seed_attempts(server, config.MAX_PER_PHONE_DAY, phone=_tel(TEL_24H))
    with server.client() as c:
        r = c.post("/api/bookings", json=booking_payload(free_day, "08:00", phone=TEL_24H))
    assert r.status_code == 429, r.text
    assert "varias reservas" in r.json()["error"]
    assert server.sql(f"SELECT COUNT(*) AS n FROM bookings WHERE date = '{free_day.isoformat()}'")[0]["n"] == 0


def test_ip_hourly_cap_blocks_the_twenty_first(server, free_day):
    seed_attempts(server, config.MAX_PER_IP_HOUR, ip="1.2.3.4")
    with server.client(headers={"cf-connecting-ip": "1.2.3.4"}) as c:
        r = c.post("/api/bookings", json=booking_payload(free_day, "08:00"))
    assert r.status_code == 429, r.text
    assert "Demasiadas reservas" in r.json()["error"]


def test_ip_cap_does_not_leak_into_other_connections(server, free_day):
    seed_attempts(server, config.MAX_PER_IP_HOUR, ip="1.2.3.4")
    with server.client(headers={"cf-connecting-ip": "5.6.7.8"}) as c:
        r = c.post("/api/bookings", json=booking_payload(free_day, "08:00"))
    assert r.status_code == 201, r.text


def test_successful_booking_records_the_attempt(server, api, free_day):
    r = api.post("/api/bookings", json=booking_payload(free_day, "08:00", phone=TEL_INTENTOS))
    assert r.status_code == 201, r.text
    rows = server.sql(f"SELECT ip FROM booking_attempts WHERE phone = '{_tel(TEL_INTENTOS)}'")
    assert len(rows) == 1
    assert rows[0]["ip"]


def test_attempts_are_only_counted_on_success(api, server, free_day):
    tel = "300 000 0005"
    api.post("/api/bookings", json=booking_payload(free_day, "08:00", phone=tel))                    # 201
    api.post("/api/bookings", json=booking_payload(free_day, "08:00", phone=tel))                    # 409, horario tomado
    api.post("/api/bookings", json=booking_payload(free_day, "14:00", phone=tel, form_token="corta"))  # 422
    counted = server.sql(
        f"SELECT COUNT(*) AS n FROM booking_attempts WHERE phone = '{_tel(tel)}'"
    )[0]["n"]
    assert counted == 1


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
    assert r.headers.get("strict-transport-security", "").startswith("max-age=")


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
