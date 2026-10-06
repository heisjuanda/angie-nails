from datetime import date, timedelta

import admin_logic
import auth
import availability
import db
import mfa
from responses import client_ip, error, json_cookies_response, json_response, read_json

MAX_RANGE_DAYS = 120
PAGE_SIZE = 25
MAX_PAGE_SIZE = 500


def _secrets(env) -> tuple[str | None, str | None]:
    return getattr(env, "SESSION_SECRET", None), getattr(env, "ADMIN_PASSWORD", None)


def _totp_secret(env) -> str | None:
    return getattr(env, "TOTP_SECRET", None) or None


def _is_https(request) -> bool:
    return request.url.startswith("https://")


async def is_authenticated(env, request) -> bool:
    secret, password = _secrets(env)
    token = auth.read_cookie(request.headers.get("cookie"))
    if not auth.verify_token(token, secret, password):
        return False
    claims = auth.token_claims(token)
    return await db.session_active(env.DB, claims.get("sid"))


def _date_range(qs: dict, default_back: int, default_forward: int) -> tuple[date, date]:
    today = availability.now_local().date()
    first = date.fromisoformat((qs.get("from") or [(today - timedelta(days=default_back)).isoformat()])[0])
    last = date.fromisoformat((qs.get("to") or [(today + timedelta(days=default_forward)).isoformat()])[0])
    if last < first or (last - first).days > MAX_RANGE_DAYS:
        raise ValueError("rango")
    return first, last


def _pagination(qs: dict) -> tuple[int, int]:
    try:
        page = int((qs.get("page") or ["1"])[0])
        per_page = int((qs.get("per_page") or [str(PAGE_SIZE)])[0])
    except (TypeError, ValueError):
        raise ValueError("paginación")
    return max(1, page), max(1, min(per_page, MAX_PAGE_SIZE))


#  sesión

async def login(env, request):
    secret, password = _secrets(env)
    if not secret or not password:
        return error(503, "El panel no está configurado (faltan ADMIN_PASSWORD / SESSION_SECRET).")

    ip = client_ip(request)
    if await db.failed_logins(env.DB, ip) >= auth.MAX_FAILED_LOGINS:
        return error(429, f"Demasiados intentos. Espera {auth.LOCKOUT_WINDOW_MIN} minutos e intenta de nuevo.")

    data = await read_json(request)
    if data is None:
        return error(400, "Solicitud inválida.")
    if not auth.password_matches(data.get("password"), password):
        await db.record_failed_login(env.DB, ip)
        return error(401, "Contraseña incorrecta.")

    await db.clear_failed_logins(env.DB, ip)
    totp = _totp_secret(env)
    if totp:
        # Segundo factor: la sesión solo se emite tras verificar el código.
        ticket = auth.create_mfa_ticket(secret, password)
        return json_response({"ok": True, "mfa_required": True},
                             headers={"set-cookie": auth.mfa_cookie(ticket, _is_https(request))})
    token = auth.create_token(secret, password)
    claims = auth.token_claims(token)
    await db.create_session(env.DB, claims["sid"], claims["exp"])
    return json_response({"ok": True}, headers={"set-cookie": auth.session_cookie(token, _is_https(request))})


async def verify_mfa(env, request):
    secret, password = _secrets(env)
    totp = _totp_secret(env)
    if not secret or not password or not totp:
        return error(503, "El panel no está configurado para el segundo factor.")

    ip = client_ip(request)
    if await db.failed_mfa(env.DB, ip) >= auth.MFA_MAX_ATTEMPTS:
        return error(429, f"Demasiados intentos. Espera {auth.LOCKOUT_WINDOW_MIN} minutos e intenta de nuevo.")

    data = await read_json(request)
    if data is None:
        return error(400, "Solicitud inválida.")

    ticket = auth.read_cookie(request.headers.get("cookie"), auth.MFA_COOKIE_NAME)
    if not auth.verify_mfa_ticket(ticket, secret, password):
        return error(401, "Primero ingresa la contraseña.", step="password")

    if not mfa.verify_code(totp, data.get("code")):
        await db.record_failed_mfa(env.DB, ip)
        return error(401, "Código incorrecto.", step="code")

    await db.clear_failed_mfa(env.DB, ip)
    token = auth.create_token(secret, password)
    claims = auth.token_claims(token)
    await db.create_session(env.DB, claims["sid"], claims["exp"])
    secure = _is_https(request)
    return json_cookies_response({"ok": True}, [
        auth.clear_mfa_cookie(secure),
        auth.session_cookie(token, secure),
    ])


