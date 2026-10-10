from datetime import timedelta, timezone

# Precio de referencia en COP. None = se muestra "$ X" en la web.
PRECIO_X = None

# Duración provisional de cada servicio, en minutos.
DURACION_X = 90
# Duración provisional de los combos, en minutos.
DURACION_COMBO_X = 150
DURACION_TRIPLE_X = 210

# Horario laboral provisional (hora de Colombia, formato 24 h).
HORA_INICIO_X = "08:00"
HORA_FIN_X = "18:00"

# Horario laboral provisional (hora de Colombia, formato 24 h).

WHATSAPP = "573245967079"

# Ubicación del estudio (Semi-privado: la dirección exacta se revela sólo tras reservar)
ESTUDIO_BARRIO = "La Flora, Cali"
ESTUDIO_REFERENCIA = "Al lado de la Parroquia Todos los Santos (Av. 3BN # 56-00)"
ESTUDIO_DIRECCION = "Calle 56 # 3AN-111"
ESTUDIO_MAPS_URL = "https://maps.google.com/?q=Calle+56+%233AN-111+La+Flora+Cali"
ESTUDIO_WAZE_URL = "https://waze.com/ul?ll=3.4735,-76.5165&navigate=yes"

# Servicios

CATEGORIES = [
    {"id": "combos", "name": "Combos"},
    {"id": "unas", "name": "Uñas"},
    {"id": "cejas", "name": "Cejas"},
    {"id": "pestanas", "name": "Pestañas"},
]

SERVICES = [
    {"id": "semipermanente", "category": "unas", "name": "Semipermanente", "price": PRECIO_X, "duration": DURACION_X},
    {"id": "acrilicas", "category": "unas", "name": "Uñas acrílicas", "price": PRECIO_X, "duration": DURACION_X},
    {"id": "polygel", "category": "unas", "name": "Polygel", "price": PRECIO_X, "duration": DURACION_X},
    {"id": "nail-art", "category": "unas", "name": "Nail art / diseño", "price": PRECIO_X, "duration": DURACION_X},
    {"id": "diseno-cejas", "category": "cejas", "name": "Diseño de cejas", "price": PRECIO_X, "duration": DURACION_X},
    {"id": "laminado-cejas", "category": "cejas", "name": "Laminado de cejas", "price": PRECIO_X, "duration": DURACION_X},
    {"id": "henna", "category": "cejas", "name": "Henna", "price": PRECIO_X, "duration": DURACION_X},
    {"id": "pelo-a-pelo", "category": "pestanas", "name": "Extensiones pelo a pelo", "price": PRECIO_X, "duration": DURACION_X},
    {"id": "volumen", "category": "pestanas", "name": "Volumen", "price": PRECIO_X, "duration": DURACION_X},
    {"id": "lifting", "category": "pestanas", "name": "Lifting de pestañas", "price": PRECIO_X, "duration": DURACION_X},
]

_SERVICES_BY_CATEGORY: dict[str, list[dict]] = {}
for _s in SERVICES:
    _SERVICES_BY_CATEGORY.setdefault(_s["category"], []).append(_s)


def compute_combo_metrics(bundle: dict, sub_services: list[dict]) -> tuple[int | None, int]:
    """Suma precios y duraciones de los sub-servicios elegidos y resta discount_cop y duration_saved_min."""
    saved_min = int(bundle.get("duration_saved_min") or 0)
    total_duration = sum(int(s["duration"]) for s in sub_services) - saved_min
    duration = max(30, total_duration)

    if not sub_services or any(s.get("price") is None for s in sub_services):
        price = None
    else:
        discount = int(bundle.get("discount_cop") or 0)
        price = max(0, sum(int(s["price"]) for s in sub_services) - discount)

    return price, duration


def _build_bundle(b: dict) -> dict:
    default_subs = []
    for cat in b["components"]:
        cat_items = _SERVICES_BY_CATEGORY.get(cat, [])
        if cat_items:
            default_subs.append(min(cat_items, key=lambda x: (x["duration"], x["price"] or 0)))
    price, duration = compute_combo_metrics(b, default_subs)
    return {**b, "price": price, "duration": duration}


BUNDLES = [
    _build_bundle({
        "id": "combo-unas-cejas",
        "category": "combos",
        "name": "Combo Uñas + Cejas",
        "components": ["unas", "cejas"],
        "discount_cop": 0,
        "duration_saved_min": 30,
    }),
    _build_bundle({
        "id": "combo-unas-pestanas",
        "category": "combos",
        "name": "Combo Uñas + Pestañas",
        "components": ["unas", "pestanas"],
        "discount_cop": 0,
        "duration_saved_min": 30,
    }),
    _build_bundle({
        "id": "combo-cejas-pestanas",
        "category": "combos",
        "name": "Combo Cejas + Pestañas",
        "components": ["cejas", "pestanas"],
        "discount_cop": 0,
        "duration_saved_min": 30,
    }),
    _build_bundle({
        "id": "combo-triple",
        "category": "combos",
        "name": "Combo Triple",
        "components": ["unas", "cejas", "pestanas"],
        "discount_cop": 0,
        "duration_saved_min": 60,
    }),
]

