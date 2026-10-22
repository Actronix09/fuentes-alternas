-- =====================================================================
--  02 · Funciones: distancia, puntaje de atipicidad y su evaluación
-- =====================================================================

-- Distancia aproximada en metros (equirrectangular; error despreciable a
-- la escala de una ciudad)
CREATE OR REPLACE FUNCTION dw.fn_distancia_m(
    lat1 DOUBLE PRECISION, lon1 DOUBLE PRECISION,
    lat2 DOUBLE PRECISION, lon2 DOUBLE PRECISION)
RETURNS DOUBLE PRECISION
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT 6371000.0 * sqrt(
        power(radians(lat2 - lat1), 2) +
        power(radians(lon2 - lon1) * cos(radians((lat1 + lat2) / 2)), 2))
$$;

-- ---------------------------------------------------------------------
--  Puntaje de atipicidad del paper y reportes reales por colonia
--
--  A_g = |x_g − μ| / (σ + ε)       (ecuación 1 del paper)
--    x_g  consumo agregado de la colonia (suma del 1er semestre de 2019)
--    μ, σ media y desviación de las colonias de SU alcaldía
--  A_g normalizado: el mismo cálculo con el consumo por manzana, para que
--    el tamaño de la colonia no domine el puntaje.
--
--  La "verdad de campo" que al paper le faltaba: los reportes del tipo y
--  periodo elegidos, por manzana (densidad). Una colonia es positiva si su
--  densidad está en el cuartil superior de la ciudad.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION dw.fn_puntajes(p_tipo TEXT, p_desde DATE, p_hasta DATE)
RETURNS TABLE (
    id_ubicacion         INTEGER,
    alcaldia             TEXT,
    colonia              TEXT,
    latitud              DOUBLE PRECISION,
    longitud             DOUBLE PRECISION,
    manzanas             INTEGER,
    consumo_m3           NUMERIC,
    consumo_por_manzana  NUMERIC,
    z                    DOUBLE PRECISION,
    a_g                  DOUBLE PRECISION,
    z_norm               DOUBLE PRECISION,
    a_g_norm             DOUBLE PRECISION,
    reportes             BIGINT,
    densidad             DOUBLE PRECISION,
    positivo             BOOLEAN)
LANGUAGE sql STABLE AS $$
    WITH consumo AS (
        SELECT u.id_ubicacion, u.alcaldia, u.colonia, u.latitud, u.longitud, u.manzanas,
               sum(f.consumo_total) AS x
        FROM dw.fact_consumo_agua f
        JOIN dw.dim_ubicacion u ON u.id_ubicacion = f.id_ubicacion
        GROUP BY u.id_ubicacion, u.alcaldia, u.colonia, u.latitud, u.longitud, u.manzanas
    ), estadistica AS (
        SELECT c.*,
               c.x / greatest(c.manzanas, 1)                                   AS x_norm,
               avg(c.x)          OVER (PARTITION BY c.alcaldia)               AS mu,
               stddev_pop(c.x)   OVER (PARTITION BY c.alcaldia)               AS sigma,
               avg(c.x / greatest(c.manzanas, 1))        OVER (PARTITION BY c.alcaldia) AS mu_n,
               stddev_pop(c.x / greatest(c.manzanas, 1)) OVER (PARTITION BY c.alcaldia) AS sigma_n
        FROM consumo c
    ), reportes AS (
        SELECT r.id_ubicacion, count(*) AS n
        FROM dw.fact_reporte_agua r
        JOIN dw.dim_tipo_reporte tr ON tr.id_tipo = r.id_tipo
        JOIN dw.dim_tiempo t        ON t.id_tiempo = r.id_tiempo
        WHERE tr.reporte = p_tipo
          AND t.fecha BETWEEN p_desde AND p_hasta
          AND r.id_ubicacion IS NOT NULL
        GROUP BY r.id_ubicacion
    ), base AS (
        SELECT e.*,
               coalesce(rp.n, 0)                                   AS n,
               coalesce(rp.n, 0)::float8 / greatest(e.manzanas, 1) AS dens
        FROM estadistica e
        LEFT JOIN reportes rp ON rp.id_ubicacion = e.id_ubicacion
    ), umbral AS (
        SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY b.dens) AS p75 FROM base b
    )
    SELECT b.id_ubicacion, b.alcaldia, b.colonia, b.latitud, b.longitud, b.manzanas,
           round(b.x, 1),
           round(b.x_norm, 2),
           (b.x - b.mu) / (b.sigma + 1e-9),
           abs(b.x - b.mu) / (b.sigma + 1e-9),
           (b.x_norm - b.mu_n) / (b.sigma_n + 1e-9),
           abs(b.x_norm - b.mu_n) / (b.sigma_n + 1e-9),
           b.n,
           b.dens,
           b.dens > 0 AND b.dens >= u.p75
    FROM base b CROSS JOIN umbral u
$$;

