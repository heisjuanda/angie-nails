try:
    from workers import Response
except ModuleNotFoundError:
    class Response:  # Fallback para pruebas unitarias fuera de Pyodide
        def __init__(self, body=None, status: int = 200, headers: dict | None = None):
            self.body = body
            self.status = status
            self.headers = dict(headers or {})

        @classmethod
        def json(cls, data, status: int = 200, headers: dict | None = None):
            return cls(data, status=status, headers=headers)

BASE_HEADERS = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "strict-transport-security": "max-age=31536000",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}


def json_response(data, status: int = 200, headers: dict | None = None) -> Response:
    return Response.json(data, status=status, headers={**BASE_HEADERS, **(headers or {})})


def json_cookies_response(data, cookies: list[str], status: int = 200) -> Response:
    from js import Headers as JsHeaders

    headers = JsHeaders.new()
    for key, value in BASE_HEADERS.items():
        headers.set(key, value)
    for cookie in cookies:
        headers.append("set-cookie", cookie)
    return Response.json(data, status=status, headers=headers)


def error(status: int, message: str, **extra) -> Response:
    return json_response({"error": message, **extra}, status=status)


def client_ip(request) -> str:
    return request.headers.get("cf-connecting-ip") or "local"


async def read_json(request):
    try:
        data = await request.json()
    except Exception:
        return None
    return data if isinstance(data, dict) else None
