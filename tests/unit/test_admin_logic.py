from datetime import date
from urllib.parse import unquote

import pytest

import admin_logic as al

ROW = {
    "code": "AC-ABC23", "service_id": "lifting", "service_name": "Lifting de pestañas", "category": "pestanas",
    "price": None, "date": "2026-10-05", "start_min": 540, "end_min": 630,
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
