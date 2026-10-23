/* =====================================================================
   Sistema 2 · Atipicidad del consumo de agua frente a reportes ciudadanos
   El color sigue a la entidad en todo el tablero:
     tipos de reporte   Falta de agua = slot 1 · Fuga = slot 2 · Mala calidad = slot 3
     puntajes           A_g del paper = color del tipo elegido (énfasis) ·
                        A_g por manzana = gris · azar = línea fina
     mapa               clases de A_g con la rampa ordinal azul (4 clases)
   ===================================================================== */
'use strict';

const SLOT_TIPO = { 'Falta de agua': 0, Fuga: 1, 'Mala calidad': 2 };
const CLASES = ['A_g < 1', '1 – 2', '2 – 3', '≥ 3'];
let mapa;
let capaColonias;
let capaPuntos;
let ultimo = null;
let disponibilidad = [];

function filtrosActuales() {
  const f = new FormData(document.getElementById('filtros'));
  const [desde, hasta] = f.get('periodo').split(',');
  return { tipo: f.get('tipo'), desde, hasta, alcaldia: f.get('alcaldia') };
}

function colorTipo(t, tipo) { return t.serie[SLOT_TIPO[tipo] ?? 0]; }
function clase(valor) { return Math.min(3, Math.max(0, Math.floor(Number(valor) || 0))); }

/* ---------------- indicadores ---------------- */
function pintarResumen(r, f) {
  const t = Tema.leer();
  const ev = Object.fromEntries(r.evaluacion.map((e) => [e.puntaje, e]));
  const paper = ev['A_g del paper'] || {};
  const manzana = ev['A_g por manzana'] || {};
  const ubicados = (r.reportes.nombre || 0) + (r.reportes.manzana_cercana || 0);
  const total = ubicados + (r.reportes.sin_ubicar || 0);
  const hayEtiquetas = (paper.positivos || 0) > 0;
  document.getElementById('aviso').textContent = hayEtiquetas ? ''
    : `No hay reportes de «${f.tipo}» ubicados en ese periodo: no se puede evaluar el puntaje. ${textoDisponibilidad(f.tipo)}`;

  document.getElementById('kpis').replaceChildren(
    kpi('AUC del A_g del paper', hayEtiquetas ? num(paper.auc, 3) : '—',
      '0.5 = azar · 1 = ordena perfecto a las colonias positivas', { heroe: true, clave: colorTipo(t, f.tipo) }),
    kpi('AUC del A_g por manzana', hayEtiquetas ? num(manzana.auc, 3) : '—',
      'mismo cálculo con el consumo por manzana', { clave: t.tenue }),
    kpi('Precisión en las 47 más atípicas', hayEtiquetas ? pct(100 * paper.precision_47) : '—',
      hayEtiquetas ? `azar: ${pct(100 * paper.prevalencia)} · por manzana: ${pct(100 * manzana.precision_47)}` : ''),
    kpi('ρ de Spearman (paper)', hayEtiquetas ? num(paper.spearman, 3) : '—', 'puntaje contra reportes por manzana'),
    kpi(`Reportes de «${f.tipo}»`, num(total),
      total ? `${pct((100 * ubicados) / total)} ubicados en una colonia` : 'en el periodo elegido'),
    kpi('Colonias evaluadas', num(paper.colonias || r.consumo.colonias),
      `${num(r.consumo.consumo_m3)} m³ de consumo en el 1er semestre de 2019`),
  );

  document.getElementById('fuentes').replaceChildren(
    ...r.citas.map((c) => el('li', {}, el('strong', {}, `${c.papel} · ${c.codigo}. `), c.cita_apa,
      el('br'), el('code', {}, `Licencia: ${c.licencia}`))),
    ...r.recursos.map((x) => el('li', {}, el('strong', {}, 'Recurso descargado: '), `${x.nombre} · `,
      el('code', {}, x.url), ` · actualizado en el portal: ${soloFecha(x.ultima_modificacion)}`)),
  );
}

