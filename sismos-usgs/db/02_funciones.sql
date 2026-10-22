-- =====================================================================
--  02 · Funciones: distancia, rango de magnitud y emparejamiento
-- =====================================================================

-- Distancia ortodrómica (haversine) en km entre dos epicentros
CREATE OR REPLACE FUNCTION dw.fn_distancia_km(
    lat1 DOUBLE PRECISION, lon1 DOUBLE PRECISION,
    lat2 DOUBLE PRECISION, lon2 DOUBLE PRECISION)
RETURNS DOUBLE PRECISION
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT 2 * 6371.0 * asin(least(1.0, sqrt(
               power(sin(radians(lat2 - lat1) / 2), 2) +
               cos(radians(lat1)) * cos(radians(lat2)) *
               power(sin(radians(lon2 - lon1) / 2), 2))))
$$;

-- Rango de magnitud al que pertenece un valor
CREATE OR REPLACE FUNCTION dw.fn_rango(p_magnitud DOUBLE PRECISION)
RETURNS SMALLINT
LANGUAGE sql STABLE AS $$
    SELECT id_rango
    FROM dw.dim_rango_magnitud
    WHERE p_magnitud >= mag_min AND p_magnitud < mag_max
$$;

-- ---------------------------------------------------------------------
--  Emparejamiento SSN ↔ USGS
--
--  p_variante elige qué marca de tiempo del SSN se usa:
--    'corregida'    el instante UTC reconstruido por el ETL (análisis)
--    'dw_original'  la marca que trae el DW del paper (diagnóstico)
--
--  1. Candidatos: para cada sismo del USGS, los del SSN que ocurrieron
--     dentro de la ventana de tiempo, a menos de la distancia máxima y con
--     una diferencia de magnitud no mayor a p_delta_mag_max. Antes de
--     p_anio_corte_hist (catálogos históricos, con epicentros redondeados
--     a grados y horas al minuto) las tolerancias de tiempo y distancia
--     son mayores.
--  2. Puntaje = Δt/Δt_max + d/d_max + |ΔM|/ΔM_max (0 = idénticos, 3 = límite).
--  3. Asignación voraz uno a uno: se toman primero los pares más
--     parecidos y un sismo no puede emparejarse dos veces. En una
--     secuencia de réplicas cada evento se queda con su mejor contraparte.
--  4. Lo que no se empareja queda como solo_usgs / solo_ssn.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION dw.fn_emparejar(
    p_variante           TEXT,
    p_ventana_seg        DOUBLE PRECISION,
    p_distancia_km       DOUBLE PRECISION,
    p_ventana_seg_hist   DOUBLE PRECISION,
    p_distancia_km_hist  DOUBLE PRECISION,
    p_anio_corte_hist    INTEGER,
    p_ssn_mag_min        DOUBLE PRECISION,
    p_delta_mag_max      DOUBLE PRECISION)
RETURNS TABLE (resultado TEXT, eventos BIGINT)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
DECLARE
    v_ventana_max  DOUBLE PRECISION := greatest(p_ventana_seg, p_ventana_seg_hist);
    v_ini_ssn      TIMESTAMPTZ;
    v_fin_ssn      TIMESTAMPTZ;
    r              RECORD;
