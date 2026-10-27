"""Fuente alterna: reportes ciudadanos de agua SACMEX 2018-2021 y 2022-2024 (Portal CDMX).

Validación: fecha y tipo obligatorios, folios únicos, coordenadas dentro de la
CDMX y nombres normalizados para cruzarlos con las colonias.
Archivos: datos/reportes/historico_2018_2021.csv y datos/reportes/incidentes_2022_2024.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

from comun import DIR_DATOS, nueva_sesion, registrar_consola
from fuentes.ckan_cdmx import extraer_recurso
from limpieza import coordenadas, normalizar, valor

DIRECTORIO = DIR_DATOS / "reportes"
RECURSOS = ("historico_2018_2021", "incidentes_2022_2024")

COLUMNAS_REPORTE = ["recurso", "folio", "fecha", "hora", "clasificacion", "reporte", "medio",
                    "alcaldia", "colonia", "alcaldia_norm", "colonia_norm", "latitud", "longitud"]


def extraer(registrar, sesion=None) -> dict[str, dict]:
    sesion = sesion or nueva_sesion()
    return {clave: extraer_recurso(clave, DIRECTORIO, sesion, registrar) for clave in RECURSOS}


def validar(archivos: dict[str, Path], registrar) -> list[list]:
    filas = []
    for recurso, archivo in archivos.items():
        historico = recurso == "historico_2018_2021"
        vistos, leidos, fuera_cdmx = set(), 0, 0
        descartes = {"folio repetido": 0, "sin fecha": 0, "sin tipo de reporte": 0}
        with open(archivo, encoding="utf-8-sig", newline="") as f:
            for reg in csv.DictReader(f):
                leidos += 1
                folio = valor(reg["folio"] if historico else reg["id_reporte"])
                if not folio or folio in vistos:
                    descartes["folio repetido"] += 1
                    continue
                vistos.add(folio)
                fecha = valor(reg["fecha"] if historico else reg["fecha_reporte"])
                if not fecha:
                    descartes["sin fecha"] += 1
                    continue
                reporte = valor(reg["tipo_de_falla"] if historico else reg["reporte"])
                if not reporte:
                    descartes["sin tipo de reporte"] += 1
                    continue
                lat, lon, ok = coordenadas(reg["latitud"], reg["longitud"])
                fuera_cdmx += not ok
                if historico:
                    # El sistema anterior solo registraba fallas de agua potable
                    clasificacion, medio, hora = "Agua Potable", "No registrado (sistema anterior a 2022)", None
                    alcaldia, colonia = valor(reg["alcaldia"]), valor(reg["colonia_datos_abiertos"])
                else:
                    clasificacion = valor(reg["clasificacion"]) or "Sin clasificación"
                    medio = valor(reg["medio_recepcion"]) or "No registrado"
                    hora = valor(reg["hora_reporte"])
                    alcaldia, colonia = valor(reg["alcaldia_catalogo"]), valor(reg["colonia_catalogo"])
                filas.append([recurso, folio, fecha, hora, clasificacion, reporte, medio,
                              alcaldia, colonia, normalizar(alcaldia), normalizar(colonia), lat, lon])
        registrar("validacion", f"Reportes {recurso}: registros leídos", leidos)
        for regla, n in descartes.items():
            registrar("validacion", f"Reportes {recurso} descartados: {regla}", n)
        registrar("validacion", f"Reportes {recurso}: coordenadas fuera de la CDMX (se anulan)", fuera_cdmx)
    registrar("validacion", "Reportes: registros válidos", len(filas))
    return filas


if __name__ == "__main__":
    meta = extraer(registrar_consola)
    print(f"{len(validar({k: m['archivo'] for k, m in meta.items()}, registrar_consola)):,} reportes válidos")
