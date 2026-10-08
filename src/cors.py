"""Manejo de CORS y política de orígenes seguros para la API."""

import re
from urllib.parse import urlparse

# Dominio oficial actual de producción en Cloudflare Workers
DEFAULT_WORKER_ORIGIN = "https://ac-luxury-aesthetics.heisjuanda.workers.dev"

# Puertos y hosts locales para pruebas y desarrollo
# Acepta localhost y 127.0.0.1 con cualquier puerto o sin puerto
_LOCAL_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?$")


def parse_allowed_origins(env) -> set[str]:
    """Obtiene el conjunto de orígenes configurados en variables de entorno."""
    origins: set[str] = set()
    if not env:
        return origins

    # ALLOWED_ORIGINS: lista separada por comas (ej. "https://acluxuryaesthetics.com,https://preview.midominio.com")
    raw = getattr(env, "ALLOWED_ORIGINS", None)
    if raw:
        for item in str(raw).split(","):
            val = item.strip().rstrip("/")
            if val:
                origins.add(val.lower())

    # CUSTOM_DOMAIN: dominio personalizado opcional (ej. "acluxuryaesthetics.com" o "https://acluxuryaesthetics.com")
    custom = getattr(env, "CUSTOM_DOMAIN", None)
    if custom:
        val = str(custom).strip().rstrip("/")
        if val:
            if not val.startswith("http://") and not val.startswith("https://"):
                origins.add(f"https://{val.lower()}")
            else:
                origins.add(val.lower())

    return origins


def is_allowed_origin(origin: str | None, env=None, request_url: str | None = None) -> bool:
    """Valida si un encabezado Origin pertenece a la lista blanca autorizada:
    1. Mismo origen que la petición actual (SOP exacto por scheme y netloc).
    2. Dominio oficial del worker de Cloudflare.
    3. Entorno local (http://localhost:* o http://127.0.0.1:*).
    4. Orígenes adicionales definidos en ALLOWED_ORIGINS o CUSTOM_DOMAIN.
    """
    if not origin:
        return False

    norm = origin.strip().rstrip("/")
    if not norm:
        return False

    # 1. Mismo origen con la URL del request
    if request_url:
        o = urlparse(norm)
        r = urlparse(request_url)
        if o.scheme and o.netloc and (o.scheme, o.netloc) == (r.scheme, r.netloc):
            return True

    # 2. Dominio oficial del worker
    if norm.lower() == DEFAULT_WORKER_ORIGIN.lower():
        return True

    # 3. Localhost / 127.0.0.1 para pruebas y desarrollo local
    if _LOCAL_ORIGIN_RE.match(norm.lower()):
        return True

    # 4. Dominios configurados por variables de entorno (futuro dominio)
    if norm.lower() in parse_allowed_origins(env):
        return True

    return False


def is_admin_origin_allowed(origin: str | None, env=None, request_url: str | None = None) -> bool:
    """Validación específica y estricta para el panel de administración /api/admin/.
    Permite:
    1. Mismo origen estricto con la URL de la petición (mismo host y puerto).
    2. Dominio oficial de producción del worker.
    3. Dominios explícitos configurados en variables de entorno.
    (No permite puertos arbitrarios no coincidentes en local para evitar CSRF local en puertos no autorizados).
    """
    if not origin:
        return False

    norm = origin.strip().rstrip("/")
    if not norm:
        return False

    # Mismo origen estricto (mismo esquema y mismo netloc/puerto)
    if request_url:
        o = urlparse(norm)
        r = urlparse(request_url)
        if o.scheme and o.netloc and (o.scheme, o.netloc) == (r.scheme, r.netloc):
            return True

    # Dominio oficial
    if norm.lower() == DEFAULT_WORKER_ORIGIN.lower():
        return True

    # Dominios de variables de entorno
    if norm.lower() in parse_allowed_origins(env):
        return True

    return False


def get_cors_headers(origin: str | None, env=None, request_url: str | None = None) -> dict[str, str]:
    """Devuelve los encabezados CORS correspondientes solo si el origen está permitido."""
    if not is_allowed_origin(origin, env, request_url):
        return {}

    return {
        "access-control-allow-origin": origin.strip().rstrip("/"),
        "access-control-allow-credentials": "true",
        "vary": "Origin",
    }


def preflight_response(origin: str | None, env=None, request_url: str | None = None):
    """Responde a peticiones preflight OPTIONS."""
    from responses import error
    from workers import Response

    if not is_allowed_origin(origin, env, request_url):
        return error(403, "Origen no permitido.")

    norm = origin.strip().rstrip("/")
    headers = {
        "access-control-allow-origin": norm,
        "access-control-allow-methods": "GET, POST, PATCH, DELETE, OPTIONS",
        "access-control-allow-headers": "Content-Type, Authorization, X-Requested-With",
        "access-control-allow-credentials": "true",
        "access-control-max-age": "86400",
        "vary": "Origin",
        "cache-control": "no-store",
    }
    return Response(None, status=204, headers=headers)


def apply_cors(response, origin: str | None, env=None, request_url: str | None = None):
    """Añade cabeceras CORS a una respuesta existente si el origen es legítimo."""
    if not response or not origin:
        return response

    if not is_allowed_origin(origin, env, request_url):
        return response

    norm = origin.strip().rstrip("/")
    try:
        js_headers = getattr(getattr(response, "js_object", None), "headers", None)
        if js_headers and hasattr(js_headers, "set"):
            js_headers.set("access-control-allow-origin", norm)
            js_headers.set("access-control-allow-credentials", "true")
            if hasattr(js_headers, "append"):
                js_headers.append("vary", "Origin")
            else:
                js_headers.set("vary", "Origin")
    except Exception:
        pass

    return response
