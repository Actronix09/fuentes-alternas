"""Descarga de un recurso del Portal de Datos Abiertos de la CDMX (API CKAN).

La usan consumo_cdmx y reportes_sacmex; cada una decide en qué carpeta guarda su archivo.
"""
from __future__ import annotations

from pathlib import Path

import requests

from comun import descargar, log
from parametros import FORZAR_DESCARGA, RECURSOS

CKAN = "https://datos.cdmx.gob.mx/api/3/action"
PORTAL = "https://datos.cdmx.gob.mx/dataset/{paquete}/resource/{id}/download/{id}.csv"


def extraer_recurso(clave: str, directorio: Path, sesion: requests.Session, registrar) -> dict:
    """Metadatos del recurso (nombre, url, fecha de actualización) y archivo descargado en directorio/<clave>.csv."""
    r = RECURSOS[clave]
    meta = {"id": r["id"], "conjunto": r["conjunto"], "nombre": clave,
            "url": PORTAL.format(paquete=r["paquete"], id=r["id"]), "ultima_modificacion": None}
    try:
        resp = sesion.get(f"{CKAN}/resource_show", params={"id": r["id"]}, timeout=60)
        resp.raise_for_status()
        info = resp.json()["result"]
        meta.update(nombre=info.get("name") or clave, url=info.get("url") or meta["url"],
                    ultima_modificacion=info.get("last_modified") or info.get("metadata_modified"))
    except Exception as e:                # noqa: BLE001 — el portal a veces tarda; se usa la URL conocida
        log.warning("No se pudieron leer los metadatos de %s (%s); se usa la URL conocida", clave, e)
    meta["archivo"] = descargar(meta["url"], directorio / f"{clave}.csv", forzar=FORZAR_DESCARGA)
    meta["bytes"] = meta["archivo"].stat().st_size
    registrar("extraccion", f"{meta['nombre']}", None,
              f"{meta['bytes'] / 1e6:.1f} MB · actualizado en el portal: {meta['ultima_modificacion'] or 's/d'}")
    return meta
