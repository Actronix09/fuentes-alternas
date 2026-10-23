'use strict';
const $=s=>document.querySelector(s);
const numero=v=>v===null||v===undefined?'—':Number(v).toLocaleString('es-MX',{maximumFractionDigits:1});
const pesos=v=>v===null||v===undefined?'—':Number(v).toLocaleString('es-MX',{style:'currency',currency:'MXN',maximumFractionDigits:0});
const nodo=(tag,texto,clase)=>{const n=document.createElement(tag);if(texto!==undefined)n.textContent=texto;if(clase)n.className=clase;return n;};
let mapa=null, puntos=null;
if(window.L){mapa=L.map('mapa').setView([19.04,-100.04],11);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap'}).addTo(mapa);puntos=L.featureGroup().addTo(mapa);}
else $('#mapa').textContent='El mapa requiere descargar Leaflet. Los datos siguen disponibles en la tabla.';
async function api(ruta,params){const r=await fetch(ruta+(params?'?'+params:''));if(!r.ok)throw Error(`Error ${r.status} al consultar la base`);return r.json();}
async function cargar(){
  const boton=$('button');boton.disabled=true;$('#estado').textContent='Consultando los datos…';
  try{
    const params=new URLSearchParams(new FormData($('#filtros')));
    const [r,obras,bit]=await Promise.all([api('/api/srft/resumen',params),api('/api/srft/obras',params),api('/api/srft/bitacora')]);
    if($('select').options.length===1)for(const opcion of r.opciones){const o=nodo('option',opcion);o.value=opcion;$('select').append(o);}
    $('#indicadores').replaceChildren();
    for(const [titulo,valor,pie] of [['Obras oficiales',numero(r.obras),'Temascaltepec · ejercicio 2025'],['Presupuesto aprobado',pesos(r.aprobado),'Pesos mexicanos'],['Pagado al cierre',pesos(r.pagado),'Acumulado, no gasto del trimestre'],['Avance financiero',r.aprobado>0?numero(100*r.pagado/r.aprobado)+' %':'—','Pagado / aprobado']]){const c=nodo('article',undefined,'indicador');c.append(nodo('span',titulo),nodo('strong',valor),nodo('small',pie));$('#indicadores').append(c);}
    $('#sectores').replaceChildren();const max=Math.max(1,...r.clasificaciones.map(x=>Number(x.aprobado)));
    for(const s of r.clasificaciones){const c=nodo('div',undefined,'sector'),linea=nodo('div',undefined,'linea'),barra=nodo('div',undefined,'barra'),relleno=nodo('i');linea.append(nodo('span',`${s.clasificacion} · ${s.obras}`),nodo('strong',pesos(s.aprobado)));relleno.style.width=(100*s.aprobado/max)+'%';barra.append(relleno);c.append(linea,barra);$('#sectores').append(c);}
    $('#obras').replaceChildren();if(puntos)puntos.clearLayers();
    for(const o of obras){const tr=nodo('tr'),nombre=nodo('td'),enlace=nodo('a',o.folio);enlace.href='/api/srft/proyecto/'+encodeURIComponent(o.folio);enlace.target='_blank';enlace.rel='noopener';nombre.append(nodo('strong',o.nombre_obra),nodo('br'),enlace);const lugar=nodo('td',o.clasificacion);lugar.append(nodo('small',o.localidad||'Localidad sin dato válido'));const estado=nodo('td');estado.append(nodo('span',o.estatus,'etiqueta'));tr.append(nombre,lugar,nodo('td',pesos(o.aprobado)),nodo('td',pesos(o.pagado)),nodo('td',o.avance_fisico_pct===null?'Sin porcentaje único':numero(o.avance_fisico_pct)+' %'),estado);$('#obras').append(tr);
      if(puntos&&o.latitud!==null&&o.longitud!==null){const contenido=nodo('div');contenido.append(nodo('strong',o.nombre_obra),nodo('p',pesos(o.aprobado)));L.circleMarker([Number(o.latitud),Number(o.longitud)],{radius:6,color:'#225e46',fillColor:'#b8d98c',fillOpacity:.85,weight:2}).bindPopup(contenido).addTo(puntos);}}
    if(!obras.length){const tr=nodo('tr'),td=nodo('td','No hay obras para estos filtros.');td.colSpan=6;tr.append(td);$('#obras').append(tr);}
    if(puntos&&puntos.getLayers().length)mapa.fitBounds(puntos.getBounds().pad(.15),{maxZoom:13});
    $('#conteo').textContent=numero(obras.length)+' obras';$('#sin-coordenadas').textContent=`${numero(r.con_coordenadas)} obras con coordenadas válidas; ${numero(r.obras-r.con_coordenadas)} sin punto asignable.`;
    $('#modelo').textContent=`La base conserva ${r.modelo.dimensiones_originales} dimensiones originales. Última ejecución: ${r.etl?r.etl.mensaje:'Sin ejecución registrada'}.`;
    $('#bitacora').replaceChildren();for(const b of bit){const p=nodo('div',undefined,'paso');p.append(nodo('span',b.fase),nodo('span',b.paso),nodo('strong',numero(b.registros)));$('#bitacora').append(p);}
    $('#estado').textContent=`Conectado al backend original · ETL ${r.etl?r.etl.estado:'pendiente'} · Fuente oficial SHCP`;
  }catch(e){$('#estado').textContent=e.message;}finally{boton.disabled=false;}
}
$('#filtros').addEventListener('submit',e=>{e.preventDefault();cargar();});cargar();
