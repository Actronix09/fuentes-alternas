/* Modulo exploratorio de consumos atipicos.
   Calcula A_g = |x - mu| / (sigma + eps) para cada colonia frente a la media de
   su alcaldia y ordena las zonas por atipicidad. Es lo que describe el articulo:
   no un diagnostico, sino una funcion de ordenamiento que dice que unidades
   territoriales mirar primero.
   Autocontenido: lee consumo.json y se inserta como una tarjeta mas del panel,
   sin tocar el JavaScript existente. */
(function () {
  'use strict';
  var EPS = 1e-9, TOPE = 15;
  var T = function (k, v) { return window.I18N.t(k, v); };
  var fmt = function (n) { return window.I18N.num(n, { maximumFractionDigits: 0 }); };
  var fmt2 = function (n) { return window.I18N.num(n, { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };

  /* Los textos fijos llevan data-i18n y los traduce i18n.js; los que se
     arman con cifras se rehacen desde aquí al cambiar de idioma. */
  function tarjeta() {
    var el = document.createElement('div');
    el.className = 'panel atipicos';
    el.innerHTML =
      '<h3 class="atip-cab"><span data-i18n="at.titulo">' + T('at.titulo') + '</span>' +
      '<button type="button" id="atipToggle" class="atip-toggle" aria-expanded="true">' +
      T('at.ocultar') + '</button></h3>' +
      '<div class="atip-cuerpo">' +
        '<p class="atip-nota" data-i18n-html="at.nota">' + T('at.nota') + '</p>' +
        '<div class="atip-controles">' +
          '<div><label for="atipAlc" data-i18n="at.alcaldia">' + T('at.alcaldia') + '</label>' +
          '<select id="atipAlc"><option value="" data-i18n="com.todas">' + T('com.todas') + '</option></select></div>' +
          '<div><label for="atipTipo" data-i18n="at.mostrarSel">' + T('at.mostrarSel') + '</label>' +
          '<select id="atipTipo">' +
          '<option value="ambos" data-i18n="at.ambos">' + T('at.ambos') + '</option>' +
          '<option value="alto" data-i18n="at.soloAlto">' + T('at.soloAlto') + '</option>' +
          '<option value="bajo" data-i18n="at.soloBajo">' + T('at.soloBajo') + '</option></select></div>' +
        '</div>' +
        '<div id="atipEstado" class="atip-nota">' + T('at.calculando') + '</div>' +
        '<div class="tabla-env" id="atipTabla"></div>' +
      '</div>';
    return el;
  }

  function insertar(el) {
    var panels = document.querySelector('.panels');
    var kpis = document.querySelector('.kpis');
    if (panels && panels.parentNode) panels.parentNode.insertBefore(el, panels.nextSibling);
    else if (kpis && kpis.parentNode) kpis.parentNode.insertBefore(el, kpis.nextSibling);
    else document.querySelector('.app-container').appendChild(el);
  }

  function calcular(filas) {
    var porColonia = {}, i, r, k;
    for (i = 0; i < filas.length; i++) {
      r = filas[i];
      k = r.alcaldia + '|' + r.colonia;
      if (!porColonia[k]) porColonia[k] = { alcaldia: r.alcaldia, colonia: r.colonia, total: 0 };
      porColonia[k].total += Number(r.consumo_total) || 0;
    }
    var porAlcaldia = {};
    Object.keys(porColonia).forEach(function (k) {
      var c = porColonia[k];
      (porAlcaldia[c.alcaldia] = porAlcaldia[c.alcaldia] || []).push(c);
    });
    var salida = [];
    Object.keys(porAlcaldia).forEach(function (a) {
      var l = porAlcaldia[a], n = l.length;
      var mu = l.reduce(function (s, c) { return s + c.total; }, 0) / n;
      var sigma = Math.sqrt(l.reduce(function (s, c) { return s + Math.pow(c.total - mu, 2); }, 0) / n);
      l.forEach(function (c) {
        salida.push({
          alcaldia: c.alcaldia, colonia: c.colonia, total: c.total,
          ag: Math.abs(c.total - mu) / (sigma + EPS),
          sentido: c.total >= mu ? 'alto' : 'bajo',
          veces: mu > 0 ? c.total / mu : 0
        });
      });
    });
    return salida.sort(function (a, b) { return b.ag - a.ag; });
  }

  function pintar(datos, alc, tipo) {
    var d = datos;
    if (alc) d = d.filter(function (x) { return x.alcaldia === alc; });
    if (tipo !== 'ambos') d = d.filter(function (x) { return x.sentido === tipo; });
    var sobre = d.filter(function (x) { return x.ag > 3; }).length;
    document.getElementById('atipEstado').innerHTML = T('at.estado', {
      sobre: fmt(sobre), total: fmt(d.length), mostradas: Math.min(TOPE, d.length)
    });
    var filas = d.slice(0, TOPE).map(function (x) {
      return '<tr><td class="nombre-largo" title="' + x.colonia + '">' + x.colonia + '</td>' +
        '<td>' + x.alcaldia + '</td>' +
        '<td class="num">' + fmt(x.total) + '</td>' +
        '<td class="num"><b>' + fmt2(x.ag) + '</b></td>' +
        '<td><span class="atip-sent ' + x.sentido + '">' +
          T(x.sentido === 'alto' ? 'at.alto' : 'at.bajo') + '</span></td>' +
        '<td class="atip-por">' + T('at.veces', { veces: fmt2(x.veces) }) + '</td></tr>';
    }).join('');
    document.getElementById('atipTabla').innerHTML = d.length
      ? '<table><thead><tr><th>' + T('at.th.colonia') + '</th><th>' + T('at.th.alcaldia') + '</th>' +
        '<th class="num">' + T('at.th.consumo') + '</th>' +
        '<th class="num">A<sub>g</sub></th><th>' + T('at.th.sentido') + '</th>' +
        '<th>' + T('at.th.lectura') + '</th></tr></thead>' +
        '<tbody>' + filas + '</tbody></table>'
      : '<p class="atip-nota">' + T('at.sinDatos') + '</p>';
  }

  /* Se guardan para poder rehacer el módulo en el otro idioma sin volver
     a pedir consumo.json ni perder lo que el usuario tiene elegido. */
  var rotularToggle = null, refrescar = null;

  function alternar() {
    var b = document.getElementById('atipToggle');
    var c = document.querySelector('.atipicos .atip-cuerpo');
    if (!b || !c) return;
    var abierto = localStorage.getItem('dwagua-atipicos') !== 'oculto';
    rotularToggle = function () {
      c.style.display = abierto ? '' : 'none';
      b.textContent = T(abierto ? 'at.ocultar' : 'at.mostrar');
      b.setAttribute('aria-expanded', String(abierto));
    };
    rotularToggle();
    b.addEventListener('click', function () {
      abierto = !abierto;
      try { localStorage.setItem('dwagua-atipicos', abierto ? 'visible' : 'oculto'); } catch (e) {}
      rotularToggle();
    });
  }

  function iniciar() {
    if (!document.querySelector('.app-container')) return;
    insertar(tarjeta());
    alternar();
    fetch('consumo.json').then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (j) {
      var datos = calcular(j.consumo_colonia || []);
      var selAlc = document.getElementById('atipAlc');
      var vistos = {};
      datos.forEach(function (d) { vistos[d.alcaldia] = 1; });
      Object.keys(vistos).sort(function (a, b) { return a.localeCompare(b, 'es'); })
        .forEach(function (a) { selAlc.add(new Option(a, a)); });
      var selTipo = document.getElementById('atipTipo');
      refrescar = function () { pintar(datos, selAlc.value, selTipo.value); };
      selAlc.onchange = selTipo.onchange = refrescar;
      refrescar();
    }).catch(function (e) {
      document.getElementById('atipEstado').innerHTML =
        T('at.errDatos', { msg: e.message || e });
    });
  }

  /* La tarjeta la inserta este script, así que i18n.js ya no la vigila:
     hay que traducirla a mano. Los selectores conservan su valor porque
     no se reconstruyen; sólo se vuelve a pintar la tabla. */
  document.addEventListener('idiomacambiado', function () {
    var t = document.querySelector('.atipicos');
    if (!t) return;
    window.I18N.aplicar(t);
    if (rotularToggle) rotularToggle();
    if (refrescar) refrescar();
  });

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar);
  else iniciar();
})();
