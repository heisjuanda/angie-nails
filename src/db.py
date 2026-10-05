import secrets
from datetime import date

import auth
import config


def _active(alias: str = "") -> str:
    """Una cita bloquea la agenda si está confirmada, o pendiente y aún no vence."""
    p = f"{alias}." if alias else ""
    return (
        f"({p}status = 'confirmed' OR ({p}status = 'pending' "
        f"AND {p}created_at > datetime('now', '-{int(config.PENDING_TTL_HOURS)} hours')))"
    )


_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_code() -> str:
    return "AC-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(5))


#  público

async def busy_intervals(db, first: date, last: date) -> dict[str, list[tuple[int, int]]]:
    res = await db.prepare(
        f"""
        SELECT date, start_min AS s, busy_until_min AS e FROM bookings
         WHERE date BETWEEN ?1 AND ?2 AND {_active()}
        UNION ALL
        SELECT date, start_min AS s, end_min AS e FROM blocked_slots
         WHERE date BETWEEN ?1 AND ?2
        """
    ).bind(first.isoformat(), last.isoformat()).all()
    busy: dict[str, list[tuple[int, int]]] = {}
    for row in res.results:
        busy.setdefault(row["date"], []).append((int(row["s"]), int(row["e"])))
    return busy


async def insert_booking_if_free(db, b: dict) -> bool:
    res = await db.prepare(
        f"""
        INSERT INTO bookings (
            code, service_id, service_name, category, price, duration_min,
            date, start_min, end_min, busy_until_min,
            customer_name, phone, neighborhood, address, notes
        )
        SELECT ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15
        WHERE NOT EXISTS (
            SELECT 1 FROM bookings
             WHERE date = ?7 AND start_min < ?10 AND busy_until_min > ?8 AND {_active()}
        )
        AND NOT EXISTS (
            SELECT 1 FROM blocked_slots
             WHERE date = ?7 AND start_min < ?10 AND end_min > ?8
        )
        """
    ).bind(
        b["code"], b["service_id"], b["service_name"], b["category"], b["price"], b["duration"],
        b["date"].isoformat(), b["start_min"], b["end_min"], b["busy_until_min"],
        b["name"], b["phone"], b["neighborhood"], b["address"], b["notes"],
    ).run()
    return int(res.meta.changes) == 1


#  admin

_BOOKING_COLUMNS = f"""
    code, service_id, service_name, category, price, date, start_min, end_min,
    customer_name, phone, neighborhood, address, notes, status, created_at,
    (status = 'pending' AND NOT {_active()}) AS expired
"""


async def list_bookings(db, first: date, last: date, status: str | None = None) -> list[dict]:
    sql = f"SELECT {_BOOKING_COLUMNS} FROM bookings WHERE date BETWEEN ?1 AND ?2"
    params = [first.isoformat(), last.isoformat()]
    if status:
        sql += " AND status = ?3"
        params.append(status)
    sql += " ORDER BY date, start_min LIMIT 500"
    res = await db.prepare(sql).bind(*params).all()
    return list(res.results)


async def get_booking(db, code: str):
    return await db.prepare(f"SELECT {_BOOKING_COLUMNS} FROM bookings WHERE code = ?1").bind(code).first()


async def set_booking_status(db, code: str, current: str, new: str) -> bool:
    guard = ""
    if new == "confirmed":
        guard = f"""
          AND NOT EXISTS (
            SELECT 1 FROM bookings o
             WHERE o.id != bookings.id AND o.date = bookings.date
               AND o.start_min < bookings.busy_until_min AND o.busy_until_min > bookings.start_min
               AND {_active('o')}
          )"""
    res = await db.prepare(
        f"""
        UPDATE bookings SET status = ?3, updated_at = datetime('now')
         WHERE code = ?1 AND status = ?2 {guard}
        """
    ).bind(code, current, new).run()
    return int(res.meta.changes) == 1


async def list_blocks(db, first: date, last: date) -> list[dict]:
    res = await db.prepare(
        "SELECT id, date, start_min, end_min, reason FROM blocked_slots "
        "WHERE date BETWEEN ?1 AND ?2 ORDER BY date, start_min"
    ).bind(first.isoformat(), last.isoformat()).all()
    return list(res.results)


async def insert_block(db, block: dict) -> int:
    res = await db.prepare(
        "INSERT INTO blocked_slots (date, start_min, end_min, reason) VALUES (?1, ?2, ?3, ?4)"
    ).bind(block["date"].isoformat(), block["start_min"], block["end_min"], block["reason"]).run()
    return int(res.meta.last_row_id)


async def delete_block(db, block_id: int) -> bool:
    res = await db.prepare("DELETE FROM blocked_slots WHERE id = ?1").bind(block_id).run()
    return int(res.meta.changes) == 1


async def count_active_overlapping(db, block: dict) -> int:
    row = await db.prepare(
        f"""
        SELECT COUNT(*) AS n FROM bookings
         WHERE date = ?1 AND start_min < ?3 AND busy_until_min > ?2 AND {_active()}
        """
    ).bind(block["date"].isoformat(), block["start_min"], block["end_min"]).first()
    return int(row["n"]) if row else 0


async def failed_logins(db, ip: str) -> int:
    row = await db.prepare(
        "SELECT COUNT(*) AS n FROM login_attempts "
        f"WHERE ip = ?1 AND attempted_at > datetime('now', '-{auth.LOCKOUT_WINDOW_MIN} minutes')"
    ).bind(ip).first()
    return int(row["n"]) if row else 0


async def record_failed_login(db, ip: str) -> None:
    await db.prepare("INSERT INTO login_attempts (ip) VALUES (?1)").bind(ip).run()
    await db.prepare("DELETE FROM login_attempts WHERE attempted_at < datetime('now', '-1 day')").run()


async def clear_failed_logins(db, ip: str) -> None:
    await db.prepare("DELETE FROM login_attempts WHERE ip = ?1").bind(ip).run()


async def failed_mfa(db, ip: str) -> int:
    row = await db.prepare(
        "SELECT COUNT(*) AS n FROM mfa_attempts "
        f"WHERE ip = ?1 AND attempted_at > datetime('now', '-{auth.LOCKOUT_WINDOW_MIN} minutes')"
    ).bind(ip).first()
    return int(row["n"]) if row else 0


async def record_failed_mfa(db, ip: str) -> None:
    await db.prepare("INSERT INTO mfa_attempts (ip) VALUES (?1)").bind(ip).run()
    await db.prepare("DELETE FROM mfa_attempts WHERE attempted_at < datetime('now', '-1 day')").run()


async def clear_failed_mfa(db, ip: str) -> None:
    await db.prepare("DELETE FROM mfa_attempts WHERE ip = ?1").bind(ip).run()
