# Cómo presentar la práctica

## Demostración de 3–5 minutos

1. Abrir agua en http://127.0.0.1:8092. Mostrar la tarjeta de integración: consumo y clima originales más 555,752 reportes reales.
2. Abrir «interfaz original del artículo». Explicar que ahora su `consumo.json` lo construye el backend desde PostgreSQL. Regresar al módulo de reportes.
3. En el periodo enero–junio de 2019, mostrar los 39,685 reportes de falta de agua, seleccionar una alcaldía y enseñar cómo cambian los indicadores, el mapa y las tablas.
4. Mostrar la bitácora de agua: 71,102 filas de consumo leídas, 216 descartadas, 12,729 folios repetidos del recurso nuevo y cinco reportes sin tipo. Los rechazos no se sustituyen por datos inventados.
5. Abrir obras en http://127.0.0.1:8093. Mostrar 59 obras, $58,834,555 aprobados, mapa y clasificación por sector.
6. Filtrar Educación: 12 obras y $9,300,000 aprobados. Abrir un folio para mostrar el registro original y sus georreferencias, metas y contratos.
7. Mostrar `obra-publica-srft/datos/procedencia.json`: URL oficial, filtro y hashes. Enseñar `evidencia/verificacion.json` y las consultas siguientes.
8. Abrir http://127.0.0.1:8093/expedientes/. Elegir un folio y mostrar contratos, números administrativos, fuentes de financiamiento y campos no publicados. Explicar que los supervisores y firmas desconocidos no se inventan.
9. Abrir http://127.0.0.1:8092/sistema/grafo.html. Ejecutar «Reportes reales por año» y «Reportes sin colonia asignable». La suma de conteos conserva los 555,752 reportes; los no ubicados suman 4,804.

## Explicación breve

«Ampliamos los data warehouses de los proyectos originales con fuentes oficiales. Para agua integramos reportes ciudadanos de SACMEX y conservamos consumo y clima del modelo anterior. Para obras descargamos el informe definitivo 2025 de SHCP, filtramos Temascaltepec y añadimos 59 obras reales al warehouse original. Los ETL extraen, validan y transforman los CSV, registran la carga y permiten rastrear cada dato. Los backend consultan las bases locales y las interfaces visualizan esos resultados. No generamos registros ficticios.»

## Evidencia de base de datos

Agua:

```powershell
docker exec fa-agua-db psql -U agua -d agua_dw -c "SELECT count(*) FROM public.fact_reporte_agua;"
docker exec fa-agua-db psql -U agua -d agua_dw -c "SELECT count(*), sum(consumo_total) FROM public.fact_consumo_agua;"
docker exec fa-agua-db psql -U agua -d agua_dw -c "SELECT count(*) FROM public.fact_clima;"
```

Resultados esperados: **555,752 reportes**; **70,886 consumos** con suma **120,357,145.33 m³**; **181 días de clima**.

Obras:

```powershell
docker compose -f obra-publica-srft/compose.yml exec db psql -U obras -d obras_publicas -c "SELECT count(*),sum(aprobado),sum(pagado) FROM warehouse.fact_srft;"
docker compose -f obra-publica-srft/compose.yml exec db psql -U obras -d obras_publicas -c "SELECT clasificacion,count(*),sum(aprobado) FROM warehouse.fact_srft GROUP BY 1 ORDER BY 1;"
```

Resultados esperados: **59 obras**, **58,834,555.00 aprobados**, **58,803,710.52 pagados**.

| Clasificación | Obras | Aprobado MXN |
|---|---:|---:|
| Agua y saneamiento | 14 | 16,486,555.00 |
| Educación | 12 | 9,300,000.00 |
| Urbanización | 30 | 32,400,000.00 |
| Vivienda | 3 | 648,000.00 |

## Qué sí y qué no afirmar

- Sí: los datos son descargables, se conservan CSV, se integran a dimensiones de los modelos originales y se visualizan con consultas al backend.
- Sí: la carga repetida se comprueba sin duplicar los reportes ni los folios de obras.
- No: que los reportes ciudadanos prueban físicamente una fuga o que el gasto reportado demuestra la ejecución material de una obra.
- No: que se incorporaron todas las obras del municipio; SHCP solo cubre los recursos federales reportados.
- No: que el consumo de 2019 representa el consumo actual o que su comparación con reportes de otros años demuestra causalidad.
- Sí: se importaron los expedientes administrativos con los campos publicados. No afirmar que incluyen actas firmadas, personal identificado o todos los documentos del expediente municipal: esos datos no aparecen en la fuente.
- Sí: el grafo incorpora todos los reportes mediante agregados verificables. Para contarlos se suma `agua:reportCount`, no se cuentan las observaciones agregadas.

## Antes de exponer

Abrir Docker Desktop, ejecutar `iniciar-docker.ps1` y comprobar ambas páginas. Si está disponible el entorno Python local, ejecutar también `python verificar.py`. Conservar la carpeta completa: incluye los CSV y las copias atribuidas de los componentes originales. No hace falta realizar push para presentar localmente.
