-- =====================================================================
--  03 · Vistas analíticas: las preguntas que responde el sistema
--
--  Todas trabajan con la variante 'corregida' (fechas UTC reconstruidas),
--  salvo las de diagnóstico, que comparan las dos variantes.
-- =====================================================================

-- Pares emparejados con el detalle de ambas fuentes (las dos variantes)
CREATE OR REPLACE VIEW dw.v_pares AS
SELECT f.id_cruce,
       f.variante,
       CASE WHEN f.variante = 'dw_original' THEN coalesce(s.fecha_hora_dw, s.fecha_hora_utc)
            ELSE s.fecha_hora_utc END   AS fecha_hora_ssn,
       u.fecha_hora_utc                 AS fecha_hora_usgs,
       s.fecha_corregida,
       t.anio,
       r.etiqueta                       AS rango_magnitud,
       s.magnitud                       AS mag_ssn,
       u.magnitud                       AS mag_usgs,
       u.tipo_magnitud                  AS tipo_mag_usgs,
       s.profundidad_km                 AS prof_ssn,
       u.profundidad_km                 AS prof_usgs,
       s.latitud  AS lat_ssn,  s.longitud AS lon_ssn,
       u.latitud  AS lat_usgs, u.longitud AS lon_usgs,
       s.lugar                          AS referencia_ssn,
       s.estado                         AS estado_ssn,
       u.lugar                          AS lugar_usgs,
       u.id_externo                     AS id_usgs,
       s.id_externo                     AS id_ssn,
       f.independiente,
       u.red_localizacion, u.red_magnitud,
       f.delta_segundos, f.distancia_km, f.delta_magnitud, f.delta_profundidad_km, f.puntaje
FROM dw.fact_cruce_sismo f
JOIN dw.dim_sismo s           ON s.id_sismo = f.id_sismo_ssn
JOIN dw.dim_sismo u           ON u.id_sismo = f.id_sismo_usgs
JOIN dw.dim_tiempo t          ON t.id_tiempo = f.id_tiempo
JOIN dw.dim_rango_magnitud r  ON r.id_rango = f.id_rango
WHERE f.resultado = 'ambas';

-- ¿Cuántos sismos coinciden y cuántos aparecen en una sola fuente?
CREATE OR REPLACE VIEW dw.v_resumen_resultado AS
SELECT resultado, count(*) AS eventos
FROM dw.fact_cruce_sismo
WHERE variante = 'corregida'
GROUP BY resultado;

-- ¿Qué tan parecidos son los pares? (epicentro, magnitud, hora, profundidad)
-- Separado por origen de la solución USGS: las que aportó el SSN (UNM) coinciden
-- casi por construcción; la validación real es la de las independientes.
CREATE OR REPLACE VIEW dw.v_estadistica_pares AS
SELECT CASE WHEN GROUPING(independiente) = 1 THEN 'todas'
            WHEN independiente THEN 'independiente'
            ELSE 'aportada_por_ssn' END                                     AS origen_usgs,
       count(*)                                                             AS pares,
       round(avg(distancia_km)::numeric, 1)                                 AS distancia_media_km,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY distancia_km))::numeric, 1) AS distancia_mediana_km,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY distancia_km))::numeric, 1) AS distancia_p90_km,
       round(avg(delta_magnitud)::numeric, 2)                               AS delta_mag_media,
       round(stddev_samp(delta_magnitud)::numeric, 2)                       AS delta_mag_desv,
       round(avg(abs(delta_magnitud))::numeric, 2)                          AS delta_mag_abs_media,
       round(avg(abs(delta_segundos))::numeric, 1)                          AS delta_seg_abs_media,
       round(avg(delta_profundidad_km)::numeric, 1)                         AS delta_prof_media_km,
       round(100.0 * avg((abs(delta_magnitud) <= 0.3)::int), 1)             AS pct_mag_dentro_0_3
FROM dw.fact_cruce_sismo
WHERE variante = 'corregida' AND resultado = 'ambas'
GROUP BY GROUPING SETS ((independiente), ());

