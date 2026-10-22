-- =====================================================================
--  Transformación 1 · staging → dimensiones
--  (la ejecuta etl.py dentro de la misma transacción que la carga)
-- =====================================================================

TRUNCATE dw.fact_cruce_sismo, dw.dim_sismo, dw.dim_tiempo RESTART IDENTITY CASCADE;

-- Dimensión tiempo: todas las fechas en que hubo un sismo en cualquier fuente
-- (incluye las fechas tal como las trae el DW del paper, para el diagnóstico)
INSERT INTO dw.dim_tiempo (id_tiempo, fecha, anio, mes, dia, trimestre, decada)
SELECT to_char(f, 'YYYYMMDD')::int,
       f,
       extract(year FROM f),
       extract(month FROM f),
       extract(day FROM f),
       extract(quarter FROM f),
       (extract(year FROM f)::int / 10) * 10
FROM (
    SELECT (fecha_hora_utc AT TIME ZONE 'UTC')::date AS f FROM staging.ssn_evento
    UNION
    SELECT (fecha_hora_dw AT TIME ZONE 'UTC')::date FROM staging.ssn_evento
    UNION
    SELECT (time AT TIME ZONE 'UTC')::date FROM staging.usgs_evento
) fechas;

-- Dimensión sismo · fuente 1: SSN (con la marca original del DW y la corregida)
INSERT INTO dw.dim_sismo (id_fuente, id_externo, fecha_hora_utc, fecha_hora_dw, fecha_corregida,
                          id_tiempo, id_rango, magnitud, tipo_magnitud, latitud, longitud,
                          profundidad_km, lugar, estado, estatus_revision)
SELECT 1,
       s.id_sismo::text,
       s.fecha_hora_utc,
       s.fecha_hora_dw,
       s.fecha_hora_dw <> s.fecha_hora_utc,
       to_char(s.fecha_hora_utc AT TIME ZONE 'UTC', 'YYYYMMDD')::int,
       r.id_rango,
       s.magnitud,
       NULL,
       s.latitud,
       s.longitud,
       s.profundidad,
       s.referencia,
       nullif(s.nombre_estado, ''),
       NULL
FROM staging.ssn_evento s
JOIN dw.dim_rango_magnitud r ON s.magnitud >= r.mag_min AND s.magnitud < r.mag_max;

-- Dimensión sismo · fuente 2: USGS ComCat (con la red que calculó cada solución:
-- UNM = Instituto de Geofísica de la UNAM, es decir, una solución aportada por el SSN)
INSERT INTO dw.dim_sismo (id_fuente, id_externo, fecha_hora_utc, id_tiempo, id_rango,
                          magnitud, tipo_magnitud, latitud, longitud, profundidad_km,
                          lugar, estado, estatus_revision,
                          red, red_localizacion, red_magnitud, aporte_ssn)
SELECT 2,
       u.id,
       u.time,
       to_char(u.time AT TIME ZONE 'UTC', 'YYYYMMDD')::int,
       r.id_rango,
       u.mag,
       u.magtype,
       u.latitude,
       u.longitude,
       u.depth,
       u.place,
       NULL,
       u.status,
       u.net,
       u.locationsource,
       u.magsource,
       coalesce(u.locationsource, '') ILIKE '%unm%' OR coalesce(u.magsource, '') ILIKE '%unm%'
FROM staging.usgs_evento u
JOIN dw.dim_rango_magnitud r ON u.mag >= r.mag_min AND u.mag < r.mag_max;

ANALYZE dw.dim_tiempo;
ANALYZE dw.dim_sismo;
