"""ETL del Sistema 2: consumo de agua en la CDMX validado con reportes ciudadanos.

Fases (las mismas del pipeline del paper del agua):

  1. Extracción      Tres recursos del Portal de Datos Abiertos de la CDMX (API CKAN):
                     el consumo del 1er semestre de 2019 (fuente del paper) y los
                     reportes ciudadanos de agua 2018-2021 y 2022-2024 (fuente alterna).
  2. Validación      Consumo: fuera las filas con alcaldía o colonia "NA" (como el paper).
                     Reportes: fecha y tipo obligatorios, folios únicos, coordenadas
                     dentro de la CDMX y nombres normalizados para cruzarlos.
  3. Carga           COPY masivo a staging.
  4. Transformación  SQL: dimensiones, puntos de manzana, hechos y ubicación de cada
                     reporte en una colonia (por nombre o por la manzana más cercana).

Este archivo solo ordena los pasos. Cada fuente está en fuentes/ (descarga y
validación) y cada destino en PostgreSQL en cargas/:

  fuentes/consumo_cdmx.py, fuentes/reportes_sacmex.py  →  cargas/dw_agua.py
  fuentes/consumo_cdmx.py, fuentes/clima_original.py   →  cargas/integrar_original.py
  DW integrado                                         →  cargas/grafo.py (RDF)

Cada paso queda en etl.bitacora con el número de registros afectados.
"""
from __future__ import annotations

import sys

from cargas import dw_agua
from cargas.grafo import materializar
from cargas.integrar_original import integrar_original
from comun import Bitacora, esperar_bd, log, nueva_sesion, ya_cargado
from fuentes import consumo_cdmx, reportes_sacmex
from parametros import FORZAR_ETL, PARAMETROS


def main() -> int:
    esperar_bd()
    if not FORZAR_ETL and ya_cargado(PARAMETROS):
        integrar_original()
        materializar()
        log.info("La base ya tiene una carga exitosa con estos parámetros; no se repite. "
                 "Usa FORZAR_ETL=1 para recargar.")
        return 0

    registrar = Bitacora(PARAMETROS)
    try:
        sesion = nueva_sesion()
        meta = {**consumo_cdmx.extraer(registrar, sesion), **reportes_sacmex.extraer(registrar, sesion)}
        consumo = consumo_cdmx.validar(meta["consumo"]["archivo"], registrar)
        reportes = reportes_sacmex.validar({k: meta[k]["archivo"] for k in reportes_sacmex.RECURSOS}, registrar)
        resumen = dw_agua.cargar(meta, consumo, reportes, registrar)
        integrar_original(registrar)
        materializar(registrar)
        registrar.terminar("ok", resumen)
        log.info("ETL terminado: %s", resumen)
        return 0
    except Exception as e:                                # noqa: BLE001 — se registra y se reporta
        log.exception("El ETL falló")
        registrar.terminar("error", f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
