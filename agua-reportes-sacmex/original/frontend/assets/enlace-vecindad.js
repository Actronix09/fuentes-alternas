/* Puente del mapa hacia el explorador de vecindad.
   Cuando se abre un globo de Leaflet, añade un enlace que lleva a
   vecindad.html filtrado por esa alcaldía (o centrado en esa colonia).

   Observa el DOM en vez de engancharse al evento 'popupopen' del mapa:
   así no depende de que la variable del mapa sea global ni del momento en
   que se inicialice. No toca buildPopupHtml(). */
(function () {
  'use strict';

  var ALCALDIAS = ['ALVARO OBREGON','AZCAPOTZALCO','BENITO JUAREZ','COYOACAN',
    'CUAJIMALPA DE MORELOS','CUAUHTEMOC','GUSTAVO A. MADERO','IZTACALCO',
    'IZTAPALAPA','LA MAGDALENA CONTRERAS','MIGUEL HIDALGO','MILPA ALTA',
    'TLAHUAC','TLALPAN','VENUSTIANO CARRANZA','XOCHIMILCO'];

  function normalizar(t) {
    return (t || '')
      .replace(/[^\p{L}\p{N}\s.\-()]/gu, ' ')   // quita emojis y adornos
      .replace(/\s+/g, ' ')
      .trim()
      .toUpperCase();
  }
  // Los datos del almacén vienen sin acentos ("CUAUHTEMOC"), pero los globos
  // del mapa los muestran con acento ("Cuauhtémoc"). Se compara y se envía
  // siempre la forma sin acentos.
  function sinAcentos(t) {
    return (t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }
  function esAlcaldia(n) {
    var s = sinAcentos(normalizar(n));
    return ALCALDIAS.some(function (a) { return sinAcentos(a) === s; });
  }

  function agregar(popup) {
    if (!popup) return;
    var titulo = popup.querySelector('.popup-title');
    if (!titulo) return;
    var nombre = normalizar(titulo.textContent);
    if (!nombre) return;

    /* Si el enlace ya está se reutiliza: así el cambio de idioma sólo le
       cambia el texto en vez de duplicarlo. */
    var a = popup.querySelector('.ir-vecindad');
    var nuevo = !a;
    if (nuevo) { a = document.createElement('a'); a.className = 'ir-vecindad'; }

    if (esAlcaldia(nombre)) {
      a.href = 'vecindad.html?alcaldia=' + encodeURIComponent(sinAcentos(nombre));
      a.innerHTML = window.I18N.t('ev.alcaldia');
    } else {
      a.href = 'vecindad.html?colonia=' + encodeURIComponent(sinAcentos(nombre));
      a.innerHTML = window.I18N.t('ev.colonia');
    }
    if (nuevo) (popup.querySelector('.leaflet-popup-content') || popup).appendChild(a);
  }

  function revisar(nodo) {
    if (!(nodo instanceof Element)) return;
    if (nodo.classList && nodo.classList.contains('leaflet-popup')) return agregar(nodo);
    var p = nodo.querySelectorAll ? nodo.querySelectorAll('.leaflet-popup') : [];
    for (var i = 0; i < p.length; i++) agregar(p[i]);
  }

  new MutationObserver(function (muts) {
    for (var i = 0; i < muts.length; i++) {
      for (var j = 0; j < muts[i].addedNodes.length; j++) revisar(muts[i].addedNodes[j]);
    }
  }).observe(document.body, { childList: true, subtree: true });

  // por si ya hubiera uno abierto al cargar
  document.querySelectorAll('.leaflet-popup').forEach(agregar);

  /* Al cambiar de idioma, mapa.html reescribe el contenido del globo con
     setPopupContent y se lleva por delante este enlace, sin que eso pase
     por el observador. Se vuelve a poner después: el setTimeout deja que
     corran antes todos los suscriptores del evento, así no depende del
     orden en que se registraron. */
  document.addEventListener('idiomacambiado', function () {
    setTimeout(function () {
      document.querySelectorAll('.leaflet-popup').forEach(agregar);
    }, 0);
  });
})();
