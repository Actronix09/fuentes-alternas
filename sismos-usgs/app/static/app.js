/* =====================================================================
   Sistema 1 · Validación cruzada SSN ↔ USGS ComCat
   El color sigue a la entidad en todo el tablero:
     slot 1 (azul)    = presente en ambas fuentes / pares
     slot 2 (naranja) = USGS
     slot 3 (aqua)    = SSN
   ===================================================================== */
'use strict';

const SLOT = { ambas: 0, solo_usgs: 1, solo_ssn: 2 };
let mapa;
const capas = {};
let ultimoEventos = null;
let ultimoResumen = null;

function filtrosActuales() {
  const f = new FormData(document.getElementById('filtros'));
  return {
    desde: f.get('desde'), hasta: f.get('hasta'), mag_min: f.get('mag_min'),
    variante: f.get('variante'), origen: f.get('origen'),
  };
}

/* ---------------- indicadores y fuentes ---------------- */
function pintarResumen(r) {
  const t = Tema.leer();
  const cuenta = Object.fromEntries(r.resultados.map((x) => [x.resultado, x.eventos]));
  const p = r.pares;
  const ambas = cuenta.ambas || 0;
  const totalSsn = ambas + (cuenta.solo_ssn || 0);
  const totalUsgs = ambas + (cuenta.solo_usgs || 0);
  document.getElementById('kpis').replaceChildren(
    kpi('Sismos en ambas fuentes', num(ambas),
      totalSsn ? `${pct((100 * ambas) / totalSsn)} de los sismos del SSN en el filtro` : 'sin sismos en el filtro',
      { heroe: true, clave: t.serie[0] }),
    kpi('Solo en el USGS', num(cuenta.solo_usgs || 0),
      totalUsgs ? `${pct((100 * (cuenta.solo_usgs || 0)) / totalUsgs)} del USGS no está en el DW` : '',
      { clave: t.serie[1] }),
    kpi('Solo en el SSN', num(cuenta.solo_ssn || 0), 'sin contraparte en ComCat', { clave: t.serie[2] }),
    kpi('Distancia mediana', p.pares ? `${num(p.distancia_mediana_km, 1)} km` : '—', 'entre los epicentros de cada par'),
    kpi('ΔM promedio (USGS − SSN)', p.pares ? num(p.delta_mag_media, 2) : '—',
      p.pares ? `desv. ${num(p.delta_mag_desv, 2)} · ${pct(p.pct_mag_dentro_0_3)} con |ΔM| ≤ 0.3` : ''),
    kpi('Diferencia de hora', p.pares ? `${num(p.delta_seg_abs_media, 1)} s` : '—', 'promedio absoluto entre fuentes'),
  );

  const periodo = Object.fromEntries(r.periodo.map((x) => [x.codigo, x]));
  document.getElementById('fuentes').replaceChildren(...r.fuentes.map((fu) => {
    const per = periodo[fu.codigo];
    return el('li', {},
      el('strong', {}, `${fu.codigo} · ${fu.nombre}. `),
      per ? `${num(per.eventos)} sismos, del ${soloFecha(per.desde)} al ${soloFecha(per.hasta)}. ` : '',
      el('br'), fu.cita_apa, el('br'), el('code', {}, `Licencia: ${fu.licencia}`));
  }));
}

/* ---------------- mapa ---------------- */
function radio(m) { return Math.min(16, Math.max(4, 2 + (Number(m) - 3.5) * 2.4)); }

function pintarPuntosLeyenda() {
  const t = Tema.leer();
  document.querySelectorAll('#leyenda-mapa .punto').forEach((p) => {
    p.style.background = t.serie[Number(p.dataset.slot)];
  });
}

function iniciarMapa() {
  mapa = crearMapa('mapa', [22.5, -101.5], 5);
  for (const k of Object.keys(SLOT)) capas[k] = L.layerGroup().addTo(mapa);
  document.querySelectorAll('#leyenda-mapa input').forEach((chk) => {
    chk.addEventListener('change', () => {
      if (chk.checked) capas[chk.value].addTo(mapa);
      else mapa.removeLayer(capas[chk.value]);
    });
  });
}

