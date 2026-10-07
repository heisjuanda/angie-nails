import re
from datetime import date

import config

MAX_LEN = {"name": 80, "notes": 500}

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_FORM_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


class ValidationError(Exception):
    def __init__(self, errors: dict[str, str]):
        super().__init__("datos inválidos")
        self.errors = errors


def normalize_phone(raw: str) -> str | None:
    """Acepta celulares colombianos: 3001234567, +57 300 123 4567, 57-300..."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("57"):
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("3"):
        return "57" + digits
    return None


def _clean(value, field: str) -> str:
    text = " ".join(str(value or "").split())
    return text[: MAX_LEN[field]]


def validate_booking(data: dict) -> dict:
    """Devuelve los datos limpios o lanza ValidationError con un mensaje por campo."""
    if not isinstance(data, dict):
        raise ValidationError({"_": "Solicitud inválida."})

    errors: dict[str, str] = {}
    out: dict = {}

    service = config.SERVICES_BY_ID.get(str(data.get("service_id", "")))
    if not service:
        errors["service_id"] = "Elige un servicio."
    out["service"] = service

    try:
        out["date"] = date.fromisoformat(str(data.get("date", "")))
    except ValueError:
        errors["date"] = "Elige una fecha."

    time = str(data.get("time", ""))
    if not _TIME_RE.match(time):
        errors["time"] = "Elige una hora."
    out["time"] = time

    out["name"] = _clean(data.get("name"), "name")
    if len(out["name"]) < 2:
        errors["name"] = "Escribe tu nombre."

    out["phone"] = normalize_phone(str(data.get("phone", "")))
    if not out["phone"]:
        errors["phone"] = "Escribe un celular válido, p. ej. 300 000 0000."

    out["notes"] = _clean(data.get("notes"), "notes")

    out["form_token"] = str(data.get("form_token") or "")
    if not _FORM_TOKEN_RE.match(out["form_token"]):
        errors["form_token"] = "Recarga la página e intenta de nuevo."

    if errors:
        raise ValidationError(errors)
    return out