-- ¿A partir de qué magnitud los dos catálogos coinciden?
-- (el rango se toma de la magnitud SSN cuando existe; si no, de la USGS)
CREATE OR REPLACE VIEW dw.v_cobertura_rango AS
SELECT r.id_rango,
       r.etiqueta,
       count(f.id_cruce) FILTER (WHERE f.resultado = 'ambas')     AS pares,
       count(f.id_cruce) FILTER (WHERE f.resultado = 'solo_ssn')  AS solo_ssn,
       count(f.id_cruce) FILTER (WHERE f.resultado = 'solo_usgs') AS solo_usgs,
       -- Bajo la magnitud mínima de análisis del SSN no se guardan sus sismos sin
       -- pareja, así que ahí el porcentaje no significa nada y se deja en NULL.
       CASE WHEN r.mag_min >= coalesce(etl.parametro('ssn_mag_min')::numeric, 4.0) THEN
       round(100.0 * count(f.id_cruce) FILTER (WHERE f.resultado = 'ambas')
             / nullif(count(f.id_cruce) FILTER (WHERE f.resultado IN ('ambas', 'solo_ssn')), 0), 1)
       END                                                        AS pct_ssn_confirmado_por_usgs,
       round(100.0 * count(f.id_cruce) FILTER (WHERE f.resultado = 'ambas')
             / nullif(count(f.id_cruce) FILTER (WHERE f.resultado IN ('ambas', 'solo_usgs')), 0), 1)
                                                                  AS pct_usgs_encontrado_en_ssn
FROM dw.dim_rango_magnitud r
LEFT JOIN dw.fact_cruce_sismo f ON f.id_rango = r.id_rango AND f.variante = 'corregida'
GROUP BY r.id_rango, r.etiqueta, r.mag_min;

-- ¿Cómo cambia la coincidencia a lo largo del tiempo?
CREATE OR REPLACE VIEW dw.v_serie_anual AS
SELECT t.anio,
       count(*) FILTER (WHERE f.resultado IN ('ambas', 'solo_ssn'))                       AS eventos_ssn,
       count(*) FILTER (WHERE f.resultado IN ('ambas', 'solo_usgs', 'fuera_de_cobertura')) AS eventos_usgs,
       count(*) FILTER (WHERE f.resultado = 'ambas')                                     AS pares
FROM dw.fact_cruce_sismo f
JOIN dw.dim_tiempo t ON t.id_tiempo = f.id_tiempo
WHERE f.variante = 'corregida'
GROUP BY t.anio;

-- Diferencia de magnitud según la escala que reporta el USGS
CREATE OR REPLACE VIEW dw.v_delta_magnitud_tipo AS
SELECT coalesce(tipo_mag_usgs, '(sin tipo)')                                    AS tipo_mag_usgs,
       count(*)                                                                AS pares,
       round(avg(delta_magnitud)::numeric, 2)                                  AS delta_mag_media,
       round(stddev_samp(delta_magnitud)::numeric, 2)                          AS delta_mag_desv,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY delta_magnitud))::numeric, 2) AS delta_mag_mediana
FROM dw.v_pares
WHERE variante = 'corregida'
GROUP BY 1
HAVING count(*) >= 20;

-- Por década: ¿mejoró la concordancia con la instrumentación moderna?
CREATE OR REPLACE VIEW dw.v_concordancia_decada AS
SELECT (anio / 10) * 10                                AS decada,
       count(*)                                        AS pares,
       round(avg(distancia_km)::numeric, 1)            AS distancia_media_km,
       round(avg(abs(delta_magnitud))::numeric, 2)     AS delta_mag_abs_media,
       round(avg(abs(delta_segundos))::numeric, 1)     AS delta_seg_abs_media
FROM dw.v_pares
WHERE variante = 'corregida'
GROUP BY 1;

