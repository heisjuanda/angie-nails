from datetime import date
from urllib.parse import unquote

import pytest

from messages import booking_whatsapp_text, format_date_es, format_price, format_time_es, whatsapp_url
from helpers import booking_payload
from validation import ValidationError, normalize_phone, validate_booking

VALID = {
    "service_id": "semipermanente",
    "date": "2026-10-05",
    "time": "11:00",
    "name": "  María   Pérez ",
    "phone": "+57 300 123 4567",
    "form_token": "a1b2c3d4e5f6a7b8c9d0",
}


@pytest.mark.parametrize("raw,expected", [
    ("3001234567", "573001234567"),
    ("300 123 4567", "573001234567"),
    ("+57 300-123-4567", "573001234567"),
    ("573001234567", "573001234567"),
    ("6021234567", None),
    ("30012345", None),
    ("", None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_valid_booking_is_cleaned():
    out = validate_booking(VALID)
    assert out["name"] == "María Pérez"
    assert out["phone"] == "573001234567"
    assert out["date"] == date(2026, 10, 5)
    assert out["service"]["id"] == "semipermanente"
    assert out["form_token"] == "a1b2c3d4e5f6a7b8c9d0"


@pytest.mark.parametrize("bad", ["", "corta", "x" * 65, "con espacio/simbolo$$", None])
def test_form_token_is_required_and_bounded(bad):
    with pytest.raises(ValidationError) as e:
        validate_booking({**VALID, "form_token": bad})
    assert "form_token" in e.value.errors


def test_helper_payload_is_valid_by_default():
    out = validate_booking(booking_payload(date(2026, 10, 5), "11:00"))
    assert out["phone"].startswith("573") and len(out["phone"]) == 12
    assert out["service"]["id"] == "semipermanente"


def test_invalid_booking_reports_each_field():
    with pytest.raises(ValidationError) as e:
        validate_booking({"service_id": "nope", "date": "x", "time": "25:00", "phone": "1"})
    assert set(e.value.errors) >= {"service_id", "date", "time", "name", "phone"}


def test_non_dict_rejected():
    with pytest.raises(ValidationError):
        validate_booking(["x"])


def test_spanish_formats():
    assert format_date_es(date(2026, 9, 30)) == "miércoles 30 sep"
    assert format_time_es("11:00") == "11:00 a. m."
    assert format_time_es("13:30") == "1:30 p. m."
    assert format_time_es("12:00") == "12:00 p. m."
    assert format_price(None) == "$ X"
    assert format_price(85000) == "$ 85.000"


def test_whatsapp_link_is_encoded():
    text = booking_whatsapp_text({
        "code": "AC-ABCDE", "service_name": "Semipermanente", "date": date(2026, 9, 30),
        "time": "11:00", "name": "Ana",
    })
    url = whatsapp_url(text, number="573001112233")
    assert url.startswith("https://wa.me/573001112233?text=")
    assert " " not in url and "\n" not in url
    assert "AC-ABCDE" in unquote(url)


def test_configured_whatsapp_is_a_valid_colombian_mobile():
    import config
    assert normalize_phone(config.WHATSAPP) == config.WHATSAPP
    assert whatsapp_url("hola").startswith(f"https://wa.me/{config.WHATSAPP}?text=")


def test_validate_booking_resolves_combo_selections():
    out = validate_booking({
        **VALID,
        "service_id": "combo-unas-pestanas",
        "combo_selections": {"unas": "semipermanente", "pestanas": "lifting"},
    })
    assert out["service"]["id"] == "combo-unas-pestanas:semipermanente+lifting"
    assert out["service"]["name"] == "Combo Uñas + Pestañas (Semipermanente + Lifting de pestañas)"


def test_validate_booking_resolves_composite_combo_id():
    out = validate_booking({
        **VALID,
        "service_id": "combo-triple:semipermanente+diseno-cejas+pelo-a-pelo",
    })
    assert out["service"]["id"] == "combo-triple:semipermanente+diseno-cejas+pelo-a-pelo"
    assert out["service"]["name"] == "Combo Triple (Semipermanente + Diseño de cejas + Extensiones pelo a pelo)"


def test_validate_booking_rejects_incomplete_or_mismatched_combo():
    with pytest.raises(ValidationError) as e1:
        validate_booking({
            **VALID,
            "service_id": "combo-unas-cejas",
            "combo_selections": {"unas": "semipermanente"},
        })
    assert "service_id" in e1.value.errors

    with pytest.raises(ValidationError) as e2:
        validate_booking({
            **VALID,
            "service_id": "combo-unas-cejas",
            "combo_selections": {"unas": "semipermanente", "cejas": "lifting"},
        })
    assert "service_id" in e2.value.errors

