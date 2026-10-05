-- Intentos fallidos del segundo factor (TOTP) del panel (bloqueo temporal).
CREATE TABLE mfa_attempts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ip            TEXT NOT NULL,
    attempted_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_mfa_attempts_ip ON mfa_attempts (ip, attempted_at);
