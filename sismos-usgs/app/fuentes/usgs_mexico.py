"""Fuente USGS ComCat para el rectángulo de México (cruce con el SSN).

Extracción por la API FDSN en bloques que no superan el límite de 20 000
eventos por consulta; validación de tipo, magnitud, fecha y rectángulo.
Archivos: datos/usgs/mexico/usgs_AAAAMMDD_AAAAMMDD_m3.5.csv
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import requests

from comun import DIR_DATOS, descargar, log, nueva_sesion, registrar_consola
from parametros import FORZAR_DESCARGA, PARAMETROS, dentro_de_mexico

DIRECTORIO = DIR_DATOS / "usgs" / "mexico"
FDSN = "https://earthquake.usgs.gov/fdsnws/event/1"
LIMITE_API = 20_000

COLUMNAS_USGS = ["time", "latitude", "longitude", "depth", "mag", "magType", "nst", "gap",
                 "dmin", "rms", "net", "id", "updated", "place", "type", "horizontalError",
                 "depthError", "magError", "magNst", "status", "locationSource", "magSource"]


def periodos_base(anio_ini: int, hoy: dt.date) -> list[tuple[dt.date, dt.date]]:
    """Décadas hasta 1989 y años completos desde 1990: bloques chicos que se
    pueden guardar en caché (un año cerrado ya no cambia)."""
    cortes, a = [], anio_ini
    while a < 1990:
        b = min(a + 10, 1990)
        cortes.append((dt.date(a, 1, 1), dt.date(b, 1, 1)))
        a = b
    for a in range(max(1990, anio_ini), hoy.year + 1):
        cortes.append((dt.date(a, 1, 1), min(dt.date(a + 1, 1, 1), hoy + dt.timedelta(days=1))))
    return cortes


def filtros_fdsn(ini: dt.date, fin: dt.date) -> dict:
    p = PARAMETROS
    return {
        "starttime": ini.isoformat(), "endtime": fin.isoformat(),
        "minlatitude": p["lat_min"], "maxlatitude": p["lat_max"],
        "minlongitude": p["lon_min"], "maxlongitude": p["lon_max"],
        "minmagnitude": p["usgs_mag_min"],
    }


def extraer(registrar, hoy: dt.date) -> list[Path]:
    sesion = nueva_sesion()
    pendientes = periodos_base(PARAMETROS["anio_inicio"], hoy)
    archivos, consultas, divisiones = [], 0, 0
    while pendientes:
        ini, fin = pendientes.pop(0)
        reciente = fin >= hoy - dt.timedelta(days=2)       # el bloque actual siempre se refresca
        etiqueta_fin = "vigente" if reciente else f"{fin:%Y%m%d}"
        destino = DIRECTORIO / f"usgs_{ini:%Y%m%d}_{etiqueta_fin}_m{PARAMETROS['usgs_mag_min']}.csv"
        if destino.exists() and not reciente and not FORZAR_DESCARGA:
            archivos.append(destino)
            continue

        try:
            r = sesion.get(f"{FDSN}/count", params={**filtros_fdsn(ini, fin), "format": "geojson"}, timeout=60)
            r.raise_for_status()
            n = r.json()["count"]
        except (requests.RequestException, ValueError) as e:
            # Sin conexión con el USGS se reutiliza el último bloque descargado del periodo en curso.
            if not destino.exists():
                raise
            log.warning("No se pudo actualizar %s (%s); se usa la copia local", destino.name, e)
            registrar("extraccion", f"USGS {ini} → {fin}: sin conexión, se usa la última copia local", None,
                      destino.name)
            archivos.append(destino)
            continue
        consultas += 1
        if n >= LIMITE_API:
            medio = ini + (fin - ini) / 2
            pendientes[0:0] = [(ini, medio), (medio, fin)]
            divisiones += 1
            registrar("extraccion", f"USGS {ini} → {fin}: supera el límite de la API, se divide en dos", n)
            continue
        if n == 0:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(",".join(COLUMNAS_USGS) + "\n", encoding="utf-8")
        else:
            descargar(f"{FDSN}/query", destino, forzar=True, sesion=sesion,
                      params={**filtros_fdsn(ini, fin), "format": "csv", "orderby": "time-asc"})
        archivos.append(destino)

    registrar("extraccion", "USGS ComCat: bloques descargados o tomados de caché", len(archivos),
              f"{consultas} consultas de conteo, {divisiones} periodos divididos por el límite de {LIMITE_API:,}")
    return archivos


def validar(archivos: list[Path], registrar) -> list[list]:
    vistos, filas = set(), []
    descartes = {"duplicado entre bloques": 0, "no es sismo (cantera, explosión…)": 0,
                 "sin magnitud o sin fecha": 0, "fuera del rectángulo de México": 0}
    leidos = 0
    for archivo in archivos:
        with open(archivo, encoding="utf-8", newline="") as f:
            for reg in csv.DictReader(f):
                leidos += 1
                if reg["id"] in vistos:
                    descartes["duplicado entre bloques"] += 1
                    continue
                vistos.add(reg["id"])
                if reg["type"] != "earthquake":
                    descartes["no es sismo (cantera, explosión…)"] += 1
                    continue
                if not reg["mag"] or not reg["time"]:
                    descartes["sin magnitud o sin fecha"] += 1
                    continue
                if not dentro_de_mexico(float(reg["latitude"]), float(reg["longitude"])):
                    descartes["fuera del rectángulo de México"] += 1
                    continue
                filas.append([reg[c] if reg[c] != "" else None for c in COLUMNAS_USGS])

    registrar("validacion", "USGS: registros leídos", leidos)
    for regla, n in descartes.items():
        registrar("validacion", f"USGS descartados: {regla}", n)
    registrar("validacion", "USGS: registros válidos", len(filas))
    return filas


if __name__ == "__main__":
    hoy = dt.datetime.now(dt.timezone.utc).date()
    print(f"{len(validar(extraer(registrar_consola, hoy), registrar_consola)):,} eventos USGS válidos")
