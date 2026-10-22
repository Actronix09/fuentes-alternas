-- =====================================================================
--  Transformación 2 · hechos
--  (la ejecuta etl.py; la distancia máxima llega en etl.distancia_max_m)
-- =====================================================================

-- Hecho del paper: consumo (mismo cruce que etl/3_fact.sql del repositorio original)
INSERT INTO dw.fact_consumo_agua (id_tiempo, id_ubicacion, id_indice_des,
        consumo_total_mixto, consumo_prom_dom, consumo_total_dom, consumo_prom_mixto,
        consumo_total, consumo_prom, consumo_prom_no_dom, consumo_total_no_dom)
SELECT to_char(c.fecha_referencia, 'YYYYMMDD')::int,
       u.id_ubicacion,
       i.id_indice_des,
       c.consumo_total_mixto, c.consumo_prom_dom, c.consumo_total_dom, c.consumo_prom_mixto,
       c.consumo_total, c.consumo_prom, c.consumo_prom_no_dom, c.consumo_total_no_dom
FROM staging.consumo c
JOIN dw.dim_ubicacion u  ON u.alcaldia_norm = c.alcaldia_norm AND u.colonia_norm = c.colonia_norm
JOIN dw.dim_indice_des i ON i.indice_des = c.indice_des;

-- ---------------------------------------------------------------------
--  Ubicación de cada reporte en una colonia del catálogo del consumo
-- ---------------------------------------------------------------------

-- 1) Por nombre: alcaldía y colonia normalizadas iguales
CREATE TEMP TABLE tmp_ubicacion ON COMMIT DROP AS
SELECT r.id_staging, u.id_ubicacion, 'nombre'::text AS metodo, NULL::float8 AS distancia_m
FROM staging.reporte_agua r
JOIN dw.dim_ubicacion u ON u.alcaldia_norm = r.alcaldia_norm AND u.colonia_norm = r.colonia_norm;

CREATE UNIQUE INDEX ON tmp_ubicacion (id_staging);

-- 2) Por cercanía: la manzana más próxima (≤ distancia máxima). La rejilla de
--    0.01° limita la búsqueda a la celda del reporte y sus 8 vecinas, así que
--    cada reporte se compara con unas decenas de manzanas y no con las 23 mil.
INSERT INTO tmp_ubicacion (id_staging, id_ubicacion, metodo, distancia_m)
SELECT DISTINCT ON (r.id_staging)
       r.id_staging, m.id_ubicacion, 'manzana_cercana', d.metros
FROM staging.reporte_agua r
CROSS JOIN (VALUES (-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 0), (0, 1), (1, -1), (1, 0), (1, 1)) AS v(dx, dy)
JOIN dw.manzana m
  ON m.celda_x = floor(r.longitud / 0.01)::int + v.dx
 AND m.celda_y = floor(r.latitud / 0.01)::int + v.dy
CROSS JOIN LATERAL (SELECT dw.fn_distancia_m(r.latitud, r.longitud, m.latitud, m.longitud) AS metros) d
WHERE r.latitud IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM tmp_ubicacion t WHERE t.id_staging = r.id_staging)
  AND d.metros <= current_setting('etl.distancia_max_m')::float8
ORDER BY r.id_staging, d.metros;

-- Hecho nuevo: un renglón por reporte
INSERT INTO dw.fact_reporte_agua (recurso, folio, id_tiempo, id_ubicacion, id_tipo, id_medio,
                                  metodo_ubicacion, distancia_m, latitud, longitud)
SELECT r.recurso,
       r.folio,
       to_char(r.fecha, 'YYYYMMDD')::int,
       t.id_ubicacion,
       tr.id_tipo,
       m.id_medio,
       t.metodo,
       round(t.distancia_m::numeric, 1),
       r.latitud,
       r.longitud
FROM staging.reporte_agua r
JOIN dw.dim_tipo_reporte tr    ON tr.clasificacion = r.clasificacion AND tr.reporte = r.reporte
JOIN dw.dim_medio_recepcion m  ON m.medio = r.medio
LEFT JOIN tmp_ubicacion t      ON t.id_staging = r.id_staging;

ANALYZE dw.fact_consumo_agua;
ANALYZE dw.fact_reporte_agua;
