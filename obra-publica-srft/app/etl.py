"""SHCP SRFT → staging → dimensiones originales → hecho oficial del warehouse."""
import csv
import datetime as dt
import hashlib
import io
import json
import os
import sys
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from psycopg.types.json import Jsonb
from comun import DIR_DATOS, Bitacora, conectar, descargar, esperar_bd, log

URL = 'https://www.transparenciapresupuestaria.gob.mx/work/models/PTP/DatosAbiertos/Entidades_Federativas/2025/ef2025.zip'
PARAMETROS = {'fuente': URL, 'entidad': 15, 'municipio': 86, 'ciclo': 2025, 'periodo': 5}
ARCHIVOS = ('ef2025.csv', 'georreferencias.csv', 'metas_avances.csv', 'contratos.csv', 'fuentes_financiamiento.csv')
RAIZ = Path(__file__).resolve().parents[1]


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


def extraer(registrar):
    zip_path = DIR_DATOS / 'ef2025.zip'
    if os.getenv('FORZAR_DESCARGA') == '1':
        descargar(URL, zip_path, forzar=True)
    if zip_path.exists():
        contenido = zip_path.read_bytes()
    elif (DIR_DATOS / 'ef2025_temascaltepec.csv').exists() and os.getenv('FORZAR_DESCARGA') != '1':
        registrar('extraccion', 'Usar extracto oficial local y manifiesto de procedencia', None)
        return json.loads((DIR_DATOS / 'procedencia.json').read_text(encoding='utf-8'))
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
            destino = DIR_DATOS / nombre.replace('.csv', '_temascaltepec.csv')
            with destino.open('w', encoding='utf-8', newline='') as f:
                escritor = csv.DictWriter(f, fieldnames=filas[0].keys() if filas else ['FOLIO'])
                escritor.writeheader()
                escritor.writerows(filas)
        meta = {'url': URL, 'sha256_zip': sha, 'bytes_zip': len(contenido),
                'extraido_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                'filas_nacionales': leidos, 'proyectos_municipio': len(proyectos),
                'filtro': PARAMETROS,
                'sha256_extractos': {n.replace('.csv','_temascaltepec.csv'): hashlib.sha256(
                    (DIR_DATOS / n.replace('.csv','_temascaltepec.csv')).read_bytes()).hexdigest() for n in ARCHIVOS}}
        (DIR_DATOS / 'procedencia.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        registrar('extraccion', 'Filas nacionales en informe definitivo SHCP 2025', leidos)
        registrar('extraccion', 'Proyectos oficiales de Temascaltepec', len(proyectos), f'SHA-256 ZIP: {sha}')
        return meta


def cargar(registrar, meta):
    datos = {}
    for nombre in ARCHIVOS:
        archivo = DIR_DATOS / nombre.replace('.csv', '_temascaltepec.csv')
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
    vistos, rechazados = set(), []
    with conectar() as conn, conn.cursor() as cur:
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
            geos, metas, contratos = [asociados[n][folio] for n in ARCHIVOS[1:4]]
            puntos = []
            for g in geos:
                try:
                    la, lo = numero(g['LAT']), numero(g['LON'])
                    if la is not None and lo is not None and 18 < la < 21 and -101 < lo < -98:
                        puntos.append((la, lo, g['LOCALIDAD']))
                except (InvalidOperation, ValueError):
                    pass
            lat, lon, localidad = puntos[0] if puntos else (None, None, None)
            # No sumar metas de unidades diferentes. Solo calcular porcentaje cuando existe una meta.
            avance = None
            if len(metas) == 1:
                objetivo, realizado = numero(metas[0]['META_MODIFICADA']), numero(metas[0]['AVANCE_FISICO'])
                if objetivo is not None and objetivo > 0 and realizado is not None:
                    avance = 100 * realizado / objetivo
            cur.execute('''INSERT INTO staging.srft VALUES(%s,2025,5,%s,%s,%s,%s)
                ON CONFLICT(folio) DO UPDATE SET datos=excluded.datos,
                georreferencias=excluded.georreferencias, metas=excluded.metas, contratos=excluded.contratos''',
                [folio, Jsonb(r), Jsonb(geos), Jsonb(metas), Jsonb(contratos)])
            obra_id = 'SRFT:' + folio
            obra = cur.execute('SELECT obra_key FROM warehouse.dim_obra WHERE obra_id=%s AND es_actual', [obra_id]).fetchone()
            if obra is None:
                obra = cur.execute('''INSERT INTO warehouse.dim_obra
                    (obra_id,codigo_expediente,nombre_obra,descripcion,fecha_inicio,fecha_final,estado_nombre,motivo_cambio)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,'Importación oficial SHCP SRFT 2025') RETURNING obra_key''',
                    [obra_id,folio,r['NOMBRE'],r['CLASIFICACION'],inicio,termino,r['DESC_ESTATUS']]).fetchone()
            # La fecha de referencia del informe definitivo es el cierre del ejercicio, no la fecha de descarga.
            cur.execute('''INSERT INTO warehouse.fact_srft
                (folio,obra_key,tiempo_key,ciclo,periodo,clasificacion,municipio,
                 aprobado,recaudado,comprometido,devengado,ejercido,pagado,estatus,
                 fecha_inicio,fecha_estimada_termino,latitud,longitud,localidad,avance_fisico_pct,fuente_url,sha256)
                VALUES(%s,%s,20251231,2025,5,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(folio) DO UPDATE SET
                 aprobado=excluded.aprobado,recaudado=excluded.recaudado,comprometido=excluded.comprometido,
                 devengado=excluded.devengado,ejercido=excluded.ejercido,pagado=excluded.pagado,
                 estatus=excluded.estatus,avance_fisico_pct=excluded.avance_fisico_pct,sha256=excluded.sha256''',
                [folio,obra[0],r['CLASIFICACION'],r['MUNICIPIO'],*montos,r['DESC_ESTATUS'],inicio,termino,
                 lat,lon,localidad,avance,meta['url'],meta['sha256_zip']])
        from integrar_expedientes import integrar
        expedientes = integrar(cur, datos, asociados, vistos, meta, numero, fecha)
        n = cur.execute('SELECT count(*) FROM warehouse.fact_srft').fetchone()[0]
    (DIR_DATOS / 'rechazados.json').write_text(json.dumps(rechazados, ensure_ascii=False, indent=2), encoding='utf-8')
    registrar('validacion', 'Proyectos rechazados por reglas de calidad', len(rechazados))
    registrar('carga', 'Proyectos reales integrados en warehouse.fact_srft', n)
    registrar('carga', 'Expedientes administrativos importados con faltantes explícitos', expedientes)
    if n == 0:
        raise ValueError('La carga no produjo obras válidas')
    return n


def main():
    esperar_bd()
    registrar = Bitacora(PARAMETROS)
    try:
        meta = extraer(registrar)
        n = cargar(registrar, meta)
        registrar.terminar('ok', f'{n} obras oficiales SHCP integradas al warehouse original')
        return 0
    except Exception as e:
        log.exception('Falló el ETL de obras')
        registrar.terminar('error', str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main())