function textoDisponibilidad(tipo) {
  const anios = disponibilidad.filter((d) => d.reporte === tipo).map((d) => `${d.anio} (${num(d.reportes)})`);
  return anios.length ? `Hay reportes de «${tipo}» en: ${anios.join(', ')}.` : '';
}

/* ---------------- curva precisión–exhaustividad ---------------- */
function graficaPR(curvas, resumen, f) {
  const ev = Object.fromEntries(resumen.evaluacion.map((e) => [e.puntaje, e]));
  const prevalencia = ev['A_g del paper'] ? Number(ev['A_g del paper'].prevalencia) : null;
  const puntos = (lista) => lista.filter((p) => p.recall_k !== null)
    .map((p) => ({ x: Number(p.recall_k), y: Number(p.precision_k), k: p.k }));
  Graficas.dibujar('g-pr', (t) => {
    const acento = colorTipo(t, f.tipo);
    const linea = (label, data, color, ancho = 2) => ({
      label, data, showLine: true, borderColor: color, backgroundColor: color, claveColor: color,
      borderWidth: ancho, pointRadius: 0, pointHoverRadius: 5, pointHoverBorderWidth: 2,
      pointHoverBorderColor: t.superficie, pointHitRadius: 8, tension: 0,
    });
    const datasets = [
      linea('A_g del paper', puntos(curvas.paper), acento),
      linea('A_g por manzana', puntos(curvas.manzana), t.tenue),
    ];
    if (prevalencia !== null) {
      datasets.push({ ...linea('Azar (proporción de positivas)', [{ x: 0, y: prevalencia }, { x: 1, y: prevalencia }], t.base, 1),
        pointHoverRadius: 0, pointHitRadius: 0 });
    }
    return {
      type: 'scatter',
      data: { datasets },
      options: {
        interaction: { mode: 'nearest', intersect: false },
        plugins: {
          legend: {
            position: 'top', align: 'start',
            labels: {
              usePointStyle: true, pointStyle: 'line', boxWidth: 20,
              generateLabels: (chart) => Chart.defaults.plugins.legend.labels.generateLabels(chart).map((it) => {
                const c = chart.data.datasets[it.datasetIndex].claveColor;
                return { ...it, strokeStyle: c, fillStyle: c, lineWidth: 3 };
              }),
            },
          },
          tooltip: {
            filter: (item) => item.datasetIndex < 2,
            callbacks: {
              title: () => '',
              label: (c) => ` ${pct(100 * c.raw.y)} de precisión con ${num(c.raw.k)} colonias (exhaustividad ${pct(100 * c.raw.x)})   ${c.dataset.label}`,
            },
          },
        },
        scales: {
          x: { type: 'linear', min: 0, max: 1, title: { display: true, text: 'Exhaustividad (recall)', color: t.tenue },
               grid: { color: t.rejilla }, border: { color: t.base },
               ticks: { color: t.tenue, callback: (v) => `${Math.round(v * 100)} %` } },
          y: { min: 0, max: 1, title: { display: true, text: 'Precisión', color: t.tenue },
               grid: { color: t.rejilla }, border: { display: false },
               ticks: { color: t.tenue, callback: (v) => `${Math.round(v * 100)} %` } },
        },
      },
    };
  });
  const muestra = (lista) => lista.filter((p) => [10, 25, 47, 100, 200, 400, 800].includes(Number(p.k)));
  const paper = Object.fromEntries(muestra(curvas.paper).map((p) => [p.k, p]));
  const manzana = Object.fromEntries(muestra(curvas.manzana).map((p) => [p.k, p]));
  vistaTabla('g-pr', [
    { titulo: 'Colonias revisadas (k)', clave: 'k', num: true, formato: (v) => num(v) },
    { titulo: 'Precisión · paper', clave: 'pp', num: true, formato: (v) => pct(100 * v) },
    { titulo: 'Exhaustividad · paper', clave: 'rp', num: true, formato: (v) => pct(100 * v) },
    { titulo: 'Precisión · por manzana', clave: 'pm', num: true, formato: (v) => pct(100 * v) },
    { titulo: 'Exhaustividad · por manzana', clave: 'rm', num: true, formato: (v) => pct(100 * v) },
  ], Object.keys(paper).map((k) => ({
    k, pp: paper[k].precision_k, rp: paper[k].recall_k,
    pm: manzana[k] ? manzana[k].precision_k : null, rm: manzana[k] ? manzana[k].recall_k : null,
  })));
}

