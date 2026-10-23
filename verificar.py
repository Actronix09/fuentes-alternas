"""Verificación de entrega: CSV → DW original → API y consistencia de importaciones."""
import csv
import datetime as dt
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ / '.runtime'))
import psycopg
import requests

resultados = []


def comprobar(nombre, condicion, detalle):
    resultados.append({'prueba': nombre, 'ok': bool(condicion), 'detalle': detalle})
    print(('OK  ' if condicion else 'ERROR  ') + nombre)


def get(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def main():
    agua = get('http://127.0.0.1:8092/api/original')
    comprobar('Agua conserva consumo y clima originales', agua['consumo_original'] == 70886 and agua['clima_original'] == 181, agua)
    with psycopg.connect('postgresql://agua:agua_local@localhost:5442/agua_dw') as conn:
        row = conn.execute('''SELECT
            (SELECT count(*) FROM public.fact_reporte_agua),
            (SELECT count(*) FROM dw.fact_reporte_agua),
            (SELECT sum(consumo_total) FROM public.fact_consumo_agua),
            (SELECT sum(consumo_total) FROM dw.fact_consumo_agua)''').fetchone()
        comprobar('Reportes integrados completos y consumo preservado', row[0] == row[1] == 555752 and row[2] == row[3], list(map(str,row)))
        sin_relacion = conn.execute('''SELECT count(*) FROM public.fact_reporte_agua r
            LEFT JOIN public.dim_tiempo t USING(id_tiempo) WHERE t.id_tiempo IS NULL''').fetchone()[0]
        comprobar('Reportes enlazados al tiempo del modelo original', sin_relacion == 0, sin_relacion)
    datos_originales = get('http://127.0.0.1:8092/sistema/consumo.json')
    comprobar('Frontend original de agua recibe datos de PostgreSQL', len(datos_originales['alcaldias']) == 16 and len(datos_originales['correlacion']) == 3, {'filas':len(datos_originales['consumo_colonia'])})
    for ruta in ['resumen','colonias','curva_pr','clases','serie_mensual','alcaldias','puntos','ubicacion','bitacora']:
        r=requests.get('http://127.0.0.1:8092/api/'+ruta, timeout=30)
        comprobar('API agua /'+ruta, r.status_code==200, r.status_code)
    invalida = requests.get('http://127.0.0.1:8092/api/resumen?desde=2025-01-01&hasta=2020-01-01',timeout=10)
    comprobar('Agua rechaza periodos invertidos', invalida.status_code==400, invalida.status_code)
    with (RAIZ/'obra-publica-srft/datos/ef2025_temascaltepec.csv').open(encoding='utf-8',newline='') as f:
        filas=list(csv.DictReader(f))
    aprobado=sum(Decimal(r['APROBADO']) for r in filas)
    pagado=sum(Decimal(r['PAGADO']) for r in filas)
    obras=get('http://127.0.0.1:8093/api/srft/obras')
    resumen=get('http://127.0.0.1:8093/api/srft/resumen')
    comprobar('Obras: folios de la API coinciden con CSV oficial', {r['folio'] for r in obras}=={r['FOLIO'] for r in filas}, len(obras))
    comprobar('Obras: montos coinciden con CSV sin duplicar relaciones', Decimal(resumen['aprobado'])==aprobado and Decimal(resumen['pagado'])==pagado, {'aprobado':str(aprobado),'pagado':str(pagado)})
    with psycopg.connect('postgresql://obras:obras_local@localhost:5443/obras_publicas') as conn:
        n=conn.execute('''SELECT count(*) FROM warehouse.fact_srft f
            JOIN warehouse.dim_obra o USING(obra_key)
            JOIN warehouse.dim_tiempo t USING(tiempo_key)''').fetchone()[0]
        comprobar('Obras vinculadas a dimensiones originales', n==len(filas), n)
        n=conn.execute("SELECT count(*) FROM warehouse.dim_obra WHERE obra_id LIKE 'SRFT:%' AND es_actual").fetchone()[0]
        comprobar('Sin dimensiones de obra duplicadas', n==len(filas), n)
        n=conn.execute("SELECT count(*) FROM public.obra WHERE origen_datos='SHCP_SRFT'").fetchone()[0]
        comprobar('Expedientes operativos corresponden a obras oficiales', n==len(filas),n)
    sector=get('http://127.0.0.1:8093/api/srft/obras?clasificacion=Educaci%C3%B3n')
    comprobar('Filtro de sector en backend de obras', len(sector)==12 and all(r['clasificacion']=='Educación' for r in sector), len(sector))
    noexiste=get('http://127.0.0.1:8093/api/srft/obras?q=NO_EXISTE_ABCXYZ')
    comprobar('Búsqueda sin coincidencias no devuelve datos de ejemplo', noexiste==[],len(noexiste))
    detalle=get('http://127.0.0.1:8093/api/srft/proyecto/'+obras[0]['folio'])
    comprobar('Trazabilidad a registros originales y relaciones', detalle['datos']['FOLIO']==obras[0]['folio'] and isinstance(detalle['georreferencias'],list), detalle['folio'])
    fuentes={}
    for carpeta in ['agua-reportes-sacmex/datos','obra-publica-srft/datos']:
        for p in (RAIZ/carpeta).glob('*.csv'):
            fuentes[p.relative_to(RAIZ).as_posix()]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    salida={'verificado_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'pruebas':resultados,'archivos_fuente':fuentes}
    (RAIZ/'evidencia').mkdir(exist_ok=True)
    (RAIZ/'evidencia/verificacion.json').write_text(json.dumps(salida,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if all(r['ok'] for r in resultados) else 1


if __name__=='__main__':
    sys.exit(main())
