// Tests de la página "Próxima elección" (proxima_eleccion.html)
// Prueba los DOS estados: (a) la página real (esperando datos) y
// (b) un snapshot sintético con datos, para asegurar que se rellena sola.
const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');

let pass = 0, fail = 0;
const t = (name, cond, extra='') => { if (cond) { pass++; console.log('  ✔', name); } else { fail++; console.log('  ✘', name, extra); } };

function cargar(html){
  const errs = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => { if(!/scrollTo|IntersectionObserver/.test(e.message)) errs.push(e.message); });
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'https://localhost/' });
  return { doc: dom.window.document, win: dom.window, errs };
}

console.log('== 1. página real (estado esperando) ==');
const html = fs.readFileSync(__dirname + '/proxima_eleccion.html', 'utf8');
const conf = JSON.parse(fs.readFileSync(__dirname + '/proxima_eleccion.json', 'utf8'));
const A = cargar(html);
t('sin errores js', A.errs.length === 0, JSON.stringify(A.errs.slice(0,2)));
t('título con nombre de la elección', A.doc.title.includes(conf.nombre));
t('cuenta regresiva o estado visible', A.doc.querySelector('#cuenta').textContent.trim().length > 0);
t('una tarjeta por cargo configurado', A.doc.querySelectorAll('.card.cargo').length === conf.cargos.length);
t('cargos sin ZIP muestran "esperando"', A.doc.querySelectorAll('.chip.esperando').length === conf.cargos.filter(c=>!c.zip).length);
t('explicación ciudadana de cada cargo', [...A.doc.querySelectorAll('.card.cargo p')].every(p => p.textContent.length > 40));
t('KPIs renderizados', A.doc.querySelectorAll('#kpis .kpi').length === 4);
t('guía para votar (5 pasos)', A.doc.querySelectorAll('#como-votar .paso').length === 5);
t('sin instrucciones técnicas visibles para el ciudadano', !A.doc.querySelector('#admin') && !/python3|gen_proxima|hito\.sh/.test(A.doc.body.textContent));
t('enlace de vuelta al tablero y a resultados 2025', !!A.doc.querySelector('a[href="index.html"]') && !!A.doc.querySelector('a[href="elecciones_chile.html"]'));
t('fuente Servel citada, sin base de datos', /Servel/.test(A.doc.querySelector('footer').textContent) && /bases de datos/.test(A.doc.querySelector('footer').textContent));

console.log('== 2. snapshot con datos (simula noche de elección) ==');
const tpl = fs.readFileSync(__dirname + '/template_proxima.html', 'utf8');
const fake = {
  nombre: 'Elección de prueba', fecha: '2020-01-01', estado: 'preparando', descripcion: 'x', generado: '2020-01-01 22:00',
  cargos: [{ id: 'alc', nombre: 'Alcaldes', emoji: '🏛️', ambito: 'comuna', ambito_nombre: 'comuna', explica: 'e', estado: 'con_datos',
    datos: { total_validos: 1000, mesas: 10,
      resumen_nacional: [{ pacto: 'Pacto A', votos: 600, pct: 60, escanos: 1 }, { pacto: 'Pacto B', votos: 400, pct: 40, escanos: 1 }],
      zonas: { 'Concepción': { mesas: 5, electores: 900, total_validos: 600, nulos: 3, blancos: 2, pactos: [], electos: ['Ana Prueba'],
                candidatos: [{ nombre: 'Ana Prueba', pacto: 'Pacto A', partido: 'P1', votos: 400, pct: 66.67, electo: true }, { nombre: 'Beto Test', pacto: 'Pacto B', partido: 'P2', votos: 200, pct: 33.33, electo: false }] },
               'Talcahuano': { mesas: 5, electores: 800, total_validos: 400, nulos: 1, blancos: 1, pactos: [], electos: ['Carla Demo'],
                candidatos: [{ nombre: 'Carla Demo', pacto: 'Pacto B', partido: 'P2', votos: 400, pct: 100, electo: true }] } } } },
    { id: 'gob', nombre: 'Gobernadores', emoji: '🏞️', ambito: 'region', ambito_nombre: 'región', explica: 'e', estado: 'esperando', zip: '' }]
};
const B = cargar(tpl.replace('/*__DATA__*/', JSON.stringify(fake)));
t('sin errores js con datos', B.errs.length === 0, JSON.stringify(B.errs.slice(0,2)));
t('estado pasa a "en curso" al haber datos', B.doc.querySelector('.estado.en_curso') !== null);
t('cargo con datos marcado ✅', B.doc.querySelectorAll('.chip.con_datos').length === 1 && B.doc.querySelectorAll('.chip.esperando').length === 1);
t('resumen nacional por pacto', B.doc.querySelector('#cargo-alc').textContent.includes('Pacto A') && B.doc.querySelector('#cargo-alc').textContent.includes('60%'));
t('electo marcado con ✔', B.doc.querySelector('#cargo-alc .electo') !== null && B.doc.querySelector('#zona-alc').textContent.includes('Ana Prueba'));
const sel = B.doc.querySelector('.sel-zona'); sel.value = 'Talcahuano'; sel.dispatchEvent(new B.win.Event('change'));
t('selector de comuna cambia el detalle', B.doc.querySelector('#zona-alc').textContent.includes('Carla Demo') && !B.doc.querySelector('#zona-alc').textContent.includes('Ana Prueba'));
t('explorador por cargo: 5 subpestañas', B.doc.querySelectorAll('#cargo-alc .subtabs button').length === 5);
t('explorador: tabla de elect@s con ✔', B.doc.querySelector('#s-alc-electos').textContent.includes('Ana Prueba') && B.doc.querySelector('#s-alc-electos').textContent.includes('Carla Demo'));
const cb = B.doc.querySelector('.cand-busca'); cb.value = 'beto'; cb.dispatchEvent(new B.win.Event('input'));
t('explorador: buscador de candidat@s (no elect@s también)', B.doc.querySelector('#b-alc').textContent.includes('Beto Test'));
const zb = B.doc.querySelector('.zona-busca'); zb.value = 'talca'; zb.dispatchEvent(new B.win.Event('input'));
t('explorador: búsqueda de comuna', B.doc.querySelector('#zona-alc').textContent.includes('Carla Demo'));
t('KPI cargos con datos = 1/2', B.doc.querySelector('#kpis').textContent.includes('1/2'));

console.log('== 3. configuración editable ==');
t('proxima_eleccion.json tiene instrucciones y cargos con campo zip', Array.isArray(conf._como_usar) && conf.cargos.every(c => 'zip' in c && c.ambito && c.id));
t('columnas Servel configurables', conf.columnas && conf.columnas.candidato && conf.columnas.votos);

console.log(`\nRESULTADO: ${pass} pass, ${fail} fail`);
process.exit(fail ? 1 : 0);
