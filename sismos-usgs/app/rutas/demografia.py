"""Consulta del contexto demográfico, independiente de los filtros sísmicos."""
from flask import Blueprint, abort, jsonify, render_template, request
from psycopg.rows import dict_row
from comun import conectar

demografia = Blueprint('demografia', __name__)


def consultar():
    pais = request.args.get('pais', 'CA')
    try:
        anio = int(request.args.get('anio', '2025'))
    except ValueError:
        abort(400, 'El año debe ser un número entre 2020 y 2025')
    if pais not in ('US', 'CA') or anio not in range(2020, 2026):
        abort(400, 'Selecciona US o CA y un año entre 2020 y 2025')
    with conectar() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT to_regclass('public.v_poblacion_demografia') AS tabla")
        if cur.fetchone()['tabla'] is None:
            abort(503, 'La demografía aún no se ha cargado. Ejecuta demografia.py.')
        cur.execute('''SELECT * FROM public.v_poblacion_demografia
            WHERE pais=%s AND anio=%s ORDER BY nivel,nombre''', [pais, anio])
        filas = cur.fetchall()
    nacional = next((r for r in filas if r['nivel'] == 'pais'), None)
    if nacional is None:
        abort(503, 'No hay observaciones para el país y año seleccionados')
    regiones = [r for r in filas if r['nivel'] == 'region']
    return dict(pais=pais, anio=anio, total=nacional, regiones=regiones,
                suma_regiones=sum(r['poblacion'] for r in regiones),
                nota='Población residente estimada al 1 de julio; no personas afectadas por un sismo.')


@demografia.get('/demografia/')
def pagina():
    return render_template('demografia.html', **consultar())


@demografia.get('/api/demografia')
def api():
    return jsonify(consultar())
