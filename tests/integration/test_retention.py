from datetime import date, timedelta

import pytest

import config
from helpers import booking_payload

pytestmark = pytest.mark.integration


def test_purge_removes_only_rows_older_than_retention(server, api, free_day):
    old = (date.today() - timedelta(days=config.RETENTION_DAYS + 1)).isoformat()
    recent = (date.today() + timedelta(days=2)).isoformat()
    server.sql(
        "INSERT INTO bookings (code, service_id, service_name, category, price, duration_min, "
        "date, start_min, end_min, busy_until_min, customer_name, phone, neighborhood, address, "
        "notes, status) VALUES "
        f"('AC-OLD01', 'semipermanente', 'Semipermanente', 'unas', 1000, 90, '{old}', 480, 570, 615, 'Vieja', '573000000001', 'Barrio', 'Dir', '', 'completed'),"
        f"('AC-OLD02', 'semipermanente', 'Semipermanente', 'unas', 1000, 90, '{old}', 600, 690, 735, 'Pendiente vieja', '573000000003', 'Barrio', 'Dir', '', 'pending'),"
        f"('AC-KEEP', 'semipermanente', 'Semipermanente', 'unas', 1000, 90, '{recent}', 1380, 1470, 1515, 'Nueva', '573000000002', 'Barrio', 'Dir', '', 'pending')"
    )
    server.sql(
        "INSERT INTO blocked_slots (date, start_min, end_min, reason) VALUES "
        f"('{old}', 0, 1440, 'viejo'), ('{recent}', 0, 1440, 'nuevo')"
    )
    r = api.post("/api/bookings", json=booking_payload(free_day, "08:00"))
    assert r.status_code == 201, r.text
    left = server.sql("SELECT code FROM bookings WHERE code IN ('AC-OLD01', 'AC-OLD02', 'AC-KEEP')")
    assert [row["code"] for row in left] == ["AC-KEEP"]
    blocks = server.sql(f"SELECT date FROM blocked_slots WHERE date IN ('{old}', '{recent}')")
    assert [row["date"] for row in blocks] == [recent]
