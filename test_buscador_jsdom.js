// Tests del BUSCADOR AVANZADO (buscador_avanzado.html)
// Simula el servidor en vivo (fetch) con respuestas sintéticas para probar el flujo completo:
// búsqueda → lista → filtros → ficha de proyecto (Cámara + Senado, voto nominal) → ficha de persona.
const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');

let pass = 0, fail = 0;
const t = (name, cond, extra='') => { if (cond) { pass++; console.log('  ✔', name); } else { fail++; console.log('  ✘', name, extra); } };
const espera = ms => new Promise(r => setTimeout(r, ms));

const BUSCAR = {
  q: 'pensiones', total: 4, fuentes: 'Cámara · Senado · LeyChile (simulado)',
  resultados: [
    {tipo:'proyecto', origen:'camara', ref:'15480-13', titulo:'Crea un nuevo Sistema Mixto de Pensiones', detalle:'Mensaje · ingresó 2022-11-07 · 12 votaciones', fecha:'2025-01-29', estado:'Tramitación terminada', score:40},
    {tipo:'ley', origen:'gobierno', ref:'21735', titulo:'Ley 21.735: Crea un nuevo sistema mixto de pensiones', detalle:'Ministerio del Trabajo · publicada el 26-03-2025', fecha:'26-03-2025', estado:'Publicada', url:'https://www.bcn.cl/leychile/navegar?idNorma=1', boletin:'15480-13', score:30},
    {tipo:'diputado', origen:'camara', ref:'1186', titulo:'Ignacio Achurra', detalle:'Diputad@ · FA · Distrito 14', estado:'En ejercicio', score:10},
    {tipo:'senador', origen:'senado', ref:'1110', titulo:'Pedro Araya Guerrero', detalle:'Senador/a · P.P.D. · Región de Antofagasta', estado:'En ejercicio', url:'https://www.senado.cl/x', score:10},
  ]
};
const dips = {}; for (let i = 1; i <= 155; i++) dips[String(i)] = {n: 'Diputad@ ' + i, g: ['UDI','PS','FA','RN','PC'][i % 5], p: 'X', dist: String((i % 28) + 1)};
const votosCam = {}; for (let i = 1; i <= 150; i++) votosCam[String(i)] = i <= 100 ? 'S' : i <= 140 ? 'N' : 'A';
const FICHA = {
  boletin: '15480-13', errores: [],
  camara: {pid:'16006', boletin:'15480-13', nombre:'Crea un nuevo Sistema Mixto de Pensiones y un Seguro Social', titulo_simple:'Crea un nuevo Sistema Mixto de Pensiones', ingreso:'2022-11-07', iniciativa:'Mensaje', origen:'Cámara de Diputados',
    autores: [], ministerios: ['Ministerio de Hacienda'], materias: ['Pensiones'], admisible:'true',
    votaciones: [
      {id:'1', fecha:'2024-01-24', si:80, no:70, abst:2, quorum:'Quórum Simple', resultado:'Aprobado', tipo:'General', articulo:'Idea de legislar', tramite:'Primer trámite constitucional'},
      {id:'2', fecha:'2025-01-29', si:100, no:40, abst:10, quorum:'Quórum Calificado', resultado:'Aprobado', tipo:'Única', exp:{titular:'Cambios hechos por el Senado · Aprobado 100-40', que:'Se vota si la Cámara acepta los cambios que el Senado le hizo al proyecto que ella ya había aprobado.', contexto:'Es el tercer trámite.', quorum:'Necesitaba 78 votos (quórum calificado).', resultado:'Se aprobó con 100 votos a favor, 40 en contra y 10 abstenciones.', consecuencia:'¿Y ahora? Con los cambios del Senado aceptados, el proyecto pasa al Presidente para promulgarlo.', propuesta:'Artículo 24.- Nuevo texto propuesto para el ingreso y egreso del país.'}, articulo:'Enmiendas del Senado', tramite:'Tercer trámite constitucional', votos: votosCam},
    ],
    url: 'https://www.camara.cl/legislacion/proyectosdeley/tramitacion.aspx?prmID=16006'},
  senado: {boletin:'15480-13', titulo:'Crea un nuevo Sistema Mixto de Pensiones', ingreso:'07/11/2022', iniciativa:'Mensaje', origen:'C.Diputados', urgencia:'Sin urgencia', etapa:'Tramitación terminada', subetapa:' / ', ley:'Ley N° 21.735', diario_oficial:'26/03/2025', estado:'Publicado',
    tramites: [{fecha:'07/11/2022', sesion:'/', que:'Ingreso de proyecto', etapa:'Primer trámite constitucional', camara:'C.Diputados', exp:'El proyecto fue presentado oficialmente en la Cámara de Diputados. Aquí empieza su camino.'}, {fecha:'27/01/2025', sesion:'98/372', que:'Aprobado en general', etapa:'Segundo trámite constitucional', camara:'Senado'}, {fecha:'26/03/2025', sesion:'/', que:'Publicada la ley en el Diario Oficial', etapa:'Tramitación terminada', camara:'Senado'}],
    autores: [], urgencias: [], materias: ['Pensiones'], url: 'https://www.senado.cl/appsenado/templates/tramitacion/index.php?boletin_ini=15480'},
  senado_votaciones: [{sesion:'98/372', fecha:'27/01/2025', tema:'Proyecto de ley de pensiones. En votación en general.', si:40, no:7, abst:0, pareo:0, quorum:'Q.C.', tipo:'Discusión general', etapa:'Segundo trámite constitucional',
    votos: [{n:'Coloma C., Juan Antonio', v:'S'}, {n:'Kuschel S., Carlos Ignacio', v:'N'}, {n:'Araya G., Pedro', v:'S'}, {n:'Allende B., Isabel', v:'S'}]}],
  diputados: dips,
  senadores: [{id:'1110', nombre:'Pedro Araya Guerrero', apellido:'Araya', partido:'P.P.D.', region:'Región de Antofagasta', circ:'3', url:'https://www.senado.cl/x'}, {id:'2', nombre:'Juan Antonio Coloma', apellido:'Coloma', partido:'U.D.I.', region:'Región del Maule', circ:'9', url:''}],
  ley: {numero:'21.735', diario_oficial:'26/03/2025', url:'https://www.bcn.cl/leychile/consulta?str=Ley+21735'}
};
const PERSONA = {tipo:'diputado', persona:{nombre:'Ignacio Achurra', partido:'FA', distrito:'14'}, asistencia:{asist:100, inas:0, inas_ef:0, grupo:'Frente Amplio'}, total_sesiones:69,
  votos_recientes:[{boletin:'17757-29', titulo:'Modifica la ley N° 19.327 (fútbol)', fecha:'2026-09-09', voto:'S', resultado:'Rechazado'}, {boletin:'15480-13', titulo:'Pensiones', fecha:'2025-01-29', voto:'N', resultado:'Aprobado'}],
  url:'https://www.camara.cl/diputados/detalle/biografia.aspx?prmId=1186', url_mociones:'https://www.camara.cl/m', url_gastos:'https://www.camara.cl/g'};

