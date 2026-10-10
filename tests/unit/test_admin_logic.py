from datetime import date, datetime, timedelta
from urllib.parse import unquote

import pytest

import admin_logic as al
import availability
import config

_next_day = availability.now_local().date() + timedelta(days=2)
while _next_day.weekday() == 6:
    _next_day += timedelta(days=1)
FUTURE_DATE = _next_day.isoformat()

ROW = {
    "code": "AC-ABC23", "service_id": "lifting", "service_name": "Lifting de pestañas", "category": "pestanas",
    "price": None, "duration_min": 90, "date": FUTURE_DATE, "start_min": 540, "end_min": 630,
    "customer_name": "María José Pérez", "phone": "573001234567",
    "notes": "", "status": "pending", "created_at": "2026-10-01 12:00:00", "expired": 0,
}


@pytest.mark.parametrize("current,new,ok", [
    ("pending", "confirmed", True),
    ("pending", "cancelled", True),
    ("pending", "completed", False),
    ("confirmed", "completed", True),
    ("confirmed", "cancelled", True),
    ("confirmed", "pending", False),
    ("cancelled", "confirmed", False),
    ("completed", "cancelled", False),
    ("pending", "pending", False),
    ("pending", "hacked", False),
    ("desconocido", "confirmed", False),
    ("pending", None, False),
])
def test_transitions(current, new, ok):
    assert al.can_transition(current, new) is ok


def test_parse_block_all_day():
    b = al.parse_block({"date": "2026-10-05", "all_day": True, "reason": "  viaje   a Bogotá "})
    assert b == {"date": date(2026, 10, 5), "start_min": 0, "end_min": 1440, "reason": "viaje a Bogotá"}


def test_parse_block_partial():
    b = al.parse_block({"date": "2026-10-05", "start": "08:00", "end": "12:30"})
    assert (b["start_min"], b["end_min"]) == (480, 750)


@pytest.mark.parametrize("data,status", [
    ({"date": "x", "all_day": True}, 422),
    ({"date": "2026-10-05", "start": "12:00", "end": "08:00"}, 422),
    ({"date": "2026-10-05", "start": "10:00", "end": "10:00"}, 422),
    ({"date": "2026-10-05", "start": "8", "end": "9"}, 422),
    ({"date": "2026-10-05"}, 422),
    (None, 400),
    ([], 400),
])
def test_parse_block_errors(data, status):
    with pytest.raises(al.AdminError) as e:
        al.parse_block(data)
    assert e.value.status == status


def test_parse_block_reason_truncated():
    assert len(al.parse_block({"date": "2026-10-05", "all_day": True, "reason": "x" * 500})["reason"]) == 120


def test_serialize_booking():
    b = al.serialize_booking({**ROW, "date": "2026-10-05"})
    assert b["start"] == "09:00" and b["end"] == "10:30"
    assert b["start_label"] == "9:00 a. m."
    assert b["date_label"] == "lunes 5 oct"
    assert b["price_label"] == "$ X"
    assert b["status_label"] == "Pendiente"
    assert b["expired"] is False


@pytest.mark.parametrize("status,needle", [
    ("confirmed", "Te confirmo"),
    ("cancelled", "no puedo atender"),
    ("completed", "Gracias"),
    ("pending", "Recibí tu solicitud"),
])
def test_customer_link_goes_to_customer_phone(status, needle):
    b = al.with_customer_link(al.serialize_booking({**ROW, "status": status}))
    assert b["whatsapp_url"].startswith("https://wa.me/573001234567?text=")
    text = unquote(b["whatsapp_url"])
    assert needle in text
    assert "Hola María" in text or "Gracias María" in text


@pytest.mark.parametrize("code,ok", [("AC-ABC23", True), ("AC-abc23", False), ("AC-ABC2", False), ("../x", False), ("AC-ABC234", False)])
def test_code_regex(code, ok):
    assert bool(al.CODE_RE.match(code)) is ok


#  edición de citas (horario, servicio y ubicación)

def test_valid_start_minutes_covers_the_labor_grid():
    # 2026-10-05 es lunes; 2026-10-11 es domingo (sin agenda).
    minutes = al.valid_start_minutes(date(2026, 10, 5))
    assert 480 in minutes and 1050 in minutes      # 08:00 y 17:30
    assert 479 not in minutes and 1080 not in minutes  # fuera de horario
    assert 495 not in minutes                       # fuera de la grilla de 30 min
    assert al.valid_start_minutes(date(2026, 10, 11)) == set()