function origenSolucion(e) {
  const red = (x) => (x || '?').toUpperCase();
  const texto = `epicentro ${red(e.red_localizacion)}, magnitud ${red(e.red_magnitud)}`;
  return e.independiente === false ? `${texto} (aportada por el SSN)` : texto;
}

function pintarEventos(datos) {
  const t = Tema.leer();
  Object.values(capas).forEach((c) => c.clearLayers());
  // Del menor al mayor: los sismos grandes quedan encima
  for (const e of [...datos.eventos].reverse()) {
    const capa = capas[e.resultado];
    if (!capa) continue;
    const color = t.serie[SLOT[e.resultado]];
    const mag = e.mag_ssn ?? e.mag_usgs;
    const estilo = { radius: radio(mag), color: t.superficie, weight: 2, fillColor: color, fillOpacity: 0.9 };
    if (e.resultado === 'ambas') {
      L.polyline([[e.lat_ssn, e.lon_ssn], [e.lat_usgs, e.lon_usgs]],
        { color, weight: 2, opacity: 0.7, interactive: false }).addTo(capa);
      L.circleMarker([e.lat_ssn, e.lon_ssn], estilo).bindPopup(popup('Sismo en ambas fuentes', [
        ['Fecha', fechaHora(e.fecha)],
        ['Fecha en el DW del paper', e.fecha_corregida ? fechaHora(e.fecha_hora_dw) : null],
        ['M SSN', num(e.mag_ssn, 1)],
        ['M USGS', `${num(e.mag_usgs, 1)} ${e.tipo_magnitud || ''}`],
        ['ΔM (USGS − SSN)', num(e.delta_magnitud, 2)],
        ['Separación de epicentros', `${num(e.distancia_km, 1)} km`],
        ['Referencia SSN', e.referencia_ssn],
        ['Lugar USGS', e.lugar_usgs],
        ['Solución en ComCat', origenSolucion(e)],
        ['Id USGS', e.id_usgs],
      ])).addTo(capa);
    } else if (e.resultado === 'solo_usgs') {
      L.circleMarker([e.lat_usgs, e.lon_usgs], estilo).bindPopup(popup('Solo en el USGS', [
        ['Fecha', fechaHora(e.fecha)],
        ['Magnitud', `${num(e.mag_usgs, 1)} ${e.tipo_magnitud || ''}`],
        ['Profundidad', e.prof_usgs != null ? `${num(e.prof_usgs, 1)} km` : null],
        ['Lugar', e.lugar_usgs],
        ['Solución en ComCat', origenSolucion(e)],
        ['Id USGS', e.id_usgs],
      ])).addTo(capa);
    } else {
      L.circleMarker([e.lat_ssn, e.lon_ssn], estilo).bindPopup(popup('Solo en el SSN', [
        ['Fecha', fechaHora(e.fecha)],
        ['Fecha en el DW del paper', e.fecha_corregida ? fechaHora(e.fecha_hora_dw) : null],
        ['Magnitud', num(e.mag_ssn, 1)],
        ['Profundidad', e.prof_ssn != null ? `${num(e.prof_ssn, 1)} km` : null],
        ['Referencia', e.referencia_ssn],
      ])).addTo(capa);
    }
  }
  const total = Object.values(datos.total).reduce((a, b) => a + b, 0);
  document.getElementById('nota-mapa').textContent = total > datos.eventos.length
    ? `Se dibujan los ${num(datos.eventos.length)} sismos de mayor magnitud de ${num(total)} en el filtro.`
    : `${num(total)} sismos en el filtro.`;
}