function cargar(html){
  const errs = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => { if(!/scrollTo|IntersectionObserver|Not implemented/.test(e.message)) errs.push(e.message); });
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'https://localhost/buscador_avanzado.html',
    beforeParse(w){
      w.scrollTo = () => {}; w.open = () => ({});
      w.fetch = async (url) => {
        const u = String(url);
        let body = {};
        if (u.startsWith('/api/contexto')) body = {citas:[{cita:'Ley N° 21.325', titulo:'LEY DE MIGRACIÓN Y EXTRANJERÍA', tipo:'Ley', numero:'21325', publicacion:'2021-04-20', organismo:'MINISTERIO DEL INTERIOR', n_articulos:184, url:'https://www.bcn.cl/leychile/navegar?idNorma=1158549', articulos:[{n:'24', texto:'Artículo 24.- Forma de ingreso y egreso. La entrada de personas al territorio nacional…', derogado:false, version:'2021-04-20'}]}]};
        else if (u.startsWith('/api/buscar')) body = BUSCAR;
        else if (u.includes('tipo=proyecto')) body = FICHA;
        else if (u.includes('tipo=diputado')) body = PERSONA;
        else if (u.includes('tipo=senador')) body = {tipo:'senador', persona:{nombre:'Pedro Araya Guerrero', partido:'P.P.D.', region:'Región de Antofagasta', circ:'3'}, url:'https://www.senado.cl/x'};
        return { json: async () => body, ok: true };
      };
    }});
  return { doc: dom.window.document, win: dom.window, errs };
}

