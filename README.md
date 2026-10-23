# Fuentes alternas: agua CDMX y obras públicas

Integración de datos oficiales en los modelos de los proyectos de los artículos.
Incluye ejecución local reproducible, fuentes oficiales y evidencia de verificación. Sismos se conserva como avance previo y queda fuera del alcance de estos dos proyectos.

| Sistema | Abrir | Datos comprobados el 23 de octubre de 2026 |
|---|---|---|
| Agua CDMX · reportes ciudadanos | http://127.0.0.1:8092 | 555,752 reportes integrados; 70,886 registros originales de consumo y 181 días de clima conservados |
| Agua · interfaz original conectada | http://127.0.0.1:8092/sistema/ | El JSON que consume el frontend se consulta en PostgreSQL, no en un archivo de ejemplo |
| Obras de Temascaltepec · SHCP | http://127.0.0.1:8093 | 59 obras, $58,834,555.00 aprobados y $58,803,710.52 pagados |
| Obras · expedientes administrativos | http://127.0.0.1:8093/expedientes/ | 59 expedientes reales con presupuesto, contratos publicados, financiamiento y faltantes explícitos |
| Agua · grafo RDF actualizado | http://127.0.0.1:8092/sistema/grafo.html | Reportes reales conectados a las mismas colonias del consumo, consultables mediante SPARQL |

## Arranque rápido en Windows

Requisitos: Docker Desktop iniciado y conexión a Internet para la primera construcción. Ejecutar desde esta carpeta:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar-docker.ps1
```

El script construye las imágenes, levanta dos bases aisladas, ejecuta los ETL y comprueba que ambas páginas responden. No cambia la configuración de ejecución de PowerShell del equipo. Los puertos son 5442/8092 para agua y 5443/8093 para obras. Las contraseñas de desarrollo están en los archivos Compose.

También se comprobó una alternativa con Python 3.14 local: `iniciar.ps1` instala las bibliotecas dentro de `.runtime/` y usa Docker únicamente para las bases. No se deben iniciar dos servidores distintos sobre el mismo puerto; el script local reutiliza las páginas que ya están respondiendo.

```powershell
# Volver a cargar desde los CSV conservados; no duplica los hechos integrados.
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar-docker.ps1 -Recargar

# Solo bases y ETL, sin iniciar servidores web.
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar.ps1 -SoloDatos

