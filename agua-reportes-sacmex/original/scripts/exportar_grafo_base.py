# Adaptación local del exportador original: recibe una conexión existente.
#!/usr/bin/env python3
"""
exportar_grafo_demo.py -- Exports a browser-sized subset of the RDF knowledge
graph, so that the SPARQL explorer of the static demonstration can run entirely
on the client.

The full materialisation of mapping.r2rml.ttl is too large to parse in a browser.
This script emits an
equivalent graph at a coarser grain:

  * every location, with its label, borough and WKT centroid  (1,553)
  * territorial adjacency limited to the six nearest neighbours within 1.5 km,
    instead of every pair within that radius
  * observations aggregated to the neighbourhood-period grain rather than one
    per fact row  (10,641 instead of 70,886)
  * the complete time and development-index dimensions, and the daily climate
    observations

The subset uses distinct observation and dataset IRIs and declares its
derivation from the full materialisation, so a consumer cannot merge both
graphs accidentally as if their observations had the same identity.

    python scripts/exportar_grafo_demo.py \
        --dsn "postgresql://postgres:postgres@localhost:5433/data_warehouse" \
        --salida kg_demo.ttl
"""

from __future__ import annotations

import argparse
import heapq
import math
import os
import sys
from datetime import datetime, timezone
from urllib.parse import quote

# En Turtle, "/" no es valido dentro de un nombre prefijado sin escapar, asi que
# cada tipo de recurso lleva su propio prefijo. Las IRIs resultantes son
# identicas a las que produce mapping.r2rml.ttl sobre el almacen completo.
PREFIJOS = """@prefix agua:    <https://w3id.org/cdmx/agua/> .
@prefix col:     <https://w3id.org/cdmx/agua/colonia/> .
@prefix alc:     <https://w3id.org/cdmx/agua/alcaldia/> .
@prefix geom:    <https://w3id.org/cdmx/agua/geom/> .
@prefix per:     <https://w3id.org/cdmx/agua/period/> .
@prefix idx:     <https://w3id.org/cdmx/agua/devindex/> .
@prefix aggobs:  <https://w3id.org/cdmx/agua/aggobs/> .
@prefix clm:     <https://w3id.org/cdmx/agua/clima/> .
@prefix qb:      <http://purl.org/linked-data/cube#> .
@prefix geo:     <http://www.opengis.net/ont/geosparql#> .
@prefix skos:    <http://www.w3.org/2004/02/skos/core#> .
@prefix time:    <http://www.w3.org/2006/time#> .
@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix prov:    <http://www.w3.org/ns/prov#> .

"""

K_VECINOS = 6
RADIO_KM = 1.5


def esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def iri_segment(s: str) -> str:
    """Return a percent-encoded IRI path segment for a borough name."""
    return quote(s or "", safe="")


def km(a, b) -> float:
    """Distancia aproximada en km entre dos (lat, lon)."""
    return 111.32 * math.hypot(a[0] - b[0],
                               (a[1] - b[1]) * math.cos(math.radians(a[0])))


