"""SPARQL de lectura sobre la materialización local; sin acceso a fuentes remotas."""
import json
from functools import lru_cache
from pathlib import Path

from rdflib import Graph, Namespace
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.parserutils import CompValue
from pyparsing import ParseResults


@lru_cache(maxsize=1)
def cargar(archivo,modificado,tamano):
    return Graph().parse(Path(archivo),format='turtle')


def validar(consulta):
    arbol=parseQuery(consulta)
    if arbol[1].name not in ('SelectQuery','AskQuery'):
        raise ValueError('Solo se permiten consultas SELECT o ASK de lectura')
    def visitar(nodo):
        if isinstance(nodo,CompValue):
            if nodo.name in ('ServiceGraphPattern','DatasetClause'):
                raise ValueError('La consulta debe usar el grafo local, sin SERVICE ni FROM remotos')
            for valor in nodo.values():
                visitar(valor)
        elif isinstance(nodo,(list,tuple,ParseResults)):
            for valor in nodo:
                visitar(valor)
    visitar(arbol)


def consultar(archivo,consulta):
    validar(consulta)
    stat=archivo.stat()
    g=cargar(str(archivo),stat.st_mtime_ns,stat.st_size)
    resultado=g.query(consulta)
    a=Namespace('https://w3id.org/cdmx/agua/')
    respuesta=json.loads(resultado.serialize(format='json'))
    respuesta['meta']={
        'triples':len(g),
        'adyacencias':sum(1 for _ in g.triples((None,a.nearbyWithin1500m,None))),
    }
    return respuesta
