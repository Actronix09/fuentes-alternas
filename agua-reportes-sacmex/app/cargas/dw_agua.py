"""Carga y transformación del DW del agua en el esquema dw.

COPY de las filas validadas por fuentes.consumo_cdmx y fuentes.reportes_sacmex
a staging, dimensiones (sql/10_dimensiones.sql), puntos de manzana, hechos y
ubicación de cada reporte en una colonia (sql/20_hechos.sql), en una sola transacción.
"""
from __future__ import annotations

from pathlib import Path

from comun import conectar
from fuentes.consumo_cdmx import COLUMNAS_CONSUMO
from fuentes.reportes_sacmex import COLUMNAS_REPORTE
from parametros import PARAMETROS

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def cargar(meta: dict[str, dict], consumo: list[list], reportes: list[list], registrar) -> str:
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE staging.consumo, staging.reporte_agua RESTART IDENTITY")
            columnas = ", ".join(COLUMNAS_CONSUMO + ["alcaldia_norm", "colonia_norm"])
            with cur.copy(f"COPY staging.consumo ({columnas}) FROM STDIN") as cp:
                for fila in consumo:
                    cp.write_row(fila)
            registrar("carga", "COPY staging.consumo", len(consumo))
            with cur.copy(f"COPY staging.reporte_agua ({', '.join(COLUMNAS_REPORTE)}) FROM STDIN") as cp:
                for fila in reportes:
                    cp.write_row(fila)
            registrar("carga", "COPY staging.reporte_agua", len(reportes))

            cur.execute("TRUNCATE etl.recurso")
            for m in meta.values():
                cur.execute(
                    "INSERT INTO etl.recurso (id_recurso, conjunto, nombre, url, ultima_modificacion, bytes) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    [m["id"], m["conjunto"], m["nombre"], m["url"], m["ultima_modificacion"], m["bytes"]])

            cur.execute((SQL_DIR / "10_dimensiones.sql").read_text(encoding="utf-8"))
            for tabla in ("dw.dim_tiempo", "dw.dim_ubicacion", "dw.manzana", "dw.dim_indice_des",
                          "dw.dim_tipo_reporte", "dw.dim_medio_recepcion"):
                registrar("transformacion", f"Poblar {tabla}",
                          cur.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0])

            cur.execute("SELECT set_config('etl.distancia_max_m', %s, true)",
                        [str(PARAMETROS["distancia_max_m"])])
            cur.execute((SQL_DIR / "20_hechos.sql").read_text(encoding="utf-8"))
            registrar("transformacion", "Poblar dw.fact_consumo_agua",
                      cur.execute("SELECT count(*) FROM dw.fact_consumo_agua").fetchone()[0])
            for recurso, metodo, n in cur.execute(
                    "SELECT recurso, coalesce(metodo_ubicacion, 'sin ubicar'), count(*) "
                    "FROM dw.fact_reporte_agua GROUP BY 1, 2 ORDER BY 1, 2").fetchall():
                registrar("transformacion", f"Reportes {recurso} ubicados por {metodo}", n)
            total = cur.execute("SELECT count(*) FROM dw.fact_reporte_agua").fetchone()[0]
            registrar("transformacion", "Poblar dw.fact_reporte_agua", total)

            ev = cur.execute("SELECT puntaje, auc, spearman, precision_47 FROM dw.v_evaluacion_2019").fetchall()
            for puntaje, auc, rho, p47 in ev:
                registrar("transformacion", f"Evaluación 1er sem. 2019 · {puntaje}", None,
                          f"AUC {auc} · Spearman {rho} · precisión@47 {p47}")
        conn.commit()
    return f"{len(consumo):,} filas de consumo y {total:,} reportes cargados"
