-- Sesiones activas del panel. El token solo vale mientras exista esta fila:
-- el logout la borra e invalida el token al instante, sin esperar a que expire.
CREATE TABLE admin_sessions (
    sid  TEXT PRIMARY KEY,
    exp  INTEGER NOT NULL
);