def exportar(conn, salida, k=K_VECINOS, radio=RADIO_KM):
    from types import SimpleNamespace
    args = SimpleNamespace(salida=str(salida), k=k, radio=radio)
    cur = conn.cursor()

    # ---------------- dimensiones ------------------------------------
    cur.execute("SELECT id_ubicacion, alcaldia, colonia, latitud, longitud "
                "FROM dim_ubicacion ORDER BY id_ubicacion;")
    ubic = cur.fetchall()
    cur.execute("SELECT id_tiempo, fecha, anio, bimestre FROM dim_tiempo "
                "ORDER BY id_tiempo;")
    tiempos = cur.fetchall()
    cur.execute("SELECT id_indice_des, indice_des FROM dim_indice_des "
                "ORDER BY indice_des;")
    indices = cur.fetchall()

    # ---------------- observaciones agregadas ------------------------
    cur.execute("""
        SELECT u.id_ubicacion, t.id_tiempo, i.id_indice_des,
               SUM(f.consumo_total), AVG(f.consumo_prom),
               SUM(f.consumo_total_dom), SUM(f.consumo_total_no_dom),
               SUM(f.consumo_total_mixto), COUNT(*)
        FROM   fact_consumo_agua f
        JOIN   dim_ubicacion  u USING (id_ubicacion)
        JOIN   dim_tiempo     t USING (id_tiempo)
        JOIN   dim_indice_des i USING (id_indice_des)
        GROUP  BY u.id_ubicacion, t.id_tiempo, i.id_indice_des
        ORDER  BY u.id_ubicacion, t.id_tiempo;
    """)
    obs = cur.fetchall()

    cur.execute("""SELECT t.id_tiempo, fc.temp_maxima, fc.temp_minima,
                          fc.temp_promedio, fc.humedad_promedio, fc.lluvia_total
                   FROM fact_clima fc JOIN dim_tiempo t USING (id_tiempo)
                   ORDER BY t.id_tiempo;""")
    clima = cur.fetchall()
    cur.close()

    # ---------------- adyacencia k-NN --------------------------------
    pts = {u[0]: (float(u[3]), float(u[4]))
           for u in ubic if u[3] is not None and u[4] is not None}
    ids = list(pts)
    adyacencia = []
    for a in ids:
        cercanos = heapq.nsmallest(
            args.k, ((km(pts[a], pts[b]), b) for b in ids if b != a))
        for dist, b in cercanos:
            if dist <= args.radio:
                adyacencia.append((a, b, round(dist, 3)))

    # ---------------- escribir Turtle --------------------------------
    n = 0
    with open(args.salida, "w", encoding="utf-8") as f:
        f.write(PREFIJOS)
        f.write(f"""agua:consumoCDMXDemo a qb:DataSet ;
  rdfs:label "Water consumption, Mexico City (browser subset)"@en ;
  dcterms:description "Browser-sized subset of the knowledge graph materialised from the data warehouse. Observations are aggregated to the neighbourhood-period grain and proximity is limited to the {args.k} nearest neighbours within {args.radio} km."@en ;
  dcterms:created "{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"^^xsd:dateTime ;
  prov:wasDerivedFrom agua:consumoCDMX ;
  qb:structure agua:consumoDSD ;
  agua:unit agua:cubicMetre .

""")
        n += 7

        f.write("# ---------- boroughs ----------\n")
        for alc in sorted({u[1] for u in ubic}):
            f.write(f'alc:{iri_segment(alc)} rdfs:label "{esc(alc)}"@es .\n')
            n += 1
        f.write("\n")

        f.write("# ---------- territory ----------\n")
        for uid, alc, col, lat, lon in ubic:
            f.write(f'col:{uid} a geo:Feature ;\n'
                    f'  rdfs:label "{esc(col)}"@es ;\n'
                    f'  agua:borough alc:{iri_segment(alc)} ;\n')
            n += 3
            if lat is not None and lon is not None:
                f.write(f'  agua:latitude {lat} ; agua:longitude {lon} ;\n'
                        f'  geo:hasGeometry geom:{uid} .\n\n'
                        f'geom:{uid} a geo:Geometry ;\n'
                        f'  geo:asWKT "POINT({lon} {lat})"^^geo:wktLiteral .\n\n')
                n += 5
            else:
                f.write("  agua:hasNoGeometry true .\n\n")

        f.write("# ---------- adjacency (derived by centroid proximity) ----------\n")
        for a, b, dist in adyacencia:
            f.write(f'col:{a} agua:nearbyWithin1500m col:{b} .\n')
            n += 1
        f.write("\n")

        f.write("# ---------- time ----------\n")
        for tid, fecha, anio, bim in tiempos:
            f.write(f'per:{tid} a time:TemporalEntity ;\n'
                    f'  agua:date "{fecha}"^^xsd:date ;\n'
                    f'  agua:year "{anio}"^^xsd:gYear ;\n'
                    f'  agua:bimester {bim} .\n')
            n += 4
        f.write("\n# ---------- development index ----------\n")
        for iid, nivel in indices:
            segmento = iri_segment(nivel)
            f.write(f'idx:{segmento} a skos:Concept ;\n'
                    f'  skos:prefLabel "{esc(nivel)}"@es ;\n'
                    f'  skos:inScheme agua:indiceDesarrollo .\n')
            n += 3

        f.write("\n# ---------- observations (neighbourhood-period grain) ----------\n")
        indice_por_id = {iid: iri_segment(nivel) for iid, nivel in indices}
        for k, (uid, tid, iid, tot, prom, dom, nodom, mix, cnt) in enumerate(obs, 1):
            f.write(f'aggobs:{k} a qb:Observation ;\n'
                    f'  qb:dataSet agua:consumoCDMXDemo ;\n'
                    f'  agua:location col:{uid} ;\n'
                    f'  agua:period per:{tid} ;\n'
                    f'  agua:developmentIndex idx:{indice_por_id[iid]} ;\n'
                    f'  agua:totalConsumption {float(tot or 0):.2f} ;\n'
                    f'  agua:averageConsumption {float(prom or 0):.2f} ;\n'
                    f'  agua:domesticConsumption {float(dom or 0):.2f} ;\n'
                    f'  agua:nonDomesticConsumption {float(nodom or 0):.2f} ;\n'
                    f'  agua:mixedConsumption {float(mix or 0):.2f} ;\n'
                    f'  agua:sourceRecords {cnt} .\n')
            n += 11

        f.write("\n# ---------- climate ----------\n")
        for k, (tid, tmax, tmin, tavg, hum, lluv) in enumerate(clima, 1):
            f.write(f'clm:{k} a qb:Observation ;\n'
                    f'  qb:dataSet agua:climaCDMX ;\n'
                    f'  agua:period per:{tid} ;\n'
                    f'  agua:maxTemperature {float(tmax or 0):.2f} ;\n'
                    f'  agua:minTemperature {float(tmin or 0):.2f} ;\n'
                    f'  agua:meanTemperature {float(tavg or 0):.2f} ;\n'
                    f'  agua:totalRainfall {float(lluv or 0):.2f} .\n')
            n += 7

    mb = os.path.getsize(args.salida) / 1024 / 1024
    print(f"Locations        : {len(ubic):,}")
    print(f"Adjacency pairs  : {len(adyacencia):,}  (k={args.k}, <= {args.radio} km)")
    print(f"Observations     : {len(obs):,}")
    print(f"Climate obs      : {len(clima):,}")
    print(f"Periods / levels : {len(tiempos)} / {len(indices)}")
    print(f"\nTriples written  : ~{n:,}")
    print(f"Output           : {args.salida}  ({mb:.1f} MB, ~{mb*0.12:.1f} MB gzipped)")
    return {"triples_base": n, "consumos_agregados": len(obs), "clima": len(clima), "colonias": len(ubic)}

