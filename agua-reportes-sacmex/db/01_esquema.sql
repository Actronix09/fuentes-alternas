-- =====================================================================
--  Sistema 2 · Consumo de agua en la CDMX validado con reportes ciudadanos
--  01 · Esquemas, staging y modelo dimensional
--
--  Se ejecuta solo la primera vez que se crea el volumen de PostgreSQL
--  (docker-entrypoint-initdb.d). Para recrearlo: docker compose down -v
--
--  Las tablas dim_tiempo, dim_ubicacion, dim_indice_des y fact_consumo_agua
--  conservan los nombres del DW del paper (repositorio data_warehouse_cdmx);
--  lo nuevo es todo lo que viene de la fuente alterna: dim_tipo_reporte,
--  dim_medio_recepcion, manzana y fact_reporte_agua.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dw;

-- ---------------------------------------------------------------------
--  ETL: cada ejecución y cada paso quedan registrados
-- ---------------------------------------------------------------------
CREATE TABLE etl.ejecucion (
    id_ejecucion  SERIAL PRIMARY KEY,
    inicio        TIMESTAMPTZ NOT NULL DEFAULT now(),
    fin           TIMESTAMPTZ,
    estado        TEXT NOT NULL DEFAULT 'en_proceso'
                  CHECK (estado IN ('en_proceso', 'ok', 'error')),
    parametros    JSONB NOT NULL DEFAULT '{}'::jsonb,
    mensaje       TEXT
);

CREATE TABLE etl.bitacora (
    id_bitacora   BIGSERIAL PRIMARY KEY,
    id_ejecucion  INTEGER NOT NULL REFERENCES etl.ejecucion ON DELETE CASCADE,
    momento       TIMESTAMPTZ NOT NULL DEFAULT now(),
    fase          TEXT NOT NULL
                  CHECK (fase IN ('extraccion', 'validacion', 'carga', 'transformacion')),
    paso          TEXT NOT NULL,
    registros     BIGINT,
    detalle       TEXT
);

-- Recursos descargados del portal (para citar la versión exacta)
CREATE TABLE etl.recurso (
    id_recurso          TEXT PRIMARY KEY,      -- id del recurso en CKAN
    conjunto            TEXT NOT NULL,
    nombre              TEXT NOT NULL,
    url                 TEXT NOT NULL,
    ultima_modificacion TIMESTAMPTZ,
    descargado          TIMESTAMPTZ NOT NULL DEFAULT now(),
    bytes               BIGINT
);

-- ---------------------------------------------------------------------
--  STAGING
-- ---------------------------------------------------------------------

-- Fuente original del paper: consumo de agua 1er semestre 2019 (SACMEX)
CREATE TABLE staging.consumo (
    fecha_referencia      DATE NOT NULL,
    anio                  INTEGER,
    bimestre              INTEGER,
    consumo_total_mixto   NUMERIC,
    consumo_prom_dom      NUMERIC,
    consumo_total_dom     NUMERIC,
    consumo_prom_mixto    NUMERIC,
    consumo_total         NUMERIC,
    consumo_prom          NUMERIC,
    consumo_prom_no_dom   NUMERIC,
    consumo_total_no_dom  NUMERIC,
    indice_des            TEXT,
    colonia               TEXT NOT NULL,
    alcaldia              TEXT NOT NULL,
    latitud               DOUBLE PRECISION,
    longitud              DOUBLE PRECISION,
    alcaldia_norm         TEXT NOT NULL,          -- MAYÚSCULAS, sin acentos ni signos
    colonia_norm          TEXT NOT NULL
);

-- Fuente alterna: reportes ciudadanos de agua (SACMEX). Los dos recursos del
-- portal (histórico 2018-2021 e incidentes 2022-2024) tienen columnas distintas;
-- el ETL los lleva a este formato común.
CREATE TABLE staging.reporte_agua (
    id_staging      BIGSERIAL PRIMARY KEY,
    recurso         TEXT NOT NULL CHECK (recurso IN ('historico_2018_2021', 'incidentes_2022_2024')),
    folio           TEXT NOT NULL,
    fecha           DATE NOT NULL,
    hora            TIME,
    clasificacion   TEXT NOT NULL,              -- Agua Potable, Drenaje, Agua Tratada
    reporte         TEXT NOT NULL,              -- Falta de agua, Fuga, Mala calidad…
    medio           TEXT NOT NULL,              -- medio de recepción
    alcaldia        TEXT,
    colonia         TEXT,
    alcaldia_norm   TEXT,
    colonia_norm    TEXT,
    latitud         DOUBLE PRECISION,           -- NULL si caía fuera de la CDMX
    longitud        DOUBLE PRECISION,
    UNIQUE (recurso, folio)
);

-- ---------------------------------------------------------------------
--  MODELO DIMENSIONAL
-- ---------------------------------------------------------------------

-- Dimensión tiempo (grano día). id_tiempo = AAAAMMDD
CREATE TABLE dw.dim_tiempo (
    id_tiempo  INTEGER PRIMARY KEY,
    fecha      DATE NOT NULL UNIQUE,
    anio       SMALLINT NOT NULL,
    mes        SMALLINT NOT NULL,
    dia        SMALLINT NOT NULL,
    bimestre   SMALLINT NOT NULL,
    semestre   SMALLINT NOT NULL
);

