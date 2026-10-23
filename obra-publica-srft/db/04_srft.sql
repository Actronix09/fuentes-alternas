-- Extensión aditiva del warehouse del artículo. No se generan supervisores,
-- personas, auditorías ni contratos que la fuente oficial no publique.
CREATE SCHEMA IF NOT EXISTS etl;
CREATE TABLE IF NOT EXISTS etl.ejecucion (
 id_ejecucion serial PRIMARY KEY, inicio timestamptz DEFAULT now(), fin timestamptz,
 estado text DEFAULT 'en_proceso', parametros jsonb DEFAULT '{}', mensaje text);
CREATE TABLE IF NOT EXISTS etl.bitacora (
 id_bitacora bigserial PRIMARY KEY, id_ejecucion integer REFERENCES etl.ejecucion,
 momento timestamptz DEFAULT now(), fase text, paso text, registros bigint, detalle text);
CREATE SCHEMA IF NOT EXISTS staging;
CREATE TABLE IF NOT EXISTS staging.srft (
 folio text PRIMARY KEY, ciclo integer NOT NULL, periodo integer NOT NULL,
 datos jsonb NOT NULL, georreferencias jsonb NOT NULL, metas jsonb NOT NULL,
 contratos jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS warehouse.fact_srft (
 folio text PRIMARY KEY,
 obra_key bigint NOT NULL REFERENCES warehouse.dim_obra,
 tiempo_key integer REFERENCES warehouse.dim_tiempo,
 ciclo integer NOT NULL, periodo integer NOT NULL,
 clasificacion text, municipio text, aprobado numeric(18,2),
 recaudado numeric(18,2), comprometido numeric(18,2), devengado numeric(18,2),
 ejercido numeric(18,2), pagado numeric(18,2), estatus text,
 fecha_inicio date, fecha_estimada_termino date,
 latitud numeric, longitud numeric, localidad text,
 avance_fisico_pct numeric, fuente_url text NOT NULL, sha256 text NOT NULL,
 cargado_en timestamptz NOT NULL DEFAULT now());
CREATE OR REPLACE VIEW warehouse.v_srft_obras AS
 SELECT f.*, o.nombre_obra, o.descripcion
 FROM warehouse.fact_srft f JOIN warehouse.dim_obra o USING(obra_key);
