"""Carga de población anual oficial de EE. UU. y Canadá (fuentes census_us y statcan_ca).

Valida que las regiones sumen los totales nacionales, guarda el extracto integrado
y lo carga en PostgreSQL.

No modifica catálogos sísmicos, economía ni impactos imputados del original.
"""
import argparse
import csv
import datetime as dt
import json

from comun import DIR_DATOS, conectar, sha256
from fuentes import census_us, statcan_ca

# Extracto integrado de ambas fuentes y su manifiesto; los originales están en us/ y ca/.
DIRECTORIO = DIR_DATOS / 'demografia'
FUENTES = {'US': census_us, 'CA': statcan_ca}
COLUMNAS = ['pais', 'codigo', 'nombre', 'nivel', 'anio', 'poblacion', 'identificador_origen', 'estado_origen']


def validar(filas):
    """Claves únicas, cobertura completa y reconciliación con totales oficiales."""
    claves = set()
    for f in filas:
        f['anio'], f['poblacion'] = int(f['anio']), int(f['poblacion'])
        clave = f['pais'], f['codigo'], f['anio']
        if clave in claves or f['poblacion'] <= 0 or f['nivel'] not in ('pais', 'region'):
            raise ValueError(f'Registro demográfico inválido o duplicado: {clave}')
        claves.add(clave)
    for pais, regiones in [('US', 51), ('CA', 13)]:
        for anio in range(2020, 2026):
            grupo = [f for f in filas if f['pais'] == pais and f['anio'] == anio]
            detalle = [f for f in grupo if f['nivel'] == 'region']
            total = [f for f in grupo if f['nivel'] == 'pais']
            if len(detalle) != regiones or len(total) != 1:
                raise ValueError(f'Cobertura incompleta {pais}/{anio}')
            if sum(f['poblacion'] for f in detalle) != total[0]['poblacion']:
                raise ValueError(f'La suma regional no coincide con el total oficial {pais}/{anio}')
    if len(filas) != 396:
        raise ValueError('Se esperaban 396 observaciones (66 geografías × 6 años)')
    return filas


def preparar(actualizar=False):
    DIRECTORIO.mkdir(parents=True, exist_ok=True)
    extracto = DIRECTORIO / 'poblacion_2020_2025.csv'
    manifiesto = DIRECTORIO / 'procedencia.json'
    if not actualizar and extracto.exists() and manifiesto.exists():
        meta = json.loads(manifiesto.read_text(encoding='utf-8'))
        if sha256(extracto) != meta['sha256_extracto']:
            raise ValueError('El extracto no coincide con el hash de procedencia')
        with extracto.open(encoding='utf-8', newline='') as f:
            return validar(list(csv.DictReader(f))), meta

    filas, fuentes = [], {}
    for pais, fuente in FUENTES.items():
        observaciones, fuentes[pais] = fuente.extraer(actualizar)
        filas.extend(observaciones)
    validar(filas)
    filas.sort(key=lambda r: (r['pais'], r['codigo'], r['anio']))
    temporal = extracto.with_suffix('.csv.part')
    with temporal.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNAS, lineterminator='\n')
        writer.writeheader()
        writer.writerows(filas)
    temporal.replace(extracto)
    meta = dict(extraido_utc=dt.datetime.now(dt.timezone.utc).isoformat(), fuentes=fuentes,
                filtro='2020–2025, 1 de julio, todas las edades, población total; 50 estados + DC y 13 provincias/territorios',
                unidad='personas', observaciones=len(filas), sha256_extracto=sha256(extracto))
    manifiesto.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return filas, meta


