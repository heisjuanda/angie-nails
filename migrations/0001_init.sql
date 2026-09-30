-- Esquema inicial. Horas en minutos desde la medianoche (hora de Colombia).
-- created_at / updated_at en UTC, formato 'YYYY-MM-DD HH:MM:SS' (datetime('now')).

CREATE TABLE bookings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT    NOT NULL UNIQUE,
    service_id      TEXT    NOT NULL,
    service_name    TEXT    NOT NULL,
    category        TEXT    NOT NULL,
    price           INTEGER,                 -- COP; NULL mientras el precio sea X
    duration_min    INTEGER NOT NULL,
    date            TEXT    NOT NULL,        -- YYYY-MM-DD
    start_min       INTEGER NOT NULL,
    end_min         INTEGER NOT NULL,
    busy_until_min  INTEGER NOT NULL,        -- end_min + tiempo de desplazamiento
    customer_name   TEXT    NOT NULL,
    phone           TEXT    NOT NULL,        -- 57XXXXXXXXXX
    neighborhood    TEXT    NOT NULL,
    address         TEXT    NOT NULL,
    notes           TEXT    NOT NULL DEFAULT '',
    status          TEXT    NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'confirmed', 'cancelled', 'completed')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_bookings_date_status ON bookings (date, status);
CREATE INDEX idx_bookings_phone ON bookings (phone);

-- Bloqueos manuales de agenda (vacaciones, compromisos). Día completo = 0..1440.
CREATE TABLE blocked_slots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    date        TEXT    NOT NULL,
    start_min   INTEGER NOT NULL,
    end_min     INTEGER NOT NULL,
    reason      TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_blocked_date ON blocked_slots (date);
