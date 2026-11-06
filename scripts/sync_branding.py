#!/usr/bin/env python3
"""
Sincroniza la información de marca y estudio desde site_config.json
hacia todos los archivos HTML públicos, el manifest, JSON-LD Schema.org
y los metadatos de SEO y OpenGraph.

Permite personalizar la plataforma o correr marcas blancas con un solo comando:
    python scripts/sync_branding.py
O mediante:
    npm run rebrand
"""
import json
import re
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "site_config.json"


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"No se encontró {CONFIG_FILE}")
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("studio", {})


def replace_data_text(html: str, attr_name: str, new_text: str) -> str:
    """Reemplaza el contenido de cualquier etiqueta con el atributo `attr_name`."""
    pattern = rf'(<([a-zA-Z0-9]+)\b[^>]*\b{re.escape(attr_name)}\b[^>]*>)([\s\S]*?)(</\2>)'
    return re.sub(pattern, rf'\g<1>{new_text}\g<4>', html)


def replace_tag_content(html: str, tag_name: str, new_content: str) -> str:
    """Reemplaza el contenido de una etiqueta de primer nivel (ej: <title>)."""
    pattern = rf'(<{tag_name}\b[^>]*>)([\s\S]*?)(</{tag_name}>)'
    return re.sub(pattern, rf'\g<1>{new_content}\g<3>', html)


def update_json_ld(html: str, updater_func) -> str:
    """Actualiza los bloques <script type="application/ld+json"> parseando y reformateando su JSON."""
    def replacer(match):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
            updated = updater_func(data)
            dumped = json.dumps(updated, indent=2, ensure_ascii=False)
            indented = "\n  " + dumped.replace("\n", "\n  ") + "\n  "
            return f'<script type="application/ld+json">{indented}</script>'
        except Exception as e:
            print(f"Advertencia: no se pudo actualizar JSON-LD: {e}")
            return match.group(0)

    return re.sub(r'<script type="application/ld\+json">([\s\S]*?)</script>', replacer, html)


def sync_webmanifest(studio: dict) -> None:
    manifest_path = ROOT / "public" / "site.webmanifest"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    full_name = studio.get("name", "AC Luxury Aesthetics")
    manifest["name"] = full_name
    manifest["short_name"] = studio.get("manifest_short_name") or studio.get("short_name", full_name[:12])
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("  ✓ public/site.webmanifest")