async def logout(env, request):
    claims = auth.token_claims(auth.read_cookie(request.headers.get("cookie")))
    await db.delete_session(env.DB, claims.get("sid"))
    secure = _is_https(request)
    return json_cookies_response({"ok": True}, [
        auth.clear_cookie(secure),
        auth.clear_mfa_cookie(secure),
    ])


def session(authenticated: bool):
    # Responde 200 siempre: el panel lo usa para decidir qué vista mostrar.
    return json_response({"authenticated": authenticated})


#  citas

async def list_bookings(env, qs: dict):
    try:
        first, last = _date_range(qs, default_back=1, default_forward=30)
    except ValueError:
        return error(400, "Rango de fechas inválido.")
    try:
        page, per_page = _pagination(qs)
    except ValueError:
        return error(400, "Paginación inválida.")
    status = (qs.get("status") or [None])[0]
    if status and status not in admin_logic.TRANSITIONS:
        return error(400, "Estado inválido.")
    rows = await db.list_bookings(env.DB, first, last, status,
                                  limit=per_page, offset=(page - 1) * per_page)
    total = await db.count_bookings(env.DB, first, last, status)
    stats = await db.booking_stats(env.DB, availability.now_local().date())
    return json_response({
        "from": first.isoformat(),
        "to": last.isoformat(),
        "stats": stats,
        "total": total,
        "page": page,
        "per_page": per_page,
        "bookings": [admin_logic.with_customer_link(admin_logic.serialize_booking(r)) for r in rows],
    })


async def update_booking(env, request, code: str):
    if not admin_logic.CODE_RE.match(code):
        return error(404, "Cita no encontrada.")
    data = await read_json(request)
    if data is None:
        return error(400, "Solicitud inválida.")
    new = data.get("status")

    row = await db.get_booking(env.DB, code)
    if not row:
        return error(404, "Cita no encontrada.")
    current = row["status"]
    if not admin_logic.can_transition(current, new):
        return error(422, f"No se puede pasar de «{admin_logic.STATUS_LABEL.get(current, current)}» a ese estado.")

    if not await db.set_booking_status(env.DB, code, current, new):
        if new == "confirmed":
            return error(409, "No se puede confirmar: ese horario ya lo ocupa otra cita.")
        return error(409, "La cita cambió mientras tanto. Recarga la agenda.")

    updated = await db.get_booking(env.DB, code)
    return json_response({"booking": admin_logic.with_customer_link(admin_logic.serialize_booking(updated))})


#  bloqueos

async def list_blocks(env, qs: dict):
    try:
        first, last = _date_range(qs, default_back=0, default_forward=60)
    except ValueError:
        return error(400, "Rango de fechas inválido.")
    rows = await db.list_blocks(env.DB, first, last)
    return json_response({"blocks": [
        {
            "id": r["id"],
            "date": r["date"],
            "start": availability.to_hhmm(int(r["start_min"])),
            "end": availability.to_hhmm(int(r["end_min"])) if int(r["end_min"]) < 1440 else "24:00",
            "all_day": int(r["start_min"]) == 0 and int(r["end_min"]) >= 1440,
            "reason": r["reason"],
        }
        for r in rows
    ]})


async def create_block(env, request):
    data = await read_json(request)
    try:
        block = admin_logic.parse_block(data)
    except admin_logic.AdminError as e:
        return error(e.status, str(e))
    block_id = await db.insert_block(env.DB, block)
    overlapping = await db.count_active_overlapping(env.DB, block)
    return json_response({"id": block_id, "overlapping_bookings": overlapping}, status=201)


async def remove_block(env, block_id: str):
    if not block_id.isdigit():
        return error(404, "Bloqueo no encontrado.")
    if not await db.delete_block(env.DB, int(block_id)):
        return error(404, "Bloqueo no encontrado.")
    return json_response({"ok": True})
