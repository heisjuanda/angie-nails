import re
import traceback
from urllib.parse import parse_qs, urlparse

from workers import WorkerEntrypoint

import admin_api
import auth
import config
import public_api
from responses import error

_BOOKING_RE = re.compile(r"^/api/admin/bookings/([^/]+)$")
_BLOCK_RE = re.compile(r"^/api/admin/blocks/([^/]+)$")

_env_applied = False


def _apply_env(env) -> None:
    global _env_applied
    if _env_applied:
        return
    _env_applied = True
    raw = getattr(env, "BOOKING_WINDOW_DAYS", None)
    if not raw:
        return
    try:
        config.BOOKING_WINDOW_DAYS = max(1, int(raw))
    except ValueError:
        print(f"BOOKING_WINDOW_DAYS inválido en el entorno: {raw!r}")


async def _drain_body(request) -> None:
    if request.method in ("GET", "HEAD"):
        return
    try:
        if not request.body_used:
            await request.bytes()
    except Exception:
        pass


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        _apply_env(self.env)
        try:
            response = await self.route(request)
        except Exception:
            print(traceback.format_exc())
            response = error(500, "Ocurrió un error inesperado. Intenta de nuevo o escríbenos por WhatsApp.")
        await _drain_body(request)
        return response

    async def route(self, request):
        env = self.env
        url = urlparse(request.url)
        path = url.path.rstrip("/") or "/"
        method = request.method
        qs = parse_qs(url.query)

        # --- público
        if path == "/api/config" and method == "GET":
            return public_api.get_config(env)
        if path == "/api/availability" and method == "GET":
            return await public_api.get_availability(env, qs)
        if path == "/api/bookings" and method == "POST":
            return await public_api.create_booking(env, request)

        # --- panel de administración
        if path.startswith("/api/admin/"):
            if method != "GET" and not auth.same_origin(request.headers.get("origin"), request.url):
                return error(403, "Origen no permitido.")
            if path == "/api/admin/login" and method == "POST":
                return await admin_api.login(env, request)
            if path == "/api/admin/mfa" and method == "POST":
                return await admin_api.verify_mfa(env, request)
            if path == "/api/admin/logout" and method == "POST":
                return await admin_api.logout(env, request)
            if path == "/api/admin/session" and method == "GET":
                return admin_api.session(await admin_api.is_authenticated(env, request))
            if not await admin_api.is_authenticated(env, request):
                return error(401, "Inicia sesión para continuar.")

            if path == "/api/admin/bookings" and method == "GET":
                return await admin_api.list_bookings(env, qs)
            if (m := _BOOKING_RE.match(path)) and method == "PATCH":
                return await admin_api.update_booking(env, request, m.group(1))
            if path == "/api/admin/blocks" and method == "GET":
                return await admin_api.list_blocks(env, qs)
            if path == "/api/admin/blocks" and method == "POST":
                return await admin_api.create_block(env, request)
            if (m := _BLOCK_RE.match(path)) and method == "DELETE":
                return await admin_api.remove_block(env, m.group(1))

        return error(404, "Ruta no encontrada.")