/* ---------------- gráficas ---------------- */
function graficaSerie(filas) {
  const anios = filas.map((f) => f.anio);
  Graficas.dibujar('g-serie', (t) => configLineas(t, anios, [
    { nombre: 'Pares (en ambas)', datos: filas.map((f) => f.pares), slot: 0 },
    { nombre: 'USGS', datos: filas.map((f) => f.eventos_usgs), slot: 1 },
    { nombre: 'SSN', datos: filas.map((f) => f.eventos_ssn), slot: 2 },
  ]));
  vistaTabla('g-serie', [
    { titulo: 'Año', clave: 'anio' },
    { titulo: 'Pares', clave: 'pares', num: true, formato: (v) => num(v) },
    { titulo: 'USGS', clave: 'eventos_usgs', num: true, formato: (v) => num(v) },
    { titulo: 'SSN', clave: 'eventos_ssn', num: true, formato: (v) => num(v) },
  ], filas);
}

function graficaCobertura(filas) {
  Graficas.dibujar('g-cobertura', (t) => {
    const c = configBarras(t, filas.map((f) => f.etiqueta), [
      { nombre: '% del SSN confirmado por el USGS', datos: filas.map((f) => f.pct_ssn_confirmado_por_usgs), slot: 2 },
      { nombre: '% del USGS encontrado en el SSN', datos: filas.map((f) => f.pct_usgs_encontrado_en_ssn), slot: 1 },
    ], { formato: (v) => pct(v), ejes: { y: { max: 100, ticks: { color: t.tenue, callback: (v) => `${v} %` } } } });
    return c;
  });
  vistaTabla('g-cobertura', [
    { titulo: 'Rango', clave: 'etiqueta' },
    { titulo: 'Pares', clave: 'pares', num: true, formato: (v) => num(v) },
    { titulo: 'Solo SSN', clave: 'solo_ssn', num: true, formato: (v) => num(v) },
    { titulo: 'Solo USGS', clave: 'solo_usgs', num: true, formato: (v) => num(v) },
    { titulo: '% SSN confirmado', clave: 'pct_ssn_confirmado_por_usgs', num: true, formato: (v) => pct(v) },
    { titulo: '% USGS en SSN', clave: 'pct_usgs_encontrado_en_ssn', num: true, formato: (v) => pct(v) },
  ], filas);
}

function graficaHistograma(id, barras, unidad, decimales) {
  const etiqueta = (b) => num((b.desde + b.hasta) / 2, decimales);
  Graficas.dibujar(id, (t) => {
    const c = configBarras(t, barras.map(etiqueta), [{ nombre: 'Pares', datos: barras.map((b) => b.n), slot: 0 }],
      { categoryPercentage: 1, barPercentage: 0.86 });
    c.options.plugins.tooltip.callbacks.title = (items) => {
      const b = barras[items[0].dataIndex];
      return `${num(b.desde, decimales)} a ${num(b.hasta, decimales)} ${unidad}`;
    };
    c.options.scales.x.title = { display: true, text: unidad, color: t.tenue };
    return c;
  });
  vistaTabla(id, [
    { titulo: `Desde (${unidad})`, clave: 'desde', num: true, formato: (v) => num(v, decimales) },
    { titulo: `Hasta (${unidad})`, clave: 'hasta', num: true, formato: (v) => num(v, decimales) },
    { titulo: 'Pares', clave: 'n', num: true, formato: (v) => num(v) },
  ], barras);
}

