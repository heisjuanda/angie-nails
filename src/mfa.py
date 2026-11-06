import base64
import hashlib
import hmac
import secrets as _secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD_S = 30
WINDOW = 1
_BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"


def random_secret() -> str:
    return "".join(_secrets.choice(_BASE32_ALPHABET) for _ in range(32))


def _default_mfa_params() -> tuple[str, str]:
    try:
        import config
        issuer = config.STUDIO.get("booking", {}).get("admin_mfa_issuer") or config.STUDIO.get("name", "AC Luxury Aesthetics")
        account = config.STUDIO.get("booking", {}).get("admin_mfa_account", "angie")
        return str(account or "angie"), str(issuer or "AC Luxury Aesthetics")
    except Exception:
        return "angie", "AC Luxury Aesthetics"


def provisioning_uri(
    secret: str, account: str | None = None, issuer: str | None = None,
) -> str:
    def_account, def_issuer = _default_mfa_params()
    act = account if account is not None else def_account
    iss = issuer if issuer is not None else def_issuer
    label = f"{quote(iss)}:{quote(act)}"
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(iss)}"


def code_at(secret: str, timestamp: int, offset: int = 0) -> str:
    counter = int(timestamp) // PERIOD_S + offset
    digest = hmac.new(_key_bytes(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    start = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[start : start + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(code).zfill(DIGITS)


def current_code(secret: str, now: float | None = None) -> str:
    return code_at(secret, int(time.time() if now is None else now))


def verify_code(secret: str, code: str, now: float | None = None) -> bool:
    if not secret or not code:
        return False
    given = str(code).strip()
    if not (given.isdigit() and len(given) == DIGITS):
        return False
    ts = int(time.time() if now is None else now)
    for offset in range(-WINDOW, WINDOW + 1):
        if hmac.compare_digest(code_at(secret, ts, offset), given):
            return True
    return False


def _key_bytes(secret: str) -> bytes:
    padded = secret.upper().replace(" ", "")
    padded += "=" * ((8 - len(padded) % 8) % 8)
    return base64.b32decode(padded)
