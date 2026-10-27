"""Fuente SHCP SRFT: informe definitivo 2025 de entidades federativas, Temascaltepec.

Del ZIP nacional (5 CSV en Windows-1252) se guardan extractos UTF-8 del
municipio con su SHA-256 en procedencia.json. La validación aplica las reglas
de calidad por proyecto; los rechazos no se cargan.
Archivos: datos/shcp_srft/<archivo>_temascaltepec.csv, procedencia.json y catalogo_shcp.json
"""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from comun import DIR_DATOS, descargar, registrar_consola

DIRECTORIO = DIR_DATOS / 'shcp_srft'
URL = 'https://www.transparenciapresupuestaria.gob.mx/work/models/PTP/DatosAbiertos/Entidades_Federativas/2025/ef2025.zip'
PARAMETROS = {'fuente': URL, 'entidad': 15, 'municipio': 86, 'ciclo': 2025, 'periodo': 5}
ARCHIVOS = ('ef2025.csv', 'georreferencias.csv', 'metas_avances.csv', 'contratos.csv', 'fuentes_financiamiento.csv')


def numero(valor):
    if valor is None or str(valor).strip() in ('', 'NA', 'N/A'):
        return None
    n = Decimal(str(valor).replace(',', '').strip())
    if not n.is_finite():
        raise ValueError('Número no finito')
    return n


def fecha(valor):
    if not valor or valor.strip() in ('NA', 'N/A'):
        return None
    return dt.datetime.strptime(valor.strip(), '%d/%m/%Y').date()


def extracto(nombre):
    return DIRECTORIO / nombre.replace('.csv', '_temascaltepec.csv')


def extraer(registrar):
    zip_path = DIRECTORIO / 'ef2025.zip'
    if os.getenv('FORZAR_DESCARGA') == '1':
        descargar(URL, zip_path, forzar=True)
    if zip_path.exists():
        contenido = zip_path.read_bytes()
    elif extracto('ef2025.csv').exists() and os.getenv('FORZAR_DESCARGA') != '1':
        registrar('extraccion', 'Usar extracto oficial local y manifiesto de procedencia', None)
        return json.loads((DIRECTORIO / 'procedencia.json').read_text(encoding='utf-8'))
    else:
        descargar(URL, zip_path)
        contenido = zip_path.read_bytes()
    sha = hashlib.sha256(contenido).hexdigest()
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        def leer(nombre):
            # Los CSV oficiales usan Windows-1252 y CRCRLF. csv respeta campos entrecomillados.
            return csv.DictReader(io.TextIOWrapper(z.open(nombre), encoding='cp1252', newline=''))
        proyectos, leidos = [], 0
        for r in leer('ef2025.csv'):
            leidos += 1
            if r['ID_ENTIDAD_FEDERATIVA'] == '15' and r['ID_MUNICIPIO'] == '86':
                proyectos.append(r)
        folios = {r['FOLIO'] for r in proyectos}
        for nombre in ARCHIVOS:
            filas = proyectos if nombre == 'ef2025.csv' else [r for r in leer(nombre) if r['FOLIO'] in folios]
            with extracto(nombre).open('w', encoding='utf-8', newline='') as f:
                escritor = csv.DictWriter(f, fieldnames=filas[0].keys() if filas else ['FOLIO'])
                escritor.writeheader()
                escritor.writerows(filas)
        meta = {'url': URL, 'sha256_zip': sha, 'bytes_zip': len(contenido),
                'extraido_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                'filas_nacionales': leidos, 'proyectos_municipio': len(proyectos),
                'filtro': PARAMETROS,
                'sha256_extractos': {extracto(n).name: hashlib.sha256(
                    extracto(n).read_bytes()).hexdigest() for n in ARCHIVOS}}
        (DIRECTORIO / 'procedencia.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        registrar('extraccion', 'Filas nacionales en informe definitivo SHCP 2025', leidos)
        registrar('extraccion', 'Proyectos oficiales de Temascaltepec', len(proyectos), f'SHA-256 ZIP: {sha}')
        return meta


def leer(meta):
    """(datos, asociados): filas de cada extracto, verificado contra el manifiesto, y las asociadas agrupadas por folio."""
    datos = {}
    for nombre in ARCHIVOS:
        archivo = extracto(nombre)
        esperado = meta['sha256_extractos'][archivo.name]
        if hashlib.sha256(archivo.read_bytes()).hexdigest() != esperado:
            raise ValueError(f'El extracto {archivo.name} no coincide con el manifiesto')
        with archivo.open(encoding='utf-8', newline='') as f:
            datos[nombre] = list(csv.DictReader(f))
    asociados = {}
    for nombre in ARCHIVOS[1:]:
        grupos = defaultdict(list)
        for r in datos[nombre]:
            grupos[r['FOLIO']].append(r)
        asociados[nombre] = grupos
    return datos, asociados


def validar(datos):
    """(validos, rechazados): validos son (fila, inicio, termino, montos); rechazados, folio y motivo."""
    vistos, validos, rechazados = set(), [], []
    for r in datos['ef2025.csv']:
        folio = r['FOLIO']
        try:
            if not folio or folio in vistos:
                raise ValueError('Folio vacío o repetido')
            if r['ID_ENTIDAD_FEDERATIVA'] != '15' or r['ID_MUNICIPIO'] != '86':
                raise ValueError('Fuera del municipio autorizado')
            if int(r['CICLO']) != 2025 or int(r['TRIMESTRE']) != 5:
                raise ValueError('Periodo distinto al informe definitivo 2025')
            inicio, termino = fecha(r['FECHA_INICIO']), fecha(r['FECHA_ESTIMADA_TERMINO'])
            if inicio and termino and inicio > termino:
                raise ValueError('Fechas invertidas')
            montos = [numero(r[k]) for k in ['APROBADO','RECAUDADO','COMPROMETIDO','DEVENGADO','EJERCIDO','PAGADO']]
            if any(n is not None and n < 0 for n in montos):
                raise ValueError('Monto negativo')
        except (ValueError, InvalidOperation) as e:
            rechazados.append({'folio': folio, 'motivo': str(e)})
            continue
        vistos.add(folio)
        validos.append((r, inicio, termino, montos))
    return validos, rechazados


if __name__ == '__main__':
    validos, rechazados = validar(leer(extraer(registrar_consola))[0])
    print(f'{len(validos)} proyectos válidos, {len(rechazados)} rechazados')
