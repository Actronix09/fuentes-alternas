/* =====================================================================
   Utilidades compartidas por las tres páginas:
   - lectura de la paleta desde las variables CSS (claro / oscuro)
   - llamadas a la API, formato de números y fechas
   - tablas construidas con textContent (los textos vienen de datos externos)
   - gráficas Chart.js con las especificaciones de marca: barras ≤ 24 px con
     extremo redondeado, líneas de 2 px, rejilla fina, tooltip con claves de
     línea y retícula vertical en series de tiempo
   ===================================================================== */
'use strict';

const Tema = {
  leer() {
    const s = getComputedStyle(document.documentElement);
    const v = (n) => s.getPropertyValue(n).trim();
    return {
      superficie: v('--surface-1'), texto: v('--text-primary'), texto2: v('--text-secondary'),
      tenue: v('--text-muted'), rejilla: v('--grid'), base: v('--baseline'),
      serie: [v('--series-1'), v('--series-2'), v('--series-3')],
      ord: [v('--ord-1'), v('--ord-2'), v('--ord-3'), v('--ord-4')],
      estado: {
        good: v('--status-good'), warning: v('--status-warning'),
        serious: v('--status-serious'), critical: v('--status-critical'),
      },
    };
  },
};

/* ---------- formato ---------- */
function num(v, dec = 0) {
  if (v === null || v === undefined || v === '' || Number.isNaN(Number(v))) return '—';
  return Number(v).toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
function compacto(v) {
  if (v === null || v === undefined) return '—';
  return Number(v).toLocaleString('es-MX', { notation: 'compact', maximumFractionDigits: 1 });
}
function pesos(v) {
  if (v === null || v === undefined) return '—';
  return Number(v).toLocaleString('es-MX', { style: 'currency', currency: 'MXN', maximumFractionDigits: 0 });
}
function pct(v, dec = 1) { return v === null || v === undefined ? '—' : `${num(v, dec)} %`; }
function fechaHora(iso) {
  if (!iso) return '—';
  return iso.replace('T', ' ').replace(/(\.\d+)?(\+00:00|Z)$/, ' UTC');
}
function soloFecha(iso) { return iso ? String(iso).slice(0, 10) : '—'; }

/* ---------- API ---------- */
async function api(ruta, params = {}) {
  const url = new URL(ruta, window.location.origin);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, v);
  }
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} al consultar ${ruta}`);
  return r.json();
}

/* ---------- DOM seguro ---------- */
function el(etiqueta, props = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') nodo.className = v;
    else if (k === 'dataset') Object.assign(nodo.dataset, v);
    else if (k === 'style') nodo.style.cssText = v;
    else nodo.setAttribute(k, v);
  }
  for (const h of hijos) nodo.append(h instanceof Node ? h : document.createTextNode(h ?? ''));
  return nodo;
}

function pintarTabla(tabla, columnas, filas, vacio = 'Sin datos para los filtros elegidos') {
  const cabeza = el('tr', {}, ...columnas.map((c) => el('th', c.num ? { class: 'num' } : {}, c.titulo)));
  const cuerpo = el('tbody');
  for (const f of filas) {
    const tr = el('tr');
    for (const c of columnas) {
      const valor = c.valor ? c.valor(f) : f[c.clave];
      const td = el('td', c.num ? { class: 'num' } : {});
      if (valor instanceof Node) td.append(valor);
      else td.textContent = c.formato ? c.formato(valor, f) : (valor ?? '—');
      tr.append(td);
    }
    cuerpo.append(tr);
  }
  if (!filas.length) cuerpo.append(el('tr', {}, el('td', { colspan: String(columnas.length) }, vacio)));
  tabla.replaceChildren(el('thead', {}, cabeza), cuerpo);
}

/* Gemela accesible de cada gráfica: la misma información como tabla */
function vistaTabla(idCanvas, columnas, filas) {
  const panel = document.getElementById(idCanvas).closest('.panel');
  let det = panel.querySelector('details.vista-tabla');
  if (!det) {
    det = el('details', { class: 'vista-tabla' }, el('summary', {}, 'Ver como tabla'),
             el('div', { class: 'tabla-scroll' }, el('table')));
    panel.append(det);
  }
  pintarTabla(det.querySelector('table'), columnas, filas);
}

/* Insignia de estado: color + ícono + texto (nunca solo color) */
function insignia(nivel, texto) {
  const iconos = { good: '✓', warning: '…', serious: '!', critical: '!' };
  return el('span', { class: `estado ${nivel}`, dataset: { icono: iconos[nivel] || '•' } }, texto);
}

function kpi(etiqueta, valor, nota, opciones = {}) {
  const tarjeta = el('div', { class: `kpi${opciones.heroe ? ' heroe' : ''}` });
  const titulo = el('div', { class: 'kpi-etiqueta' });
  if (opciones.clave) titulo.append(el('span', { class: 'clave', style: `background:${opciones.clave}` }));
  titulo.append(etiqueta);
  tarjeta.append(titulo, el('div', { class: 'kpi-valor' }, valor));
  if (nota) tarjeta.append(el('div', { class: 'kpi-nota' }, nota));
  return tarjeta;
}

/* ---------- Chart.js ---------- */
const reticula = {
  id: 'reticula',
  defaults: { activo: false, color: '#c3c2b7' },
  afterDatasetsDraw(chart, _args, opts) {
    if (!opts.activo) return;
    const activos = chart.tooltip && chart.tooltip.getActiveElements();
    if (!activos || !activos.length) return;
    const x = Math.round(activos[0].element.x) + 0.5;
    const { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.strokeStyle = opts.color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.restore();
  },
};

Chart.register(reticula);

function configurarChart() {
  const t = Tema.leer();
  const d = Chart.defaults;
  d.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
  d.font.size = 12;
  d.color = t.texto2;
  d.borderColor = t.rejilla;
  d.maintainAspectRatio = false;
  d.animation = false;
  const tt = d.plugins.tooltip;
  tt.backgroundColor = t.superficie;
  tt.titleColor = t.texto2;
  tt.bodyColor = t.texto;
  tt.footerColor = t.tenue;
  tt.borderColor = t.base;
  tt.borderWidth = 1;
  tt.padding = 10;
  tt.boxPadding = 6;
  tt.usePointStyle = true;
  tt.bodyFont = { weight: '600' };
  tt.callbacks.labelPointStyle = () => ({ pointStyle: 'line', rotation: 0 });
  tt.callbacks.labelColor = (ctx) => {
    const c = ctx.dataset.claveColor || ctx.dataset.borderColor;
    return { borderColor: c, backgroundColor: c, borderWidth: 3 };
  };
  d.plugins.legend.labels.color = t.texto2;
}

function ejes(t, { x = {}, y = {} } = {}) {
  return {
    x: {
      grid: { display: false },
      border: { color: t.base },
      ticks: { color: t.tenue, maxRotation: 0, autoSkipPadding: 14 },
      ...x,
    },
    y: {
      beginAtZero: true,
      grid: { color: t.rejilla, lineWidth: 1 },
      border: { display: false },
      ticks: { color: t.tenue, callback: (v) => compacto(v) },
      ...y,
    },
  };
}

/* Varias series en el tiempo. series: [{nombre, datos, slot | color, puntos}]
   (color permite la forma de énfasis: una serie en su tono y la otra en gris) */
function configLineas(t, etiquetas, series, extra = {}) {
  return {
    type: 'line',
    data: {
      labels: etiquetas,
      datasets: series.map((s) => ({
        label: s.nombre, data: s.datos,
        borderColor: s.color || t.serie[s.slot], backgroundColor: s.color || t.serie[s.slot],
        claveColor: s.color || t.serie[s.slot],
        borderWidth: 2, borderJoinStyle: 'round', borderCapStyle: 'round',
        pointRadius: s.puntos ? 4 : 0, pointBorderWidth: 2, pointBorderColor: t.superficie,
        pointHoverRadius: 5, pointHoverBorderWidth: 2, pointHoverBorderColor: t.superficie,
        pointHitRadius: 12, tension: 0, spanGaps: true,
      })),
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      plugins: {
        reticula: { activo: true, color: t.base },
        legend: {
          display: series.length > 1, position: 'top', align: 'start',
          labels: {
            usePointStyle: true, pointStyle: 'line', boxWidth: 20,
            // Con usePointStyle Chart.js toma el color del borde del punto (el anillo
            // de superficie); la clave de la leyenda debe llevar el color de la serie.
            generateLabels: (chart) => Chart.defaults.plugins.legend.labels.generateLabels(chart)
              .map((it) => {
                const c = chart.data.datasets[it.datasetIndex].claveColor;
                return { ...it, strokeStyle: c, fillStyle: c, lineWidth: 3 };
              }),
          },
        },
        tooltip: {
          callbacks: {
            label: (c) => ` ${extra.formato ? extra.formato(c.parsed.y) : num(c.parsed.y, extra.decimales ?? 0)}   ${c.dataset.label}`,
          },
        },
      },
      scales: ejes(t, extra.ejes),
    },
  };
}

/* Barras delgadas con extremo redondeado. series: [{nombre, datos, slot, colores?}] */
function configBarras(t, etiquetas, series, extra = {}) {
  const horizontal = !!extra.horizontal;
  const escalas = ejes(t, extra.ejes);
  if (horizontal) {
    escalas.x.grid = { color: t.rejilla, lineWidth: 1 };
    escalas.x.border = { display: false };
    escalas.x.ticks = { color: t.tenue, callback: (v) => compacto(v) };
    escalas.x.beginAtZero = true;
    escalas.y.grid = { display: false };
    escalas.y.border = { color: t.base };
    escalas.y.ticks = { color: t.texto2, autoSkip: false };
    delete escalas.y.beginAtZero;
  }
  return {
    type: 'bar',
    data: {
      labels: etiquetas,
      datasets: series.map((s) => {
        const color = t.serie[s.slot ?? 0];
        return {
          label: s.nombre, data: s.datos,
          backgroundColor: s.colores || color, claveColor: color,
          hoverBackgroundColor: s.colores || `${color}cc`,
          borderRadius: 4, borderSkipped: 'start', maxBarThickness: 24,
          barPercentage: extra.barPercentage ?? 0.85,
          categoryPercentage: extra.categoryPercentage ?? 0.8,
        };
      }),
    },
    options: {
      indexAxis: horizontal ? 'y' : 'x',
      interaction: { mode: 'index', intersect: false, axis: horizontal ? 'y' : 'x' },
      plugins: {
        legend: { display: series.length > 1, position: 'top', align: 'start' },
        tooltip: {
          callbacks: {
            label: (c) => {
              const v = horizontal ? c.parsed.x : c.parsed.y;
              return ` ${extra.formato ? extra.formato(v) : num(v, extra.decimales ?? 0)}   ${c.dataset.label}`;
            },
          },
        },
      },
      scales: escalas,
    },
  };
}

const Graficas = {
  instancias: new Map(),
  constructores: new Map(),
  dibujar(id, constructor) {
    this.constructores.set(id, constructor);
    this._crear(id);
  },
  _crear(id) {
    const previa = this.instancias.get(id);
    if (previa) previa.destroy();
    const config = this.constructores.get(id)(Tema.leer());
    this.instancias.set(id, new Chart(document.getElementById(id), config));
  },
  redibujarTodo() {
    configurarChart();
    for (const id of this.constructores.keys()) this._crear(id);
  },
};

/* ---------- Leaflet ---------- */
function crearMapa(id, centro, zoom) {
  // Lienzo con tolerancia de 8 px: el área de clic de cada punto mide al menos 24 px
  const mapa = L.map(id, { renderer: L.canvas({ tolerance: 8 }) }).setView(centro, zoom);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(mapa);
  return mapa;
}

/* Contenido de ventana emergente: filas [etiqueta, valor] como nodos de texto */
function popup(titulo, filas) {
  const caja = el('div', {}, el('strong', {}, titulo));
  for (const [k, v] of filas) {
    if (v === null || v === undefined || v === '') continue;
    caja.append(el('br'), el('span', { style: 'color:var(--text-secondary)' }, `${k}: `), String(v));
  }
  return caja;
}

/* ---------- arranque común ---------- */
function alCambiarTema(fn) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    Graficas.redibujarTodo();
    if (fn) fn();
  });
}

async function conCarga(fn) {
  const main = document.querySelector('main');
  main.classList.add('cargando');
  try {
    await fn();
  } catch (e) {
    console.error(e);
    const aviso = document.getElementById('aviso');
    if (aviso) aviso.textContent = `No se pudieron cargar los datos: ${e.message}`;
  } finally {
    main.classList.remove('cargando');
  }
}
