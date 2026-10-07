"""Reglas del panel de administración. Lógica pura (sin Cloudflare)."""

import re
from datetime import date

import availability
import config
import messages

# Cambios de estado permitidos para una cita.
TRANSITIONS = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"completed", "cancelled"},
    "cancelled": set(),
    "completed": set(),
}

STATUS_LABEL = {
    "pending": "Pendiente",
    "confirmed": "Confirmada",
    "cancelled": "Cancelada",
    "completed": "Completada",
}

CODE_RE = re.compile(r"^AC-[A-Z0-9]{5}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class AdminError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, set())


def parse_block(data: dict) -> dict:
    """Valida un bloqueo de agenda. Devuelve {date, start_min, end_min, reason}."""
    if not isinstance(data, dict):
        raise AdminError("Solicitud inválida.", 400)
    try:
        day = date.fromisoformat(str(data.get("date", "")))
    except ValueError:
        raise AdminError("Elige una fecha válida.")

    if data.get("all_day"):
        start, end = 0, 24 * 60
    else:
        s, e = str(data.get("start", "")), str(data.get("end", ""))
        if not (_TIME_RE.match(s) and _TIME_RE.match(e)):
            raise AdminError("Escribe hora de inicio y fin (HH:MM).")
        start, end = availability.to_minutes(s), availability.to_minutes(e)
        if end <= start:
            raise AdminError("La hora de fin debe ser posterior a la de inicio.")

    reason = " ".join(str(data.get("reason") or "").split())[:120]
    return {"date": day, "start_min": start, "end_min": end, "reason": reason}


#  edición de citas: horario, servicio y fecha.

EDITABLE_STATUSES = {"pending", "confirmed"}
EDIT_FIELDS = ("time", "service_id", "date")


def has_edit_fields(data) -> bool:
    return isinstance(data, dict) and any(f in data for f in EDIT_FIELDS)


def valid_start_minutes(day: date) -> set[int]:
    minutes: set[int] = set()
    for open_hhmm, close_hhmm in config.BUSINESS_HOURS.get(day.weekday(), []):
        start = availability.to_minutes(open_hhmm)
        close = availability.to_minutes(close_hhmm)
        while start < close:
            minutes.add(start)
            start += config.SLOT_STEP_MIN
    return minutes


def parse_booking_edit(data: dict, row: dict, now=None) -> dict:
    if not isinstance(data, dict):
        raise AdminError("Solicitud inválida.", 400)
    if "customer_name" in data or "phone" in data:
        raise AdminError("El nombre y el teléfono no se pueden cambiar.")

    if now is None:
        now = availability.now_local()
    today = now.date()
    now_min = now.hour * 60 + now.minute

    out: dict = {}
    current_date = date.fromisoformat(row["date"])
    target_date = current_date

    if "date" in data:
        try:
            target_date = date.fromisoformat(str(data.get("date") or ""))
        except ValueError:
            raise AdminError("Elige una fecha válida.")
        if target_date < today:
            raise AdminError("La fecha no puede ser en el pasado.")
        if (target_date - today).days > 120:
            raise AdminError("La fecha está fuera del rango permitido.")
        out["date"] = target_date.isoformat()

    start_min = int(row["start_min"])
    duration = int(row["duration_min"])

    if "time" in data:
        time = str(data.get("time") or "")
        if not _TIME_RE.match(time):
            raise AdminError("Elige una hora válida.")
        start_min = availability.to_minutes(time)
        out["start_min"] = start_min

    valid_slots = valid_start_minutes(target_date)
    if not valid_slots:
        raise AdminError("No hay atención en esa fecha.")
    if start_min not in valid_slots:
        raise AdminError("Ese horario queda fuera del horario de atención.")

    if target_date < today or (target_date == today and start_min <= now_min):
        raise AdminError("Ese horario ya pasó.")

    if "service_id" in data:
        service = config.SERVICES_BY_ID.get(str(data.get("service_id") or ""))
        if not service:
            raise AdminError("Elige un servicio válido.")
        out.update({
            "service_id": service["id"],
            "service_name": service["name"],
            "category": service["category"],
            "price": service["price"],
            "duration_min": service["duration"],
        })
        duration = service["duration"]

    if "start_min" in out or "duration_min" in out or "date" in out:
        out["start_min"] = start_min
        out["end_min"] = start_min + duration
        out["busy_until_min"] = start_min + duration

    if not out:
        raise AdminError("Nada que cambiar.", 400)
    return out


def serialize_booking(row: dict) -> dict:
    d = date.fromisoformat(row["date"])
    return {
        "code": row["code"],
        "service_id": row["service_id"],
        "service_name": row["service_name"],
        "category": row["category"],
        "price_label": messages.format_price(row["price"]),
        "date": row["date"],
        "date_label": messages.format_date_es(d),
        "start": availability.to_hhmm(int(row["start_min"])),
        "end": availability.to_hhmm(int(row["end_min"])),
        "start_label": messages.format_time_es(availability.to_hhmm(int(row["start_min"]))),
        "customer_name": row["customer_name"],
        "phone": row["phone"],
        "notes": row["notes"],
        "status": row["status"],
        "status_label": STATUS_LABEL.get(row["status"], row["status"]),
        "expired": bool(row.get("expired")),
        "created_at": row["created_at"],
    }


def customer_message(b: dict) -> str:
    """Mensaje que Angélica envía a la clienta según el estado de la cita."""
    first = b["customer_name"].split(" ")[0]
    when = f"el {b['date_label']} a las {b['start_label']}"
    if b["status"] == "confirmed":
        return (
            f"Hola {first} ✨ Te confirmo tu cita de {b['service_name']} {when} "
            f"en el estudio. Código {b['code']}. ¡Nos vemos! — Angélica"
        )
    if b["status"] == "cancelled":
        return (
            f"Hola {first}, lamentablemente no puedo atender tu cita de {b['service_name']} {when} "
            f"(código {b['code']}). Escríbeme y buscamos otro horario 💕 — Angélica"
        )
    if b["status"] == "completed":
        return f"¡Gracias {first}! Fue un gusto atenderte ✨ Si te gustó, cuéntamelo en Instagram @lashes_nails_a.c 💅"
    return f"Hola {first} ✨ Recibí tu solicitud de cita de {b['service_name']} {when} (código {b['code']})."


def with_customer_link(b: dict) -> dict:
    return {**b, "whatsapp_url": messages.whatsapp_url(customer_message(b), number=b["phone"])}
