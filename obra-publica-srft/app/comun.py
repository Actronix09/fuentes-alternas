"""Utilidades compartidas por el ETL y la API web.

- Conexión a PostgreSQL (variable DATABASE_URL).
- Bitácora del pipeline en las tablas etl.ejecucion y etl.bitacora.
- Descargas con caché local en /datos, reintentos y escritura atómica.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import psycopg
import requests

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/postgres")
DIR_DATOS = Path(os.environ.get("DIR_DATOS", "/datos"))
AGENTE = "fuentes-alternas-escom/1.0 (prototipo academico de bases de datos)"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("etl")


ZONA_BD = os.environ.get("ZONA_BD", "America/Mexico_City")


def conectar(autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, autocommit=autocommit, options=f"-c TimeZone={ZONA_BD}")


def esperar_bd(intentos: int = 30, pausa: float = 2.0) -> None:
    """Espera a que PostgreSQL acepte conexiones y tenga el esquema creado."""
    for i in range(1, intentos + 1):
        try:
            with conectar(autocommit=True) as c:
                c.execute("SELECT 1 FROM etl.ejecucion LIMIT 1")
            return
        except psycopg.Error as e:
            log.info("Esperando a PostgreSQL (%d/%d): %s", i, intentos, str(e).strip())
            time.sleep(pausa)
    raise RuntimeError(
        "PostgreSQL no respondió o no tiene el esquema. "
        "Si cambiaste los archivos de db/, recrea el volumen: docker compose down -v"
    )


def normalizar(parametros: dict) -> dict:
    return json.loads(json.dumps(parametros, ensure_ascii=False, default=str))


class Bitacora:
    """Registra la ejecución y cada paso en una conexión propia (autocommit),
    de modo que el rastro queda aunque la transformación falle y se revierta."""

    def __init__(self, parametros: dict):
        self.conn = conectar(autocommit=True)
        self.id = self.conn.execute(
            "INSERT INTO etl.ejecucion (parametros) VALUES (%s) RETURNING id_ejecucion",
            [json.dumps(normalizar(parametros), ensure_ascii=False)],
        ).fetchone()[0]

    def __call__(self, fase: str, paso: str, registros: int | None = None,
                 detalle: str | None = None) -> None:
        extra = f" · {registros:,} registros" if registros is not None else ""
        extra += f" · {detalle}" if detalle else ""
        log.info("[%s] %s%s", fase, paso, extra)
        self.conn.execute(
            "INSERT INTO etl.bitacora (id_ejecucion, fase, paso, registros, detalle) "
            "VALUES (%s, %s, %s, %s, %s)",
            [self.id, fase, paso, registros, detalle],
        )

    def terminar(self, estado: str, mensaje: str | None = None) -> None:
        self.conn.execute(
            "UPDATE etl.ejecucion SET fin = now(), estado = %s, mensaje = %s "
            "WHERE id_ejecucion = %s",
            [estado, mensaje, self.id],
        )
        self.conn.close()


def ya_cargado(parametros: dict) -> bool:
    """True si la última carga exitosa usó exactamente los mismos parámetros."""
    with conectar() as c:
        fila = c.execute(
            "SELECT parametros FROM etl.ejecucion WHERE estado = 'ok' "
            "ORDER BY id_ejecucion DESC LIMIT 1"
        ).fetchone()
    return fila is not None and fila[0] == normalizar(parametros)


def nueva_sesion() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = AGENTE
    return s


def descargar(url: str, destino: Path, *, forzar: bool = False,
              sesion: requests.Session | None = None, verify: bool | str = True,
              params: dict | None = None, timeout: int = 180, intentos: int = 4) -> Path:
    """Descarga url en destino. Si el archivo ya existe se reutiliza (caché),
    salvo que forzar=True. Escribe primero en .part y renombra al terminar,
    así una descarga interrumpida nunca se confunde con una completa."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 0 and not forzar:
        log.info("Caché: %s (%.1f MB)", destino.name, destino.stat().st_size / 1e6)
        return destino

    sesion = sesion or nueva_sesion()
    parcial = destino.with_name(destino.name + ".part")
    for intento in range(1, intentos + 1):
        try:
            with sesion.get(url, params=params, stream=True, timeout=timeout, verify=verify) as r:
                r.raise_for_status()
                total, aviso = 0, 25_000_000
                with open(parcial, "wb") as f:
                    for bloque in r.iter_content(chunk_size=1 << 20):
                        f.write(bloque)
                        total += len(bloque)
                        if total >= aviso:
                            log.info("  %s … %.0f MB", destino.name, total / 1e6)
                            aviso += 25_000_000
            parcial.replace(destino)
            log.info("Descargado %s (%.1f MB)", destino.name, destino.stat().st_size / 1e6)
            return destino
        except requests.RequestException as e:
            espera = 5 * intento
            log.warning("Fallo al descargar %s (intento %d/%d): %s. Reintento en %d s",
                        url, intento, intentos, e, espera)
            time.sleep(espera)
    raise RuntimeError(f"No se pudo descargar {url}")
