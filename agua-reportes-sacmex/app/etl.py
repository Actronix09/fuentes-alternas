"""ETL del Sistema 2: consumo de agua en la CDMX validado con reportes ciudadanos.

Fases (las mismas del pipeline del paper del agua):

  1. Extracción      Tres recursos del Portal de Datos Abiertos de la CDMX (API CKAN):
                     el consumo del 1er semestre de 2019 (fuente del paper) y los
                     reportes ciudadanos de agua 2018-2021 y 2022-2024 (fuente alterna).
  2. Validación      Consumo: fuera las filas con alcaldía o colonia "NA" (como el paper).
                     Reportes: fecha y tipo obligatorios, folios únicos, coordenadas
                     dentro de la CDMX y nombres normalizados para cruzarlos.
  3. Carga           COPY masivo a staging.
  4. Transformación  SQL: dimensiones, puntos de manzana, hechos y ubicación de cada
                     reporte en una colonia (por nombre o por la manzana más cercana).

Cada paso queda en etl.bitacora con el número de registros afectados.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import re
import sys
import unicodedata
from pathlib import Path

from comun import (DIR_DATOS, Bitacora, conectar, descargar, esperar_bd, log,
                   nueva_sesion, ya_cargado)

CKAN = "https://datos.cdmx.gob.mx/api/3/action"
PORTAL = "https://datos.cdmx.gob.mx/dataset/{paquete}/resource/{id}/download/{id}.csv"

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
SQL_DIR = Path(__file__).parent / "sql"

COLUMNAS_CONSUMO = ["fecha_referencia", "anio", "bimestre", "consumo_total_mixto", "consumo_prom_dom",
                    "consumo_total_dom", "consumo_prom_mixto", "consumo_total", "consumo_prom",
                    "consumo_prom_no_dom", "consumo_total_no_dom", "indice_des", "colonia", "alcaldia",
                    "latitud", "longitud"]
COLUMNAS_REPORTE = ["recurso", "folio", "fecha", "hora", "clasificacion", "reporte", "medio",
                    "alcaldia", "colonia", "alcaldia_norm", "colonia_norm", "latitud", "longitud"]


# ---------------------------------------------------------------------------
# Utilidades de limpieza
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 1. EXTRACCIÓN
# ---------------------------------------------------------------------------
def extraer(registrar: Bitacora) -> dict[str, dict]:
    sesion = nueva_sesion()
    salida = {}
    for clave, r in RECURSOS.items():
        meta = {"id": r["id"], "conjunto": r["conjunto"], "nombre": clave,
                "url": PORTAL.format(paquete=r["paquete"], id=r["id"]), "ultima_modificacion": None}
        try:                                  # metadatos del recurso (nombre, url, fecha de actualización)
            resp = sesion.get(f"{CKAN}/resource_show", params={"id": r["id"]}, timeout=60)
            resp.raise_for_status()
            info = resp.json()["result"]
            meta.update(nombre=info.get("name") or clave, url=info.get("url") or meta["url"],
                        ultima_modificacion=info.get("last_modified") or info.get("metadata_modified"))
        except Exception as e:                # noqa: BLE001 — el portal a veces tarda; se usa la URL conocida
            log.warning("No se pudieron leer los metadatos de %s (%s); se usa la URL conocida", clave, e)
        meta["archivo"] = descargar(meta["url"], DIR_DATOS / f"{clave}.csv", forzar=FORZAR_DESCARGA)
        meta["bytes"] = meta["archivo"].stat().st_size
        registrar("extraccion", f"{meta['nombre']}", None,
                  f"{meta['bytes'] / 1e6:.1f} MB · actualizado en el portal: {meta['ultima_modificacion'] or 's/d'}")
        salida[clave] = meta
    return salida


# ---------------------------------------------------------------------------
# 2. VALIDACIÓN Y LIMPIEZA
# ---------------------------------------------------------------------------
def validar_consumo(archivo: Path, registrar: Bitacora) -> list[list]:
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


def validar_reportes(archivos: dict[str, Path], registrar: Bitacora) -> list[list]:
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


# ---------------------------------------------------------------------------
# 3. CARGA  y  4. TRANSFORMACIÓN
# ---------------------------------------------------------------------------
def cargar_y_transformar(meta: dict[str, dict], consumo: list[list], reportes: list[list],
                         registrar: Bitacora) -> str:
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE staging.consumo, staging.reporte_agua RESTART IDENTITY")
            columnas = ", ".join(COLUMNAS_CONSUMO + ["alcaldia_norm", "colonia_norm"])
            with cur.copy(f"COPY staging.consumo ({columnas}) FROM STDIN") as cp:
                for fila in consumo:
                    cp.write_row(fila)
            registrar("carga", "COPY staging.consumo", len(consumo))
            with cur.copy(f"COPY staging.reporte_agua ({', '.join(COLUMNAS_REPORTE)}) FROM STDIN") as cp:
                for fila in reportes:
                    cp.write_row(fila)
            registrar("carga", "COPY staging.reporte_agua", len(reportes))

            cur.execute("TRUNCATE etl.recurso")
            for m in meta.values():
                cur.execute(
                    "INSERT INTO etl.recurso (id_recurso, conjunto, nombre, url, ultima_modificacion, bytes) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    [m["id"], m["conjunto"], m["nombre"], m["url"], m["ultima_modificacion"], m["bytes"]])

            cur.execute((SQL_DIR / "10_dimensiones.sql").read_text(encoding="utf-8"))
            for tabla in ("dw.dim_tiempo", "dw.dim_ubicacion", "dw.manzana", "dw.dim_indice_des",
                          "dw.dim_tipo_reporte", "dw.dim_medio_recepcion"):
                registrar("transformacion", f"Poblar {tabla}",
                          cur.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0])

            cur.execute("SELECT set_config('etl.distancia_max_m', %s, true)",
                        [str(PARAMETROS["distancia_max_m"])])
            cur.execute((SQL_DIR / "20_hechos.sql").read_text(encoding="utf-8"))
            registrar("transformacion", "Poblar dw.fact_consumo_agua",
                      cur.execute("SELECT count(*) FROM dw.fact_consumo_agua").fetchone()[0])
            for recurso, metodo, n in cur.execute(
                    "SELECT recurso, coalesce(metodo_ubicacion, 'sin ubicar'), count(*) "
                    "FROM dw.fact_reporte_agua GROUP BY 1, 2 ORDER BY 1, 2").fetchall():
                registrar("transformacion", f"Reportes {recurso} ubicados por {metodo}", n)
            total = cur.execute("SELECT count(*) FROM dw.fact_reporte_agua").fetchone()[0]
            registrar("transformacion", "Poblar dw.fact_reporte_agua", total)

            ev = cur.execute("SELECT puntaje, auc, spearman, precision_47 FROM dw.v_evaluacion_2019").fetchall()
            for puntaje, auc, rho, p47 in ev:
                registrar("transformacion", f"Evaluación 1er sem. 2019 · {puntaje}", None,
                          f"AUC {auc} · Spearman {rho} · precisión@47 {p47}")
        conn.commit()
    return f"{len(consumo):,} filas de consumo y {total:,} reportes cargados"


def main() -> int:
    esperar_bd()
    if not FORZAR_ETL and ya_cargado(PARAMETROS):
        from integrar_original import integrar_original
        integrar_original()
        from grafo import materializar
        materializar()
        log.info("La base ya tiene una carga exitosa con estos parámetros; no se repite. "
                 "Usa FORZAR_ETL=1 para recargar.")
        return 0

    registrar = Bitacora(PARAMETROS)
    try:
        meta = extraer(registrar)
        consumo = validar_consumo(meta["consumo"]["archivo"], registrar)
        reportes = validar_reportes({k: meta[k]["archivo"] for k in ("historico_2018_2021",
                                                                      "incidentes_2022_2024")}, registrar)
        resumen = cargar_y_transformar(meta, consumo, reportes, registrar)
        from integrar_original import integrar_original
        integrar_original(registrar)
        from grafo import materializar
        materializar(registrar)
        registrar.terminar("ok", resumen)
        log.info("ETL terminado: %s", resumen)
        return 0
    except Exception as e:                                # noqa: BLE001 — se registra y se reporta
        log.exception("El ETL falló")
        registrar.terminar("error", f"{type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
