"""Verificación reproducible del catálogo regional, geografía y API.

Desde app/: python -m verificacion.norteamerica
"""
import csv
import datetime as dt
import json
import os
from collections import Counter
import requests
from comun import conectar, sha256
from fuentes import limites, usgs_norteamerica
from fuentes.limites import asignar, regiones


def main():
    pruebas=[]
    def comprobar(nombre,ok,detalle=None):
        pruebas.append(dict(prueba=nombre,ok=bool(ok),detalle=detalle))
        if not ok:
            raise AssertionError(nombre)
    raw={}
    archivos=[(fuente.DIRECTORIO,archivo) for fuente in (usgs_norteamerica,limites)
              for archivo in json.loads((fuente.DIRECTORIO/'procedencia.json').read_text(encoding='utf-8'))['archivos']]
    for directorio,archivo in archivos:
        p=directorio/archivo['archivo']
        comprobar('SHA-256 '+p.name,sha256(p)==archivo['sha256'])
        if 'registros' in archivo:
            with p.open(encoding='utf-8-sig',newline='') as f:
                filas=list(csv.DictReader(f))
            comprobar('Conteo y exclusividad de bloque '+p.name,len(filas)==archivo['registros'] and not(set(raw)&{r['id'] for r in filas}))
            raw.update({r['id']:r for r in filas})
    poligonos=regiones()
    for nombre,lat,lon,esperado in [('Denver',39.7392,-104.9903,('US','08')),
                                   ('Toronto',43.6532,-79.3832,('CA','35')),
                                   ('Winnipeg',49.8951,-97.1384,('CA','46')),
                                   ('Anchorage',61.2181,-149.9003,('US','02')),
                                   ('Honolulu',21.3069,-157.8583,('US','15')),
                                   ('Mar Pacífico',40,-150,(None,None))]:
        comprobar('Asignación geográfica de control: '+nombre,asignar(lat,lon,poligonos)==esperado)
    with conectar() as c:
        registros=c.execute('''SELECT id_usgs,latitud,longitud,magnitud,pais,codigo
            FROM public.fact_sismo_norteamerica''').fetchall()
        comprobar('Cada evento fuente tiene exactamente una fila del warehouse',len(raw)==len(registros) and set(raw)=={r[0] for r in registros},len(registros))
        comprobar('Coordenadas y magnitud coinciden con los CSV para todos los eventos',all(
            lat==float(raw[i]['latitude']) and lon==float(raw[i]['longitude']) and mag==float(raw[i]['mag'])
            for i,lat,lon,mag,_,_ in registros))
        comprobar('Asignación territorial reproducible para todos los eventos',all(asignar(lat,lon,poligonos)==(pais,codigo) for _,lat,lon,_,pais,codigo in registros))
        faltantes=c.execute('''SELECT count(*) FROM public.v_sismo_norteamerica
            WHERE pais IS NOT NULL AND (region IS NULL OR poblacion_region IS NULL)''').fetchone()[0]
        comprobar('Todos los eventos asignados enlazan con región y población del año',faltantes==0)
        comprobar('La vista demográfica no multiplica eventos',c.execute('SELECT count(*) FROM public.v_sismo_norteamerica').fetchone()[0]==len(raw))
        originales=c.execute('''SELECT (SELECT count(*) FROM public.dim_sismos),
            (SELECT count(*) FROM public.fact_impacto_sismos_imputed),
            (SELECT count(*) FROM public.v_cruce_usgs)''').fetchone()
        comprobar('Catálogo y hechos originales conservan sus conteos',originales==(319592,196576,49272),originales)
        totales=dict(Counter(p or 'SIN_ASIGNAR' for _,_,_,_,p,_ in registros))
    base=os.environ.get('URL_SISMOS','http://127.0.0.1:8091')
    for pais in ('US','CA','MX','SIN_ASIGNAR','TODOS'):
        for anio in (2020,2025):
            r=requests.get(base+'/api/norteamerica',params=dict(pais=pais,anio=anio,magnitud=3.5),timeout=30)
            r.raise_for_status()
            datos=r.json()
            comprobar(f'API {pais}/{anio}: puntos acotados y agregados completos',
                      len(datos['puntos'])<=4000 and sum(m['eventos'] for m in datos['meses'])==datos['resumen']['total'])
            comprobar(f'API {pais}/{anio}: país y magnitud coherentes',all(
                e['magnitud']>=3.5 and (pais=='TODOS' or e['pais']==(None if pais=='SIN_ASIGNAR' else pais))
                for e in datos['puntos']))
    for parametros in ({'anio':1900},{'magnitud':'nan'},{'pais':'inventado'}):
        comprobar('Filtro inválido '+str(parametros),requests.get(base+'/api/norteamerica',params=parametros,timeout=30).status_code==400)
    for pais in ('US','CA'):
        r=requests.get(base+'/norteamerica/',params=dict(pais=pais,anio=2020),timeout=30)
        comprobar('Página del mapa '+pais,r.status_code==200 and 'puntosNA=' in r.text and '10.5066/F7MS3QZH' in r.text)
    print(json.dumps(dict(verificado_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                          totales=totales,pruebas=pruebas),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
