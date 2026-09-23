const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');

const html = fs.readFileSync(__dirname + '/elecciones_chile.html', 'utf8');
const errs = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => { if(!/scrollTo\(\) method/.test(e.message)) errs.push('jsdomError: ' + e.message); });
vc.on('error', (...a) => errs.push('console.error: ' + a.join(' ')));

const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'https://localhost/elecciones' });
const { window } = dom;
const doc = window.document;
const $ = s => doc.querySelector(s);
const $$ = s => [...doc.querySelectorAll(s)];
let pass = 0, fail = 0;
const t = (name, cond, extra='') => { if (cond) { pass++; console.log('  ✔', name); } else { fail++; console.log('  ✘', name, extra); } };

console.log('== 1. carga sin errores de script ==');
t('sin errores js en load', errs.length === 0, JSON.stringify(errs.slice(0,3)));

console.log('== 2. tabs ==');
t('existe botón de tab mapa', !!$('nav.tabs button[data-tab="mapa"]'));
$('nav.tabs button[data-tab="mapa"]').click();
t('al hacer clic se muestra tab-mapa', !$('#tab-mapa').classList.contains('oculto'));
t('tab diputados oculto', $('#tab-diputados').classList.contains('oculto'));

console.log('== 3. modo diputados (default) ==');
let cells = $$('#svg-mapa .cell[data-t="dip"]');
t('28 celdas de distrito', cells.length === 28, 'hay ' + cells.length);
t('todas las celdas tienen relleno de pacto (no gris default)', cells.every(c => c.getAttribute('fill') !== '#e4e8f2'));
const ks = cells.map(c => +c.dataset.k).sort((a,b)=>a-b);
t('distritos 1..28 presentes', JSON.stringify(ks) === JSON.stringify([...Array(28)].map((_,i)=>i+1)));
t('viewBox geográfico 460×2490', $('#svg-mapa').getAttribute('viewBox') === '0 0 460 2490', $('#svg-mapa').getAttribute('viewBox'));
t('geografía real: +300 paths de comunas', $$('#svg-mapa path').length > 300, 'paths='+$$('#svg-mapa path').length);
t('fondo continental de 343 comunas', $$('#svg-mapa .pais-fondo path').length === 343, 'n='+$$('#svg-mapa .pais-fondo path').length);
t('28 números de distrito sobre el mapa', $$('#svg-mapa .lbl-num').length === 28, 'n='+$$('#svg-mapa .lbl-num').length);
t('chip islas (D7) presente', $$('#svg-mapa .cell.isla').length === 1);
const ley = $('#mapa-leyenda').textContent;
t('leyenda menciona pacto mayoritario', /UNIDAD POR CHILE/.test(ley), ley.slice(0,80));
t('nota menciona pacto más votado', /más votado/i.test($('#mapa-nota').textContent));

console.log('== 4. clic en distrito 20 (Gran Concepción) ==');
const c20 = cells.find(c => c.dataset.k === '20');
c20.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
t('detalle muestra Distrito N° 20', /Distrito N° 20/.test($('#mapa-detalle').textContent));
t('detalle menciona Biobío', /Biobío/.test($('#mapa-detalle').textContent));
t('detalle lista electos (Paz Charpentier)', /Paz Charpentier/.test($('#mapa-detalle').textContent));
t('selector de Diputados sincronizado a 20', $('#sel-distrito').value === '20');
t('panel original #dip-distrito también actualizado', /Distrito|elect/i.test($('#dip-distrito').textContent));
t('celda 20 marcada como .sel', c20.classList.contains('sel'));

console.log('== 5. tooltip (mousemove no lanza) ==');
try { c20.dispatchEvent(new window.MouseEvent('mousemove', { bubbles: true, clientX: 120, clientY: 300 })); t('mousemove sin excepción', true); }
catch(e){ t('mousemove sin excepción', false, e.message); }

console.log('== 6. cambio a modo senadores ==');
$('button[data-elec="senadores"]').click();
const sc = $$('#svg-mapa .cell[data-t="sen"]');
t('16 franjas senatoriales', sc.length === 16, 'hay ' + sc.length);
const colored = sc.filter(c => c.getAttribute('fill') !== '#e4e8f2');
t('exactamente 7 con color (renuevan)', colored.length === 7, 'hay ' + colored.length);
const sens = sc.map(c => +c.dataset.k).sort((a,b)=>a-b);
t('circunscripciones 1,2,4,6,9,11,14 coloreadas', JSON.stringify(colored.map(c=>+c.dataset.k).sort((a,b)=>a-b)) === JSON.stringify([1,2,4,6,9,11,14]), JSON.stringify(sens));
const c11 = sc.find(c => c.dataset.k === '11');
c11.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
t('detalle C°11 = Araucanía con Carter', /Circunscripción senatorial N° 11/.test($('#mapa-detalle').textContent) && /Carter/.test($('#mapa-detalle').textContent));
const c3 = sc.find(c => c.dataset.k === '3');
c3.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
t('clic en C°3 (no renueva) → aviso 2029', /2029/.test($('#mapa-detalle').textContent));

