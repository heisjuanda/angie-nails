"""Respuestas JSON comunes de la API."""

from workers import Response

NO_STORE = {"cache-control": "no-store"}


def json_response(data, status: int = 200, headers: dict | None = None) -> Response:
    return Response.json(data, status=status, headers={**NO_STORE, **(headers or {})})


def error(status: int, message: str, **extra) -> Response:
    return json_response({"error": message, **extra}, status=status)


async def read_json(request):
    """Devuelve el cuerpo como dict, o None si no es un objeto JSON válido."""
    try:
        data = await request.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None
