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
                     hecho public.fact_cruce_usgs (integrar_original.py).

Cada paso queda en etl.bitacora con el número de registros afectados.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from comun import (DIR_DATOS, Bitacora, conectar, descargar, esperar_bd, log,
                   nueva_sesion, ya_cargado)
from integrar_original import integrar_original


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

FDSN = "https://earthquake.usgs.gov/fdsnws/event/1"
LIMITE_API = 20_000
RAW_SSN = ("https://raw.githubusercontent.com/gabrielhuav/Seismic-Data-Visualization-System/"
           "{commit}/sql/{archivo}")

COLUMNAS_USGS = ["time", "latitude", "longitude", "depth", "mag", "magType", "nst", "gap",
                 "dmin", "rms", "net", "id", "updated", "place", "type", "horizontalError",
                 "depthError", "magError", "magNst", "status", "locationSource", "magSource"]

SQL_DIR = Path(__file__).parent / "sql"

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


# ---------------------------------------------------------------------------
# 1. EXTRACCIÓN
# ---------------------------------------------------------------------------
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


def extraer_usgs(registrar: Bitacora, hoy: dt.date) -> list[Path]:
    sesion = nueva_sesion()
    pendientes = periodos_base(PARAMETROS["anio_inicio"], hoy)
    archivos, consultas, divisiones = [], 0, 0
    while pendientes:
        ini, fin = pendientes.pop(0)
        reciente = fin >= hoy - dt.timedelta(days=2)       # el bloque actual siempre se refresca
        etiqueta_fin = "vigente" if reciente else f"{fin:%Y%m%d}"
        destino = DIR_DATOS / "usgs" / f"usgs_{ini:%Y%m%d}_{etiqueta_fin}_m{PARAMETROS['usgs_mag_min']}.csv"
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


def extraer_ssn(registrar: Bitacora) -> dict[str, Path]:
    commit = PARAMETROS["ssn_repo_commit"]
    rutas = {}
    for archivo in ("02-dim_tiempo.sql", "03-dim_sismos.sql", "05-fact_impacto_sismos_imputed.sql"):
        rutas[archivo] = descargar(RAW_SSN.format(commit=commit, archivo=archivo),
                                   DIR_DATOS / "ssn" / f"{commit[:7]}_{archivo}",
                                   forzar=FORZAR_DESCARGA)
    registrar("extraccion", "SSN: dim_sismos, dim_tiempo y fact_impacto_sismos_imputed del DW del paper", 3,
              f"commit {commit[:7]} de gabrielhuav/Seismic-Data-Visualization-System")
    return rutas


# ---------------------------------------------------------------------------
# 2. VALIDACIÓN Y LIMPIEZA
# ---------------------------------------------------------------------------
def dentro_de_mexico(lat: float, lon: float) -> bool:
    p = PARAMETROS
    return p["lat_min"] <= lat <= p["lat_max"] and p["lon_min"] <= lon <= p["lon_max"]


def validar_usgs(archivos: list[Path], registrar: Bitacora) -> list[list]:
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


_NUM = r"(NULL|-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
_TXT = r"(NULL|'(?:[^']|'')*')"
RE_SISMO = re.compile(rf"VALUES \((\d+), {_NUM}, {_NUM}, {_NUM}, {_NUM}, {_TXT}, {_TXT}, {_TXT}\);")
RE_TIEMPO = re.compile(rf"VALUES \((\d+), {_TXT}, {_TXT}, ")


def _txt(token: str) -> str | None:
    return None if token == "NULL" else token[1:-1].replace("''", "'")


def _num(token: str) -> float | None:
    return None if token == "NULL" else float(token)


def validar_ssn(rutas: dict[str, Path], registrar: Bitacora) -> list[list]:
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


# ---------------------------------------------------------------------------
# 3. CARGA  y  4. TRANSFORMACIÓN
# ---------------------------------------------------------------------------
def cargar_y_transformar(filas_usgs: list[list], filas_ssn: list[list], registrar: Bitacora) -> str:
    p = PARAMETROS
    with conectar() as conn:                      # una sola transacción
        with conn.cursor() as cur:
            cur.execute("TRUNCATE staging.usgs_evento, staging.ssn_evento")
            cols = ", ".join(c.lower() for c in COLUMNAS_USGS)
            with cur.copy(f"COPY staging.usgs_evento ({cols}) FROM STDIN") as cp:
                for fila in filas_usgs:
                    cp.write_row(fila)
            registrar("carga", "COPY staging.usgs_evento", len(filas_usgs))

            with cur.copy("COPY staging.ssn_evento (id_sismo, fecha_local, hora_utc, fecha_hora_dw, "
                          "fecha_hora_utc, magnitud, latitud, longitud, profundidad, referencia, "
                          "estado, nombre_estado) FROM STDIN") as cp:
                for fila in filas_ssn:
                    cp.write_row(fila)
            registrar("carga", "COPY staging.ssn_evento", len(filas_ssn))

            cur.execute((SQL_DIR / "10_dimensiones.sql").read_text(encoding="utf-8"))
            for tabla in ("dw.dim_tiempo", "dw.dim_sismo"):
                n = cur.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]
                registrar("transformacion", f"Poblar {tabla}", n)

            # Primero con las fechas tal como están en el DW (diagnóstico) y
            # después con las fechas corregidas (la que usa el análisis).
            for variante in ("dw_original", "corregida"):
                resultados = cur.execute(
                    "SELECT resultado, eventos FROM dw.fn_emparejar(%s, %s, %s, %s, %s, %s, %s, %s)",
                    [variante, p["ventana_seg"], p["distancia_km"], p["ventana_seg_hist"],
                     p["distancia_km_hist"], p["anio_corte_hist"], p["ssn_mag_min"],
                     p["delta_mag_max"]],
                ).fetchall()
                for resultado, n in resultados:
                    registrar("transformacion", f"Emparejamiento ({variante}) → {resultado}", n)
        conn.commit()
    return ", ".join(f"{r}: {n:,}" for r, n in resultados)


def main() -> int:
    esperar_bd()
    # Módulo independiente: no cambia las reglas ni la bitácora del cruce sísmico.
    from demografia import ejecutar as cargar_demografia
    log.info("Demografía oficial: %s observaciones", cargar_demografia())
    from norteamerica import ejecutar as cargar_norteamerica
    log.info("Catálogo de Norteamérica: %s", cargar_norteamerica())
    if not FORZAR_ETL and ya_cargado(PARAMETROS):
        log.info("La base ya tiene una carga exitosa con estos parámetros; no se repite. "
                 "Usa FORZAR_ETL=1 para recargar.")
        with conectar() as conn:
            integrado = conn.execute("SELECT to_regclass('public.fact_cruce_usgs')").fetchone()[0]
        if integrado is None:
            extraer_ssn(lambda *a, **k: None)
            log.info("Cruce integrado al DW original: %s registros", f"{integrar_original():,}")
        return 0

    registrar = Bitacora(PARAMETROS)
    try:
        hoy = dt.datetime.now(dt.timezone.utc).date()
        archivos_usgs = extraer_usgs(registrar, hoy)
        rutas_ssn = extraer_ssn(registrar)
        filas_usgs = validar_usgs(archivos_usgs, registrar)
        filas_ssn = validar_ssn(rutas_ssn, registrar)
        resumen = cargar_y_transformar(filas_usgs, filas_ssn, registrar)
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