# Verificar fuente → base → API y guardar evidencia.
python .\verificar.py
```

Si las páginas ya responden, el script reutiliza los servidores. Tras editar código Python hay que reiniciar el proceso correspondiente. Los registros de los servidores iniciados por el script quedan en `evidencia/logs/`.

## Qué se integra

**Agua:** se carga el esquema original en `public`, con sus tablas de hechos de consumo y clima. Se añade `public.fact_reporte_agua`, enlazada por claves foráneas a las dimensiones originales de fecha y ubicación. Una tabla de equivalencias relaciona los nombres originales con las colonias normalizadas. `dw` conserva el área analítica que dejó el compañero; el gráfico mensual consulta el hecho integrado de `public`. La interfaz original está en `original/frontend` y consume el endpoint dinámico `/sistema/consumo.json`.

**Obras:** se cargan el esquema operacional, las diez dimensiones y los disparadores del proyecto original. Se añade `warehouse.fact_srft`, que reutiliza `warehouse.dim_obra` y `warehouse.dim_tiempo`. El ETL conserva los CSV crudos filtrados y sus relaciones en `staging.srft`. El backend Flask original registra el nuevo blueprint `srft`; su frontend se amplía con un tablero de datos oficiales y un enlace desde la interfaz original.

Se importan también las 59 obras a `public.obra`, sus presupuestos a `public.presupuesto_obra` y el financiamiento a `public.financia`. Se conservan los contratos y los números de expediente publicados. `public.expediente_srft` registra procedencia y campos no publicados; `/expedientes/` permite revisarlos sin crear cuentas ni personal de ejemplo. Las API públicas originales visualizan las obras reales. No se ejecuta el generador sintético original.

Cuando SHCP no publica un supervisor o proyectista, el importador conserva `NULL`. Una migración permite esos desconocidos en registros identificados como importados; los registros manuales conservan sus requisitos mediante restricciones condicionales. No se inventan actas, firmas ni RFC de contratistas. La auditoría distingue el evento técnico de importación actual de una creación histórica de obra.

El ETL de agua regenera `datos/grafo_integrado.ttl` desde PostgreSQL. Incluye consumo, clima, colonias y los reportes agregados por colonia, año, tipo, clasificación y recurso. Conserva todos los reportes, incluidos los no ubicados. El explorador original ofrece nuevas consultas SPARQL mediante un endpoint de lectura en el backend local. Así el navegador no tiene que procesar el grafo completo. El mapeo de reportes está en `original/frontend/mapping-reportes.r2rml.ttl`.

## Fuentes y trazabilidad

- [SACMEX: consumo de agua](https://datos.cdmx.gob.mx/dataset/consumo-agua), primer semestre de 2019.
- [SACMEX: reportes de agua](https://datos.cdmx.gob.mx/dataset/reportes-de-agua), recursos históricos 2018–2021 y 2022–2024.
- [SHCP: datos abiertos](https://www.transparenciapresupuestaria.gob.mx/Datos-Abiertos), [ZIP del informe definitivo 2025](https://www.transparenciapresupuestaria.gob.mx/work/models/PTP/DatosAbiertos/Entidades_Federativas/2025/ef2025.zip). Se filtran entidad **15**, municipio **86**, ciclo **2025**, periodo **5**. El periodo 5 significa informe definitivo, no quinto trimestre.

Los extractos de obras se guardan como CSV UTF-8, con nombres terminados en `_temascaltepec.csv`. `datos/procedencia.json` registra URL, filtro, fecha, tamaño y SHA-256 del ZIP y de cada extracto. El ZIP nacional se conserva localmente y se excluye de Git; los extractos y el manifiesto permiten repetir la carga sin descargarlo.

Los CSV de agua se conservan en `agua-reportes-sacmex/datos`. El ETL consulta metadatos CKAN y registra las URL en `etl.recurso`. La evidencia incluye hashes SHA-256 de todos los CSV empleados. El clima de 2019 procede del archivo distribuido con el proyecto original y se conserva como `clima_original_2019.csv`.

## Límites que se deben explicar en la exposición

- El consumo disponible es de 2019. Compararlo con reportes de otros años es exploratorio; no es una validación simultánea ni evidencia causal.
- En agua se conservan **4,804 reportes sin colonia asignable**, con ubicación nula. Las coordenadas fuera del rectángulo de validación se anulan, sin inventar puntos.
- La normalización produce 1,550 pares alcaldía–colonia en el área analítica: fusiona variantes de escritura. La dimensión original se conserva.
- La asignación por manzana cercana a menos de 1 km es aproximada, no una intersección con polígonos oficiales.
- SHCP incluye recursos federales, no toda la obra municipal. El estatus terminado y el avance físico son declaraciones de la fuente, no inspecciones de campo. No se suman metas expresadas en unidades diferentes.
- El mapa base requiere Internet. La tabla, los expedientes y el RDF vienen de la base local. El grafo usa agregados para funcionar en el navegador: contar observaciones RDF no equivale a contar reportes; se debe sumar `agua:reportCount`.

## Documentación y evidencia

- [Guion y consultas para la entrega](ENTREGA.md).
- [Versiones y atribución de los originales](PROCEDENCIA_ORIGINALES.md).
- [Resultados ejecutables de verificación](evidencia/verificacion.json).
- [Verificación de expedientes y RDF/SPARQL](evidencia/extensiones.json), reproducible con `python verificar_extensiones.py` y las dependencias de `requirements-local.txt`.
- [Detalle de agua](agua-reportes-sacmex/README.md) y [detalle de obras](obra-publica-srft/README.md).

Los comandos Docker están documentados por proyecto. Se comprobó primero la ejecución con PostgreSQL en Docker y Python local, y después el arranque completo de ambos sistemas dentro de Docker, con las mismas 22 verificaciones aprobadas.
