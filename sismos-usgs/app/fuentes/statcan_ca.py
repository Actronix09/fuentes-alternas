"""Fuente Statistics Canada: población estimada al 1 de julio, 2020–2025.

13 provincias/territorios y el total nacional. Archivo: datos/demografia/ca/17100005-eng.zip
"""
import csv
import io
import zipfile

from comun import DIR_DATOS, descargar, sha256

DIRECTORIO = DIR_DATOS / 'demografia' / 'ca'
FUENTE = {
    'institucion': 'Statistics Canada',
    'titulo': 'Table 17-10-0005-01, Population estimates on July 1, by age and gender',
    'pagina': 'https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710000501',
    'url': 'https://www150.statcan.gc.ca/n1/tbl/csv/17100005-eng.zip',
    'archivo': '17100005-eng.zip', 'doi': '10.25318/1710000501-eng',
}


def extraer(actualizar=False):
    """(filas, fuente): observaciones por provincia y año, y metadatos con SHA-256 del original."""
    archivo = descargar(FUENTE['url'], DIRECTORIO / FUENTE['archivo'], forzar=actualizar)
    filas = []
    with zipfile.ZipFile(archivo) as z, z.open('17100005.csv') as entrada:
        for r in csv.DictReader(io.TextIOWrapper(entrada, encoding='utf-8-sig')):
            if r['REF_DATE'] not in {str(a) for a in range(2020, 2026)}:
                continue
            if r['Gender'] != 'Total - gender' or r['Age group'] != 'All ages':
                continue
            if r['UOM'] != 'Persons' or r['SCALAR_FACTOR'] != 'units' or not r['VALUE']:
                raise ValueError('Unidad o valor de población canadiense no esperado')
            nacional = r['GEO'] == 'Canada'
            filas.append(dict(pais='CA', codigo='00' if nacional else r['DGUID'][-2:],
                              nombre=r['GEO'], nivel='pais' if nacional else 'region',
                              anio=r['REF_DATE'], poblacion=r['VALUE'],
                              identificador_origen=r['DGUID'], estado_origen=r['STATUS']))
    return filas, {**FUENTE, 'sha256': sha256(archivo), 'bytes': archivo.stat().st_size}


if __name__ == '__main__':
    print(f'{len(extraer()[0])} observaciones de Statistics Canada')