COMMENT ON FUNCTION dw.fn_puntajes IS
'Por colonia: consumo, puntaje A_g del paper (y normalizado por manzana), reportes del tipo y periodo dados, densidad y etiqueta de cuartil superior.';

-- ---------------------------------------------------------------------
--  Evaluación del puntaje contra los reportes
--    auc          área bajo la curva ROC (Mann-Whitney): 0.5 = azar
--    spearman     correlación de rangos entre puntaje y densidad
--    precision_47 de las 47 colonias más atípicas, cuántas son positivas
--                 (47 es el punto de operación que usa el paper)
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION dw.fn_evaluacion(p_tipo TEXT, p_desde DATE, p_hasta DATE,
                                            p_alcaldia TEXT DEFAULT NULL)
RETURNS TABLE (
    puntaje        TEXT,
    colonias       BIGINT,
    positivos      BIGINT,
    reportes       NUMERIC,
    auc            NUMERIC,
    spearman       NUMERIC,
    precision_47   NUMERIC,
    recall_47      NUMERIC,
    precision_100  NUMERIC,
    prevalencia    NUMERIC)
LANGUAGE sql STABLE AS $$
    WITH p AS (
        SELECT * FROM dw.fn_puntajes(p_tipo, p_desde, p_hasta) x
        WHERE p_alcaldia IS NULL OR x.alcaldia = p_alcaldia
    ), largo AS (
        SELECT 'A_g del paper' AS cual, p.a_g AS s, p.densidad, p.positivo, p.reportes FROM p
        UNION ALL
        SELECT 'A_g por manzana', p.a_g_norm, p.densidad, p.positivo, p.reportes FROM p
    ), rangos AS (
        SELECT l.*,
               rank() OVER (PARTITION BY l.cual ORDER BY l.s)
                 + (count(*) OVER (PARTITION BY l.cual, l.s) - 1) / 2.0        AS r_s,
               rank() OVER (PARTITION BY l.cual ORDER BY l.densidad)
                 + (count(*) OVER (PARTITION BY l.cual, l.densidad) - 1) / 2.0 AS r_d,
               row_number() OVER (PARTITION BY l.cual ORDER BY l.s DESC)      AS orden
        FROM largo l
    )
    SELECT r.cual,
           count(*),
           count(*) FILTER (WHERE r.positivo),
           sum(r.reportes),
           round(((sum(r.r_s) FILTER (WHERE r.positivo)
                   - count(*) FILTER (WHERE r.positivo) * (count(*) FILTER (WHERE r.positivo) + 1) / 2.0)
                  / nullif(count(*) FILTER (WHERE r.positivo) * count(*) FILTER (WHERE NOT r.positivo), 0))::numeric, 3),
           round(corr(r.r_s, r.r_d)::numeric, 3),
           round(avg(r.positivo::int) FILTER (WHERE r.orden <= 47)::numeric, 3),
           round(count(*) FILTER (WHERE r.positivo AND r.orden <= 47)::numeric
                 / nullif(count(*) FILTER (WHERE r.positivo), 0), 3),
           round(avg(r.positivo::int) FILTER (WHERE r.orden <= 100)::numeric, 3),
           round(avg(r.positivo::int)::numeric, 3)
    FROM rangos r
    GROUP BY r.cual
    ORDER BY r.cual DESC
$$;

COMMENT ON FUNCTION dw.fn_evaluacion IS
'AUC, Spearman y precisión@47/100 del puntaje A_g (del paper y por manzana) contra la densidad de reportes reales.';

-- Curva precision-recall completa del puntaje (lo que el paper deja como trabajo futuro)
CREATE OR REPLACE FUNCTION dw.fn_curva_pr(p_tipo TEXT, p_desde DATE, p_hasta DATE,
                                          p_alcaldia TEXT DEFAULT NULL,
                                          p_normalizado BOOLEAN DEFAULT FALSE)
RETURNS TABLE (k BIGINT, precision_k NUMERIC, recall_k NUMERIC)
LANGUAGE sql STABLE AS $$
    WITH p AS (
        SELECT CASE WHEN p_normalizado THEN x.a_g_norm ELSE x.a_g END AS s, x.positivo
        FROM dw.fn_puntajes(p_tipo, p_desde, p_hasta) x
        WHERE p_alcaldia IS NULL OR x.alcaldia = p_alcaldia
    ), acumulado AS (
        SELECT row_number() OVER (ORDER BY p.s DESC)                                 AS k,
               sum(p.positivo::int) OVER (ORDER BY p.s DESC ROWS UNBOUNDED PRECEDING) AS tp,
               sum(p.positivo::int) OVER ()                                          AS total_pos
        FROM p
    )
    SELECT a.k,
           round(a.tp::numeric / a.k, 4),
           round(a.tp::numeric / nullif(a.total_pos, 0), 4)
    FROM acumulado a
    ORDER BY a.k
$$;
