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
    desc        TEXT DEFAULT '',
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

-- Deshabilitar RLS (el service_key tiene acceso completo)
ALTER TABLE cuotas   DISABLE ROW LEVEL SECURITY;
ALTER TABLE reservas DISABLE ROW LEVEL SECURITY;
ALTER TABLE usuarios DISABLE ROW LEVEL SECURITY;