BEGIN
    IF p_variante NOT IN ('corregida', 'dw_original') THEN
        RAISE EXCEPTION 'Variante desconocida: %', p_variante;
    END IF;

    DELETE FROM dw.fact_cruce_sismo WHERE variante = p_variante;

    -- Sismos del SSN con la marca de tiempo de la variante
    DROP TABLE IF EXISTS tmp_ssn;
    CREATE TEMP TABLE tmp_ssn AS
    SELECT id_sismo, magnitud, latitud, longitud, profundidad_km, id_rango,
           CASE WHEN p_variante = 'dw_original'
                THEN coalesce(fecha_hora_dw, fecha_hora_utc)
                ELSE fecha_hora_utc END AS t
    FROM dw.dim_sismo
    WHERE id_fuente = 1;
    CREATE INDEX ON tmp_ssn (t);
    ANALYZE tmp_ssn;

    SELECT min(t), max(t) INTO v_ini_ssn, v_fin_ssn FROM tmp_ssn;

    -- 1-2. Candidatos con su puntaje
    DROP TABLE IF EXISTS tmp_candidato;
    CREATE TEMP TABLE tmp_candidato AS
    SELECT c.id_usgs, c.id_ssn, c.dt_seg, c.d_km,
           c.dt_seg / c.v_max + c.d_km / c.d_max + c.dm / p_delta_mag_max AS puntaje
    FROM (
        SELECT u.id_sismo AS id_usgs,
               s.id_sismo AS id_ssn,
               abs(extract(epoch FROM (u.fecha_hora_utc - s.t))) AS dt_seg,
               dw.fn_distancia_km(u.latitud, u.longitud, s.latitud, s.longitud) AS d_km,
               abs(u.magnitud - s.magnitud) AS dm,
               CASE WHEN extract(year FROM u.fecha_hora_utc) < p_anio_corte_hist
                    THEN p_ventana_seg_hist ELSE p_ventana_seg END AS v_max,
               CASE WHEN extract(year FROM u.fecha_hora_utc) < p_anio_corte_hist
                    THEN p_distancia_km_hist ELSE p_distancia_km END AS d_max
        FROM dw.dim_sismo u
        JOIN tmp_ssn s
          ON s.t BETWEEN u.fecha_hora_utc - make_interval(secs => v_ventana_max)
                     AND u.fecha_hora_utc + make_interval(secs => v_ventana_max)
        WHERE u.id_fuente = 2
    ) c
    WHERE c.dt_seg <= c.v_max
      AND c.d_km   <= c.d_max
      AND c.dm     <= p_delta_mag_max;

    -- 3. Asignación voraz uno a uno
    DROP TABLE IF EXISTS tmp_par;
    CREATE TEMP TABLE tmp_par (
        id_usgs  BIGINT PRIMARY KEY,
        id_ssn   BIGINT NOT NULL UNIQUE,
        dt_seg   DOUBLE PRECISION,
        d_km     DOUBLE PRECISION,
        puntaje  DOUBLE PRECISION
    );

    FOR r IN SELECT * FROM tmp_candidato ORDER BY puntaje, id_usgs, id_ssn LOOP
        INSERT INTO tmp_par VALUES (r.id_usgs, r.id_ssn, r.dt_seg, r.d_km, r.puntaje)
        ON CONFLICT DO NOTHING;      -- uno de los dos ya tiene pareja: se descarta
    END LOOP;

    -- 4a. Pares
    INSERT INTO dw.fact_cruce_sismo
        (variante, resultado, id_sismo_ssn, id_sismo_usgs, id_tiempo, id_rango, magnitud_ref,
         independiente, delta_segundos, distancia_km, delta_magnitud, delta_profundidad_km, puntaje)
    SELECT p_variante, 'ambas', s.id_sismo, u.id_sismo,
           to_char(s.t AT TIME ZONE 'UTC', 'YYYYMMDD')::int, s.id_rango, s.magnitud,
           NOT u.aporte_ssn,
           extract(epoch FROM (u.fecha_hora_utc - s.t)),
           p.d_km,
           u.magnitud - s.magnitud,
           u.profundidad_km - s.profundidad_km,
           p.puntaje
    FROM tmp_par p
    JOIN dw.dim_sismo u ON u.id_sismo = p.id_usgs
    JOIN tmp_ssn s      ON s.id_sismo = p.id_ssn;

    -- 4b. Solo en el USGS (o fuera del periodo que cubre el catálogo SSN)
    INSERT INTO dw.fact_cruce_sismo (variante, resultado, id_sismo_usgs, id_tiempo, id_rango,
                                     magnitud_ref, independiente)
    SELECT p_variante,
           CASE WHEN u.fecha_hora_utc > v_fin_ssn OR u.fecha_hora_utc < v_ini_ssn
                THEN 'fuera_de_cobertura' ELSE 'solo_usgs' END,
           u.id_sismo, u.id_tiempo, u.id_rango, u.magnitud, NOT u.aporte_ssn
    FROM dw.dim_sismo u
    WHERE u.id_fuente = 2
      AND NOT EXISTS (SELECT 1 FROM tmp_par p WHERE p.id_usgs = u.id_sismo);

    -- 4c. Solo en el SSN (a partir de la magnitud mínima de análisis)
    INSERT INTO dw.fact_cruce_sismo (variante, resultado, id_sismo_ssn, id_tiempo, id_rango, magnitud_ref)
    SELECT p_variante, 'solo_ssn', s.id_sismo,
           to_char(s.t AT TIME ZONE 'UTC', 'YYYYMMDD')::int, s.id_rango, s.magnitud
    FROM tmp_ssn s
    WHERE s.magnitud >= p_ssn_mag_min
      AND NOT EXISTS (SELECT 1 FROM tmp_par p WHERE p.id_ssn = s.id_sismo);

    ANALYZE dw.fact_cruce_sismo;

    RETURN QUERY
    SELECT f.resultado, count(*)::BIGINT
    FROM dw.fact_cruce_sismo f
    WHERE f.variante = p_variante
    GROUP BY f.resultado
    ORDER BY f.resultado;
END;
$$;

COMMENT ON FUNCTION dw.fn_emparejar IS
'Empareja sismos SSN↔USGS uno a uno por cercanía en tiempo, espacio y magnitud, y llena dw.fact_cruce_sismo para la variante indicada.';
