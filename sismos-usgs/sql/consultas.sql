-- =====================================================================
--  Consultas de ejemplo · Sistema 1 (validación SSN ↔ USGS)
--  docker compose exec db psql -U sismos -d sismos_dw -f /consultas/consultas.sql
-- =====================================================================
\pset footer off
\echo '== 1. ¿Cuántos sismos coinciden y cuántos están en una sola fuente?'
SELECT * FROM dw.v_resumen_resultado ORDER BY eventos DESC;

\echo '== 2. ¿Qué tan parecidos son los pares?'
SELECT * FROM dw.v_estadistica_pares;

\echo '== 3. ¿A partir de qué magnitud los catálogos coinciden?'
SELECT etiqueta, pares, solo_ssn, solo_usgs,
       pct_ssn_confirmado_por_usgs, pct_usgs_encontrado_en_ssn
FROM dw.v_cobertura_rango ORDER BY id_rango;

\echo '== 4. ¿Mejoró la concordancia con la instrumentación moderna?'
SELECT * FROM dw.v_concordancia_decada ORDER BY decada;

\echo '== 5. Diferencia de magnitud según la escala que reporta el USGS'
SELECT * FROM dw.v_delta_magnitud_tipo ORDER BY pares DESC;

\echo '== 6. Confirmación por estado (SSN, M ≥ 4.5)'
SELECT * FROM dw.v_concordancia_estado ORDER BY sismos_ssn DESC LIMIT 15;

\echo '== 7. Los 10 sismos más fuertes que el USGS registra y el DW del SSN no'
SELECT fecha_hora_utc, magnitud, tipo_magnitud, lugar, id_usgs
FROM dw.v_solo_usgs ORDER BY magnitud DESC LIMIT 10;

\echo '== 8. Los 10 sismos más fuertes del SSN sin contraparte en el USGS'
SELECT fecha_hora_utc, magnitud, referencia, estado
FROM dw.v_solo_ssn ORDER BY magnitud DESC LIMIT 10;

\echo '== 9. Los sismos de septiembre de 2017 en ambas fuentes'
SELECT fecha_hora_ssn, mag_ssn, mag_usgs, tipo_mag_usgs,
       round(distancia_km::numeric, 1) AS km, referencia_ssn
FROM dw.v_pares
WHERE fecha_hora_ssn >= '2017-09-07' AND fecha_hora_ssn < '2017-09-21' AND mag_ssn >= 6
ORDER BY fecha_hora_ssn;

\echo '== 10. Trazabilidad: la última ejecución del ETL'
SELECT b.fase, b.paso, b.registros, b.detalle
FROM etl.bitacora b
WHERE b.id_ejecucion = (SELECT max(id_ejecucion) FROM etl.ejecucion)
ORDER BY b.id_bitacora;
