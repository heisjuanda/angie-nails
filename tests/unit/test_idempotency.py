import pytest

from db import classify_unique_error


@pytest.mark.parametrize("message,expected", [
    ("UNIQUE constraint failed: bookings.form_token", "form_token"),
    ("UNIQUE constraint failed: bookings.code", "code"),
    ("UNIQUE constraint failed: bookings.code, bookings.form_token", "form_token"),
    ("UNIQUE constraint failed:otra.tabla.form_token", "other"),
    ("UNIQUE constraint failed: bookings.id", "other"),
    ("no such table: bookings", None),
    ("D1_ERROR: D1_ERROR: UNIQUE constraint failed: bookings.code", "code"),
    ("", None),
])
def test_detects_which_constraint_failed(message, expected):
    assert classify_unique_error(Exception(message)) == expected


def test_form_token_is_checked_before_code():
    exc = Exception("UNIQUE constraint failed: bookings.form_token")
    assert classify_unique_error(exc) == "form_token"
    assert classify_unique_error(exc) != "code"
