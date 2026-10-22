-- =====================================================================
--  03 · Vistas analíticas
-- =====================================================================

-- Colonias del 1er semestre de 2019: puntaje del paper contra los reportes
-- de "Falta de agua" del mismo periodo (el cruce más directo posible)
CREATE OR REPLACE VIEW dw.v_atipicidad_2019 AS
SELECT *
FROM dw.fn_puntajes('Falta de agua', DATE '2019-01-01', DATE '2019-06-30');

-- Métricas de la evaluación para ese mismo cruce
CREATE OR REPLACE VIEW dw.v_evaluacion_2019 AS
SELECT *
FROM dw.fn_evaluacion('Falta de agua', DATE '2019-01-01', DATE '2019-06-30');

-- Reportes por mes y tipo (agua potable)
CREATE OR REPLACE VIEW dw.v_reportes_mes AS
SELECT date_trunc('month', t.fecha)::date AS mes,
       tr.reporte,
       count(*)                             AS reportes
FROM dw.fact_reporte_agua r
JOIN dw.dim_tiempo t        ON t.id_tiempo = r.id_tiempo
JOIN dw.dim_tipo_reporte tr ON tr.id_tipo = r.id_tipo
WHERE tr.es_agua_potable
GROUP BY 1, 2;

-- ¿Cómo se ubicó cada reporte en una colonia?
CREATE OR REPLACE VIEW dw.v_ubicacion_reportes AS
SELECT recurso,
       coalesce(metodo_ubicacion, 'sin ubicar')                       AS metodo,
       count(*)                                                       AS reportes,
       round(100.0 * count(*) / sum(count(*)) OVER (PARTITION BY recurso), 1) AS pct,
       round(avg(distancia_m)::numeric)                               AS distancia_media_m
FROM dw.fact_reporte_agua
GROUP BY recurso, metodo_ubicacion;

-- Consumo por alcaldía y bimestre, doméstico contra no doméstico
-- (una de las preguntas del paper)
CREATE OR REPLACE VIEW dw.v_consumo_alcaldia AS
SELECT u.alcaldia,
       t.bimestre,
       round(sum(f.consumo_total))        AS consumo_total_m3,
       round(sum(f.consumo_total_dom))    AS consumo_domestico_m3,
       round(sum(f.consumo_total_no_dom)) AS consumo_no_domestico_m3,
       round(100.0 * sum(f.consumo_total_dom) / nullif(sum(f.consumo_total), 0), 1) AS pct_domestico
FROM dw.fact_consumo_agua f
JOIN dw.dim_ubicacion u ON u.id_ubicacion = f.id_ubicacion
JOIN dw.dim_tiempo t    ON t.id_tiempo = f.id_tiempo
GROUP BY u.alcaldia, t.bimestre;

-- Reportes de agua potable por colonia y año (para mapas y comparaciones)
CREATE OR REPLACE VIEW dw.v_reportes_colonia_anio AS
SELECT u.alcaldia, u.colonia, t.anio, tr.reporte, count(*) AS reportes,
       round(count(*)::numeric / greatest(u.manzanas, 1), 3) AS reportes_por_manzana
FROM dw.fact_reporte_agua r
JOIN dw.dim_ubicacion u     ON u.id_ubicacion = r.id_ubicacion
JOIN dw.dim_tiempo t        ON t.id_tiempo = r.id_tiempo
JOIN dw.dim_tipo_reporte tr ON tr.id_tipo = r.id_tipo
WHERE tr.es_agua_potable
GROUP BY u.alcaldia, u.colonia, u.manzanas, t.anio, tr.reporte;
