import time

import pytest

import auth

SECRET, PASSWORD = "s3cr3t-firma", "clave-admin"


def test_token_roundtrip():
    token = auth.create_token(SECRET, PASSWORD)
    assert auth.verify_token(token, SECRET, PASSWORD)


def test_token_expires():
    old = time.time() - auth.SESSION_TTL_S - 5
    assert not auth.verify_token(auth.create_token(SECRET, PASSWORD, now=old), SECRET, PASSWORD)


def test_token_valid_until_just_before_expiry():
    now = time.time()
    token = auth.create_token(SECRET, PASSWORD, now=now)
    assert auth.verify_token(token, SECRET, PASSWORD, now=now + auth.SESSION_TTL_S - 1)
    assert not auth.verify_token(token, SECRET, PASSWORD, now=now + auth.SESSION_TTL_S + 1)


@pytest.mark.parametrize("mutate", [
    lambda t: t[:-2] + ("AA" if not t.endswith("AA") else "BB"),
    lambda t: "e30" + t[3:],
    lambda t: t.replace(".", ""),
    lambda t: t + ".extra",
    lambda t: "",
])
def test_tampered_tokens_rejected(mutate):
    assert not auth.verify_token(mutate(auth.create_token(SECRET, PASSWORD)), SECRET, PASSWORD)


def test_changing_password_or_secret_invalidates_sessions():
    token = auth.create_token(SECRET, PASSWORD)
    assert not auth.verify_token(token, SECRET, "otra-clave")
    assert not auth.verify_token(token, "otro-secreto", PASSWORD)


def test_missing_config_never_authenticates():
    token = auth.create_token(SECRET, PASSWORD)
    assert not auth.verify_token(token, None, PASSWORD)
    assert not auth.verify_token(token, SECRET, None)
    assert not auth.verify_token(None, SECRET, PASSWORD)


def test_forged_payload_with_valid_shape_rejected():
    forged = auth._b64e(b'{"exp":9999999999}') + "." + auth._b64e(b"x" * 32)
    assert not auth.verify_token(forged, SECRET, PASSWORD)


@pytest.mark.parametrize("given,expected,ok", [
    ("clave-admin", "clave-admin", True),
    ("clave-admiN", "clave-admin", False),
    ("", "clave-admin", False),
    (None, "clave-admin", False),
    ("", "", False),
])
def test_password_matches(given, expected, ok):
    assert auth.password_matches(given, expected) is ok


def test_read_cookie():
    header = "foo=1; ac_admin=abc.def; bar=2"
    assert auth.read_cookie(header) == "abc.def"
    assert auth.read_cookie("foo=1") is None
    assert auth.read_cookie(None) is None


def test_cookie_flags():
    c = auth.session_cookie("tok", secure=True)
    for flag in ("HttpOnly", "SameSite=Strict", "Secure", "Path=/api/admin", f"Max-Age={auth.SESSION_TTL_S}"):
        assert flag in c
    assert "Secure" not in auth.session_cookie("tok", secure=False)
    assert "Max-Age=0" in auth.clear_cookie()


def test_mfa_ticket_roundtrip():
    ticket = auth.create_mfa_ticket(SECRET, PASSWORD)
    assert auth.verify_mfa_ticket(ticket, SECRET, PASSWORD)


def test_mfa_ticket_expires_early():
    old = time.time() - auth.MFA_TTL_S - 5
    assert not auth.verify_mfa_ticket(auth.create_mfa_ticket(SECRET, PASSWORD, now=old), SECRET, PASSWORD)


def test_mfa_ticket_bound_to_secret_and_password():
    ticket = auth.create_mfa_ticket(SECRET, PASSWORD)
    assert not auth.verify_mfa_ticket(ticket, "otro-secreto", PASSWORD)
    assert not auth.verify_mfa_ticket(ticket, SECRET, "otra-clave")


def test_mfa_cookie_flags():
    c = auth.mfa_cookie("tok", secure=True)
    assert c.startswith(f"{auth.MFA_COOKIE_NAME}=")
    for flag in ("HttpOnly", "SameSite=Strict", "Secure", "Path=/api/admin", f"Max-Age={auth.MFA_TTL_S}"):
        assert flag in c
    assert "Secure" not in auth.mfa_cookie("tok", secure=False)
    assert auth.clear_mfa_cookie().startswith(f"{auth.MFA_COOKIE_NAME}=;")
    assert "Max-Age=0" in auth.clear_mfa_cookie()


@pytest.mark.parametrize("origin,url,ok", [
    ("https://sitio.dev", "https://sitio.dev/api/admin/login", True),
    ("https://evil.dev", "https://sitio.dev/api/admin/login", False),
    ("http://sitio.dev", "https://sitio.dev/api/admin/login", False),
    ("https://sitio.dev:8443", "https://sitio.dev/api/admin/login", False),
    (None, "https://sitio.dev/api/admin/login", False),
    ("null", "https://sitio.dev/api/admin/login", False),
])
def test_same_origin(origin, url, ok):
    assert auth.same_origin(origin, url) is ok
