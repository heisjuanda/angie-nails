"""Utilidades compartidas por las pruebas de integración y e2e."""

import httpx


def booking_payload(day, time="08:00", service="semipermanente", **overrides) -> dict:
    return {
        "service_id": service,
        "date": day.isoformat(),
        "time": time,
        "name": "Clienta de Prueba",
        "phone": "300 123 4567",
        "neighborhood": "San Fernando",
        "address": "Carrera 34 # 5-20",
        "notes": "",
        "turnstile_token": "XXXX.DUMMY.TOKEN.XXXX",
        **overrides,
    }


def slots_of(client: httpx.Client, day, service="semipermanente") -> dict[str, bool]:
    r = client.get("/api/availability", params={"service": service, "from": day.isoformat(), "days": 1})
    assert r.status_code == 200, r.text
    return {s["time"]: s["available"] for s in r.json()["days"][0]["slots"]}
