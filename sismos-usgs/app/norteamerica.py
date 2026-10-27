"""Catálogo regional USGS 2020–2025 y asignación territorial oficial US/CA.

Independiente del emparejamiento SSN: no lo reemplaza ni recalcula impactos.
"""
import argparse
import csv
import datetime as dt
import io
import json
import math
import zipfile
from collections import Counter

import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform
from shapely import make_valid
from shapely.prepared import prep

from comun import DIR_DATOS, conectar, descargar, nueva_sesion, log
from demografia import sha256

DIRECTORIO = DIR_DATOS / 'norteamerica'
FDSN = 'https://earthquake.usgs.gov/fdsnws/event/1'
DOI = '10.5066/F7MS3QZH'
LIMITES = {
    'US': {'archivo':'cb_2024_us_state_20m.zip',
           'url':'https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_20m.zip',
           'institucion':'U.S. Census Bureau',
           'pagina':'https://www.census.gov/geographies/mapping-files/2024/geo/carto-boundary-file.html'},
    'CA': {'archivo':'provincias_canada.geojson',
           'url':'https://geoportal.gov.mb.ca/api/download/v1/items/e46938cbb3e84c3688d03b8622d8f212/geojson?layers=0',
           'institucion':'Government of Manitoba, catálogo Open Government Canada',
           'pagina':'https://open.canada.ca/data/dataset/85efc01b-163f-ebba-2378-c43eadfb3b3f'},
}
# Equivalencia de abreviaturas postales con códigos de provincia de Statistics Canada.
CODIGOS_CA = dict(NL='10',PE='11',NS='12',NB='13',QC='24',ON='35',MB='46',SK='47',AB='48',BC='59',YT='60',NT='61',NU='62')
VENTANAS = [('principal',14,84,-180,-50), ('aleutianas_este',50,73,170,180)]


def regiones():
    resultado=[]
    for pais,fuente in LIMITES.items():
        path=descargar(fuente['url'], DIRECTORIO / fuente['archivo'])
        if pais=='US':
            with zipfile.ZipFile(path) as z:
                base=next(n[:-4] for n in z.namelist() if n.endswith('.shp'))
                crs=CRS.from_wkt(z.read(base+'.prj').decode())
                proyeccion=Transformer.from_crs(crs,4326,always_xy=True).transform
                lector=shapefile.Reader(shp=io.BytesIO(z.read(base+'.shp')),
                                       shx=io.BytesIO(z.read(base+'.shx')),
                                       dbf=io.BytesIO(z.read(base+'.dbf')),encoding='utf-8')
                for r in lector.iterShapeRecords():
                    p=r.record.as_dict()
                    if p['STATEFP'] in ('60','66','69','72','78'):
                        continue
                    geometria=make_valid(transform(proyeccion,shape(r.shape.__geo_interface__)))
                    resultado.append((pais,p['STATEFP'],prep(geometria),geometria.bounds))
        else:
            geo=json.loads(path.read_text(encoding='utf-8-sig'))
            crs=geo.get('crs',{}).get('properties',{}).get('name','EPSG:4326')
            proyeccion=Transformer.from_crs(crs,4326,always_xy=True).transform
            for r in geo['features']:
                abrev=r['properties']['postal']
                if abrev=='CA':  # agregado nacional: no duplicar provincias
                    continue
                codigo=CODIGOS_CA[abrev]
                geometria=make_valid(transform(proyeccion,shape(r['geometry'])))
                resultado.append((pais,codigo,prep(geometria),geometria.bounds))
    if Counter(p for p,_,_,_ in resultado) != {'US':51,'CA':13}:
        raise ValueError('Los límites no contienen 51 estados/DC y 13 provincias/territorios')
    return resultado


def asignar(lat,lon,poligonos):
    punto=Point(lon,lat)
    coincidencias=[(p,c) for p,c,g,(x0,y0,x1,y1) in poligonos
                   if x0<=lon<=x1 and y0<=lat<=y1 and g.covers(punto)]
    return coincidencias[0] if len(coincidencias)==1 else (None,None)


