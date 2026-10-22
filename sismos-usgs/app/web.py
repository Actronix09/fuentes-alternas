"""API REST y página web del Sistema 1 (validación SSN ↔ USGS).

Todas las rutas /api aceptan los mismos filtros (desde, hasta, mag_min), de
modo que los indicadores, el mapa, las gráficas y las tablas de la página
siempre describen el mismo subconjunto de sismos.
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

LIMITE_MAPA = 4000


def consulta(sql: str, params: dict | list | None = None) -> list[dict]:
    with conectar() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


VARIANTES = ("corregida", "dw_original")
ORIGENES = ("independientes", "todas", "aportadas")


def filtros() -> dict:
    """Filtros comunes: periodo (años), magnitud de referencia mínima, qué
    fechas del SSN se usan (corregidas o tal como están en el DW del paper) y
    qué soluciones de ComCat entran (las independientes o también las que
    aportó el propio SSN a través de UNM)."""
    try:
        p = {
            "desde": int(request.args.get("desde", 1900)),
            "hasta": int(request.args.get("hasta", dt.date.today().year)),
            "mag_min": float(request.args.get("mag_min", 4.0)),
            "variante": request.args.get("variante", "corregida"),
            "origen": request.args.get("origen", "independientes"),
        }
    except ValueError:
        abort(400, "Los filtros desde, hasta y mag_min deben ser numéricos")
    if p["variante"] not in VARIANTES:
        abort(400, "variante debe ser corregida o dw_original")
    if p["origen"] not in ORIGENES:
        abort(400, "origen debe ser independientes, todas o aportadas")
    return p


# Condición de origen de la solución USGS (los sismos solo_ssn no tienen USGS y siempre entran)
ORIGEN_HECHOS = """
      AND (%(origen)s = 'todas' OR f.id_sismo_usgs IS NULL
           OR f.independiente = (%(origen)s = 'independientes'))"""


# Hechos dentro de los filtros (se antepone a cada consulta como CTE)
HECHOS = """
WITH f AS (
    SELECT f.*, t.anio
    FROM dw.fact_cruce_sismo f
    JOIN dw.dim_tiempo t ON t.id_tiempo = f.id_tiempo
    WHERE f.variante = %(variante)s
      AND t.anio BETWEEN %(desde)s AND %(hasta)s
      AND f.magnitud_ref >= %(mag_min)s""" + ORIGEN_HECHOS + """
)"""

# Pares dentro de los filtros (para la vista dw.v_pares la magnitud de referencia es la del SSN)
PARES = """
WITH p AS (
    SELECT * FROM dw.v_pares
    WHERE variante = %(variante)s
      AND anio BETWEEN %(desde)s AND %(hasta)s AND mag_ssn >= %(mag_min)s
      AND (%(origen)s = 'todas' OR independiente = (%(origen)s = 'independientes'))
)"""


@app.get("/")
def inicio():
    return render_template("index.html", anio_actual=dt.date.today().year)


@app.get("/api/salud")
def salud():
    consulta("SELECT 1")
    return {"ok": True}


@app.get("/api/resumen")
def resumen():
    p = filtros()
    return jsonify(
        resultados=consulta(HECHOS + " SELECT resultado, count(*) AS eventos FROM f GROUP BY 1", p),
        pares=consulta(PARES + """
            SELECT count(*)                                                    AS pares,
                   round((percentile_cont(0.5) WITHIN GROUP (ORDER BY distancia_km))::numeric, 1) AS distancia_mediana_km,
                   round(avg(delta_magnitud)::numeric, 2)                      AS delta_mag_media,
                   round(stddev_samp(delta_magnitud)::numeric, 2)              AS delta_mag_desv,
                   round(100.0 * avg((abs(delta_magnitud) <= 0.3)::int), 1)    AS pct_mag_dentro_0_3,
                   round(avg(abs(delta_segundos))::numeric, 1)                 AS delta_seg_abs_media
            FROM p""", p)[0],
        periodo=consulta("""
            SELECT fu.codigo, min(s.fecha_hora_utc)::date AS desde,
                   max(s.fecha_hora_utc)::date AS hasta, count(*) AS eventos
            FROM dw.dim_sismo s JOIN dw.dim_fuente fu USING (id_fuente)
            GROUP BY fu.codigo ORDER BY fu.codigo"""),
        fuentes=consulta("SELECT codigo, nombre, institucion, url, doi, licencia, cita_apa "
                         "FROM dw.dim_fuente ORDER BY id_fuente"),
        etl=consulta("SELECT id_ejecucion, inicio, fin, parametros, mensaje FROM etl.ejecucion "
                     "WHERE estado = 'ok' ORDER BY id_ejecucion DESC LIMIT 1"),
        filtros=p,
    )


@app.get("/api/cobertura")
def cobertura():
    return jsonify(consulta(HECHOS + """
        SELECT r.id_rango, r.etiqueta,
               count(*) FILTER (WHERE f.resultado = 'ambas')     AS pares,
               count(*) FILTER (WHERE f.resultado = 'solo_ssn')  AS solo_ssn,
               count(*) FILTER (WHERE f.resultado = 'solo_usgs') AS solo_usgs,
               CASE WHEN r.mag_min >= coalesce(etl.parametro('ssn_mag_min')::numeric, 4.0) THEN
               round(100.0 * count(*) FILTER (WHERE f.resultado = 'ambas')
                     / nullif(count(*) FILTER (WHERE f.resultado IN ('ambas', 'solo_ssn')), 0), 1)
               END AS pct_ssn_confirmado_por_usgs,
               round(100.0 * count(*) FILTER (WHERE f.resultado = 'ambas')
                     / nullif(count(*) FILTER (WHERE f.resultado IN ('ambas', 'solo_usgs')), 0), 1)
                     AS pct_usgs_encontrado_en_ssn
        FROM f JOIN dw.dim_rango_magnitud r USING (id_rango)
        GROUP BY r.id_rango, r.etiqueta, r.mag_min
        ORDER BY r.id_rango""", filtros()))


@app.get("/api/serie")
def serie():
    return jsonify(consulta(HECHOS + """
        SELECT anio,
               count(*) FILTER (WHERE resultado IN ('ambas', 'solo_ssn'))                         AS eventos_ssn,
               count(*) FILTER (WHERE resultado IN ('ambas', 'solo_usgs', 'fuera_de_cobertura'))  AS eventos_usgs,
               count(*) FILTER (WHERE resultado = 'ambas')                                       AS pares
        FROM f GROUP BY anio ORDER BY anio""", filtros()))


@app.get("/api/concordancia")
def concordancia():
    p = filtros()
    return jsonify(
        decada=consulta(PARES + """
            SELECT (anio / 10) * 10 AS decada, count(*) AS pares,
                   round(avg(distancia_km)::numeric, 1)        AS distancia_media_km,
                   round(avg(abs(delta_magnitud))::numeric, 2) AS delta_mag_abs_media,
                   round(avg(abs(delta_segundos))::numeric, 1) AS delta_seg_abs_media
            FROM p GROUP BY 1 ORDER BY 1""", p),
        tipo=consulta(PARES + """
            SELECT coalesce(tipo_mag_usgs, '(sin tipo)') AS tipo_mag_usgs, count(*) AS pares,
                   round(avg(delta_magnitud)::numeric, 2)     AS delta_mag_media,
                   round(stddev_samp(delta_magnitud)::numeric, 2) AS delta_mag_desv,
                   round((percentile_cont(0.5) WITHIN GROUP (ORDER BY delta_magnitud))::numeric, 2) AS delta_mag_mediana
            FROM p GROUP BY 1 HAVING count(*) >= 10 ORDER BY pares DESC""", p),
        origen=consulta("""
            SELECT CASE WHEN independiente THEN 'Calculada por otra red (independiente)'
                        ELSE 'Aportada por el SSN (UNM, UNAM)' END AS origen,
                   count(*) AS pares,
                   round((percentile_cont(0.5) WITHIN GROUP (ORDER BY distancia_km))::numeric, 1) AS distancia_mediana_km,
                   round(avg(abs(delta_magnitud))::numeric, 2)  AS delta_mag_abs_media,
                   round(100.0 * avg((abs(delta_magnitud) < 0.05)::int), 1) AS pct_mag_identica,
                   round(avg(abs(delta_segundos))::numeric, 1)  AS delta_seg_abs_media
            FROM dw.v_pares
            WHERE variante = %(variante)s AND anio BETWEEN %(desde)s AND %(hasta)s
              AND mag_ssn >= %(mag_min)s
            GROUP BY independiente ORDER BY independiente DESC""", p),
        estado=consulta(HECHOS + """
            SELECT coalesce(s.estado, '(sin estado / mar)') AS estado,
                   count(*)                                   AS sismos_ssn,
                   count(*) FILTER (WHERE f.resultado = 'ambas') AS confirmados_usgs,
                   round(100.0 * count(*) FILTER (WHERE f.resultado = 'ambas') / count(*), 1) AS pct_confirmado,
                   round(avg(f.distancia_km)::numeric, 1)     AS distancia_media_km
            FROM f JOIN dw.dim_sismo s ON s.id_sismo = f.id_sismo_ssn
            WHERE f.resultado IN ('ambas', 'solo_ssn')
            GROUP BY 1 HAVING count(*) >= 10
            ORDER BY sismos_ssn DESC""", p),
    )


HISTOGRAMAS = {                       # variable: (mínimo, máximo, número de barras)
    "delta_magnitud": (-2.0, 2.0, 40),
    "distancia_km": (0.0, 150.0, 30),
    "delta_segundos": (-60.0, 60.0, 40),
}


@app.get("/api/histograma/<variable>")
def histograma(variable: str):
    if variable not in HISTOGRAMAS:
        abort(404)
    lo, hi, n = HISTOGRAMAS[variable]
    p = {**filtros(), "lo": lo, "hi": hi, "n": n}
    filas = consulta(PARES + f"""
        SELECT least(greatest(width_bucket({variable}, %(lo)s, %(hi)s, %(n)s), 1), %(n)s) AS barra,
               count(*) AS n
        FROM p WHERE {variable} IS NOT NULL
        GROUP BY 1 ORDER BY 1""", p)
    ancho = (hi - lo) / n
    conteo = {f["barra"]: f["n"] for f in filas}
    return jsonify([{"desde": round(lo + (b - 1) * ancho, 3), "hasta": round(lo + b * ancho, 3),
                     "n": conteo.get(b, 0)} for b in range(1, n + 1)])


@app.get("/api/dispersion")
def dispersion():
    """Pares agregados en celdas de 0.1 de magnitud (evita la sobreposición de puntos)."""
    return jsonify(consulta(PARES + """
        SELECT round(mag_ssn::numeric, 1) AS mag_ssn, round(mag_usgs::numeric, 1) AS mag_usgs, count(*) AS n
        FROM p GROUP BY 1, 2 ORDER BY 3""", filtros()))


@app.get("/api/eventos")
def eventos():
    p = filtros()
    total = consulta(HECHOS + " SELECT resultado, count(*) AS n FROM f "
                     "WHERE resultado <> 'fuera_de_cobertura' GROUP BY 1", p)
    filas = consulta(HECHOS + f"""
        SELECT f.resultado,
               coalesce(CASE WHEN f.variante = 'dw_original' THEN s.fecha_hora_dw
                             ELSE s.fecha_hora_utc END, u.fecha_hora_utc) AS fecha,
               s.fecha_corregida, s.fecha_hora_dw,
               s.magnitud AS mag_ssn, u.magnitud AS mag_usgs, u.tipo_magnitud,
               s.latitud AS lat_ssn, s.longitud AS lon_ssn,
               u.latitud AS lat_usgs, u.longitud AS lon_usgs,
               s.profundidad_km AS prof_ssn, u.profundidad_km AS prof_usgs,
               s.lugar AS referencia_ssn, u.lugar AS lugar_usgs, u.id_externo AS id_usgs,
               u.red_localizacion, u.red_magnitud, f.independiente,
               round(f.distancia_km::numeric, 1) AS distancia_km,
               round(f.delta_magnitud::numeric, 2) AS delta_magnitud
        FROM f
        LEFT JOIN dw.dim_sismo s ON s.id_sismo = f.id_sismo_ssn
        LEFT JOIN dw.dim_sismo u ON u.id_sismo = f.id_sismo_usgs
        WHERE f.resultado <> 'fuera_de_cobertura'
        ORDER BY f.magnitud_ref DESC, fecha DESC
        LIMIT {LIMITE_MAPA}""", p)
    return jsonify(total={t["resultado"]: t["n"] for t in total}, limite=LIMITE_MAPA, eventos=filas)


@app.get("/api/discrepancias")
def discrepancias():
    return jsonify(consulta(PARES + """
        SELECT fecha_hora_ssn, mag_ssn, mag_usgs, tipo_mag_usgs,
               round(delta_magnitud::numeric, 2) AS delta_magnitud,
               round(distancia_km::numeric, 1)  AS distancia_km,
               referencia_ssn, lugar_usgs, id_usgs
        FROM p
        WHERE abs(delta_magnitud) >= 0.5 OR distancia_km >= 75
        ORDER BY abs(delta_magnitud) DESC, distancia_km DESC
        LIMIT 40""", filtros()))


@app.get("/api/solo/<fuente>")
def solo(fuente: str):
    if fuente == "usgs":
        sql = HECHOS + """
            SELECT u.fecha_hora_utc, u.magnitud, u.tipo_magnitud, u.profundidad_km,
                   u.lugar, u.id_externo AS id_usgs, u.estatus_revision
            FROM f JOIN dw.dim_sismo u ON u.id_sismo = f.id_sismo_usgs
            WHERE f.resultado = 'solo_usgs'
            ORDER BY u.magnitud DESC, u.fecha_hora_utc DESC LIMIT 50"""
    elif fuente == "ssn":
        sql = HECHOS + """
            SELECT CASE WHEN f.variante = 'dw_original' THEN s.fecha_hora_dw
                        ELSE s.fecha_hora_utc END AS fecha_hora_utc,
                   s.magnitud, s.profundidad_km,
                   s.lugar AS referencia, s.estado, s.id_externo AS id_ssn
            FROM f JOIN dw.dim_sismo s ON s.id_sismo = f.id_sismo_ssn
            WHERE f.resultado = 'solo_ssn'
            ORDER BY s.magnitud DESC, s.fecha_hora_utc DESC LIMIT 50"""
    else:
        abort(404)
    return jsonify(consulta(sql, filtros()))


@app.get("/api/diagnostico")
def diagnostico():
    """Compara las dos variantes de fecha del SSN dentro del periodo y la magnitud
    elegidos (aquí se ignora el selector de variante: se muestran ambas)."""
    p = filtros()
    base = """
        FROM dw.fact_cruce_sismo f
        JOIN dw.dim_tiempo t ON t.id_tiempo = f.id_tiempo
        JOIN dw.dim_sismo s  ON s.id_sismo = f.id_sismo_ssn
        WHERE f.resultado IN ('ambas', 'solo_ssn')
          AND t.anio BETWEEN %(desde)s AND %(hasta)s
          AND f.magnitud_ref >= %(mag_min)s""" + ORIGEN_HECHOS
    return jsonify(
        horas=consulta("""
            SELECT f.variante, extract(hour FROM s.fecha_hora_utc AT TIME ZONE 'UTC')::int AS hora_utc,
                   count(*) AS sismos_ssn,
                   count(*) FILTER (WHERE f.resultado = 'ambas') AS emparejados,
                   round(100.0 * count(*) FILTER (WHERE f.resultado = 'ambas') / count(*), 1) AS pct_emparejado
            """ + base + " GROUP BY 1, 2 ORDER BY 2, 1", p),
        variantes=consulta("""
            SELECT f.variante, count(*) AS sismos_ssn,
                   count(*) FILTER (WHERE f.resultado = 'ambas') AS emparejados,
                   round(100.0 * count(*) FILTER (WHERE f.resultado = 'ambas') / count(*), 1) AS pct_emparejado
            """ + base + " GROUP BY 1", p),
        corregidas=consulta("""
            SELECT count(*) AS sismos_ssn,
                   count(*) FILTER (WHERE s.fecha_corregida) AS con_fecha_corregida,
                   round(100.0 * avg(s.fecha_corregida::int), 1) AS pct_corregidos
            FROM dw.dim_sismo s JOIN dw.dim_tiempo t ON t.id_tiempo = s.id_tiempo
            WHERE s.id_fuente = 1 AND t.anio BETWEEN %(desde)s AND %(hasta)s
              AND s.magnitud >= %(mag_min)s""", p)[0],
        ejemplos=consulta("""
            SELECT s.fecha_hora_dw, s.fecha_hora_utc, s.magnitud, s.lugar AS referencia,
                   u.fecha_hora_utc AS fecha_hora_usgs, u.lugar AS lugar_usgs, u.id_externo AS id_usgs
            FROM dw.fact_cruce_sismo f
            JOIN dw.dim_tiempo t ON t.id_tiempo = f.id_tiempo
            JOIN dw.dim_sismo s  ON s.id_sismo = f.id_sismo_ssn
            JOIN dw.dim_sismo u  ON u.id_sismo = f.id_sismo_usgs
            WHERE f.variante = 'corregida' AND f.resultado = 'ambas' AND s.fecha_corregida
              AND t.anio BETWEEN %(desde)s AND %(hasta)s AND f.magnitud_ref >= %(mag_min)s
              """ + ORIGEN_HECHOS + """
            ORDER BY s.magnitud DESC LIMIT 15""", p),
    )


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
