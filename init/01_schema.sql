CREATE EXTENSION IF NOT EXISTS vector;


CREATE TABLE IF NOT EXISTS cat_departamento (
    id   SMALLSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cat_provincia (
    id             SMALLSERIAL PRIMARY KEY,
    nombre         TEXT NOT NULL,
    departamento_id SMALLINT REFERENCES cat_departamento(id),
    UNIQUE (nombre, departamento_id)
);

CREATE TABLE IF NOT EXISTS cat_distrito (
    id          SMALLSERIAL PRIMARY KEY,
    nombre      TEXT NOT NULL,
    provincia_id SMALLINT REFERENCES cat_provincia(id),
    UNIQUE (nombre, provincia_id)
);

CREATE TABLE IF NOT EXISTS cat_sector (
    id     SMALLSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cat_nivel_gobierno (
    id     SMALLSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cat_clasificador_n1 (
    id     SMALLSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cat_clasificador_n2 (
    id   SMALLSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    n1_id  SMALLINT REFERENCES cat_clasificador_n1(id),
    UNIQUE (nombre, n1_id)
);

CREATE TABLE IF NOT EXISTS cat_clasificador_n3 (
    id    SMALLSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    n2_id  SMALLINT REFERENCES cat_clasificador_n2(id),
    UNIQUE (nombre, n2_id)
);

CREATE TABLE IF NOT EXISTS cat_estado_ejecucion (
    id     SMALLSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cat_modalidad (
    id     SMALLSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS cat_naturaleza (
    id     SMALLSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS obras (
    id                  SERIAL PRIMARY KEY,
    codigo_infobras     INTEGER NOT NULL UNIQUE,

    -- Descripción
    nombre_obra         TEXT,
    nombre_proyecto     TEXT,
    entidad_publica     TEXT,

    -- FKs a catálogos
    departamento_id     SMALLINT REFERENCES cat_departamento(id),
    provincia_id        SMALLINT REFERENCES cat_provincia(id),
    distrito_id         SMALLINT REFERENCES cat_distrito(id),
    sector_id           SMALLINT REFERENCES cat_sector(id),
    nivel_gobierno_id   SMALLINT REFERENCES cat_nivel_gobierno(id),
    clasificador_n1_id  SMALLINT REFERENCES cat_clasificador_n1(id),
    clasificador_n2_id  SMALLINT REFERENCES cat_clasificador_n2(id),
    clasificador_n3_id  SMALLINT REFERENCES cat_clasificador_n3(id),
    estado_ejecucion_id SMALLINT REFERENCES cat_estado_ejecucion(id),
    modalidad_id        SMALLINT REFERENCES cat_modalidad(id),
    naturaleza_id       SMALLINT REFERENCES cat_naturaleza(id),

    -- Flags booleanos
    existe_paralizacion       BOOLEAN DEFAULT FALSE,
    marca_reconstruccion      BOOLEAN DEFAULT FALSE,
    marca_reactivacion        BOOLEAN DEFAULT FALSE,

    -- Texto libre
    direccion           TEXT,
    empresa_contratista TEXT,
    motivo_no_100       TEXT,
    causal_paralizacion TEXT,
    comentarios         TEXT,
    estado_proyecto     TEXT,

    -- Fechas relevantes
    fecha_inicio_obra   DATE,
    fecha_fin_real      DATE,

    -- Texto que se embebió
    texto_embedding     TEXT
);

-- ============================================================
-- TABLA DE EMBEDDINGS 
-- ============================================================
CREATE TABLE IF NOT EXISTS embeddings (
    id              SERIAL PRIMARY KEY,
    obra_id         INTEGER NOT NULL REFERENCES obras(id) ON DELETE CASCADE,
    vector          vector(384) NOT NULL          -- paraphrase-multilingual-MiniLM-L12-v2
);

-- Indice HNSW: busqueda aproximada rapida con similitud coseno
CREATE INDEX IF NOT EXISTS idx_emb_hnsw
    ON embeddings
    USING hnsw (vector vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Indice para JOIN rapido entre obras y embeddings
CREATE INDEX IF NOT EXISTS idx_emb_obra_id ON embeddings(obra_id);
CREATE INDEX IF NOT EXISTS idx_obras_codigo ON obras(codigo_infobras);