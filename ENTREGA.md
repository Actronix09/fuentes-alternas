# Cómo presentar la práctica

## Demostración de 4–6 minutos

1. Abrir agua en http://127.0.0.1:8092. Mostrar la tarjeta de integración: consumo y clima originales más 555,752 reportes reales.
2. Abrir «interfaz original del artículo». Explicar que ahora su `consumo.json` lo construye el backend desde PostgreSQL. Regresar al módulo de reportes.
3. En el periodo enero–junio de 2019, mostrar los 39,685 reportes de falta de agua, seleccionar una alcaldía y enseñar cómo cambian los indicadores, el mapa y las tablas.
4. Mostrar la bitácora de agua: 71,102 filas de consumo leídas, 216 descartadas, 12,729 folios repetidos del recurso nuevo y cinco reportes sin tipo. Los rechazos no se sustituyen por datos inventados.
5. Abrir obras en http://127.0.0.1:8093. Mostrar 59 obras, $58,834,555 aprobados, mapa y clasificación por sector.
6. Filtrar Educación: 12 obras y $9,300,000 aprobados. Abrir un folio para mostrar el registro original y sus georreferencias, metas y contratos.
7. Mostrar `obra-publica-srft/datos/procedencia.json`: URL oficial, filtro y hashes. Enseñar `evidencia/verificacion.json` y las consultas siguientes.
8. Abrir http://127.0.0.1:8093/expedientes/. Elegir un folio y mostrar contratos, números administrativos, fuentes de financiamiento y campos no publicados. Explicar que los supervisores y firmas desconocidos no se inventan.
9. Abrir http://127.0.0.1:8092/sistema/grafo.html. Ejecutar «Reportes reales por año» y «Reportes sin colonia asignable». La suma de conteos conserva los 555,752 reportes; los no ubicados suman 4,804.
10. Abrir sismos en http://127.0.0.1:8091. Mostrar la tarjeta de ampliación del DW original y el hallazgo de fechas: con M ≥ 4.5 y «Todas» las soluciones, la confirmación pasa de 64.2 % con las fechas del DW a 83.5 % con las corregidas.
11. Abrir la interfaz original en http://127.0.0.1:8094, entrar a «Mapa de sismos con confirmación USGS», elegir 2017 y magnitud 8. El M8.2 de Tehuantepec aparece el 7 de septiembre (fecha del DW) y su ventana indica que ComCat lo confirma a 36.4 km.

## Explicación breve

«Ampliamos los data warehouses de los proyectos originales con fuentes oficiales. Para sismos cargamos el DW del artículo y lo cruzamos con el catálogo ComCat del USGS. Así encontramos que el DW recorre un día la fecha de casi la cuarta parte de los sismos. Para agua integramos reportes ciudadanos de SACMEX y conservamos consumo y clima del modelo anterior. Para obras descargamos el informe definitivo 2025 de SHCP, filtramos Temascaltepec y añadimos 59 obras reales al warehouse original. Los ETL extraen, validan y transforman los CSV, registran la carga y permiten rastrear cada dato. Los backend consultan las bases locales y las interfaces visualizan esos resultados. No generamos registros ficticios.»

## Evidencia de base de datos

Sismos:

```powershell
docker exec fa-sismos-db psql -U sismos -d sismos_dw -c "SELECT count(*) FROM public.dim_sismos;" -c "SELECT count(*) FROM public.fact_impacto_sismos_imputed;"
docker exec fa-sismos-db psql -U sismos -d sismos_dw -c "SELECT variante, resultado, count(*) FROM public.fact_cruce_usgs GROUP BY 1,2 ORDER BY 1,2;"
```

Resultados esperados: **319,592 sismos** y **196,576 hechos de impacto** originales. Con la variante `corregida`, **18,489 sismos confirmados** y **30,783 solo en el SSN** (M ≥ 4.0). Con la variante `dw_original`, 14,084 y 34,075. Los conteos de ComCat pueden crecer un poco al recargar, porque el año en curso se vuelve a descargar.

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