console.log('== 7. modo presidente (1ª vuelta por distrito) ==');
$('button[data-elec="presidente"]').click();
const pc = $$('#svg-mapa .cell[data-t="presi"]');
t('28 distritos geográficos en presidencial', pc.length === 28, 'n=' + pc.length);
t('cada distrito con color de su 1ª mayoría', pc.every(c => c.getAttribute('fill') !== '#e4e8f2'));
const nRojo = pc.filter(c => c.getAttribute('fill') === '#d92632').length;
const nVio = pc.filter(c => c.getAttribute('fill') === '#7c3aed').length;
t('mezcla real: Jara ≥12 distritos rojos y Kast ≥8 violetas', nRojo >= 12 && nVio >= 8, 'rojo=' + nRojo + ' violeta=' + nVio);
t('etiquetas de apellido del ganador', $$('#svg-mapa text').filter(x => /^(Kast|Jara|Parisi|Matthei)$/.test(x.textContent)).length >= 28);
pc[0].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
t('clic muestra detalle del distrito (no nacional plano)', /Distrito N° \d+ · 1ª vuelta/.test($('#mapa-detalle').textContent));
t('leyenda presidencial por distrito', /Primera mayoría por distrito/.test($('#mapa-tit-leyenda').textContent) && /Jeannette Jara/.test($('#mapa-leyenda').textContent));
try { pc[1].dispatchEvent(new window.MouseEvent('mousemove', { bubbles: true, clientX: 90, clientY: 300 }));
  t('tooltip presidencial distrital', /1ª vuelta 16-N/.test($('#mapa-tip').innerHTML)); }
catch(e){ t('tooltip presidencial sin excepción', false, e.message); }

console.log('== 8. modo municipales ==');
$('button[data-elec="municipales"]').click();
const mc = $$('#svg-mapa .cell[data-t="mun"]');
t('16 franjas grises punteadas', mc.length === 16 && mc.every(c => c.getAttribute('fill') === '#e4e8f2'));
mc[0].dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
t('clic explica snapshot sin municipales 2028', /2028|no está en el snapshot/i.test($('#mapa-detalle').textContent));

console.log('== 9. vuelta a diputados y render consistente ==');
$('button[data-elec="diputados"]').click();
t('28 celdas otra vez', $$('#svg-mapa .cell[data-t="dip"]').length === 28);

console.log('== 10. segunda vuelta: pestaña Presidencial ==');
t('sv-kpis con 4 tarjetas', $$('#sv-kpis .kpi').length === 4);
const svb = $$('#sv-barras .bar-row');
t('sv-barras con 2 candidaturas', svb.length === 2, 'hay ' + svb.length);
t('Kast 58.17% y chip PRESIDENTE ELECTO', /58\.17%/.test($('#sv-barras').textContent) && /PRESIDENTE ELECTO/.test($('#sv-barras').textContent));
t('Jara 41.83% presente', /41\.83%/.test($('#sv-barras').textContent));
t('desglose Chile + extranjero', /Dentro de Chile/.test($('#sv-desglose').textContent) && /Extranjero/.test($('#sv-desglose').textContent));
t('Kast ganó 16/16 regiones (desglose)', /16 de 16/.test($('#sv-desglose').textContent));
t('nota fuente apunta al ZIP oficial', /Datos_SegundaVotacion\.zip/.test($('#sv-nota').innerHTML) && /servel\.cl/.test($('#sv-nota').innerHTML));

