"""Límites oficiales de estados de EE. UU. y provincias/territorios de Canadá.

Archivos: datos/limites/us/cb_2024_us_state_20m.zip y datos/limites/ca/provincias_canada.geojson,
con su SHA-256 en datos/limites/procedencia.json.
"""
import argparse
import datetime as dt
import io
import json
import zipfile
from collections import Counter

import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform
from shapely import make_valid
from shapely.prepared import prep

from comun import DIR_DATOS, descargar, sha256

DIRECTORIO = DIR_DATOS / 'limites'
LIMITES = {
    'US': {'archivo':'us/cb_2024_us_state_20m.zip',
           'url':'https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_20m.zip',
           'institucion':'U.S. Census Bureau',
           'pagina':'https://www.census.gov/geographies/mapping-files/2024/geo/carto-boundary-file.html'},
    'CA': {'archivo':'ca/provincias_canada.geojson',
           'url':'https://geoportal.gov.mb.ca/api/download/v1/items/e46938cbb3e84c3688d03b8622d8f212/geojson?layers=0',
           'institucion':'Government of Manitoba, catálogo Open Government Canada',
           'pagina':'https://open.canada.ca/data/dataset/85efc01b-163f-ebba-2378-c43eadfb3b3f'},
}
# Equivalencia de abreviaturas postales con códigos de provincia de Statistics Canada.
CODIGOS_CA = dict(NL='10',PE='11',NS='12',NB='13',QC='24',ON='35',MB='46',SK='47',AB='48',BC='59',YT='60',NT='61',NU='62')


def extraer(actualizar=False):
    """Descarga (o toma de caché) los límites y verifica o regenera su manifiesto."""
    manifiesto=DIRECTORIO/'procedencia.json'
    if manifiesto.exists() and not actualizar:
        meta=json.loads(manifiesto.read_text(encoding='utf-8'))
        for f in meta['archivos']:
            if sha256(DIRECTORIO/f['archivo']) != f['sha256']:
                raise ValueError(f"Archivo alterado: {f['archivo']}")
        return meta
    archivos=[]
    for pais,fuente in LIMITES.items():
        p=descargar(fuente['url'],DIRECTORIO/fuente['archivo'])
        archivos.append(dict(archivo=fuente['archivo'],sha256=sha256(p),url=fuente['url'],pais=pais))
    meta=dict(extraido_utc=dt.datetime.now(dt.timezone.utc).isoformat(),fuentes=LIMITES,archivos=archivos,
              alcance='50 estados + DC (sin territorios) y 13 provincias/territorios; se omite el agregado nacional de Canadá.')
    manifiesto.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return meta


def regiones():
    """Polígonos (pais, codigo, geometría preparada, bbox) en EPSG:4326. Llamar antes a extraer()."""
    resultado=[]
    for pais,fuente in LIMITES.items():
        path=DIRECTORIO/fuente['archivo']
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


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--descargar',action='store_true')
    args=parser.parse_args()
    extraer(args.descargar)
    print(json.dumps(dict(Counter(p for p,_,_,_ in regiones()))))
