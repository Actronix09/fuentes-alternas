"""SHCP SRFT → staging → dimensiones originales → hecho oficial del warehouse.

Este archivo solo ordena los pasos:

  fuentes/shcp_srft.py  →  cargas/warehouse_srft.py  →  cargas/expedientes.py
"""
import sys

from cargas.warehouse_srft import cargar
from comun import Bitacora, esperar_bd, log
from fuentes.shcp_srft import PARAMETROS, extraer


def main():
    esperar_bd()
    registrar = Bitacora(PARAMETROS)
    try:
        meta = extraer(registrar)
        n = cargar(registrar, meta)
        registrar.terminar('ok', f'{n} obras oficiales SHCP integradas al warehouse original')
        return 0
    except Exception as e:
        log.exception('Falló el ETL de obras')
        registrar.terminar('error', str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main())