/* ---------------- clases de puntaje ---------------- */
function graficaClases(filas, resumen, f) {
  const valor = (puntaje, c) => {
    const fila = filas.find((x) => x.puntaje === puntaje && x.clase === c);
    return fila ? fila.pct_cuartil_superior : null;
  };
  const ev = resumen.evaluacion.find((e) => e.puntaje === 'A_g del paper');
  const azar = ev && ev.prevalencia !== null ? 100 * ev.prevalencia : null;
  Graficas.dibujar('g-clases', (t) => {
    const c = configBarras(t, CLASES, [
      { nombre: 'A_g del paper', datos: [0, 1, 2, 3].map((k) => valor('paper', k)), slot: SLOT_TIPO[f.tipo] },
      { nombre: 'A_g por manzana', datos: [0, 1, 2, 3].map((k) => valor('manzana', k)), slot: 0 },
    ], { formato: (v) => pct(v), ejes: { y: { max: 100, ticks: { color: t.tenue, callback: (v) => `${v} %` } } } });
    // La segunda serie es el contraste (gris), no una entidad nueva
    c.data.datasets[1].backgroundColor = t.tenue;
    c.data.datasets[1].hoverBackgroundColor = t.tenue;
    c.data.datasets[1].claveColor = t.tenue;
    if (azar !== null) {
      c.data.datasets.push({
        type: 'line', label: 'Azar', data: CLASES.map(() => azar), borderColor: t.base, borderWidth: 1,
        pointRadius: 0, pointHitRadius: 0, claveColor: t.base,
      });
    }
    return c;
  });
  vistaTabla('g-clases', [
    { titulo: 'Puntaje', clave: 'puntaje', formato: (v) => (v === 'paper' ? 'A_g del paper' : 'A_g por manzana') },
    { titulo: 'Clase', clave: 'clase', formato: (v) => CLASES[v] },
    { titulo: 'Colonias', clave: 'colonias', num: true, formato: (v) => num(v) },
    { titulo: '% en cuartil superior', clave: 'pct_cuartil_superior', num: true, formato: (v) => pct(v) },
    { titulo: 'Reportes por manzana', clave: 'densidad_media', num: true, formato: (v) => num(v, 2) },
  ], filas);
}

/* ---------------- serie mensual ---------------- */
function graficaSerie(filas) {
  const meses = [...new Set(filas.map((x) => x.mes))].sort();
  const serie = (tipo) => meses.map((m) => {
    const fila = filas.find((x) => x.mes === m && x.reporte === tipo);
    return fila ? fila.reportes : 0;
  });
  Graficas.dibujar('g-serie', (t) => configLineas(t, meses.map((m) => m.slice(0, 7)),
    Object.keys(SLOT_TIPO).map((tipo) => ({ nombre: tipo, datos: serie(tipo), slot: SLOT_TIPO[tipo] }))));
  vistaTabla('g-serie', [
    { titulo: 'Mes', clave: 'mes', formato: (v) => v.slice(0, 7) },
    ...Object.keys(SLOT_TIPO).map((tipo) => ({ titulo: tipo, clave: tipo, num: true, formato: (v) => num(v) })),
  ], meses.map((m, i) => Object.fromEntries([['mes', m], ...Object.keys(SLOT_TIPO).map((tp) => [tp, serie(tp)[i]])])));
}

