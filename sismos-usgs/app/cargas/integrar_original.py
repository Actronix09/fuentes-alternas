"""Extiende el DW original del paper en public sin reemplazar sus dimensiones ni su hecho de impacto.

El DW original (gabrielhuav/Seismic-Data-Visualization-System) se carga una sola vez desde sus
propios scripts SQL. Después se añade public.fact_cruce_usgs, que liga cada sismo del SSN
(public.dim_sismos) y su tiempo original (public.dim_tiempo, donde id_tiempo = id_sismo) con el
resultado del emparejamiento contra USGS ComCat calculado en el esquema dw.
"""
from pathlib import Path

from comun import conectar
from fuentes import ssn_original

RAIZ = Path(__file__).resolve().parents[2]
COMMIT = "8569667"


def scripts_originales() -> list[Path]:
    """Scripts del DW original en el orden de su docker-compose."""
    sql = RAIZ / "original/sql"
    ssn = ssn_original.DIRECTORIO
    return [sql / "00-datawarehouse_tables.sql",
            sql / "01-dim_zonas.sql",
            ssn / f"{COMMIT}_02-dim_tiempo.sql",
            ssn / f"{COMMIT}_03-dim_sismos.sql",
            sql / "04-dim_economia.sql",
            ssn / f"{COMMIT}_05-fact_impacto_sismos_imputed.sql"]


def integrar_original(registrar=None):
    with conectar() as conn, conn.cursor() as cur:
        # El DW original se carga tal cual, con sus propias claves; no se recarga si ya existe.
        if cur.execute("SELECT to_regclass('public.fact_impacto_sismos_imputed')").fetchone()[0] is None:
            for script in scripts_originales():
                cur.execute(script.read_text(encoding="utf-8"))
                if registrar:
                    registrar("carga", f"DW original: {script.name.removeprefix(COMMIT + '_')}")

        cur.execute('''
            CREATE TABLE IF NOT EXISTS public.dim_fuente_sismo (
                id_fuente smallint PRIMARY KEY,
                codigo text NOT NULL UNIQUE,
                nombre text NOT NULL,
                institucion text NOT NULL,
                url text NOT NULL,
                doi text,
                cita_apa text NOT NULL);
            INSERT INTO public.dim_fuente_sismo
            SELECT id_fuente, codigo, nombre, institucion, url, doi, cita_apa FROM dw.dim_fuente
            ON CONFLICT (id_fuente) DO UPDATE SET
                codigo=excluded.codigo, nombre=excluded.nombre, institucion=excluded.institucion,
                url=excluded.url, doi=excluded.doi, cita_apa=excluded.cita_apa;
            CREATE TABLE IF NOT EXISTS public.fact_cruce_usgs (
                variante text NOT NULL CHECK (variante IN ('corregida', 'dw_original')),
                id_sismo integer NOT NULL REFERENCES public.dim_sismos,
                id_tiempo integer NOT NULL REFERENCES public.dim_tiempo,
                id_fuente smallint NOT NULL REFERENCES public.dim_fuente_sismo,
                resultado text NOT NULL CHECK (resultado IN ('ambas', 'solo_ssn')),
                fecha_hora_utc timestamptz NOT NULL,
                fecha_corregida boolean NOT NULL,
                id_usgs text,
                fecha_hora_usgs timestamptz,
                magnitud_usgs double precision,
                tipo_magnitud_usgs text,
                red_localizacion text,
                red_magnitud text,
                independiente boolean,
                delta_segundos double precision,
                distancia_km double precision,
                delta_magnitud double precision,
                delta_profundidad_km double precision,
                PRIMARY KEY (variante, id_sismo),
                CHECK ((resultado = 'ambas') = (id_usgs IS NOT NULL)));
            CREATE INDEX IF NOT EXISTS idx_cruce_usgs_tiempo ON public.fact_cruce_usgs(id_tiempo);
            CREATE INDEX IF NOT EXISTS idx_cruce_usgs_resultado ON public.fact_cruce_usgs(variante, resultado);
            DELETE FROM public.fact_cruce_usgs;
            INSERT INTO public.fact_cruce_usgs
            SELECT f.variante, o.id_sismo, t.id_tiempo, 2, f.resultado,
                   s.fecha_hora_utc, s.fecha_corregida,
                   u.id_externo, u.fecha_hora_utc, u.magnitud, u.tipo_magnitud,
                   u.red_localizacion, u.red_magnitud, f.independiente,
                   f.delta_segundos, f.distancia_km, f.delta_magnitud, f.delta_profundidad_km
            FROM dw.fact_cruce_sismo f
            JOIN dw.dim_sismo s ON s.id_sismo = f.id_sismo_ssn
            JOIN public.dim_sismos o ON o.id_sismo = s.id_externo::integer
            JOIN public.dim_tiempo t ON t.id_tiempo = o.id_sismo
            LEFT JOIN dw.dim_sismo u ON u.id_sismo = f.id_sismo_usgs
            WHERE f.resultado IN ('ambas', 'solo_ssn');
            CREATE OR REPLACE VIEW public.v_cruce_usgs AS
            SELECT c.id_sismo, c.resultado = 'ambas' AS confirmado_usgs, c.independiente,
                   c.id_usgs, c.magnitud_usgs, c.tipo_magnitud_usgs,
                   round(c.distancia_km::numeric, 1) AS distancia_km,
                   round(c.delta_magnitud::numeric, 2) AS delta_magnitud,
                   c.fecha_hora_utc, c.fecha_corregida
            FROM public.fact_cruce_usgs c
            WHERE c.variante = 'corregida';
            COMMENT ON TABLE public.fact_cruce_usgs IS
                'Extensión del DW original: resultado del cruce de cada sismo del SSN con USGS ComCat.';
            COMMENT ON COLUMN public.fact_cruce_usgs.id_tiempo IS
                'Registro original de public.dim_tiempo (fecha local + hora UTC); fecha_hora_utc es el instante reconstruido.';
            COMMENT ON VIEW public.v_cruce_usgs IS
                'Cruce con fechas corregidas a UTC, para consultas del frontend original.';
        ''')
        n = cur.execute("SELECT count(*) FROM public.fact_cruce_usgs").fetchone()[0]
    if registrar:
        registrar("transformacion", "Integrar el cruce al DW original public.fact_cruce_usgs", n)
    return n


if __name__ == "__main__":
    print(f"{integrar_original():,} registros de cruce integrados al DW original")