function graficaDispersion(celdas) {
  const valores = celdas.flatMap((c) => [c.mag_ssn, c.mag_usgs]);
  const lo = Math.floor(Math.min(...valores, 4)) - 0.2;
  const hi = Math.ceil(Math.max(...valores, 6)) + 0.2;
  Graficas.dibujar('g-disp', (t) => ({
    type: 'bubble',
    data: {
      datasets: [
        {
          label: 'Pares', claveColor: t.serie[0],
          data: celdas.map((c) => ({ x: c.mag_ssn, y: c.mag_usgs, r: Math.min(20, Math.max(4, Math.sqrt(c.n) * 1.4)), n: c.n })),
          backgroundColor: `${t.serie[0]}b3`, borderColor: t.superficie, borderWidth: 2,
          hoverBackgroundColor: t.serie[0], hoverBorderColor: t.superficie, hitRadius: 8,
        },
        {
          type: 'line', label: 'Concordancia perfecta', data: [{ x: lo, y: lo }, { x: hi, y: hi }],
          borderColor: t.base, borderWidth: 1, pointRadius: 0, pointHitRadius: 0, claveColor: t.base,
        },
      ],
    },
    options: {
      interaction: { mode: 'nearest', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          filter: (item) => item.datasetIndex === 0,
          callbacks: {
            title: () => '',
            label: (c) => ` ${num(c.raw.n)} pares   SSN ${num(c.raw.x, 1)} · USGS ${num(c.raw.y, 1)}`,
          },
        },
      },
      scales: {
        x: { min: lo, max: hi, title: { display: true, text: 'Magnitud SSN', color: t.tenue },
             grid: { color: t.rejilla }, border: { color: t.base }, ticks: { color: t.tenue } },
        y: { min: lo, max: hi, title: { display: true, text: 'Magnitud USGS', color: t.tenue },
             grid: { color: t.rejilla }, border: { display: false }, ticks: { color: t.tenue } },
      },
    },
  }));
  vistaTabla('g-disp', [
    { titulo: 'M SSN', clave: 'mag_ssn', num: true, formato: (v) => num(v, 1) },
    { titulo: 'M USGS', clave: 'mag_usgs', num: true, formato: (v) => num(v, 1) },
    { titulo: 'Pares', clave: 'n', num: true, formato: (v) => num(v) },
  ], [...celdas].sort((a, b) => b.n - a.n));
}

/* ---------------- diagnóstico de fechas ---------------- */
function pintarDiagnostico(d) {
  const t = Tema.leer();
  const v = Object.fromEntries(d.variantes.map((x) => [x.variante, x]));
  const dw = v.dw_original || {};
  const cor = v.corregida || {};
  const ganancia = (cor.emparejados || 0) - (dw.emparejados || 0);
  document.getElementById('kpis-diagnostico').replaceChildren(
    kpi('Sismos del SSN con la fecha recorrida', num(d.corregidas.con_fecha_corregida),
      `${pct(d.corregidas.pct_corregidos)} de ${num(d.corregidas.sismos_ssn)} en el filtro`),
    kpi('Confirmados por el USGS con la fecha del DW', pct(dw.pct_emparejado),
      `${num(dw.emparejados)} de ${num(dw.sismos_ssn)} sismos`, { clave: t.tenue }),
    kpi('Confirmados con la fecha corregida', pct(cor.pct_emparejado),
      `${num(cor.emparejados)} sismos · ${ganancia >= 0 ? '+' : ''}${num(ganancia)} pares recuperados`, { clave: t.serie[0] }),
  );

  const horas = [...Array(24).keys()];
  const serie = (variante) => horas.map((h) => {
    const fila = d.horas.find((x) => x.variante === variante && x.hora_utc === h);
    return fila ? fila.pct_emparejado : null;
  });
  Graficas.dibujar('g-diagnostico', (tt) => configLineas(tt, horas.map((h) => `${String(h).padStart(2, '0')} h`), [
    { nombre: 'Con la fecha corregida', datos: serie('corregida'), slot: 0, puntos: true },
    { nombre: 'Tal como está en el DW del paper', datos: serie('dw_original'), color: tt.tenue, puntos: true },
  ], {
    formato: (x) => pct(x),
    ejes: {
      x: { title: { display: true, text: 'Hora UTC del sismo', color: tt.tenue } },
      y: { min: 0, max: 100, ticks: { color: tt.tenue, callback: (x) => `${x} %` },
           title: { display: true, text: '% del SSN que el USGS confirma', color: tt.tenue } },
    },
  }));
  vistaTabla('g-diagnostico', [
    { titulo: 'Hora UTC', clave: 'hora' },
    { titulo: '% con fecha corregida', clave: 'cor', num: true, formato: (x) => pct(x) },
    { titulo: '% con fecha del DW', clave: 'dw', num: true, formato: (x) => pct(x) },
  ], horas.map((h, i) => ({ hora: `${String(h).padStart(2, '0')}:00`, cor: serie('corregida')[i], dw: serie('dw_original')[i] })));

  pintarTabla(document.getElementById('t-diagnostico'), [
    { titulo: 'Fecha en el DW del paper', clave: 'fecha_hora_dw', formato: fechaHora },
    { titulo: 'Fecha UTC reconstruida', clave: 'fecha_hora_utc', formato: fechaHora },
    { titulo: 'Fecha en el USGS', clave: 'fecha_hora_usgs', formato: fechaHora },
    { titulo: 'M', clave: 'magnitud', num: true, formato: (x) => num(x, 1) },
    { titulo: 'Referencia SSN', clave: 'referencia' },
    { titulo: 'Lugar USGS', clave: 'lugar_usgs' },
  ], d.ejemplos);
}

