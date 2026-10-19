-- ═══════════════════════════════════════════════════════════════
--  Riviera Park II — Supabase Schema
--  Pega este SQL en: Supabase → SQL Editor → New query → Run
-- ═══════════════════════════════════════════════════════════════

-- Tabla principal de cuotas (plan de pagos)
CREATE TABLE IF NOT EXISTS cuotas (
    id          SERIAL PRIMARY KEY,
    proyecto    TEXT NOT NULL DEFAULT 'riviera-park-2',
    unidad      TEXT NOT NULL,
    nombre      TEXT NOT NULL,
    num_cuota   INTEGER,
    descripcion TEXT DEFAULT '',
    fecha_venc  DATE,
    monto       NUMERIC(12,2) NOT NULL DEFAULT 0,
    fecha_pago  DATE,
    forma_pago  TEXT,
    referencia  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla de reservas
CREATE TABLE IF NOT EXISTS reservas (
    id          SERIAL PRIMARY KEY,
    proyecto    TEXT NOT NULL DEFAULT 'riviera-park-2',
    nombre      TEXT NOT NULL,
    unidad      TEXT NOT NULL,
    monto       NUMERIC(12,2) NOT NULL DEFAULT 0,
    fecha       TEXT,
    notas       TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla de usuarios dinámicos (los del panel admin)
CREATE TABLE IF NOT EXISTS usuarios (
    id            SERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    nombre        TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    rol           TEXT NOT NULL DEFAULT 'usuario',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para velocidad
CREATE INDEX IF NOT EXISTS idx_cuotas_proyecto    ON cuotas(proyecto);
CREATE INDEX IF NOT EXISTS idx_cuotas_unidad      ON cuotas(unidad);
CREATE INDEX IF NOT EXISTS idx_cuotas_fecha_pago  ON cuotas(fecha_pago);
CREATE INDEX IF NOT EXISTS idx_reservas_proyecto  ON reservas(proyecto);

-- Recibos emitidos. El PDF vive en Storage: recibos/{unidad}/Recibo_{num}.pdf
CREATE TABLE IF NOT EXISTS recibos (
    num       INTEGER PRIMARY KEY,
    cuota_id  INTEGER,
    unidad    TEXT,
    nombre    TEXT,
    "desc"    TEXT,
    monto     NUMERIC(12,2),
    fecha     TEXT,
    estado    TEXT DEFAULT 'emitido',
    proyecto  TEXT,
    forma     TEXT
);

-- Consecutivo de recibos. La fila nombre='recibo' arranca en 1020.
CREATE TABLE IF NOT EXISTS contadores (
    nombre  TEXT PRIMARY KEY,
    valor   INTEGER NOT NULL
);

-- Llaves para que otras apps suban contratos y anexos.
-- Hasta crear esta tabla, la app guarda los hashes en Storage: sistema/api_claves.json
CREATE TABLE IF NOT EXISTS api_claves (
    id          TEXT PRIMARY KEY,
    etiqueta    TEXT NOT NULL,
    key_hash    TEXT NOT NULL UNIQUE,
    prefijo     TEXT NOT NULL,
    activa      BOOLEAN NOT NULL DEFAULT TRUE,
    creado_por  TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    ultimo_uso  TIMESTAMPTZ
);

-- Deshabilitar RLS (el service_key tiene acceso completo)
ALTER TABLE cuotas     DISABLE ROW LEVEL SECURITY;
ALTER TABLE reservas   DISABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios   DISABLE ROW LEVEL SECURITY;
ALTER TABLE recibos    DISABLE ROW LEVEL SECURITY;
ALTER TABLE contadores DISABLE ROW LEVEL SECURITY;
ALTER TABLE api_claves DISABLE ROW LEVEL SECURITY;