def sync_index_html(studio: dict) -> None:
    path = ROOT / "public" / "index.html"
    if not path.exists():
        return
    html = path.read_text(encoding="utf-8")

    full_name = studio.get("name", "AC Luxury Aesthetics")
    short_name = studio.get("short_name", full_name)
    tagline = studio.get("tagline", "Uñas · Cejas · Pestañas")
    brand_desc = studio.get("brand_description", "")
    whatsapp = studio.get("whatsapp", "573245967079")
    city = studio.get("city", "Cali")
    neighborhood = studio.get("neighborhood", "La Flora")
    address = studio.get("address", "")
    reference = studio.get("reference", "")
    maps_url = studio.get("maps_url", "")
    waze_url = studio.get("waze_url", "")

    social = studio.get("social", {})
    ig_handle = social.get("instagram_handle", "")
    ig_url = social.get("instagram_url", "")
    tk_handle = social.get("tiktok_handle", "")
    tk_url = social.get("tiktok_url", "")

    specialist = studio.get("specialist", {})
    specialist_name = specialist.get("name", "Angélica Castrillón")
    first_name = specialist_name.split()[0] if specialist_name else "Angélica"
    specialist_title = specialist.get("title", "")
    specialist_bio = specialist.get("bio", "")
    specialist_quote = specialist.get("quote", "")

    # 1. <title> y metatags SEO / OpenGraph
    html = replace_tag_content(html, "title", f"{short_name} · {tagline} en {city}")
    meta_desc = f"{tagline} con acabado de salón, en el estudio de {first_name} en {city}. Mira los trabajos de {specialist_name} y agenda tu cita en línea."
    html = re.sub(r'<meta name="description"[\s\S]*?>', f'<meta name="description"\n    content="{meta_desc}">', html)
    html = re.sub(r'<meta property="og:title" content="[^"]*">', f'<meta property="og:title" content="{short_name} · Tu momento de belleza, en el estudio">', html)
    html = re.sub(r'<meta property="og:description" content="[^"]*">', f'<meta property="og:description" content="{tagline} en el estudio de {first_name} en {city}. Agenda en línea.">', html)

    # 2. Schema.org JSON-LD
    def update_index_json_ld(data):
        graph = data.get("@graph", [])
        for item in graph:
            t = item.get("@type")
            types = t if isinstance(t, list) else [t]
            if "WebSite" in types:
                item["name"] = short_name
            elif "WebPage" in types:
                item["name"] = f"{short_name} · {tagline} en {city}"
            elif "BeautySalon" in types or "NailSalon" in types:
                item["name"] = short_name
                alt = [full_name]
                if ig_handle:
                    alt.append(ig_handle)
                item["alternateName"] = alt
                if brand_desc:
                    item["description"] = brand_desc
                item["telephone"] = f"+{whatsapp}" if not whatsapp.startswith("+") else whatsapp
                if "founder" in item and isinstance(item["founder"], dict):
                    item["founder"]["name"] = specialist_name
                    if specialist_title:
                        item["founder"]["jobTitle"] = specialist_title
                if "address" in item and isinstance(item["address"], dict):
                    if address:
                        item["address"]["streetAddress"] = address
                    if city:
                        item["address"]["addressLocality"] = city
                if "areaServed" in item and isinstance(item["areaServed"], list):
                    for area in item["areaServed"]:
                        if area.get("@type") == "City":
                            area["name"] = city
                        elif area.get("@type") == "AdministrativeArea":
                            area["name"] = f"{neighborhood}, {city}"
                same_as = [u for u in [ig_url, tk_url] if u]
                if same_as:
                    item["sameAs"] = same_as
        return data

    html = update_json_ld(html, update_index_json_ld)

    # 3. Encabezado / Barra de navegación
    html = re.sub(r'<a class="brand" href="#inicio" aria-label="[^"]*">', f'<a class="brand" href="#inicio" aria-label="{short_name}, inicio">', html)

    # 4. Hero
    html = re.sub(r'<p class="eyebrow">Estudio privado · [^<]*</p>', f'<p class="eyebrow">Estudio privado · {neighborhood}, Norte de {city}</p>', html)
    html = re.sub(r'<p class="lead">Uñas, cejas y pestañas con acabado de salón, en el estudio de [^<]*<span\s+class="hide-mobile">[^<]*</span></p>', f'<p class="lead">Uñas, cejas y pestañas con acabado de salón, en el estudio de {first_name} en {neighborhood}.<span\n              class="hide-mobile"> Mira los trabajos de {first_name}, elige tu servicio y agenda en minutos.</span></p>', html)
    html = re.sub(r'(<svg[^>]*>[\s\S]*?</svg>\s*)[^<]*?· Fácil parqueo', rf'\g<1>{neighborhood} · Fácil parqueo', html)

    # 5. Redes sociales en portafolio
    if ig_url:
        html = re.sub(r'(href=")[^"]*("\s+target="_blank"\s+rel="noopener"\s+data-social-instagram>)', rf'\g<1>{ig_url}\g<2>', html)
    if tk_url:
        html = re.sub(r'(href=")[^"]*("\s+target="_blank"\s+rel="noopener"\s+data-social-tiktok>)', rf'\g<1>{tk_url}\g<2>', html)
    if ig_handle:
        html = replace_data_text(html, "data-social-instagram-text", f"Más en Instagram · {ig_handle}")
    if tk_handle:
        html = replace_data_text(html, "data-social-tiktok-text", f"Videos en TikTok · {tk_handle}")

    # 6. Ubicación y cómo llegar
    html = re.sub(r'<h2 class="h2">Tu cita en <em>[^<]*</em></h2>', f'<h2 class="h2">Tu cita en <em>{neighborhood} · Norte de {city}</em></h2>', html)
    if reference:
        html = re.sub(r'Punto de referencia: [^<]*?· [^<\n]*', f'Punto de referencia: {reference}', html)
        html = re.sub(r'<h3 class="detail-title">Punto de Referencia</h3>\s*<p><strong>[^<]*</strong><br>', f'<h3 class="detail-title">Punto de Referencia</h3>\n                  <p><strong>{reference}</strong><br>', html)
    html = re.sub(r'<h3 class="detail-title">Sector y Barrio</h3>\s*<p><strong>Barrio [^<]*</strong>, Norte de [^<.]*\.<br>', f'<h3 class="detail-title">Sector y Barrio</h3>\n                  <p><strong>Barrio {neighborhood}</strong>, Norte de {city}.<br>', html)

    if maps_url:
        html = re.sub(r'(href=")[^"]*("\s+target="_blank"\s+rel="noopener"\s+data-maps-link>)', rf'\g<1>{maps_url}\g<2>', html)
    if waze_url:
        html = re.sub(r'(href=")[^"]*("\s+target="_blank"\s+rel="noopener"\s+data-waze-link>)', rf'\g<1>{waze_url}\g<2>', html)

    # 7. Sobre mí
    html = re.sub(r'<span class="ph-label">\[Retrato de [^\]]* trabajando\]</span>', f'<span class="ph-label">[Retrato de {first_name} trabajando]</span>', html)
    if specialist_bio:
        html = replace_data_text(html, "data-specialist-bio", specialist_bio)
    if specialist_quote:
        html = replace_data_text(html, "data-specialist-quote", f"“{specialist_quote}”")
    html = replace_data_text(html, "data-brand-full-name", full_name)

    # 8. Footer
    html = replace_data_text(html, "data-footer-tag", f"{tagline} · {neighborhood}, {city}")
    html = re.sub(r'href="https://wa\.me/[^"]*"(\s+data-whatsapp-link)', f'href="https://wa.me/{whatsapp}"\\g<1>', html)
    if ig_url:
        html = re.sub(r'(href=")[^"]*("\s+target="_blank"\s+rel="noopener"\s+data-social-instagram>Instagram</a>)', rf'\g<1>{ig_url}\g<2>', html)
    if tk_url:
        html = re.sub(r'(href=")[^"]*("\s+target="_blank"\s+rel="noopener"\s+data-social-tiktok>TikTok</a>)', rf'\g<1>{tk_url}\g<2>', html)

    # 9. Barra móvil inferior
    html = re.sub(r'<span class="mobile-sticky-title">Estudio en [^<]*</span>', f'<span class="mobile-sticky-title">Estudio en {neighborhood}</span>', html)
    html = re.sub(r'<span class="mobile-sticky-sub">Norte de [^<]* · Cita previa</span>', f'<span class="mobile-sticky-sub">Norte de {city} · Cita previa</span>', html)

    # 10. Reemplazos universales mediante data-*
    html = replace_data_text(html, "data-brand-name", short_name)
    html = replace_data_text(html, "data-brand-tag", tagline)
    html = replace_data_text(html, "data-specialist-name", specialist_name)
    html = replace_data_text(html, "data-specialist-first", first_name)
    html = replace_data_text(html, "data-studio-neighborhood", neighborhood)
    html = replace_data_text(html, "data-studio-city", city)

    path.write_text(html, encoding="utf-8")
    print("  ✓ public/index.html")