/* ---------------- mapa ---------------- */
function iniciarMapa() {
  mapa = crearMapa('mapa', [19.36, -99.13], 11);
  capaColonias = L.layerGroup().addTo(mapa);
  capaPuntos = L.layerGroup();
  document.querySelectorAll('input[name=color]').forEach((r) => r.addEventListener('change', () => ultimo && pintarMapa()));
  document.getElementById('ver-puntos').addEventListener('change', async (ev) => {
    if (ev.target.checked) {
      await cargarPuntos();
      capaPuntos.addTo(mapa);
    } else {
      mapa.removeLayer(capaPuntos);
    }
  });
}

function pintarEscala() {
  const t = Tema.leer();
  const barra = el('span', { class: 'barra' }, ...t.ord.map((c) => el('span', { style: `background:${c}` })));
  document.getElementById('escala').replaceChildren(el('span', {}, 'Menos atípica'), barra, el('span', {}, 'Más atípica'),
    el('span', {}, `· clases: ${CLASES.join(' · ')}`));
}

function pintarMapa() {
  const t = Tema.leer();
  const campo = document.querySelector('input[name=color]:checked').value;
  capaColonias.clearLayers();
  const filas = ultimo.colonias.filter((c) => c.latitud !== null);
  for (const c of [...filas].sort((a, b) => a[campo] - b[campo])) {
    const radio = Math.min(14, Math.max(4, 3 + Math.sqrt(Number(c.densidad) || 0) * 2.2));
    L.circleMarker([c.latitud, c.longitud], {
      radius: radio, color: t.superficie, weight: 2, fillColor: t.ord[clase(c[campo])], fillOpacity: 0.9,
    }).bindPopup(popup(c.colonia, [
      ['Alcaldía', c.alcaldia],
      ['Consumo 1er sem. 2019', `${num(c.consumo_m3)} m³ (${num(c.manzanas)} manzanas)`],
      ['A_g del paper', `${num(c.a_g, 2)} (z = ${num(c.z, 2)})`],
      ['A_g por manzana', `${num(c.a_g_norm, 2)} (z = ${num(c.z_norm, 2)})`],
      ['Reportes', `${num(c.reportes)} · ${num(c.densidad, 2)} por manzana`],
      ['Cuartil superior de reportes', c.positivo ? 'sí' : 'no'],
    ])).addTo(capaColonias);
  }
  document.getElementById('nota-mapa').textContent = `${num(filas.length)} colonias`;
}

async function cargarPuntos() {
  const t = Tema.leer();
  const f = filtrosActuales();
  const puntos = await api('/api/puntos', f);
  capaPuntos.clearLayers();
  for (const p of puntos) {
    L.circleMarker([p.latitud, p.longitud], {
      radius: 3, stroke: false, fillColor: colorTipo(t, f.tipo), fillOpacity: 0.55,
    }).bindPopup(popup(f.tipo, [['Fecha', soloFecha(p.fecha)], ['Colonia', p.colonia || 'sin ubicar'],
      ['Ubicado por', p.metodo_ubicacion === 'nombre' ? 'nombre de la colonia' : 'manzana más cercana']]))
      .addTo(capaPuntos);
  }
}

