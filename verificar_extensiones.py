"""Verifica expedientes reales y que RDF/SPARQL conserve los datos del DW."""
import csv
import datetime as dt
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

RAIZ=Path(__file__).resolve().parent
sys.path.insert(0,str(RAIZ/'.runtime'))
import psycopg
import requests
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF

pruebas=[]
def comprobar(nombre,condicion,detalle):
    pruebas.append(dict(prueba=nombre,ok=bool(condicion),detalle=detalle))
    print(('OK  ' if condicion else 'ERROR  ')+nombre,flush=True)


def main():
    base='http://127.0.0.1:8093'
    r=requests.get(base+'/api/public/obras',timeout=30)
    r.raise_for_status()
    obras=r.json()['data']
    comprobar('API original visualiza 59 obras oficiales',len(obras)==59,len(obras))
    comprobar('Estatus original respeta el cierre SHCP',all(x['status']=='completada' for x in obras),len(obras))
    detalle=requests.get(base+'/api/srft/expediente/MEX250202529773',timeout=30).json()
    comprobar('Expediente incluye contrato oficial y presupuesto',detalle['contrato_srft'] and Decimal(str(detalle['presupuesto_total']))==Decimal('600000'),detalle.get('folio'))
    with psycopg.connect('postgresql://obras:obras_local@localhost:5443/obras_publicas') as c:
        n=c.execute('SELECT count(*) FROM public.expediente_srft e JOIN public.obra o USING(id_obra) JOIN public.presupuesto_obra p USING(id_obra)').fetchone()[0]
        comprobar('59 expedientes vinculados a obra y presupuesto originales',n==59,n)
        n=c.execute('SELECT count(*) FROM public.personal').fetchone()[0]
        comprobar('No se inventó personal para importar expedientes',n==0,n)
        n=c.execute('SELECT count(*) FROM public.acta_entrega').fetchone()[0]
        comprobar('No se inventaron actas de entrega',n==0,n)
        n=c.execute("SELECT count(*) FROM public.obra WHERE origen_datos='SHCP_SRFT' AND codigo_supervisor IS NULL").fetchone()[0]
        comprobar('Supervisores no publicados permanecen nulos',n==59,n)
        n=c.execute("SELECT count(*) FROM public.constructora WHERE id_constructora LIKE 'SRFT:%' AND rfc IS NOT NULL").fetchone()[0]
        comprobar('RFC del convocante no se atribuye a contratistas',n==0,n)
        with (RAIZ/'obra-publica-srft/datos/shcp_srft/contratos_temascaltepec.csv').open(encoding='utf-8',newline='') as f:
            fuente=list(csv.DictReader(f))
        n=c.execute('SELECT count(*) FROM public.contrato_srft').fetchone()[0]
        comprobar('Se conservan todos los contratos publicados',n==len(fuente),n)
        aprobado=c.execute('SELECT sum(p.presupuesto_total) FROM public.presupuesto_obra p JOIN public.expediente_srft e USING(id_obra)').fetchone()[0]
        comprobar('Presupuesto administrativo coincide con SHCP',aprobado==Decimal('58834555.00'),str(aprobado))
        n=c.execute("SELECT count(*) FROM warehouse.fact_eventos_auditoria e JOIN warehouse.dim_tipo_evento t USING(tipo_evento_key) WHERE t.codigo_evento='IMPORTACION_SHCP'").fetchone()[0]
        comprobar('Auditoría distingue importaciones de creación histórica',n==59,n)
        n=c.execute("SELECT count(*) FROM warehouse.dim_obra WHERE obra_id LIKE 'SRFT:%' AND es_actual").fetchone()[0]
        comprobar('Una versión vigente por expediente después de recargar',n==59,n)
    print('Analizando RDF completo...',flush=True)
    contenido=requests.get('http://127.0.0.1:8092/sistema/kg_demo.ttl',timeout=90)
    contenido.raise_for_status()
    g=Graph().parse(data=contenido.content,format='turtle')
    comprobar('RDF Turtle integrado válido',len(g)>148000,len(g))
    a=Namespace('https://w3id.org/cdmx/agua/')
    total=sum(int(n) for n in g.objects(None,a.reportCount))
    comprobar('RDF conserva los 555752 reportes',total==555752,total)
    sin=sum(int(g.value(s,a.reportCount)) for s in g.subjects(a.hasUnassignedLocation,None))
    comprobar('RDF conserva 4804 reportes sin inventar colonia',sin==4804,sin)
    col=URIRef('http://www.opengis.net/ont/geosparql#Feature')
    invalidos=[str(o) for o in g.objects(None,a.location) if (o,RDF.type,col) not in g]
    comprobar('Consumo y reportes comparten colonias del DW vivo',not invalidos,len(invalidos))
    consulta='''PREFIX agua:<https://w3id.org/cdmx/agua/>
        SELECT ?anio (SUM(?n) AS ?total) WHERE {
        ?o agua:reportYear ?anio ; agua:reportCount ?n . } GROUP BY ?anio ORDER BY ?anio'''
    rdf={int(r[0]):int(r[1]) for r in g.query(consulta)}
    with psycopg.connect('postgresql://agua:agua_local@localhost:5442/agua_dw') as c:
        sql=dict(c.execute('SELECT t.anio,count(*) FROM public.fact_reporte_agua r JOIN public.dim_tiempo t USING(id_tiempo) GROUP BY 1').fetchall())
    comprobar('SPARQL por año coincide con SQL',rdf==sql,rdf)
    respuesta=requests.post('http://127.0.0.1:8092/api/grafo/sparql',json={'query':consulta},timeout=120)
    respuesta.raise_for_status()
    bindings=respuesta.json()['results']['bindings']
    servidor={int(r['anio']['value']):int(r['total']['value']) for r in bindings}
    comprobar('Endpoint SPARQL del explorador coincide con SQL',servidor==sql,servidor)
    sin_ubicacion=list(g.subjects(a.hasUnassignedLocation,None))
    comprobar('Agregados no ubicados carecen de colonia inventada',all(g.value(s,a.location) is None for s in sin_ubicacion),len(sin_ubicacion))
    # Validar también el mapeo declarativo que acompaña a la extensión.
    m=Graph().parse(RAIZ/'agua-reportes-sacmex/original/frontend/mapping-reportes.r2rml.ttl',format='turtle')
    comprobar('Mapeo R2RML de reportes sintácticamente válido',len(m)>0,len(m))
    salida=dict(verificado_utc=dt.datetime.now(dt.timezone.utc).isoformat(),pruebas=pruebas,
                grafo=dict(triples=len(g),sha256=hashlib.sha256(contenido.content).hexdigest(),reportes_por_anio=rdf))
    (RAIZ/'evidencia/extensiones.json').write_text(json.dumps(salida,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if all(p['ok'] for p in pruebas) else 1


if __name__=='__main__':
    sys.exit(main())
