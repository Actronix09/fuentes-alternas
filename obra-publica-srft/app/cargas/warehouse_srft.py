"""Carga de los proyectos SHCP SRFT validados: staging → dim_obra → hecho oficial del warehouse.

Después integra los expedientes administrativos (cargas/expedientes.py) en la misma transacción.
Los rechazos de la validación se guardan en datos/generados/rechazados.json.
"""
import json
from decimal import InvalidOperation

from psycopg.types.json import Jsonb

from cargas.expedientes import integrar
from comun import DIR_DATOS, conectar, registrar_consola
from fuentes.shcp_srft import extraer, leer, numero, validar

DIR_GENERADOS = DIR_DATOS / 'generados'


def cargar(registrar, meta):
    datos, asociados = leer(meta)
    validos, rechazados = validar(datos)
    vistos = {r['FOLIO'] for r, *_ in validos}
    with conectar() as conn, conn.cursor() as cur:
        for r, inicio, termino, montos in validos:
            folio = r['FOLIO']
            geos, metas, contratos = [asociados[n][folio] for n in ('georreferencias.csv', 'metas_avances.csv', 'contratos.csv')]
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
        expedientes = integrar(cur, datos, asociados, vistos, meta)
        n = cur.execute('SELECT count(*) FROM warehouse.fact_srft').fetchone()[0]
    DIR_GENERADOS.mkdir(parents=True, exist_ok=True)
    (DIR_GENERADOS / 'rechazados.json').write_text(json.dumps(rechazados, ensure_ascii=False, indent=2), encoding='utf-8')
    registrar('validacion', 'Proyectos rechazados por reglas de calidad', len(rechazados))
    registrar('carga', 'Proyectos reales integrados en warehouse.fact_srft', n)
    registrar('carga', 'Expedientes administrativos importados con faltantes explícitos', expedientes)
    if n == 0:
        raise ValueError('La carga no produjo obras válidas')
    return n


if __name__ == '__main__':
    print(f'{cargar(registrar_consola, extraer(registrar_consola))} obras en warehouse.fact_srft')
