"""Fuente SSN: el catálogo tal como quedó en el DW del programa original.

Se descargan dim_tiempo, dim_sismos y fact_impacto_sismos_imputed del
repositorio gabrielhuav/Seismic-Data-Visualization-System en un commit fijo,
sin modificarlos. Archivos: datos/original/ssn/<commit>_<script>.sql
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from comun import DIR_DATOS, descargar, registrar_consola
from parametros import FORZAR_DESCARGA, PARAMETROS, dentro_de_mexico

DIRECTORIO = DIR_DATOS / "original" / "ssn"
RAW_SSN = ("https://raw.githubusercontent.com/gabrielhuav/Seismic-Data-Visualization-System/"
           "{commit}/sql/{archivo}")
ARCHIVOS = ("02-dim_tiempo.sql", "03-dim_sismos.sql", "05-fact_impacto_sismos_imputed.sql")

# El catálogo del SSN publica la fecha y la hora en tiempo del centro de México
# y, aparte, la fecha y la hora UTC. El DW del paper combinó la FECHA LOCAL con
# la HORA UTC, así que todo sismo ocurrido entre ~18:00 y 23:59 hora del centro
# quedó con la fecha de un día antes. Se recupera el instante UTC real con:
#   - desde 1996: la zona America/Mexico_City (incluye el horario de verano
#     1996-2022, con el caso especial de 2001);
#   - antes de 1996: UTC−6 fijo. La base de zonas horarias registra la hora
#     media local (−6:36) hasta 1922 y periodos en −7, pero el SSN expresa la
#     hora local histórica como hora del centro; el cruce con el USGS lo confirma.
ZONA_SSN = ZoneInfo("America/Mexico_City")
HORA_CENTRO = dt.timezone(dt.timedelta(hours=-6))
INICIO_HORARIO_VERANO = dt.date(1996, 1, 1)


def instante_utc(fecha_local: dt.date, hora_utc: dt.time) -> dt.datetime:
    """Instante UTC con hora hora_utc cuyo día local (centro de México) es fecha_local."""
    zona = ZONA_SSN if fecha_local >= INICIO_HORARIO_VERANO else HORA_CENTRO
    for dias in (0, 1, -1):
        candidato = dt.datetime.combine(fecha_local + dt.timedelta(days=dias), hora_utc,
                                        tzinfo=dt.timezone.utc)
        if candidato.astimezone(zona).date() == fecha_local:
            return candidato
    return dt.datetime.combine(fecha_local, hora_utc, tzinfo=dt.timezone.utc)


def extraer(registrar) -> dict[str, Path]:
    commit = PARAMETROS["ssn_repo_commit"]
    rutas = {}
    for archivo in ARCHIVOS:
        rutas[archivo] = descargar(RAW_SSN.format(commit=commit, archivo=archivo),
                                   DIRECTORIO / f"{commit[:7]}_{archivo}",
                                   forzar=FORZAR_DESCARGA)
    registrar("extraccion", "SSN: dim_sismos, dim_tiempo y fact_impacto_sismos_imputed del DW del paper", 3,
              f"commit {commit[:7]} de gabrielhuav/Seismic-Data-Visualization-System")
    return rutas


_NUM = r"(NULL|-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
_TXT = r"(NULL|'(?:[^']|'')*')"
RE_SISMO = re.compile(rf"VALUES \((\d+), {_NUM}, {_NUM}, {_NUM}, {_NUM}, {_TXT}, {_TXT}, {_TXT}\);")
RE_TIEMPO = re.compile(rf"VALUES \((\d+), {_TXT}, {_TXT}, ")


def _txt(token: str) -> str | None:
    return None if token == "NULL" else token[1:-1].replace("''", "'")


def _num(token: str) -> float | None:
    return None if token == "NULL" else float(token)


def validar(rutas: dict[str, Path], registrar) -> list[list]:
    tiempos = {}
    with open(rutas["02-dim_tiempo.sql"], encoding="utf-8") as f:
        for linea in f:
            m = RE_TIEMPO.search(linea)
            if m:
                tiempos[int(m.group(1))] = (_txt(m.group(2)), _txt(m.group(3)))

    filas, leidos, sin_parsear, corregidos = [], 0, 0, 0
    descartes = {"sin fecha u hora": 0, "sin magnitud o coordenadas": 0,
                 "fuera del rectángulo de México": 0}
    with open(rutas["03-dim_sismos.sql"], encoding="utf-8") as f:
        for linea in f:
            if not linea.startswith("INSERT"):
                continue
            leidos += 1
            m = RE_SISMO.search(linea)
            if not m:
                sin_parsear += 1
                continue
            id_sismo = int(m.group(1))
            mag, lat, lon, prof = (_num(m.group(i)) for i in range(2, 6))
            hora, fecha = tiempos.get(id_sismo, (None, None))
            if not hora or not fecha:
                descartes["sin fecha u hora"] += 1
                continue
            if mag is None or lat is None or lon is None:
                descartes["sin magnitud o coordenadas"] += 1
                continue
            if not dentro_de_mexico(lat, lon):
                descartes["fuera del rectángulo de México"] += 1
                continue
            fecha_local = dt.date.fromisoformat(fecha)
            hora_utc = dt.time.fromisoformat(hora)
            marca_dw = dt.datetime.combine(fecha_local, hora_utc, tzinfo=dt.timezone.utc)
            marca_real = instante_utc(fecha_local, hora_utc)
            corregidos += marca_real != marca_dw
            filas.append([id_sismo, fecha_local, hora_utc, marca_dw, marca_real, mag, lat, lon, prof,
                          _txt(m.group(6)), _txt(m.group(7)), _txt(m.group(8))])

    registrar("validacion", "SSN: registros leídos", leidos,
              f"{len(tiempos):,} registros de tiempo; {sin_parsear} líneas no reconocidas")
    for regla, n in descartes.items():
        registrar("validacion", f"SSN descartados: {regla}", n)
    registrar("validacion", "SSN: registros válidos", len(filas))
    registrar("validacion", "SSN: fecha reconstruida en UTC (el DW une fecha local con hora UTC)",
              corregidos, f"{100 * corregidos / max(len(filas), 1):.1f} % de los sismos quedaban con un día de menos")
    return filas


if __name__ == "__main__":
    print(f"{len(validar(extraer(registrar_consola), registrar_consola)):,} sismos SSN válidos")
