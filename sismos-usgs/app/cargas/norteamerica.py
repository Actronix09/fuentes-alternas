"""Carga del catálogo regional USGS 2020–2025 con asignación territorial oficial US/CA.

Une las fuentes usgs_norteamerica (eventos) y limites (polígonos) y enlaza cada
evento con dim_region_demografia, así que se carga después de cargas.demografia.
Independiente del emparejamiento SSN: no lo reemplaza ni recalcula impactos.
"""
import argparse
import json
from collections import Counter

from comun import conectar, log
from fuentes import limites, usgs_norteamerica


DDL='''
CREATE TABLE IF NOT EXISTS staging.usgs_norteamerica (
    id_usgs text PRIMARY KEY, datos jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS public.fact_sismo_norteamerica (
    id_usgs text PRIMARY KEY, fecha_hora_utc timestamptz NOT NULL,
    latitud double precision NOT NULL CHECK(latitud BETWEEN -90 AND 90),
    longitud double precision NOT NULL CHECK(longitud BETWEEN -180 AND 180),
    profundidad_km double precision NOT NULL, magnitud double precision NOT NULL,
    tipo_magnitud text NOT NULL, lugar text NOT NULL, red text NOT NULL, estado text NOT NULL,
    pais text, codigo text, CHECK((pais IS NULL)=(codigo IS NULL)),
    FOREIGN KEY(pais,codigo) REFERENCES public.dim_region_demografia);
CREATE INDEX IF NOT EXISTS idx_sismo_na_fecha ON public.fact_sismo_norteamerica(fecha_hora_utc);
CREATE INDEX IF NOT EXISTS idx_sismo_na_pais ON public.fact_sismo_norteamerica(pais,codigo);
CREATE TABLE IF NOT EXISTS etl.norteamerica_carga (
    id bigserial PRIMARY KEY, cargado_utc timestamptz NOT NULL DEFAULT now(),
    eventos integer NOT NULL, procedencia jsonb NOT NULL);
CREATE OR REPLACE VIEW public.v_sismo_norteamerica AS
SELECT e.*, r.nombre AS region,
       p.poblacion AS poblacion_region, p.fecha_referencia AS fecha_poblacion,
       'https://earthquake.usgs.gov/earthquakes/eventpage/'||e.id_usgs AS url_fuente
FROM public.fact_sismo_norteamerica e
LEFT JOIN public.dim_region_demografia r USING(pais,codigo)
LEFT JOIN public.fact_poblacion_demografia p ON p.pais=e.pais AND p.codigo=e.codigo
    AND p.fecha_referencia=make_date(extract(year FROM e.fecha_hora_utc AT TIME ZONE 'UTC')::integer,7,1);
COMMENT ON VIEW public.v_sismo_norteamerica IS
    'Población regional del año del evento, no afectados. No sumar población por evento.';
'''


def ejecutar(actualizar=False):
    meta=usgs_norteamerica.extraer(actualizar)
    leidos=usgs_norteamerica.validar(meta)
    meta={**meta,'limites':limites.extraer(actualizar)}
    poligonos=limites.regiones()
    eventos={}
    for ident,(r,fecha,lat,lon,mag,prof) in leidos.items():
        pais,codigo=limites.asignar(lat,lon,poligonos)
        eventos[ident]=(r,fecha,lat,lon,mag,prof,pais,codigo)
    with conectar() as conn:
        conn.execute(DDL)
        # Sustituye solo este catálogo acotado, en una transacción; no toca SSN ni cruce.
        conn.execute('DELETE FROM public.fact_sismo_norteamerica')
        conn.execute('DELETE FROM staging.usgs_norteamerica')
        with conn.cursor() as cur:
            with cur.copy('COPY staging.usgs_norteamerica(id_usgs,datos) FROM STDIN') as copia:
                for ident,(r,*_) in eventos.items():
                    copia.write_row((ident,json.dumps(r)))
            with cur.copy('COPY public.fact_sismo_norteamerica FROM STDIN') as copia:
                for ident,(r,fecha,lat,lon,mag,prof,pais,codigo) in eventos.items():
                    copia.write_row((ident,fecha,lat,lon,prof,mag,r['magType'],r['place'],r['net'],r['status'],pais,codigo))
        conn.execute('INSERT INTO etl.norteamerica_carga(eventos,procedencia) VALUES(%s,%s::jsonb)',
                     [len(eventos),json.dumps(meta)])
    resumen=Counter(pais or 'SIN_ASIGNAR' for _,_,_,_,_,_,pais,_ in eventos.values())
    log.info('Catálogo regional cargado: %s',dict(resumen))
    return dict(resumen)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--descargar',action='store_true')
    args=parser.parse_args()
    print(json.dumps(ejecutar(args.descargar)))