def sync_faq_html(studio: dict) -> None:
    path = ROOT / "public" / "preguntas-frecuentes" / "index.html"
    if not path.exists():
        return
    html = path.read_text(encoding="utf-8")

    full_name = studio.get("name", "AC Luxury Aesthetics")
    short_name = studio.get("short_name", full_name)
    tagline = studio.get("tagline", "Uñas · Cejas · Pestañas")
    phone_display = studio.get("phone_display", "+57 324 596 7079")
    whatsapp = studio.get("whatsapp", "573245967079")
    city = studio.get("city", "Cali")
    neighborhood = studio.get("neighborhood", "La Flora")

    social = studio.get("social", {})
    ig_url = social.get("instagram_url", "")
    tk_url = social.get("tiktok_url", "")

    specialist = studio.get("specialist", {})
    specialist_name = specialist.get("name", "Angélica Castrillón")
    first_name = specialist_name.split()[0] if specialist_name else "Angélica"

    # 1. <title> y metatags SEO / OpenGraph
    html = replace_tag_content(html, "title", f"Preguntas Frecuentes · {short_name} {city}")
    meta_desc = f"Respuestas a tus dudas sobre uñas acrílicas, semipermanente, polygel, lifting de pestañas, cejas, políticas de abono y cuidados en {short_name} {city}."
    html = re.sub(r'<meta name="description"[\s\S]*?>', f'<meta name="description"\n    content="{meta_desc}">', html)
    html = re.sub(r'<meta property="og:title" content="[^"]*">', f'<meta property="og:title" content="Preguntas Frecuentes · {short_name} {city}">', html)
    html = re.sub(r'<meta property="og:description"[\s\S]*?>', f'<meta property="og:description"\n    content="Resuelve tus dudas sobre reservas, técnicas de uñas, lifting de pestañas, cejas y protocolos de atención en nuestro estudio privado en {neighborhood}, {city}.">', html)

    # 2. Schema.org JSON-LD
    def update_faq_json_ld(data):
        graph = data.get("@graph", [])
        for item in graph:
            t = item.get("@type")
            if t == "FAQPage":
                if "isPartOf" in item and isinstance(item["isPartOf"], dict):
                    item["isPartOf"]["name"] = f"Preguntas Frecuentes · {short_name} {city}"
                item["description"] = f"Respuestas a dudas comunes sobre técnicas de uñas, lifting, cejas, políticas de reserva y cuidados en el estudio privado de {specialist_name} en {city}."
                if "author" in item and isinstance(item["author"], dict):
                    item["author"]["name"] = specialist_name
                if "publisher" in item and isinstance(item["publisher"], dict):
                    item["publisher"]["name"] = short_name
                # En la primera pregunta sobre agendamiento
                entities = item.get("mainEntity", [])
                if entities and isinstance(entities, list):
                    q1 = entities[0]
                    ans = q1.get("acceptedAnswer", {})
                    ans_text = ans.get("text", "")
                    ans["text"] = re.sub(r'WhatsApp oficial \([^)]+\)', f'WhatsApp oficial ({phone_display})', ans_text)
        return data

    html = update_json_ld(html, update_faq_json_ld)

    # 3. Encabezado / Marca
    html = re.sub(r'<a class="brand" href="/" aria-label="[^"]*">', f'<a class="brand" href="/" aria-label="{short_name}, inicio">', html)

    # 4. Hero text
    html = re.sub(r'en nuestro estudio privado en [^<.]*, [^<.]*\.</p>', f'en nuestro estudio privado en {neighborhood}, {city}.</p>', html)

    # 5. Enlace WhatsApp en pregunta 1
    html = re.sub(
        r'<a href="https://wa\.me/\d+" target="_blank" rel="noopener">\+?[^<]*</a>',
        f'<a href="https://wa.me/{whatsapp}" target="_blank" rel="noopener">{phone_display}</a>',
        html,
    )

    # 6. Tarjeta WhatsApp de escape
    encoded_wa = quote_plus(f"Hola {first_name}, tengo una duda sobre los servicios de {short_name}")
    html = re.sub(
        r'href="https://wa\.me/\d+\?text=[^"]*"\s+target="_blank"\s+rel="noopener"\s+data-faq-whatsapp-link',
        f'href="https://wa.me/{whatsapp}?text={encoded_wa}" target="_blank" rel="noopener" data-faq-whatsapp-link',
        html,
    )

    # 7. Footer
    html = replace_data_text(html, "data-footer-tag", f"{tagline} · {neighborhood}, {city}")
    html = re.sub(r'href="https://wa\.me/[^"]*"(\s+target="_blank"\s+rel="noopener"\s+data-whatsapp-link>)', f'href="https://wa.me/{whatsapp}"\\g<1>', html)
    if ig_url:
        html = re.sub(r'(href=")[^"]*("\s+target="_blank"\s+rel="noopener"\s+data-social-instagram>Instagram</a>)', rf'\g<1>{ig_url}\g<2>', html)
    if tk_url:
        html = re.sub(r'(href=")[^"]*("\s+target="_blank"\s+rel="noopener"\s+data-social-tiktok>TikTok</a>)', rf'\g<1>{tk_url}\g<2>', html)

    # 8. Reemplazos universales mediante data-*
    html = replace_data_text(html, "data-brand-name", short_name)
    html = replace_data_text(html, "data-brand-tag", tagline)
    html = replace_data_text(html, "data-specialist-name", specialist_name)
    html = replace_data_text(html, "data-specialist-first", first_name)

    path.write_text(html, encoding="utf-8")
    print("  ✓ public/preguntas-frecuentes/index.html")