DDL = '''
CREATE TABLE IF NOT EXISTS public.dim_fuente_demografia (
    pais text PRIMARY KEY CHECK (pais IN ('US','CA')),
    institucion text NOT NULL, titulo text NOT NULL, url text NOT NULL, doi text,
    sha256_original text NOT NULL);
CREATE TABLE IF NOT EXISTS public.dim_region_demografia (
    pais text NOT NULL REFERENCES public.dim_fuente_demografia,
    codigo text NOT NULL, nombre text NOT NULL,
    nivel text NOT NULL CHECK (nivel IN ('pais','region')),
    identificador_origen text NOT NULL, PRIMARY KEY(pais,codigo));
CREATE TABLE IF NOT EXISTS public.fact_poblacion_demografia (
    pais text NOT NULL, codigo text NOT NULL,
    fecha_referencia date NOT NULL, poblacion bigint NOT NULL CHECK (poblacion>0),
    estado_origen text NOT NULL,
    PRIMARY KEY(pais,codigo,fecha_referencia),
    FOREIGN KEY(pais,codigo) REFERENCES public.dim_region_demografia);
CREATE TABLE IF NOT EXISTS etl.demografia_carga (
    id bigserial PRIMARY KEY, cargado_utc timestamptz NOT NULL DEFAULT now(),
    sha256_extracto text NOT NULL, registros integer NOT NULL, procedencia jsonb NOT NULL);
CREATE OR REPLACE VIEW public.v_poblacion_demografia AS
SELECT r.pais,r.codigo,r.nombre,r.nivel,r.identificador_origen,
       extract(year FROM p.fecha_referencia)::integer AS anio,
       p.fecha_referencia,p.poblacion,p.estado_origen,
       f.institucion,f.titulo,f.url,f.doi
FROM public.fact_poblacion_demografia p
JOIN public.dim_region_demografia r USING(pais,codigo)
JOIN public.dim_fuente_demografia f USING(pais);
COMMENT ON TABLE public.fact_poblacion_demografia IS
    'Estimaciones oficiales de población al 1 de julio. Contexto demográfico; no población afectada por sismos.';
'''


def cargar(filas, meta):
    with conectar() as conn:
        conn.execute(DDL)
        for pais, f in meta['fuentes'].items():
            conn.execute('''INSERT INTO public.dim_fuente_demografia VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT(pais) DO UPDATE SET institucion=excluded.institucion,
                titulo=excluded.titulo,url=excluded.url,doi=excluded.doi,sha256_original=excluded.sha256_original''',
                         [pais, f['institucion'], f['titulo'], f['pagina'], f['doi'], f['sha256']])
        with conn.cursor() as cur:
            for r in filas:
                cur.execute('''INSERT INTO public.dim_region_demografia VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT(pais,codigo) DO UPDATE SET nombre=excluded.nombre,
                    nivel=excluded.nivel,identificador_origen=excluded.identificador_origen''',
                            [r[k] for k in ['pais','codigo','nombre','nivel','identificador_origen']])
                cur.execute('''INSERT INTO public.fact_poblacion_demografia VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT(pais,codigo,fecha_referencia) DO UPDATE SET
                    poblacion=excluded.poblacion,estado_origen=excluded.estado_origen''',
                            [r['pais'], r['codigo'], dt.date(r['anio'],7,1),r['poblacion'],r['estado_origen']])
        conn.execute('''INSERT INTO etl.demografia_carga(sha256_extracto,registros,procedencia)
            SELECT %s,%s,%s::jsonb WHERE NOT EXISTS
            (SELECT 1 FROM etl.demografia_carga WHERE sha256_extracto=%s)''',
                     [meta['sha256_extracto'],len(filas),json.dumps(meta),meta['sha256_extracto']])
    return len(filas)


def ejecutar(actualizar=False):
    filas, meta = preparar(actualizar)
    return cargar(filas, meta)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--descargar', action='store_true', help='Actualizar fuentes y regenerar extracto')
    parser.add_argument('--solo-extraer', action='store_true', help='Preparar y validar archivos sin cargar PostgreSQL')
    args = parser.parse_args()
    filas, meta = preparar(args.descargar)
    print(f'{len(filas)} observaciones validadas' if args.solo_extraer else f'{cargar(filas, meta)} observaciones cargadas')
