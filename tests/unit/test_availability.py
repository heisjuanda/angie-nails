from datetime import date, datetime

import config
from availability import day_slots, is_slot_bookable, to_hhmm, to_minutes

HOURS = {d: [("08:00", "12:00")] for d in range(6)} | {6: []}
MONDAY = date(2026, 10, 5)
SUNDAY = date(2026, 10, 4)
# "Ahora" = viernes 2 oct 2026, 10:00 en Colombia.
NOW = datetime(2026, 10, 2, 10, 0, tzinfo=config.TZ)


def slots(day=MONDAY, duration=60, busy=(), now=NOW, **kw):
    kw.setdefault("hours", HOURS)
    kw.setdefault("step", 30)
    kw.setdefault("buffer", 30)
    kw.setdefault("min_notice_hours", 3)
    return day_slots(day, duration, list(busy), now, **kw)


def available(result):
    return [s["time"] for s in result if s["available"]]


def test_minutes_roundtrip():
    assert to_minutes("13:30") == 810
    assert to_hhmm(810) == "13:30"


def test_grid_ends_when_service_no_longer_fits():
    # Servicio de 60 min en franja 08:00-12:00 → último inicio 11:00.
    assert [s["time"] for s in slots()] == ["08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00"]


def test_sunday_closed():
    assert slots(day=SUNDAY) == []


def test_existing_booking_blocks_overlap_and_travel_time():
    # Cita existente 09:00-10:00 + 30 min de traslado → ocupado [540, 630).
    result = available(slots(busy=[(540, 630)]))
    # 08:00 → termina 09:00 + traslado 09:30 → choca. 08:30 también.
    # Nada que empiece antes de 10:30 sirve.
    assert result == ["10:30", "11:00"]


def test_back_to_back_respects_buffer_exactly():
    # Ocupado hasta 10:30 exacto: 10:30 debe quedar libre (intervalos semiabiertos).
    assert "10:30" in available(slots(busy=[(540, 630)]))


def test_min_notice_hides_near_slots_today():
    today = NOW.date()
    hours = {today.weekday(): [("08:00", "18:00")]}
    result = available(slots(day=today, hours=hours))
    # Ahora 10:00 + 3 h de anticipación → primer horario 13:00.
    assert result[0] == "13:00"


def test_is_slot_bookable_checks_window_and_grid():
    assert is_slot_bookable(MONDAY, to_minutes("08:00"), 60, [], NOW, hours=HOURS)
    assert not is_slot_bookable(MONDAY, to_minutes("08:15"), 60, [], NOW, hours=HOURS)  # fuera de la grilla
    assert not is_slot_bookable(date(2026, 10, 1), to_minutes("08:00"), 60, [], NOW, hours=HOURS)  # pasado
    far = date(2026, 12, 31)
    assert not is_slot_bookable(far, to_minutes("08:00"), 60, [], NOW, hours=HOURS)  # fuera de la ventana
