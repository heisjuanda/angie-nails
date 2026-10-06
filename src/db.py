import secrets
from datetime import date

import auth
import config


def _active(alias: str = "") -> str:
    p = f"{alias}." if alias else ""
    inicio = f"{p}date || ' ' || printf('%02d:%02d', {p}start_min / 60, {p}start_min % 60)"
    return (
        f"({p}status = 'confirmed' OR ({p}status = 'pending' AND ("
        f"{p}created_at > datetime('now', '-{int(config.PENDING_TTL_HOURS)} hours')"
        f" OR {inicio} > datetime('now', '-5 hours'))))"
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


def classify_unique_error(exc: Exception) -> str | None:
    msg = str(exc)
    if "UNIQUE" not in msg and "PRIMARY KEY" not in msg:
        return None
    if "bookings.form_token" in msg:
        return "form_token"
    if "bookings.code" in msg:
        return "code"
    return "other"


async def insert_booking_if_free(db, b: dict) -> bool:
    res = await db.prepare(
        f"""
        INSERT INTO bookings (
            code, service_id, service_name, category, price, duration_min,
            date, start_min, end_min, busy_until_min,
            customer_name, phone, neighborhood, address, notes, form_token
        )
        SELECT ?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16
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
        b["name"], b["phone"], b["neighborhood"], b["address"], b["notes"], b["form_token"],
    ).run()
    return int(res.meta.changes) == 1


#  admin

_BOOKING_COLUMNS = f"""
    code, service_id, service_name, category, price, date, start_min, end_min,
    customer_name, phone, neighborhood, address, notes, status, created_at,
    (status = 'pending' AND NOT {_active()}) AS expired
"""


async def list_bookings(
    db, first: date, last: date, status: str | None = None,
    limit: int = 500, offset: int = 0,
) -> list[dict]:
    sql = f"SELECT {_BOOKING_COLUMNS} FROM bookings WHERE date BETWEEN ?1 AND ?2"
    params: list = [first.isoformat(), last.isoformat()]
    if status:
        sql += " AND status = ?3"
        params.append(status)
    sql += f" ORDER BY date, start_min LIMIT ?{len(params) + 1} OFFSET ?{len(params) + 2}"
    params.extend([limit, offset])
    res = await db.prepare(sql).bind(*params).all()
    return list(res.results)


async def count_bookings(db, first: date, last: date, status: str | None = None) -> int:
    sql = "SELECT COUNT(*) AS n FROM bookings WHERE date BETWEEN ?1 AND ?2"
    params: list = [first.isoformat(), last.isoformat()]
    if status:
        sql += " AND status = ?3"
        params.append(status)
    row = await db.prepare(sql).bind(*params).first()
    return int(row["n"]) if row else 0


async def get_booking(db, code: str):
    return await db.prepare(f"SELECT {_BOOKING_COLUMNS} FROM bookings WHERE code = ?1").bind(code).first()


async def booking_stats(db, today: date) -> dict:
    row = await db.prepare(
        f"""
        SELECT
          COALESCE(SUM(CASE WHEN status = 'pending' AND {_active()} THEN 1 ELSE 0 END), 0) AS pending,
          COALESCE(SUM(CASE WHEN date = ?1 AND {_active()} THEN 1 ELSE 0 END), 0) AS today,
          COALESCE(SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END), 0) AS confirmed
        FROM bookings
        """
    ).bind(today.isoformat()).first()
    return {
        "pending": int(row["pending"]),
        "today": int(row["today"]),
        "confirmed": int(row["confirmed"]),
    }


async def get_booking_by_form_token(db, token: str):
    return await db.prepare(
        f"SELECT {_BOOKING_COLUMNS} FROM bookings WHERE form_token = ?1"
    ).bind(token).first()


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


async def create_session(db, sid: str, exp: int) -> None:
    await db.prepare("INSERT INTO admin_sessions (sid, exp) VALUES (?1, ?2)").bind(sid, exp).run()
    await db.prepare("DELETE FROM admin_sessions WHERE exp < strftime('%s', 'now')").run()


async def delete_session(db, sid: str | None) -> None:
    if sid:
        await db.prepare("DELETE FROM admin_sessions WHERE sid = ?1").bind(sid).run()


async def session_active(db, sid: str | None) -> bool:
    if not sid:
        return False
    row = await db.prepare(
        "SELECT 1 FROM admin_sessions WHERE sid = ?1 AND exp > strftime('%s', 'now')"
    ).bind(sid).first()
    return row is not None


#  topes de reservas

async def active_bookings_for_phone(db, phone: str, day: date) -> int:
    """Citas activas de ese teléfono para esa fecha. Las vencidas no cuentan."""
    row = await db.prepare(
        f"SELECT COUNT(*) AS n FROM bookings WHERE phone = ?1 AND date = ?2 AND {_active()}"
    ).bind(phone, day.isoformat()).first()
    return int(row["n"]) if row else 0


async def phone_attempts_in_day(db, phone: str) -> int:
    row = await db.prepare(
        "SELECT COUNT(*) AS n FROM booking_attempts "
        "WHERE phone = ?1 AND created_at > datetime('now', '-1 day')"
    ).bind(phone).first()
    return int(row["n"]) if row else 0


async def ip_attempts_in_hour(db, ip: str) -> int:
    row = await db.prepare(
        "SELECT COUNT(*) AS n FROM booking_attempts "
        "WHERE ip = ?1 AND created_at > datetime('now', '-1 hour')"
    ).bind(ip).first()
    return int(row["n"]) if row else 0


async def record_booking_attempt(db, ip: str, phone: str) -> None:
    await db.prepare("INSERT INTO booking_attempts (ip, phone) VALUES (?1, ?2)").bind(ip, phone).run()
    await db.prepare(
        "DELETE FROM booking_attempts WHERE created_at < datetime('now', '-2 days')"
    ).run()


async def purge_old_bookings(db, retention_days: int = config.RETENTION_DAYS) -> int:
    res = await db.prepare(
        f"DELETE FROM bookings WHERE date < date('now', '-{int(retention_days)} days')"
    ).run()
    return int(res.meta.changes)


async def purge_old_blocks(db, retention_days: int = config.RETENTION_DAYS) -> int:
    res = await db.prepare(
        f"DELETE FROM blocked_slots WHERE date < date('now', '-{int(retention_days)} days')"
    ).run()
    return int(res.meta.changes)
