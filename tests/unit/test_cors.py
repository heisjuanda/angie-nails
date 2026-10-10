from types import SimpleNamespace

import pytest

import cors


def test_default_worker_origin_allowed():
    assert cors.is_allowed_origin("https://ac-luxury-aesthetics.heisjuanda.workers.dev")
    assert cors.is_allowed_origin("https://ac-luxury-aesthetics.heisjuanda.workers.dev/")


@pytest.mark.parametrize("origin", [
    "http://localhost",
    "http://localhost:8787",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1",
    "http://127.0.0.1:8787",
    "http://127.0.0.1:5500",
    "https://localhost:8787",
])
def test_localhost_and_loopback_allowed(origin):
    assert cors.is_allowed_origin(origin)


@pytest.mark.parametrize("origin", [
    "https://evil.com",
    "http://evil.example",
    "https://ac-luxury-aesthetics.heisjuanda.workers.dev.evil.com",
    "https://attacker.workers.dev",
    "null",
    "",
    None,
])
def test_malicious_origins_rejected(origin):
    assert not cors.is_allowed_origin(origin)


def test_env_allowed_origins_supported():
    env = SimpleNamespace(ALLOWED_ORIGINS="https://acluxuryaesthetics.com, https://preview.acluxuryaesthetics.com")
    assert cors.is_allowed_origin("https://acluxuryaesthetics.com", env=env)
    assert cors.is_allowed_origin("https://preview.acluxuryaesthetics.com", env=env)
    assert not cors.is_allowed_origin("https://otro-sitio.com", env=env)


def test_env_custom_domain_supported():
    env = SimpleNamespace(CUSTOM_DOMAIN="acluxuryaesthetics.com")
    assert cors.is_allowed_origin("https://acluxuryaesthetics.com", env=env)
    assert not cors.is_allowed_origin("https://otro-sitio.com", env=env)


def test_same_origin_with_request_url():
    req_url = "https://custom.test.com/api/availability"
    assert cors.is_allowed_origin("https://custom.test.com", request_url=req_url)
    assert not cors.is_allowed_origin("https://evil.com", request_url=req_url)


def test_admin_origin_strict_rules():
    req_url = "http://127.0.0.1:8791/api/admin/login"
    # Mismo origen exacto con request_url
    assert cors.is_admin_origin_allowed("http://127.0.0.1:8791", request_url=req_url)
    # Puerto diferente no configurado en env
    assert not cors.is_admin_origin_allowed("http://127.0.0.1:1", request_url=req_url)
    # Dominio de producción
    assert cors.is_admin_origin_allowed("https://ac-luxury-aesthetics.heisjuanda.workers.dev", request_url=req_url)
    # Dominio de env
    env = SimpleNamespace(CUSTOM_DOMAIN="acluxuryaesthetics.com")
    assert cors.is_admin_origin_allowed("https://acluxuryaesthetics.com", env=env, request_url=req_url)
    # Malicioso
    assert not cors.is_admin_origin_allowed("https://evil.example", env=env, request_url=req_url)
    assert not cors.is_admin_origin_allowed(None, env=env, request_url=req_url)


def test_get_cors_headers():
    allowed = "https://ac-luxury-aesthetics.heisjuanda.workers.dev"
    headers = cors.get_cors_headers(allowed)
    assert headers["access-control-allow-origin"] == allowed
    assert headers["access-control-allow-credentials"] == "true"
    assert headers["vary"] == "Origin"

    assert cors.get_cors_headers("https://evil.com") == {}

    # En rutas públicas se permite cualquier puerto de localhost, pero en /api/admin/* solo el mismo puerto
    assert cors.get_cors_headers("http://127.0.0.1:1", request_url="http://127.0.0.1:8791/api/availability") != {}
    assert cors.get_cors_headers("http://127.0.0.1:1", request_url="http://127.0.0.1:8791/api/admin/login") == {}
    assert cors.get_cors_headers("http://127.0.0.1:8791", request_url="http://127.0.0.1:8791/api/admin/login") != {}


