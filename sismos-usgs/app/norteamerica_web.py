"""Mapa regional, sin atribuir impactos o duplicar eventos entre países."""
import datetime as dt
import math
from flask import Blueprint, abort, jsonify, render_template, request
from psycopg.rows import dict_row
from comun import conectar

norteamerica=Blueprint('norteamerica',__name__)
LIMITE=4000


def datos():
    try:
        anio=int(request.args.get('anio',2025))
        magnitud=float(request.args.get('magnitud',3.5))
    except ValueError:
        abort(400,'Año y magnitud deben ser numéricos')
    pais=request.args.get('pais','TODOS')
    if anio not in range(2020,2026) or not math.isfinite(magnitud) or not 3.5<=magnitud<=10 or pais not in ('TODOS','US','CA','MX','SIN_ASIGNAR'):
        abort(400,'Selecciona 2020–2025, magnitud de 3.5 a 10 y un país válido')
    inicio,fin=dt.datetime(anio,1,1,tzinfo=dt.timezone.utc),dt.datetime(anio+1,1,1,tzinfo=dt.timezone.utc)
    params=dict(inicio=inicio,fin=fin,mag=magnitud,pais=pais)
    # México usa exclusivamente el SSN ya integrado, no las filas USGS sin asignar.
    # SIN_ASIGNAR es una vista alternativa del área completa: incluye mar y otros países.
    sql='''WITH eventos AS (
      SELECT id_usgs AS id, 'USGS ComCat'::text AS fuente,fecha_hora_utc,latitud,longitud,
             magnitud,profundidad_km,tipo_magnitud,lugar,pais,codigo,region,poblacion_region,
             fecha_poblacion,url_fuente
      FROM public.v_sismo_norteamerica
      WHERE fecha_hora_utc >= %(inicio)s AND fecha_hora_utc < %(fin)s AND magnitud >= %(mag)s
        AND ((%(pais)s='TODOS' AND pais IS NOT NULL) OR pais=%(pais)s
             OR (%(pais)s='SIN_ASIGNAR' AND pais IS NULL))
      UNION ALL
      SELECT 'ssn:'||s.id_externo,'SSN · DW original',s.fecha_hora_utc,s.latitud,s.longitud,
             s.magnitud,s.profundidad_km,s.tipo_magnitud,s.lugar,'MX',NULL,NULL,NULL::bigint,
             NULL::date,'https://www.ssn.unam.mx/'
      FROM dw.dim_sismo s
      WHERE s.id_fuente=1 AND s.fecha_hora_utc >= %(inicio)s AND s.fecha_hora_utc < %(fin)s
        AND s.magnitud >= %(mag)s AND %(pais)s IN ('TODOS','MX')
    )'''
    with conectar() as conn,conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT to_regclass('public.v_sismo_norteamerica') AS tabla")
        if cur.fetchone()['tabla'] is None:
            abort(503,'Falta cargar norteamerica.py')
        cur.execute(sql+''' SELECT count(*) AS total,max(magnitud) AS maxima,
             count(*) FILTER(WHERE pais='US') AS us,
             count(*) FILTER(WHERE pais='CA') AS ca,
             count(*) FILTER(WHERE pais='MX') AS mx FROM eventos''',params)
        resumen=cur.fetchone()
        cur.execute(sql+''' SELECT * FROM eventos ORDER BY magnitud DESC,fecha_hora_utc DESC,id
            LIMIT 4000''',params)
        puntos=cur.fetchall()
        cur.execute(sql+''' SELECT extract(month FROM fecha_hora_utc AT TIME ZONE 'UTC')::integer AS mes,
            count(*) AS eventos FROM eventos GROUP BY 1 ORDER BY 1''',params)
        meses=cur.fetchall()
        cur.execute('''SELECT eventos,cargado_utc,procedencia->>'doi' AS doi
            FROM etl.norteamerica_carga ORDER BY id DESC LIMIT 1''')
        carga=cur.fetchone()
    return dict(anio=anio,magnitud=magnitud,pais=pais,resumen=resumen,puntos=puntos,
                meses=meses,carga=carga,limite=LIMITE,mostrados=len(puntos))


@norteamerica.get('/norteamerica/')
def pagina():
    return render_template('norteamerica.html',**datos())


@norteamerica.get('/api/norteamerica')
def api():
    return jsonify(datos())
