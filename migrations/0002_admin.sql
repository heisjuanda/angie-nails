-- Intentos fallidos de ingreso al panel (bloqueo temporal contra fuerza bruta).
CREATE TABLE login_attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ip            TEXT NOT NULL,
    attempted_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_login_attempts_ip ON login_attempts (ip, attempted_at);