def test_preflight_response_allowed_includes_base_and_cors_headers():
    from responses import BASE_HEADERS

    origin = "http://127.0.0.1:5173"
    resp = cors.preflight_response(origin, request_url="http://127.0.0.1:8791/api/bookings")
    assert resp.status == 204
    for key, val in BASE_HEADERS.items():
        assert resp.headers[key] == val
    assert resp.headers["access-control-allow-origin"] == origin
    assert resp.headers["access-control-allow-credentials"] == "true"
    assert "OPTIONS" in resp.headers["access-control-allow-methods"]
    assert "Content-Type" in resp.headers["access-control-allow-headers"]
    assert resp.headers["access-control-max-age"] == "86400"
    assert resp.headers["vary"] == "Origin"


def test_preflight_response_rejects_disallowed_and_mismatched_admin_origins():
    from responses import BASE_HEADERS

    # Origen malicioso en ruta pública
    bad_public = cors.preflight_response("https://evil.com", request_url="http://127.0.0.1:8791/api/bookings")
    assert bad_public.status == 403
    assert "access-control-allow-origin" not in bad_public.headers
    for key, val in BASE_HEADERS.items():
        assert bad_public.headers[key] == val

    # Puerto local distinto en ruta /api/admin/* debe ser rechazado en preflight
    bad_admin = cors.preflight_response("http://127.0.0.1:1", request_url="http://127.0.0.1:8791/api/admin/login")
    assert bad_admin.status == 403
    assert "access-control-allow-origin" not in bad_admin.headers

    # Mismo puerto exacto en ruta /api/admin/* es aceptado
    ok_admin = cors.preflight_response("http://127.0.0.1:8791", request_url="http://127.0.0.1:8791/api/admin/login")
    assert ok_admin.status == 204
    assert ok_admin.headers["access-control-allow-origin"] == "http://127.0.0.1:8791"
    for key, val in BASE_HEADERS.items():
        assert ok_admin.headers[key] == val


def test_apply_cors_with_dict_and_js_headers():
    from responses import Response

    # 1. Respuesta con diccionario de headers en ruta pública
    r_pub = cors.apply_cors(
        Response({"ok": True}, status=200),
        "http://127.0.0.1:1",
        request_url="http://127.0.0.1:8791/api/config",
    )
    assert r_pub.headers["access-control-allow-origin"] == "http://127.0.0.1:1"
    assert r_pub.headers["access-control-allow-credentials"] == "true"
    assert r_pub.headers["vary"] == "Origin"

    # 2. En ruta /api/admin/* no debe inyectar cabeceras CORS a un puerto local distinto
    r_admin_bad = cors.apply_cors(
        Response({"error": "Origen no permitido."}, status=403),
        "http://127.0.0.1:1",
        request_url="http://127.0.0.1:8791/api/admin/login",
    )
    assert "access-control-allow-origin" not in r_admin_bad.headers

    # 3. Simulación del objeto js_object.headers del runtime de Cloudflare Workers
    class FakeJsHeaders:
        def __init__(self):
            self.store = {}

        def set(self, k, v):
            self.store[k] = v

        def append(self, k, v):
            self.store[k] = f"{self.store[k]}, {v}" if k in self.store else v

    js_h = FakeJsHeaders()
    fake_worker_resp = SimpleNamespace(js_object=SimpleNamespace(headers=js_h))
    cors.apply_cors(
        fake_worker_resp,
        "http://127.0.0.1:8791",
        request_url="http://127.0.0.1:8791/api/admin/login",
    )
    assert js_h.store["access-control-allow-origin"] == "http://127.0.0.1:8791"
    assert js_h.store["access-control-allow-credentials"] == "true"
    assert js_h.store["vary"] == "Origin"

