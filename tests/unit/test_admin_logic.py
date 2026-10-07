from datetime import date
from urllib.parse import unquote

import pytest

import admin_logic as al
import config

ROW = {
    "code": "AC-ABC23", "service_id": "lifting", "service_name": "Lifting de pestañas", "category": "pestanas",
    "price": None, "duration_min": 90, "date": "2026-10-05", "start_min": 540, "end_min": 630,
    "customer_name": "María José Pérez", "phone": "573001234567", "neighborhood": "Granada",
    "address": "Calle 10 # 1-1", "notes": "", "status": "pending", "created_at": "2026-10-01 12:00:00", "expired": 0,
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
    b = al.serialize_booking(ROW)
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
    assert edit["busy_until_min"] == 795
    assert "service_id" not in edit and "neighborhood" not in edit


def test_parse_edit_service_only_keeps_the_time():
    edit = al.parse_booking_edit({"service_id": "combo-triple"}, ROW)
    assert edit["service_id"] == "combo-triple"
    assert edit["service_name"] == "Combo Triple"
    assert edit["category"] == "combos"
    assert edit["duration_min"] == config.DURACION_TRIPLE_X
    assert edit["start_min"] == 540                 # horario actual
    assert edit["end_min"] == 540 + config.DURACION_TRIPLE_X
    assert edit["busy_until_min"] == 540 + config.DURACION_TRIPLE_X + config.TRAVEL_BUFFER_MIN


def test_parse_edit_time_and_service_together():
    edit = al.parse_booking_edit({"time": "09:30", "service_id": "volumen"}, ROW)
    assert edit["start_min"] == 570
    assert edit["end_min"] == 570 + 90
    assert edit["busy_until_min"] == 570 + 90 + config.TRAVEL_BUFFER_MIN
    assert edit["service_name"] == "Volumen"


def test_parse_edit_location_only():
    edit = al.parse_booking_edit(
        {"neighborhood": "El Peñón", "address": "Avenida 4 Oeste # 2-10"}, ROW)
    assert edit == {"neighborhood": "El Peñón", "address": "Avenida 4 Oeste # 2-10"}


def test_parse_edit_location_is_cleaned_and_truncated():
    edit = al.parse_booking_edit(
        {"neighborhood": "  El   Peñón  ", "address": "x" * 300}, ROW)
    assert edit["neighborhood"] == "El Peñón"
    assert len(edit["address"]) == 160


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


@pytest.mark.parametrize("data", [
    {"neighborhood": "x"},
    {"address": "abc"},
    {"neighborhood": "", "address": "Avenida 4 Oeste # 2-10"},
])
def test_parse_edit_rejects_short_location(data):
    with pytest.raises(al.AdminError):
        al.parse_booking_edit(data, ROW)


def test_parse_edit_without_changes():
    with pytest.raises(al.AdminError) as e:
        al.parse_booking_edit({}, ROW)
    assert e.value.status == 400


def test_parse_edit_rejects_non_dict():
    with pytest.raises(al.AdminError) as e:
        al.parse_booking_edit(None, ROW)
    assert e.value.status == 400


@pytest.mark.parametrize("data,ok", [
    ({"time": "11:00"}, True),
    ({"service_id": "volumen"}, True),
    ({"neighborhood": "El Peñón"}, True),
    ({"address": "Avenida 4 Oeste # 2-10"}, True),
    ({"status": "confirmed"}, False),
    ({}, False),
    ({"status": "confirmed", "time": "11:00"}, True),
])
def test_has_edit_fields(data, ok):
    assert al.has_edit_fields(data) is ok