ALL_SERVICES = BUNDLES + SERVICES
SERVICES_BY_ID = {s["id"]: s for s in ALL_SERVICES}


def resolve_service(raw_service_id: str, combo_selections=None) -> dict | None:
    """Resuelve un servicio individual o un combo con sus sub-servicios seleccionados."""
    if not isinstance(raw_service_id, str) or not raw_service_id.strip():
        return None
    base_id, sep, suffix = raw_service_id.strip().partition(":")
    base = SERVICES_BY_ID.get(base_id)
    if not base:
        return None

    components = base.get("components")
    if not components:
        if sep or combo_selections:
            return None
        return {**base, "base_id": base["id"], "sub_services": []}

    parts: list[str] | None = None
    if sep:
        parts = [p.strip() for p in suffix.split("+") if p.strip()]
    elif combo_selections is not None:
        if isinstance(combo_selections, dict):
            parts = [str(combo_selections.get(cat) or "").strip() for cat in components]
        elif isinstance(combo_selections, (list, tuple)):
            parts = [str(x or "").strip() for x in combo_selections]
        else:
            return None

    if parts is None:
        return {**base, "base_id": base["id"], "sub_services": []}

    if len(parts) != len(components) or any(not p for p in parts):
        return None

    chosen: list[dict] = []
    for cat, sub_id in zip(components, parts):
        sub = SERVICES_BY_ID.get(sub_id)
        if not sub or sub.get("category") != cat or sub.get("components"):
            return None
        chosen.append(sub)

    price, duration = compute_combo_metrics(base, chosen)
    sub_ids = [s["id"] for s in chosen]
    sub_names = " + ".join(s["name"] for s in chosen)
    return {
        **base,
        "id": f"{base['id']}:{'+'.join(sub_ids)}",
        "base_id": base["id"],
        "name": f"{base['name']} ({sub_names})",
        "price": price,
        "duration": duration,
        "sub_services": sub_ids,
    }

TZ = timezone(timedelta(hours=-5), "America/Bogota")

# Franjas de trabajo por día de la semana (0 = lunes ... 6 = domingo).
BUSINESS_HOURS: dict[int, list[tuple[str, str]]] = {
    0: [(HORA_INICIO_X, HORA_FIN_X)],
    1: [(HORA_INICIO_X, HORA_FIN_X)],
    2: [(HORA_INICIO_X, HORA_FIN_X)],
    3: [(HORA_INICIO_X, HORA_FIN_X)],
    4: [(HORA_INICIO_X, HORA_FIN_X)],
    5: [(HORA_INICIO_X, HORA_FIN_X)],
    6: [],  # domingo: sin agenda
}

# Cada cuántos minutos se ofrece un horario de inicio.
SLOT_STEP_MIN = 30

# Anticipación mínima para reservar, en horas.
MIN_NOTICE_HOURS = 1

# Hasta cuántos días hacia adelante se puede reservar.
BOOKING_WINDOW_DAYS = 21

# Una cita "pendiente" que Angélica no confirma se libera después de estas horas
# (o apenas llegue la hora de inicio de la cita, lo que ocurra primero).
PENDING_TTL_HOURS = 24

# Citas y bloqueos con fecha de la cita más vieja que estos días se borran de
# forma permanente al crear una reserva (privacidad: ya no sirven en el panel,
# que consulta hasta 120 días). Borrado duro e irreversible.
RETENTION_DAYS = 120

# Una cita activa por teléfono y fecha. Un día tiene 4 huecos, así que con este tope
# llenarlo exige cuatro teléfonos distintos. También evita el absurdo de cuatro citas el
# mismo día; los combos son la salida para quien quiere varios servicios en una visita.
MAX_ACTIVE_PER_PHONE_DAY = 1

# Reservas creadas por teléfono en 24 h, con ventana móvil. Cubre el crear-y-cancelar
# rápido, que no activa ninguna de las reglas de estado.
MAX_PER_PHONE_DAY = 8

# Reservas creadas por IP en 1 h. Va holgado a propósito: en Colombia hay CGNAT y un hogar
# comparte IP. Frena al script, no a la familia.
MAX_PER_IP_HOUR = 20
