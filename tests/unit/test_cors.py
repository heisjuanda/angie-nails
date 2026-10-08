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

