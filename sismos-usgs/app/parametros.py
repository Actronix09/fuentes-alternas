"""Parámetros del cruce SSN ↔ USGS ComCat.

Se guardan en etl.ejecucion: si cambian, el ETL vuelve a cargar todo
(ver comun.ya_cargado). Los comparten las fuentes y la carga del cruce.
"""
from __future__ import annotations

import os


def _float(nombre: str, defecto: float) -> float:
    return float(os.environ.get(nombre, defecto))


def _int(nombre: str, defecto: int) -> int:
    return int(os.environ.get(nombre, defecto))


PARAMETROS = {
    # Rectángulo de México usado por el pipeline del paper
    "lat_min": 14.0, "lat_max": 33.0, "lon_min": -118.0, "lon_max": -86.0,
    "anio_inicio": _int("ANIO_INICIO", 1900),
    # Se descarga el USGS desde 3.5 para no perder pares cuyo SSN es ≥ 4.0
    # pero que el USGS calculó ligeramente por debajo.
    "usgs_mag_min": _float("USGS_MAG_MIN", 3.5),
    "ssn_mag_min": _float("SSN_MAG_MIN", 4.0),
    # Tolerancias del emparejamiento (modernas e históricas)
    "ventana_seg": _float("VENTANA_SEG", 30),
    "distancia_km": _float("DISTANCIA_KM", 100),
    "ventana_seg_hist": _float("VENTANA_SEG_HIST", 120),
    "distancia_km_hist": _float("DISTANCIA_KM_HIST", 250),
    "delta_mag_max": _float("DELTA_MAG_MAX", 1.0),
    "anio_corte_hist": _int("ANIO_CORTE_HIST", 1964),
    # Versión exacta del DW del paper que se valida
    "ssn_repo_commit": os.environ.get("SSN_REPO_COMMIT", "8569667cf4f46fab640dba3f82a7b324ca7efaf7"),
}

FORZAR_ETL = os.environ.get("FORZAR_ETL") == "1"
FORZAR_DESCARGA = os.environ.get("FORZAR_DESCARGA") == "1"


def dentro_de_mexico(lat: float, lon: float) -> bool:
    p = PARAMETROS
    return p["lat_min"] <= lat <= p["lat_max"] and p["lon_min"] <= lon <= p["lon_max"]
