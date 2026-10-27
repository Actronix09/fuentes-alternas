"""Fuente U.S. Census Bureau: población estimada al 1 de julio, 2020–2025.

50 estados + DC y el total nacional. Archivo: datos/demografia/us/NST-EST2025-ALLDATA.csv
"""
import csv

from comun import DIR_DATOS, descargar, sha256

DIRECTORIO = DIR_DATOS / 'demografia' / 'us'
FUENTE = {
    'institucion': 'U.S. Census Bureau',
    'titulo': 'NST-EST2025-ALLDATA, Vintage 2025',
    'pagina': 'https://www.census.gov/data/datasets/time-series/demo/popest/2020s-state-total.html',
    'url': 'https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/state/totals/NST-EST2025-ALLDATA.csv',
    'archivo': 'NST-EST2025-ALLDATA.csv', 'doi': None,
}


def extraer(actualizar=False):
    """(filas, fuente): observaciones por estado y año, y metadatos con SHA-256 del original."""
    archivo = descargar(FUENTE['url'], DIRECTORIO / FUENTE['archivo'], forzar=actualizar)
    filas = []
    with archivo.open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            # 040 = estados/DC; 010 = nacional. Excluye regiones censales y Puerto Rico.
            if r['SUMLEV'] not in ('010', '040') or r['STATE'] == '72':
                continue
            for anio in range(2020, 2026):
                filas.append(dict(pais='US', codigo=r['STATE'], nombre=r['NAME'],
                                  nivel='pais' if r['SUMLEV'] == '010' else 'region',
                                  anio=anio, poblacion=r[f'POPESTIMATE{anio}'],
                                  identificador_origen=r['STATE'], estado_origen=''))
    return filas, {**FUENTE, 'sha256': sha256(archivo), 'bytes': archivo.stat().st_size}


if __name__ == '__main__':
    print(f'{len(extraer()[0])} observaciones del Census Bureau')
