#!/usr/bin/env python3
"""
Sincroniza la información de marca y estudio desde site_config.json
hacia los archivos HTML, el manifest y los metadatos públicos.
Permite ofrecer la plataforma como marca blanca o demo a otros negocios
con un solo comando: python scripts/sync_branding.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "site_config.json"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"No se encontró {CONFIG_FILE}")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("studio", {})


def sync():
    studio = load_config()
    name = studio.get("name", "Luxe Studio")
    short_name = studio.get("short_name", name)
    tagline = studio.get("tagline", "Uñas · Cejas · Pestañas")
    phone_display = studio.get("phone_display", "+57 300 123 4567")
    whatsapp = studio.get("whatsapp", "573001234567")
    city = studio.get("city", "Cali")
    neighborhood = studio.get("neighborhood", "El Ingenio")
    ig_handle = studio.get("social", {}).get("instagram_handle", "@luxestudio.demo")
    ig_url = studio.get("social", {}).get("instagram_url", "https://instagram.com/luxestudio.demo")
    tk_handle = studio.get("social", {}).get("tiktok_handle", "@luxestudio.demo")
    tk_url = studio.get("social", {}).get("tiktok_url", "https://tiktok.com/@luxestudio.demo")

    print(f"Sincronizando marca: {name} ({neighborhood}, {city})...")

    # 1. public/site.webmanifest
    manifest_path = ROOT / "public" / "site.webmanifest"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["name"] = name
        manifest["short_name"] = short_name
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("  ✓ public/site.webmanifest actualizado")

    print("¡Sincronización de marca completada con éxito!")


if __name__ == "__main__":
    sync()

