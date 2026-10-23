/* =====================================================================
   mapa-teselas.js — que el mapa base nunca se quede en blanco.
   Compartido por mapa.html y vecindad.html.

   Los dos mapas pedían sus teselas a OpenStreetMap y a nadie más. Un
   artefacto hermano (Obras Públicas) se quedó sin mapa en plena
   presentación cuando su único proveedor, CARTO, empezó a contestar sin
   clave con un 200 OK y una imagen que dice «API KEY REQUIRED»: para
   Leaflet eso no es un error, así que nada cambió de proveedor. Aquí el
   riesgo era el mismo. Este módulo sustituye esa dependencia única por
   una cadena de proveedores gratuitos y sin clave:

     1. OpenStreetMap, el que usa el artículo.
     2. Esri Canvas (gris claro u oscuro), Esri World Street Map,
        OpenStreetMap HOT, OpenTopoMap y Esri World Imagery.
     3. CARTO, al final, y sólo si pasa la prueba de la marca de agua.
     4. La copia local: un extracto de OpenStreetMap servido desde este
        mismo sitio (assets/mapa-base/cdmx.json) y dibujado en el
        navegador. Si la página cargó, esto también carga.
     5. Y si ni ese archivo llegara, el contorno de la ciudad y de sus
        alcaldías, que va escrito aquí abajo (CONTORNO_MINIMO).

   Cada proveedor se prueba antes de usarlo: se piden dos teselas
   contiguas del centro de la ciudad, que tienen que llegar, ser imágenes
   y ser distintas entre sí, porque una marca de agua es la misma imagen
   en cualquier coordenada. Ya en uso se vigila: si las teselas fallan o
   se atascan, se pasa solo al siguiente y se avisa. Y si el mapa lleva
   más de PROVISIONAL ms sin nada que enseñar, se ve la copia local
   debajo mientras tanto, de modo que nunca espera en blanco.

   El control «¿No carga el mapa? Probar otro proveedor», abajo a la
   derecha, enseña la lista con el estado de cada uno. Lo que se elige
   ahí se recuerda como el tema, el modo y el idioma (dwagua-*);
   `?teselas=<id>` en la URL fija uno sólo para esa visita.

   Uso, en lugar de L.tileLayer(...):
       MapaTeselas.montar(mapa, { maxZoom: 19 });
   La copia local la genera scripts/generar_mapa_base.py.
   ===================================================================== */
