/* =====================================================================
   i18n.js — diccionario español/inglés y motor de traducción.
   Compartido por las 4 páginas. Debe cargarse en el <head>, sin defer y
   antes que nav.js: fija el idioma del documento antes de que el
   navegador pinte, igual que el tema.

   La preferencia vive en localStorage con la misma convención que el
   tema y el modo claro/oscuro (dwagua-*).

   Al cambiar de idioma emite el evento 'idiomacambiado' sobre document,
   siguiendo el patrón de 'temacambiado' de nav.js. Cada página se
   suscribe y repinta lo que ella misma genera; nada se recarga.

   El inglés sigue el vocabulario del artículo: alcaldía = borough,
   colonia = neighbourhood, bimestre = bimester.
   ===================================================================== */
(function () {
  'use strict';

  var K_IDIOMA = 'dwagua-idioma';
  var IDIOMAS = [
    { id: 'es', etiqueta: 'ES', nombre: 'Español' },
    { id: 'en', etiqueta: 'EN', nombre: 'English' }
  ];
  var LOCALE = { es: 'es-MX', en: 'en-US' };

  /* ------------------------------------------------------------------
     Diccionario. Clave → texto. El español es la lengua de origen: si
     una clave falta en inglés se usa el español en su lugar, para que
     una traducción incompleta nunca deje un hueco en la interfaz.
     ------------------------------------------------------------------ */
  var DICC = {

  es: {
    /* ---------------- documento ---------------- */
    'titulo.index':    'Consumo de Agua CDMX — Panel',
    'titulo.mapa':     'Mapa de consumo — CDMX',
    'titulo.grafo':    'Grafo de conocimiento — Consumo de Agua CDMX',
    'titulo.vecindad': 'Vecindad territorial — Consumo de Agua CDMX',

    'meta.index': 'Almacén de datos y grafo de conocimiento del consumo de agua en la Ciudad de México, construido con datos abiertos de SACMEX. Consulta por alcaldía y colonia, mapa coroplético y SPARQL en el navegador.',
    'meta.mapa': 'Almacén de datos y grafo de conocimiento del consumo de agua en la Ciudad de México, construido con datos abiertos de SACMEX. Consulta por alcaldía y colonia, mapa coroplético y SPARQL en el navegador.',
    'meta.grafo': 'Explorador SPARQL sobre el grafo RDF materializado desde el almacén de datos de consumo de agua de la Ciudad de México.',
    'meta.vecindad': 'Recorrido de grafo sobre la relación agua:nearbyWithin1500m: elige una colonia y consulta sus vecinas con SPARQL.',

    /* ---------------- barra y pie ---------------- */
    'barra.marca': 'Consumo de Agua CDMX',
    'barra.lema':  'Almacén de datos y grafo de conocimiento territorial',
    'barra.tema':   'Tema de color',
    'barra.idioma': 'Idioma',
    'nav.index':    'Panel',
    'nav.mapa':     'Mapa',
    'nav.grafo':    'Grafo de conocimiento',
    'nav.vecindad': 'Vecindad territorial',
    'tema.escom':  'Azul',
    'tema.guinda': 'Guinda',
    'modo.claro':    'Modo claro',
    'modo.oscuro':   'Modo oscuro',
    'modo.auto':     'Automático',
    'modo.cambiar':  '{modo} — clic para cambiar',
    'idioma.cambiar': 'Ver el sitio en {nombre}',

    'pie.datos':     'Datos:',
    'pie.portal':    'Portal de Datos Abiertos de la Ciudad de México (2019, bimestres 1–3)',
    'pie.clima':     'Clima:',
    'pie.mapabase':  'Mapa base:',
    'pie.artefacto': 'Artefacto de',
    'pie.repo':      'Repositorio',

    /* ---------------- vocabulario compartido ---------------- */
    'com.todos':      'Todos',
    'com.todas':      'Todas',
    'com.anio':       'Año',
    'com.bimestre':   'Bimestre',
    'com.alcaldia':   'Alcaldía',
    'com.colonia':    'Colonia',
    'com.colonias':   'Colonias',
    'com.registros':  'Registros',
    'com.indice':     'Índice de desarrollo',
    'com.consultar':  '🔍 Consultar',
    'com.limpiar':    '↺ Limpiar',
    'com.bimestreN':  'Bimestre {n}',
    'com.bimN':       'Bim {n}',
    'com.sinResultados': 'Sin resultados',

    /* Niveles del índice de desarrollo. Vienen así del portal; POPULAR
       es una categoría publicada, no una traducción nuestra. */
    'ind.ALTO':    'ALTO',
    'ind.MEDIO':   'MEDIO',
    'ind.BAJO':    'BAJO',
    'ind.POPULAR': 'POPULAR',

    /* ---------------- panel (index.html) ---------------- */
    'idx.h1':        '💧 Consumo de Agua en CDMX',
    'idx.porPagina': 'Resultados por página',

    'idx.kpi.registros':    'Registros',
    'idx.kpi.registrosSub': 'Coincidencias con los filtros',
    'idx.kpi.total':        'Consumo total (m³)',
    'idx.kpi.totalSub':     'Suma del consumo total',
    'idx.kpi.promedio':     'Consumo promedio',
    'idx.kpi.promedioSub':  'Promedio por registro',
    'idx.kpi.colonias':     'Colonias únicas',
    'idx.kpi.coloniasSub':  'Distintas en el resultado',

    'idx.panel.top':      '📊 Top 10 colonias con mayor consumo',
    'idx.panel.corr':     '🌡️ Correlación consumo vs. temperatura promedio (por bimestre)',
    'idx.panel.alcaldia': '📈 Consumo total por alcaldía',
    'idx.panel.tabla':    '📋 Detalle de registros',

    'idx.th.anio':       'Año',
    'idx.th.bim':        'Bim.',
    'idx.th.fecha':      'Fecha',
    'idx.th.alcaldia':   'Alcaldía',
    'idx.th.colonia':    'Colonia',
    'idx.th.indice':     'Índice',
    'idx.th.total':      'Consumo total (m³)',
    'idx.th.prom':       'Consumo prom.',
    'idx.th.domTotal':   'Doméstico total',
    'idx.th.domProm':    'Doméstico prom.',
    'idx.th.mixtoTotal': 'Mixto total',
    'idx.th.noDomTotal': 'No dom. total',

    'idx.pag.anterior':  '◀ Anterior',
    'idx.pag.siguiente': 'Siguiente ▶',
    'idx.pag.mostrando': 'Mostrando {desde}–{hasta} de {total} registros',

    'idx.est.cargando':   'Cargando datos…',
    'idx.est.dataset':    'Cargando conjunto de datos estático…',
    'idx.est.error':      'Error: {msg}',
    'idx.est.noSePudo':   'No se pudo cargar {url} ({msg}).',

    'idx.g.consumoTotal': 'Consumo total',
    'idx.g.ejeM3':        'm³',
    'idx.g.ejeTemp':      'Temperatura promedio (°C)',
    'idx.g.ejeConsumo':   'Consumo total (m³)',
    'idx.g.barraTemp':    'Temp °C',
    'idx.g.bimAnio':      'Bim {b} / {a}',
    'idx.g.hoverTemp':    '🌡️ Temp prom',
    'idx.g.hoverAgua':    '💧 Consumo',
    'idx.g.hoverLluvia':  '🌧️ Lluvia',
    'idx.g.hoverCalor':   '🔥 Días de ola de calor',
    'idx.g.hoverFrio':    '❄️ Días fríos',

    /* ---------------- mapa (mapa.html) ---------------- */
    'map.h1':          '🗺️ Mapa de consumo — CDMX',
    'map.selAlcaldia': 'Alcaldía seleccionada:',
    'map.limpiarSel':  '✕ Limpiar selección',

    'map.detalle':     '💧 Datos de agua',
    'map.d.total':     'Consumo total',
    'map.d.prom':      'Consumo prom.',
    'map.d.dom':       '🏠 Doméstico',
    'map.d.noDom':     '🏢 No doméstico',
    'map.d.mixto':     '🏬 Mixto',
    'map.d.promDom':   'Prom. dom.',
    'map.d.colonias':  'Colonias',
    'map.d.registros': 'Registros',

    'map.leyenda':     'Intensidad de consumo',
    'map.ly.muyBajo':  'Muy bajo',
    'map.ly.bajo':     'Bajo',
    'map.ly.medio':    'Medio',
    'map.ly.alto':     'Alto',
    'map.ly.muyAlto':  'Muy alto',
    'map.top':         '📌 Top alcaldías',

    'map.popup.sinDatos':  'Sin datos de agua para los filtros',
    'map.popup.desglose':  'DESGLOSE POR TIPO',
    'map.popup.periodo':   'Período: {rango}',

    'map.err.geojson': 'No se cargó el GeoJSON de alcaldías (alcaldias.geojson).',
    'map.err.carga':   'No se pudo cargar {url} ({msg}).',

    /* ---------------- grafo (grafo.html) ---------------- */
    'gr.kpi.triples':     'Triples cargados',
    'gr.kpi.esperando':   'esperando…',
    'gr.kpi.enSegundos':  'en {seg} s, en tu navegador',
    'gr.kpi.obs':         'Observaciones',
    'gr.kpi.feat':        'Unidades territoriales',
    'gr.kpi.featNota':    'geo:Feature con geometría',
    'gr.kpi.ady':         'Relaciones de vecindad',

    'gr.intro': 'Este grafo se materializa desde el almacén relacional con un mapeo <b>R2RML</b> declarativo, alineado a <b>RDF Data Cube</b> (el cubo de observaciones), <b>GeoSPARQL</b> (territorio), una relación propia de proximidad entre centroides, <b>SKOS</b> (índice de desarrollo) y <b>OWL-Time</b> (periodos). Las consultas se ejecutan íntegramente en tu navegador: no hay servidor detrás.',

    'gr.ejemplos':   'Consultas de ejemplo',
    'gr.motor':      'motor en el navegador',
    'gr.etiqueta':   'Consulta — puedes editarla libremente',
    'gr.ejecutar':   'Ejecutar',
    'gr.copiar':     'Copiar',
    'gr.copiado':    'Copiado',
    'gr.noCopio':    'No se pudo',
    'gr.resultados': 'Resultados',
    'gr.filas':      'Filas',
    'gr.tiempo':     'Tiempo',
    'gr.elige':      'Elige una consulta o escribe la tuya.',

    'gr.est.cargando':   'cargando el grafo…',
    'gr.est.analizando': 'analizando {mb} MB de Turtle…',
    'gr.est.listo':      'grafo listo',
    'gr.est.ejecutando': 'ejecutando…',
    'gr.est.ok':         'listo',
    'gr.est.error':      'error',
    'gr.est.errorCarga': 'Error al cargar el grafo',
    'gr.est.sinLibs':    'No se pudieron cargar las bibliotecas RDF (revisa tu conexión).',

    'gr.av.sinLibs':   'Este explorador necesita las copias locales de N3.js y Comunica incluidas en el repositorio.',
    'gr.av.noCarga':   'No se pudo cargar el grafo.',
    'gr.av.file':      '<b>Est&aacute;s abriendo la p&aacute;gina como archivo local</b> (<code>file://</code>). Los navegadores bloquean <code>fetch</code> en ese modo por seguridad, aunque el archivo exista. Sirve la carpeta por HTTP:<br><code>python -m http.server 8000</code><br>y abre <code>http://localhost:8000/{pagina}</code>',
    'gr.av.publicado': 'Revisa que <code>kg_demo.ttl</code> est&eacute; publicado en el repositorio. Lo genera <code>publicar_demo_grafo.ps1</code>.',
    'gr.av.consulta':  'La consulta no se pudo ejecutar.',
    'gr.av.sinFilas':  'La consulta es válida pero no devolvió filas.',
    'gr.av.http':      'HTTP {codigo} al pedir kg_demo.ttl',
    'gr.primeras':     'Mostrando las primeras 500 de {total} filas.',

    'gr.ej.vecindad.t': 'Vecindad territorial',
    'gr.ej.vecindad.d': 'Recorre agua:nearbyWithin1500m para hallar las colonias dentro de 1.5 km de una dada y suma su consumo. Es proximidad entre centroides, no una relación topológica.',
    'gr.ej.clima.t':    'Agua y clima, unidos por el tiempo',
    'gr.ej.clima.d':    'Dos tablas de hechos distintas comparten la dimensión temporal. En el grafo, unirlas es seguir agua:period desde ambas.',
    'gr.ej.noDom.t':    'Alcaldías por proporción no doméstica',
    'gr.ej.noDom.d':    'El artículo argumenta que el consumo total no es un indicador per cápita. Esta consulta lo muestra: separa la demanda comercial de la residencial.',
    'gr.ej.indice.t':   'Consumo por nivel de desarrollo',
    'gr.ej.indice.d':   'Navega el esquema SKOS del índice de desarrollo, cuya escala tiene cuatro niveles: alto, medio, bajo y popular.',
    'gr.ej.grado.t':    'Grado en el grafo territorial',
    'gr.ej.grado.d':    '¿Qué colonias tienen más vecinas? Una pregunta de topología de red que el modelo relacional no expresa de forma natural.',
    'gr.ej.clases.t':   'Composición del grafo',
    'gr.ej.clases.d':   'Cuántas instancias hay de cada clase. Útil para ver de qué está hecho el grafo.',

    /* ---------------- vecindad (vecindad.html) ---------------- */
    'vec.kpi.col':      'Unidades territoriales',
    'vec.kpi.colNota':  'colonias con centroide',
    'vec.kpi.ady':      'Relaciones de vecindad',
    'vec.kpi.adyNota':  'agua:nearbyWithin1500m, ≤ 1.5 km',
    'vec.kpi.sel':      'Seleccionada',
    'vec.kpi.ninguna':  'ninguna',
    'vec.kpi.elige':    'elige una en el mapa',
    'vec.kpi.vec':      'Vecinas encontradas',

    'vec.intro': 'Cada punto es una colonia, representada por el centroide de sus lecturas. Al elegir una, se lanza una consulta <b>SPARQL</b> que recorre <code>agua:nearbyWithin1500m</code> sobre el grafo RDF y suma el consumo de cada vecina. Es proximidad entre centroides con umbral de 1.5 km, no topología de fronteras. La consulta que se ejecuta aparece abajo, tal cual. Todo ocurre en tu navegador.',

    'vec.mapa':        'Mapa territorial',
    'vec.buscar':      'Buscar colonia',
    'vec.placeholder': 'Escribe al menos tres letras…',
    'vec.placeholderAlc': 'Buscar en {alcaldia}…',
    'vec.ly.sel':      'seleccionada',
    'vec.ly.vecina':   'vecina directa',
    'vec.ly.resto':    'resto',

    'vec.consulta':      'Consulta ejecutada',
    'vec.eligeColonia':  'Elige una colonia.',
    'vec.vecinas':       'Vecinas',
    'vec.sinSeleccion':  'Sin selección.',
    'vec.th.vecina':     'Colonia vecina',
    'vec.th.alcaldia':   'Alcaldía',
    'vec.th.consumo':    'Consumo total (m³)',
    'vec.sinVecinas':    'Esta colonia no tiene vecinas dentro de 1.5 km en el grafo.',
    'vec.errConsulta':   'Error en la consulta: {msg}',
    'vec.deSparql':      '{t} de SPARQL',
    'vec.sinCoincidencias': 'Sin coincidencias',

    'vec.filtro.vacio':   'No hay colonias para <b>{alcaldia}</b>. Mostrando toda la ciudad.',
    'vec.filtro.cuenta':  '<b>{n}</b> colonias de <b>{alcaldia}</b>',
    'vec.filtro.verTodo': 'Ver toda la ciudad',

    'vec.est.cargando':   'cargando el grafo…',
    'vec.est.analizando': 'analizando {mb} MB…',
    'vec.est.ubicando':   'ubicando colonias…',
    'vec.est.listas':     '{n} colonias listas',
    'vec.est.error':      'error',
    'vec.est.sinLibs':    'sin bibliotecas RDF',
    'vec.av.sinLibs':     'Este explorador necesita las copias locales de N3.js y Comunica incluidas en el repositorio.',

    /* ---------------- consumos atípicos (atipicos.js) ---------------- */
    'at.titulo':    'Zonas con consumo atípico',
    'at.ocultar':   'Ocultar',
    'at.mostrar':   'Mostrar',
    'at.nota':      'Score <b>A<sub>g</sub></b> = |x &minus; &mu;| / (&sigma; + &epsilon;), calculado para cada colonia frente a la media de su alcaldía. Es un criterio de <b>relevancia</b>, no un diagnóstico: ordena qué zonas revisar primero. El umbral convencional es A<sub>g</sub> &gt; 3.',
    'at.alcaldia':  'Alcaldía',
    'at.mostrarSel':'Mostrar',
    'at.ambos':     'Altos y bajos',
    'at.soloAlto':  'Solo consumo alto',
    'at.soloBajo':  'Solo consumo bajo',
    'at.calculando':'Calculando…',
    'at.estado':    '<b>{sobre}</b> zonas superan el umbral A<sub>g</sub> &gt; 3 de {total} evaluadas. Se muestran las {mostradas} más atípicas.',
    'at.th.colonia':  'Colonia',
    'at.th.alcaldia': 'Alcaldía',
    'at.th.consumo':  'Consumo (m³)',
    'at.th.sentido':  'Sentido',
    'at.th.lectura':  'Lectura',
    'at.alto':      '&#9650; alto',
    'at.bajo':      '&#9660; bajo',
    'at.veces':     'consume <b>{veces}&times;</b> la media de su alcaldía',
    'at.sinDatos':  'Sin datos para esta combinación.',
    'at.errDatos':  'No se pudieron cargar los datos: {msg}',

    /* ---------------- paginación (paginacion.js) ---------------- */
    'pg.primera': 'Primera página',
    'pg.ultima':  'Última página',
    'pg.irA':     'Ir a',
    'pg.de':      'de',

    /* ---------------- puente al mapa (enlace-vecindad.js) ---------------- */
    'ev.alcaldia': 'Ver colonias y su vecindad &rarr;',
    'ev.colonia':  'Ver sus colonias vecinas &rarr;',

    /* ---------------- mapa base (mapa-teselas.js) ---------------- */
    'teselas.pregunta':  '¿No carga el mapa?',
    'teselas.probar':    'Probar otro proveedor',
    'teselas.elegir':    'Elegir el proveedor del mapa base',
    'teselas.titulo':    'Mapa base',
    'teselas.explica':   'Cada proveedor se comprueba antes de usarlo; si deja de responder, el mapa pasa solo al siguiente. La copia local se sirve desde este mismo sitio y no depende de ningún servidor externo.',
    'teselas.local':     'Copia local',
    'teselas.aviso':     '{antes} no respondía; ahora el mapa usa {ahora}.',
    'teselas.usando':    'Ahora el mapa usa {nombre}.',
    'teselas.estado.uso':         'en uso',
    'teselas.estado.ok':          'disponible',
    'teselas.estado.falla':       'no responde',
    'teselas.estado.comprobando': 'comprobando…',
    'teselas.nota.osm':      'el del artículo',
    'teselas.nota.gris':     'gris claro u oscuro',
    'teselas.nota.calles':   'callejero',
    'teselas.nota.hot':      'estilo humanitario',
    'teselas.nota.topo':     'topográfico',
    'teselas.nota.satelite': 'imagen de satélite',
    'teselas.nota.carto':    'sólo si no muestra marca de agua',
    'teselas.nota.local':    'OpenStreetMap, servido desde este sitio'
  },

  en: {
    /* ---------------- document ---------------- */
    'titulo.index':    'Mexico City Water Consumption — Dashboard',
    'titulo.mapa':     'Consumption map — Mexico City',
    'titulo.grafo':    'Knowledge graph — Mexico City Water Consumption',
    'titulo.vecindad': 'Territorial adjacency — Mexico City Water Consumption',

    'meta.index': 'Data warehouse and knowledge graph of water consumption in Mexico City, built from SACMEX open data. Query by borough and neighbourhood, choropleth map and SPARQL in the browser.',
    'meta.mapa': 'Data warehouse and knowledge graph of water consumption in Mexico City, built from SACMEX open data. Query by borough and neighbourhood, choropleth map and SPARQL in the browser.',
    'meta.grafo': 'SPARQL explorer over the RDF graph materialised from the Mexico City water-consumption data warehouse.',
    'meta.vecindad': 'Graph traversal over the agua:nearbyWithin1500m relation: pick a neighbourhood and query its neighbours with SPARQL.',

    /* ---------------- bar and footer ---------------- */
    'barra.marca': 'Mexico City Water Consumption',
    'barra.lema':  'Data warehouse and territorial knowledge graph',
    'barra.tema':   'Colour theme',
    'barra.idioma': 'Language',
    'nav.index':    'Dashboard',
    'nav.mapa':     'Map',
    'nav.grafo':    'Knowledge graph',
    'nav.vecindad': 'Territorial adjacency',
    'tema.escom':  'Blue',
    'tema.guinda': 'Guinda',
    'modo.claro':    'Light mode',
    'modo.oscuro':   'Dark mode',
    'modo.auto':     'Automatic',
    'modo.cambiar':  '{modo} — click to change',
    'idioma.cambiar': 'View the site in {nombre}',

    'pie.datos':     'Data:',
    'pie.portal':    'Mexico City Open Data Portal (2019, bimesters 1–3)',
    'pie.clima':     'Climate:',
    'pie.mapabase':  'Base map:',
    'pie.artefacto': 'Artefact of',
    'pie.repo':      'Repository',

    /* ---------------- shared vocabulary ---------------- */
    'com.todos':      'All',
    'com.todas':      'All',
    'com.anio':       'Year',
    'com.bimestre':   'Bimester',
    'com.alcaldia':   'Borough',
    'com.colonia':    'Neighbourhood',
    'com.colonias':   'Neighbourhoods',
    'com.registros':  'Records',
    'com.indice':     'Development index',
    'com.consultar':  '🔍 Query',
    'com.limpiar':    '↺ Clear',
    'com.bimestreN':  'Bimester {n}',
    'com.bimN':       'Bim {n}',
    'com.sinResultados': 'No results',

    /* Development-index levels as published by the portal. POPULAR names
       a category of the source data, so it is left as it is. */
    'ind.ALTO':    'HIGH',
    'ind.MEDIO':   'MEDIUM',
    'ind.BAJO':    'LOW',
    'ind.POPULAR': 'POPULAR',

    /* ---------------- dashboard (index.html) ---------------- */
    'idx.h1':        '💧 Water consumption in Mexico City',
    'idx.porPagina': 'Results per page',

    'idx.kpi.registros':    'Records',
    'idx.kpi.registrosSub': 'Matching the filters',
    'idx.kpi.total':        'Total consumption (m³)',
    'idx.kpi.totalSub':     'Sum of total consumption',
    'idx.kpi.promedio':     'Average consumption',
    'idx.kpi.promedioSub':  'Average per record',
    'idx.kpi.colonias':     'Distinct neighbourhoods',
    'idx.kpi.coloniasSub':  'Distinct in the result',

    'idx.panel.top':      '📊 Top 10 neighbourhoods by consumption',
    'idx.panel.corr':     '🌡️ Consumption vs. mean temperature (by bimester)',
    'idx.panel.alcaldia': '📈 Total consumption by borough',
    'idx.panel.tabla':    '📋 Record detail',

    'idx.th.anio':       'Year',
    'idx.th.bim':        'Bim.',
    'idx.th.fecha':      'Date',
    'idx.th.alcaldia':   'Borough',
    'idx.th.colonia':    'Neighbourhood',
    'idx.th.indice':     'Index',
    'idx.th.total':      'Total consumption (m³)',
    'idx.th.prom':       'Mean consumption',
    'idx.th.domTotal':   'Domestic total',
    'idx.th.domProm':    'Domestic mean',
    'idx.th.mixtoTotal': 'Mixed total',
    'idx.th.noDomTotal': 'Non-dom. total',

    'idx.pag.anterior':  '◀ Previous',
    'idx.pag.siguiente': 'Next ▶',
    'idx.pag.mostrando': 'Showing {desde}–{hasta} of {total} records',

    'idx.est.cargando':   'Loading data…',
    'idx.est.dataset':    'Loading static dataset…',
    'idx.est.error':      'Error: {msg}',
    'idx.est.noSePudo':   'Could not load {url} ({msg}).',

    'idx.g.consumoTotal': 'Total consumption',
    'idx.g.ejeM3':        'm³',
    'idx.g.ejeTemp':      'Mean temperature (°C)',
    'idx.g.ejeConsumo':   'Total consumption (m³)',
    'idx.g.barraTemp':    'Temp °C',
    'idx.g.bimAnio':      'Bim {b} / {a}',
    'idx.g.hoverTemp':    '🌡️ Mean temp',
    'idx.g.hoverAgua':    '💧 Consumption',
    'idx.g.hoverLluvia':  '🌧️ Rainfall',
    'idx.g.hoverCalor':   '🔥 Heatwave days',
    'idx.g.hoverFrio':    '❄️ Cold days',

    /* ---------------- map (mapa.html) ---------------- */
    'map.h1':          '🗺️ Consumption map — Mexico City',
    'map.selAlcaldia': 'Selected borough:',
    'map.limpiarSel':  '✕ Clear selection',

    'map.detalle':     '💧 Water data',
    'map.d.total':     'Total consumption',
    'map.d.prom':      'Mean consumption',
    'map.d.dom':       '🏠 Domestic',
    'map.d.noDom':     '🏢 Non-domestic',
    'map.d.mixto':     '🏬 Mixed',
    'map.d.promDom':   'Domestic mean',
    'map.d.colonias':  'Neighbourhoods',
    'map.d.registros': 'Records',

    'map.leyenda':     'Consumption intensity',
    'map.ly.muyBajo':  'Very low',
    'map.ly.bajo':     'Low',
    'map.ly.medio':    'Medium',
    'map.ly.alto':     'High',
    'map.ly.muyAlto':  'Very high',
    'map.top':         '📌 Top boroughs',

    'map.popup.sinDatos':  'No water data for these filters',
    'map.popup.desglose':  'BREAKDOWN BY TYPE',
    'map.popup.periodo':   'Period: {rango}',

    'map.err.geojson': 'The borough GeoJSON (alcaldias.geojson) did not load.',
    'map.err.carga':   'Could not load {url} ({msg}).',

    /* ---------------- graph (grafo.html) ---------------- */
    'gr.kpi.triples':     'Triples loaded',
    'gr.kpi.esperando':   'waiting…',
    'gr.kpi.enSegundos':  'in {seg} s, in your browser',
    'gr.kpi.obs':         'Observations',
    'gr.kpi.feat':        'Territorial units',
    'gr.kpi.featNota':    'geo:Feature with geometry',
    'gr.kpi.ady':         'Adjacency relations',

    'gr.intro': 'This graph is materialised from the relational warehouse through a declarative <b>R2RML</b> mapping, aligned to <b>RDF Data Cube</b> (the observation cube), <b>GeoSPARQL</b> (territory), a custom centroid-proximity relation, <b>SKOS</b> (development index) and <b>OWL-Time</b> (periods). Queries run entirely in your browser: there is no server behind this page.',

    'gr.ejemplos':   'Example queries',
    'gr.motor':      'engine in the browser',
    'gr.etiqueta':   'Query — edit it freely',
    'gr.ejecutar':   'Run',
    'gr.copiar':     'Copy',
    'gr.copiado':    'Copied',
    'gr.noCopio':    'Copy failed',
    'gr.resultados': 'Results',
    'gr.filas':      'Rows',
    'gr.tiempo':     'Time',
    'gr.elige':      'Pick a query or write your own.',

    'gr.est.cargando':   'loading the graph…',
    'gr.est.analizando': 'parsing {mb} MB of Turtle…',
    'gr.est.listo':      'graph ready',
    'gr.est.ejecutando': 'running…',
    'gr.est.ok':         'done',
    'gr.est.error':      'error',
    'gr.est.errorCarga': 'The graph could not be loaded',
    'gr.est.sinLibs':    'The RDF libraries could not be loaded (check your connection).',

    'gr.av.sinLibs':   'This explorer needs the local copies of N3.js and Comunica included in the repository.',
    'gr.av.noCarga':   'The graph could not be loaded.',
    'gr.av.file':      '<b>You are opening the page as a local file</b> (<code>file://</code>). Browsers block <code>fetch</code> in that mode for security, even when the file exists. Serve the folder over HTTP:<br><code>python -m http.server 8000</code><br>and open <code>http://localhost:8000/{pagina}</code>',
    'gr.av.publicado': 'Check that <code>kg_demo.ttl</code> is published in the repository. <code>publicar_demo_grafo.ps1</code> generates it.',
    'gr.av.consulta':  'The query could not be executed.',
    'gr.av.sinFilas':  'The query is valid but returned no rows.',
    'gr.av.http':      'HTTP {codigo} while requesting kg_demo.ttl',
    'gr.primeras':     'Showing the first 500 of {total} rows.',

    'gr.ej.vecindad.t': 'Territorial adjacency',
    'gr.ej.vecindad.d': 'Traverses agua:nearbyWithin1500m to find neighbourhoods within 1.5 km of a given one and sums their consumption. This is centroid proximity, not a topological relation.',
    'gr.ej.clima.t':    'Water and climate, joined through time',
    'gr.ej.clima.d':    'Two different fact tables share the time dimension. In the graph, joining them is a matter of following agua:period from both.',
    'gr.ej.noDom.t':    'Boroughs by non-domestic share',
    'gr.ej.noDom.d':    'The paper argues that total consumption is not a per-capita indicator. This query shows why: it separates commercial from residential demand.',
    'gr.ej.indice.t':   'Consumption by development level',
    'gr.ej.indice.d':   'Navigates the SKOS scheme of the development index, whose scale has four levels: high, medium, low and popular.',
    'gr.ej.grado.t':    'Degree in the territorial graph',
    'gr.ej.grado.d':    'Which neighbourhoods have the most neighbours? A network-topology question the relational model does not express naturally.',
    'gr.ej.clases.t':   'Composition of the graph',
    'gr.ej.clases.d':   'How many instances there are of each class. Useful to see what the graph is made of.',

    /* ---------------- adjacency (vecindad.html) ---------------- */
    'vec.kpi.col':      'Territorial units',
    'vec.kpi.colNota':  'neighbourhoods with a centroid',
    'vec.kpi.ady':      'Adjacency relations',
    'vec.kpi.adyNota':  'agua:nearbyWithin1500m, ≤ 1.5 km',
    'vec.kpi.sel':      'Selected',
    'vec.kpi.ninguna':  'none',
    'vec.kpi.elige':    'pick one on the map',
    'vec.kpi.vec':      'Neighbours found',

    'vec.intro': 'Each dot is a neighbourhood, represented by the centroid of its readings. Choosing one issues a <b>SPARQL</b> query that traverses <code>agua:nearbyWithin1500m</code> over the RDF graph and sums the consumption of every neighbour. It is centroid proximity with a 1.5 km threshold, not a topological relation. The query being executed appears below, verbatim. Everything happens in your browser.',

    'vec.mapa':        'Territorial map',
    'vec.buscar':      'Search neighbourhood',
    'vec.placeholder': 'Type at least three letters…',
    'vec.placeholderAlc': 'Search in {alcaldia}…',
    'vec.ly.sel':      'selected',
    'vec.ly.vecina':   'direct neighbour',
    'vec.ly.resto':    'the rest',

    'vec.consulta':      'Query executed',
    'vec.eligeColonia':  'Pick a neighbourhood.',
    'vec.vecinas':       'Neighbours',
    'vec.sinSeleccion':  'Nothing selected.',
    'vec.th.vecina':     'Neighbouring unit',
    'vec.th.alcaldia':   'Borough',
    'vec.th.consumo':    'Total consumption (m³)',
    'vec.sinVecinas':    'This neighbourhood has no neighbours within 1.5 km in the graph.',
    'vec.errConsulta':   'Query error: {msg}',
    'vec.deSparql':      '{t} of SPARQL',
    'vec.sinCoincidencias': 'No matches',

    'vec.filtro.vacio':   'There are no neighbourhoods for <b>{alcaldia}</b>. Showing the whole city.',
    'vec.filtro.cuenta':  '<b>{n}</b> neighbourhoods in <b>{alcaldia}</b>',
    'vec.filtro.verTodo': 'See the whole city',

    'vec.est.cargando':   'loading the graph…',
    'vec.est.analizando': 'parsing {mb} MB…',
    'vec.est.ubicando':   'locating neighbourhoods…',
    'vec.est.listas':     '{n} neighbourhoods ready',
    'vec.est.error':      'error',
    'vec.est.sinLibs':    'no RDF libraries',
    'vec.av.sinLibs':     'This explorer needs the local copies of N3.js and Comunica included in the repository.',

    /* ---------------- outlying consumption (atipicos.js) ---------------- */
    'at.titulo':    'Zones with outlying consumption',
    'at.ocultar':   'Hide',
    'at.mostrar':   'Show',
    'at.nota':      'Score <b>A<sub>g</sub></b> = |x &minus; &mu;| / (&sigma; + &epsilon;), computed for each neighbourhood against the mean of its borough. It is a criterion of <b>relevance</b>, not a diagnosis: it ranks which zones to inspect first. The conventional threshold is A<sub>g</sub> &gt; 3.',
    'at.alcaldia':  'Borough',
    'at.mostrarSel':'Show',
    'at.ambos':     'High and low',
    'at.soloAlto':  'High consumption only',
    'at.soloBajo':  'Low consumption only',
    'at.calculando':'Computing…',
    'at.estado':    '<b>{sobre}</b> zones exceed the A<sub>g</sub> &gt; 3 threshold out of {total} evaluated. The {mostradas} most atypical are shown.',
    'at.th.colonia':  'Neighbourhood',
    'at.th.alcaldia': 'Borough',
    'at.th.consumo':  'Consumption (m³)',
    'at.th.sentido':  'Direction',
    'at.th.lectura':  'Reading',
    'at.alto':      '&#9650; high',
    'at.bajo':      '&#9660; low',
    'at.veces':     'consumes <b>{veces}&times;</b> the mean of its borough',
    'at.sinDatos':  'No data for this combination.',
    'at.errDatos':  'The data could not be loaded: {msg}',

    /* ---------------- pagination (paginacion.js) ---------------- */
    'pg.primera': 'First page',
    'pg.ultima':  'Last page',
    'pg.irA':     'Go to',
    'pg.de':      'of',

    /* ---------------- bridge from the map (enlace-vecindad.js) ------- */
    'ev.alcaldia': 'See its neighbourhoods and adjacency &rarr;',
    'ev.colonia':  'See its neighbouring units &rarr;',

    /* ---------------- basemap (mapa-teselas.js) ---------------- */
    'teselas.pregunta':  'Map not loading?',
    'teselas.probar':    'Try another provider',
    'teselas.elegir':    'Choose the basemap provider',
    'teselas.titulo':    'Basemap',
    'teselas.explica':   'Each provider is checked before it is used; if it stops answering, the map moves to the next one on its own. The local copy is served from this same site and depends on no external server.',
    'teselas.local':     'Local copy',
    'teselas.aviso':     '{antes} was not answering; the map now uses {ahora}.',
    'teselas.usando':    'The map now uses {nombre}.',
    'teselas.estado.uso':         'in use',
    'teselas.estado.ok':          'available',
    'teselas.estado.falla':       'not answering',
    'teselas.estado.comprobando': 'checking…',
    'teselas.nota.osm':      'the one in the paper',
    'teselas.nota.gris':     'light or dark grey',
    'teselas.nota.calles':   'street map',
    'teselas.nota.hot':      'humanitarian style',
    'teselas.nota.topo':     'topographic',
    'teselas.nota.satelite': 'satellite imagery',
    'teselas.nota.carto':    'only if it shows no watermark',
    'teselas.nota.local':    'OpenStreetMap, served from this site'
  }

  };

  /* ------------------------------------------------------------------
     Estado. Se lee antes de que exista el <body>: el idioma queda
     fijado en <html lang> mientras el navegador aún analiza la página.
     ------------------------------------------------------------------ */
  var leer = function (k, d) {
    try { return localStorage.getItem(k) || d; } catch (e) { return d; }
  };
  var guardar = function (k, v) {
    try { localStorage.setItem(k, v); } catch (e) {}
  };
  var valido = function (id) {
    return IDIOMAS.some(function (i) { return i.id === id; });
  };

  /* Sin preferencia guardada se respeta la del navegador; el español es
     el punto de partida porque es la lengua de los datos. */
  function porDefecto() {
    var n = (navigator.language || 'es').toLowerCase();
    return n.indexOf('en') === 0 ? 'en' : 'es';
  }

  var idioma = leer(K_IDIOMA, '');
  if (!valido(idioma)) idioma = porDefecto();

  var pagina = (location.pathname.split('/').pop() || 'index.html')
                 .toLowerCase().replace(/\.html$/, '') || 'index';

  /* ------------------------------------------------------------------
     Traducción
     ------------------------------------------------------------------ */
  function crudo(clave) {
    var d = DICC[idioma];
    if (d && Object.prototype.hasOwnProperty.call(d, clave)) return d[clave];
    if (DICC.es && Object.prototype.hasOwnProperty.call(DICC.es, clave)) return DICC.es[clave];
    return null;
  }

  /* t('idx.pag.mostrando', {desde:1, hasta:50, total:'10,641'}) */
  function t(clave, vars) {
    var s = crudo(clave);
    if (s === null) return clave;           // la clave visible delata el hueco
    if (!vars) return s;
    return s.replace(/\{(\w+)\}/g, function (m, n) {
      return Object.prototype.hasOwnProperty.call(vars, n) ? String(vars[n]) : m;
    });
  }

  /* ------------------------------------------------------------------
     Aplicación al marcado estático
       data-i18n="clave"                    → textContent
       data-i18n-html="clave"               → innerHTML (textos con <b>)
       data-i18n-attr="title:clave|aria-label:otra"
     ------------------------------------------------------------------ */
  var SELECTOR = '[data-i18n],[data-i18n-html],[data-i18n-attr]';

  function traducirNodo(el) {
    var c = el.getAttribute('data-i18n');
    if (c) el.textContent = t(c);
    var h = el.getAttribute('data-i18n-html');
    if (h) el.innerHTML = t(h);
    var a = el.getAttribute('data-i18n-attr');
    if (a) {
      a.split('|').forEach(function (par) {
        var i = par.indexOf(':');
        if (i < 0) return;
        el.setAttribute(par.slice(0, i).trim(), t(par.slice(i + 1).trim()));
      });
    }
  }

  function aplicar(raiz) {
    var r = raiz || document;
    if (r.nodeType === 1 && r.matches && r.matches(SELECTOR)) traducirNodo(r);
    if (!r.querySelectorAll) return;
    var l = r.querySelectorAll(SELECTOR);
    for (var i = 0; i < l.length; i++) traducirNodo(l[i]);
  }

  /* Cabecera del documento: idioma, título y metadescripción. */
  function cabecera() {
    document.documentElement.lang = idioma;
    var tit = crudo('titulo.' + pagina);
    if (tit) document.title = tit;
    var desc = crudo('meta.' + pagina);
    if (desc) {
      var m = document.querySelector('meta[name="description"]');
      if (m) m.setAttribute('content', desc);
    }
  }
  cabecera();   // el <head> ya está analizado cuando corre este script

  /* ------------------------------------------------------------------
     Sin parpadeo: mientras el analizador construye el cuerpo, cada nodo
     con data-i18n se traduce en cuanto aparece, antes de que la página
     se pinte. Al terminar el análisis se hace una pasada completa y el
     observador se retira: a partir de ahí cada página traduce lo que
     ella misma genera.
     ------------------------------------------------------------------ */
  var observador = null;
  if (window.MutationObserver && document.readyState === 'loading') {
    observador = new MutationObserver(function (muts) {
      for (var i = 0; i < muts.length; i++) {
        var n = muts[i].addedNodes;
        for (var j = 0; j < n.length; j++) if (n[j].nodeType === 1) aplicar(n[j]);
      }
    });
    observador.observe(document.documentElement, { childList: true, subtree: true });
  }

  function listo() {
    if (observador) { observador.disconnect(); observador = null; }
    aplicar(document);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', listo);
  } else {
    listo();
  }

  /* ------------------------------------------------------------------
     Cambio de idioma. Mismo patrón que 'temacambiado' de nav.js: se
     guarda la preferencia, se repinta lo estático y se avisa para que
     cada página rehaga lo suyo sin recargar ni perder el estado.
     ------------------------------------------------------------------ */
  function set(nuevo) {
    if (!valido(nuevo) || nuevo === idioma) return;
    idioma = nuevo;
    guardar(K_IDIOMA, idioma);
    API.idioma = idioma;
    cabecera();
    aplicar(document);
    document.dispatchEvent(new CustomEvent('idiomacambiado', { detail: { idioma: idioma } }));
  }

  /* ------------------------------------------------------------------
     Números. es-MX y en-US coinciden en los separadores, así que el
     cambio de idioma no altera las cifras; se expone de todos modos
     para no dejar el locale escrito a mano por las páginas.
     ------------------------------------------------------------------ */
  function locale() { return LOCALE[idioma] || 'es-MX'; }
  function num(n, opciones) {
    if (n == null || n === '' || isNaN(Number(n))) return '—';
    return new Intl.NumberFormat(locale(), opciones).format(Number(n));
  }

  var API = {
    idioma: idioma,
    idiomas: IDIOMAS,
    t: t,
    set: set,
    aplicar: aplicar,
    locale: locale,
    num: num,
    /* Etiqueta del índice de desarrollo; el valor crudo sigue siendo la
       clase CSS del badge y el valor del <option>, que no se tocan. */
    indice: function (v) {
      if (!v) return '—';
      var e = crudo('ind.' + String(v).toUpperCase());
      return e === null ? v : e;
    }
  };
  window.I18N = API;
})();
