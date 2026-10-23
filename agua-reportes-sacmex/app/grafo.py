"""Materialización RDF del DW vivo: consumo/clima originales y reportes SACMEX."""
import datetime as dt
import gzip
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import quote

from comun import DIR_DATOS, conectar

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / 'original/scripts'))

VISTA = '''CREATE OR REPLACE VIEW public.v_rdf_reportes AS
 SELECT md5(jsonb_build_array(r.id_ubicacion,t.anio,r.tipo_reporte,r.clasificacion,r.recurso)::text) AS id_agregado,
        r.id_ubicacion,t.anio,r.tipo_reporte,r.clasificacion,r.recurso,
        count(*) AS reportes, count(*) FILTER(WHERE r.metodo_ubicacion='manzana_cercana') AS ubicados_por_cercania,
        coalesce(r.id_ubicacion::text,'SIN_UBICACION') AS ubicacion_clave,
        CASE WHEN r.id_ubicacion IS NULL THEN true END AS sin_ubicacion
 FROM public.fact_reporte_agua r JOIN public.dim_tiempo t USING(id_tiempo)
 GROUP BY r.id_ubicacion,t.anio,r.tipo_reporte,r.clasificacion,r.recurso'''


def literal(v):
    return json.dumps(str(v),ensure_ascii=False)


def materializar(registrar=None):
    from exportar_grafo_base import exportar
    destino=DIR_DATOS/'grafo_integrado.ttl'
    temporal=DIR_DATOS/'grafo_integrado.ttl.part'
    with conectar() as conn:
        conn.execute(VISTA)
        resumen=exportar(conn,temporal)
        cur=conn.cursor()
        fuentes=cur.execute("SELECT nombre,url FROM etl.recurso WHERE conjunto='reportes-de-agua' ORDER BY id_recurso").fetchall()
        filas=cur.execute('''SELECT id_agregado,id_ubicacion,anio,tipo_reporte,clasificacion,recurso,
            reportes,ubicados_por_cercania FROM public.v_rdf_reportes ORDER BY id_agregado''').fetchall()
        # Columnas del SELECT: id, colonia, año, tipo, clasificación, recurso, total, cercanía.
        total=sum(r[6] for r in filas)
        esperado=cur.execute('SELECT count(*) FROM public.fact_reporte_agua').fetchone()[0]
        if total != esperado:
            raise ValueError('El agregado RDF no conserva el total de reportes')
        tipos=sorted({r[3] for r in filas})
        with temporal.open('a',encoding='utf-8',newline='\n') as f:
            f.write('\n# Extension local: reportes oficiales; agregados por colonia/año/tipo/recurso.\n')
            f.write('@prefix rep: <https://w3id.org/cdmx/agua/reportes/> .\n')
            f.write('@prefix tipo: <https://w3id.org/cdmx/agua/tipo-reporte/> .\n')
            f.write('agua:reportesSACMEX a qb:DataSet ; rdfs:label "Reportes ciudadanos oficiales SACMEX"@es ;\n')
            f.write('  dcterms:description "Todos los reportes integrados, agregados por colonia, año, tipo, clasificación y recurso. No son observaciones individuales ni diagnósticos de fugas."@es ;\n')
            f.write(f'  agua:sourceRecords {total} ; qb:structure agua:reportesDSD ;\n')
            f.write('  dcterms:source <https://datos.cdmx.gob.mx/dataset/reportes-de-agua> .\n')
            f.write('agua:reportesDSD a qb:DataStructureDefinition ;\n'
                    ' qb:component [qb:dimension agua:reportLocationKey], [qb:dimension agua:reportYear], '
                    '[qb:dimension agua:reportType], [qb:dimension agua:reportClassification], '
                    '[qb:dimension agua:sourceResource], [qb:measure agua:reportCount] .\n')
            f.write('agua:reportLocationKey a qb:DimensionProperty .\nagua:reportYear a qb:DimensionProperty .\n'
                    'agua:reportClassification a qb:DimensionProperty .\nagua:sourceResource a qb:DimensionProperty .\n'
                    'agua:reportType a qb:DimensionProperty .\nagua:reportCount a qb:MeasureProperty .\n')
            for nombre,url in fuentes:
                uri=quote(url,safe=':/?=&%#-_.~')
                f.write(f'agua:reportesSACMEX prov:wasDerivedFrom <{uri}> .\n')
            for tipo in tipos:
                f.write(f'tipo:{quote(tipo,safe="")} a skos:Concept ; skos:prefLabel {literal(tipo)}@es .\n')
            for ident,colonia,anio,tipo,clase,recurso,n,cercania in filas:
                f.write(f'rep:{ident} a qb:Observation ; qb:dataSet agua:reportesSACMEX ;\n')
                # Código técnico explícito para un dato faltante, nunca una colonia inventada.
                f.write(f' agua:reportLocationKey {literal(colonia if colonia is not None else "SIN_UBICACION")} ;\n')
                if colonia is not None:
                    f.write(f' agua:location col:{colonia} ;\n')
                else:
                    f.write(' agua:hasUnassignedLocation true ;\n')
                f.write(f' agua:reportYear {anio} ; agua:reportType tipo:{quote(tipo,safe="")} ;\n')
                f.write(f' agua:reportClassification {literal(clase)} ; agua:sourceResource {literal(recurso)} ;\n')
                f.write(f' agua:reportCount {n} ; agua:nearbyAssignedReports {cercania} .\n')
    temporal.replace(destino)
    resumen.update(reportes_representados=total,agregados_reportes=len(filas),
                   sin_colonia=sum(r[6] for r in filas if r[1] is None),
                   generado_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                   granularidad='colonia, año, tipo, clasificación y recurso',
                   bytes=destino.stat().st_size,sha256=hashlib.sha256(destino.read_bytes()).hexdigest())
    comprimido=destino.with_suffix('.ttl.gz')
    parcial=comprimido.with_suffix('.gz.part')
    with destino.open('rb') as entrada,gzip.open(parcial,'wb') as salida:
        import shutil
        shutil.copyfileobj(entrada,salida)
    parcial.replace(comprimido)
    meta=DIR_DATOS/'grafo_integrado.json'
    meta.write_text(json.dumps(resumen,ensure_ascii=False,indent=2),encoding='utf-8')
    if registrar:
        registrar('transformacion','Materializar reportes reales en el grafo RDF',total,
                  f'{len(filas):,} observaciones agregadas; {resumen["sin_colonia"]:,} reportes sin colonia conservados')
    return resumen


if __name__=='__main__':
    print(json.dumps(materializar(),ensure_ascii=False,indent=2))
