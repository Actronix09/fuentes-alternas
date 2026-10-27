"""Parámetros del ETL del agua.

Se guardan en etl.ejecucion: si cambian, el ETL vuelve a cargar todo
(ver comun.ya_cargado). Los comparten las fuentes y las cargas.
"""
from __future__ import annotations

import os

# Recursos del Portal de Datos Abiertos de la CDMX (API CKAN)
RECURSOS = {
    "consumo": {"id": "2263bf74-c0ed-4e7c-bb9c-73f0624ac1a9",
                "paquete": "eb38823c-488a-49e8-a2cf-62e628fa246f", "conjunto": "consumo-agua"},
    "historico_2018_2021": {"id": "65a6b1a6-5d6e-49b9-aeed-ca7b22e8de03",
                            "paquete": "57ffc13a-7207-4b69-a9a9-2fef3fce6331", "conjunto": "reportes-de-agua"},
    "incidentes_2022_2024": {"id": "a8069e94-c7cb-45d7-8166-561e80884422",
                             "paquete": "57ffc13a-7207-4b69-a9a9-2fef3fce6331", "conjunto": "reportes-de-agua"},
}

PARAMETROS = {
    "recursos": {k: v["id"] for k, v in RECURSOS.items()},
    # Rectángulo de la Ciudad de México para validar coordenadas
    "lat_min": 19.00, "lat_max": 19.65, "lon_min": -99.40, "lon_max": -98.90,
    # Distancia máxima a la manzana más cercana para ubicar un reporte
    "distancia_max_m": float(os.environ.get("DISTANCIA_MAX_M", 1000)),
}

FORZAR_ETL = os.environ.get("FORZAR_ETL") == "1"
FORZAR_DESCARGA = os.environ.get("FORZAR_DESCARGA") == "1"
