#!/usr/bin/env python3
"""
exportar_estatico.py -- Genera consumo.json para la demo estática A PARTIR DEL
ALMACÉN REAL, sustituyendo el conjunto generado que se publicó originalmente.

Lee de PostgreSQL (el contenedor de warehouse/) y produce exactamente la
estructura que consumen index.html y mapa.html:

    {
      "anios": [...], "bimestres": [...], "alcaldias": [...], "indices": [...],
      "colonias_por_alcaldia": {alcaldia: [colonias]},
      "consumo_colonia": [ {anio, bimestre, fecha, alcaldia, colonia,
                            indice_des, consumo_total, consumo_prom,
                            consumo_total_dom, consumo_prom_dom,
                            consumo_total_mixto, consumo_prom_mixto,
                            consumo_total_no_dom, consumo_prom_no_dom,
                            latitud, longitud} ],
      "correlacion": [ {anio, bimestre, total_agua, temp_promedio,
                        dias_ola_calor, dias_frio, total_lluvia} ],
      "generado_en": "...", "nota": "..."
    }

Valida la salida antes de escribirla: si el almacén está vacío o la estructura
no cuadra, sale con código 1 y no toca el archivo publicado.

Uso:
    python exportar_estatico.py --dsn "postgresql://postgres:postgres@localhost:5433/data_warehouse" \
                                --salida consumo.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

CLAVES = ("anios", "bimestres", "alcaldias", "indices",
          "colonias_por_alcaldia", "consumo_colonia", "correlacion")

SQL_CONSUMO = """
SELECT t.anio, t.bimestre, t.fecha,
       u.alcaldia, u.colonia, u.latitud, u.longitud,
       i.indice_des,
       SUM(f.consumo_total)        AS consumo_total,
       AVG(f.consumo_prom)         AS consumo_prom,
       SUM(f.consumo_total_dom)    AS consumo_total_dom,
       AVG(f.consumo_prom_dom)     AS consumo_prom_dom,
       SUM(f.consumo_total_mixto)  AS consumo_total_mixto,
       AVG(f.consumo_prom_mixto)   AS consumo_prom_mixto,
       SUM(f.consumo_total_no_dom) AS consumo_total_no_dom,
       AVG(f.consumo_prom_no_dom)  AS consumo_prom_no_dom
FROM   fact_consumo_agua f
JOIN   dim_tiempo     t USING (id_tiempo)
JOIN   dim_ubicacion  u USING (id_ubicacion)
JOIN   dim_indice_des i USING (id_indice_des)
GROUP  BY t.anio, t.bimestre, t.fecha, u.alcaldia, u.colonia,
          u.latitud, u.longitud, i.indice_des
ORDER  BY t.anio, t.bimestre, u.alcaldia, u.colonia;
"""

SQL_CORRELACION = """
WITH clima AS (
    SELECT t.anio, t.bimestre,
           ROUND(AVG(fc.temp_promedio), 2)                        AS temp_promedio,
           COUNT(CASE WHEN fc.temp_maxima >= 28 THEN 1 END)        AS dias_ola_calor,
           COUNT(CASE WHEN fc.temp_minima <= 10 THEN 1 END)        AS dias_frio,
           ROUND(SUM(fc.lluvia_total), 2)                          AS total_lluvia
    FROM   fact_clima fc
    JOIN   dim_tiempo t USING (id_tiempo)
    GROUP  BY t.anio, t.bimestre
),
agua AS (
    SELECT t.anio, t.bimestre, ROUND(SUM(f.consumo_total), 2) AS total_agua
    FROM   fact_consumo_agua f
    JOIN   dim_tiempo t USING (id_tiempo)
    GROUP  BY t.anio, t.bimestre
)
SELECT a.anio, a.bimestre, a.total_agua, c.temp_promedio,
       c.dias_ola_calor, c.dias_frio, c.total_lluvia
