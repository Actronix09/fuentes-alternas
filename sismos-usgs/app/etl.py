"""ETL del Sistema 1: validación cruzada del catálogo sísmico SSN ↔ USGS ComCat.

Fases (las mismas del pipeline del paper "Cuando México tiembla"):

  1. Extracción      USGS ComCat por la API FDSN, en bloques que no superan
                     el límite de 20 000 eventos por consulta, y el catálogo
                     SSN tal como quedó en el DW del paper (repositorio, commit fijo).
  2. Validación      Rectángulo de México, magnitud y fecha válidas, solo
                     sismos (sin explosiones de cantera) y sin duplicados.
  3. Carga           COPY masivo a las tablas staging.
  4. Transformación  SQL: dimensiones, emparejamiento uno a uno y hechos.
  5. Integración     El DW original del paper se carga en public y recibe el
                     hecho public.fact_cruce_usgs.

Este archivo solo ordena los pasos. Cada fuente está en fuentes/ (descarga y
validación) y cada destino en PostgreSQL en cargas/:

  fuentes/usgs_mexico.py, fuentes/ssn_original.py  →  cargas/cruce_ssn_usgs.py
                                                   →  cargas/integrar_original.py
  fuentes/census_us.py, fuentes/statcan_ca.py      →  cargas/demografia.py
  fuentes/usgs_norteamerica.py, fuentes/limites.py →  cargas/norteamerica.py

Cada paso queda en etl.bitacora con el número de registros afectados.
"""
from __future__ import annotations

import datetime as dt
import sys

from cargas import cruce_ssn_usgs, demografia, norteamerica
from cargas.integrar_original import integrar_original
from comun import Bitacora, conectar, esperar_bd, log, ya_cargado
from fuentes import ssn_original, usgs_mexico
from parametros import FORZAR_ETL, PARAMETROS


def main() -> int:
    esperar_bd()
    # Módulos independientes: no cambian las reglas ni la bitácora del cruce sísmico.
    # Norteamérica va después de demografía porque enlaza con sus regiones.
    log.info("Demografía oficial: %s observaciones", demografia.ejecutar())
    log.info("Catálogo de Norteamérica: %s", norteamerica.ejecutar())
    if not FORZAR_ETL and ya_cargado(PARAMETROS):
        log.info("La base ya tiene una carga exitosa con estos parámetros; no se repite. "
                 "Usa FORZAR_ETL=1 para recargar.")
        with conectar() as conn:
            integrado = conn.execute("SELECT to_regclass('public.fact_cruce_usgs')").fetchone()[0]
        if integrado is None:
            ssn_original.extraer(lambda *a, **k: None)
            log.info("Cruce integrado al DW original: %s registros", f"{integrar_original():,}")
        return 0

    registrar = Bitacora(PARAMETROS)
    try:
        hoy = dt.datetime.now(dt.timezone.utc).date()
        archivos_usgs = usgs_mexico.extraer(registrar, hoy)
        rutas_ssn = ssn_original.extraer(registrar)
        filas_usgs = usgs_mexico.validar(archivos_usgs, registrar)
        filas_ssn = ssn_original.validar(rutas_ssn, registrar)
        resumen = cruce_ssn_usgs.cargar(filas_usgs, filas_ssn, registrar)
        integrar_original(registrar)
        registrar.terminar("ok", resumen)
        log.info("ETL terminado: %s", resumen)
        return 0
    except Exception as e:                              # noqa: BLE001 — se registra y se reporta
        log.exception("El ETL falló")
        registrar.terminar("error", f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
