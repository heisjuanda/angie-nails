"""Respuestas JSON comunes de la API."""

from workers import Response

NO_STORE = {"cache-control": "no-store"}


def json_response(data, status: int = 200, headers: dict | None = None) -> Response:
    return Response.json(data, status=status, headers={**NO_STORE, **(headers or {})})


def json_cookies_response(data, cookies: list[str], status: int = 200) -> Response:
    from js import Headers as JsHeaders

    headers = JsHeaders.new()
    headers.set("cache-control", NO_STORE["cache-control"])
    for cookie in cookies:
        headers.append("set-cookie", cookie)
    return Response.json(data, status=status, headers=headers)


def error(status: int, message: str, **extra) -> Response:
    return json_response({"error": message, **extra}, status=status)


async def read_json(request):
    try:
        data = await request.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None
