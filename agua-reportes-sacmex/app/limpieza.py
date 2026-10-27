"""Utilidades de limpieza compartidas por las fuentes de consumo y de reportes."""
from __future__ import annotations

import re
import unicodedata

from parametros import PARAMETROS


def normalizar(texto: str | None) -> str | None:
    """MAYÚSCULAS, sin acentos ni signos y con un solo espacio: 'Álvaro Obregón' → 'ALVARO OBREGON'."""
    if texto is None:
        return None
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()
    t = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", t)).strip()
    return None if t in ("", "NA", "N A") else t


def valor(texto: str | None) -> str | None:
    """Cadena vacía o 'NA' → NULL."""
    if texto is None:
        return None
    t = texto.strip()
    return None if t in ("", "NA") else t


def coordenadas(lat: str | None, lon: str | None) -> tuple[float | None, float | None, bool]:
    """(lat, lon, válidas). Fuera de la CDMX se anulan pero el registro se conserva."""
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        return None, None, False
    p = PARAMETROS
    if p["lat_min"] <= la <= p["lat_max"] and p["lon_min"] <= lo <= p["lon_max"]:
        return la, lo, True
    return None, None, False
