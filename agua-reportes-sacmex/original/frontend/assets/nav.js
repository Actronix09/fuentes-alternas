/* Barra de navegación, temas, modo claro/oscuro e idioma. Compartido por las 4 páginas. */
(function () {
  /* i18n.js se carga antes que este script. El respaldo evita que la barra
     desaparezca si alguna página se abriera sin él: se queda sin selector
     de idioma, pero sigue funcionando. */
  const I = window.I18N || { t: k => k, idioma: 'es', idiomas: [], set: () => {} };
  const T = (k, v) => I.t(k, v);

  const TEMAS = [
    { id:'escom',  clave:'tema.escom',  muestra:'#123f8f' },
    { id:'guinda', clave:'tema.guinda', muestra:'#6f1d46' },
  ];
  const K_TEMA = 'dwagua-tema', K_MODO = 'dwagua-modo';
  const leer = (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
  const guardar = (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} };

  let tema = leer(K_TEMA, 'escom');
  if (!TEMAS.some(t => t.id === tema)) tema = 'escom';
  let modo = leer(K_MODO, 'claro');           // auto | claro | oscuro

  const svg = d => '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" ' +
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
    'stroke-linejoin="round" aria-hidden="true">' + d + '</svg>';
  const ICONO = {
    claro:  svg('<circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4"/>'),
    oscuro: svg('<path d="M20.5 14.3A8.5 8.5 0 1 1 9.7 3.5a6.8 6.8 0 0 0 10.8 10.8z"/>'),
    auto:   svg('<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17" /><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor" stroke="none"/>'),
  };
  const CLAVE_MODO = { claro:'modo.claro', oscuro:'modo.oscuro', auto:'modo.auto' };

  const raiz = document.documentElement;
  /* avisar = false cuando sólo se refresca la barra tras cambiar de idioma:
     el tema no ha cambiado y no hay que hacer repintar a quien lo escucha. */
  function pintar(avisar) {
    raiz.setAttribute('data-tema', tema);
    if (modo === 'auto') raiz.removeAttribute('data-modo');
    else raiz.setAttribute('data-modo', modo);
    document.querySelectorAll('.tema-btn').forEach(b =>
      b.setAttribute('aria-pressed', String(b.dataset.tema === tema)));
    document.querySelectorAll('.idioma-btn').forEach(b =>
      b.setAttribute('aria-pressed', String(b.dataset.idioma === I.idioma)));
    const b = document.querySelector('.modo-btn');
    if (b) {
      b.innerHTML = ICONO[modo];
      b.title = T('modo.cambiar', { modo: T(CLAVE_MODO[modo]) });
      b.setAttribute('aria-label', b.title);
      b.dataset.modo = modo;
    }
    if (avisar !== false) {
      document.dispatchEvent(new CustomEvent('temacambiado', { detail:{ tema, modo } }));
    }
  }
  pintar();   // antes de renderizar, para que no parpadee

  const paginas = [
    ['index.html',    'nav.index'],
    ['mapa.html',     'nav.mapa'],
    ['grafo.html',    'nav.grafo'],
    ['vecindad.html', 'nav.vecindad'],
  ];
  const actual = (location.pathname.split('/').pop() || 'index.html').toLowerCase();

  function construirBarra() {
    const enlaces = paginas.map(([h, k]) =>
      `<a href="${h}"${h.toLowerCase() === actual ? ' aria-current="page"' : ''}>${T(k)}</a>`).join('');

    /* Un segmentado igual que el del tema: dos botones excluyentes con
       aria-pressed. El nombre accesible es la propia etiqueta visible
       ("ES"/"EN"); el atributo lang hace que se lea en su idioma. */
    const idiomas = I.idiomas.map(l =>
      `<button class="idioma-btn" type="button" data-idioma="${l.id}" lang="${l.id}"
         title="${l.nombre}">${l.etiqueta}</button>`).join('');
    const selectorIdioma = idiomas
      ? `<div class="segmentado" role="group" aria-label="${T('barra.idioma')}">${idiomas}</div>`
      : '';

    document.querySelectorAll('[data-barra]').forEach(el => {
      el.className = 'barra';
      el.innerHTML = `
      <div class="barra-in">
        <div class="marca">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 2.5c-3.6 4.4-6.5 8-6.5 11.4a6.5 6.5 0 0 0 13 0C18.5 10.5 15.6 6.9 12 2.5z"
                  fill="var(--acento-300)"/>
            <path d="M9.2 14.2a2.8 2.8 0 0 0 2.8 2.8" stroke="var(--marca-700)"
                  stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <span>${T('barra.marca')}
            <small>${T('barra.lema')}</small>
          </span>
        </div>
        <nav class="nav">${enlaces}<a href="/">Reportes ciudadanos</a></nav>
        <div class="temas">
          <div class="segmentado" role="group" aria-label="${T('barra.tema')}">
            ${TEMAS.map(t => `<button class="tema-btn" type="button" data-tema="${t.id}"
               title="${T(t.clave)}"><i style="background:${t.muestra}"></i>${T(t.clave)}</button>`).join('')}
          </div>
          ${selectorIdioma}
          <button class="modo-btn" type="button"></button>
        </div>
      </div>`;
    });

    document.querySelectorAll('.tema-btn').forEach(b =>
      b.addEventListener('click', () => { tema = b.dataset.tema; guardar(K_TEMA, tema); pintar(); }));
    document.querySelectorAll('.idioma-btn').forEach(b =>
      b.addEventListener('click', () => I.set(b.dataset.idioma)));
    const mb = document.querySelector('.modo-btn');
    if (mb) mb.addEventListener('click', () => {
      modo = modo === 'auto' ? 'claro' : modo === 'claro' ? 'oscuro' : 'auto';
      guardar(K_MODO, modo); pintar();
    });
  }

  function construirPie() {
    document.querySelectorAll('[data-pie]').forEach(el => {
      el.className = 'pie';
      el.innerHTML = `
      ${T('pie.datos')} <a href="https://datos.cdmx.gob.mx/dataset/consumo-agua" target="_blank" rel="noopener">SACMEX</a>,
      ${T('pie.portal')} &middot;
      ${T('pie.clima')} <a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo</a> (CC BY 4.0) &middot;
      ${T('pie.mapabase')} &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> (ODbL)<br>
      ${T('pie.artefacto')} <em>Territorial Information Retrieval from Heterogeneous Open Data through the
      Construction of a Data Warehouse for Water Management in Mexico City</em> &middot;
      <a href="https://github.com/gabrielhuav/Data_Warehouse_static" target="_blank" rel="noopener">${T('pie.repo')}</a>`;
    });
  }

  construirBarra();
  construirPie();

  pintar();   // otra vez: ahora la barra ya existe y el boton puede recibir su icono

  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { if (modo === 'auto') pintar(); });

  /* La barra y el pie se generan aquí, así que se rehacen enteros al
     cambiar de idioma; el tema y el modo se conservan tal como estaban. */
  document.addEventListener('idiomacambiado', () => {
    construirBarra();
    construirPie();
    pintar(false);
  });
})();
