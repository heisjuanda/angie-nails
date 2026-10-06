# AC Luxury Aesthetics

Sitio web y agenda de citas a domicilio (uñas, cejas y pestañas) de Angélica Castrillón, en Cali.

- **Frontend:** HTML + CSS + JS sin frameworks ni build, en `public/`.
- **Backend:** Python Workers de Cloudflare (`src/`), solo para `/api/*`.
- **Base de datos:** Cloudflare D1 (SQLite), migraciones en `migrations/`.
- **Anti-spam:** Cloudflare Turnstile + topes por teléfono e IP. Si el navegador bloquea la verificación, la web lo dice y ofrece salida.
- **Confirmación:** enlace `wa.me` con el resumen de la cita hacia el WhatsApp de Angélica.
- **Aviso de cita nueva:** WhatsApp (CallMeBot) y/o email (Resend) al crear la reserva. Gratis, sin librerías: una llamada `fetch` por canal, disparada con `ctx.waitUntil` para no demorar la respuesta.
- **Panel:** `/admin` para que Angélica confirme, cancele y bloquee horarios.

**En producción:** https://ac-luxury-aesthetics.heisjuanda.workers.dev · panel en `/admin/`

## Requisitos

- [uv](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`)
- Node.js 20+

## Desarrollo local

```bash
npm install                    # instala wrangler
uv sync                        # instala workers-py y pytest
cp .dev.vars.example .dev.vars # claves de prueba de Turnstile
rm -rf .wrangler/state       # elimina la D1 local y sus datos
npm run db:migrate:local       # crea las tablas en la D1 local
npm run dev                    # http://127.0.0.1:8787  (panel: /admin/, clave en .dev.vars)
```

Ver las citas guardadas en local:

```bash
npx wrangler d1 execute ac-luxury-db --local --command "SELECT code, service_name, date, start_min, customer_name, status FROM bookings"
```

### Limpiar los datos locales

Para empezar de cero al probar a mano. **Con `wrangler dev` apagado** (Ctrl+C), porque la D1 local está en uso:

```bash
# Borra los datos pero conserva el esquema
npx wrangler d1 execute ac-luxury-db --local --command \
  "DELETE FROM bookings; DELETE FROM booking_attempts; DELETE FROM blocked_slots; DELETE FROM login_attempts; DELETE FROM mfa_attempts;"
```

Si prefieres empezar sin esquema, borra el estado completo y vuelve a aplicar las migraciones:

```bash
rm -rf .wrangler/state
npm run db:migrate:local
```

El esquema **no** lo borran los `DELETE`, así que no hay que volver a migrar en el caso normal. `booking_attempts` es
la que se llena sola con cada reserva: si la tabla crece mucho durante las pruebas, es la primera que hay que limpiar.

## Datos pendientes (valores X)

Todo lo que falta definir está en **`src/config.py`**, arriba del archivo:

| Constante | Qué es |
|---|---|
| `PRECIO_X` | Precio de cada servicio (COP). `None` muestra "$ X". Se puede poner un precio distinto por servicio en `SERVICES`. |
| `DURACION_X` | Duración de los servicios en minutos (hoy 90 para todos). |
| `DURACION_COMBO_X` / `DURACION_TRIPLE_X` | Duración de los combos de 2 y de 3 servicios. |
| `HORA_INICIO_X` / `HORA_FIN_X` | Horario laboral: define cuándo se pueden **iniciar** citas. Una cita puede terminar después del cierre. Para horarios distintos por día o almuerzo, editar `BUSINESS_HOURS`. |
| `COBERTURA_X` | Barrios que atiende. Vacío = cualquier barrio. |
| `RECARGO_DOMICILIO_X` | Recargo de domicilio en COP. |

El WhatsApp de Angélica está en `WHATSAPP` (`57` + celular, solo dígitos).

Otros ajustes de agenda en el mismo archivo: `TRAVEL_BUFFER_MIN` (traslado entre citas, 45 min), `SLOT_STEP_MIN`,
`MIN_NOTICE_HOURS`, `BOOKING_WINDOW_DAYS`, `PENDING_TTL_HOURS`.

`PENDING_TTL_HOURS` (12 h) es el plazo que tiene Angélica para responder, y solo aplica a **citas próximas**: una
pendiente para dentro de tres semanas no se libera por antigüedad de la reserva, porque el horario volvería al
calendario mientras la clienta sigue esperando respuesta y otra persona podría tomarlo (`db._active`). Superada la
cita, una pendiente sin confirmar ya no bloquea nada. El panel marca las vencidas como tales y se pueden cancelar a
mano si la clienta nunca contestó.

`BOOKING_WINDOW_DAYS` es el único que se puede sobreescribir desde el entorno
(`npx wrangler secret put BOOKING_WINDOW_DAYS`, o en `.dev.vars`), sin editar código.

Textos de "Sobre mí" y certificaciones: `public/index.html`. Fotos: ver `public/img/portafolio/LEEME.md`.

## Topes de la agenda

Tres reglas, en `config.py`:

| Regla | Valor | Qué previene |
|---|---|---|
| Citas activas por teléfono y fecha | 1 | agendar cuatro citas el mismo día, y llenar un día entero con un solo teléfono |
| Reservas creadas por teléfono / 24 h | 8 | crear y cancelar rápido, que no activa ninguna regla de estado |
| Reservas creadas por IP / 1 h | 20 | inundar desde una sola máquina |

**"Activa" y "creada" son distintas.** *Activa* ocupa un horario ahora mismo (pendiente no
vencida + confirmada, vía `db._active()`): es un estado y baja sola cuando la cita se vence,
se cancela o se completa. *Creada* cuenta cuántas veces se reservó en una ventana móvil: es un
ritmo y baja sola 24 h (o 1 h) después de la más antigua. La primera no ve el caso de crear y
cancelar rápido, que deja cero activas y aun así llena el panel de ruido.

El tope por teléfono es **1 por día y no 3 en total**, porque un día tiene 4 huecos: con 3 se
podía llenar el día entero desde un solo número. Y con 1, llenarlo exige cuatro teléfonos
distintos. Quien quiera varios servicios agenda un **combo**, que es justo para qué están.

El de IP va **holgado a propósito**: en Colombia hay CGNAT y un hogar comparte IP, así que un
tope de "1 por día" bloquearía a las familias. Un tope total de citas bloquearía a la clienta
que agenda para ella y su hija.

Son topes de velocidad, no muros: con 8/día, un script con un solo teléfono necesita ~10 días
para llenar la ventana. Y si el atacante usa varios teléfonos, ninguna regla de conteo lo
detiene. El `COUNT` y el `INSERT` tampoco son atómicos, así que el tope puede pasarse por uno
bajo concurrencia; `is_slot_bookable` sigue impidiendo el doble booking de un horario, que es el
daño que importa.

Los tres devuelven **429 con enlace a WhatsApp**, porque un tope tiene que sonar a ayuda: con
CGNAT un falso positivo por IP es fácil y nunca debe dejar el error sin salida.

## Combos

Una cita puede incluir varios servicios (uñas y cejas, por ejemplo). **Un combo es un servicio
más**: una entrada en `BUNDLES` con su propio id, nombre, precio y duración. No hay lista de
servicios dentro de la cita ni columna nueva en la base de datos — la reserva sigue siendo una
sola fila y todo lo demás (disponibilidad, bloqueo de horarios, panel, WhatsApp) funciona sin cambios.

```python
BUNDLES = [
    {"id": "combo-unas-cejas", "category": "combos", "name": "Combo Uñas + Cejas",
     "price": PRECIO_X, "duration": DURACION_COMBO_X},
]
```

- Los combos son su propia categoría (`combos`, la primera de `CATEGORIES`), así que la web los
  muestra en su propia tarjeta y en su propia lista, sin tocar `index.html` ni el JavaScript.
- **Solo se combinan servicios de categorías distintas**: uñas + cejas sí; semipermanente + uñas
  acrílicas no, porque son los dos sobre las mismas uñas. Cumplir eso es elegir bien qué combos
  ofrecer, no una regla del código.
- La duración del combo es **menor que la suma** de sus servicios: Angélica trabaja las cejas o
  las pestañas mientras seca las uñas. `DURACION_COMBO_X` (150) y `DURACION_TRIPLE_X` (210) son
  valores provisionales que hay que medir.
- Un combo ocupa más agenda que un servicio simple: 150 + 45 = 195 min, o sea **3 combos por día**
  en vez de las 4 citas simples que caben hoy.

## Cómo funciona la agenda

1. `GET /api/config` entrega servicios, precios, días abiertos y la ventana de reserva.
2. `GET /api/availability?service=<id>&from=YYYY-MM-DD&days=N` calcula la grilla de horarios por día.
   La grilla cubre todo el horario laboral (de apertura a cierre, de 30 en 30 min) sin importar la
   duración del servicio: el cierre es el último **inicio** posible y la cita puede terminar después
   de él. Cada cita ocupa `[inicio, fin + traslado)`; un horario se ofrece solo si su intervalo no
   choca con otra cita o bloqueo y respeta la anticipación mínima.
3. `POST /api/bookings` valida Turnstile y los datos, y guarda la cita como **pendiente** con un código (`AC-XXXXX`).
   La inserción es una única sentencia condicional (`INSERT … SELECT … WHERE NOT EXISTS`), por lo que dos personas que
   reservan el mismo horario a la vez no pueden quedar ambas registradas.
   El token de Turnstile es obligatorio **en el servidor**. Si el navegador no logra obtenerlo (adblocker, DNS bloqueado,
   red), `booking.js` lo detecta —script que no carga, script que llega sin `turnstile`, `render()` que falla o 12 s de
   silencio— y muestra un aviso con dos salidas: reintentar la verificación (hasta 2 veces) o escribir por WhatsApp con el
   resumen ya escrito. Ningún caso deja el botón de confirmar sin respuesta.
4. `POST /api/bookings` lleva una **llave de idempotencia** (`form_token`) que el navegador genera al abrir el
   formulario. *Antes* de validar Turnstile se busca si esa llave ya creó una cita; si la encontró se devuelve esa
   misma cita con 201 en vez de crear otra. Eso es lo que hace que una clienta a la que se le perdió la respuesta
   pueda reintentar y reciba su código, en lugar de ver "ese horario ya está reservado" mientras Angélica tiene una
   cita que nadie sabe que existe.

5. La clienta abre WhatsApp con el resumen y Angélica confirma. Una cita pendiente sigue reservando el horario hasta
   que su cita empiece, o hasta que Angélica la confirme o cancele.

## Aviso de cita nueva (WhatsApp / email)

Sin esto, Angélica solo se entera de una reserva si tiene el panel abierto (el
navegador hace *poll* cada 60 s) y la cita pendiente se libera a las 12 h. El
aviso cierra ese hueco: al guardar la reserva, el Worker le manda el resumen
(código, servicio, fecha, hora, clienta, barrio, dirección y notas) por
WhatsApp y/o email. Es **best-effort**: si un canal falla, la reserva igual
queda guardada y la clienta recibe su código.

Dos canales, ambos gratuitos y ambos con una sola llamada HTTP (`workers.fetch`,
cero librerías nuevas). Cada uno se activa solo si tiene sus variables:

| Canal | Servicio | Gratis | Variables |
|---|---|---|---|
| WhatsApp | [CallMeBot](https://www.callmebot.com) | ilimitado para uso personal | `CALLMEBOT_APIKEY` (obligatoria), `NOTIFY_PHONE` (opcional; por defecto `config.WHATSAPP`) |
| Email | [Resend](https://resend.com) | 3.000 correos/mes (100/día) | `RESEND_API_KEY` + `NOTIFY_EMAIL`, `RESEND_FROM` (opcional) |

**WhatsApp (CallMeBot):**

1. En el celular de Angélica, guarda el número del bot **+34 644 99 26 98** en contactos.
2. Envíale el mensaje `I allow callmebot to send me messages`.
3. El bot responde con una **apikey**. Actívala en el Worker:

```bash
npx wrangler secret put CALLMEBOT_APIKEY
```

El aviso llega al número que activó la apikey (por defecto el de
`config.WHATSAPP`; si el celular de Angélica es otro, ponlo en `NOTIFY_PHONE`).

**Email (Resend):** crea una cuenta y una clave en resend.com, y verifica el
dominio (tres registros DNS en el dashboard de Cloudflare, gratis) para enviar
desde tu propio dominio. Sin verificar, solo funciona con direcciones
`@resend.dev` (sirve para probar):

```bash
npx wrangler secret put RESEND_API_KEY
npx wrangler secret put NOTIFY_EMAIL     # p. ej. angie@tu-dominio.com
# RESEND_FROM por defecto es "AC Luxury Aesthetics <noreply@resend.dev>";
# con el dominio verificado, cámbialo a tu dirección real.
```

**Notas:**

- CallMeBot es un servicio de terceros cuya API gratuita es **para uso
  personal** (un aviso al celular de la dueña entra en ese caso). Si quieres la
  vía oficial, la **WhatsApp Cloud API** de Meta tiene 1.000 conversaciones
  gratis al mes, pero exige verificación de empresa y plantillas de mensaje:
  basta reescribir `send_whatsapp` en `src/notify.py`, el resto no cambia.
- El aviso sale con `waitUntil`: no demora la respuesta a la clienta y el
  runtime lo completa aunque ya haya respondido (tope de 30 s).
- Local: las variables van comentadas en `.dev.vars`. Sin ellas, el aviso es
  un no-op silencioso (así las pruebas no mandan mensajes reales).

### Probar en local

1. **Descomenta** las variables en `.dev.vars` (las líneas que empiezan con
   `#` son comentarios: el Worker no las ve).
2. **Reinicia** `npm run dev`: el servidor lee `.dev.vars` al arrancar, no
   en caliente.
3. Prueba cada canal de forma aislada (sin agendar una cita):

   ```bash
   uv run python scripts/probe_notify.py
   ```

   Muestra qué canales están activos, la petición y la **respuesta cruda** de
   cada API. Si algo falla, el mensaje de la API dice por qué (apikey
   inválida, número no activado, dominio sin verificar…).

4. Prueba de punta a punta: agenda una cita en http://127.0.0.1:8787 (la
   clave de prueba de Turnstile siempre pasa) y revisa el correo/WhatsApp.
   Los fallos del aviso se imprimen en la consola de `wrangler dev` con
   prefijo `notify:`.