def extraer(actualizar=False):
    DIRECTORIO.mkdir(parents=True,exist_ok=True)
    manifiesto=DIRECTORIO/'procedencia.json'
    if manifiesto.exists() and not actualizar:
        meta=json.loads(manifiesto.read_text(encoding='utf-8'))
        for f in meta['archivos']:
            if sha256(DIRECTORIO/f['archivo']) != f['sha256']:
                raise ValueError(f"Archivo alterado: {f['archivo']}")
        return meta
    archivos=[]
    sesion=nueva_sesion()

    def bloque(ini,fin,ventana):
        nombre,lat0,lat1,lon0,lon1=ventana
        params=dict(format='csv',starttime=ini.isoformat(),
                    endtime=(fin-dt.timedelta(milliseconds=1)).isoformat(),
                    minlatitude=lat0,maxlatitude=lat1,minlongitude=lon0,maxlongitude=lon1,
                    minmagnitude=3.5,eventtype='earthquake',orderby='time-asc',limit=20000)
        destino=DIRECTORIO/f'usgs_{nombre}_{ini:%Y%m%d}_{fin:%Y%m%d}_m3.5.csv'
        descargar(FDSN+'/query',destino,forzar=actualizar,sesion=sesion,params=params)
        with destino.open(encoding='utf-8-sig') as f:
            if not f.readline().startswith('time,latitude,longitude,depth,mag,'):
                raise ValueError(f'La API no devolvió CSV de eventos: {destino.name}')
        with destino.open(encoding='utf-8-sig',newline='') as f:
            n=sum(1 for _ in csv.DictReader(f))
        if n>=20000:
            if fin-ini<=dt.timedelta(days=1):
                raise ValueError('Demasiados eventos en un día; reducir periodo')
            medio=ini+(fin-ini)/2
            bloque(ini,medio,ventana)
            bloque(medio,fin,ventana)
            return
        archivos.append(dict(archivo=destino.name,sha256=sha256(destino),registros=n,
                             url=FDSN+'/query',parametros=params))
        log.info('%s: %s eventos',destino.name,n)

    for anio in range(2020,2026):
        for ventana in VENTANAS:
            bloque(dt.datetime(anio,1,1),dt.datetime(anio+1,1,1),ventana)
    for pais,fuente in LIMITES.items():
        p=descargar(fuente['url'],DIRECTORIO/fuente['archivo'])
        archivos.append(dict(archivo=p.name,sha256=sha256(p),url=fuente['url'],pais=pais))
    meta=dict(extraido_utc=dt.datetime.now(dt.timezone.utc).isoformat(),institucion='U.S. Geological Survey',
              doi=DOI,api=FDSN,periodo='2020-01-01 / 2026-01-01 (fin excluido)',magnitud_minima=3.5,
              ventanas=VENTANAS,limites=LIMITES,archivos=archivos,
              alcance='Dos ventanas regionales; país/provincia solo si el punto cae en un polígono oficial. Sin asignación no significa océano necesariamente.')
    manifiesto.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return meta


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
    meta=extraer(actualizar)
    poligonos=regiones()
    eventos={}
    for archivo in meta['archivos']:
        if 'registros' not in archivo:
            continue
        with (DIRECTORIO/archivo['archivo']).open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                fecha=dt.datetime.fromisoformat(r['time'].replace('Z','+00:00'))
                lat,lon,mag,prof=map(float,[r['latitude'],r['longitude'],r['mag'],r['depth']])
                if not all(map(math.isfinite,[lat,lon,mag,prof])) or not(-90<=lat<=90 and -180<=lon<=180) or mag<3.5 or not 2020<=fecha.year<=2025 or r['type']!='earthquake':
                    raise ValueError(f"Evento inválido: {r['id']}")
                if r['id'] in eventos:
                    raise ValueError(f"Evento repetido entre bloques: {r['id']}")
                pais,codigo=asignar(lat,lon,poligonos)
                eventos[r['id']]=(r,fecha,lat,lon,mag,prof,pais,codigo)
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
