import json
from datetime import date, timedelta

from workers import fetch

import availability
import config
import db
import messages
import notify
from responses import client_ip, error, json_response, read_json
from validation import ValidationError, validate_booking

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def get_config(env):
    today = availability.now_local().date()
    first, last = availability.booking_window(today)
    return json_response(
        {
            "categories": config.CATEGORIES,
            "services": [{**s, "price_label": messages.format_price(s["price"])} for s in config.ALL_SERVICES],
            "open_weekdays": [d for d, spans in config.BUSINESS_HOURS.items() if spans],
            "window": {"first": first.isoformat(), "last": last.isoformat()},
            "whatsapp": config.WHATSAPP,
            "coverage": config.COBERTURA_X,
            "travel_fee_label": (
                None if config.RECARGO_DOMICILIO_X is None else messages.format_price(config.RECARGO_DOMICILIO_X)
            ),
            "turnstile_site_key": getattr(env, "TURNSTILE_SITE_KEY", None),
        },
        headers={"cache-control": "public, max-age=300"},
    )


async def get_availability(env, qs: dict):
    """?service=<id>&from=YYYY-MM-DD&days=N → horarios por día."""
    service = config.SERVICES_BY_ID.get((qs.get("service") or [""])[0])
    if not service:
        return error(400, "Servicio inválido.")

    now = availability.now_local()
    window_first, window_last = availability.booking_window(now.date())
    try:
        first = date.fromisoformat((qs.get("from") or [window_first.isoformat()])[0])
        days = max(1, min(int((qs.get("days") or ["7"])[0]), config.BOOKING_WINDOW_DAYS))
    except ValueError:
        return error(400, "Parámetros inválidos.")

    first = max(first, window_first)
    last = min(first + timedelta(days=days - 1), window_last)
    busy = await db.busy_intervals(env.DB, first, last) if first <= last else {}

    result = []
    d = first
    while d <= last:
        result.append({
            "date": d.isoformat(),
            "slots": availability.day_slots(d, service["duration"], busy.get(d.isoformat(), []), now),
        })
        d += timedelta(days=1)
    return json_response({"service": service["id"], "days": result})


def created_payload(record: dict, service: dict, b: dict, status: str = "pending") -> dict:
   return {
        "code": record["code"],
        "status": status,
        "summary": {
            "service": service["name"],
            "date": messages.format_date_es(b["date"]),
            "time": messages.format_time_es(b["time"]),
            "price": messages.format_price(service["price"]),
        },
        "whatsapp_url": messages.whatsapp_url(messages.booking_whatsapp_text(record)),
    }


def replay_response(row):
    if row["status"] in ("cancelled", "completed"):
        return error(409, "Esa cita ya no está activa. Escríbenos por WhatsApp y la volvemos a agendar.")
    record = {
        "code": row["code"],
        "service_name": row["service_name"],
        "date": date.fromisoformat(row["date"]),
        "time": availability.to_hhmm(row["start_min"]),
        "name": row["customer_name"],
        "neighborhood": row["neighborhood"],
        "address": row["address"],
        "notes": row["notes"],
    }
    service = {"name": row["service_name"], "price": row["price"]}
    return json_response(
        created_payload(record, service, {"date": record["date"], "time": record["time"]}, row["status"]),
        status=201,
    )


async def limits_response(env, request, b: dict):
    phone = b["phone"]
    if await db.active_bookings_for_phone(env.DB, phone, b["date"]) >= config.MAX_ACTIVE_PER_PHONE_DAY:
        message = messages.LIMIT_ONE_PER_DAY
    elif await db.phone_attempts_in_day(env.DB, phone) >= config.MAX_PER_PHONE_DAY:
        message = messages.LIMIT_PHONE_DAY
    elif await db.ip_attempts_in_hour(env.DB, client_ip(request)) >= config.MAX_PER_IP_HOUR:
        message = messages.LIMIT_IP_HOUR
    else:
        return None
    return error(429, message, whatsapp_url=messages.limit_whatsapp_url(message))


async def create_booking(env, request):
    data = await read_json(request)
    if data is None:
        return error(400, "Solicitud inválida.")
    raw_token = data.get("form_token")
    if isinstance(raw_token, str) and raw_token.strip():
        previous = await db.get_booking_by_form_token(env.DB, raw_token.strip())
        if previous:
            return replay_response(previous)

    if not await verify_turnstile(env, data.get("turnstile_token"), request):
        return error(403, "No pudimos verificar que eres una persona. Recarga la página e intenta de nuevo.")

    try:
        b = validate_booking(data)
    except ValidationError as e:
        return error(422, "Revisa los datos del formulario.", fields=e.errors)

    blocked = await limits_response(env, request, b)
    if blocked:
        return blocked

    service = b["service"]
    start = availability.to_minutes(b["time"])
    now = availability.now_local()
    busy = await db.busy_intervals(env.DB, b["date"], b["date"])
    if not availability.is_slot_bookable(b["date"], start, service["duration"], busy.get(b["date"].isoformat(), []), now):
        return error(409, "Ese horario ya no está disponible. Elige otro, por favor.")

    record = {
        **b,
        "service_id": service["id"],
        "service_name": service["name"],
        "category": service["category"],
        "price": service["price"],
        "duration": service["duration"],
        "start_min": start,
        "end_min": start + service["duration"],
        "busy_until_min": start + service["duration"] + config.TRAVEL_BUFFER_MIN,
    }

    inserted = False
    for _ in range(3):
        record["code"] = db.new_code()
        try:
            inserted = await db.insert_booking_if_free(env.DB, record)
            break
        except Exception as e:
            conflict = db.classify_unique_error(e)
            if conflict == "form_token":
                winner = await db.get_booking_by_form_token(env.DB, record["form_token"])
                if winner:
                    return replay_response(winner)
                raise
            if conflict != "code":
                raise
    if not inserted:
        return error(409, "Ese horario acaba de ser reservado. Elige otro, por favor.")

    await db.record_booking_attempt(env.DB, client_ip(request), b["phone"])
    notify.notify_booking_later(env, record)
    return json_response(created_payload(record, service, b), status=201)


async def verify_turnstile(env, token, request) -> bool:
    secret = getattr(env, "TURNSTILE_SECRET", None)
    if not secret:
        print("TURNSTILE_SECRET no está configurado; se rechaza la reserva.")
        return False
    if not token or not isinstance(token, str) or len(token) > 2048:
        return False
    resp = await fetch(
        TURNSTILE_VERIFY_URL,
        method="POST",
        headers={"content-type": "application/json"},
        body=json.dumps({
            "secret": secret,
            "response": token,
            "remoteip": request.headers.get("cf-connecting-ip"),
        }),
    )
    result = await resp.json()
    return bool(result.get("success"))