- Sí: el DW original de sismos se conserva intacto. El cruce con USGS se añade como un hecho nuevo, enlazado a sus dimensiones.
- No: que todos los pares son una confirmación independiente. Cuando la solución de ComCat viene de la red `UNM` (UNAM), la aportó el propio SSN; el tablero las separa.
- No: que la fecha corregida modifica el DW del artículo. Se conservan ambas marcas y se comparan.
- Sí: los datos son descargables, se conservan CSV, se integran a dimensiones de los modelos originales y se visualizan con consultas al backend.
- Sí: la carga repetida se comprueba sin duplicar los reportes ni los folios de obras.
- No: que los reportes ciudadanos prueban físicamente una fuga o que el gasto reportado demuestra la ejecución material de una obra.
- No: que se incorporaron todas las obras del municipio; SHCP solo cubre los recursos federales reportados.
- No: que el consumo de 2019 representa el consumo actual o que su comparación con reportes de otros años demuestra causalidad.
- Sí: se importaron los expedientes administrativos con los campos publicados. No afirmar que incluyen actas firmadas, personal identificado o todos los documentos del expediente municipal: esos datos no aparecen en la fuente.
- Sí: el grafo incorpora todos los reportes mediante agregados verificables. Para contarlos se suma `agua:reportCount`, no se cuentan las observaciones agregadas.

## Antes de exponer

### Demografía de Estados Unidos y Canadá (ampliación del 25 de octubre)

1. Abrir http://localhost:8091/demografia/ o «Población de Estados Unidos y Canadá» en el menú original de sismos.
2. Elegir Estados Unidos, año 2025: se muestran 341,784,857 personas, distribuidas en 50 estados y Washington D. C.
3. Cambiar a Canadá: se muestran 41,608,982 personas en 13 provincias y territorios. Elegir otro año para mostrar
que la consulta cambia; hay información de 2020 a 2025.
4. Enseñar «Fuente y alcance»: Census Bureau para EE. UU. y Statistics Canada para Canadá, con enlace y DOI canadiense.
5. Mostrar en PostgreSQL `public.fact_poblacion_demografia` y la vista `public.v_poblacion_demografia`.
   Hay 396 observaciones: 384 regionales y 12 totales nacionales. No sumarlas todas como si fueran personas distintas.
6. Mostrar `evidencia/demografia.json`: 22 comprobaciones aprobadas de esta ampliación. El detalle técnico y los comandos
   están en `sismos-usgs/README.md`, sección «Registro de implementación del 25 de octubre de 2026».

Explicación breve:

«Mi parte fue integrar población oficial de Estados Unidos y Canadá. Descargamos los archivos, seleccionamos población
total al 1 de julio de 2020 a 2025, validamos que las regiones sumaran los totales nacionales y cargamos tablas nuevas
en PostgreSQL. La página consulta esa base con filtros. La ampliación posterior de Norteamérica ya relaciona los eventos
USGS asignados con la población de su región y año. No son cifras de personas afectadas.»

### Actualización: mapa de Norteamérica, 26 de octubre

La integración sísmica mencionada como pendiente en la fase anterior ya se implementó en esta copia local.

1. Entrar en «Sismos de Norteamérica» en el menú original, o abrir http://localhost:8091/norteamerica/.
2. Elegir Estados Unidos, 2020 y magnitud 3.5: hay 643 eventos asignados a polígonos oficiales. Cambiar a Canadá:
   hay 24. Los resultados pueden ser cero con magnitudes mayores; no significa que falle el mapa.
3. Abrir un punto: mostrar fecha, magnitud, región, población regional del año y enlace a la ficha oficial USGS.
4. Seleccionar «Área regional sin país asignado» para ver eventos que no se atribuyeron a US/CA, incluidos marítimos
   y de otras zonas del rectángulo. No se asignan al país más cercano.
5. Mostrar `public.fact_sismo_norteamerica`, `public.v_sismo_norteamerica`, el manifiesto de fuentes y
   `evidencia/norteamerica.json` con 63 comprobaciones aprobadas. Hay 14,041 eventos regionales conservados,
   2,455 asignados a EE. UU., 245 a Canadá y 11,341 sin asignación única.

«Ampliamos también los eventos con USGS ComCat, fuente oficial con DOI. Los descargamos y validamos, los asignamos
a límites gubernamentales por coordenadas y los relacionamos con población del mismo año y región. El mapa muestra
magnitud y la fuente de cada evento, no daños inventados. México conserva el catálogo original del SSN. La cobertura
implementada es 2020–2025 y magnitud mínima 3.5; no afirmamos que incluya todos los micro-sismos o toda jurisdicción marítima.»

Abrir Docker Desktop, ejecutar `iniciar-docker.ps1` (o `./iniciar.sh` en Linux) y comprobar las páginas 8091–8094. Si está disponible el entorno Python local, ejecutar también `python verificar.py`. Conservar la carpeta completa: incluye los CSV y las copias atribuidas de los componentes originales.