/* ---------------- tablas ---------------- */
function tablas(colonias, alcaldias, ubicacion, bit) {
  pintarTabla(document.getElementById('t-top'), [
    { titulo: '#', valor: (f) => String(colonias.indexOf(f) + 1), num: true },
    { titulo: 'Alcaldía', clave: 'alcaldia' },
    { titulo: 'Colonia', clave: 'colonia' },
    { titulo: 'Consumo (m³)', clave: 'consumo_m3', num: true, formato: (v) => num(v) },
    { titulo: 'z', clave: 'z', num: true, formato: (v) => num(v, 2) },
    { titulo: 'A_g', clave: 'a_g', num: true, formato: (v) => num(v, 2) },
    { titulo: 'A_g por manzana', clave: 'a_g_norm', num: true, formato: (v) => num(v, 2) },
    { titulo: 'Reportes', clave: 'reportes', num: true, formato: (v) => num(v) },
    { titulo: 'Por manzana', clave: 'densidad', num: true, formato: (v) => num(v, 2) },
    { titulo: 'Cuartil superior', clave: 'positivo', formato: (v) => (v ? 'sí' : 'no') },
  ], colonias.slice(0, 47));
  pintarTabla(document.getElementById('t-alcaldias'), [
    { titulo: 'Alcaldía', clave: 'alcaldia' },
    { titulo: 'Colonias', clave: 'colonias', num: true, formato: (v) => num(v) },
    { titulo: 'Consumo (m³)', clave: 'consumo_m3', num: true, formato: (v) => num(v) },
    { titulo: 'Reportes', clave: 'reportes', num: true, formato: (v) => num(v) },
    { titulo: 'Por manzana', clave: 'densidad_media', num: true, formato: (v) => num(v, 2) },
    { titulo: 'ρ paper', clave: 'spearman_paper', num: true, formato: (v) => num(v, 2) },
    { titulo: 'ρ por manzana', clave: 'spearman_manzana', num: true, formato: (v) => num(v, 2) },
  ], alcaldias);
  pintarTabla(document.getElementById('t-ubicacion'), [
    { titulo: 'Recurso', clave: 'recurso' },
    { titulo: 'Método', clave: 'metodo' },
    { titulo: 'Reportes', clave: 'reportes', num: true, formato: (v) => num(v) },
    { titulo: '%', clave: 'pct', num: true, formato: (v) => pct(v) },
    { titulo: 'Distancia media', clave: 'distancia_media_m', num: true, formato: (v) => (v == null ? '—' : `${num(v)} m`) },
  ], ubicacion);
  pintarTabla(document.getElementById('t-bitacora'), [
    { titulo: 'Fase', clave: 'fase' },
    { titulo: 'Paso', clave: 'paso' },
    { titulo: 'Registros', clave: 'registros', num: true, formato: (v) => num(v) },
    { titulo: 'Detalle', clave: 'detalle' },
  ], bit.pasos);
}

/* ---------------- orquestación ---------------- */
async function cargarTodo() {
  const f = filtrosActuales();
  await conCarga(async () => {
    const [res, curvas, clases, serie, colonias, porAlcaldia, ubicacion, bit] = await Promise.all([
      api('/api/resumen', f), api('/api/curva_pr', f), api('/api/clases', f), api('/api/serie_mensual', f),
      api('/api/colonias', f), api('/api/alcaldias', f), api('/api/ubicacion'), api('/api/bitacora'),
    ]);
    ultimo = { res, colonias, f };
    pintarResumen(res, f);
    graficaPR(curvas, res, f);
    graficaClases(clases, res, f);
    graficaSerie(serie);
    pintarMapa();
    pintarEscala();
    tablas(colonias, porAlcaldia, ubicacion, bit);
    document.getElementById('disponibilidad').textContent =
      `Los filtros acotan todo el tablero. ${textoDisponibilidad(f.tipo)}`;
    if (document.getElementById('ver-puntos').checked) await cargarPuntos();
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  configurarChart();
  iniciarMapa();
  alCambiarTema(() => {
    if (!ultimo) return;
    pintarResumen(ultimo.res, ultimo.f);
    pintarMapa();
    pintarEscala();
  });
  try {
    const original = await api('/api/original');
    document.getElementById('integracion-original').textContent =
      `${num(original.consumo_original)} registros originales de consumo · ` +
      `${num(original.clima_original)} días de clima · ${num(original.reportes_integrados)} reportes integrados. ` +
      `${num(original.sin_colonia)} reportes conservados sin colonia asignable.`;
    const op = await api('/api/opciones');
    disponibilidad = op.disponibilidad;
    const sel = document.querySelector('select[name=alcaldia]');
    for (const a of op.alcaldias) sel.append(el('option', { value: a }, a));
  } catch (e) {
    document.getElementById('aviso').textContent = `No se pudieron cargar las opciones: ${e.message}`;
  }
  document.getElementById('filtros').addEventListener('submit', (ev) => {
    ev.preventDefault();
    cargarTodo();
  });
  cargarTodo();
});