**Trampas comunes:**

- **Resend gratis sin dominio verificado** solo puede enviar al correo de tu
  propia cuenta de Resend (para cualquier otro destinatario contesta 403).
  Para avisar a otro correo: verifica tu dominio en resend.com (tres
  registros DNS en el dashboard de Cloudflare) y ponlo en `RESEND_FROM`.
- **CallMeBot** ata la apikey al número que la activó: si ese número no es
  el de `config.WHATSAPP`, ponlo en `NOTIFY_PHONE`.
- Si editaste `.dev.vars` con el servidor corriendo, reinícialo.

## Panel de administración (`/admin/`)

- **Agenda:** citas por día con filtros por periodo y estado. Acciones: confirmar, cancelar (pide doble toque) y
  marcar como completada. Cada acción ofrece un enlace de WhatsApp **hacia la clienta** con el mensaje ya escrito.
  Una pendiente vencida se puede confirmar solo si su horario sigue libre.
- **Bloqueos:** día completo o franja horaria (vacaciones, compromisos). Avisa si ya hay citas en ese horario.
- **Seguridad:**
   - Contraseña única (`ADMIN_PASSWORD`) y cookie de sesión firmada con HMAC (`SESSION_SECRET`), `HttpOnly`,
     `Secure` y `SameSite=Strict`, válida 7 días.
   - El logout borra la sesión en D1 (`admin_sessions`): el token deja de valer al instante, no solo al
     expirar. Un token firmado sin fila en esa tabla no autentica nada.
   - Cambiar cualquiera de los dos secretos cierra todas las sesiones.
  - Las escrituras exigen `Origin` del mismo sitio.
  - Después de 5 intentos fallidos en 15 minutos, bloquea esa IP.
  - **Segundo factor (2FA) opcional** con TOTP: ver [Segundo factor](#segundo-factor-2fa-opcional).

Cambiar la contraseña de producción:

```bash
npx wrangler secret put ADMIN_PASSWORD
```

### Segundo factor (2FA, opcional)

El login del panel puede exigir un código TOTP (RFC 6238) de tu autenticador
(Google Authenticator, Authy, Microsoft Authenticator). **Sin `TOTP_SECRET`
el flujo actual de un solo factor no cambia** (así está local por defecto).

1. Genera el secreto y el QR (una sola vez):

   ```bash
   PYTHONPATH=src uv run python - <<'EOF'
   import mfa
   import qrcode

   s = mfa.random_secret()
   uri = mfa.provisioning_uri(s)
   print("Secreto (guárdalo):", s)
   print("URI:", uri)
   qr = qrcode.QRCode(border=2)
   qr.add_data(uri)
   qr.make(fit=True)
   qr.print_ascii(invert=True)  # quita invert=True si tu terminal es de fondo claro
   EOF
   ```

   Escanea el QR con tu app de autenticación (o añade la cuenta a
   mano con el secreto impreso). `qrcode` es dependencia de dev
   (`uv sync` la instala); el Worker no la usa.

2. Actívalo en producción:

   ```bash
   npx wrangler secret put TOTP_SECRET   # pega el secreto base32
   npm run db:migrate:remote && npm run deploy
   ```

El login pasa a dos pasos: contraseña → código de 6 dígitos. La contraseña
correcta emite un ticket de 5 minutos (`ac_admin_mfa`); solo con un código
válido se emite la sesión. Límite: 10 códigos errados en 15 minutos por IP.
Si pierdes el autenticador, rota el secreto con el mismo `wrangler secret put`
(genera uno nuevo con el comando del paso 1).

API: `POST /api/admin/login|mfa|logout`, `GET /api/admin/session`, `GET /api/admin/bookings?from&to&status`,
`PATCH /api/admin/bookings/<código>` `{status}`, `GET|POST /api/admin/blocks`, `DELETE /api/admin/blocks/<id>`.

## Pruebas

```bash
npm test             # unitarias + integración + navegador (≈3 min)
npm run test:unit    # solo lógica pura (< 1 s)
npm run test:smoke   # contra producción, sin crear datos
```

- **Unitarias** (`tests/unit`): horarios, traslado, validación, fechas, sesión HMAC, transiciones de estado y
  bloqueos, invariantes de la carta de servicios, y qué restricción única falló al insertar.
- **Integración** (`tests/integration`): levantan **dos Workers reales** con `wrangler dev`, cada uno con su propia
  D1 y sus propios secretos. Uno usa el Turnstile de prueba que aprueba y el otro el que rechaza. Cubren:
  - happy paths y errores 400/401/403/404/409/422/429;
  - 8 reservas simultáneas del mismo horario;
  - vencimiento de pendientes, simulado adelantando `created_at`;
  - CSRF, cookies falsificadas o vencidas y bloqueo por fuerza bruta.
- **Navegador** (`tests/e2e`): Microsoft Edge vía Playwright, en móvil y escritorio, con la CSP real del sitio.
  Emulan a la clienta (reserva, errores del formulario, horario tomado mientras llena los datos, adblocker que bloquea
  el script de Turnstile) y a Angélica (login, confirmar, cancelar, filtrar, bloquear un día y verificar que la clienta
  lo ve cerrado).
- **Humo** (`tests/smoke`): verifican el sitio publicado. Revisan cabeceras, Turnstile real (rechaza tokens falsos),
  login del panel con cookie `Secure` y la carga en navegador. No crean citas.

Cada test que agenda recibe un día libre propio del fixture `free_day`. Como en la ventana de producción (21 días) no
caben todos, los tests amplían la ventana a 60 días con `BOOKING_WINDOW_DAYS` en `.env.test`; el valor sale de
`TEST_WINDOW_DAYS` en `tests/helpers.py` para que el pool de días y el Worker coincidan. Si agregas un test que agenda
y el pool se agota, ese es el número que hay que subir.

Además, cada test usa **su propia IP y su propio teléfono** (`conftest._ip_para` y `helpers.random_phone`), porque los
topes de la agenda son acumulativos y 45 tests compartiendo `127.0.0.1` se toparían entre sí. No conviene "arreglarlo"
borrando la tabla entre tests: `Instance.sql()` lanza un subproceso `wrangler` y cuesta unos 3 s por test, lo que
multiplica por cinco el tiempo de la suite.

## Estructura

```
src/
  entry.py         Worker: router de /api/*
  public_api.py    configuración, disponibilidad y reservas (+ Turnstile)
  admin_api.py     panel: sesión, citas y bloqueos
  config.py        constantes del negocio (valores X)
  availability.py  cálculo de horarios (puro)
  validation.py    validación de datos (puro)
  messages.py      fechas en español y enlace de WhatsApp (puro)
  notify.py        aviso de cita nueva: WhatsApp (CallMeBot) y email (Resend)
  auth.py          sesión firmada, cookies, CSRF (puro)
  mfa.py           segundo factor TOTP (puro)
  admin_logic.py   transiciones de estado, bloqueos, mensajes a clientas (puro)
  db.py            toda la SQL de D1
  responses.py     respuestas JSON
migrations/        esquema D1
public/            sitio estático (index.html, admin/, css/, js/, img/)
tests/             unit/, integration/, e2e/, smoke/
assets/            logo original (no se publica)
```

## Cloudflare (producción)

| Recurso | Valor |
|---|---|
| Worker | `ac-luxury-aesthetics` → https://ac-luxury-aesthetics.heisjuanda.workers.dev |
| D1 | `ac-luxury-db` (`04d25f7f-7dea-46af-b0ec-4512392b8042`) |
| Turnstile | widget "AC Luxury Aesthetics" (modo *managed*, dominio del workers.dev) |
| Secretos | `TURNSTILE_SECRET`, `ADMIN_PASSWORD`, `SESSION_SECRET`, y opcionalmente `CALLMEBOT_APIKEY` / `RESEND_API_KEY` / `NOTIFY_EMAIL` para el aviso de citas (copia local en `.secrets.production.local`, fuera de git) |

Publicar cambios:

```bash
npm run db:migrate:remote   # solo si hay migraciones nuevas
npm run deploy
npm run test:smoke
```

Al pasar a dominio propio, agrega el dominio al widget de Turnstile. Se puede hacer en el dashboard o por la API
de `challenges/widgets`.

## Próximas fases

- Portafolio con fotos reales; subida de foto de referencia (R2).
- Recordatorios automáticos por WhatsApp Cloud API (cron diario).
- Dominio propio.
