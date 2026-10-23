"""Extensión local: datos reales de SHCP en el backend original del artículo."""
from flask import Blueprint, jsonify, request, render_template, abort
from app.database import get_db

srft_bp = Blueprint('srft', __name__)
FILTRO = "WHERE (%s = '' OR clasificacion = %s) AND (%s = '' OR nombre_obra ILIKE %s OR folio ILIKE %s)"


def parametros():
    clase = request.args.get('clasificacion', '')
    q = request.args.get('q', '').strip()[:200]
    return (clase, clase, q, '%' + q + '%', '%' + q + '%')


@srft_bp.get('/api/srft/obras')
def obras():
    with get_db() as (_, cur):
        cur.execute('SELECT * FROM warehouse.v_srft_obras ' + FILTRO + ' ORDER BY aprobado DESC NULLS LAST, folio', parametros())
        filas = cur.fetchall()
    for fila in filas:
        for k in ('fecha_inicio','fecha_estimada_termino','cargado_en'):
            if fila[k] is not None:
                fila[k] = fila[k].isoformat()
    return jsonify(filas)


@srft_bp.get('/api/srft/resumen')
def resumen():
    with get_db() as (_, cur):
        cur.execute('''SELECT count(*) AS obras, sum(aprobado) AS aprobado,
            sum(pagado) AS pagado, count(*) FILTER(WHERE latitud IS NOT NULL) AS con_coordenadas,
            avg(avance_fisico_pct) AS avance_fisico_promedio,
            count(*) FILTER(WHERE avance_fisico_pct IS NOT NULL) AS obras_con_avance,
            count(DISTINCT localidad) AS localidades
            FROM warehouse.v_srft_obras ''' + FILTRO, parametros())
        resumen = dict(cur.fetchone())
        cur.execute('''SELECT clasificacion, count(*) AS obras, sum(aprobado) AS aprobado,
            sum(pagado) AS pagado FROM warehouse.v_srft_obras ''' + FILTRO + ' GROUP BY 1 ORDER BY aprobado DESC', parametros())
        resumen['clasificaciones'] = cur.fetchall()
        cur.execute('SELECT DISTINCT clasificacion FROM warehouse.fact_srft ORDER BY 1')
        resumen['opciones'] = [r['clasificacion'] for r in cur.fetchall()]
        cur.execute('SELECT id_ejecucion,inicio,fin,estado,mensaje FROM etl.ejecucion ORDER BY id_ejecucion DESC LIMIT 1')
        resumen['etl'] = cur.fetchone()
        cur.execute('SELECT count(*) AS dimensiones_originales FROM information_schema.tables WHERE table_schema=%s AND table_name LIKE %s', ['warehouse','dim_%'])
        resumen['modelo'] = cur.fetchone()
    resumen['fuente'] = {
        'institucion': 'Secretaría de Hacienda y Crédito Público',
        'url': 'https://www.transparenciapresupuestaria.gob.mx/Datos-Abiertos',
        'periodo': 'Informe definitivo 2025 (periodo 5, no quinto trimestre)',
        'alcance': 'Obras con recursos federales reportadas en Temascaltepec, Estado de México',
    }
    return jsonify(resumen)


@srft_bp.get('/api/srft/bitacora')
def bitacora():
    with get_db() as (_, cur):
        cur.execute('''SELECT fase,paso,registros,detalle,momento FROM etl.bitacora
            WHERE id_ejecucion=(SELECT max(id_ejecucion) FROM etl.ejecucion) ORDER BY id_bitacora''')
        return jsonify(cur.fetchall())


@srft_bp.get('/api/srft/proyecto/<folio>')
def proyecto(folio):
    with get_db() as (_, cur):
        cur.execute('SELECT * FROM staging.srft WHERE folio=%s', [folio])
        fila = cur.fetchone()
        return (jsonify(fila), 200) if fila else (jsonify(error='Folio desconocido'), 404)


def leer_expediente(folio):
    with get_db() as (_, cur):
        cur.execute('''SELECT e.*,o.nombre_obra,o.fecha_inicio,o.fecha_final,o.codigo_supervisor,
            o.estatus_fuente,o.codigo_expediente,p.presupuesto_total,c.nombre_const,c.rfc,
            r.comunidad,r.barrio,i.avance_fisico_pct,i.pagado,i.aprobado
            FROM public.expediente_srft e JOIN public.obra o USING(id_obra)
            LEFT JOIN public.presupuesto_obra p USING(id_obra)
            LEFT JOIN public.constructora c ON c.id_constructora=o.id_constructora
            LEFT JOIN public.region r ON r.id_region=o.id_region
            LEFT JOIN public.informe_fuente_srft i USING(id_obra)
            WHERE e.folio=%s''',[folio])
        expediente = cur.fetchone()
        if expediente is None:
            return None
        for tabla in ('contrato_srft','financiamiento_srft'):
            # Nombres internos fijos, nunca procedentes de parámetros HTTP.
            cur.execute('SELECT * FROM public.'+tabla+' WHERE id_obra=%s ORDER BY id_registro',[expediente['id_obra']])
            expediente[tabla] = cur.fetchall()
        cur.execute('SELECT metas_originales FROM public.informe_fuente_srft WHERE id_obra=%s',[expediente['id_obra']])
        expediente['metas'] = cur.fetchone()['metas_originales']
        return expediente


@srft_bp.get('/api/srft/expediente/<folio>')
def expediente_api(folio):
    e = leer_expediente(folio)
    return (jsonify(e),200) if e else (jsonify(error='Expediente desconocido'),404)


@srft_bp.get('/expedientes/')
@srft_bp.get('/expedientes/<folio>')
def expediente_pagina(folio=None):
    with get_db() as (_,cur):
        cur.execute('''SELECT e.folio,o.nombre_obra,o.estatus_fuente,
            (SELECT count(*) FROM public.contrato_srft c WHERE c.id_obra=o.id_obra) AS contratos
            FROM public.expediente_srft e JOIN public.obra o USING(id_obra) ORDER BY e.folio''')
        lista=cur.fetchall()
    detalle=leer_expediente(folio) if folio else None
    if folio and not detalle:
        abort(404)
    from urllib.parse import urlparse
    def url_segura(valor):
        return valor if valor and urlparse(valor).scheme in ('https','http') else None
    return render_template('expediente.html',expedientes=lista,e=detalle,url_segura=url_segura)
