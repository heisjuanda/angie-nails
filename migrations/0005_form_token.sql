-- Llave de idempotencia: la genera el navegador al abrir el formulario y se manda en
-- cada POST /api/bookings. Si la respuesta se pierde y la clienta reintenta, el servidor
-- devuelve la cita que ya creó en vez de decir "ese horario ya está reservado".
--
-- No es una credencial ni un control de abuso: se valida que esté presente, no que sea
-- auténtica. Lo que hace única es correlationar dos envíos del mismo formulario.

ALTER TABLE bookings ADD COLUMN form_token TEXT;

-- Índice único parcial: las filas viejas (NULL) no chocan entre sí.
CREATE UNIQUE INDEX IF NOT EXISTS idx_bookings_form_token
    ON bookings (form_token) WHERE form_token IS NOT NULL;