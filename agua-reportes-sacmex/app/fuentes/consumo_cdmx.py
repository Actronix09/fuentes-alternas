"""Fuente: consumo de agua del 1er semestre de 2019 (Portal de Datos Abiertos CDMX).

Es la misma fuente del paper; también alimenta el DW original (cargas/integrar_original.py).
Validación: fuera las filas con alcaldía o colonia "NA", como el paper.
Archivo: datos/consumo/consumo.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

from comun import DIR_DATOS, nueva_sesion, registrar_consola
from fuentes.ckan_cdmx import extraer_recurso
from limpieza import coordenadas, normalizar, valor

DIRECTORIO = DIR_DATOS / "consumo"
ARCHIVO = DIRECTORIO / "consumo.csv"

COLUMNAS_CONSUMO = ["fecha_referencia", "anio", "bimestre", "consumo_total_mixto", "consumo_prom_dom",
                    "consumo_total_dom", "consumo_prom_mixto", "consumo_total", "consumo_prom",
                    "consumo_prom_no_dom", "consumo_total_no_dom", "indice_des", "colonia", "alcaldia",
                    "latitud", "longitud"]


def extraer(registrar, sesion=None) -> dict[str, dict]:
    return {"consumo": extraer_recurso("consumo", DIRECTORIO, sesion or nueva_sesion(), registrar)}


def validar(archivo: Path, registrar) -> list[list]:
    filas, leidos = [], 0
    descartes = {"alcaldía o colonia NA": 0, "sin fecha": 0}
    sin_coordenadas = 0
    with open(archivo, encoding="utf-8-sig", newline="") as f:
        for reg in csv.DictReader(f):
            leidos += 1
            alcaldia_n, colonia_n = normalizar(reg["alcaldia"]), normalizar(reg["colonia"])
            if not alcaldia_n or not colonia_n:
                descartes["alcaldía o colonia NA"] += 1
                continue
            if not valor(reg["fecha_referencia"]):
                descartes["sin fecha"] += 1
                continue
            lat, lon, ok = coordenadas(reg["latitud"], reg["longitud"])
            sin_coordenadas += not ok
            fila = [valor(reg[c]) for c in COLUMNAS_CONSUMO]
            fila[-2], fila[-1] = lat, lon
            filas.append(fila + [alcaldia_n, colonia_n])
    registrar("validacion", "Consumo: registros leídos", leidos)
    for regla, n in descartes.items():
        registrar("validacion", f"Consumo descartados: {regla}", n)
    registrar("validacion", "Consumo: sin coordenadas válidas (se conservan)", sin_coordenadas)
    registrar("validacion", "Consumo: registros válidos", len(filas))
    return filas


if __name__ == "__main__":
    meta = extraer(registrar_consola)
    print(f"{len(validar(meta['consumo']['archivo'], registrar_consola)):,} filas de consumo válidas")
