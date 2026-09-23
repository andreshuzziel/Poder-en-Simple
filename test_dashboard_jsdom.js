// Tests de funcionamiento del dashboard principal (index.html)
// Estático: la página trae los datos embebidos (DATA), así que basta jsdom.
const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');

const html = fs.readFileSync(__dirname + '/index.html', 'utf8');
const errs = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => { if(!/scrollTo\(\) method|IntersectionObserver/.test(e.message)) errs.push('jsdomError: ' + e.message); });
vc.on('error', (...a) => errs.push('console.error: ' + a.join(' ')));

const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'https://localhost/' });
const { window } = dom;
const doc = window.document;
const $ = s => doc.querySelector(s);
const $$ = s => [...doc.querySelectorAll(s)];
let pass = 0, fail = 0;
const t = (name, cond, extra='') => { if (cond) { pass++; console.log('  ✔', name); } else { fail++; console.log('  ✘', name, extra); } };

setTimeout(() => {
console.log('== 1. carga sin errores ==');
t('sin errores js en load', errs.length === 0, JSON.stringify(errs.slice(0,3)));
t('título "El Poder en Simple" (sin bandera)', doc.title.includes('El Poder en Simple') && !doc.title.includes('🇨🇱'));
t('h1 sin bandera', !($('#main h1') || $('header h1')).textContent.includes('🇨🇱'));

console.log('== 2. datos embebidos y renders ==');
t('DATA inyectada', html.includes('const DATA = {'));
t('KPIs renderizados', $$('#kpis .kpi-card').length >= 5);
t('tabla con 155 diputad@s', $$('#tbody tr.fila-d').length === 155, 'hay ' + $$('#tbody tr.fila-d').length);
t('noticias renderizadas', $$('.not-item').length >= 3);
t('gabinete renderizado', $$('.gob-card').length >= 20);
t('mesas directivas', $$('#cards-mesas .card').length === 2);
t('proyectos clave del año', $('#pk-anio') && $('#pk-anio').children.length > 0);
t('fechas próximas', $$('#fechas-proximas .prox-card').length >= 1);
t('feriados', $$('#fechas-feriados .fer-card').length >= 5);

console.log('== 3. accesos al tablero electoral ==');
t('botón grande hacia elecciones_chile.html', !!$('#btn-elecciones'));
t('nav incluye Elecciones', $$('nav.menu a').some(a => a.textContent.includes('Elecciones') && a.getAttribute('href') === 'elecciones_chile.html'));
t('nav incluye Calendario de votaciones', $$('nav.menu a').some(a => a.textContent.includes('Calendario') && a.getAttribute('href') === 'calendario_votaciones.html'));
const cd = $('#elecciones-countdown');
t('cuadro próxima elección visible', cd && cd.innerHTML.includes('Próxima elección'));
t('cuadro próxima elección con botón electoral', cd && !!cd.querySelector('a[href="elecciones_chile.html"]'));

console.log('== 4. interactividad ==');
const buscar = $('#buscar');
buscar.value = 'jiles';
buscar.dispatchEvent(new window.Event('input', { bubbles: true }));
const n1 = $$('#tbody tr.fila-d').length;
t('buscador filtra la tabla', n1 < 155, 'quedan ' + n1);
buscar.value = '';
buscar.dispatchEvent(new window.Event('input', { bubbles: true }));
t('buscador vacío restaura los 155', $$('#tbody tr.fila-d').length === 155);
const th = doc.querySelector('#tabla th[data-k="g_tot"]');
th.click();
t('ordenar por gasto funciona (primera fila es la de mayor gasto)', (() => {
  const filas = $$('#tbody tr.fila-d td:last-child').map(td => parseInt(td.textContent.replace(/[^0-9]/g,'')));
  return filas.length && filas[0] >= filas[filas.length-1];
})());
t('click en fila abre ficha detalle', (() => {
  const fila = doc.querySelector('#tbody tr.fila-d');
  fila.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  return !!doc.querySelector('#tbody tr.detalle');
})());
t('comparador: selects poblados', $('#cmp-a') && $('#cmp-a').options.length > 100);
t('buscador ciudadano del hero existe', !!$('#busq'));
const btnDark = $('#dark-toggle');
btnDark.click();
t('modo oscuro alterna', doc.body.classList.contains('dark'));
btnDark.click();
t('modo claro vuelve', !doc.body.classList.contains('dark'));

console.log('== 5. enlaces y robustez ==');
t('handler de enlaces externos instalado', html.includes('avisarEnlace'));
t('polifill scrollIntoView', html.includes('Element.prototype.scrollIntoView'));
const ext = $$('a[href^="http"]').length;
t('enlaces externos presentes', ext >= 20, 'hay ' + ext);
t('secciones ancladas existen', ['resumen','noticias','fechas','asistencia','gastos','votaciones','gobierno','senado','explorador','distrito','comparador','glosario'].every(id => !!doc.getElementById(id)));

console.log('== 6. responsive (todos los dispositivos) ==');
t('meta viewport presente', (doc.querySelector('meta[name=viewport]') || {}).getAttribute('content').includes('width=device-width'));
t('safe-area insets (móviles con notch)', html.includes('env(safe-area-inset-left)'));
t('prefers-reduced-motion respetado', html.includes('prefers-reduced-motion'));
t('inputs 16px anti-zoom iOS', /input, select\{ font-size:16px; \}/.test(html));
t('touch-action en controles táctiles', html.includes('touch-action:manipulation'));
t('nav compacta en móvil (toda visible, letra achicada)', html.includes('Nav compacta en móvil') && html.includes('nav.menu a{ font-size:10px;') && html.includes('flex-wrap:wrap; justify-content:center'));
t('modo oscuro legible (KPIs, tablas y chips oscurecidos)', html.includes('texto siempre legible') && html.includes('body.dark .kpi-card .num') && html.includes('body.dark .tabla-wrap{background:#171e30') && html.includes('body.dark .voto-chip.N'));
t('botón claro/oscuro visible en ambos modos', html.includes('#dark-toggle{margin-left:auto; border:1px solid #b9c8ec; background:#eef2fd') && html.includes('body.dark #dark-toggle{background:#25314f'));

console.log('== 7. buscador de contenido de la página ==');
const busq = $('#busq');
const panel = $('#busq-res');
busq.value = 'quorum';
busq.dispatchEvent(new window.Event('input', {bubbles:true}));
t('buscador indexa el glosario ciudadano', panel.textContent.includes('Información de la página') && panel.textContent.includes('Quórum'));
busq.value = 'año nuevo';
busq.dispatchEvent(new window.Event('input', {bubbles:true}));
t('buscador encuentra fechas clave (Año Nuevo)', panel.textContent.includes('Año Nuevo'));
busq.value = 'ministerio';
busq.dispatchEvent(new window.Event('input', {bubbles:true}));
t('buscador encuentra al gabinete', panel.textContent.includes('Presidente de la República') || panel.textContent.includes('🇨🇱'));
busq.value = '';
busq.dispatchEvent(new window.Event('input', {bubbles:true}));

console.log('== 8. utilidades ciudadanas: modo 12 años, ranking, accesibilidad, escuchar ==');
const nt = $('#ninos-toggle');
t('botón 🧒 modo 12 años en la nav', !!nt);
const leadIntro = $('#intro p.lead').textContent;
nt.click();
t('modo 12 años reemplaza las explicaciones', doc.body.classList.contains('modo-ninos') && $('#intro p.lead').textContent.startsWith('🧒') && $('#asistencia p.lead').textContent.includes('clases'));
nt.click();
t('modo 12 años se desactiva y restaura texto', !doc.body.classList.contains('modo-ninos') && $('#intro p.lead').textContent === leadIntro);
t('ranking renderiza top 10', $$('#rank-lista .rank-row').length === 10);
const primero = $('#rank-lista .rank-row .val').textContent;
$$('#rank-toggles button').find(b=>b.dataset.k==='gastan').click();
t('ranking cambia de criterio (gastan → $)', $('#rank-lista .rank-row .val').textContent !== primero && /\$/.test($('#rank-lista .rank-row .val').textContent));
const selR = $('#rank-region'); selR.value = 'Biobío'; selR.dispatchEvent(new window.Event('change'));
t('ranking filtra por región (Biobío)', $$('#rank-lista .rank-row').length > 0 && $$('#rank-lista .rank-row small').every(s=>s.textContent.includes('Biobío')));
t('botones 🔊 Escuchar en cada sección', $$('h2.tit .leer-btn').length >= 15);
const ab = $('#a11y-btn'); ab.click();
t('panel de accesibilidad abre', $('#a11y-panel').classList.contains('abierto'));
$$('#a11y-letra .opt').find(b=>b.dataset.v==='letra-xg').click();
$('#a11y-contraste').click(); $('#a11y-lectura').click();
t('letra grande + contraste + lectura fácil aplican', doc.body.classList.contains('letra-xg') && doc.body.classList.contains('contraste') && doc.body.classList.contains('lectura-facil'));
$('#a11y-reset').click();
t('restablecer limpia accesibilidad', !doc.body.classList.contains('letra-xg') && !doc.body.classList.contains('contraste'));
t('nav incluye Próxima elección', $$('nav.menu a').some(a => a.getAttribute('href') === 'proxima_eleccion.html'));
t('botón Próxima elección en fechas', !!$('#btn-proxima') && $('#btn-proxima').getAttribute('href') === 'proxima_eleccion.html');
t('SEO: description, robots, og:title y favicon presentes', !!$('meta[name="description"]') && !!$('meta[name="robots"]') && !!$('meta[property="og:title"]') && !!$('link[rel="icon"]'));
t('archivo antiguo redirige a index.html', fs.readFileSync(__dirname + '/dashboard_congreso.html','utf8').includes('url=index.html'));
const sdR = $('#sel-distrito'); sdR.value = '20'; sdR.dispatchEvent(new window.Event('change'));
setTimeout(()=>{}, 0);
t('nav incluye Ranking', $$('nav.menu a').some(a => a.getAttribute('href') === '#ranking'));
t('media queries para móvil chico', html.includes('@media (max-width:480px)'));
t('sin errores acumulados', errs.length === 0, JSON.stringify(errs.slice(0,5)));

console.log(`\nRESULTADO: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
}, 400);