console.log('== 11. mapa modo 2ª vuelta (geográfico) ==');
$('button[data-elec="segundavuerta"]').click();
const svs = $$('#svg-mapa .cell[data-t="sv"]');
t('16 regiones geográficas coloreadas', svs.length === 16 && svs.every(c => c.getAttribute('fill') !== '#e4e8f2'), 'n=' + svs.length);
t('todas en violeta Kast (ganó 16/16)', svs.every(c => c.getAttribute('fill') === '#7c3aed'));
t('etiquetas "Kast NN%" en las regiones', $$('#svg-mapa text').filter(x => /^Kast \d+%$/.test(x.textContent)).length === 16);
t('16 nombres de región como etiquetas', $$('#svg-mapa .lbl-reg-geo').length >= 16, 'n='+$$('#svg-mapa .lbl-reg-geo').length);
t('chip extranjero rojo (Jara ganó afuera)', (() => { const e = $('#svg-mapa .cell[data-t="svext"]'); return e && e.getAttribute('fill') === '#d92632'; })());
try { svs[0].dispatchEvent(new window.MouseEvent('mousemove', { bubbles: true, clientX: 150, clientY: 40 }));
  t('tooltip región menciona 2ª vuelta', /2ª vuelta presidencial 14-D/.test($('#mapa-tip').innerHTML)); }
catch(e){ t('tooltip sin excepción', false, e.message); }
const bio = svs.find(c => c.dataset.k === 'Biobío');
bio.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
t('clic Biobío → detalle con Kast 717.027', /Región Biobío · 2ª vuelta/.test($('#mapa-detalle').textContent) && /717\.027/.test($('#mapa-detalle').textContent), $('#mapa-detalle').textContent.slice(0,120));
t('detalle Biobío marca GANÓ AQUÍ en Kast', /GANÓ AQUÍ/.test($('#mapa-detalle').innerHTML));
$('#svg-mapa .cell[data-t="svext"]').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
t('clic extranjero → detalle con España y Jara', /España/.test($('#mapa-detalle').textContent) && /Jara/.test($('#mapa-detalle').textContent));
t('leyenda 2ª vuelta con pcts nacionales', /58\.17%/.test($('#mapa-leyenda').textContent) && /41\.83%/.test($('#mapa-leyenda').textContent));
$('button[data-elec="diputados"]').click();
t('vuelta a diputados: 28 celdas intactas', $$('#svg-mapa .cell[data-t="dip"]').length === 28);

console.log('== 11b. buscador y métricas ==');
$('#mapa-buscar').value = 'Concepcion';
$('#mapa-buscar').dispatchEvent(new window.Event('change'));
t('buscador «Concepcion» → Distrito N° 20', /Distrito N° 20/.test($('#mapa-detalle').textContent), $('#mapa-detalle').textContent.slice(0,80));
t('la comuna buscada queda resaltada en el mapa', $$('#svg-mapa .comuna-hl').length === 1, 'n=' + $$('#svg-mapa .comuna-hl').length);
t('el resaltado es el path de Concepción', (()=>{ const p = $('#svg-mapa .comuna-hl'); return p && p.getAttribute('data-n').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase() === 'concepcion'; })());
t('buscador sincroniza select de distritos', $('#sel-distrito').value === '20');
$('#mapa-buscar').value = 'Ñuñoa';
$('#mapa-buscar').dispatchEvent(new window.Event('change'));
t('buscador «Ñuñoa» → Distrito 10 (sin tildes funciona)', /Distrito N° 10/.test($('#mapa-detalle').textContent), $('#mapa-detalle').textContent.slice(0,80));
const fillsAntes = $$('#svg-mapa .cell.geo[data-t="dip"]').map(c=>c.getAttribute('fill'));
t('28 grupos geo en modo dip', fillsAntes.length === 28, 'n='+fillsAntes.length);
$('button[data-m="participacion"]').click();
const fillsPart = $$('#svg-mapa .cell.geo[data-t="dip"]').map(c=>c.getAttribute('fill'));
t('métrica participación repinta con rampa', fillsPart.join() !== fillsAntes.join());
t('leyenda de participación con rango %', /Participación/.test($('#mapa-tit-leyenda').textContent) && /\d+\.\d% → \d+\.\d%/.test($('#mapa-leyenda').textContent), $('#mapa-leyenda').textContent.slice(0,90));
$('button[data-m="nulosblancos"]').click();
t('métrica nulos+blancos repinta de nuevo', $$('#svg-mapa .cell.geo[data-t="dip"]').map(c=>c.getAttribute('fill')).join() !== fillsPart.join());
$('button[data-m="territorio"]').click();
t('volver a territorio restaura los colores', $$('#svg-mapa .cell.geo[data-t="dip"]').map(c=>c.getAttribute('fill')).join() === fillsAntes.join());
$('button[data-elec="presidente"]').click();
t('presidente YA muestra métricas (hay datos por distrito)', $('#mapa-metricas').style.display === 'flex');
const fillsPresi = $$('#svg-mapa .cell.geo[data-t="presi"]').map(c=>c.getAttribute('fill'));
$('button[data-m="nulosblancos"]').click();
t('nulos+blancos repinta la presidencial distrital', $$('#svg-mapa .cell.geo[data-t="presi"]').map(c=>c.getAttribute('fill')).join() !== fillsPresi.join());
$('button[data-m="territorio"]').click();
$('button[data-elec="municipales"]').click();
t('municipales sigue sin métricas (no hay snapshot 2028)', $('#mapa-metricas').style.display === 'none');
t('el corte antártico se oculta si el trazado no tiene cuña', $('#mapa-corte').style.display === 'none');
$('button[data-elec="diputados"]').click();
t('diputados re-muestra la barra', $('#mapa-metricas').style.display === 'flex');
t('badge de frescura muestra sellos de tiempo', /datos 16-N: \d{4}-/.test($('#badge-frescura').textContent), $('#badge-frescura').textContent.slice(0,90));
t('badge menciona la 2ª vuelta', /2ª vuelta: /.test($('#badge-frescura').textContent));
t('celdas navegables por teclado', $('#svg-mapa .cell[data-t="dip"]').getAttribute('tabindex') === '0' && $('#svg-mapa .cell[data-t="dip"]').getAttribute('role') === 'button');
$$('#svg-mapa .cell[data-t="dip"][data-k="10"]')[0].dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
t('Enter abre el detalle del distrito 10', /Distrito N° 10/.test($('#mapa-detalle').textContent));

