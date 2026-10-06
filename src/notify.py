import json
from urllib.parse import quote

import config
import messages

CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"
RESEND_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "AC Luxury Aesthetics <noreply@resend.dev>"

_pending: set = set()


def _env(env, name: str) -> str | None:
    value = getattr(env, name, None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def whatsapp_url(phone: str, text: str, apikey: str) -> str:
    return f"{CALLMEBOT_URL}?phone={quote(phone)}&text={quote(text)}&apikey={quote(apikey)}"


def email_payload(subject: str, text: str, sender: str, to: str) -> dict:
    return {"from": sender, "to": to, "subject": subject, "text": text}


def booking_subject(record: dict) -> str:
    when = f"{messages.format_date_es(record['date'])} {messages.format_time_es(record['time'])}"
    return f"Nueva cita {record['code']}: {record['service_name']} · {when}"


async def send_whatsapp(env, text: str, http=None) -> bool:
    apikey = _env(env, "CALLMEBOT_APIKEY")
    if not apikey:
        return False
    phone = _env(env, "NOTIFY_PHONE") or config.WHATSAPP
    if http is None:
        from workers import fetch as http

    resp = await http(whatsapp_url(phone, text, apikey))
    if not resp.ok:
        print(f"notify: CallMeBot respondió {resp.status}")
        return False
    try:
        data = await resp.json()
    except Exception:
        return True
    # CallMeBot puede contestar 200 con {"result": false, "error": ...}.
    if isinstance(data, dict) and data.get("result") is False:
        print(f"notify: CallMeBot rechazó el mensaje: {data.get('error')}")
        return False
    return True


async def send_email(env, subject: str, text: str, http=None) -> bool:
    apikey = _env(env, "RESEND_API_KEY")
    to = _env(env, "NOTIFY_EMAIL")
    if not apikey or not to:
        return False
    sender = _env(env, "RESEND_FROM") or DEFAULT_FROM
    if http is None:
        from workers import fetch as http

    resp = await http(
        RESEND_URL,
        method="POST",
        headers={
            "authorization": f"Bearer {apikey}",
            "content-type": "application/json",
        },
        body=json.dumps(email_payload(subject, text, sender, to)),
    )
    if not resp.ok:
        print(f"notify: Resend respondió {resp.status}")
        return False
    return True


async def notify_booking(env, record: dict, http=None) -> list[str]:
    text = messages.booking_whatsapp_text(record)
    fired: list[str] = []
    try:
        if await send_whatsapp(env, text, http=http):
            fired.append("whatsapp")
    except Exception as e:
        print(f"notify: WhatsApp falló: {e!r}")
    try:
        if await send_email(env, booking_subject(record), text, http=http):
            fired.append("email")
    except Exception as e:
        print(f"notify: email falló: {e!r}")
    return fired


def notify_booking_later(env, record: dict) -> None:
    try:
        from asyncio import ensure_future

        from workers import wait_until

        task = ensure_future(notify_booking(env, record))
        _pending.add(task)
        task.add_done_callback(_pending.discard)
        wait_until(task)
    except Exception as e:
        print(f"notify: no se pudo agendar el aviso: {e!r}")
