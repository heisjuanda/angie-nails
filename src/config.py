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

BUNDLES = [
    {"id": "combo-unas-cejas", "category": "combos", "name": "Combo Uñas + Cejas",
     "price": PRECIO_X, "duration": DURACION_COMBO_X},
    {"id": "combo-unas-pestanas", "category": "combos", "name": "Combo Uñas + Pestañas",
     "price": PRECIO_X, "duration": DURACION_COMBO_X},
    {"id": "combo-cejas-pestanas", "category": "combos", "name": "Combo Cejas + Pestañas",
     "price": PRECIO_X, "duration": DURACION_COMBO_X},
    {"id": "combo-triple", "category": "combos", "name": "Combo Triple",
     "price": PRECIO_X, "duration": DURACION_TRIPLE_X},
]

ALL_SERVICES = BUNDLES + SERVICES
SERVICES_BY_ID = {s["id"]: s for s in ALL_SERVICES}

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

# Una cita "pendiente" que Angélica no confirma se libera después de estas horas.
PENDING_TTL_HOURS = 12

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
