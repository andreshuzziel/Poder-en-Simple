// Tests de funcionamiento del calendario de votaciones (calendario_votaciones.html)
const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');

const html = fs.readFileSync('/home/user/calendario_votaciones.html', 'utf8');
const errs = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => { if(!/scrollTo\(\) method/.test(e.message)) errs.push('jsdomError: ' + e.message); });
vc.on('error', (...a) => errs.push('console.error: ' + a.join(' ')));

const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'https://localhost/calendario' });
const { window } = dom;
const doc = window.document;
const $ = s => doc.querySelector(s);
const $$ = s => [...doc.querySelectorAll(s)];
let pass = 0, fail = 0;
const t = (name, cond, extra='') => { if (cond) { pass++; console.log('  ✔', name); } else { fail++; console.log('  ✘', name, extra); } };

setTimeout(() => {
const D = JSON.parse(html.match(/const DATA = (\{.*\});/)[1]);
console.log('== 1. carga sin errores ==');
t('sin errores js en load', errs.length === 0, JSON.stringify(errs.slice(0,3)));
t('DATA inyectada', html.includes('const DATA = {'));
t('badges del hero con totales', $('#hero-badges').textContent.includes(String(D.votaciones.length)));
t('KPIs del año (4)', $$('#kpis-anio .kpi').length === 4);
t('155 diputad@s en el padrón', Object.keys(D.diputados).length === 155);

console.log('== 2. calendario ==');
const meses = $$('#mes-nav button[data-m]').length;
t('navegador de meses pintado', meses >= 8, 'meses=' + meses);
// los días pintados deben calzar con los datos del mes visible
const mesOn = $('#mes-nav button.on').dataset.m;
const esperados = new Set(D.votaciones.filter(v => v.fecha.startsWith(mesOn)).map(v => v.fecha)).size;
const diasCon = $$('#cal .dia.con').length;
t('días con votaciones calzan con los datos', diasCon === esperados, `pintados=${diasCon} esperados=${esperados}`);

// elegir una votación objetivo: ley con voto nominal y votos en contra
const target = D.votaciones.find(v => v.nominal && v.no > 0 && v.si > 0 && v.tipo === 'Proyecto de Ley');
t('hay votación objetivo con nominal', !!target);
$('#mes-nav button[data-m="' + target.fecha.slice(0,7) + '"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
const celda = $('#cal .dia.con[data-f="' + target.fecha + '"]');
t('día objetivo existe en el calendario', !!celda, target.fecha);
celda.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
t('clic en día abre la sección del día', $('#sec-dia').style.display !== 'none');
const items = $$('#dia-lista .voto-item').length;
t('lista del día tiene votaciones', items >= 1, 'n=' + items);

console.log('== 3. ficha completa de la ley ==');
$('#dia-lista .voto-item[data-id="' + target.id + '"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
t('ficha abre (otra vista)', $('#vista-detalle').style.display !== 'none' && $('#vista-calendario').style.display === 'none');
t('ficha muestra título del proyecto', $('#det-contenido').textContent.length > 200);
t('ficha explica de qué trata el proyecto', $('#det-contenido').textContent.includes('¿De qué trata este proyecto?'));
const oficial = $('#det-contenido .btn-oficial:not(.btn-ficha)');
t('ficha tiene enlace oficial del Congreso', !!oficial && /camara\.cl\/legislacion\/proyectosdeley\/tramitacion\.aspx\?prmID=\d+/.test(oficial.getAttribute('href')), oficial ? oficial.getAttribute('href') : 'sin botón');
t('ficha indica qué se está votando', $('#det-contenido').textContent.includes('¿Qué se está votando exactamente aquí?') || $('#det-contenido').textContent.includes('Quórum'));
t('ficha muestra los 4 KPIs (favor/contra/abst/ausente)', $$('#det-contenido .kpi').length === 4);
t('ficha muestra la barra de la Cámara completa', !!$('#det-contenido .stack'));
const chips = $$('#det-dips .dip').length;
t('los 155 diputad@s aparecen en la ficha', chips === 155, 'chips=' + chips);

console.log('== 4. filtros y búsqueda en la ficha ==');
const nEsp = (target.nominal.N || []).length;
$$('#det-filtros button').find(b => b.dataset.f === 'N').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
let solo = $$('#det-dips .dip');
t('filtro "En contra" muestra exactamente los votos N', solo.length === nEsp && solo.every(c => c.classList.contains('N')), `n=${solo.length} esperado=${nEsp}`);
$$('#det-filtros button').find(b => b.dataset.f === 'S').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
solo = $$('#det-dips .dip');
t('filtro "A favor" muestra exactamente los votos S', solo.length === (target.nominal.S || []).length && solo.every(c => c.classList.contains('S')));
$$('#det-filtros button').find(b => b.dataset.f === 'X').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
solo = $$('#det-dips .dip');
const xEsp = 155 - (target.nominal.S||[]).length - (target.nominal.N||[]).length - (target.nominal.A||[]).length;
t('filtro "No votaron" calza con ausencias', solo.length === xEsp && solo.every(c => c.classList.contains('X')), `n=${solo.length} esperado=${xEsp}`);
$$('#det-filtros button').find(b => b.dataset.f === 'T').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
const input = $('#det-buscar');
input.value = 'jiles';
input.dispatchEvent(new window.Event('input', { bubbles: true }));
solo = $$('#det-dips .dip');
t('buscador filtra por nombre', solo.length >= 1 && solo.length <= 4 && solo.every(c => /jiles/i.test(c.textContent)), 'n=' + solo.length);

console.log('== 5. volver y navegación ==');
$('#btn-volver').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
t('volver regresa al calendario', $('#vista-calendario').style.display !== 'none' && $('#vista-detalle').style.display === 'none');
const flecha = $('#m-prev');
if (flecha && !flecha.disabled) {
  const mesAntes = $('#mes-nav button.on').dataset.m;
  flecha.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  t('flecha de mes anterior funciona', $('#mes-nav button.on').dataset.m !== mesAntes);
} else t('flecha de mes anterior funciona', true, 'ya en el primer mes');

console.log('== 6. enlaces y contenido ciudadano ==');
t('enlace de regreso al tablero principal', ($$('.volver')[0] || {}).getAttribute('href') === 'index.html');
t('nota sobre el Senado presente', doc.body.textContent.includes('Senado'));
t('fuente citada (datos abiertos)', doc.body.textContent.includes('datos abiertos'));

console.log('== 7. responsive (todos los dispositivos) ==');
t('meta viewport presente', (doc.querySelector('meta[name=viewport]') || {}).getAttribute('content').includes('width=device-width'));
t('safe-area insets (móviles con notch)', html.includes('env(safe-area-inset-left)'));
t('prefers-reduced-motion respetado', html.includes('prefers-reduced-motion'));
t('inputs 16px anti-zoom iOS', /input, select\{ font-size:16px; \}/.test(html));
t('touch-action en controles táctiles', html.includes('touch-action:manipulation'));
t('media queries para móvil chico', html.includes('@media (max-width:600px)') && html.includes('@media (max-width:360px)'));
t('sin errores acumulados', errs.length === 0, JSON.stringify(errs.slice(0,5)));

console.log('== 8. votaciones del período anterior (antes del 11-mar-2026) ==');
const vAnt = D.votaciones.find(v => v.nominal && v.fecha < '2026-03-11');
if (vAnt) { window.abrirDetalle(vAnt.id); const nSNA = vAnt.nominal.S.length + vAnt.nominal.N.length + vAnt.nominal.A.length;
  t('aviso "Cámara anterior" visible', $('#det-contenido').textContent.includes('Cámara anterior'));
  t('lista solo a quienes votaron (sin ausencias ficticias)', $$('#det-dips .dip').length === nSNA && $('.kpi.au .num').textContent === '0');
  t('exdiputad@s identificados', $('#det-dips').textContent.includes('Exdiputad')); }
const vAct = D.votaciones.find(v => v.nominal && v.fecha >= '2026-03-11');
window.abrirDetalle(vAct.id); t('votación actual: 155 chips con ausencias reales', $$('#det-dips .dip').length === 155);

console.log('== 9. observación completa de lo que se vota ==');
const vObs = D.votaciones.filter(v => v.obs && v.obs.articulo && v.obs.articulo.length > 240).sort((a,b) => b.obs.articulo.length - a.obs.articulo.length)[0];
t('el snapshot guarda el texto oficial completo (hay observaciones de más de 240 caracteres)', !!vObs);
if (vObs) {
  window.abrirDetalle(vObs.id);
  const dc = $('#det-contenido').textContent;
  t('la ficha muestra la observación íntegra, sin recortes', dc.includes(vObs.obs.articulo));
  t('explica "en simple" qué se está votando (recuadro amarillo antes del texto oficial)', !!$('#det-contenido .simple') && /En simple/.test($('#det-contenido .simple').textContent) && $('#det-contenido .simple').textContent.length > 80);
  const nExp = D.votaciones.filter(v => v.exp && v.exp.que).length;
  t(`todas las votaciones del snapshot traen explicación en simple (${nExp}/${D.votaciones.length})`, nExp === D.votaciones.length);
  t('las explicaciones distinguen tipos: cambios del Senado, indicaciones, inadmisibilidad, partes del proyecto', ['acepta los cambios que el Senado','propuesta para cambiar el texto','inadmisible','Se vota el artículo'].every(s => D.votaciones.some(v => v.exp && v.exp.que.includes(s))));
  t('explica trámite, informe, quórum y resultado en lista', $$('#det-contenido .obs dt').length >= 4 && /Resultado/.test(dc));
  t('trámite constitucional traducido a simple', /primera cámara|otra cámara|cambios que le hizo|acuerdo|observaciones del Presidente/.test(dc));
  t('caja "estado actual en vivo" presente', !!$('#obs-vivo'));
  t('enlace a la ficha completa en el buscador avanzado (con boletín)', !!$(`#det-contenido a[href*="buscador_avanzado.html#q=${encodeURIComponent(vObs.boletin)}"]`));
}
// simula el modo en vivo: el servidor responde con estado + contexto de normas citadas
window.fetch = async () => ({ json: async () => ({ senado:{etapa:'Segundo trámite constitucional (Senado)', estado:'En tramitación', url:'https://www.senado.cl/x'}, ley:null, votacion:{numero:2,total_votaciones:5},
  contexto:{citas:[{cita:'Ley N° 20.898', titulo:'PROCEDIMIENTO SIMPLIFICADO PARA LA REGULARIZACIÓN DE VIVIENDAS', tipo:'Ley', numero:'20898', publicacion:'2016-02-04', n_articulos:20, url:'https://www.bcn.cl/leychile/navegar?idNorma=1086866', articulos:[{n:'3', texto:'Artículo 3º.- El procedimiento regulado por el presente Título…', derogado:false, version:'2016-02-04'}]}]} }) });
window.despuesEnVivo(vObs || vAct);
setTimeout(() => {
  const ov = $('#obs-vivo');
  t('en vivo: muestra el estado actual del proyecto (etapa) y la votación N de M', /Segundo trámite/.test(ov.textContent) && /2 de 5/.test(ov.textContent));
  t('en vivo: contexto con la norma citada, su título y enlace a LeyChile', /Ley N° 20\.898/.test(ov.textContent) && !!ov.querySelector('.ctx a[href*="leychile"][target="_blank"]'));
  t('en vivo: texto vigente del artículo citado, completo y desplegable', /Artículo 3º\.- El procedimiento/.test(ov.querySelector('.ctx-art pre').textContent));
  window.fetch = async () => { throw new Error('sin servidor'); };
  window.despuesEnVivo(vObs || vAct);
}, 200);
setTimeout(() => {
  const ov = $('#obs-vivo');
  t('sin servidor, la caja en vivo explica que necesita el modo en vivo', !!ov && /modo en vivo/.test(ov.textContent));
  console.log(`\nRESULTADO: ${pass} pass, ${fail} fail`);
  process.exit(fail ? 1 : 0);
}, 600);
return;
}, 500);
