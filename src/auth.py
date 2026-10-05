import base64
import hashlib
import hmac
import json
import time

COOKIE_NAME = "ac_admin"
MFA_COOKIE_NAME = "ac_admin_mfa"
COOKIE_PATH = "/api/admin"
SESSION_TTL_S = 7 * 24 * 3600
MFA_TTL_S = 300  # 5 minutos para completar el segundo paso

MAX_FAILED_LOGINS = 5
MFA_MAX_ATTEMPTS = 10
LOCKOUT_WINDOW_MIN = 15


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _key(session_secret: str, admin_password: str) -> bytes:
    return hashlib.sha256(f"{session_secret}\x00{admin_password}".encode()).digest()


def password_matches(given: str, expected: str) -> bool:
    # Compara resúmenes de igual longitud en tiempo constante.
    a = hashlib.sha256(str(given or "").encode()).digest()
    b = hashlib.sha256(str(expected or "").encode()).digest()
    return bool(expected) and hmac.compare_digest(a, b)


def create_token(
    session_secret: str, admin_password: str, now: float | None = None, ttl_s: int = SESSION_TTL_S,
) -> str:
    now = time.time() if now is None else now
    payload = _b64e(json.dumps({"exp": int(now) + ttl_s}, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(_key(session_secret, admin_password), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token(token: str | None, session_secret: str, admin_password: str, now: float | None = None) -> bool:
    if not token or token.count(".") != 1 or not session_secret or not admin_password:
        return False
    payload, sig = token.split(".")
    expected = _b64e(hmac.new(_key(session_secret, admin_password), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return False
    try:
        exp = int(json.loads(_b64d(payload))["exp"])
    except (ValueError, KeyError, TypeError):
        return False
    return (time.time() if now is None else now) < exp


def create_mfa_ticket(session_secret: str, admin_password: str, now: float | None = None) -> str:
    """Ticket de un solo paso: certifica que la contraseña fue correcta y
    da MFA_TTL_S para completar el segundo factor."""
    return create_token(session_secret, admin_password, now, ttl_s=MFA_TTL_S)


def verify_mfa_ticket(token: str | None, session_secret: str, admin_password: str, now: float | None = None) -> bool:
    return verify_token(token, session_secret, admin_password, now)


def read_cookie(header: str | None, name: str = COOKIE_NAME) -> str | None:
    for part in (header or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return None


def session_cookie(token: str, secure: bool = True) -> str:
    flags = f"Path={COOKIE_PATH}; Max-Age={SESSION_TTL_S}; HttpOnly; SameSite=Strict"
    return f"{COOKIE_NAME}={token}; {flags}" + ("; Secure" if secure else "")


def clear_cookie(secure: bool = True) -> str:
    flags = f"Path={COOKIE_PATH}; Max-Age=0; HttpOnly; SameSite=Strict"
    return f"{COOKIE_NAME}=; {flags}" + ("; Secure" if secure else "")


def mfa_cookie(token: str, secure: bool = True) -> str:
    flags = f"Path={COOKIE_PATH}; Max-Age={MFA_TTL_S}; HttpOnly; SameSite=Strict"
    return f"{MFA_COOKIE_NAME}={token}; {flags}" + ("; Secure" if secure else "")


def clear_mfa_cookie(secure: bool = True) -> str:
    flags = f"Path={COOKIE_PATH}; Max-Age=0; HttpOnly; SameSite=Strict"
    return f"{MFA_COOKIE_NAME}=; {flags}" + ("; Secure" if secure else "")


def same_origin(origin: str | None, request_url: str) -> bool:
    if not origin:
        return False
    from urllib.parse import urlparse
    o, r = urlparse(origin), urlparse(request_url)
    return (o.scheme, o.netloc) == (r.scheme, r.netloc)
