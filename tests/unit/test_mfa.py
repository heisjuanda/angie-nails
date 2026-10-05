import re

import pytest

import mfa

# Vectores oficiales del RFC 6238 (Apéndice B): SHA-1, 6 dígitos, periodo
# de 30 s y semilla ASCII "12345678901234567890" codificada en base32.
# (Los valores de 8 dígitos del RFC son 94287082, 07081804, 14050471,
# 89005924, 69279037 y 65353130; aquí se muestran los 6 dígitos finales.)
RFC6238 = [
    (59, "287082"),
    (1111111109, "081804"),
    (1111111111, "050471"),
    (1234567890, "005924"),
    (2000000000, "279037"),
    (20000000000, "353130"),
]
SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32("12345678901234567890")


def test_rfc6238_test_vectors():
    for timestamp, expected in RFC6238:
        assert mfa.code_at(SECRET, timestamp) == expected, timestamp


def test_verify_accepts_current_and_adjacent_periods():
    now = 1234567890
    assert mfa.verify_code(SECRET, mfa.code_at(SECRET, now), now)
    assert mfa.verify_code(SECRET, mfa.code_at(SECRET, now - mfa.PERIOD_S), now)
    assert mfa.verify_code(SECRET, mfa.code_at(SECRET, now + mfa.PERIOD_S), now)
    # Dos periodos de diferencia ya no sirve (fuera de la ventana).
    assert not mfa.verify_code(SECRET, mfa.code_at(SECRET, now - 2 * mfa.PERIOD_S), now)
    assert not mfa.verify_code(SECRET, mfa.code_at(SECRET, now + 2 * mfa.PERIOD_S), now)


@pytest.mark.parametrize("bad", ["", " ", "abc", "12345", "1234567", "000000", None, 123456])
def test_verify_rejects_malformed_codes(bad):
    assert not mfa.verify_code(SECRET, bad, 1234567890)


def test_verify_rejects_missing_secret():
    assert not mfa.verify_code("", "123456", 1234567890)
    assert not mfa.verify_code(None, "123456", 1234567890)


def test_random_secret_is_unique_base32():
    a, b = mfa.random_secret(), mfa.random_secret()
    assert a != b
    assert re.fullmatch(r"[A-Z2-7]{32}", a)


def test_provisioning_uri():
    uri = mfa.provisioning_uri(SECRET)
    assert uri.startswith("otpauth://totp/")
    assert "secret=" + SECRET in uri
    assert "issuer=AC%20Luxury%20Aesthetics" in uri
