from datetime import date
from urllib.parse import quote

import config

DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def format_date_es(d: date) -> str:
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def format_time_es(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    suffix = "a. m." if h < 12 else "p. m."
    return f"{(h % 12) or 12}:{m:02d} {suffix}"


def format_price(price: int | None) -> str:
    if price is None:
        return "$ X"
    return "$ " + f"{price:,}".replace(",", ".")


def booking_whatsapp_text(b: dict) -> str:
    lines = [
        "Hola Angélica ✨ Acabo de agendar una cita en la web:",
        "",
        f"• Código: {b['code']}",
        f"• Servicio: {b['service_name']}",
        f"• Fecha: {format_date_es(b['date'])}",
        f"• Hora: {format_time_es(b['time'])}",
        f"• Nombre: {b['name']}",
    ]
    if b.get("notes"):
        lines.append(f"• Notas: {b['notes']}")
    lines += ["", "¿Me confirmas, por favor?"]
    return "\n".join(lines)


def whatsapp_url(text: str, number: str = config.WHATSAPP) -> str:
    return f"https://wa.me/{number}?text={quote(text)}"


# Topes de la agenda. Todos devuelven 429 y ofrecen WhatsApp, porque un tope tiene que
# sonar a ayuda y no a castigo: con CGNAT un falso positivo por IP es fácil.

LIMIT_ONE_PER_DAY = (
    "Ya tienes una cita para ese día. Si quieres añadir otro servicio, escríbenos por "
    "WhatsApp y lo ajustamos."
)
LIMIT_PHONE_DAY = (
    "Ya hiciste varias reservas en las últimas 24 horas. Si necesitas cambiar algo, "
    "escríbenos por WhatsApp."
)
LIMIT_IP_HOUR = (
    "Demasiadas reservas desde esta conexión. Si eres clienta y necesitas agendar, "
    "escríbenos por WhatsApp."
)


def limit_whatsapp_url(limit_message: str) -> str:
    return whatsapp_url(
        "Hola Angélica ✨\n\n"
        f"{limit_message}\n\n"
        "Podemos acomodarlo, escríbeme por acá."
    )
