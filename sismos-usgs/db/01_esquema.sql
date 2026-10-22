-- =====================================================================
--  Sistema 1 · Validación cruzada del catálogo sísmico SSN ↔ USGS
--  01 · Esquemas, staging y modelo dimensional
--
--  Se ejecuta solo la primera vez que se crea el volumen de PostgreSQL
--  (docker-entrypoint-initdb.d). Para recrearlo: docker compose down -v
-- =====================================================================

-- En sismología todo se expresa en UTC: cualquier sesión (psql, DBeaver, la API)
-- ve las marcas de tiempo en UTC aunque el servidor esté en hora del centro.
DO $$ BEGIN
    EXECUTE format('ALTER DATABASE %I SET timezone TO %L', current_database(), 'UTC');
END $$;
SET timezone TO 'UTC';

CREATE SCHEMA IF NOT EXISTS etl;      -- trazabilidad del pipeline
CREATE SCHEMA IF NOT EXISTS staging;  -- datos crudos, tal como llegan
CREATE SCHEMA IF NOT EXISTS dw;       -- modelo dimensional

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

-- Valor de un parámetro de la última carga exitosa (lo usan las vistas)
CREATE FUNCTION etl.parametro(p_clave TEXT)
RETURNS TEXT
LANGUAGE sql STABLE AS $$
    SELECT parametros ->> p_clave
    FROM etl.ejecucion
    WHERE estado = 'ok'
    ORDER BY id_ejecucion DESC
    LIMIT 1
$$;

-- ---------------------------------------------------------------------
--  STAGING
-- ---------------------------------------------------------------------