-- Dimensión ubicación: par alcaldía–colonia del catálogo del consumo.
-- A diferencia del DW original se guarda el centroide (promedio de las
-- manzanas de la colonia) para el mapa y el número de manzanas, que sirve
-- para normalizar los reportes por tamaño de colonia.
CREATE TABLE dw.dim_ubicacion (
    id_ubicacion   SERIAL PRIMARY KEY,
    alcaldia       TEXT NOT NULL,
    colonia        TEXT NOT NULL,
    alcaldia_norm  TEXT NOT NULL,
    colonia_norm   TEXT NOT NULL,
    latitud        DOUBLE PRECISION,
    longitud       DOUBLE PRECISION,
    manzanas       INTEGER NOT NULL DEFAULT 0,
    UNIQUE (alcaldia_norm, colonia_norm)
);

-- Puntos de manzana del consumo: permiten asignar un reporte con coordenadas
-- a la colonia de la manzana más cercana. celda_x / celda_y forman una rejilla
-- de 0.01° (~1.1 km) que hace de índice espacial sin necesidad de PostGIS.
CREATE TABLE dw.manzana (
    id_manzana    SERIAL PRIMARY KEY,
    id_ubicacion  INTEGER NOT NULL REFERENCES dw.dim_ubicacion,
    latitud       DOUBLE PRECISION NOT NULL,
    longitud      DOUBLE PRECISION NOT NULL,
    celda_x       INTEGER NOT NULL,
    celda_y       INTEGER NOT NULL
);
CREATE INDEX idx_manzana_celda ON dw.manzana (celda_x, celda_y);

-- Dimensión índice de desarrollo (igual que en el DW original)
CREATE TABLE dw.dim_indice_des (
    id_indice_des  SERIAL PRIMARY KEY,
    indice_des     TEXT NOT NULL UNIQUE
);

-- Hecho del paper: consumo por manzana, índice de desarrollo y bimestre
CREATE TABLE dw.fact_consumo_agua (
    id_fact               SERIAL PRIMARY KEY,
    id_tiempo             INTEGER NOT NULL REFERENCES dw.dim_tiempo,
    id_ubicacion          INTEGER NOT NULL REFERENCES dw.dim_ubicacion,
    id_indice_des         INTEGER NOT NULL REFERENCES dw.dim_indice_des,
    consumo_total_mixto   NUMERIC,
    consumo_prom_dom      NUMERIC,
    consumo_total_dom     NUMERIC,
    consumo_prom_mixto    NUMERIC,
    consumo_total         NUMERIC,
    consumo_prom          NUMERIC,
    consumo_prom_no_dom   NUMERIC,
    consumo_total_no_dom  NUMERIC
);
CREATE INDEX idx_fact_consumo_ubicacion ON dw.fact_consumo_agua (id_ubicacion);

-- NUEVO · Dimensión tipo de reporte
CREATE TABLE dw.dim_tipo_reporte (
    id_tipo          SERIAL PRIMARY KEY,
    clasificacion    TEXT NOT NULL,
    reporte          TEXT NOT NULL,
    es_agua_potable  BOOLEAN NOT NULL,
    UNIQUE (clasificacion, reporte)
);

-- NUEVO · Dimensión medio de recepción
CREATE TABLE dw.dim_medio_recepcion (
    id_medio  SERIAL PRIMARY KEY,
    medio     TEXT NOT NULL UNIQUE
);

-- NUEVO · Hecho: un renglón por reporte ciudadano
CREATE TABLE dw.fact_reporte_agua (
    id_reporte        BIGSERIAL PRIMARY KEY,
    recurso           TEXT NOT NULL,
    folio             TEXT NOT NULL,
    id_tiempo         INTEGER NOT NULL REFERENCES dw.dim_tiempo,
    id_ubicacion      INTEGER REFERENCES dw.dim_ubicacion,      -- NULL si no se pudo ubicar
    id_tipo           INTEGER NOT NULL REFERENCES dw.dim_tipo_reporte,
    id_medio          INTEGER NOT NULL REFERENCES dw.dim_medio_recepcion,
    metodo_ubicacion  TEXT CHECK (metodo_ubicacion IN ('nombre', 'manzana_cercana')),
    distancia_m       DOUBLE PRECISION,       -- a la manzana elegida (solo por cercanía)
    latitud           DOUBLE PRECISION,
    longitud          DOUBLE PRECISION,
    UNIQUE (recurso, folio)
);
CREATE INDEX idx_fact_reporte_tipo_tiempo ON dw.fact_reporte_agua (id_tipo, id_tiempo);
CREATE INDEX idx_fact_reporte_ubicacion   ON dw.fact_reporte_agua (id_ubicacion);

-- ---------------------------------------------------------------------
--  Diccionario de datos
-- ---------------------------------------------------------------------
COMMENT ON TABLE staging.consumo        IS 'Consumo de agua del 1er semestre de 2019 por manzana e índice de desarrollo (SACMEX, Datos Abiertos CDMX).';
COMMENT ON TABLE staging.reporte_agua   IS 'Reportes ciudadanos de agua 2018-2024 (SACMEX) en un formato común para los dos recursos del portal.';
COMMENT ON TABLE dw.dim_ubicacion       IS 'Par alcaldía-colonia del catálogo del consumo, con centroide y número de manzanas.';
COMMENT ON TABLE dw.manzana             IS 'Puntos de manzana del consumo con una rejilla de 0.01° como índice espacial.';
COMMENT ON TABLE dw.fact_reporte_agua   IS 'Un reporte ciudadano por renglón, ubicado en una colonia por nombre o por la manzana más cercana.';
COMMENT ON COLUMN dw.fact_reporte_agua.metodo_ubicacion IS 'nombre: coincidió alcaldía y colonia normalizadas · manzana_cercana: la manzana más próxima a ≤ 1 km.';
