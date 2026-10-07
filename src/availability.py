from datetime import date, datetime, timedelta

import config


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def overlaps(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    """Intervalos semiabiertos [start, end)."""
    return start_a < end_b and start_b < end_a


def now_local() -> datetime:
    return datetime.now(config.TZ)


def booking_window(today: date) -> tuple[date, date]:
    return today, today + timedelta(days=config.BOOKING_WINDOW_DAYS - 1)


def day_slots(
    day: date,
    duration: int,
    busy: list[tuple[int, int]],
    now: datetime,
    hours: dict[int, list[tuple[str, str]]] | None = None,
    step: int = config.SLOT_STEP_MIN,
    min_notice_hours: int = config.MIN_NOTICE_HOURS,
) -> list[dict]:
    hours = config.BUSINESS_HOURS if hours is None else hours
    earliest = now + timedelta(hours=min_notice_hours)
    slots = []
    for open_hhmm, close_hhmm in hours.get(day.weekday(), []):
        open_min, close_min = to_minutes(open_hhmm), to_minutes(close_hhmm)
        start = open_min
        while start < close_min:
            slot_dt = datetime.combine(day, datetime.min.time(), config.TZ) + timedelta(minutes=start)
            taken = any(overlaps(start, start + duration, b0, b1) for b0, b1 in busy)
            slots.append({
                "time": to_hhmm(start),
                "available": not taken and slot_dt >= earliest,
            })
            start += step
    return slots


def is_slot_bookable(
    day: date,
    start: int,
    duration: int,
    busy: list[tuple[int, int]],
    now: datetime,
    **kwargs,
) -> bool:
    today = now.date()
    first, last = booking_window(today)
    if not (first <= day <= last):
        return False
    return any(
        s["available"] and to_minutes(s["time"]) == start
        for s in day_slots(day, duration, busy, now, **kwargs)
    )
