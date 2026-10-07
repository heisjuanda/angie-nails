import secrets

import httpx

import config

# Ventana de reserva que usa el Worker durante las pruebas. Cada test que agenda necesita
# un día libre propio y dentro de la ventana de producción (21 días) no caben. El Worker
# la toma del entorno; aquí está la misma constante para que el pool de días coincida.
TEST_WINDOW_DAYS = 120


def random_phone() -> str:
    return "300 " + f"{secrets.randbelow(10_000_000):07d}"


def booking_payload(day, time="08:00", service="semipermanente", **overrides) -> dict:
    return {
        "service_id": service,
        "date": day.isoformat(),
        "time": time,
        "name": "Clienta de Prueba",
        "phone": random_phone(),
        "notes": "",
        "turnstile_token": "XXXX.DUMMY.TOKEN.XXXX",
        "form_token": form_token(),
        **overrides,
    }


def form_token() -> str:
    return secrets.token_urlsafe(16)


def seed_attempts(server, count: int, ip: str = "9.9.9.9", phone: str | None = None) -> None:
    valor = f"'{phone}'" if phone else "NULL"
    server.sql(
        "INSERT INTO booking_attempts (ip, phone) "
        f"SELECT '{ip}', {valor} FROM (WITH RECURSIVE seq(c) AS "
        f"(SELECT 1 UNION ALL SELECT c + 1 FROM seq WHERE c < {count}) SELECT c FROM seq)"
    )


def expire_booking(server, code: str, dias_atras: int = 1) -> None:
    server.sql(
        f"UPDATE bookings SET date = date(date('now', '-5 hours'), '-{dias_atras} days'), "
        f"created_at = datetime('now', '-{config.PENDING_TTL_HOURS + 1} hours') WHERE code = '{code}'"
    )


def slots_of(client: httpx.Client, day, service="semipermanente") -> dict[str, bool]:
    r = client.get("/api/availability", params={"service": service, "from": day.isoformat(), "days": 1})
    assert r.status_code == 200, r.text
    return {s["time"]: s["available"] for s in r.json()["days"][0]["slots"]}
