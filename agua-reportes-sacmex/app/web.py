"""API REST y página web del Sistema 2 (consumo de agua validado con reportes).

Todas las rutas /api aceptan los mismos filtros (tipo, desde, hasta, alcaldia),
así que indicadores, mapa, gráficas y tablas describen siempre el mismo corte.
"""
from __future__ import annotations

import datetime as dt
import decimal

from flask import Flask, abort, jsonify, render_template, request
from flask.json.provider import DefaultJSONProvider
from psycopg.rows import dict_row

from comun import conectar


class ProveedorJSON(DefaultJSONProvider):
    ensure_ascii = False
    sort_keys = False

    @staticmethod
    def default(o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        if isinstance(o, (dt.datetime, dt.date)):
            return o.isoformat()
        return DefaultJSONProvider.default(o)


app = Flask(__name__)
app.json = ProveedorJSON(app)

TIPOS = ("Falta de agua", "Fuga", "Mala calidad")
CITAS = [
    {
        "codigo": "Consumo",
        "papel": "Fuente del paper",
        "cita_apa": "Sistema de Aguas de la Ciudad de México. (2026). Consumo de agua [Conjunto de datos]. "
                    "Portal de Datos Abiertos de la Ciudad de México. https://datos.cdmx.gob.mx/dataset/consumo-agua",
        "licencia": "CC BY 4.0",
    },
    {
        "codigo": "Reportes",
        "papel": "Fuente alterna",
        "cita_apa": "Sistema de Aguas de la Ciudad de México. (2026). Reportes de agua [Conjunto de datos]. "
                    "Portal de Datos Abiertos de la Ciudad de México. https://datos.cdmx.gob.mx/dataset/reportes-de-agua",
        "licencia": "CC BY 4.0",
    },
    {
        "codigo": "Paper",
        "papel": "Sistema original",
        "cita_apa": "Velázquez Arrieta, E. U., Pulido Morales, O. F., García López, E., Hernández Martínez, C. A., "
                    "y Hurtado Avilés, G. (en prensa). Territorial information retrieval from heterogeneous open data "
                    "through the construction of a data warehouse for water management in Mexico City. En Advances in "
                    "Computer Science Applications and Research. Springer.",
        "licencia": "Código: MIT (github.com/gabrielhuav/data_warehouse_cdmx)",
    },
]


def consulta(sql: str, params: dict | list | None = None) -> list[dict]:
    with conectar() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def alcaldias() -> list[str]:
    return [f["alcaldia"] for f in consulta("SELECT DISTINCT alcaldia FROM dw.dim_ubicacion ORDER BY 1")]


def filtros() -> dict:
    tipo = request.args.get("tipo", "Falta de agua")
    if tipo not in TIPOS:
        abort(400, "tipo debe ser: " + ", ".join(TIPOS))
    try:
        desde = dt.date.fromisoformat(request.args.get("desde", "2019-01-01"))
        hasta = dt.date.fromisoformat(request.args.get("hasta", "2019-06-30"))
    except ValueError:
        abort(400, "desde y hasta deben ser fechas AAAA-MM-DD")
    alcaldia = request.args.get("alcaldia") or None
    if alcaldia and alcaldia not in alcaldias():
        abort(400, "alcaldía desconocida")
    return {"tipo": tipo, "desde": desde, "hasta": hasta, "alcaldia": alcaldia}


PUNTAJES = """
WITH p AS (
    SELECT * FROM dw.fn_puntajes(%(tipo)s, %(desde)s, %(hasta)s) x
    WHERE %(alcaldia)s::text IS NULL OR x.alcaldia = %(alcaldia)s::text
)"""


@app.get("/")
def inicio():
    return render_template("index.html")


@app.get("/api/salud")
def salud():
    consulta("SELECT 1")
    return {"ok": True}


@app.get("/api/opciones")
def opciones():
    return jsonify(
        alcaldias=alcaldias(),
        tipos=list(TIPOS),
        disponibilidad=consulta("""
            SELECT tr.reporte, t.anio, count(*) AS reportes
            FROM dw.fact_reporte_agua r
            JOIN dw.dim_tipo_reporte tr ON tr.id_tipo = r.id_tipo
            JOIN dw.dim_tiempo t        ON t.id_tiempo = r.id_tiempo
            WHERE tr.reporte = ANY(%(tipos)s) AND tr.es_agua_potable
            GROUP BY 1, 2 ORDER BY 1, 2""", {"tipos": list(TIPOS)}),
    )


@app.get("/api/resumen")
def resumen():
    p = filtros()
    reportes = consulta("""
        SELECT coalesce(r.metodo_ubicacion, 'sin_ubicar') AS metodo, count(*) AS reportes
        FROM dw.fact_reporte_agua r
        JOIN dw.dim_tipo_reporte tr ON tr.id_tipo = r.id_tipo
        JOIN dw.dim_tiempo t        ON t.id_tiempo = r.id_tiempo
        LEFT JOIN dw.dim_ubicacion u ON u.id_ubicacion = r.id_ubicacion
        WHERE tr.reporte = %(tipo)s AND tr.es_agua_potable
          AND t.fecha BETWEEN %(desde)s AND %(hasta)s
          AND (%(alcaldia)s::text IS NULL OR u.alcaldia = %(alcaldia)s::text)
        GROUP BY 1""", p)
    return jsonify(
        evaluacion=consulta("SELECT * FROM dw.fn_evaluacion(%(tipo)s, %(desde)s, %(hasta)s, %(alcaldia)s)", p),
        reportes={f["metodo"]: f["reportes"] for f in reportes},
        consumo=consulta("""
            SELECT round(sum(f.consumo_total)) AS consumo_m3, count(DISTINCT f.id_ubicacion) AS colonias
            FROM dw.fact_consumo_agua f JOIN dw.dim_ubicacion u USING (id_ubicacion)
            WHERE %(alcaldia)s::text IS NULL OR u.alcaldia = %(alcaldia)s::text""", p)[0],
        recursos=consulta("SELECT nombre, conjunto, url, ultima_modificacion, bytes FROM etl.recurso ORDER BY conjunto, nombre"),
        citas=CITAS,
        etl=consulta("SELECT id_ejecucion, inicio, fin, mensaje FROM etl.ejecucion "
                     "WHERE estado = 'ok' ORDER BY id_ejecucion DESC LIMIT 1"),
        filtros=p,
    )


@app.get("/api/colonias")
def colonias():
    return jsonify(consulta(PUNTAJES + """
        SELECT id_ubicacion, alcaldia, colonia, latitud, longitud, manzanas, consumo_m3,
               consumo_por_manzana, round(z::numeric, 2) AS z, round(a_g::numeric, 2) AS a_g,
               round(z_norm::numeric, 2) AS z_norm, round(a_g_norm::numeric, 2) AS a_g_norm,
               reportes, round(densidad::numeric, 2) AS densidad, positivo
        FROM p ORDER BY a_g DESC""", filtros()))


@app.get("/api/curva_pr")
def curva_pr():
    p = filtros()
    sql = "SELECT k, precision_k, recall_k FROM dw.fn_curva_pr(%(tipo)s, %(desde)s, %(hasta)s, %(alcaldia)s, %(norm)s)"
    return jsonify(
        paper=consulta(sql, {**p, "norm": False}),
        manzana=consulta(sql, {**p, "norm": True}),
    )


@app.get("/api/clases")
def clases():
    """% de colonias en el cuartil superior de reportes, por clase de puntaje."""
    return jsonify(consulta(PUNTAJES + """
        , clases AS (
            SELECT 'paper' AS puntaje, least(floor(a_g), 3)::int AS clase, positivo, densidad FROM p
            UNION ALL
            SELECT 'manzana', least(floor(a_g_norm), 3)::int, positivo, densidad FROM p
        )
        SELECT puntaje, clase, count(*) AS colonias,
               round(100.0 * avg(positivo::int), 1) AS pct_cuartil_superior,
               round(avg(densidad)::numeric, 2)     AS densidad_media
        FROM clases GROUP BY 1, 2 ORDER BY 1, 2""", filtros()))


@app.get("/api/serie_mensual")
def serie_mensual():
    p = filtros()
    return jsonify(consulta("""
        SELECT date_trunc('month', t.fecha)::date AS mes, tr.reporte, count(*) AS reportes
        FROM dw.fact_reporte_agua r
        JOIN dw.dim_tiempo t        ON t.id_tiempo = r.id_tiempo
        JOIN dw.dim_tipo_reporte tr ON tr.id_tipo = r.id_tipo
        LEFT JOIN dw.dim_ubicacion u ON u.id_ubicacion = r.id_ubicacion
        WHERE tr.es_agua_potable AND tr.reporte = ANY(%(tipos)s)
          AND (%(alcaldia)s::text IS NULL OR u.alcaldia = %(alcaldia)s::text)
        GROUP BY 1, 2 ORDER BY 1, 2""", {**p, "tipos": list(TIPOS)}))


@app.get("/api/alcaldias")
def por_alcaldia():
    return jsonify(consulta(PUNTAJES + """
        , r AS (
            SELECT p.*,
                   rank() OVER (PARTITION BY alcaldia ORDER BY a_g)      AS r_ag,
                   rank() OVER (PARTITION BY alcaldia ORDER BY a_g_norm) AS r_agn,
                   rank() OVER (PARTITION BY alcaldia ORDER BY densidad) AS r_d
            FROM p
        )
        SELECT alcaldia, count(*) AS colonias, round(sum(consumo_m3)) AS consumo_m3,
               sum(reportes) AS reportes, round(avg(densidad)::numeric, 2) AS densidad_media,
               round(corr(r_ag, r_d)::numeric, 2)  AS spearman_paper,
               round(corr(r_agn, r_d)::numeric, 2) AS spearman_manzana
        FROM r GROUP BY alcaldia ORDER BY reportes DESC""", filtros()))


@app.get("/api/puntos")
def puntos():
    """Muestra de reportes individuales para el mapa (hasta 4 000)."""
    return jsonify(consulta("""
        SELECT r.latitud, r.longitud, t.fecha, u.colonia, r.metodo_ubicacion
        FROM dw.fact_reporte_agua r
        JOIN dw.dim_tipo_reporte tr ON tr.id_tipo = r.id_tipo
        JOIN dw.dim_tiempo t        ON t.id_tiempo = r.id_tiempo
        LEFT JOIN dw.dim_ubicacion u ON u.id_ubicacion = r.id_ubicacion
        WHERE tr.reporte = %(tipo)s AND tr.es_agua_potable
          AND t.fecha BETWEEN %(desde)s AND %(hasta)s
          AND r.latitud IS NOT NULL
          AND (%(alcaldia)s::text IS NULL OR u.alcaldia = %(alcaldia)s::text)
        ORDER BY md5(r.folio) LIMIT 4000""", filtros()))


@app.get("/api/ubicacion")
def ubicacion():
    return jsonify(consulta("SELECT * FROM dw.v_ubicacion_reportes ORDER BY recurso, metodo"))


@app.get("/api/bitacora")
def bitacora():
    ejecucion = consulta("SELECT id_ejecucion, inicio, fin, estado, mensaje FROM etl.ejecucion "
                         "ORDER BY id_ejecucion DESC LIMIT 1")
    if not ejecucion:
        return jsonify(ejecucion=None, pasos=[])
    pasos = consulta("SELECT momento, fase, paso, registros, detalle FROM etl.bitacora "
                     "WHERE id_ejecucion = %(id)s ORDER BY id_bitacora",
                     {"id": ejecucion[0]["id_ejecucion"]})
    return jsonify(ejecucion=ejecucion[0], pasos=pasos)
