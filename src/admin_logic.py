"""Reglas del panel de administración. Lógica pura (sin Cloudflare)."""

import re
from datetime import date

import availability
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
        "neighborhood": row["neighborhood"],
        "address": row["address"],
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
            f"en {b['address']} ({b['neighborhood']}). Código {b['code']}. ¡Nos vemos! — Angélica"
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