(function () {
  'use strict';

  var K_PROVEEDOR = 'dwagua-teselas';
  /* Centro de mapa.html (CDMX_CENTER). Las teselas de prueba son las del
     centro, que luego se ven, así que la prueba no se desperdicia. */
  var CENTRO = { lat: 19.4326, lng: -99.1332 };
  var ZOOM_PRUEBA = 12;
  var ESPERA_PRUEBA = 4000;   // ms por tesela de prueba
  var ESCALON = 700;          // ms antes de probar el siguiente en paralelo
  var PLAZO_TOTAL = 6000;     // ms para decidir, aunque sea por la copia local
  var PROVISIONAL = 1500;     // ms en blanco antes de enseñar la copia local
  var ATASCO = 10000;         // ms cargando sin recibir ni una tesela
  var ESPERA_BASE = 800;      // ms que se espera al archivo antes del contorno mínimo
  var PLAZO_BASE = 15000;     // ms para bajar el archivo antes de darlo por perdido
  var REINTENTO_BASE = 10000; // ms entre intentos de bajarlo

  var BASE_URL = 'assets/mapa-base/cdmx.json';
  try {
    if (document.currentScript && document.currentScript.src) {
      BASE_URL = new URL('mapa-base/cdmx.json', document.currentScript.src).href;
    }
  } catch (e) { /* se queda la ruta relativa a la página */ }

  var OSM = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  var ESRI = 'Tiles &copy; <a href="https://www.esri.com/">Esri</a>';
  var ARCGIS = 'https://server.arcgisonline.com/ArcGIS/rest/services/';

  /* `invertir`: no tiene versión oscura y en modo oscuro se invierte con
     CSS (.teselas-invertidas, en estilo.css). */
  var PROVEEDORES = [
    { id: 'osm', nombre: 'OpenStreetMap', nota: 'teselas.nota.osm',
      claro: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      invertir: true, max: 19, atribucion: OSM },
    { id: 'esri-gris', nombre: 'Esri Canvas', nota: 'teselas.nota.gris',
      claro: ARCGIS + 'Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
      oscuro: ARCGIS + 'Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
      max: 16,
      atribucion: ESRI + ' &mdash; Esri, HERE, Garmin, ' + OSM + ', and the GIS User Community' },
    { id: 'esri-calles', nombre: 'Esri World Street Map', nota: 'teselas.nota.calles',
      claro: ARCGIS + 'World_Street_Map/MapServer/tile/{z}/{y}/{x}',
      invertir: true, max: 19,
      atribucion: ESRI + ' &mdash; Source: Esri, HERE, Garmin, USGS, ' + OSM },
    { id: 'osm-hot', nombre: 'OpenStreetMap HOT', nota: 'teselas.nota.hot',
      claro: 'https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png',
      sub: 'abc', invertir: true, max: 19,
      atribucion: OSM + ', tiles style by <a href="https://www.hotosm.org/">HOT</a>' +
        ' hosted by <a href="https://openstreetmap.fr/">OpenStreetMap France</a>' },
    { id: 'topo', nombre: 'OpenTopoMap', nota: 'teselas.nota.topo',
      claro: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
      sub: 'abc', invertir: true, max: 17,
      atribucion: 'Map data: ' + OSM + ', SRTM | Map style: &copy; ' +
        '<a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)' },
    { id: 'esri-satelite', nombre: 'Esri World Imagery', nota: 'teselas.nota.satelite',
      claro: ARCGIS + 'World_Imagery/MapServer/tile/{z}/{y}/{x}',
      max: 19,
      atribucion: ESRI + ' &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community' },
    { id: 'carto', nombre: 'CARTO', nota: 'teselas.nota.carto',
      claro: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
      oscuro: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      sub: 'abcd', max: 20,
      atribucion: OSM + ' &copy; <a href="https://carto.com/attributions">CARTO</a>' },
    { id: 'local', nombre: null, nota: 'teselas.nota.local', local: true,
      atribucion: OSM + ' (ODbL)' }
  ];
  var LOCAL = PROVEEDORES[PROVEEDORES.length - 1];

  /* Respaldo de la copia local, por si ni su archivo llegara: el contorno
     de la ciudad (simplificado a 120 m), los límites entre alcaldías
     (a 250 m) y sus nombres, en enteros de 1e-5 grados codificados en
     deltas. Lo reescribe scripts/generar_mapa_base.py a partir de
     alcaldias.geojson; no se edita a mano. */
  var CONTORNO_MINIMO = [[-9918231,1950748,526,-129,401,240,1586,-574,-580,1511,-1120,551,281,372,-399,290,-169,-76,104,271,1685,-514,236,119,-180,77,275,358,-266,148,743,1093,-982,441,333,579,-53,230,196,280,333,181,191,-144,410,412,204,619,519,457,167,573,414,511,677,227,328,425,425,-77,157,-140,-71,-613,394,-466,284,-1107,372,-384,-2247,-2880,320,-101,-63,-1055,1359,-1347,677,-3,34,-135,990,295,3354,-1385,-413,-970,2153,-4672,-874,-1809,-294,-2358,3857,-1743,2763,-1566,-262,-946,1577,-1485,447,-626,1642,-1380,-507,-650,-181,-985,-244,-91,-931,-5284,1054,-319,-260,-1772,2829,-898,-225,-763,-854,257,-286,-353,-874,-51,-584,-357,170,-161,-285,-471,198,-112,67,-322,-66,-1017,784,-1057,368,-241,378,-812,-1498,-420,1274,-1492,-1183,-565,895,-2149,-155,-1810,-666,-1842,-1328,-1140,-459,430,-4540,661,-1422,-961,-1659,-2752,-6563,1382,-995,2724,-9140,676,-5192,3564,-891,1490,-1515,4426,-438,2287,-911,777,91,770,-596,347,-542,-10,-410,537,-1152,318,248,1853,223,439,-153,366,-553,178,-352,448,-1371,178,-300,203,1134,1416,-96,136,305,86,-201,325,351,-56,-628,517,-34,467,2277,2391,557,1461,-21,789,209,58,310,467,516,-18,-257,228,309,529,222,16,230,456,533,111,428,627,217,-75,8,-738,221,-218,110,180,403,83,328,487,491,142,287,496,2111,1459,359,877,115,-433,94,313,773,509,1126,390,621,916,538,488,319,43,-455,432,65,263,-346,340,1150,674,-202,201,18,676,468,334,375,1177,268,209,169,-51,35,165,-1430,385,1186,3734,459,273,2236,-766]]; // fin CONTORNO_MINIMO
  var LIMITES_MINIMOS = [[-9915718,1950285,23,-13],[-9915657,1950166,1345,-3660],[-9914312,1946506,-1553,-114,-506,-749,-460,75],[-9914312,1946506,978,-21,1110,-507],[-9917111,1945763,-767,130],[-9917992,1945913,-736,135],[-9918848,1946078,24,157],[-9918800,1946381,-201,62],[-9919073,1946467,15,327],[-9919044,1947046,-1024,289,-614,-213],[-9910346,1932442,-947,1095,-905,2229,-1786,-74],[-9910278,1932406,71,-42],[-9910170,1932342,175,-150],[-9909930,1932110,22,-66],[-9909908,1932044,-185,-2042],[-9909908,1932044,3011,-3548],[-9910093,1930002,-1588,140,-1791,687,-790,-868,-479,168,-925,-445,-560,444,-3279,77,-1070,363],[-9910093,1930002,-43,-482,-2901,-1148],[-9920575,1930568,702,1013],[-9920575,1930568,-964,194,-454,464],[-9919499,1932184,6,19],[-9919489,1932346,-87,849],[-9919627,1933268,-25,102],[-9919660,1933371,-162,-20],[-9919990,1933323,930,449],[-9919032,1933867,1861,2090],[-9917171,1935957,2281,-210],[-9917171,1935957,-603,557,-597,-342,-738,177,-64,1919,337,1095,-225,569],[-9914805,1935743,821,-51],[-9913984,1935692,887,4072,-621,156,59,361],[-9925581,1940357,58,-206],[-9925540,1940036,3,-30],[-9925521,1939914,-20,-95],[-9925622,1939667,-147,-109],[-9925844,1939505,-122,-92],[-9925959,1939376,34,-116],[-9925922,1939257,485,165],[-9925482,1939474,180,-99],[-9925288,1939357,302,6],[-9924943,1939348,257,50],[-9924681,1939385,-118,-707],[-9924769,1938632,-2245,-1351,171,-410,335,304,-175,-820,570,-272,213,-1277,-2216,-1063,95,-220,-464,131,-267,-550],[-9928753,1933095,-54,251,-323,-1084],[-9929116,1932252,32,-11],[-9929067,1932232,-407,-541,-407,356],[-9929900,1932106,-147,124],[-9930053,1932225,-76,-1274,-201,163,-549,-604,-278,171,-487,-681,71,-1780,-791,-1711,-68,-3248],[-9905087,1945018,-1142,-539,-1830,535],[-9908115,1945001,-601,-424,-224,247],[-9908975,1944856,-88,81],[-9909115,1944986,-1022,8,-2087,984],[-9912224,1945978,-596,-4602,250,-943],[-9905813,1940072,-80,-563],[-9905898,1939454,-62,-384],[-9905971,1939001,-114,-742,-2317,998,-1163,-1297,-2683,284,-5,-674,-1250,170],[-9913659,1940281,1089,152],[-9913659,1940281,-1974,125,-1411,-427],[-9912570,1940433,2773,481,1973,-209,874,1320,1371,189],[-9896045,1932537,-83,4],[-9896131,1932542,-1725,-152,-2279,323,-4226,-1492,-301,267,-1325,-1044,-353,124,177,-1302,-734,-770],[-9906897,1928496,3165,-1325],[-9922047,1932108,778,584,430,1093],[-9922057,1932099,-40,-496],[-9922096,1931596,103,-370],[-9921993,1931226,-1211,-838],[-9923225,1930379,-94,-709,-938,-422,25,-761],[-9924266,1928434,-66,-200],[-9924345,1928226,-15,-1199],[-9924347,1926979,-27,-44],[-9924395,1926921,-54,-37],[-9924497,1926852,10,14],[-9924578,1926777,119,-1504,-832,-1726,-1777,-1127,-666,-948,-1541,-95,-2281,1363],[-9932225,1923265,-91,658,552,526,228,1187,1738,509,2466,2374,-285,391,643,1208,-232,139],[-9927141,1930308,5,5],[-9927098,1930352,181,198],[-9926933,1930557,-46,16],[-9926987,1930574,-45,58],[-9927084,1930676,-8,6],[-9927120,1930722,10,-20],[-9927134,1930826,0,2],[-9927115,1930905,31,-19],[-9927105,1930929,99,223],[-9927027,1931220,233,194],[-9926780,1931420,503,258],[-9926244,1931717,633,826],[-9925592,1932573,1169,283,692,-386,611,514,2235,779],[-9899368,1922731,-211,-227,-643,232],[-9899362,1922712,7,-25],[-9899348,1922639,1,-6],[-9899346,1922625,5,-34],[-9899334,1922545],[-9899326,1922494,900,-473],[-9898384,1921986,1531,-929],[-9913648,1908938,-2681,2811,1079,2463,289,1819,1720,-1170,217,393],[-9913024,1915254,3032,5485,536,415,1079,98],[-9913024,1915254,-265,519,294,1452,-244,628,531,874,-359,404,113,937],[-9908347,1921258,5328,1105],[-9903019,1922363,3009,269,-289,125],[-9903019,1922363,1748,2151],[-9924657,1938683,636,182,261,492,4540,1017],[-9919219,1940324,6,-226],[-9919202,1940086,119,-121],[-9901240,1924612,536,549,-782,738],[-9901556,1925934,-311,140],[-9901891,1926083,-693,138],[-9902686,1926176,39,1],[-9902720,1926184,-653,586],[-9903567,1927026,-79,72],[-9913083,1928359,-1023,-106,-386,-1508,600,-2148,-534,-123,25,-506,-351,58,307,-574,-623,17,-270,-871,223,-257,-324,-277,1607,-491,878,-1466],[-9918862,1939563,1818,416],[-9917044,1939979,-55,309],[-9917108,1940350,-1273,416],[-9918430,1940783,924,1521],[-9917510,1942316,-184,31],[-9917764,1942360,1186,2005,177,1062]]; // fin LIMITES_MINIMOS
  var ALCALDIAS_MINIMAS = [["Azcapotzalco",0,-9918211,1948533],["Coyoacán",0,-9915038,1932667],["Cuajimalpa de Morelos",0,-9931093,1932432],["Gustavo A. Madero",0,-9911586,1950407],["Iztacalco",0,-9909433,1939691],["Iztapalapa",0,-9905680,1934917],["La Magdalena Contreras",0,-9926841,1926898],["Milpa Alta",0,-9905110,1913946],["Álvaro Obregón",0,-9924682,1933618],["Tláhuac",0,-9900282,1927700],["Tlalpan",0,-9920622,1919834],["Xochimilco",0,-9909036,1924515],["Benito Juárez",0,-9916113,1938064],["Cuauhtémoc",0,-9914906,1943137],["Miguel Hidalgo",0,-9920458,1942807],["Venustiano Carranza",0,-9909311,1943050]]; // fin ALCALDIAS_MINIMAS

  var estado = {
    mapa: null, maxZoom: 19, remota: null, local: null, control: null,
    actual: null, preferido: null, provisional: false, cayendo: false,
    modo: modoDocumento(), disponibilidad: {},
    vig: null,          // vigilancia de la capa remota en uso
    esperaDesde: 0,     // desde cuándo el mapa no tiene nada que enseñar
    cubriendo: false,   // la copia local está a la vista (sola o debajo)
    recuperar: { espera: 0, reloj: null }
  };
  var pruebas = {};

  /* ------------------------------------------------------------------ */

  function t(clave, vars) {
    return window.I18N && window.I18N.t ? window.I18N.t(clave, vars) : clave;
  }

  function leer(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function guardar(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* sin almacenamiento */ } }

  /* Mismo criterio que estilo.css: data-modo manda; si falta (modo
     automático), el sistema. */
  function modoDocumento() {
    var m = document.documentElement.getAttribute('data-modo');
    if (m === 'claro' || m === 'oscuro') return m;
    return window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'oscuro' : 'claro';
  }

  function porId(id) {
    for (var i = 0; i < PROVEEDORES.length; i++) if (PROVEEDORES[i].id === id) return PROVEEDORES[i];
    return null;
  }

  function nombre(p) { return p.nombre || t('teselas.local'); }

  function plantilla(p, modo) { return (modo === 'oscuro' && p.oscuro) || p.claro; }

  /* Las pruebas y su resultado se guardan por URL: claro y oscuro sólo
     son distintos en los proveedores con versión oscura. */
  function clave(p, modo) { return p.id + (modo === 'oscuro' && p.oscuro ? ':oscuro' : ''); }

  /* ------------------------------------------------------------------
     Comprobación
     ------------------------------------------------------------------ */

  function teselaCentro(z) {
    var n = Math.pow(2, z), lat = CENTRO.lat * Math.PI / 180;
    return {
      x: Math.floor((CENTRO.lng + 180) / 360 * n),
      y: Math.floor((1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2 * n)
    };
  }

  function urlTesela(p, modo, z, x, y) {
    return plantilla(p, modo)
      .replace('{s}', p.sub ? p.sub.charAt(0) : '')
      .replace('{z}', z).replace('{x}', x).replace('{y}', y).replace('{r}', '');
  }

  /* El plazo no depende de que fetch respete la señal de cancelar: si la
     petición se cuelga, la carrera la da por perdida igual. */
  function bajar(url) {
    var ctl = window.AbortController ? new AbortController() : null;
    var reloj;
    var plazo = new Promise(function (_, no) {
      reloj = setTimeout(function () { if (ctl) ctl.abort(); no(new Error('plazo')); }, ESPERA_PRUEBA);
    });
    var pedido = fetch(url, { mode: 'cors', credentials: 'omit', signal: ctl ? ctl.signal : undefined })
      .then(function (r) {
        var tipo = r.headers.get('content-type') || '';
        if (!r.ok || tipo.indexOf('image/') !== 0) throw new Error(r.status + ' ' + tipo);
        return r.arrayBuffer();
      });
    return Promise.race([pedido, plazo]).then(
      function (b) { clearTimeout(reloj); return b; },
      function (e) { clearTimeout(reloj); throw e; });
  }

  function iguales(a, b) {
    if (a.byteLength !== b.byteLength) return false;
    var x = new Uint8Array(a), y = new Uint8Array(b);
    for (var i = 0; i < x.length; i++) if (x[i] !== y[i]) return false;
    return true;
  }

  function marcar(p, modo, valor) {
    estado.disponibilidad[clave(p, modo)] = valor;
    pintarControl();
  }

  function disponible(p) {
    return estado.disponibilidad[clave(p, estado.modo)];
  }

  /* Promesa de booleano. Nunca se rechaza. */
  function probar(p, modo) {
    if (p.local) return Promise.resolve(true);
    if (!window.fetch || !window.Promise) return Promise.resolve(true);  // sin forma de comprobarlo
    var k = clave(p, modo);
    if (pruebas[k]) return pruebas[k];
    marcar(p, modo, 'comprobando');
    var c = teselaCentro(ZOOM_PRUEBA);
    var prueba;
    try {
      prueba = Promise.all([
        bajar(urlTesela(p, modo, ZOOM_PRUEBA, c.x, c.y)),
        bajar(urlTesela(p, modo, ZOOM_PRUEBA, c.x + 1, c.y))
      ]);
    } catch (e) {
      prueba = Promise.reject(e);   // fetch que lanza en lugar de rechazar
    }
    pruebas[k] = prueba
      .then(function (b) { return !iguales(b[0], b[1]); }, function () { return false; })
      .then(function (ok) { marcar(p, modo, ok ? 'ok' : 'falla'); return ok; });
    return pruebas[k];
  }

  /* El primero de `orden` que pase la prueba. Se prueban escalonados: si el
     preferido responde enseguida no se molesta a los demás, y si tarda, el
     siguiente ya va en camino. Pasado PLAZO_TOTAL se elige lo mejor que haya
     respondido, y si nada respondió, la copia local; si después contesta un
     proveedor remoto, se cambia a él. */
  function elegir(orden) {
    return new Promise(function (resolver) {
      var res = {}, lanzados = 0, listo = false;

      function decidir(final) {
        if (listo) return;
        for (var i = 0; i < orden.length; i++) {
          var r = res[orden[i].id];
          if (r === true) { listo = true; resolver(orden[i]); return; }
          if (r === undefined && !final) return;
        }
        if (final) { listo = true; resolver(LOCAL); }
      }

      function lanzar() {
        if (listo || lanzados >= orden.length) return;
        var p = orden[lanzados++];
        var siguiente = setTimeout(lanzar, ESCALON);
        probar(p, estado.modo).then(function (ok) {
          res[p.id] = ok;
          clearTimeout(siguiente);
          if (!ok) lanzar();
          if (listo && ok && !p.local && estado.actual === LOCAL && estado.preferido !== LOCAL) {
            activar(p, 'auto');
          }
          decidir(false);
        });
      }

      lanzar();
      setTimeout(function () { decidir(true); }, PLAZO_TOTAL);
    });
  }

  /* `?teselas=<id>` manda sólo en esa visita; lo elegido en el control se
     recuerda. En los dos casos el preferido se prueba primero y, si no
     sirve, se sigue con el orden de siempre. */
  function ordenInicial() {
    var preferido = null;
    try { preferido = porId(new URLSearchParams(window.location.search).get('teselas')); } catch (e) { /* nada */ }
    if (!preferido) preferido = porId(leer(K_PROVEEDOR));
    estado.preferido = preferido;
    var orden = preferido ? [preferido] : [];
    for (var i = 0; i < PROVEEDORES.length; i++) {
      if (PROVEEDORES[i] !== preferido) orden.push(PROVEEDORES[i]);
    }
    return orden;
  }

  /* ------------------------------------------------------------------
     Activación y vigilancia
     ------------------------------------------------------------------ */

  function activar(p, origen) {
    estado.actual = p;
    if (origen === 'manual') {
      estado.preferido = p;
      estado.provisional = false;
      guardar(K_PROVEEDOR, p.id);
      if (!estado.cubriendo) estado.esperaDesde = Date.now();
      /* Elegido a mano se vuelve a probar aunque antes hubiera fallado:
         puede que ya responda. */
      if (!p.local && disponible(p) === 'falla') delete pruebas[clave(p, estado.modo)];
    }
    document.documentElement.setAttribute('data-teselas', p.id);
    pintar();
    pintarControl();
    /* Uno elegido a mano tampoco se queda puesto si no sirve. */
    if (!p.local) probar(p, estado.modo).then(function (ok) { if (!ok && estado.actual === p) caer(); });
    if (p.local && origen === 'auto' && !estado.provisional) programarRecuperacion();
  }

  /* En la copia local por una caída, y no porque alguien la eligiera, la
     cadena se vuelve a probar de vez en cuando (cada vez más espaciado) y
     en cuanto el navegador recupera la conexión: si la red de la sala se
     cayó un momento, el mapa regresa solo a un proveedor remoto. */
  function programarRecuperacion() {
    var r = estado.recuperar;
    clearTimeout(r.reloj);
    r.espera = Math.min(600000, r.espera ? r.espera * 2 : 60000);
    r.reloj = setTimeout(recuperar, r.espera);
  }

  function recuperar() {
    var r = estado.recuperar;
    clearTimeout(r.reloj);
    if (estado.actual !== LOCAL || estado.preferido === LOCAL || estado.cayendo) return;
    var remotos = PROVEEDORES.filter(function (p) {
      if (p.local) return false;
      delete pruebas[clave(p, estado.modo)];
      delete estado.disponibilidad[clave(p, estado.modo)];
      return true;
    });
    elegir(remotos.concat(LOCAL)).then(function (q) {
      if (estado.actual !== LOCAL || estado.preferido === LOCAL) return;
      if (q.local) { programarRecuperacion(); return; }
      r.espera = 0;
      activar(q, 'auto');
      avisar(t('teselas.usando', { nombre: nombre(q) }));
    });
  }
  window.addEventListener('online', recuperar);

  function caer() {
    var p = estado.actual;
    if (!p || p.local || estado.cayendo) return;
    estado.cayendo = true;
    pruebas[clave(p, estado.modo)] = Promise.resolve(false);
    marcar(p, estado.modo, 'falla');
    cubrir(true);   // mientras se elige otro, la copia local tapa el hueco
    /* Los remotos que siguen en la lista, dando la vuelta, y la copia local
       siempre al final. */
    var resto = [];
    var i0 = PROVEEDORES.indexOf(p);
    for (var i = 1; i < PROVEEDORES.length; i++) {
      var q = PROVEEDORES[(i0 + i) % PROVEEDORES.length];
      if (!q.local && disponible(q) !== 'falla') resto.push(q);
    }
    resto.push(LOCAL);
    elegir(resto).then(function (q) {
      estado.cayendo = false;
      if (estado.actual !== p) return;   // entretanto se eligió otro a mano
      activar(q, 'auto');
      avisar(t('teselas.aviso', { antes: nombre(p), ahora: nombre(q) }));
    });
  }

  function vigilar(capa) {
    var v = estado.vig = {
      ok: 0, cargando: false, tandaOk: 0, tandaErr: 0, ultima: Date.now(), ventana: []
    };
    function vigente() { return estado.vig === v && estado.remota === capa; }
    function apuntar(bien) {
      v.ultima = Date.now();
      v.ventana.push(bien);
      if (v.ventana.length > 12) v.ventana.shift();
    }
    capa.on('loading', function () {
      if (!vigente()) return;
      v.cargando = true;
      v.tandaOk = v.tandaErr = 0;
      v.ultima = Date.now();
    });
    capa.on('tileload', function () {
      if (!vigente()) return;
      v.ok++;
      v.tandaOk++;
      apuntar(true);
    });
    /* Se cae cuando fallan más de la mitad de las últimas teselas (y al
       menos cuatro): una suelta que no llega no cuenta, pero un proveedor
       que se cae a media sesión sí, aunque antes hubiera servido cientos. */
    capa.on('tileerror', function () {
      if (!vigente()) return;
      v.tandaErr++;
      apuntar(false);
      var malas = 0;
      for (var i = 0; i < v.ventana.length; i++) if (!v.ventana[i]) malas++;
      if (malas >= 4 && malas * 2 > v.ventana.length) caer();
      else cubrir(true);   // el hueco de esa tesela lo tapa la copia local
    });
    capa.on('load', function () {
      if (!vigente()) return;
      v.cargando = false;
      if (v.tandaOk && !v.tandaErr && !estado.cayendo) cubrir(false);
    });
  }

  /* Cada cuarto de segundo: el atasco (una tanda entera sin que llegue ni
     una tesela) y el plazo para no dejar el mapa en blanco. */
  function revisar() {
    if (!estado.mapa) return;
    var p = estado.actual, v = estado.vig, ahora = Date.now();
    if (p && !p.local && v) {
      var quieto = v.cargando && !v.tandaOk ? ahora - v.ultima : 0;
      if (quieto >= ATASCO) { caer(); return; }
      if (quieto >= PROVISIONAL) cubrir(true);
    }
    var nada = !p || (!p.local && (!v || !v.ok));
    if (nada && !estado.cubriendo) {
      var espera = ahora - estado.esperaDesde;
      /* A un tercio del plazo se empieza a bajar el archivo de la copia
         local, por si hace falta: así, al cumplirse, ya llegó o ya se
         sabe que no llega y se dibuja el contorno mínimo sin más espera. */
      if (espera >= PROVISIONAL / 3) cargarBase().catch(function () { /* contorno mínimo */ });
      if (espera >= PROVISIONAL) cubrir(true);
    }
  }

  /* ------------------------------------------------------------------
     Capas en el mapa
     ------------------------------------------------------------------ */

  function pintar() {
    var mapa = estado.mapa, p = estado.actual;
    if (!mapa || !window.L) return;
    var remoto = p && !p.local ? p : null;
    var url = remoto ? plantilla(remoto, estado.modo) : null;
    var r = estado.remota;
    if (r && (!remoto || r._proveedor !== remoto || r._plantilla !== url)) {
      mapa.removeLayer(r);
      estado.remota = r = null;
      estado.vig = null;
    }
    if (remoto && !r) {
      r = L.tileLayer(url, {
        subdomains: remoto.sub || 'abc',
        maxZoom: estado.maxZoom,
        maxNativeZoom: Math.min(remoto.max, estado.maxZoom),
        attribution: remoto.atribucion,
        zIndex: 1
      });
      r._proveedor = remoto;
      r._plantilla = url;
      estado.remota = r;
      vigilar(r);
      r.addTo(mapa);
    }
    if (r && r.getContainer()) {
      var invertir = !!(remoto.invertir && estado.modo === 'oscuro');
      r.getContainer().classList.toggle('teselas-invertidas', invertir);
    }
    if (p && p.local) cubrir(true);
  }

  /* La copia local se enseña sola cuando es el proveedor en uso, y debajo
     del remoto mientras éste no tenga nada que enseñar. */
  function cubrir(mostrar) {
    if (estado.actual && estado.actual.local) mostrar = true;
    estado.cubriendo = mostrar;
    var mapa = estado.mapa;
    if (!mapa) return;
    var local = capaLocal();
    if (!local) return;
    if (mostrar && !mapa.hasLayer(local)) local.addTo(mapa);
    else if (!mostrar && mapa.hasLayer(local)) mapa.removeLayer(local);
  }

  /* ------------------------------------------------------------------
     Copia local: el extracto de OSM dibujado en lienzos de 256 px.
     ------------------------------------------------------------------ */

  var base = null, baseCargando = null, baseDesde = 0, baseFallo = 0, conMinima = false;
  var etiquetasPorZoom = {};
  var POLIGONOS = { agua: true, parque: true };

  function proyectar(lon, lat) {
    var s = Math.sin(lat * Math.PI / 180);
    return [lon / 360 + 0.5, 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)];
  }

  function decodificar(enteros, q) {
    var n = enteros.length, p = new Float64Array(n);
    var lon = 0, lat = 0, caja = [Infinity, Infinity, -Infinity, -Infinity];
    for (var i = 0; i < n; i += 2) {
      lon += enteros[i];
      lat += enteros[i + 1];
      var m = proyectar(lon / q, lat / q);
      p[i] = m[0];
      p[i + 1] = m[1];
      if (m[0] < caja[0]) caja[0] = m[0];
      if (m[1] < caja[1]) caja[1] = m[1];
      if (m[0] > caja[2]) caja[2] = m[0];
      if (m[1] > caja[3]) caja[3] = m[1];
    }
    return { p: p, caja: caja };
  }

  function poligono(anillos, q) {
    var a = anillos.map(function (r) { return decodificar(r, q); });
    var caja = [Infinity, Infinity, -Infinity, -Infinity];
    a.forEach(function (r) {
      caja = [Math.min(caja[0], r.caja[0]), Math.min(caja[1], r.caja[1]),
              Math.max(caja[2], r.caja[2]), Math.max(caja[3], r.caja[3])];
    });
    return { anillos: a, caja: caja };
  }

  function preparar(doc) {
    var q = doc.q || 100000;
    var capas = {};
    Object.keys(doc.capas || {}).forEach(function (c) {
      capas[c] = doc.capas[c].map(function (r) {
        return POLIGONOS[c] ? poligono(r, q) : decodificar(r, q);
      });
    });
    return {
      ciudad: poligono(doc.ciudad || [], q),
      capas: capas,
      lugares: (doc.lugares || []).map(function (l) {
        var m = proyectar(l[2] / q, l[3] / q);
        return { n: l[0], c: l[1], x: m[0], y: m[1] };
      })
    };
  }

  var BASE_MINIMA = null;
  function baseMinima() {
    if (!BASE_MINIMA) {
      BASE_MINIMA = preparar({
        ciudad: CONTORNO_MINIMO, capas: { limite: LIMITES_MINIMOS }, lugares: ALCALDIAS_MINIMAS
      });
    }
    return BASE_MINIMA;
  }

  function cargarBase() {
    if (base) return Promise.resolve(base);
    if (!baseCargando) {
      /* Si el archivo acaba de fallar no se vuelve a pedir con cada tesela. */
      if (Date.now() - baseFallo < REINTENTO_BASE) return Promise.reject(new Error('reciente'));
      baseDesde = Date.now();
      var reloj;
      var plazo = new Promise(function (_, no) {
        reloj = setTimeout(function () { no(new Error('plazo')); }, PLAZO_BASE);
      });
      var pedido;
      try {
        pedido = fetch(BASE_URL, { credentials: 'same-origin' })
          .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
      } catch (e) {
        pedido = Promise.reject(e);
      }
      baseCargando = Promise.race([pedido, plazo])
        .then(function (doc) {
          clearTimeout(reloj);
          base = preparar(doc);
          etiquetasPorZoom = {};
          /* Teselas que salieron del contorno mínimo mientras el archivo no
             llegaba: ahora que llegó, se rehacen con el mapa completo. */
          if (conMinima && estado.local) {
            conMinima = false;
            setTimeout(function () { estado.local.redraw(); }, 0);
          }
          return base;
        }, function (e) {
          clearTimeout(reloj);
          baseCargando = null;
          baseFallo = Date.now();
          throw e;
        });
    }
    return baseCargando;
  }

  /* Color de marca del tema activo (--marca-600) como "r, g, b". */
  function marca() {
    var v = getComputedStyle(document.documentElement).getPropertyValue('--marca-600').trim();
    var m = /^#([0-9a-f]{6})$/i.exec(v);
    if (m) {
      var n = parseInt(m[1], 16);
      return [(n >> 16) & 255, (n >> 8) & 255, n & 255].join(', ');
    }
    m = /^rgba?\(([^)]+)\)/i.exec(v);
    return m ? m[1].split(',').slice(0, 3).join(',') : '28, 82, 173';
  }

  function paleta() {
    var m = marca();
    return estado.modo === 'oscuro' ? {
      relleno: 'rgba(' + m + ', 0.08)', borde: 'rgba(' + m + ', 0.85)',
      limite: 'rgba(' + m + ', 0.65)',
      agua: '#173247', rio: '#24506f', canal: '#204862', parque: '#1b3127',
      via1: '#7b8696', via2: '#606b7a', via3: '#4b5563',
      texto: '#b9c3cf', alcaldia: '#dfe6ee', halo: 'rgba(8, 12, 18, 0.9)'
    } : {
      relleno: 'rgba(' + m + ', 0.04)', borde: 'rgba(' + m + ', 0.7)',
      limite: 'rgba(' + m + ', 0.45)',
      agua: '#bcd5e8', rio: '#9cc0dc', canal: '#a9c8e0', parque: '#d6e7cf',
      via1: '#a4adb9', via2: '#b6bec8', via3: '#c8ced6',
      texto: '#3c4757', alcaldia: '#1f2937', halo: 'rgba(250, 251, 253, 0.92)'
    };
  }

  /* Grosor a zoom 12 y zoom mínimo al que aparece cada capa de líneas. */
  var LINEAS = [
    ['canal', 0.9, 12], ['rio', 1.2, 10], ['via3', 1.0, 13], ['via2', 1.4, 12],
    ['via1', 2.0, 10], ['limite', 1.2, 0]
  ];

  function cruza(caja, v) {
    return caja[2] >= v[0] && caja[0] <= v[2] && caja[3] >= v[1] && caja[1] <= v[3];
  }

  function trazar(ctx, p, k, ox, oy) {
    ctx.moveTo(p[0] * k - ox, p[1] * k - oy);
    for (var i = 2; i < p.length; i += 2) ctx.lineTo(p[i] * k - ox, p[i + 1] * k - oy);
  }

  var FAMILIA = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';
  function fuente(clase, z) {
    return clase === 0 ? '650 ' + (z >= 13 ? 14 : 12) + 'px ' + FAMILIA
      : clase === 1 ? '500 11px ' + FAMILIA
      : '400 10px ' + FAMILIA;
  }

  /* Los rótulos se colocan una vez por zoom y para todo el mapa, no por
     tesela: así un nombre que cruza el borde entre dos teselas aparece
     entero en las dos mitades y nunca choca con otro. Las alcaldías van
     primero; las colonias sólo de cerca. */
  function etiquetas(b, z) {
    var k0 = z + (b === base ? '' : 'm');
    if (etiquetasPorZoom[k0]) return etiquetasPorZoom[k0];
    var maxClase = z < 13 ? 0 : z < 15 ? 1 : 2;
    var k = 256 * Math.pow(2, z);
    var ctx = document.createElement('canvas').getContext('2d');
    var puestas = [];
    b.lugares.forEach(function (l) {
      if (l.c > maxClase) return;
      ctx.font = fuente(l.c, z);
      var an = ctx.measureText(l.n).width, al = l.c === 0 ? 14 : 11;
      var x = l.x * k, y = l.y * k;
      var caja = [x - an / 2 - 4, y - al / 2 - 3, x + an / 2 + 4, y + al / 2 + 3];
      for (var i = 0; i < puestas.length; i++) if (cruza(puestas[i].caja, caja)) return;
      puestas.push({ l: l, x: x, y: y, caja: caja });
    });
    etiquetasPorZoom[k0] = puestas;
    return puestas;
  }

  function dibujar(lienzo, coords, r, b) {
    var ctx = lienzo.getContext('2d');
    var z = coords.z, n = Math.pow(2, z), k = 256 * n;
    var ox = coords.x * 256, oy = coords.y * 256;
    var margen = 12 / k;
    var vista = [coords.x / n - margen, coords.y / n - margen,
                 (coords.x + 1) / n + margen, (coords.y + 1) / n + margen];
    var c = paleta();
    var escala = Math.min(4, Math.pow(2, (z - 12) * 0.6));
    ctx.setTransform(r, 0, 0, r, 0, 0);
    ctx.clearRect(0, 0, 256, 256);
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';

    function rellenar(pol, color) {
      if (!pol.anillos.length || !cruza(pol.caja, vista)) return;
      ctx.beginPath();
      pol.anillos.forEach(function (a) { trazar(ctx, a.p, k, ox, oy); ctx.closePath(); });
      ctx.fillStyle = color;
      ctx.fill('evenodd');
    }

    rellenar(b.ciudad, c.relleno);
    if (z >= 10) {
      (b.capas.parque || []).forEach(function (pol) { rellenar(pol, c.parque); });
      (b.capas.agua || []).forEach(function (pol) { rellenar(pol, c.agua); });
    }

    LINEAS.forEach(function (def) {
      var lista = b.capas[def[0]];
      if (!lista || z < def[2]) return;
      ctx.beginPath();
      for (var i = 0; i < lista.length; i++) {
        if (cruza(lista[i].caja, vista)) trazar(ctx, lista[i].p, k, ox, oy);
      }
      ctx.strokeStyle = c[def[0]];
      ctx.lineWidth = Math.min(9, def[1] * escala);
      ctx.setLineDash(def[0] === 'limite' ? [6, 4] : []);
      ctx.stroke();
    });

    /* El contorno de la ciudad, encima de todo lo demás. */
    if (b.ciudad.anillos.length && cruza(b.ciudad.caja, vista)) {
      ctx.beginPath();
      b.ciudad.anillos.forEach(function (a) { trazar(ctx, a.p, k, ox, oy); ctx.closePath(); });
      ctx.setLineDash([]);
      ctx.strokeStyle = c.borde;
      ctx.lineWidth = Math.max(1.6, Math.min(4, 2 * escala));
      ctx.stroke();
    }

    var vistaPx = [ox, oy, ox + 256, oy + 256];
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.setLineDash([]);
    etiquetas(b, z).forEach(function (e) {
      if (!cruza(e.caja, vistaPx)) return;
      ctx.font = fuente(e.l.c, z);
      ctx.lineWidth = 3;
      ctx.strokeStyle = c.halo;
      ctx.strokeText(e.l.n, e.x - ox, e.y - oy);
      ctx.fillStyle = e.l.c === 0 ? c.alcaldia : c.texto;
      ctx.fillText(e.l.n, e.x - ox, e.y - oy);
    });
  }

  function capaLocal() {
    if (estado.local) return estado.local;
    if (!window.L || !L.GridLayer) return null;
    var Clase = L.GridLayer.extend({
      /* El archivo tiene ESPERA_BASE desde que se pidió, no desde cada
         tesela: si no ha llegado, se dibuja el contorno mínimo y la tesela
         se rehace cuando llegue. */
      createTile: function (coords, hecho) {
        var tam = this.getTileSize();
        var r = Math.min(2, window.devicePixelRatio || 1);
        var lienzo = document.createElement('canvas');
        lienzo.width = tam.x * r;
        lienzo.height = tam.y * r;
        var listo = false;
        function con(b, minima) {
          if (listo) return;
          listo = true;
          if (minima) conMinima = true;
          try { dibujar(lienzo, coords, r, b); } catch (e) { if (window.console) console.error('mapa-teselas:', e); }
          hecho(null, lienzo);
        }
        /* hecho() tiene que llegar después de que createTile devuelva el
           lienzo: Leaflet registra la tesela justo entonces. */
        if (base) {
          Promise.resolve().then(function () { con(base); });
        } else {
          cargarBase().then(function (b) { con(b); }, function () { con(baseMinima(), true); });
          setTimeout(function () { con(baseMinima(), true); },
                     Math.max(0, baseDesde + ESPERA_BASE - Date.now()));
        }
        return lienzo;
      }
    });
    estado.local = new Clase({
      maxZoom: estado.maxZoom, zIndex: 0, keepBuffer: 3, attribution: LOCAL.atribucion
    });
    return estado.local;
  }

  /* Con el mapa ya en pie, el archivo de la copia local se baja en segundo
     plano: si la red se cae a media sesión (la wifi de una sala, por
     ejemplo), la copia ya está en memoria y no hace falta pedirla. */
  function precargar() {
    function ya() { cargarBase().catch(function () { /* se reintenta al usarla */ }); }
    function luego() {
      setTimeout(function () {
        if (window.requestIdleCallback) requestIdleCallback(ya, { timeout: 5000 });
        else ya();
      }, 3000);
    }
    if (document.readyState === 'complete') luego();
    else window.addEventListener('load', luego);
  }

  /* ------------------------------------------------------------------
     El control «¿No carga el mapa?»
     ------------------------------------------------------------------ */

  var aviso = { nodo: null, reloj: null };

  function montarControl(mapa) {
    if (estado.control || !L.Control) return;
    var Control = L.Control.extend({
      options: { position: 'bottomright' },
      onAdd: function () {
        var raiz = L.DomUtil.create('div', 'mapa-teselas leaflet-control');
        raiz.innerHTML =
          '<div class="mapa-teselas__aviso" role="status" aria-live="polite" hidden></div>' +
          '<div class="mapa-teselas__panel" id="mapa-teselas-panel" hidden>' +
          '<p class="mapa-teselas__titulo"></p>' +
          '<ul class="mapa-teselas__lista"></ul>' +
          '<p class="mapa-teselas__nota"></p>' +
          '</div>' +
          '<div class="mapa-teselas__barra">' +
          '<button type="button" class="mapa-teselas__probar">' +
          '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
          '<span class="mapa-teselas__pregunta"></span> <strong class="mapa-teselas__accion"></strong>' +
          '</button>' +
          '<button type="button" class="mapa-teselas__abrir" aria-expanded="false" aria-controls="mapa-teselas-panel">' +
          '<span class="mapa-teselas__actual"></span>' +
          '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 15l6-6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>' +
          '</button>' +
          '</div>';
        L.DomEvent.disableClickPropagation(raiz);
        L.DomEvent.disableScrollPropagation(raiz);

        raiz.querySelector('.mapa-teselas__probar').addEventListener('click', probarOtro);
        raiz.querySelector('.mapa-teselas__abrir').addEventListener('click', function () {
          abrirPanel(raiz.querySelector('.mapa-teselas__panel').hidden);
        });
        raiz.querySelector('.mapa-teselas__lista').addEventListener('click', function (ev) {
          var b = ev.target.closest('[data-id]');
          if (!b) return;
          var p = porId(b.getAttribute('data-id'));
          if (p) activar(p, 'manual');
        });
        raiz.addEventListener('keydown', function (ev) {
          if (ev.key === 'Escape') {
            abrirPanel(false);
            raiz.querySelector('.mapa-teselas__abrir').focus();
          }
        });
        aviso.nodo = raiz.querySelector('.mapa-teselas__aviso');
        return raiz;
      }
    });
    estado.control = new Control().addTo(mapa);
    mapa.on('click', function () { abrirPanel(false); });
    mapa.on('resize', ajustarControl);
    pintarControl();
    ajustarControl();
  }

  function raizControl() { return estado.control && estado.control.getContainer(); }

  /* El control se mide contra el mapa, no contra la ventana: en
     vecindad.html, en un teléfono, el mapa es bastante más estrecho que la
     pantalla, y la lista abierta no debe salirse por arriba. Lo que tiene
     encima la lista depende de la barra y de la atribución, que con Esri
     ocupa varias líneas, así que se mide en lugar de suponerlo. */
  function ajustarControl() {
    var raiz = raizControl();
    if (!raiz || !estado.mapa) return;
    var mapa = estado.mapa.getContainer().getBoundingClientRect();
    raiz.style.maxWidth = Math.max(160, mapa.width - 20) + 'px';
    var barra = raiz.querySelector('.mapa-teselas__barra').getBoundingClientRect();
    if (!barra.height) return;   // sin pintar todavía
    raiz.querySelector('.mapa-teselas__panel').style.maxHeight =
      Math.max(120, barra.top - mapa.top - 16) + 'px';
  }

  function abrirPanel(abrir) {
    var raiz = raizControl();
    if (!raiz) return;
    raiz.querySelector('.mapa-teselas__panel').hidden = !abrir;
    raiz.querySelector('.mapa-teselas__abrir').setAttribute('aria-expanded', abrir ? 'true' : 'false');
    if (abrir) ajustarControl();
    /* Al abrir la lista se comprueban todos, para que el estado de cada uno
       esté a la vista antes de elegir. */
    if (abrir) PROVEEDORES.forEach(function (p) { probar(p, estado.modo); });
  }

  /* El siguiente de la lista que no haya fallado; si todos fallaron, el
     siguiente sin más, que se vuelve a probar. */
  function probarOtro() {
    var n = PROVEEDORES.length;
    var i0 = Math.max(0, PROVEEDORES.indexOf(estado.actual));
    var q = null;
    for (var i = 1; i < n && !q; i++) {
      var c = PROVEEDORES[(i0 + i) % n];
      if (disponible(c) !== 'falla') q = c;
    }
    q = q || PROVEEDORES[(i0 + 1) % n];
    activar(q, 'manual');
    avisar(t('teselas.usando', { nombre: nombre(q) }));
  }

  function avisar(texto) {
    if (!aviso.nodo) return;
    aviso.nodo.textContent = texto;
    aviso.nodo.hidden = false;
    clearTimeout(aviso.reloj);
    aviso.reloj = setTimeout(function () { aviso.nodo.hidden = true; }, 6000);
  }

  function pintarControl() {
    var raiz = raizControl();
    if (!raiz) return;
    var p = estado.actual;
    raiz.querySelector('.mapa-teselas__pregunta').textContent = t('teselas.pregunta');
    raiz.querySelector('.mapa-teselas__accion').textContent = t('teselas.probar');
    raiz.querySelector('.mapa-teselas__actual').textContent = p ? nombre(p) : t('teselas.estado.comprobando');
    var abrir = raiz.querySelector('.mapa-teselas__abrir');
    abrir.title = t('teselas.elegir');
    abrir.setAttribute('aria-label', t('teselas.elegir') + ' — ' + (p ? nombre(p) : t('teselas.estado.comprobando')));
    raiz.querySelector('.mapa-teselas__titulo').textContent = t('teselas.titulo');
    raiz.querySelector('.mapa-teselas__nota').textContent = t('teselas.explica');
    /* Los botones se crean una vez y luego sólo se actualizan: rehacerlos
       con cada resultado de prueba le quitaría el foco a quien navega con
       el teclado. */
    var lista = raiz.querySelector('.mapa-teselas__lista');
    if (!lista.children.length) {
      PROVEEDORES.forEach(function (q) {
        var li = document.createElement('li');
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'mapa-teselas__opcion';
        b.setAttribute('data-id', q.id);
        b.innerHTML = '<span class="mapa-teselas__punto" aria-hidden="true"></span>' +
          '<span class="mapa-teselas__nombre"></span><small class="mapa-teselas__tipo"></small>' +
          '<span class="mapa-teselas__estado"></span>';
        li.appendChild(b);
        lista.appendChild(li);
      });
    }
    PROVEEDORES.forEach(function (q, i) {
      var b = lista.children[i].firstChild;
      var disp = q === p ? 'uso' : (disponible(q) || (q.local ? 'ok' : 'nada'));
      b.setAttribute('data-estado', disp);
      b.setAttribute('aria-pressed', q === p ? 'true' : 'false');
      b.querySelector('.mapa-teselas__nombre').textContent = nombre(q);
      b.querySelector('.mapa-teselas__tipo').textContent = t(q.nota);
      b.querySelector('.mapa-teselas__estado').textContent =
        disp === 'nada' ? '' : t('teselas.estado.' + disp);
    });
    ajustarControl();   // la atribución del nuevo proveedor puede medir otra cosa
  }

  document.addEventListener('idiomacambiado', pintarControl);

  /* nav.js emite 'temacambiado' al cambiar el tema, el modo, o el modo del
     sistema cuando está en automático. El modo cambia la URL de los que
     tienen versión oscura y el filtro de los que no; el tema, el color de
     la copia local. */
  document.addEventListener('temacambiado', function () {
    var modo = modoDocumento();
    if (modo !== estado.modo) {
      estado.modo = modo;
      var p = estado.actual;
      if (p && !p.local) {
        if (!estado.cubriendo) estado.esperaDesde = Date.now();
        pintar();
        probar(p, modo).then(function (ok) { if (!ok && estado.actual === p) caer(); });
      }
      pintarControl();
    }
    if (estado.local && estado.mapa && estado.mapa.hasLayer(estado.local)) estado.local.redraw();
  });

  /* ------------------------------------------------------------------
     Arranque
     ------------------------------------------------------------------ */

  function montar(mapa, opciones) {
    if (estado.mapa) return;   // un mapa por página
    estado.mapa = mapa;
    estado.maxZoom = (opciones && opciones.maxZoom) || 19;
    estado.esperaDesde = Date.now();
    montarControl(mapa);
    pintar();
    setInterval(revisar, 250);
    precargar();
  }

  /* La elección arranca en cuanto carga este script, antes de que la página
     cree el mapa: para entonces normalmente ya se sabe qué proveedor
     responde. Si tarda más de PROVISIONAL, entretanto se muestra la copia
     local, para que el mapa no espere en blanco a que se agoten los plazos. */
  var provisional = setTimeout(function () {
    if (estado.actual) return;
    estado.provisional = true;
    activar(LOCAL, 'auto');
  }, PROVISIONAL);
  elegir(ordenInicial()).then(function (p) {
    clearTimeout(provisional);
    /* La bandera se apaga antes de activar: si la decisión también es la
       copia local, ya no es provisional y hay que programar su recuperación. */
    var eraProvisional = estado.provisional;
    estado.provisional = false;
    if (!estado.actual || (eraProvisional && estado.actual === LOCAL)) activar(p, 'auto');
  });

  window.MapaTeselas = {
    montar: montar,
    proveedores: PROVEEDORES.map(function (p) { return p.id; }),
    actual: function () { return estado.actual && estado.actual.id; },
    disponibilidad: function () { return JSON.parse(JSON.stringify(estado.disponibilidad)); },
    usar: function (id) { var p = porId(id); if (p) activar(p, 'manual'); return !!p; }
  };
})();
