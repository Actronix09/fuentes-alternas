"""Carga administrativa fiel a SHCP, sin inferir supervisores, RFC ni actas."""
import datetime as dt
import hashlib
import json
from pathlib import Path

from psycopg.types.json import Jsonb

from fuentes.shcp_srft import fecha, numero


def texto(v):
    s = (v or '').strip()
    return None if s in ('', 'NA', 'N/A') else s


def clave(prefijo, *partes):
    contenido = json.dumps(partes, ensure_ascii=False, sort_keys=True)
    return 'SRFT:' + prefijo + ':' + hashlib.sha256(contenido.encode()).hexdigest()[:24]


def integrar(cur, datos, asociados, folios, meta):
    sql = Path(__file__).resolve().parents[2] / 'db/05_expedientes.sql'
    # Disponible tanto para una base nueva como para los volúmenes ya creados.
    cur.execute(sql.read_text(encoding='utf-8'))
    for r in datos['ef2025.csv']:
        folio = r['FOLIO']
        if folio not in folios:
            continue
        obra_id = 'SRFT:' + folio
        geos = asociados['georreferencias.csv'][folio]
        contratos = asociados['contratos.csv'][folio]
        fuentes = asociados['fuentes_financiamiento.csv'][folio]
        contratistas = {}
        for c in contratos:
            nombre = texto(c.get('CONTRATISTA'))
            if nombre:
                ident = clave('CONTRATISTA', ' '.join(nombre.upper().split()))
                contratistas[ident] = nombre
                # RFC_CONVOCANTE es de la autoridad, NO del contratista.
                cur.execute('''INSERT INTO public.constructora
                    (id_constructora,rfc,nombre_const,tipo_ejecutor) VALUES(%s,NULL,%s,%s)
                    ON CONFLICT(id_constructora) DO NOTHING''',
                    [ident,nombre,texto(c.get('CONTRATACION'))])
        localidades = {}
        for g in geos:
            if texto(g.get('LOCALIDAD')) and texto(g.get('ID_LOCALIDAD')):
                ident = 'SRFT:LOCALIDAD:' + ':'.join(g[k] for k in ('ID_ENTIDAD_FEDERATIVA','ID_MUNICIPIO','ID_LOCALIDAD'))
                localidades[ident] = g['LOCALIDAD']
                cur.execute('''INSERT INTO public.region(id_region,comunidad,barrio,colonia)
                    VALUES(%s,%s,NULL,NULL) ON CONFLICT(id_region) DO NOTHING''', [ident,g['LOCALIDAD']])
        constructora = next(iter(contratistas)) if len(contratistas) == 1 else None
        region = next(iter(localidades)) if len(localidades) == 1 else None
        beneficiarios = {k:r.get(k) for k in ('POBLACION_BENEFICIADA','MUJERES','HOMBRES','BENEFICIARIOS')}
        # La etapa del flujo interno y el estado operativo no se deducen de "Terminado".
        existe = cur.execute('SELECT 1 FROM public.obra WHERE id_obra=%s',[obra_id]).fetchone()
        if not existe:
            cur.execute('''UPDATE warehouse.dim_obra SET es_actual=false,fecha_expiracion=now(),
                motivo_cambio='Vinculación al expediente operacional importado de SHCP'
                WHERE obra_id=%s AND es_actual''',[obra_id])
        cur.execute('''INSERT INTO public.obra
            (id_obra,codigo_expediente,nombre_obra,etapa,fecha_inicio,fecha_final,descripcion,
             beneficiarios,id_constructora,id_region,codigo_supervisor,estado,
             origen_datos,folio_fuente,fuente_url,estatus_fuente)
            VALUES(%s,%s,%s,NULL,%s,%s,%s,%s,%s,%s,NULL,true,'SHCP_SRFT',%s,%s,%s)
            ON CONFLICT(id_obra) DO UPDATE SET
             nombre_obra=excluded.nombre_obra,descripcion=excluded.descripcion,
             id_constructora=excluded.id_constructora,id_region=excluded.id_region,
             estatus_fuente=excluded.estatus_fuente
            WHERE (obra.nombre_obra,obra.descripcion,obra.id_constructora,obra.id_region,obra.estatus_fuente)
             IS DISTINCT FROM (excluded.nombre_obra,excluded.descripcion,excluded.id_constructora,excluded.id_region,excluded.estatus_fuente)''',
            [obra_id,folio,r['NOMBRE'],fecha(r['FECHA_INICIO']),fecha(r['FECHA_ESTIMADA_TERMINO']),
             r['CLASIFICACION'],json.dumps(beneficiarios,ensure_ascii=False),constructora,region,
             folio,meta['url'],r['DESC_ESTATUS']])
        cur.execute('''INSERT INTO public.presupuesto_obra
            (id_presupuesto,presupuesto_total,id_proyectista,id_obra,origen_datos)
            VALUES(%s,%s,NULL,%s,'SHCP_SRFT')
            ON CONFLICT(id_obra) DO UPDATE SET presupuesto_total=excluded.presupuesto_total
            WHERE presupuesto_obra.presupuesto_total IS DISTINCT FROM excluded.presupuesto_total''',
            ['SRFT:PRESUPUESTO:'+folio,numero(r['APROBADO']),obra_id])
        for c in contratos:
            ident = clave('CONTRATO',folio,c)
            cur.execute('''INSERT INTO public.contrato_srft VALUES
                (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(id_registro) DO NOTHING''',
                [ident,obra_id,texto(c.get('ID_CONTRATO')),texto(c.get('NUMERO_EXPEDIENTE')),
                 texto(c.get('NUMERO_CONTRATO')),texto(c.get('CONTRATISTA')),texto(c.get('MODALIDAD_CONTRATACION')),
                 numero(c.get('MONTO')),numero(c.get('IMPORTE_MODIFICADO')),fecha(texto(c.get('FECHA_FIRMA'))),
                 fecha(texto(c.get('FECHA_CONCLUSION_CONTRATO'))),texto(c.get('URL')),texto(c.get('URL_DOCUMENTO')),Jsonb(c)])
        for f in fuentes:
            fuente = 'SRFT:' + ':'.join(f.get(k,'') for k in ('CICLO_RECURSO','RAMO','MODALIDAD','PROGR_PRES'))
            programa = f"Ramo {f['RAMO']} / {f['MODALIDAD']}{f['PROGR_PRES']} / {f['CICLO_RECURSO']}"
            cur.execute('''INSERT INTO public.fuente_presupuestaria VALUES(%s,%s,%s)
                ON CONFLICT(id_fuente) DO NOTHING''',[fuente,f['TIPO_RECURSO'],programa])
            cur.execute('INSERT INTO public.financia VALUES(%s,%s) ON CONFLICT DO NOTHING',[obra_id,fuente])
            cur.execute('''INSERT INTO public.financiamiento_srft VALUES(%s,%s,%s,%s,%s,%s)
                ON CONFLICT(id_registro) DO NOTHING''',
                [clave('FINANCIAMIENTO',folio,f),obra_id,fuente,numero(f['MONTO_APROBADO']),numero(f['MONTO_MODIFICADO']),Jsonb(f)])
        faltantes = ['supervisor','proyectista','acta_entrega','firmantes','permisos','fotografias_de_campo']
        if not constructora:
            faltantes.append('contratista_unico_no_determinado')
        if not region:
            faltantes.append('localidad_unica_no_determinada')
        cur.execute('''INSERT INTO public.expediente_srft
            (id_obra,folio,datos_originales,fecha_referencia,fuente_url,sha256,campos_no_publicados)
            VALUES(%s,%s,%s,'2025-12-31',%s,%s,%s)
            ON CONFLICT(id_obra) DO UPDATE SET datos_originales=excluded.datos_originales,
             sha256=excluded.sha256,campos_no_publicados=excluded.campos_no_publicados''',
            [obra_id,folio,Jsonb(r),meta['url'],meta['sha256_zip'],Jsonb(faltantes)])
        cur.execute('''INSERT INTO public.informe_fuente_srft
            SELECT %s,'2025-12-31',avance_fisico_pct,aprobado,pagado,estatus,%s,fuente_url
            FROM warehouse.fact_srft WHERE folio=%s
            ON CONFLICT(id_obra) DO UPDATE SET avance_fisico_pct=excluded.avance_fisico_pct,
             aprobado=excluded.aprobado,pagado=excluded.pagado,estatus_publicado=excluded.estatus_publicado,
             metas_originales=excluded.metas_originales''',
            [obra_id,Jsonb(asociados['metas_avances.csv'][folio]),folio])
        cur.execute('''UPDATE warehouse.fact_srft f SET obra_key=o.obra_key
            FROM warehouse.dim_obra o WHERE f.folio=%s AND o.obra_id=%s AND o.es_actual''',[folio,obra_id])
    # El disparador original registra la inserción local; identificarla como importación,
    # sin atribuir al municipio una inspección, firma o fecha histórica inexistente.
    cur.execute('''UPDATE warehouse.fact_eventos_auditoria e SET
        tipo_evento_key=(SELECT tipo_evento_key FROM warehouse.dim_tipo_evento WHERE codigo_evento='IMPORTACION_SHCP'),
        descripcion_evento='Importación ETL local desde SHCP; no acredita creación histórica ni inspección física'
        FROM warehouse.dim_obra o WHERE e.obra_key=o.obra_key AND o.obra_id LIKE 'SRFT:%'
         AND e.descripcion_evento='Obra registrada en el sistema' ''')
    return cur.execute('SELECT count(*) FROM public.expediente_srft').fetchone()[0]