def sync_cuidados_html(studio: dict) -> None:
    path = ROOT / "public" / "cuidados" / "index.html"
    if not path.exists():
        return
    html = path.read_text(encoding="utf-8")

    full_name = studio.get("name", "AC Luxury Aesthetics")
    short_name = studio.get("short_name", full_name)
    tagline = studio.get("tagline", "Uñas · Cejas · Pestañas")
    whatsapp = studio.get("whatsapp", "573245967079")
    city = studio.get("city", "Cali")
    neighborhood = studio.get("neighborhood", "La Flora")

    social = studio.get("social", {})
    ig_url = social.get("instagram_url", "")
    tk_url = social.get("tiktok_url", "")

    specialist = studio.get("specialist", {})
    specialist_name = specialist.get("name", "Angélica Castrillón")
    first_name = specialist_name.split()[0] if specialist_name else "Angélica"

    # 1. <title> y metatags SEO / OpenGraph
    html = replace_tag_content(html, "title", f"Guía de Cuidados Post-Cita · {short_name} {city}")
    meta_desc = f"Cómo cuidar tu mirada y tus uñas: consejos de oro de {specialist_name}. Protocolo aftercare boutique para lifting de pestañas, cejas y uñas en {city}."
    html = re.sub(r'<meta name="description"[\s\S]*?>', f'<meta name="description"\n    content="{meta_desc}">', html)
    html = re.sub(r'<meta property="og:title" content="[^"]*">', f'<meta property="og:title" content="Guía de Cuidados Post-Cita · {short_name}">', html)
    html = re.sub(r'<meta property="og:description"[\s\S]*?>', f'<meta property="og:description"\n    content="Consejos de oro para cuidar tus uñas, cejas y pestañas después de tu cita en {short_name} {city}.">', html)

    # 2. Schema.org JSON-LD
    def update_cuidados_json_ld(data):
        graph = data.get("@graph", [])
        for item in graph:
            t = item.get("@type")
            if t == "Article":
                if "isPartOf" in item and isinstance(item["isPartOf"], dict):
                    item["isPartOf"]["name"] = f"Guía de Cuidados Post-Cita · {short_name} {city}"
                item["description"] = f"Protocolo aftercare boutique de {specialist_name} para prolongar la belleza, salud y duración de lifting de pestañas, cejas y manicura semipermanente."
                if "author" in item and isinstance(item["author"], dict):
                    item["author"]["name"] = specialist_name
                if "publisher" in item and isinstance(item["publisher"], dict):
                    item["publisher"]["name"] = short_name
        return data

    html = update_json_ld(html, update_cuidados_json_ld)

    # 3. Encabezado / Marca
    html = re.sub(r'<a class="brand" href="/" aria-label="[^"]*">', f'<a class="brand" href="/" aria-label="{short_name}, inicio">', html)

    # 4. Hero lead
    html = re.sub(r'<p class="lead">Consejos de oro de [^<]* para prolongar la belleza', f'<p class="lead">Consejos de oro de {specialist_name} para prolongar la belleza', html)

    # 5. Footer
    html = replace_data_text(html, "data-footer-tag", f"{tagline} · {neighborhood}, {city}")
    html = re.sub(r'href="https://wa\.me/[^"]*"(\s+target="_blank"\s+rel="noopener"\s+data-whatsapp-link>)', f'href="https://wa.me/{whatsapp}"\\g<1>', html)
    if ig_url:
        html = re.sub(r'(href=")[^"]*("\s+target="_blank"\s+rel="noopener"\s+data-social-instagram>Instagram</a>)', rf'\g<1>{ig_url}\g<2>', html)
    if tk_url:
        html = re.sub(r'(href=")[^"]*("\s+target="_blank"\s+rel="noopener"\s+data-social-tiktok>TikTok</a>)', rf'\g<1>{tk_url}\g<2>', html)

    # 6. Reemplazos universales mediante data-*
    html = replace_data_text(html, "data-brand-name", short_name)
    html = replace_data_text(html, "data-brand-tag", tagline)
    html = replace_data_text(html, "data-specialist-name", specialist_name)
    html = replace_data_text(html, "data-specialist-first", first_name)
    html = replace_data_text(html, "data-studio-neighborhood", neighborhood)
    html = replace_data_text(html, "data-studio-city", city)

    path.write_text(html, encoding="utf-8")
    print("  ✓ public/cuidados/index.html")


