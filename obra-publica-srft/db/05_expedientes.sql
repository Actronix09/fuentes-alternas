-- Expedientes importados: admitir desconocidos explícitos sin crear personas.
-- Se conservan los requisitos del registro manual mediante CHECK condicional.
ALTER TABLE public.obra ADD COLUMN IF NOT EXISTS origen_datos text NOT NULL DEFAULT 'OPERATIVO';
ALTER TABLE public.obra ADD COLUMN IF NOT EXISTS folio_fuente text;
ALTER TABLE public.obra ADD COLUMN IF NOT EXISTS fuente_url text;
ALTER TABLE public.obra ADD COLUMN IF NOT EXISTS estatus_fuente text;
ALTER TABLE public.obra ALTER COLUMN codigo_supervisor DROP NOT NULL;
ALTER TABLE public.obra ALTER COLUMN id_constructora DROP NOT NULL;
ALTER TABLE public.obra ALTER COLUMN id_region DROP NOT NULL;
ALTER TABLE public.obra ALTER COLUMN beneficiarios DROP NOT NULL;
ALTER TABLE public.region ALTER COLUMN barrio DROP NOT NULL;
ALTER TABLE warehouse.dim_region ALTER COLUMN barrio DROP NOT NULL;
ALTER TABLE public.constructora ALTER COLUMN tipo_ejecutor DROP NOT NULL;
ALTER TABLE warehouse.dim_constructora ALTER COLUMN tipo_ejecutor DROP NOT NULL;
ALTER TABLE public.presupuesto_obra ADD COLUMN IF NOT EXISTS origen_datos text NOT NULL DEFAULT 'OPERATIVO';
ALTER TABLE public.presupuesto_obra ALTER COLUMN id_proyectista DROP NOT NULL;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='obra_requisitos_origen') THEN
  ALTER TABLE public.obra ADD CONSTRAINT obra_requisitos_origen CHECK (
   (origen_datos='SHCP_SRFT' AND folio_fuente IS NOT NULL AND fuente_url IS NOT NULL)
   OR (origen_datos='OPERATIVO' AND codigo_supervisor IS NOT NULL
       AND id_constructora IS NOT NULL AND id_region IS NOT NULL AND beneficiarios IS NOT NULL));
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='presupuesto_requisitos_origen') THEN
  ALTER TABLE public.presupuesto_obra ADD CONSTRAINT presupuesto_requisitos_origen CHECK (
   origen_datos='SHCP_SRFT' OR (origen_datos='OPERATIVO' AND id_proyectista IS NOT NULL));
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_constraint WHERE conname='region_barrio_origen') THEN
  ALTER TABLE public.region ADD CONSTRAINT region_barrio_origen CHECK (
   id_region LIKE 'SRFT:%' OR barrio IS NOT NULL);
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS public.expediente_srft (
 id_obra text PRIMARY KEY REFERENCES public.obra,
 folio text NOT NULL UNIQUE REFERENCES warehouse.fact_srft(folio),
 datos_originales jsonb NOT NULL, fecha_referencia date NOT NULL,
 fuente_url text NOT NULL, sha256 text NOT NULL,
 campos_no_publicados jsonb NOT NULL,
 importado_en timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS public.contrato_srft (
 id_registro text PRIMARY KEY, id_obra text NOT NULL REFERENCES public.obra,
 id_contrato_fuente text, numero_expediente text, numero_contrato text,
 contratista text, modalidad text, monto numeric, importe_modificado numeric,
 fecha_firma date, fecha_conclusion date, url_publicada text, url_documento text,
 datos_originales jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS public.financiamiento_srft (
 id_registro text PRIMARY KEY, id_obra text NOT NULL REFERENCES public.obra,
 id_fuente text REFERENCES public.fuente_presupuestaria,
 aprobado numeric, modificado numeric, datos_originales jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS public.informe_fuente_srft (
 id_obra text PRIMARY KEY REFERENCES public.obra,
 fecha_referencia date NOT NULL, avance_fisico_pct numeric,
 aprobado numeric, pagado numeric, estatus_publicado text,
 metas_originales jsonb NOT NULL, fuente_url text NOT NULL);
INSERT INTO warehouse.dim_tipo_evento(codigo_evento,nombre_evento,categoria,descripcion)
 VALUES('IMPORTACION_SHCP','Importación de expediente SHCP','administrativo',
 'Evento técnico de carga local. No acredita una creación o supervisión histórica.')
 ON CONFLICT(codigo_evento) DO NOTHING;