/* ---------------- tablas ---------------- */
function tablas(conc, disc, soloUsgs, soloSsn, bit) {
  pintarTabla(document.getElementById('t-decada'), [
    { titulo: 'Década', clave: 'decada' },
    { titulo: 'Pares', clave: 'pares', num: true, formato: (v) => num(v) },
    { titulo: 'Distancia media', clave: 'distancia_media_km', num: true, formato: (v) => `${num(v, 1)} km` },
    { titulo: '|ΔM| medio', clave: 'delta_mag_abs_media', num: true, formato: (v) => num(v, 2) },
    { titulo: '|Δt| medio', clave: 'delta_seg_abs_media', num: true, formato: (v) => `${num(v, 1)} s` },
  ], conc.decada);
  pintarTabla(document.getElementById('t-origen'), [
    { titulo: 'Origen de la solución USGS', clave: 'origen' },
    { titulo: 'Pares', clave: 'pares', num: true, formato: (v) => num(v) },
    { titulo: 'Distancia mediana', clave: 'distancia_mediana_km', num: true, formato: (v) => `${num(v, 1)} km` },
    { titulo: '|ΔM| medio', clave: 'delta_mag_abs_media', num: true, formato: (v) => num(v, 2) },
    { titulo: 'Magnitud idéntica', clave: 'pct_mag_identica', num: true, formato: (v) => pct(v) },
    { titulo: '|Δt| medio', clave: 'delta_seg_abs_media', num: true, formato: (v) => `${num(v, 1)} s` },
  ], conc.origen);
  pintarTabla(document.getElementById('t-tipo'), [
    { titulo: 'Escala USGS', clave: 'tipo_mag_usgs' },
    { titulo: 'Pares', clave: 'pares', num: true, formato: (v) => num(v) },
    { titulo: 'ΔM medio', clave: 'delta_mag_media', num: true, formato: (v) => num(v, 2) },
    { titulo: 'Desv.', clave: 'delta_mag_desv', num: true, formato: (v) => num(v, 2) },
    { titulo: 'Mediana', clave: 'delta_mag_mediana', num: true, formato: (v) => num(v, 2) },
  ], conc.tipo);
  pintarTabla(document.getElementById('t-estado'), [
    { titulo: 'Estado', clave: 'estado' },
    { titulo: 'Sismos SSN', clave: 'sismos_ssn', num: true, formato: (v) => num(v) },
    { titulo: 'Confirmados', clave: 'confirmados_usgs', num: true, formato: (v) => num(v) },
    { titulo: '% confirmado', clave: 'pct_confirmado', num: true, formato: (v) => pct(v) },
    { titulo: 'Distancia media', clave: 'distancia_media_km', num: true, formato: (v) => (v == null ? '—' : `${num(v, 1)} km`) },
  ], conc.estado);
  pintarTabla(document.getElementById('t-discrepancias'), [
    { titulo: 'Fecha (UTC)', clave: 'fecha_hora_ssn', formato: fechaHora },
    { titulo: 'M SSN', clave: 'mag_ssn', num: true, formato: (v) => num(v, 1) },
    { titulo: 'M USGS', clave: 'mag_usgs', num: true, formato: (v) => num(v, 1) },
    { titulo: 'Escala', clave: 'tipo_mag_usgs' },
    { titulo: 'ΔM', clave: 'delta_magnitud', num: true, formato: (v) => num(v, 2) },
    { titulo: 'Separación', clave: 'distancia_km', num: true, formato: (v) => `${num(v, 1)} km` },
    { titulo: 'Referencia SSN', clave: 'referencia_ssn' },
    { titulo: 'Lugar USGS', clave: 'lugar_usgs' },
  ], disc);
  pintarTabla(document.getElementById('t-solo-usgs'), [
    { titulo: 'Fecha (UTC)', clave: 'fecha_hora_utc', formato: fechaHora },
    { titulo: 'M', clave: 'magnitud', num: true, formato: (v) => num(v, 1) },
    { titulo: 'Escala', clave: 'tipo_magnitud' },
    { titulo: 'Prof.', clave: 'profundidad_km', num: true, formato: (v) => (v == null ? '—' : `${num(v, 0)} km`) },
    { titulo: 'Lugar', clave: 'lugar' },
    { titulo: 'Id USGS', clave: 'id_usgs' },
  ], soloUsgs);
  pintarTabla(document.getElementById('t-solo-ssn'), [
    { titulo: 'Fecha (UTC)', clave: 'fecha_hora_utc', formato: fechaHora },
    { titulo: 'M', clave: 'magnitud', num: true, formato: (v) => num(v, 1) },
    { titulo: 'Prof.', clave: 'profundidad_km', num: true, formato: (v) => (v == null ? '—' : `${num(v, 0)} km`) },
    { titulo: 'Referencia', clave: 'referencia' },
    { titulo: 'Estado', clave: 'estado' },
  ], soloSsn);
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
    const [res, diag, serie, cob, dmag, dist, disp, eventos, conc, disc, soloUsgs, soloSsn, bit] = await Promise.all([
      api('/api/resumen', f), api('/api/diagnostico', f), api('/api/serie', f), api('/api/cobertura', f),
      api('/api/histograma/delta_magnitud', f), api('/api/histograma/distancia_km', f),
      api('/api/dispersion', f), api('/api/eventos', f), api('/api/concordancia', f),
      api('/api/discrepancias', f), api('/api/solo/usgs', f), api('/api/solo/ssn', f), api('/api/bitacora'),
    ]);
    document.getElementById('aviso').textContent = '';
    ultimoResumen = res;
    ultimoEventos = eventos;
    pintarResumen(res);
    pintarDiagnostico(diag);
    pintarEventos(eventos);
    graficaSerie(serie);
    graficaCobertura(cob);
    graficaHistograma('g-dmag', dmag, 'ΔM', 2);
    graficaHistograma('g-dist', dist, 'km', 0);
    graficaDispersion(disp);
    tablas(conc, disc, soloUsgs, soloSsn, bit);
  });
}

