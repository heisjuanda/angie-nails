import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.sync_branding as sync_branding


def test_sync_branding_is_idempotent():
    config = sync_branding.load_config()
    sync_branding.sync()

    manifest_before = (ROOT / "public" / "site.webmanifest").read_text(encoding="utf-8")
    index_before = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
    faq_before = (ROOT / "public" / "preguntas-frecuentes" / "index.html").read_text(encoding="utf-8")
    cuidados_before = (ROOT / "public" / "cuidados" / "index.html").read_text(encoding="utf-8")
    admin_before = (ROOT / "public" / "admin" / "index.html").read_text(encoding="utf-8")
    notfound_before = (ROOT / "public" / "404.html").read_text(encoding="utf-8")

    # Ejecutar sync de nuevo
    sync_branding.sync()

    assert (ROOT / "public" / "site.webmanifest").read_text(encoding="utf-8") == manifest_before
    assert (ROOT / "public" / "index.html").read_text(encoding="utf-8") == index_before
    assert (ROOT / "public" / "preguntas-frecuentes" / "index.html").read_text(encoding="utf-8") == faq_before
    assert (ROOT / "public" / "cuidados" / "index.html").read_text(encoding="utf-8") == cuidados_before
    assert (ROOT / "public" / "admin" / "index.html").read_text(encoding="utf-8") == admin_before
    assert (ROOT / "public" / "404.html").read_text(encoding="utf-8") == notfound_before


def test_sync_branding_reflects_config_in_all_files():
    studio = sync_branding.load_config()
    short_name = studio.get("short_name", studio.get("name"))
    specialist_name = studio.get("specialist", {}).get("name")
    first_name = specialist_name.split()[0]

    # 1. Manifest
    manifest = json.loads((ROOT / "public" / "site.webmanifest").read_text(encoding="utf-8"))
    assert manifest["name"] == studio["name"]

    # 2. Index HTML
    index_html = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
    assert f"<title>{short_name}" in index_html
    assert f'data-brand-name>{short_name}</span>' in index_html
    assert f'data-specialist-name>{specialist_name}</span>' in index_html
    assert f'data-specialist-first>{first_name}</span>' in index_html

    # 3. FAQ HTML
    faq_html = (ROOT / "public" / "preguntas-frecuentes" / "index.html").read_text(encoding="utf-8")
    assert f"<title>Preguntas Frecuentes · {short_name}" in faq_html
    assert f'data-brand-name>{short_name}</span>' in faq_html

    # 4. Cuidados HTML
    cuidados_html = (ROOT / "public" / "cuidados" / "index.html").read_text(encoding="utf-8")
    assert f"<title>Guía de Cuidados Post-Cita · {short_name}" in cuidados_html
    assert f'data-brand-name>{short_name}</span>' in cuidados_html
    assert f'data-specialist-first>{first_name}</span>' in cuidados_html

    # 5. Admin HTML
    admin_html = (ROOT / "public" / "admin" / "index.html").read_text(encoding="utf-8")
    assert f"<title>Panel · {short_name}" in admin_html
    assert f'data-specialist-first>{first_name}</span>' in admin_html

    # 6. 404 HTML
    notfound_html = (ROOT / "public" / "404.html").read_text(encoding="utf-8")
    assert f"<title>Página no encontrada · {short_name}" in notfound_html


def test_sync_branding_with_custom_name_and_revert():
    orig_config = sync_branding.CONFIG_FILE.read_text(encoding="utf-8")
    try:
        custom_studio = {
            "name": "Studio Demo WhiteLabel",
            "short_name": "Studio Demo",
            "tagline": "Uñas & Pestañas",
            "brand_description": "Estudio boutique demo.",
            "phone_display": "+57 300 111 2233",
            "whatsapp": "573001112233",
            "city": "Medellín",
            "neighborhood": "El Poblado",
            "address": "Calle 10 # 40-50",
            "reference": "Frente al parque",
            "maps_url": "https://maps.google.com/?q=El+Poblado",
            "waze_url": "https://waze.com/ul?ll=6.2,-75.5",
            "social": {
                "instagram_handle": "@studiodemo",
                "instagram_url": "https://instagram.com/studiodemo",
                "tiktok_handle": "@studiodemo",
                "tiktok_url": "https://tiktok.com/@studiodemo",
            },
            "specialist": {
                "name": "Valentina Gómez",
                "title": "Master Artist",
                "bio": "Especialista en Medellín.",
                "quote": "Belleza con estilo.",
            },
            "booking": {
                "code_prefix": "SD-",
                "currency": "COP",
                "admin_mfa_issuer": "Studio Demo",
                "admin_mfa_account": "valen",
            },
        }

        # Ejecutar sincronización con datos de prueba
        sync_branding.sync_webmanifest(custom_studio)
        sync_branding.sync_index_html(custom_studio)
        sync_branding.sync_faq_html(custom_studio)
        sync_branding.sync_cuidados_html(custom_studio)
        sync_branding.sync_admin_html(custom_studio)
        sync_branding.sync_404_html(custom_studio)

        # Validar que los archivos reflejan el nuevo nombre
        index_text = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        assert "Studio Demo" in index_text
        assert "Valentina Gómez" in index_text
        assert "El Poblado" in index_text
        assert "Medellín" in index_text

        admin_text = (ROOT / "public" / "admin" / "index.html").read_text(encoding="utf-8")
        assert "Panel · Studio Demo" in admin_text
        assert "Valentina" in admin_text

        faq_text = (ROOT / "public" / "preguntas-frecuentes" / "index.html").read_text(encoding="utf-8")
        assert "Preguntas Frecuentes · Studio Demo Medellín" in faq_text
        assert "Valentina" in faq_text

    finally:
        # Restaurar la configuración original y re-sincronizar
        sync_branding.CONFIG_FILE.write_text(orig_config, encoding="utf-8")
        sync_branding.sync()