console.log('== 12. piezas originales intactas ==');
t('barras presidencial original presentes', $$('#pres-barras .bar-row').length === 8);
t('KPIs presidencial presentes', $$('#pres-kpis .kpi').length === 4);
t('barras nacionales diputados', $$('#dip-nacional .bar-row').length > 0);
t('select diputados con 28 opciones', $('#sel-distrito').options.length === 29);
t('select senadores con 7 opciones', $('#sel-circ').options.length === 8);
t('enlaces a Servel intactos', html.includes('https://www.servel.cl') && html.includes('index.html'));

console.log('== 13. responsive (todos los dispositivos) ==');
t('meta viewport presente', (doc.querySelector('meta[name=viewport]') || {}).getAttribute('content').includes('width=device-width'));
t('safe-area insets (móviles con notch)', html.includes('env(safe-area-inset-left)'));
t('prefers-reduced-motion respetado', html.includes('prefers-reduced-motion'));
t('SVG del mapa fluido', /#svg-mapa\{\s*width:100%/.test(html));
t('touch-action en controles táctiles', html.includes('touch-action:manipulation'));
t('sin errores acumulados', errs.length === 0, JSON.stringify(errs.slice(0,5)));

console.log('== 14. explorador presidencial completo ==');
t('explorador presente con 6 subpestañas', $$('#pres-subtabs button').length === 6);
t('1ª vuelta: ganadores por distrito suman 28', [...$$('#v1-ganadores div')].reduce((s,d)=>s+ (d.textContent.match(/(\d+) distrito/)? +d.textContent.match(/(\d+) distrito/)[1] : 0), 0) === 28);
t('1ª vuelta: mejor/peor distrito por candidatura (8)', $$('#v1-extremos div').length === 8);
t('2ª vuelta: tabla con 16 regiones', $$('#v2-tabla tbody tr').length === 16);
t('2ª vuelta: nota cuenta regiones ganadas', /ganó en \d+ de 16 regiones/.test($('#v2-nota').textContent));
t('Chile vs extranjero: tarjetas 2ª vuelta con países', $('#ext-cards').textContent.includes('Extranjero') && $('#ext-cards').textContent.includes('España'));
t('comparación 1ª→2ª: dos finalistas con ▲ votos', $$('#cmp-cards .flecha b').length === 2 && $('#cmp-cards').textContent.includes('▲'));
t('comparación regional: 16 filas', $$('#cmp-tabla tbody tr').length === 16);
const zv = $('#zona-valor'); zv.value = '20'; zv.dispatchEvent(new window.Event('change'));
t('zona: distrito 20 muestra comunas y 2ª vuelta Biobío', $('#zona-detalle').textContent.includes('Concepción') && $('#zona-detalle').textContent.includes('2ª vuelta en la región de Biobío'));
const zb = $('#zona-busca'); zb.value = 'temuco'; zb.dispatchEvent(new window.Event('input'));
t('zona: buscar comuna "temuco" → distrito 23', $('#zona-detalle').textContent.includes('Distrito 23'));
$('#zona-tipo').value = 'reg'; $('#zona-tipo').dispatchEvent(new window.Event('change'));
t('zona: modo región lista distritos de la región', $('#zona-detalle').textContent.includes('1ª vuelta en sus distritos'));
t('tabla completa: 28 distritos × candidaturas', $$('#tabla-full tbody tr').length === 28 && $$('#tabla-full thead th').length >= 12);
const thPart = [...$$('#tabla-full thead th')].find(th => th.textContent.startsWith('Particip')); thPart.click();
const v = [...$$('#tabla-full tbody tr')].map(tr => parseFloat(tr.lastElementChild.textContent));
t('tabla completa: ordena por participación desc', v[0] >= v[1] && v[1] >= v[27]);
$('#tabla-modo').value = 'reg'; $('#tabla-modo').dispatchEvent(new window.Event('change'));
t('tabla completa: modo regiones 16 filas', $$('#tabla-full tbody tr').length === 16);

console.log('== 15. exploradores parlamentarios (diputados y senado) ==');
const DATA = JSON.parse(fs.readFileSync(__dirname + '/elecciones_resultados.json', 'utf8'));
const nEscD = Object.values(DATA.diputados.distritos).reduce((s,d)=>s+d.electos.length,0);
const nEscS = Object.values(DATA.senadores.distritos).reduce((s,d)=>s+d.electos.length,0);
t('diputados: explorador con 6 subpestañas', $$('#dip-subtabs button').length === 6);
t('diputados: tabla de elect@s = escaños del snapshot ('+nEscD+')', $$('#dip-electos-tabla tbody tr').length === nEscD, 'hay '+$$('#dip-electos-tabla tbody tr').length);
const selPac = $('#dip-electos-pacto'); selPac.value = DATA.diputados.resumen_nacional[0].pacto; selPac.dispatchEvent(new window.Event('change'));
t('diputados: filtro por pacto = escaños del pacto', $$('#dip-electos-tabla tbody tr').length === DATA.diputados.resumen_nacional[0].escanos);
t('diputados: tabla pactos con escaños por 1%', $$('#dip-pactos-tabla tbody tr').length === DATA.diputados.resumen_nacional.length && $('#dip-pactos-tabla').textContent.includes('Escaños por 1 %'));
t('diputados: tabla partidos', $$('#dip-partidos-tabla tbody tr').length > 10);
const dz = $('#dip-zona-sel'); dz.value = '20'; dz.dispatchEvent(new window.Event('change'));
t('diputados: distrito 20 lista TODAS sus candidaturas', $('#dip-zona-det').textContent.includes('Todas las candidaturas ('+DATA.diputados.distritos['20'].candidatos.length+')') && $('#dip-zona-det').textContent.includes('Concepción'));
const dzb = $('#dip-zona-busca'); dzb.value = 'valdivia'; dzb.dispatchEvent(new window.Event('input'));
t('diputados: buscar comuna "valdivia" → distrito 24', $('#dip-zona-det').textContent.includes('Distrito 24'));
t('diputados: top 15 más votad@s', $$('#dip-top div').length === 16);
const db = $('#dip-busca'); db.value = 'unidad por chile'; db.dispatchEvent(new window.Event('input'));
t('diputados: buscador por pacto devuelve filas', $$('#dip-busca-tabla tbody tr').length >= 20);
t('diputados: tabla completa 28 filas ordenable', $$('#dip-tabla-full tbody tr').length === 28);
$$('#dip-tabla-full thead th').find(th=>th.textContent.startsWith('Particip')).click();
const pv = [...$$('#dip-tabla-full tbody tr')].map(tr=>parseFloat(tr.lastElementChild.textContent));
t('diputados: orden por participación desc', pv[0] >= pv[1] && pv[1] >= pv[27]);
t('senado: explorador elect@s = '+nEscS, $$('#sen-electos-tabla tbody tr').length === nEscS);
t('senado: zona muestra región y distritos', /Región de .* · distritos D/.test($('#sen-zona-det').textContent));
t('senado: tabla completa = circunscripciones en disputa', $$('#sen-tabla-full tbody tr').length === Object.keys(DATA.senadores.distritos).length);
t('regionales: enlace al tablero de próxima elección', !!$('#tab-regionales a[href="proxima_eleccion.html"]'));

console.log(`\nRESULTADO: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
