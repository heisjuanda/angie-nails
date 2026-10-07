from datetime import date, datetime

import config
from availability import day_slots, is_slot_bookable, to_hhmm, to_minutes

HOURS = {d: [("08:00", "12:00")] for d in range(6)} | {6: []}
MONDAY = date(2026, 10, 5)
SUNDAY = date(2026, 10, 4)
NOW = datetime(2026, 10, 2, 10, 0, tzinfo=config.TZ)


def slots(day=MONDAY, duration=60, busy=(), now=NOW, **kw):
    kw.setdefault("hours", HOURS)
    kw.setdefault("step", 30)
    kw.setdefault("min_notice_hours", 3)
    return day_slots(day, duration, list(busy), now, **kw)


def available(result):
    return [s["time"] for s in result if s["available"]]


def test_minutes_roundtrip():
    assert to_minutes("13:30") == 810
    assert to_hhmm(810) == "13:30"


def test_grid_covers_the_whole_workday():
    assert [s["time"] for s in slots()] == [
        "08:00", "08:30", "09:00", "09:30", "10:00", "10:30", "11:00", "11:30",
    ]


def test_sunday_closed():
    assert slots(day=SUNDAY) == []


def test_existing_booking_blocks_its_own_duration():
    # Ocupado 09:00–10:30; sin traslado, el hueco vuelve a abrir a las 10:30.
    result = available(slots(busy=[(540, 630)]))
    assert result == ["08:00", "10:30", "11:00", "11:30"]


def test_back_to_back_is_allowed():
    assert "10:30" in available(slots(busy=[(540, 630)]))


def test_min_notice_hides_near_slots_today():
    today = NOW.date()
    hours = {today.weekday(): [("08:00", "18:00")]}
    result = available(slots(day=today, hours=hours))
    assert result[0] == "13:00"


def test_is_slot_bookable_checks_window_and_grid():
    assert is_slot_bookable(MONDAY, to_minutes("08:00"), 60, [], NOW, hours=HOURS)
    assert not is_slot_bookable(MONDAY, to_minutes("08:15"), 60, [], NOW, hours=HOURS)  # fuera de la grilla
    assert not is_slot_bookable(date(2026, 10, 1), to_minutes("08:00"), 60, [], NOW, hours=HOURS)  # pasado
    far = date(2026, 12, 31)
    assert not is_slot_bookable(far, to_minutes("08:00"), 60, [], NOW, hours=HOURS)  # fuera de la ventana


def test_long_service_offers_slots_until_closing():
    hours = {MONDAY.weekday(): [("08:00", "18:00")]}
    result = slots(duration=210, hours=hours)
    assert [s["time"] for s in result][-1] == "17:30"
    assert all(s["available"] for s in result)


def test_booking_at_14_blocks_the_afternoon():
    hours = {MONDAY.weekday(): [("08:00", "18:00")]}
    busy = [(to_minutes("14:00"), to_minutes("14:00") + 210)]
    result = available(slots(duration=210, busy=busy, hours=hours))
    assert "10:30" in result           # último inicio de la mañana
    assert "11:00" not in result       # ya choca con la cita de 14:00
    for t in ("14:00", "15:00", "16:00", "17:00"):
        assert t not in result
    assert "17:30" in result           # back-to-back tras la cita
