-- =====================================================================
--  Transformación 1 · staging → dimensiones
--  (la ejecuta etl.py dentro de la misma transacción que la carga)
-- =====================================================================

TRUNCATE dw.fact_reporte_agua, dw.fact_consumo_agua, dw.manzana, dw.dim_ubicacion,
         dw.dim_indice_des, dw.dim_tipo_reporte, dw.dim_medio_recepcion, dw.dim_tiempo
         RESTART IDENTITY CASCADE;

-- Dimensión tiempo: todos los días entre la primera y la última fecha de las fuentes
INSERT INTO dw.dim_tiempo (id_tiempo, fecha, anio, mes, dia, bimestre, semestre)
SELECT to_char(d, 'YYYYMMDD')::int,
       d,
       extract(year FROM d),
       extract(month FROM d),
       extract(day FROM d),
       (extract(month FROM d)::int + 1) / 2,
       CASE WHEN extract(month FROM d) <= 6 THEN 1 ELSE 2 END
FROM generate_series(
        least((SELECT min(fecha) FROM staging.reporte_agua),
              (SELECT min(fecha_referencia) FROM staging.consumo)),
        greatest((SELECT max(fecha) FROM staging.reporte_agua),
                 (SELECT max(fecha_referencia) FROM staging.consumo)),
        interval '1 day') AS g(ts),
     LATERAL (SELECT g.ts::date AS d) x;

-- Dimensión ubicación: un registro por par alcaldía–colonia del consumo, con el
-- centroide de sus manzanas y cuántas manzanas tiene
WITH nombres AS (
    SELECT alcaldia_norm, colonia_norm, min(alcaldia) AS alcaldia, min(colonia) AS colonia
    FROM staging.consumo
    GROUP BY alcaldia_norm, colonia_norm
), puntos AS (
    SELECT DISTINCT alcaldia_norm, colonia_norm, latitud, longitud
    FROM staging.consumo
    WHERE latitud IS NOT NULL
)
INSERT INTO dw.dim_ubicacion (alcaldia, colonia, alcaldia_norm, colonia_norm, latitud, longitud, manzanas)
SELECT n.alcaldia, n.colonia, n.alcaldia_norm, n.colonia_norm,
       avg(p.latitud), avg(p.longitud), count(p.latitud)
FROM nombres n
LEFT JOIN puntos p ON p.alcaldia_norm = n.alcaldia_norm AND p.colonia_norm = n.colonia_norm
GROUP BY n.alcaldia, n.colonia, n.alcaldia_norm, n.colonia_norm;

-- Puntos de manzana con su celda de 0.01° (índice espacial para ubicar reportes)
INSERT INTO dw.manzana (id_ubicacion, latitud, longitud, celda_x, celda_y)
SELECT DISTINCT ON (c.latitud, c.longitud)
       u.id_ubicacion, c.latitud, c.longitud,
       floor(c.longitud / 0.01)::int, floor(c.latitud / 0.01)::int
FROM staging.consumo c
JOIN dw.dim_ubicacion u ON u.alcaldia_norm = c.alcaldia_norm AND u.colonia_norm = c.colonia_norm
WHERE c.latitud IS NOT NULL
ORDER BY c.latitud, c.longitud, u.id_ubicacion;

-- Dimensión índice de desarrollo
INSERT INTO dw.dim_indice_des (indice_des)
SELECT DISTINCT indice_des FROM staging.consumo WHERE indice_des IS NOT NULL ORDER BY 1;

-- Dimensiones nuevas de la fuente alterna
INSERT INTO dw.dim_tipo_reporte (clasificacion, reporte, es_agua_potable)
SELECT DISTINCT clasificacion, reporte, clasificacion = 'Agua Potable'
FROM staging.reporte_agua
ORDER BY 1, 2;

INSERT INTO dw.dim_medio_recepcion (medio)
SELECT DISTINCT medio FROM staging.reporte_agua ORDER BY 1;

ANALYZE dw.dim_tiempo;
ANALYZE dw.dim_ubicacion;
ANALYZE dw.manzana;
