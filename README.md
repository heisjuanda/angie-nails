# AC Luxury Aesthetics

Sitio web y sistema de agendamiento de citas para **AC Luxury Aesthetics** (uñas, cejas y pestañas).

## Stack tecnológico

- **Frontend:** HTML, CSS y JavaScript vanilla (`public/`).
- **Backend:** Cloudflare Python Workers (`src/`).
- **Base de datos:** Cloudflare D1 / SQLite (`migrations/`).
- **Seguridad y notificaciones:** Protección anti-abuso con Cloudflare Turnstile, autenticación con soporte para 2FA (TOTP) y alertas de nuevas reservas por correo (Resend) y/o WhatsApp.

## Requisitos

- [uv](https://docs.astral.sh/uv/)
- Node.js 20+

## Desarrollo local

```bash
npm install                    # instala wrangler y dependencias de desarrollo
uv sync                        # instala workers-py y dependencias de Python
cp .dev.vars.example .dev.vars # variables de entorno locales
npm run db:migrate:local       # aplica las migraciones en la base de datos D1 local
npm run dev                    # inicia el servidor en http://127.0.0.1:8787
```

Para reiniciar la base de datos local desde cero (con el servidor detenido):

```bash
rm -rf .wrangler/state
npm run db:migrate:local
```

## Configuración

### Identidad de marca y estudio (`site_config.json`)

Toda la información del negocio, identidad de marca, especialista, ubicación y canales de contacto está centralizada en `site_config.json`:

* **Estudio / Negocio:** `name`, `short_name`, `tagline`, `brand_description`.
* **Contacto y ubicación:** `whatsapp`, `phone_display`, `city`, `neighborhood`, `address`, `reference`, `maps_url`, `waze_url`.
* **Redes sociales:** `instagram_handle`, `instagram_url`, `tiktok_handle`, `tiktok_url`.
* **Especialista:** `name`, `title`, `bio`, `quote`.
* **Reservas y autenticación:** `code_prefix`, `currency`, `admin_mfa_issuer`, `admin_mfa_account`.

#### Sincronización automática (`rebrand`)

Para propagar cualquier cambio de `site_config.json` a todo el proyecto (archivos HTML estáticos, SEO, metadatos OpenGraph, Schema.org JSON-LD, PWA webmanifest y compilación de assets), ejecuta:

```bash
npm run rebrand
```

Este comando ejecuta `python3 scripts/sync_branding.py` seguido de `npm run build:assets`:
1. Actualiza `public/site.webmanifest` (PWA).
2. Actualiza `<title>`, `<meta description>`, OpenGraph y Schema.org en todas las páginas públicas (`index.html`, `preguntas-frecuentes/index.html`, `cuidados/index.html`, `admin/index.html` y `404.html`).
3. Actualiza encabezados, textos, menciones a la especialista, enlaces a redes sociales y llamadas a la acción de WhatsApp.
4. El backend (`src/config.py`, `src/notify.py`, `src/mfa.py`, `src/messages.py`) lee `site_config.json` automáticamente para correos, mensajes de WhatsApp y códigos 2FA.
5. El frontend (`public/js/main.js` y `public/js/booking.js`) hidrata los elementos dinámicos mediante atributos `data-brand-*` desde `/api/config`.

### Reglas y catálogo del negocio (`src/config.py`)

El catálogo de servicios, combos (`BUNDLES`), precios, duraciones, reglas de topes y horarios de atención (`BUSINESS_HOURS`) se configuran en `src/config.py`.

El contenido estático base se encuentra en `public/index.html` y las imágenes del portafolio en `public/img/portafolio/` (ver `public/img/portafolio/LEEME.md`).

### Variables de entorno y secretos

En desarrollo local se leen desde `.dev.vars` (ver `.dev.vars.example` para el detalle de cada variable). En producción se configuran mediante `npx wrangler secret put <NOMBRE>`:

| Variable | Uso |
|---|---|
| `TURNSTILE_SECRET` | Validación de Cloudflare Turnstile en el servidor |
| `ADMIN_PASSWORD` | Contraseña de acceso al panel de administración |
| `SESSION_SECRET` | Clave para firmar las sesiones del panel |
| `TOTP_SECRET` | *(Opcional)* Secreto Base32 para habilitar el segundo factor (2FA) |
| `RESEND_API_KEY` / `NOTIFY_EMAIL` / `RESEND_FROM` | *(Opcional)* Notificaciones de reservas por correo |
| `CALLMEBOT_APIKEY` / `NOTIFY_PHONE` | *(Opcional)* Notificaciones de reservas por WhatsApp |
| `ESTUDIO_DIRECCION` | *(Opcional)* Dirección exacta del estudio mostrada tras agendar |
| `ALLOWED_ORIGINS` | *(Opcional)* Orígenes adicionales permitidos para CORS |

Para probar los canales de notificación configurados en `.dev.vars` sin crear una reserva:

```bash
uv run python scripts/probe_notify.py
```

Para generar un nuevo secreto y código QR para 2FA (TOTP):

```bash
PYTHONPATH=src uv run python - <<'EOF'
import mfa, qrcode
s = mfa.random_secret()
print("Secreto:", s)
qr = qrcode.QRCode(border=2)
qr.add_data(mfa.provisioning_uri(s))
qr.make(fit=True)
qr.print_ascii(invert=True)
EOF
```

## Estructura del proyecto

```text
site_config.json   Configuración centralizada de marca, estudio, especialista y contacto
scripts/
  sync_branding.py Sincronizador de marca hacia HTMLs, manifest y metadatos SEO
  probe_notify.py  Prueba de canales de notificación (email / WhatsApp)
  run_tests.sh     Ejecutor de pruebas
src/
  entry.py         Router principal del Worker (/api/*)
  public_api.py    Endpoints públicos de configuración, disponibilidad y reservas
  admin_api.py     Endpoints del panel de administración
  config.py        Catálogo de servicios, horarios y parámetros del negocio
  availability.py  Cálculo de disponibilidad de horarios
  validation.py    Validación y normalización de datos de entrada
  messages.py      Formato de fechas y generación de mensajes
  notify.py        Envío de notificaciones (email / WhatsApp)
  auth.py          Gestión de sesiones, cookies y protección CSRF
  mfa.py           Autenticación de dos factores (TOTP)
  admin_logic.py   Reglas de negocio para gestión de citas y bloqueos
  db.py            Consultas y operaciones sobre Cloudflare D1
  responses.py     Utilidades para respuestas HTTP/JSON
migrations/        Esquema y migraciones SQL de D1
public/            Archivos estáticos del frontend
tests/             Suites de pruebas (unit, integration, e2e, smoke)
```

## Pruebas

```bash
npm test             # suite completa: unitarias, integración y e2e
npm run test:unit    # solo pruebas unitarias
npm run test:smoke   # verificación rápida de humo
```

## Despliegue

```bash
npm run db:migrate:remote   # aplica migraciones pendientes en D1 remoto
npm run deploy              # publica el Worker en Cloudflare
```

## Licencia

Software propietario — Todos los derechos reservados © 2026 **Juan David Moreno Alfonso**. Uso comercial autorizado únicamente para **AC Luxury Aesthetics**. Consulta el archivo [LICENSE](LICENSE) para más detalles.

