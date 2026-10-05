-- Topes de reservas: cuentan cuántas citas creó cada teléfono y cada IP.
-- Es un tope de velocidad, no un muro: frena el script y el error, no al atacante
-- decidido. La tabla se limpia sola en cada registro, así que queda acotada a dos días.

CREATE TABLE booking_attempts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ip         TEXT NOT NULL,
    phone      TEXT,                        -- normalizado (57XXXXXXXXXX); puede ser NULL
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_booking_attempts_ip    ON booking_attempts (ip, created_at);
CREATE INDEX IF NOT EXISTS idx_booking_attempts_phone ON booking_attempts (phone, created_at);