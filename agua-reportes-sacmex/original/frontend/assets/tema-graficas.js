/* Hace que las gráficas de Plotly sigan el tema y el modo claro/oscuro.
   No toca el código que las crea: intercepta Plotly.newPlot y Plotly.react
   para inyectar el layout del tema, y las repinta al cambiar de tema. */
(function () {
  if (typeof Plotly === 'undefined') return;
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  function layoutTema() {
    return {
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: css('--texto-2'), family: css('--sans') || 'system-ui', size: 12 },
      colorway: [css('--marca-600'), css('--acento-500'), css('--marca-500'),
                 css('--acento-700'), css('--marca-800')],
      hoverlabel: { bgcolor: css('--superficie'), bordercolor: css('--borde'),
                    font: { color: css('--texto'), size: 12 } },
      xaxis: { gridcolor: css('--borde'), zerolinecolor: css('--borde'),
               linecolor: css('--borde'), automargin: true,
               tickfont: { color: css('--texto-3'), size: 11 } },
      yaxis: { gridcolor: css('--borde'), zerolinecolor: css('--borde'),
               linecolor: css('--borde'), automargin: true,
               tickfont: { color: css('--texto-3'), size: 11 } },
      margin: { t: 30, r: 16, b: 44, l: 56 },
    };
  }
  const fundir = (base, extra) => {
    const r = Object.assign({}, layoutTema(), base || {});
    ['xaxis', 'yaxis'].forEach(k => {
      r[k] = Object.assign({}, layoutTema()[k], (base && base[k]) || {});
    });
    return Object.assign(r, extra || {});
  };

  /* Para repintar hay que pasar por relayout con notación de punto.
     Con un objeto anidado, relayout sustituye el contenedor entero: un
     {xaxis:{gridcolor…}} se lleva por delante xaxis.title, y los títulos
     de eje desaparecían al cambiar de tema. Con 'xaxis.gridcolor' sólo se
     tocan las hojas y lo que puso la página sigue en pie.
     El margen se excluye a propósito: es geometría de cada gráfica —el
     panel usa 220 px a la izquierda para los nombres largos— y un cambio
     de tema no tiene por qué recolocarla. */
  function aplanar(obj, prefijo, salida) {
    salida = salida || {};
    Object.keys(obj).forEach(k => {
      const v = obj[k], ruta = prefijo ? prefijo + '.' + k : k;
      if (v && typeof v === 'object' && !Array.isArray(v)) aplanar(v, ruta, salida);
      else salida[ruta] = v;
    });
    return salida;
  }
  function soloColores() {
    const plano = aplanar(layoutTema());
    Object.keys(plano).forEach(k => { if (k.indexOf('margin.') === 0) delete plano[k]; });
    return plano;
  }

  /* Etiquetas largas -------------------------------------------------
     Nombres como "SAN JERONIMO ACULCO - LIDICE (PBLO) (LA MAGDALENA
     CONTRERAS)" no caben en el eje y Plotly los encima. Se recortan para
     el eje y el nombre completo se conserva en el globo de información.
     Se trabaja sobre una copia: los datos originales no se tocan. */
  const TOPE = 30;
  const recorta = t => (t.length > TOPE ? t.slice(0, TOPE - 1).trimEnd() + '…' : t);

  function acorta(data) {
    if (!Array.isArray(data)) return data;
    return data.map(tr => {
      if (!tr || typeof tr !== 'object') return tr;
      const eje = ['y', 'x'].find(k =>
        Array.isArray(tr[k]) && tr[k].some(v => typeof v === 'string' && v.length > TOPE));
      if (!eje) return tr;
      const copia = Object.assign({}, tr);
      const completos = tr[eje];
      copia[eje] = completos.map(v => (typeof v === 'string' ? recorta(v) : v));
      if (copia.hovertext === undefined && copia.hovertemplate === undefined) {
        copia.hovertext = completos;
        copia.hovertemplate = '%{hovertext}<br>%{' + (eje === 'y' ? 'x' : 'y') + ':,.0f}<extra></extra>';
      }
      return copia;
    });
  }

  /* Plotly dibuja las marcas del eje como <text> en un SVG y no les pone
     título, así que al recortarlas el nombre completo quedaba inaccesible.
     Tras cada dibujado se les añade un <title>, que es lo que el navegador
     muestra al detener el cursor encima. */
  const DICC = new WeakMap();

  function anotarEjes(gd) {
    const dicc = DICC.get(typeof gd === 'string' ? document.getElementById(gd) : gd);
    const nodo = typeof gd === 'string' ? document.getElementById(gd) : gd;
    if (!dicc || !nodo) return;
    nodo.querySelectorAll('.xtick text, .ytick text').forEach(t => {
      const completo = dicc.get((t.textContent || '').trim());
      if (!completo) return;
      let titulo = t.querySelector('title');
      if (!titulo) {
        titulo = document.createElementNS('http://www.w3.org/2000/svg', 'title');
        t.appendChild(titulo);
      }
      titulo.textContent = completo;
      t.style.cursor = 'help';
    });
  }

  /* Trazas sin color propio ----------------------------------------
     Plotly resuelve el colorway al dibujar y escribe el color elegido en
     _fullData, así que un relayout posterior del colorway ya no las
     alcanza: al cambiar de tema las barras se quedaban del color viejo.
     Se anota qué trazas venían sin marker.color para poder recolorearlas.
     Las que sí lo traen —la de correlación lleva la temperatura en el
     color, con su escala secuencial— no se tocan nunca. */
  const LIBRES = new WeakMap();

  function anotarLibres(gd, data) {
    const nodo = typeof gd === 'string' ? document.getElementById(gd) : gd;
    if (!nodo || !Array.isArray(data)) return;
    const libres = [];
    data.forEach((tr, i) => {
      const c = tr && tr.marker && tr.marker.color;
      if (c === undefined || c === null) libres.push(i);
    });
    LIBRES.set(nodo, libres);
  }

  function recolorear(gd) {
    const libres = LIBRES.get(gd);
    if (!libres || !libres.length) return;
    const via = layoutTema().colorway;
    return Plotly.restyle(gd, { 'marker.color': libres.map(i => via[i % via.length]) }, libres);
  }

  function registrar(gd, data) {
    const nodo = typeof gd === 'string' ? document.getElementById(gd) : gd;
    if (!nodo || !Array.isArray(data)) return;
    const dicc = DICC.get(nodo) || new Map();
    data.forEach(tr => ['y', 'x'].forEach(k => {
      if (!Array.isArray(tr && tr[k])) return;
      tr[k].forEach(v => { if (typeof v === 'string' && v.length > TOPE) dicc.set(recorta(v), v); });
    }));
    DICC.set(nodo, dicc);
  }

  const nuevo = Plotly.newPlot, react = Plotly.react;
  function tras(p, gd) {
    return Promise.resolve(p).then(r => { setTimeout(() => anotarEjes(gd), 0); return r; });
  }
  Plotly.newPlot = function (gd, data, layout, config) {
    registrar(gd, data); anotarLibres(gd, data);
    return tras(nuevo.call(Plotly, gd, acorta(data), fundir(layout), config), gd);
  };
  Plotly.react = function (gd, data, layout, config) {
    registrar(gd, data); anotarLibres(gd, data);
    return tras(react.call(Plotly, gd, acorta(data), fundir(layout), config), gd);
  };

  document.addEventListener('temacambiado', () => {
    requestAnimationFrame(() => {
      const colores = soloColores();
      document.querySelectorAll('.js-plotly-plot').forEach(gd => {
        try {
          Plotly.relayout(gd, colores)
            .then(() => recolorear(gd))
            .then(() => anotarEjes(gd));
        } catch (e) {}
      });
    });
  });
})();