-- Concordancia por estado (según la referencia del SSN), sismos M ≥ 4.5
CREATE OR REPLACE VIEW dw.v_concordancia_estado AS
SELECT coalesce(s.estado, '(sin estado / mar)')                               AS estado,
       count(*)                                                              AS sismos_ssn,
       count(*) FILTER (WHERE f.resultado = 'ambas')                         AS confirmados_usgs,
       round(100.0 * count(*) FILTER (WHERE f.resultado = 'ambas') / count(*), 1) AS pct_confirmado,
       round(avg(f.distancia_km)::numeric, 1)                                AS distancia_media_km,
       round(avg(f.delta_magnitud)::numeric, 2)                              AS delta_mag_media
FROM dw.fact_cruce_sismo f
JOIN dw.dim_sismo s ON s.id_sismo = f.id_sismo_ssn
WHERE f.variante = 'corregida'
  AND f.resultado IN ('ambas', 'solo_ssn')
  AND s.magnitud >= 4.5
GROUP BY 1;

-- Sismos que el USGS registra y el SSN del DW no
CREATE OR REPLACE VIEW dw.v_solo_usgs AS
SELECT u.fecha_hora_utc, u.magnitud, u.tipo_magnitud, u.profundidad_km,
       u.latitud, u.longitud, u.lugar, u.id_externo AS id_usgs, u.estatus_revision
FROM dw.fact_cruce_sismo f
JOIN dw.dim_sismo u ON u.id_sismo = f.id_sismo_usgs
WHERE f.variante = 'corregida' AND f.resultado = 'solo_usgs';

-- Sismos que el SSN registra y el USGS no
CREATE OR REPLACE VIEW dw.v_solo_ssn AS
SELECT s.fecha_hora_utc, s.fecha_hora_dw, s.magnitud, s.profundidad_km,
       s.latitud, s.longitud, s.lugar AS referencia, s.estado, s.id_externo AS id_ssn
FROM dw.fact_cruce_sismo f
JOIN dw.dim_sismo s ON s.id_sismo = f.id_sismo_ssn
WHERE f.variante = 'corregida' AND f.resultado = 'solo_ssn';

-- Pares para revisar a mano: magnitudes o epicentros muy distintos
CREATE OR REPLACE VIEW dw.v_discrepancias AS
SELECT *
FROM dw.v_pares
WHERE variante = 'corregida'
  AND (abs(delta_magnitud) >= 0.5 OR distancia_km >= 75);

-- ---------------------------------------------------------------------
--  DIAGNÓSTICO del DW del paper: fecha local + hora UTC
-- ---------------------------------------------------------------------

-- Por hora UTC del sismo (M ≥ 4.5): % del SSN que el USGS confirma con la
-- fecha tal como está en el DW y con la fecha corregida. Con la fecha del DW
-- la tasa se desploma entre las 00:00 y las 05:59 UTC (de 18:00 a 23:59 en el
-- centro del país), justo cuando la fecha local es la del día anterior.
CREATE OR REPLACE VIEW dw.v_diagnostico_hora AS
SELECT f.variante,
       extract(hour FROM s.fecha_hora_utc AT TIME ZONE 'UTC')::int          AS hora_utc,
       count(*)                                                             AS sismos_ssn,
       count(*) FILTER (WHERE f.resultado = 'ambas')                        AS emparejados,
       round(100.0 * count(*) FILTER (WHERE f.resultado = 'ambas') / count(*), 1) AS pct_emparejado
FROM dw.fact_cruce_sismo f
JOIN dw.dim_sismo s ON s.id_sismo = f.id_sismo_ssn
WHERE f.resultado IN ('ambas', 'solo_ssn')
  AND s.magnitud >= 4.5
GROUP BY 1, 2;

-- Resultado del cruce en cada variante
CREATE OR REPLACE VIEW dw.v_resumen_variantes AS
SELECT variante, resultado, count(*) AS eventos
FROM dw.fact_cruce_sismo
GROUP BY variante, resultado;

-- Cuántos sismos del DW tienen la fecha recorrida un día
CREATE OR REPLACE VIEW dw.v_fechas_corregidas AS
SELECT count(*)                                           AS sismos_ssn,
       count(*) FILTER (WHERE fecha_corregida)            AS con_fecha_corregida,
       round(100.0 * avg(fecha_corregida::int), 1)        AS pct_corregidos
FROM dw.dim_sismo
WHERE id_fuente = 1;