FROM   agua a JOIN clima c USING (anio, bimestre)
ORDER  BY a.anio, a.bimestre;
"""


def num(v):
    """Decimal/None -> float/None, redondeado como el JSON original."""
    return None if v is None else round(float(v), 2)


def construir(cur) -> dict:
    cur.execute(SQL_CONSUMO)
    cols = [d[0] for d in cur.description]
    consumo, colonias, alcaldias, indices, anios, bimestres = [], {}, set(), set(), set(), set()

    for fila in cur.fetchall():
        r = dict(zip(cols, fila))
        alcaldias.add(r["alcaldia"])
        indices.add(r["indice_des"])
        anios.add(int(r["anio"]))
        bimestres.add(int(r["bimestre"]))
        colonias.setdefault(r["alcaldia"], set()).add(r["colonia"])
        consumo.append({
            "anio": int(r["anio"]),
            "bimestre": int(r["bimestre"]),
            "fecha": r["fecha"].isoformat() if r["fecha"] else None,
            "alcaldia": r["alcaldia"],
            "colonia": r["colonia"],
            "indice_des": r["indice_des"],
            "consumo_total": num(r["consumo_total"]),
            "consumo_prom": num(r["consumo_prom"]),
            "consumo_total_dom": num(r["consumo_total_dom"]),
            "consumo_prom_dom": num(r["consumo_prom_dom"]),
            "consumo_total_mixto": num(r["consumo_total_mixto"]),
            "consumo_prom_mixto": num(r["consumo_prom_mixto"]),
            "consumo_total_no_dom": num(r["consumo_total_no_dom"]),
            "consumo_prom_no_dom": num(r["consumo_prom_no_dom"]),
            "latitud": num(r["latitud"]),
            "longitud": num(r["longitud"]),
        })

    cur.execute(SQL_CORRELACION)
    ccols = [d[0] for d in cur.description]
    correlacion = []
    for fila in cur.fetchall():
        r = dict(zip(ccols, fila))
        correlacion.append({
            "anio": int(r["anio"]), "bimestre": int(r["bimestre"]),
            "total_agua": num(r["total_agua"]),
            "temp_promedio": num(r["temp_promedio"]),
            "dias_ola_calor": int(r["dias_ola_calor"] or 0),
            "dias_frio": int(r["dias_frio"] or 0),
            "total_lluvia": num(r["total_lluvia"]),
        })

    return {
        "anios": sorted(anios),
        "bimestres": sorted(bimestres),
        "alcaldias": sorted(alcaldias),
        "indices": sorted(indices),
        "colonias_por_alcaldia": {a: sorted(c) for a, c in sorted(colonias.items())},
        "consumo_colonia": consumo,
        "correlacion": correlacion,
        "generado_en": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nota": ("Exportado del almacen de datos real (SACMEX + Open-Meteo, 2019). "
                 "Generado automaticamente por scripts/exportar_estatico.py."),
    }


def validar(d: dict) -> list[str]:
    """Devuelve la lista de problemas. Vacía = se puede publicar."""
    p = []
    for k in CLAVES:
        if k not in d:
            p.append(f"falta la clave '{k}'")
    if not p:
        if not d["consumo_colonia"]:
            p.append("consumo_colonia esta vacio")
        if len(d["alcaldias"]) < 16:
            p.append(f"solo {len(d['alcaldias'])} alcaldias, se esperaban 16")
        if not d["correlacion"]:
            p.append("correlacion esta vacia")
        faltan = [r for r in d["consumo_colonia"][:100]
                  if r.get("consumo_total") is None]
        if faltan:
            p.append(f"{len(faltan)} de las primeras 100 filas sin consumo_total")
        sin_geo = sum(1 for r in d["consumo_colonia"] if r.get("latitud") is None)
        if sin_geo:
            p.append(f"{sin_geo} filas sin coordenada "
                     "(¿corrio warehouse/etl/2_geo.sql?)")
    return p


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--salida", default="consumo.json")
    ap.add_argument("--solo-validar", action="store_true",
                    help="genera y valida, pero no escribe el archivo")
    args = ap.parse_args()

    import psycopg2

    with psycopg2.connect(args.dsn) as conn, conn.cursor() as cur:
        datos = construir(cur)

    problemas = validar(datos)
    print(f"Registros exportados : {len(datos['consumo_colonia']):,}")
    print(f"Alcaldias            : {len(datos['alcaldias'])}")
    print(f"Colonias             : {sum(len(v) for v in datos['colonias_por_alcaldia'].values()):,}")
    print(f"Anios / bimestres    : {datos['anios']} / {datos['bimestres']}")
    print(f"Indices              : {datos['indices']}")
    print(f"Filas de correlacion : {len(datos['correlacion'])}")

    if problemas:
        print("\nVALIDACION FALLIDA -- no se escribe nada:")
        for x in problemas:
            print(f"  - {x}")
        return 1

    print("\nValidacion OK")
    if args.solo_validar:
        print("(--solo-validar: no se escribio el archivo)")
        return 0

    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, separators=(",", ":"))
    import os
    print(f"Escrito {args.salida} ({os.path.getsize(args.salida)/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