def test_parse_edit_time_only():
    edit = al.parse_booking_edit({"time": "11:00"}, ROW)
    assert edit["start_min"] == 660
    assert edit["end_min"] == 750
    assert edit["busy_until_min"] == 750
    assert "service_id" not in edit


def test_parse_edit_service_only_keeps_the_time():
    edit = al.parse_booking_edit({"service_id": "combo-triple"}, ROW)
    assert edit["service_id"] == "combo-triple"
    assert edit["service_name"] == "Combo Triple"
    assert edit["category"] == "combos"
    assert edit["duration_min"] == config.DURACION_TRIPLE_X
    assert edit["start_min"] == 540                 # horario actual
    assert edit["end_min"] == 540 + config.DURACION_TRIPLE_X
    assert edit["busy_until_min"] == 540 + config.DURACION_TRIPLE_X


def test_parse_edit_time_and_service_together():
    edit = al.parse_booking_edit({"time": "09:30", "service_id": "volumen"}, ROW)
    assert edit["start_min"] == 570
    assert edit["end_min"] == 570 + 90
    assert edit["busy_until_min"] == 570 + 90
    assert edit["service_name"] == "Volumen"


@pytest.mark.parametrize("data", [
    {"customer_name": "Otra Persona"},
    {"phone": "573009999999"},
    {"customer_name": "Otra", "phone": "573009999999", "time": "11:00"},
])
def test_parse_edit_rejects_name_and_phone(data):
    with pytest.raises(al.AdminError) as e:
        al.parse_booking_edit(data, ROW)
    assert e.value.status == 422
    assert "nombre" in str(e.value) and "teléfono" in str(e.value)


@pytest.mark.parametrize("time", ["07:00", "18:00", "08:15", "25:00", "8:00", "", None, 1100])
def test_parse_edit_rejects_invalid_time(time):
    with pytest.raises(al.AdminError):
        al.parse_booking_edit({"time": time}, ROW)


def test_parse_edit_rejects_unknown_service():
    with pytest.raises(al.AdminError) as e:
        al.parse_booking_edit({"service_id": "no-existe"}, ROW)
    assert e.value.status == 422


def test_parse_edit_without_changes():
    with pytest.raises(al.AdminError) as e:
        al.parse_booking_edit({}, ROW)
    assert e.value.status == 400


def test_parse_edit_rejects_non_dict():
    with pytest.raises(al.AdminError) as e:
        al.parse_booking_edit(None, ROW)
    assert e.value.status == 400


def test_parse_edit_date_only():
    new_day = _next_day + timedelta(days=1)
    if new_day.weekday() == 6:
        new_day += timedelta(days=1)
    edit = al.parse_booking_edit({"date": new_day.isoformat()}, ROW)
    assert edit["date"] == new_day.isoformat()
    assert edit["start_min"] == 540
    assert edit["end_min"] == 630


def test_parse_edit_date_time_and_service():
    new_day = _next_day + timedelta(days=1)
    if new_day.weekday() == 6:
        new_day += timedelta(days=1)
    edit = al.parse_booking_edit({"date": new_day.isoformat(), "time": "14:00", "service_id": "acrilicas"}, ROW)
    assert edit["date"] == new_day.isoformat()
    assert edit["start_min"] == 840
    assert edit["service_id"] == "acrilicas"


def test_parse_edit_rejects_past_date():
    yesterday = availability.now_local().date() - timedelta(days=1)
    with pytest.raises(al.AdminError) as e:
        al.parse_booking_edit({"date": yesterday.isoformat()}, ROW)
    assert "pasado" in str(e.value)


def test_parse_edit_rejects_past_time_today():
    now = datetime(2026, 10, 7, 15, 30, tzinfo=config.TZ)
    today_row = {**ROW, "date": "2026-10-07"}
    with pytest.raises(al.AdminError) as e:
        al.parse_booking_edit({"time": "09:00"}, today_row, now=now)
    assert "ya pasó" in str(e.value)


def test_parse_edit_accepts_future_time_today():
    now = datetime(2026, 10, 7, 15, 30, tzinfo=config.TZ)
    today_row = {**ROW, "date": "2026-10-07"}
    edit = al.parse_booking_edit({"time": "16:00"}, today_row, now=now)
    assert edit["start_min"] == 960


def test_parse_edit_rejects_date_without_service():
    sunday = _next_day
    while sunday.weekday() != 6:
        sunday += timedelta(days=1)
    with pytest.raises(al.AdminError) as e:
        al.parse_booking_edit({"date": sunday.isoformat()}, ROW)
    assert "atención" in str(e.value)


