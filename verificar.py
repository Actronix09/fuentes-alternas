"""Verificación de entrega: CSV → DW original → API y consistencia de importaciones."""
import csv
import datetime as dt
import hashlib
import json
import re
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


def inserts(archivo):
    with (RAIZ/'sismos-usgs/datos/original/ssn'/archivo).open(encoding='utf-8') as f:
        return sum(linea.startswith('INSERT') for linea in f)


def verificar_sismos():
    with psycopg.connect('postgresql://sismos:sismos_local@localhost:5441/sismos_dw') as conn:
        row=conn.execute('''SELECT (SELECT count(*) FROM public.dim_sismos),
            (SELECT count(*) FROM public.dim_tiempo),
            (SELECT count(*) FROM public.fact_impacto_sismos_imputed)''').fetchone()
        esperado=(inserts('8569667_03-dim_sismos.sql'),inserts('8569667_02-dim_tiempo.sql'),
                  inserts('8569667_05-fact_impacto_sismos_imputed.sql'))
        comprobar('Sismos conserva dimensiones y hecho de impacto originales', row==esperado,
                  {'sismos':row[0],'tiempos':row[1],'impacto':row[2]})
        sin_relacion=conn.execute('''SELECT count(*) FROM public.fact_cruce_usgs c
            LEFT JOIN public.dim_sismos s USING(id_sismo)
            LEFT JOIN public.dim_tiempo t ON t.id_tiempo=c.id_tiempo
            WHERE s.id_sismo IS NULL OR t.id_tiempo IS NULL OR c.id_tiempo<>c.id_sismo''').fetchone()[0]
        comprobar('Cruce USGS enlazado a dim_sismos y dim_tiempo originales', sin_relacion==0, sin_relacion)
        filas=conn.execute('''SELECT d.variante, d.n, coalesce(p.n,0) FROM
            (SELECT variante, count(*) n FROM dw.fact_cruce_sismo WHERE resultado IN ('ambas','solo_ssn') GROUP BY 1) d
            LEFT JOIN (SELECT variante, count(*) n FROM public.fact_cruce_usgs GROUP BY 1) p USING(variante)
            ORDER BY 1''').fetchall()
        comprobar('Cruce integrado completo y sin duplicar', len(filas)==2 and all(a==b for _,a,b in filas),
                  {v:b for v,_,b in filas})
        tehuantepec=conn.execute('''SELECT t.fecha, c.fecha_hora_utc::date, c.confirmado_usgs, c.magnitud_usgs, c.id_usgs
            FROM public.v_cruce_usgs c JOIN public.dim_sismos s USING(id_sismo)
            JOIN public.dim_tiempo t ON t.id_tiempo=s.id_sismo
            WHERE s.magnitud=8.2 AND t.fecha BETWEEN '2017-09-07' AND '2017-09-08' ''').fetchone()
        comprobar('Tehuantepec M8.2: fecha original recorrida y confirmada con UTC corregida',
                  tehuantepec is not None and str(tehuantepec[0])=='2017-09-07' and str(tehuantepec[1])=='2017-09-08' and tehuantepec[2],
                  None if tehuantepec is None else {'fecha_dw':str(tehuantepec[0]),'fecha_utc':str(tehuantepec[1]),'id_usgs':tehuantepec[4]})
    diag=get('http://127.0.0.1:8091/api/diagnostico?mag_min=4.5')
    pct={v['variante']:float(v['pct_emparejado']) for v in diag['variantes']}
    comprobar('Sismos: la fecha corregida aumenta la confirmación M≥4.5', pct.get('corregida',0)>pct.get('dw_original',100), pct)
    for ruta in ['resumen','cobertura','serie','concordancia','histograma/delta_magnitud','dispersion','eventos',
                 'discrepancias','solo/usgs','solo/ssn','bitacora','original']:
        r=requests.get('http://127.0.0.1:8091/api/'+ruta, timeout=60)
        comprobar('API sismos /'+ruta, r.status_code==200, r.status_code)
    invalida=requests.get('http://127.0.0.1:8091/api/resumen?variante=inventada', timeout=10)
    comprobar('Sismos rechaza variantes desconocidas', invalida.status_code==400, invalida.status_code)
    pagina=requests.get('http://127.0.0.1:8094/sismos.php?anio=2017&magnitud=8', timeout=60)
    comprobar('Frontend original de sismos muestra el cruce desde PostgreSQL',
              pagina.status_code==200 and '"confirmado_usgs":"t"' in pagina.text and 'Confirmados por USGS' in pagina.text,
              pagina.status_code)
    std3=requests.get('http://127.0.0.1:8094/std3.php', timeout=60).text
    aeco=requests.get('http://127.0.0.1:8094/aeconomica.php', timeout=60).text
    n_std3=len(json.loads(re.search(r'var datosEconomicos = (\[.*?\]);', std3).group(1)))
    n_aeco=len(json.loads(re.search(r'const datosEstados = (\{.*?\});', aeco).group(1)))
    comprobar('Mapas económicos originales reciben las 32 entidades', n_std3==32 and n_aeco==32,
              {'std3':n_std3,'aeconomica':n_aeco})


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
    with (RAIZ/'obra-publica-srft/datos/shcp_srft/ef2025_temascaltepec.csv').open(encoding='utf-8',newline='') as f:
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
    verificar_sismos()
    fuentes={}
    for carpeta, patron in [('agua-reportes-sacmex/datos','**/*.csv'),('obra-publica-srft/datos','**/*.csv'),
                            ('sismos-usgs/datos/original/ssn','*.sql'),('sismos-usgs/datos/usgs/mexico','*.csv')]:
        for p in sorted((RAIZ/carpeta).glob(patron)):
            fuentes[p.relative_to(RAIZ).as_posix()]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    salida={'verificado_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'pruebas':resultados,'archivos_fuente':fuentes}
    (RAIZ/'evidencia').mkdir(exist_ok=True)
    (RAIZ/'evidencia/verificacion.json').write_text(json.dumps(salida,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if all(r['ok'] for r in resultados) else 1


if __name__=='__main__':
    sys.exit(main())