async function pintarIntegracion() {
  try {
    const o = await api('/api/original');
    document.getElementById('integracion-original').textContent =
      `${num(o.sismos_original)} sismos, ${num(o.impacto_original)} hechos de impacto, ` +
      `${num(o.zonas_original)} zonas y ${num(o.economia_original)} registros económicos originales. ` +
      `${num(o.sismos_cruzados)} sismos del SSN cruzados con ComCat: ${num(o.confirmados_usgs)} confirmados ` +
      `(${num(o.confirmados_independientes)} por redes independientes del SSN).`;
    document.getElementById('enlace-original').href = o.url_original + '/';
  } catch (e) {
    document.getElementById('integracion-original').textContent = 'No se pudo consultar el DW original: ' + e.message;
  }
}

document.addEventListener('DOMContentLoaded', () => {
  configurarChart();
  pintarIntegracion();
  iniciarMapa();
  pintarPuntosLeyenda();
  alCambiarTema(() => {
    pintarPuntosLeyenda();
    if (ultimoEventos) pintarEventos(ultimoEventos);
    if (ultimoResumen) pintarResumen(ultimoResumen);
  });
  document.getElementById('filtros').addEventListener('submit', (ev) => {
    ev.preventDefault();
    cargarTodo();
  });
  cargarTodo();
});
