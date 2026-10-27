"""Carga y transformación del cruce SSN ↔ USGS ComCat en el esquema dw.

COPY de las filas validadas por fuentes.usgs_mexico y fuentes.ssn_original a
staging, dimensiones (sql/10_dimensiones.sql) y emparejamiento uno a uno con
dw.fn_emparejar, en una sola transacción.
"""
from __future__ import annotations

from pathlib import Path

from comun import conectar
from fuentes.usgs_mexico import COLUMNAS_USGS
from parametros import PARAMETROS

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def cargar(filas_usgs: list[list], filas_ssn: list[list], registrar) -> str:
    p = PARAMETROS
    with conectar() as conn:                      # una sola transacción
        with conn.cursor() as cur:
            cur.execute("TRUNCATE staging.usgs_evento, staging.ssn_evento")
            cols = ", ".join(c.lower() for c in COLUMNAS_USGS)
            with cur.copy(f"COPY staging.usgs_evento ({cols}) FROM STDIN") as cp:
                for fila in filas_usgs:
                    cp.write_row(fila)
            registrar("carga", "COPY staging.usgs_evento", len(filas_usgs))

            with cur.copy("COPY staging.ssn_evento (id_sismo, fecha_local, hora_utc, fecha_hora_dw, "
                          "fecha_hora_utc, magnitud, latitud, longitud, profundidad, referencia, "
                          "estado, nombre_estado) FROM STDIN") as cp:
                for fila in filas_ssn:
                    cp.write_row(fila)
            registrar("carga", "COPY staging.ssn_evento", len(filas_ssn))

            cur.execute((SQL_DIR / "10_dimensiones.sql").read_text(encoding="utf-8"))
            for tabla in ("dw.dim_tiempo", "dw.dim_sismo"):
                n = cur.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]
                registrar("transformacion", f"Poblar {tabla}", n)

            # Primero con las fechas tal como están en el DW (diagnóstico) y
            # después con las fechas corregidas (la que usa el análisis).
            for variante in ("dw_original", "corregida"):
                resultados = cur.execute(
                    "SELECT resultado, eventos FROM dw.fn_emparejar(%s, %s, %s, %s, %s, %s, %s, %s)",
                    [variante, p["ventana_seg"], p["distancia_km"], p["ventana_seg_hist"],
                     p["distancia_km_hist"], p["anio_corte_hist"], p["ssn_mag_min"],
                     p["delta_mag_max"]],
                ).fetchall()
                for resultado, n in resultados:
                    registrar("transformacion", f"Emparejamiento ({variante}) → {resultado}", n)
        conn.commit()
    return ", ".join(f"{r}: {n:,}" for r, n in resultados)
