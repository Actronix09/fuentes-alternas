"""Verifica fuentes → extracto → PostgreSQL → API y página.

Ejecutar desde app/ con las mismas DATABASE_URL y DIR_DATOS que el ETL:
    python -m verificacion.demografia
No modifica datos ni genera evidencia de otros módulos.
"""
import csv
import datetime as dt
import io
import json
import os
import zipfile

import requests
from cargas.demografia import preparar
from comun import conectar, sha256
from fuentes import census_us, statcan_ca


def main():
    filas, meta = preparar()
    base = os.environ.get('URL_SISMOS', 'http://127.0.0.1:8091')
    pruebas = []

    def comprobar(nombre, condicion):
        pruebas.append({'prueba': nombre, 'ok': bool(condicion)})
        if not condicion:
            raise AssertionError(nombre)

    with conectar() as c:
        bd = c.execute('''SELECT pais,codigo,anio,poblacion FROM public.v_poblacion_demografia
            ORDER BY pais,codigo,anio''').fetchall()
        esperado = sorted((r['pais'],r['codigo'],r['anio'],r['poblacion']) for r in filas)
        comprobar('Las 396 observaciones del extracto coinciden con PostgreSQL', bd == esperado)
        duplicados = c.execute('''SELECT count(*) FROM (
            SELECT pais,codigo,fecha_referencia FROM public.fact_poblacion_demografia
            GROUP BY 1,2,3 HAVING count(*)>1) d''').fetchone()[0]
        comprobar('No existen claves duplicadas', duplicados == 0)
    # Controles independientes de los originales, no una suma de los mismos datos cargados.
    us = census_us.DIRECTORIO / meta['fuentes']['US']['archivo']
    comprobar('CSV original Census conserva SHA-256', sha256(us) == meta['fuentes']['US']['sha256'])
    with us.open(encoding='utf-8-sig', newline='') as f:
        nacional_us = next(r for r in csv.DictReader(f) if r['SUMLEV'] == '010')
    controles = {('US',a):int(nacional_us[f'POPESTIMATE{a}']) for a in range(2020,2026)}
    ca = statcan_ca.DIRECTORIO / meta['fuentes']['CA']['archivo']
    # Al clonar, el ZIP canadiense se descarga si hace falta para este control de procedencia.
    if not ca.exists():
        from comun import descargar
        descargar(meta['fuentes']['CA']['url'], ca)
    comprobar('ZIP original Statistics Canada conserva SHA-256', sha256(ca) == meta['fuentes']['CA']['sha256'])
    with zipfile.ZipFile(ca) as z, z.open('17100005.csv') as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig')):
            if r['GEO']=='Canada' and r['Gender']=='Total - gender' and r['Age group']=='All ages' and r['REF_DATE'] in {str(a) for a in range(2020,2026)}:
                controles['CA',int(r['REF_DATE'])] = int(r['VALUE'])
    for (pais,anio),total in controles.items():
        r = requests.get(base+'/api/demografia',params={'pais':pais,'anio':anio},timeout=20)
        r.raise_for_status()
        datos = r.json()
        comprobar(f'{pais}/{anio}: API, total de origen y suma regional coinciden',
                  datos['total']['poblacion']==total==datos['suma_regiones'] and
                  len(datos['regiones'])==(51 if pais=='US' else 13))
    for params in [{'pais':'MX'},{'anio':'2019'},{'anio':'abc'}]:
        comprobar(f'Filtro inválido rechazado: {params}', requests.get(base+'/api/demografia',params=params,timeout=20).status_code==400)
    for pais,nombre in [('US','California'),('CA','Ontario')]:
        r=requests.get(base+'/demografia/',params={'pais':pais},timeout=20)
        comprobar(f'Página {pais} muestra datos y fuente', r.status_code==200 and nombre in r.text and 'Fuente y alcance' in r.text)
    comprobar('Tablero sísmico enlaza a demografía', '/demografia/' in requests.get(base+'/',timeout=20).text)
    salida={'verificado_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'pruebas':pruebas,
            'sha256_extracto':meta['sha256_extracto']}
    print(json.dumps(salida,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