def sync_admin_html(studio: dict) -> None:
    path = ROOT / "public" / "admin" / "index.html"
    if not path.exists():
        return
    html = path.read_text(encoding="utf-8")

    full_name = studio.get("name", "AC Luxury Aesthetics")
    short_name = studio.get("short_name", full_name)
    specialist_name = studio.get("specialist", {}).get("name", "Angélica Castrillón")
    first_name = specialist_name.split()[0] if specialist_name else "Angélica"

    html = replace_tag_content(html, "title", f"Panel · {short_name}")
    html = replace_data_text(html, "data-specialist-first", first_name)
    html = replace_data_text(html, "data-brand-name", short_name)

    path.write_text(html, encoding="utf-8")
    print("  ✓ public/admin/index.html")


def sync_404_html(studio: dict) -> None:
    path = ROOT / "public" / "404.html"
    if not path.exists():
        return
    html = path.read_text(encoding="utf-8")

    full_name = studio.get("name", "AC Luxury Aesthetics")
    short_name = studio.get("short_name", full_name)

    html = replace_tag_content(html, "title", f"Página no encontrada · {short_name}")

    path.write_text(html, encoding="utf-8")
    print("  ✓ public/404.html")


def sync() -> None:
    studio = load_config()
    name = studio.get("name", "AC Luxury Aesthetics")
    short_name = studio.get("short_name", name)
    city = studio.get("city", "Cali")
    neighborhood = studio.get("neighborhood", "La Flora")

    print(f"Sincronizando marca: {name} / {short_name} ({neighborhood}, {city})...")

    sync_webmanifest(studio)
    sync_index_html(studio)
    sync_faq_html(studio)
    sync_cuidados_html(studio)
    sync_admin_html(studio)
    sync_404_html(studio)

    print("¡Sincronización de marca completada con éxito!")


if __name__ == "__main__":
    sync()
