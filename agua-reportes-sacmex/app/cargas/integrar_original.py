"""Extiende el DW original en public sin reemplazar sus hechos de consumo y clima."""
import csv
import re
import unicodedata
from pathlib import Path

from comun import conectar
from fuentes import clima_original, consumo_cdmx

RAIZ = Path(__file__).resolve().parents[2]


def normalizar(texto):
    t = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode().upper()
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Z0-9 ]', ' ', t)).strip()


def integrar_original(registrar=None):
    with conectar() as conn, conn.cursor() as cur:
        # Se conserva el esquema original, con sus propias claves sustitutas.
        if cur.execute("SELECT to_regclass('public.fact_consumo_agua')").fetchone()[0] is None:
            cur.execute((RAIZ / 'original/ddl/0_schema.sql').read_text(encoding='utf-8'))
            for tabla, archivo in [('staging_consumo', consumo_cdmx.ARCHIVO),
                                   ('staging_clima', clima_original.ARCHIVO)]:
                with archivo.open(encoding='utf-8-sig', newline='') as f:
                    lector = csv.reader(f)
                    next(lector)
                    with cur.copy(f'COPY public.{tabla} FROM STDIN') as cp:
                        for fila in lector:
                            cp.write_row([None if v in ('NA', '') else v for v in fila])
            cur.execute((RAIZ / 'original/etl/2_dim.sql').read_text(encoding='utf-8'))
            cur.execute((RAIZ / 'original/etl/3_fact.sql').read_text(encoding='utf-8'))

        cur.execute('''
            ALTER TABLE public.dim_ubicacion ADD COLUMN IF NOT EXISTS latitud numeric(9,6);
            ALTER TABLE public.dim_ubicacion ADD COLUMN IF NOT EXISTS longitud numeric(9,6);
            UPDATE public.dim_ubicacion u SET latitud=c.lat, longitud=c.lon
            FROM (SELECT alcaldia,colonia,avg(latitud) AS lat,avg(longitud) AS lon
                  FROM staging.consumo WHERE latitud IS NOT NULL GROUP BY 1,2) c
            WHERE u.alcaldia=c.alcaldia AND u.colonia=c.colonia;
            CREATE TABLE IF NOT EXISTS public.dim_equivalencia_colonia (
                id_dw integer PRIMARY KEY REFERENCES dw.dim_ubicacion,
                id_original integer NOT NULL REFERENCES public.dim_ubicacion);
            CREATE TABLE IF NOT EXISTS public.fact_reporte_agua (
                recurso text NOT NULL, folio text NOT NULL,
                id_tiempo integer NOT NULL REFERENCES public.dim_tiempo,
                id_ubicacion integer REFERENCES public.dim_ubicacion,
                tipo_reporte text NOT NULL, clasificacion text NOT NULL,
                medio_recepcion text, metodo_ubicacion text,
                latitud numeric, longitud numeric,
                PRIMARY KEY(recurso, folio));
            CREATE INDEX IF NOT EXISTS idx_reporte_original_fecha
                ON public.fact_reporte_agua(id_tiempo, id_ubicacion);
            CREATE INDEX IF NOT EXISTS idx_reporte_original_tipo
                ON public.fact_reporte_agua(tipo_reporte, id_tiempo);
            CREATE INDEX IF NOT EXISTS idx_equivalencia_colonia_original
                ON public.dim_equivalencia_colonia(id_original);
            INSERT INTO public.dim_tiempo(fecha, anio, mes, dia, bimestre)
            SELECT fecha, anio, mes, dia, bimestre FROM dw.dim_tiempo
            ON CONFLICT(fecha) DO NOTHING;
            DELETE FROM public.dim_equivalencia_colonia;
        ''')
        equivalencias = {}
        for ident, alcaldia, colonia in cur.execute(
                'SELECT id_ubicacion, alcaldia, colonia FROM public.dim_ubicacion ORDER BY id_ubicacion'):
            equivalencias.setdefault((normalizar(alcaldia), normalizar(colonia)), ident)
        for ident, alcaldia, colonia in cur.execute(
                'SELECT id_ubicacion, alcaldia_norm, colonia_norm FROM dw.dim_ubicacion').fetchall():
            origen = equivalencias.get((alcaldia, colonia))
            if origen is not None:
                cur.execute('INSERT INTO public.dim_equivalencia_colonia VALUES (%s,%s)', [ident, origen])
        cur.execute('''
            INSERT INTO public.fact_reporte_agua
            SELECT r.recurso, r.folio, t.id_tiempo, e.id_original,
                   tr.reporte, tr.clasificacion, m.medio, r.metodo_ubicacion, r.latitud, r.longitud
            FROM dw.fact_reporte_agua r
            JOIN dw.dim_tiempo d ON d.id_tiempo=r.id_tiempo
            JOIN public.dim_tiempo t ON t.fecha=d.fecha
            JOIN dw.dim_tipo_reporte tr ON tr.id_tipo=r.id_tipo
            JOIN dw.dim_medio_recepcion m ON m.id_medio=r.id_medio
            LEFT JOIN public.dim_equivalencia_colonia e ON e.id_dw=r.id_ubicacion
            ON CONFLICT(recurso,folio) DO UPDATE SET
                id_tiempo=excluded.id_tiempo, id_ubicacion=excluded.id_ubicacion,
                tipo_reporte=excluded.tipo_reporte, clasificacion=excluded.clasificacion,
                medio_recepcion=excluded.medio_recepcion, metodo_ubicacion=excluded.metodo_ubicacion,
                latitud=excluded.latitud, longitud=excluded.longitud;
            CREATE OR REPLACE VIEW public.v_reportes_colonia AS
            SELECT u.alcaldia, u.colonia, t.anio, r.tipo_reporte, count(*) AS reportes
            FROM public.fact_reporte_agua r
            JOIN public.dim_tiempo t USING(id_tiempo)
            LEFT JOIN public.dim_ubicacion u USING(id_ubicacion)
            GROUP BY 1,2,3,4;
        ''')
        n = cur.execute('SELECT count(*) FROM public.fact_reporte_agua').fetchone()[0]
    if registrar:
        registrar('transformacion', 'Integrar reportes al DW original public.fact_reporte_agua', n)
    return n


if __name__ == '__main__':
    print(f'{integrar_original():,} reportes integrados al DW original')
