"""Constantes del negocio.

Todo lo que aún no está definido por Angélica está marcado con X.
Cuando tengas los datos reales, solo cambia este archivo.
"""

from datetime import timedelta, timezone

# ---------------------------------------------------------------------------
# Valores pendientes (X)
# ---------------------------------------------------------------------------

# Precio de referencia en COP. None = se muestra "$ X" en la web.
PRECIO_X = None

# Duración provisional de cada servicio, en minutos.
DURACION_X = 90

# Horario laboral provisional (hora de Colombia, formato 24 h).
HORA_INICIO_X = "08:00"
HORA_FIN_X = "18:00"

# Barrios o comunas de Cali que atiende. Vacío = se acepta cualquier barrio.
COBERTURA_X: list[str] = []

# Recargo de domicilio en COP. None = no se muestra.
RECARGO_DOMICILIO_X = None

# ---------------------------------------------------------------------------
# Contacto
# ---------------------------------------------------------------------------

# WhatsApp de Angélica en formato internacional, solo dígitos (57 + celular).
WHATSAPP = "573245967079"

# ---------------------------------------------------------------------------
# Servicios
# ---------------------------------------------------------------------------

CATEGORIES = [
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

SERVICES_BY_ID = {s["id"]: s for s in SERVICES}

# ---------------------------------------------------------------------------
# Agenda
# ---------------------------------------------------------------------------

# Colombia es UTC-5 todo el año (sin horario de verano).
TZ = timezone(timedelta(hours=-5), "America/Bogota")

# Franjas de trabajo por día de la semana (0 = lunes ... 6 = domingo).
# Puede haber varias franjas por día, p. ej. para un descanso de almuerzo.
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

# Tiempo de desplazamiento reservado después de cada cita (es a domicilio).
TRAVEL_BUFFER_MIN = 45

# Anticipación mínima para reservar, en horas.
MIN_NOTICE_HOURS = 3

# Hasta cuántos días hacia adelante se puede reservar.
BOOKING_WINDOW_DAYS = 21

# Una cita "pendiente" que Angélica no confirma se libera después de estas horas.
PENDING_TTL_HOURS = 12
