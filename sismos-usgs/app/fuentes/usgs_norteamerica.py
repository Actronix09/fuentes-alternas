"""Fuente USGS ComCat regional de Norteamérica, 2020–2025, magnitud ≥ 3.5.

Independiente del emparejamiento SSN: no lo reemplaza ni recalcula impactos.
Archivos: datos/usgs/norteamerica/<ventana>/usgs_<ventana>_AAAAMMDD_AAAAMMDD_m3.5.csv,
con su SHA-256 en datos/usgs/norteamerica/procedencia.json.
"""
import argparse
import csv
import datetime as dt
import json
import math

from comun import DIR_DATOS, descargar, log, nueva_sesion, sha256

DIRECTORIO = DIR_DATOS / 'usgs' / 'norteamerica'
FDSN = 'https://earthquake.usgs.gov/fdsnws/event/1'
DOI = '10.5066/F7MS3QZH'
VENTANAS = [('principal',14,84,-180,-50), ('aleutianas_este',50,73,170,180)]


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
        destino=DIRECTORIO/nombre/f'usgs_{nombre}_{ini:%Y%m%d}_{fin:%Y%m%d}_m3.5.csv'
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
        archivos.append(dict(archivo=destino.relative_to(DIRECTORIO).as_posix(),sha256=sha256(destino),
                             registros=n,url=FDSN+'/query',parametros=params))
        log.info('%s: %s eventos',destino.name,n)

    for anio in range(2020,2026):
        for ventana in VENTANAS:
            bloque(dt.datetime(anio,1,1),dt.datetime(anio+1,1,1),ventana)
    meta=dict(extraido_utc=dt.datetime.now(dt.timezone.utc).isoformat(),institucion='U.S. Geological Survey',
              doi=DOI,api=FDSN,periodo='2020-01-01 / 2026-01-01 (fin excluido)',magnitud_minima=3.5,
              ventanas=VENTANAS,archivos=archivos,
              alcance='Dos ventanas regionales. País/provincia se asigna al cargar, con los límites de datos/limites.')
    manifiesto.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return meta


def validar(meta):
    """{id_usgs: (fila, fecha, lat, lon, mag, prof)}; falla ante cualquier evento inválido o repetido."""
    eventos={}
    for archivo in meta['archivos']:
        with (DIRECTORIO/archivo['archivo']).open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                fecha=dt.datetime.fromisoformat(r['time'].replace('Z','+00:00'))
                lat,lon,mag,prof=map(float,[r['latitude'],r['longitude'],r['mag'],r['depth']])
                if not all(map(math.isfinite,[lat,lon,mag,prof])) or not(-90<=lat<=90 and -180<=lon<=180) or mag<3.5 or not 2020<=fecha.year<=2025 or r['type']!='earthquake':
                    raise ValueError(f"Evento inválido: {r['id']}")
                if r['id'] in eventos:
                    raise ValueError(f"Evento repetido entre bloques: {r['id']}")
                eventos[r['id']]=(r,fecha,lat,lon,mag,prof)
    return eventos


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--descargar',action='store_true')
    args=parser.parse_args()
    print(f'{len(validar(extraer(args.descargar))):,} eventos regionales válidos')
