# Proyectos originales y cambios locales

Se descargaron los repositorios públicos el 23 de octubre de 2026. Las copias de trabajo completas están en `referencias/` (excluida de Git). Los componentes necesarios se incorporan en las carpetas `original/`, con sus licencias y archivos README. No se añaden repositorios Git anidados a la entrega.

| Original | Commit consultado | Componentes conservados |
|---|---|---|
| [gabrielhuav/data_warehouse_cdmx](https://github.com/gabrielhuav/data_warehouse_cdmx) | `9d69cf8c6ab854fa9c32e5f465b099bed93a5317` | DDL, ETL, consultas, licencia y datos de clima |
| [gabrielhuav/Data_Warehouse_static](https://github.com/gabrielhuav/Data_Warehouse_static) | `bc23780da3330347bedc2200c3f1434f5097a901` | Interfaz, módulos JS/CSS, mapas, grafo de referencia y exportador de datos |
| [gabrielhuav/PublicMunicipalWorks_DWH](https://github.com/gabrielhuav/PublicMunicipalWorks_DWH) | `7ecb6ea12f18fe9234b534a864419d3451353fe2` | Esquemas operacional y warehouse, disparadores, backend y frontend de referencia, licencia y cita |

Los autores originales mantienen la autoría de esos componentes. La documentación original que habla de datos sintéticos, usuarios de demostración o despliegues externos describe el proyecto de origen; no describe los datos importados para esta entrega.

## Extensiones locales

Agua: `app/integrar_original.py` inicializa una copia local del DW original si no existe y añade un nuevo hecho de reportes ciudadanos. Conserva los hechos previos; amplía las fechas y añade coordenadas a las colonias. El backend sirve la interfaz original y construye su JSON desde PostgreSQL. Se añade navegación al módulo nuevo.

Obras: `db/04_srft.sql` añade staging y el hecho oficial al warehouse. `app/etl.py` extrae y valida el informe de SHCP. `original/backend/routes/srft.py` se registra en el backend original. Se fija explícitamente el controlador psycopg2 que usa ese backend y se corrige la liberación del cursor ante errores de conexión. Las URL de los clientes originales apuntan al mismo backend local. Se añade navegación al tablero oficial.

Se conservaron únicamente los componentes necesarios para ejecutar y revisar los sistemas; no se copiaron los paquetes de publicación de los artículos ni los generadores de datos sintéticos.

## Ampliación posterior: expedientes y grafo

`obra-publica-srft/db/05_expedientes.sql` y `app/integrar_expedientes.py` importan los campos administrativos oficiales a las tablas operacionales originales. La API original de obras muestra el estatus y el avance del cierre SHCP y distingue los informes de fuente de los informes firmados por supervisores. Se añaden una página pública de expedientes y su API de lectura.

`agua-reportes-sacmex/original/scripts/exportar_grafo_base.py` adapta el exportador `scripts/exportar_grafo_demo.py` del mismo commit de `Data_Warehouse_static`: recibe una conexión existente. `app/grafo.py` añade la materialización de reportes oficiales y reconstruye el grafo desde el DW vivo. La página original `grafo.html` conserva el explorador y suma ejemplos y métricas de los reportes integrados. La ejecución SPARQL se traslada a RDFLib en el backend local para resolver el grafo completo sin saturar el navegador. El endpoint admite SELECT y ASK y rechaza fuentes remotas. No se mantiene una copia estática desactualizada como respuesta del grafo.