(async () => {
  const html = fs.readFileSync('/home/user/buscador_avanzado.html', 'utf8');
  console.log('== 1. carga y estructura ==');
  const A = cargar(html); const d = A.doc, w = A.win;
  await espera(200);
  t('sin errores js al cargar', A.errs.length === 0, JSON.stringify(A.errs.slice(0,2)));
  t('título y descripción SEO', /Buscador avanzado/.test(d.title) && d.querySelector('meta[name=description]').content.length > 60);
  t('caja de búsqueda y botón', !!d.querySelector('#q') && !!d.querySelector('#form button[type=submit]'));
  t('ejemplos clicables', d.querySelectorAll('.ejemplos button').length >= 4);
  t('menú con enlaces a las otras páginas', ['index.html','elecciones_chile.html','calendario_votaciones.html','proxima_eleccion.html'].every(h => d.querySelector(`nav.tabs a[href="${h}"]`)));
  t('botón de modo oscuro presente', !!d.querySelector('#dark-toggle'));
  t('sin instrucciones técnicas visibles', !/python3|gen_|hito\.sh/.test(d.body.textContent));
  t('footer cita fuentes oficiales y sin base de datos', /No existe base de datos/.test(d.querySelector('footer').textContent) && /Senado/.test(d.querySelector('footer').textContent));

  console.log('== 2. búsqueda → lista ==');
  d.querySelector('#q').value = 'pensiones';
  d.querySelector('#form').dispatchEvent(new w.Event('submit', {cancelable:true, bubbles:true}));
  await espera(150);
  const items = d.querySelectorAll('#lista .item');
  t('lista con los 4 resultados', items.length === 4, items.length);
  t('cada resultado indica su origen (Cámara/Senado/Gobierno)', [...items].every(i => i.querySelector('.tag')) && d.querySelector('.tag.senado') && d.querySelector('.tag.gobierno'));
  t('estado de la búsqueda con total y fuentes', /4 resultados/.test(d.querySelector('#estado').textContent));
  t('filtros visibles', d.querySelector('#filtros').style.display !== 'none');
  d.querySelector('#filtros [data-f="persona"]').click();
  t('filtro Personas deja 2', d.querySelectorAll('#lista .item').length === 2);
  d.querySelector('#filtros [data-o="senado"]').click();
  t('filtro Senado deja 1 (senador)', d.querySelectorAll('#lista .item').length === 1 && /Araya/.test(d.querySelector('#lista .item').textContent));
  d.querySelector('#filtros [data-o="senado"]').click(); d.querySelector('#filtros [data-f="todo"]').click();
  t('volver a Todo restablece 4', d.querySelectorAll('#lista .item').length === 4);
  t('hash con la consulta (compartible)', /q=pensiones/.test(w.location.hash));

  console.log('== 3. ficha de proyecto (Cámara + Senado) ==');
  d.querySelector('#lista .item').click();
  await espera(200);
  t('la ficha se muestra y la lista se oculta', d.querySelector('#ficha').style.display === 'block' && d.querySelector('#resultados').style.display === 'none');
  const fc = d.querySelector('#ficha-contenido');
  t('título simple del proyecto', /Sistema Mixto de Pensiones/.test(fc.querySelector('h2').textContent));
  t('boletín, ley y etapa como etiquetas', /Boletín 15480-13/.test(fc.textContent) && /Ley 21\.735/.test(fc.textContent) && /Tramitación terminada/.test(fc.textContent));
  t('explicación en simple', /En simple/.test(d.querySelector('#explica').textContent) && /Ya es ley/.test(d.querySelector('#explica').textContent));
  t('KPIs: ingreso, quién propuso, votaciones Cámara y Senado', fc.querySelectorAll('.kpi').length >= 4 && /Votaciones en la Cámara/.test(fc.textContent) && /Votaciones en el Senado/.test(fc.textContent));
  t('5 pestañas (resumen, cámara, senado, tramitación, fuentes)', fc.querySelectorAll('.subtabs button').length === 5);
  t('resumen: quién lo presentó (Gobierno) y ministerio', /Presidente de la República/.test(d.querySelector('#s-resumen').textContent) && /Hacienda/.test(d.querySelector('#s-resumen').textContent));
  // cámara
  fc.querySelector('.subtabs [data-s="camara"]').click();
  t('pestaña Cámara con 2 votaciones y semáforo', d.querySelector('#s-camara').classList.contains('on') && d.querySelectorAll('#s-camara .vot').length === 2 && d.querySelectorAll('#s-camara .stack').length === 2);
  const btnCam = d.querySelector('#s-camara .btn-det');
  t('botón "cómo votó cada diputad@" solo en la votación con detalle', !!btnCam && d.querySelectorAll('#s-camara .btn-det:not(.btn-ctx)').length === 1);
  btnCam.click();
  const cajaCam = d.querySelector('#cam-2');
  t('detalle nominal de diputad@s: 155 chips', cajaCam.querySelectorAll('.dip').length === 155, cajaCam.querySelectorAll('.dip').length);
  t('colores por voto (100 a favor, 40 en contra, 10 abst, 5 no votaron)', cajaCam.querySelectorAll('.dip.S').length === 100 && cajaCam.querySelectorAll('.dip.N').length === 40 && cajaCam.querySelectorAll('.dip.A').length === 10 && cajaCam.querySelectorAll('.dip.X').length === 5);
  t('agrupados por bancada', cajaCam.querySelectorAll('.grupo').length === 5);
  cajaCam.querySelector('[data-f="N"]').click();
  t('filtro "en contra" deja 40', cajaCam.querySelectorAll('.dip').length === 40);
  cajaCam.querySelector('input').value = 'Diputad@ 12'; cajaCam.querySelector('input').dispatchEvent(new w.Event('input'));
  t('buscador de nombre dentro del detalle', cajaCam.querySelectorAll('.dip').length >= 1 && cajaCam.querySelectorAll('.dip').length < 40);
  // senado
  fc.querySelector('.subtabs [data-s="senado"]').click();
  t('pestaña Senado con 1 votación (40/7) aprobada', d.querySelectorAll('#s-senado .vot').length === 1 && /A favor.*40/.test(d.querySelector('#s-senado').textContent) && /Aprobado/.test(d.querySelector('#s-senado .res').textContent));
  d.querySelector('#s-senado .btn-det').click();
  const cajaSen = d.querySelector('#sen-0');
  t('detalle nominal de senador@s: 4 chips con colores', cajaSen.querySelectorAll('.dip').length === 4 && cajaSen.querySelectorAll('.dip.S').length === 3 && cajaSen.querySelectorAll('.dip.N').length === 1);
  t('senador@s agrupados por partido (P.P.D., U.D.I.)', /P\.P\.D\./.test(cajaSen.textContent) && /U\.D\.I\./.test(cajaSen.textContent));
  // tramitación y fuentes
  fc.querySelector('.subtabs [data-s="tramite"]').click();
  t('línea de tiempo con los 3 pasos (Cámara → Senado → ley)', d.querySelectorAll('#s-tramite .timeline li').length === 3 && d.querySelectorAll('#s-tramite li.sen').length >= 1 && d.querySelectorAll('#s-tramite li.ley').length >= 1);
  fc.querySelector('.subtabs [data-s="fuentes"]').click();
  const links = [...d.querySelectorAll('#s-fuentes a')];
  t('enlaces oficiales a camara.cl, senado.cl y LeyChile, en pestaña nueva', links.length === 3 && links.every(a => a.target === '_blank' && /noopener/.test(a.rel)) && /camara\.cl/.test(links[0].href) && /senado\.cl/.test(links[1].href) && /bcn\.cl/.test(links[2].href));
  const simp = d.querySelector('#s-camara .simple');
  t('cada votación explica "en simple" qué se votó (recuadro amarillo con titular)', !!simp && /Cambios hechos por el Senado · Aprobado 100-40/.test(simp.querySelector('.titular').textContent) && /acepta los cambios que el Senado/.test(simp.textContent));
  t('dice qué pasa ahora (consecuencia) y esconde trámite/quórum en "ver más"', /¿Y ahora\?/.test(simp.querySelector('.ahora').textContent) && /tercer trámite/.test(simp.querySelector('details.mas').textContent));
  t('aviso de explicación automática con enlace a la fuente oficial', /Explicación automática/.test(simp.querySelector('.aviso-auto').textContent) && !!simp.querySelector('.aviso-auto a[target="_blank"]'));
  t('palabras del Congreso marcadas con glosario emergente (quórum calificado, tercer trámite…)', d.querySelectorAll('#ficha-contenido .glos').length >= 2);
  const gl = d.querySelector('#ficha-contenido .glos'); gl.click();
  t('al tocar una palabra aparece su definición y se cierra con ✕', !!d.querySelector('.glos-pop') && d.querySelector('.glos-pop').textContent.length > 40 && (d.querySelector('.glos-pop .glos-x').click(), !d.querySelector('.glos-pop')));
  t('comparado "así dice hoy / así quedaría" cuando la votación trae texto propuesto', !!d.querySelector('#comparado-cam-2 .comparado .prop') && /Nuevo texto propuesto/.test(d.querySelector('#comparado-cam-2 .prop').textContent));
  t('la línea de tramitación explica cada paso en simple', /presentado oficialmente en la Cámara/.test(d.querySelector('#s-tramite .timeline .simple').textContent));
  const bctx = d.querySelector('#s-camara .btn-ctx');
  t('cada votación tiene botón "Ver el contexto" (leyes y artículos citados)', !!bctx && d.querySelectorAll('.btn-ctx').length >= 3);
  bctx.click(); await espera(120);
  const cajaCtx = d.getElementById(bctx.dataset.ctx);
  t('el contexto muestra la norma citada con su título, fecha y enlace a LeyChile', /Ley N° 21\.325/.test(cajaCtx.textContent) && /MIGRACIÓN/.test(cajaCtx.textContent) && /20\/04\/2021/.test(cajaCtx.textContent) && !!cajaCtx.querySelector('a[href*="leychile"][target="_blank"]'));
  t('muestra el texto vigente completo del artículo citado', /Artículo 24\.- Forma de ingreso y egreso/.test(cajaCtx.querySelector('.ctx-art pre').textContent));
  t('tras cargar el contexto, el comparado muestra "así dice hoy" con el artículo vigente de LeyChile', /Forma de ingreso y egreso/.test(d.querySelector('#comparado-cam-2 .hoy').textContent));
  t('botón Escuchar presente', !!d.querySelector('#btn-escuchar'));

  {
    let hablado = ''; w.speechSynthesis = { cancel(){}, speak(u){ hablado = u.text; } }; w.SpeechSynthesisUtterance = function(t){ this.text = t; };
    d.querySelector('#btn-escuchar').click();
    t('Escuchar lee también las explicaciones "en simple" de las votaciones', /Votaciones, en simple/.test(hablado) && /acepta los cambios que el Senado/.test(hablado) && !/Explicación automática/.test(hablado));
  }
  console.log('== 4. volver y ficha de persona ==');
  d.querySelector('#btn-volver').click();
  t('volver muestra la lista con los mismos resultados', d.querySelector('#resultados').style.display === '' && d.querySelectorAll('#lista .item').length === 4);
  d.querySelectorAll('#lista .item')[2].click();
  await espera(200);
  t('ficha de diputad@: nombre, partido, distrito', /Ignacio Achurra/.test(fc.querySelector('h2').textContent) && /Distrito 14/.test(fc.textContent));
  t('asistencia oficial y sesiones', /100%/.test(fc.textContent) && /69 sesiones/.test(fc.textContent));
  const vr = fc.querySelectorAll('[data-bol]');
  t('votos recientes listados con color y resultado', vr.length === 2 && /A favor/.test(vr[0].textContent) && /En contra/.test(vr[1].textContent));
  vr[1].click(); await espera(200);
  t('clic en una ley del diputad@ abre la ficha del proyecto', /Sistema Mixto de Pensiones/.test(fc.querySelector('h2').textContent));
  d.querySelector('#btn-volver').click(); d.querySelectorAll('#lista .item')[3].click(); await espera(200);
  t('ficha de senador/a con región y partido', /Araya/.test(fc.querySelector('h2').textContent) && /Antofagasta/.test(fc.textContent) && /P\.P\.D\./.test(fc.textContent));

  console.log('== 5. ley publicada abre la ficha del proyecto (por su boletín) ==');
  d.querySelector('#btn-volver').click(); d.querySelectorAll('#lista .item')[1].click(); await espera(200);
  t('ley 21.735 → ficha completa del boletín 15480-13 con votaciones', /Boletín 15480-13/.test(fc.textContent) && fc.querySelectorAll('.subtabs button').length === 5);

  console.log('== 6. modo oscuro y arranque por URL ==');
  d.querySelector('#dark-toggle').click();
  t('modo oscuro activa clase y guarda preferencia compartida', d.body.classList.contains('dark') && w.localStorage.getItem('eps_dark') === '1');
  const B = cargar(html.replace('<body>', '<body>')); B.win.location.hash = '#q=pensiones';
  const C = new JSDOM(html, { runScripts:'dangerously', pretendToBeVisual:true, url:'https://localhost/buscador_avanzado.html#q=pensiones&tipo=proyecto&ref=15480-13', beforeParse(w2){ w2.scrollTo=()=>{}; w2.fetch = async u => ({ json: async () => String(u).startsWith('/api/buscar') ? BUSCAR : FICHA }); }, virtualConsole: new VirtualConsole() });
  await espera(400);
  t('URL con q+ref abre directamente la ficha (enlace compartible)', C.window.document.querySelector('#ficha').style.display === 'block' && /Pensiones/.test(C.window.document.querySelector('#ficha-contenido h2').textContent));

  console.log('== 7. sin servidor: mensaje claro ==');
  const D = new JSDOM(html, { runScripts:'dangerously', pretendToBeVisual:true, url:'https://localhost/buscador_avanzado.html', beforeParse(w3){ w3.scrollTo=()=>{}; w3.fetch = async () => { throw new Error('Failed to fetch'); }; }, virtualConsole: new VirtualConsole() });
  D.window.document.querySelector('#q').value = 'x'; D.window.document.querySelector('#form').dispatchEvent(new D.window.Event('submit', {cancelable:true}));
  await espera(150);
  t('explica que necesita el modo en vivo', /modo en vivo/.test(D.window.document.querySelector('#estado').textContent));

  console.log('== 7b. motor de citas (python) ==');
  const pyc = require('child_process').spawnSync('python3', ['-c', `
import buscador as B
c = B.citas_en_texto('Modifica el decreto ley N°321, de 1925; los artículos 49, 50 y 51 del Código Penal; el artículo 3 de la ley N° 20.898 y el artículo 17 del decreto ley N° 3.500')
print('|'.join(sorted(x['cita'] + ':' + ','.join(x['articulos']) for x in c)))`], {encoding:'utf8', cwd: __dirname});
  const citas = (pyc.stdout||'').trim();
  t('detecta DL 321, Código Penal (arts. 49-51), Ley 20.898 (art. 3) y DL 3.500 (art. 17) sin confundir "decreto ley" con "ley"', citas === ['Código Penal:49,50,51','Decreto Ley N° 3.500 (sistema de pensiones):17','Decreto Ley N° 321 (libertad condicional):','Ley N° 20.898:3'].sort().join('|'), citas);

  console.log('== 7c. explicador (python): observaciones y trámites en simple ==');
  const pye = require('child_process').spawnSync('python3', ['-c', `
import explicador as E
ok = 0
r = E.explicar_votacion('Numeral 4) del artículo único del proyecto, cuya votación separada ha sido solicitada por el diputado X', 'Primer Trámite', 'Segundo Informe', 'Quórum Simple', 'Aprobado', 80, 20, 3, 'Proyecto de Ley', 'Reconoce el circo tradicional')
ok += 'el numeral 4 del artículo único' in r['que'] and 'aparte' in r['que'] and 'primer trámite' in r['contexto'].lower() and 'artículo por artículo' in r['contexto'] and '80 votos a favor' in r['resultado']
r = E.explicar_votacion('Modificaciones incorporadas por el Senado en el proyecto de ley que “X”.', 'Tercer Trámite', 'Sin Informe', 'Quórum Calificado', 'Rechazado', 70, 60, 0)
ok += 'acepta los cambios que el Senado' in r['que'] and 'Comisión Mixta' in r['que'] and '78 votos' in r['quorum'] and 'no alcanzó el mínimo' in r['resultado']
r = E.explicar_votacion('Reclamación de la declaración de inadmisibilidad de la indicación del diputado Y')
ok += 'inadmisible' in r['que'] and 'No se vota el fondo' in r['que']
r = E.explicar_votacion('Indicación renovada de la diputada Z, para reemplazar el artículo único por el siguiente')
ok += 'propuesta para cambiar el texto' in r['que'] and 'renovada' in r['que']
r = E.explicar_votacion('Observación número 2 de S.E. el Presidente de la República para suprimir el artículo 39 del proyecto.', 'Observaciones P. De La R.')
ok += 'veto' in r['que']
r = E.explicar_votacion('Proyecto de acuerdo que “Aprueba el Tratado entre Chile y Brasil”', tipo_proyecto='Proyecto de Acuerdo')
ok += 'tratado' in r['que']
ok += 'primera en revisar' in E.explicar_votacion('Artículo 58 transitorio del proyecto.', 'Primer Trámite')['contexto'] and 'entra en vigencia' in E.explicar_votacion('Artículo 58 transitorio del proyecto.')['que']
ok += 'Comisión de Cultura, Patrimonio, Artes, Deportes y Recreación' in E.explicar_tramite('Cuenta de proyecto . Pasa a Comisión de Cultura, Patrimonio, Artes, Deportes y Recreación', '', 'Senado')
ok += 'al Senado' in E.explicar_tramite('Oficio de ley a Cámara Revisora .', '', 'C.Diputados') and 'Presidente' in E.explicar_tramite('Oficio de ley al Ejecutivo.') and 'urgencia simple (30 días)' in E.explicar_tramite('Cuenta del Mensaje 22-374 que hace presente la urgencia Simple')
ok += 'en general' in E.explicar_votacion_senado({'tema':'En votación en general el proyecto', 'tipo':'Discusión general', 'etapa':'Segundo trámite constitucional', 'quorum':'Q.C.', 'si':40, 'no':7, 'abst':0, 'pareo':2}) and '26 votos' in E.explicar_votacion_senado({'tema':'', 'tipo':'Discusión general', 'quorum':'Q.C.', 'si':40, 'no':7, 'pareo':2}) and 'pareo' in E.explicar_votacion_senado({'tema':'', 'tipo':'', 'quorum':'', 'si':1, 'no':0, 'pareo':2})
r = E.explicar_votacion('', 'Primer Trámite', 'Primer Informe', 'Quórum Simple', 'Aprobado', 90, 10, 0, 'Proyecto de Ley', 'X')
ok += 'idea de legislar' in r['que'] and 'ahora se discuten' in r['consecuencia'] and r['titular'].startswith('Idea de legislar')
r = E.explicar_votacion('', '', '', '', 'Aprobado', 70, 10, 0, 'Otros', '', '3-Creacion Comision Investigadora')
ok += 'comisión investigadora' in r['que'] and 'La comisión se forma' in r['consecuencia']
r = E.explicar_votacion('Numeral 2) del artículo único del proyecto, cuya votación separada ha sido solicitada', 'Primer Trámite', 'Segundo Informe', 'Quórum Simple', 'Rechazado', 60, 70, 1)
ok += 'se cae' in r['consecuencia'] and 'Rechazado 60-70' in r['titular']
r = E.explicar_votacion('Indicación renovada del diputado X para agregar el siguiente artículo nuevo: “Artículo 3 bis.- Las municipalidades podrán conformar equipos comunales de regularización de viviendas integrados por arquitectos municipales.”', 'Primer Trámite', 'Segundo Informe', 'Quórum Simple', 'Rechazado', 60, 70, 1)
ok += r['propuesta'].startswith('Artículo 3 bis') and 'se descarta' in r['consecuencia']
print(ok, 14)`], {encoding:'utf8', cwd: __dirname});
  const [oke, tote] = (pye.stdout || '0 0').trim().split(/\s+/).map(Number);
  t(`explicador: ${oke}/${tote} casos (partes del proyecto, cambios del Senado, inadmisibilidad, indicaciones, veto, tratados, transitorios, trámites, Senado)`, oke === tote && tote > 0, pye.stderr && pye.stderr.slice(0, 300));

  console.log('== 8. tolerancia a faltas de ortografía ==');
  const E = new JSDOM(html, { runScripts:'dangerously', pretendToBeVisual:true, url:'https://localhost/buscador_avanzado.html', beforeParse(w4){ w4.scrollTo=()=>{}; w4.fetch = async u => ({ json: async () => (String(u).includes('q=pencion') || String(u).includes('q=pensiones')) ? Object.assign({}, BUSCAR, {sugerencia: String(u).includes('pencion') ? 'pensiones' : ''}) : BUSCAR }); }, virtualConsole: new VirtualConsole() });
  const ed = E.window.document;
  ed.querySelector('#q').value = 'pencion'; ed.querySelector('#form').dispatchEvent(new E.window.Event('submit', {cancelable:true}));
  await espera(150);
  t('con "pencion" igual muestra resultados', ed.querySelectorAll('#lista .item').length === BUSCAR.resultados.length);
  const sg = ed.querySelector('#estado .sugerencia');
  t('avisa que se buscó como «pensiones» (tolera faltas de ortografía)', !!sg && /pensiones/.test(sg.textContent) && /ortograf/i.test(sg.textContent));
  const bsug = ed.querySelector('#estado .btn-sug');
  t('botón para buscar la palabra corregida', !!bsug);
  bsug.click(); await espera(150);
  t('al pulsarlo, la caja queda con la palabra corregida y desaparece el aviso', ed.querySelector('#q').value === 'pensiones' && !ed.querySelector('#estado .sugerencia'));
  // motor python: pruebas unitarias de la coincidencia aproximada
  const py = require('child_process').spawnSync('python3', ['-c', `
import buscador as B
casos = [('pencion','sistema de pensiones',1),('condisional','libertad condicional',1),('biolencia','violencia intrafamiliar',1),('trasporte','ley de transportes',1),('educasion','calidad de la educacion',1),('comicion','comision de hacienda',1),('seguridá','ley de seguridad',1),('kast','castillo',0),('pensiones','futbol',0),('gato','pago',0)]
print(sum(1 for q,tx,esp in casos if (B.puntaje(tx, B.tokens(q), q) > 0) == bool(esp)), len(casos))`], {encoding:'utf8', cwd: __dirname});
  const [okn, totn] = (py.stdout || '0 0').trim().split(/\s+/).map(Number);
  t(`motor: ${okn}/${totn} casos de ortografía (b/v, s/c, h, letras cambiadas) correctos y sin falsos positivos`, okn === totn && totn > 0);

  console.log(`\nRESULTADO: ${pass} pass, ${fail} fail`);
  process.exit(fail ? 1 : 0);
})();