-- Fuente alterna: USGS ANSS ComCat. Mismas 22 columnas del CSV de la API
-- FDSN (https://earthquake.usgs.gov/fdsnws/event/1/).
CREATE TABLE staging.usgs_evento (
    time             TIMESTAMPTZ NOT NULL,
    latitude         DOUBLE PRECISION NOT NULL,
    longitude        DOUBLE PRECISION NOT NULL,
    depth            DOUBLE PRECISION,
    mag              DOUBLE PRECISION NOT NULL,
    magtype          TEXT,
    nst              INTEGER,
    gap              DOUBLE PRECISION,
    dmin             DOUBLE PRECISION,
    rms              DOUBLE PRECISION,
    net              TEXT,
    id               TEXT PRIMARY KEY,
    updated          TIMESTAMPTZ,
    place            TEXT,
    type             TEXT,
    horizontalerror  DOUBLE PRECISION,
    deptherror       DOUBLE PRECISION,
    magerror         DOUBLE PRECISION,
    magnst           INTEGER,
    status           TEXT,
    locationsource   TEXT,
    magsource        TEXT
);

-- Fuente original: catálogo del SSN tal como quedó en el data warehouse
-- del paper (dim_sismos ⋈ dim_tiempo, donde id_sismo = id_tiempo).
-- El DW guarda la FECHA LOCAL del SSN junto a la HORA UTC; el ETL conserva
-- esa marca (fecha_hora_dw) y reconstruye el instante UTC real (fecha_hora_utc).
CREATE TABLE staging.ssn_evento (
    id_sismo        INTEGER PRIMARY KEY,
    fecha_local     DATE NOT NULL,                -- tal como viene en dim_tiempo.fecha
    hora_utc        TIME NOT NULL,                -- tal como viene en dim_tiempo.hora_utc
    fecha_hora_dw   TIMESTAMPTZ NOT NULL,         -- fecha_local + hora_utc, como lo usa el DW
    fecha_hora_utc  TIMESTAMPTZ NOT NULL,         -- instante UTC reconstruido
    magnitud        DOUBLE PRECISION NOT NULL,
    latitud         DOUBLE PRECISION NOT NULL,
    longitud        DOUBLE PRECISION NOT NULL,
    profundidad     DOUBLE PRECISION,
    referencia      TEXT,
    estado          TEXT,
    nombre_estado   TEXT
);

-- ---------------------------------------------------------------------
--  MODELO DIMENSIONAL
-- ---------------------------------------------------------------------

-- Dimensión fuente: de dónde viene cada sismo y cómo se cita
CREATE TABLE dw.dim_fuente (
    id_fuente    SMALLINT PRIMARY KEY,
    codigo       TEXT NOT NULL UNIQUE,
    nombre       TEXT NOT NULL,
    institucion  TEXT NOT NULL,
    url          TEXT NOT NULL,
    doi          TEXT,
    licencia     TEXT,
    cita_apa     TEXT NOT NULL
);

INSERT INTO dw.dim_fuente VALUES
(1, 'SSN',
 'Catálogo de sismos del Servicio Sismológico Nacional (versión del DW del paper)',
 'Servicio Sismológico Nacional, UNAM',
 'https://github.com/gabrielhuav/Seismic-Data-Visualization-System',
 '10.24275/AZC2026E1004',
 'MIT (repositorio); datos del SSN-UNAM',
 'Villa Vargas, J. M., Hurtado Avilés, G., y Climent Hernández, J. A. (2026). Cuando México tiembla: la historia contada por los datos. AZCATL Revista de Divulgación de la Ciencia, la Ingeniería y la Innovación, 4(6), 28–33. https://doi.org/10.24275/AZC2026E1004'),
(2, 'USGS',
 'Advanced National Seismic System (ANSS) Comprehensive Catalog (ComCat)',
 'U.S. Geological Survey',
 'https://earthquake.usgs.gov/fdsnws/event/1/',
 '10.5066/F7MS3QZH',
 'Dominio público (U.S. Government)',
 'U.S. Geological Survey. (2017). Advanced National Seismic System (ANSS) Comprehensive Catalog [Conjunto de datos]. U.S. Geological Survey. https://doi.org/10.5066/F7MS3QZH');

-- Dimensión tiempo (grano día; la hora vive en dim_sismo)
CREATE TABLE dw.dim_tiempo (
    id_tiempo  INTEGER PRIMARY KEY,          -- AAAAMMDD
    fecha      DATE NOT NULL UNIQUE,
    anio       SMALLINT NOT NULL,
    mes        SMALLINT NOT NULL,
    dia        SMALLINT NOT NULL,
    trimestre  SMALLINT NOT NULL,
    decada     SMALLINT NOT NULL
);

-- Dimensión rango de magnitud (catálogo fijo)
CREATE TABLE dw.dim_rango_magnitud (
    id_rango  SMALLINT PRIMARY KEY,
    etiqueta  TEXT NOT NULL UNIQUE,
    mag_min   NUMERIC(3,1) NOT NULL,
    mag_max   NUMERIC(3,1) NOT NULL,
    CHECK (mag_min < mag_max)
);

INSERT INTO dw.dim_rango_magnitud VALUES
(1, 'M < 4.0',     -9.9,  4.0),
(2, 'M 4.0 – 4.4',  4.0,  4.5),
(3, 'M 4.5 – 4.9',  4.5,  5.0),
(4, 'M 5.0 – 5.9',  5.0,  6.0),
(5, 'M 6.0 – 6.9',  6.0,  7.0),
(6, 'M ≥ 7.0',      7.0, 99.9);

-- Dimensión sismo: un registro por evento y por fuente
CREATE TABLE dw.dim_sismo (
    id_sismo          BIGSERIAL PRIMARY KEY,
    id_fuente         SMALLINT NOT NULL REFERENCES dw.dim_fuente,
    id_externo        TEXT NOT NULL,                 -- id del SSN o del USGS
    fecha_hora_utc    TIMESTAMPTZ NOT NULL,              -- instante UTC (corregido en el SSN)
    fecha_hora_dw     TIMESTAMPTZ,                       -- solo SSN: la marca que trae el DW del paper
    fecha_corregida   BOOLEAN NOT NULL DEFAULT FALSE,    -- solo SSN: fecha_hora_dw ≠ fecha_hora_utc
    id_tiempo         INTEGER NOT NULL REFERENCES dw.dim_tiempo,
    id_rango          SMALLINT NOT NULL REFERENCES dw.dim_rango_magnitud,
    magnitud          DOUBLE PRECISION NOT NULL,
    tipo_magnitud     TEXT,                          -- solo USGS (mww, mb, ml…)
    latitud           DOUBLE PRECISION NOT NULL,
    longitud          DOUBLE PRECISION NOT NULL,
    profundidad_km    DOUBLE PRECISION,
    lugar             TEXT,
    estado            TEXT,                          -- solo SSN
    estatus_revision  TEXT,                          -- solo USGS (reviewed / automatic)
    red               TEXT,                          -- solo USGS: red que publicó el evento
    red_localizacion  TEXT,                          -- solo USGS: quién calculó el epicentro
    red_magnitud      TEXT,                          -- solo USGS: quién calculó la magnitud
    aporte_ssn        BOOLEAN NOT NULL DEFAULT FALSE,-- solo USGS: epicentro o magnitud de UNM (UNAM, el SSN)
    UNIQUE (id_fuente, id_externo)
);

CREATE INDEX idx_dim_sismo_fuente_fecha ON dw.dim_sismo (id_fuente, fecha_hora_utc);
CREATE INDEX idx_dim_sismo_fecha_dw     ON dw.dim_sismo (fecha_hora_dw) WHERE id_fuente = 1;

-- Hecho: resultado del cruce entre catálogos.
-- Grano: por cada variante de fecha del SSN, un sismo emparejado (SSN + USGS)
-- o un sismo que solo aparece en una de las dos fuentes.
--   variante = 'corregida'    fechas del SSN reconstruidas en UTC (análisis)
--   variante = 'dw_original'  fechas tal como están en el DW del paper (diagnóstico)
CREATE TABLE dw.fact_cruce_sismo (
    id_cruce              BIGSERIAL PRIMARY KEY,
    variante              TEXT NOT NULL CHECK (variante IN ('corregida', 'dw_original')),
    resultado             TEXT NOT NULL CHECK (resultado IN
                          ('ambas', 'solo_usgs', 'solo_ssn', 'fuera_de_cobertura')),
    id_sismo_ssn          BIGINT REFERENCES dw.dim_sismo,
    id_sismo_usgs         BIGINT REFERENCES dw.dim_sismo,
    id_tiempo             INTEGER NOT NULL REFERENCES dw.dim_tiempo,
    id_rango              SMALLINT NOT NULL REFERENCES dw.dim_rango_magnitud,
    magnitud_ref          DOUBLE PRECISION NOT NULL,  -- la del SSN si existe; si no, la del USGS
    independiente         BOOLEAN,            -- la solución USGS no la aportó el SSN (NULL en solo_ssn)
    delta_segundos        DOUBLE PRECISION,   -- t(USGS) − t(SSN)
    distancia_km          DOUBLE PRECISION,   -- entre epicentros
    delta_magnitud        DOUBLE PRECISION,   -- M(USGS) − M(SSN)
    delta_profundidad_km  DOUBLE PRECISION,   -- z(USGS) − z(SSN)
    puntaje               DOUBLE PRECISION,   -- 0 = idénticos; 3 = límite de tolerancia
    UNIQUE (variante, id_sismo_ssn),        -- en cada variante un sismo se empareja una sola vez
    UNIQUE (variante, id_sismo_usgs),
    CHECK (id_sismo_ssn IS NOT NULL OR id_sismo_usgs IS NOT NULL),
    CHECK ((resultado = 'ambas') = (id_sismo_ssn IS NOT NULL AND id_sismo_usgs IS NOT NULL))
);

CREATE INDEX idx_fact_cruce_resultado ON dw.fact_cruce_sismo (variante, resultado);
CREATE INDEX idx_fact_cruce_tiempo    ON dw.fact_cruce_sismo (id_tiempo);
CREATE INDEX idx_fact_cruce_rango     ON dw.fact_cruce_sismo (id_rango);
CREATE INDEX idx_fact_cruce_magnitud  ON dw.fact_cruce_sismo (magnitud_ref);

-- ---------------------------------------------------------------------
--  Diccionario de datos (se consulta con \d+ o desde DBeaver)
-- ---------------------------------------------------------------------
COMMENT ON TABLE staging.usgs_evento  IS 'Eventos crudos de USGS ComCat (API FDSN, CSV) dentro del rectángulo de México.';
COMMENT ON TABLE staging.ssn_evento   IS 'Eventos del SSN reconstruidos del DW del paper (dim_sismos ⋈ dim_tiempo).';
COMMENT ON COLUMN staging.ssn_evento.fecha_hora_dw  IS 'Fecha local del SSN + hora UTC: la combinación que usa el DW del paper (un día antes del real entre ~18:00 y 24:00 hora del centro).';
COMMENT ON COLUMN staging.ssn_evento.fecha_hora_utc IS 'Instante UTC cuyo día local en America/Mexico_City es fecha_local.';
COMMENT ON COLUMN dw.dim_sismo.aporte_ssn IS 'ComCat también publica soluciones que le envía el Instituto de Geofísica de la UNAM (código UNM, donde opera el SSN). Esos pares no son una validación independiente.';
COMMENT ON COLUMN dw.fact_cruce_sismo.independiente IS 'TRUE si el epicentro y la magnitud del USGS los calculó una red distinta del SSN.';
COMMENT ON COLUMN dw.dim_sismo.fecha_corregida IS 'TRUE si la fecha UTC real difiere de la que trae el DW del paper.';
COMMENT ON COLUMN dw.fact_cruce_sismo.variante IS 'corregida: fechas UTC reconstruidas (análisis) · dw_original: fechas tal como las trae el DW (diagnóstico).';
COMMENT ON TABLE dw.dim_fuente        IS 'Catálogo de fuentes con su cita APA y DOI.';
COMMENT ON TABLE dw.dim_sismo         IS 'Un sismo por fuente. id_externo conserva el identificador original.';
COMMENT ON TABLE dw.fact_cruce_sismo  IS 'Resultado del emparejamiento SSN ↔ USGS: pares y sismos sin contraparte.';
COMMENT ON COLUMN dw.fact_cruce_sismo.resultado IS 'ambas | solo_usgs | solo_ssn | fuera_de_cobertura (USGS posterior al último sismo del catálogo SSN).';
COMMENT ON COLUMN dw.fact_cruce_sismo.magnitud_ref IS 'Magnitud con la que se clasifica y filtra el registro: SSN cuando existe, USGS en otro caso.';
COMMENT ON COLUMN dw.fact_cruce_sismo.puntaje   IS 'Δt/Δt_max + d/d_max + |ΔM|/ΔM_max del par elegido; menor es mejor.';