@pytest.mark.parametrize("data,ok", [
    ({"time": "11:00"}, True),
    ({"service_id": "volumen"}, True),
    ({"date": "2026-10-15"}, True),
    ({"combo_selections": {"unas": "manicure", "cejas": "henna"}}, True),
    ({"status": "confirmed"}, False),
    ({}, False),
    ({"status": "confirmed", "time": "11:00"}, True),
    ({"status": "confirmed", "date": "2026-10-15"}, True),
])
def test_has_edit_fields(data, ok):
    assert al.has_edit_fields(data) is ok


def test_parse_edit_combo_with_subservices():
    edit = al.parse_booking_edit(
        {"service_id": "combo-unas-pestanas:semipermanente+lifting"},
        ROW,
    )
    assert edit["service_id"] == "combo-unas-pestanas:semipermanente+lifting"
    assert edit["service_name"] == "Combo Uñas + Pestañas (Semipermanente + Lifting de pestañas)"
    assert edit["category"] == "combos"
    assert edit["start_min"] == 540
    assert edit["end_min"] == 540 + edit["duration_min"]


def test_parse_edit_combo_via_combo_selections_only():
    combo_row = {
        **ROW,
        "service_id": "combo-unas-cejas:semipermanente+diseno-cejas",
        "service_name": "Combo Uñas + Cejas (Semipermanente + Diseño de cejas)",
        "category": "combos",
    }
    edit = al.parse_booking_edit(
        {"combo_selections": {"unas": "acrilicas", "cejas": "henna"}},
        combo_row,
    )
    assert edit["service_id"] == "combo-unas-cejas:acrilicas+henna"
    assert edit["service_name"] == "Combo Uñas + Cejas (Uñas acrílicas + Henna)"


def test_is_past_booking():
    now = datetime(2026, 10, 10, 11, 0, tzinfo=config.TZ)
    assert al.is_past_booking({**ROW, "date": "2026-10-09", "start_min": 900}, now=now) is True
    assert al.is_past_booking({**ROW, "date": "2026-10-10", "start_min": 600}, now=now) is True   # 10:00 <= 11:00
    assert al.is_past_booking({**ROW, "date": "2026-10-10", "start_min": 660}, now=now) is True   # 11:00 <= 11:00
    assert al.is_past_booking({**ROW, "date": "2026-10-10", "start_min": 690}, now=now) is False  # 11:30 > 11:00
    assert al.is_past_booking({**ROW, "date": "2026-10-11", "start_min": 480}, now=now) is False


def test_db_active_sql_logic_in_sqlite():
    import sqlite3
    import db

    assert config.PENDING_TTL_HOURS == 24
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE bookings (code TEXT, status TEXT, created_at TEXT, date TEXT, start_min INTEGER)")
    # Insertar escenarios relativos al reloj actual de SQLite:
    # 1. Cita futura creada hace 2 horas (< 24h) -> ACTIVA (1)
    # 2. Cita futura creada hace 13 horas (< 24h) -> ACTIVA (1)
    # 3. Cita futura creada hace 25 horas (> 24h) -> VENCIDA (0)
    # 4. Cita pasada (ayer) creada hace 1 hora (< 24h) -> VENCIDA (0)
    # 5. Cita de hoy cuya hora ya pasó hace 1 hora, creada hace 2 horas (< 24h) -> VENCIDA (0)
    # 6. Cita confirmada en el pasado y creada hace 50 horas -> ACTIVA (1)
    con.executescript(f"""
        INSERT INTO bookings VALUES
          ('FUTURA_2H',  'pending',   datetime('now', '-2 hours'),  date('now', '-5 hours', '+3 days'), 600),
          ('FUTURA_13H', 'pending',   datetime('now', '-13 hours'), date('now', '-5 hours', '+3 days'), 600),
          ('FUTURA_25H', 'pending',   datetime('now', '-25 hours'), date('now', '-5 hours', '+3 days'), 600),
          ('AYER_1H',    'pending',   datetime('now', '-1 hours'),  date('now', '-5 hours', '-1 days'), 600),
          ('HOY_PASADA', 'pending',   datetime('now', '-2 hours'),  date('now', '-5 hours'),            0),
          ('CONFIRMADA', 'confirmed', datetime('now', '-50 hours'), date('now', '-5 hours', '-1 days'), 600);
    """)
    rows = dict(con.execute(f"SELECT code, {db._active()} FROM bookings").fetchall())
    assert rows == {
        "FUTURA_2H": 1,
        "FUTURA_13H": 1,
        "FUTURA_25H": 0,
        "AYER_1H": 0,
        "HOY_PASADA": 0,
        "CONFIRMADA": 1,
    }


