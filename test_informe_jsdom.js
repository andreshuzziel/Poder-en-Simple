// Tests del INFORME COMPLETO DE PROYECTO (informe_proyecto.html)
// Simula el servidor en vivo (fetch) con una respuesta real recortada de /api/informe?boletin=15480-13 (pensiones, Ley 21.735).
const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');
let pass = 0, fail = 0;
const t = (name, cond, extra='') => { if (cond) { pass++; console.log('  ✔', name); } else { fail++; console.log('  ✘', name, extra); } };
const espera = ms => new Promise(r => setTimeout(r, ms));
const FIX = JSON.parse(fs.readFileSync(__dirname + '/test_informe_fixture.json', 'utf8'));
const DOCS = JSON.parse(fs.readFileSync(__dirname + '/test_documentos_fixture.json', 'utf8'));

function cargar(html, opts={}){
  const errs = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => { if(!/scrollTo|IntersectionObserver|Not implemented/.test(e.message)) errs.push(e.message); });
  const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc, url: 'https://localhost/informe_proyecto.html' + (opts.hash||''),
    beforeParse(w){
      w.scrollTo = () => {}; w.open = () => ({}); w.print = () => { w.__printed = true; }; w.HTMLElement.prototype.scrollIntoView = function(){};
      w.fetch = async (url) => {
        const u = String(url); w.__urls = (w.__urls||[]).concat(u);
        if (opts.falla) throw new Error('sin conexión');
        let body = {error:'boletín no encontrado'};
        if (u.startsWith('/api/informe') && /15480-13/.test(u)) body = FIX;
        else if (u.startsWith('/api/documentos/cerrar')) body = {eliminados: 2};
        else if (u.startsWith('/api/documentos')) {
          if (opts.sinDocs) throw new Error('documentos no disponibles');
          if (opts.dosTandas) {
            if (/tanda=2/.test(u)) body = Object.assign({}, DOCS, {tanda:2, pendientes:0, otros:[], analizados:1,
              documentos:[Object.assign({}, DOCS.documentos[0], {doc_id:'999999', doc_tipo:'COMPARADO', etiqueta:'📊 Texto comparado', titulo:'Comparado de prueba', url:'https://www.senado.cl/appsenado/index.php?mo=tramitacion&ac=getDocto&iddocto=999999&tipodoc=compa', citas:[]})]});
            else body = Object.assign({}, DOCS, {pendientes: 1});
          } else body = DOCS;
        }
        return { json: async () => body, ok: true };
      };
    }});
  return { doc: dom.window.document, win: dom.window, errs };
}

(async () => {
  const html = fs.readFileSync(__dirname + '/informe_proyecto.html', 'utf8');
  console.log('== 1. carga y estructura ==');
  const A = cargar(html); const d = A.doc, w = A.win;
  await espera(150);
  t('sin errores js al cargar', A.errs.length === 0, JSON.stringify(A.errs.slice(0,2)));
  t('título y descripción SEO', /Informe/.test(d.title) && d.querySelector('meta[name=description]').content.length > 60);
  t('caja de boletín, botón y ejemplos', !!d.querySelector('#bol') && !!d.querySelector('#form-inf button[type=submit]') && d.querySelectorAll('#ejemplos button').length >= 3);
  t('menú con enlaces a las otras páginas', ['index.html','elecciones_chile.html','calendario_votaciones.html','proxima_eleccion.html','buscador_avanzado.html'].every(h => d.querySelector(`nav.tabs a[href="${h}"]`)));
  t('menú marca esta página como activa', /Informe/.test((d.querySelector('nav.tabs a.on')||{}).textContent||''));
  t('botón de modo oscuro presente', !!d.querySelector('#dark-toggle'));
  t('informe oculto hasta pedirlo', d.querySelector('#informe').style.display === 'none');
  t('sin instrucciones técnicas visibles', !/python3|gen_|hito\.sh/.test(d.body.textContent));
  t('footer cita fuentes oficiales y sin base de datos', /no se almacena|No existe base de datos|Nada se almacena/i.test(d.querySelector('footer').textContent) && /Senado/.test(d.querySelector('footer').textContent));
  t('enlaces externos en pestaña nueva', [...d.querySelectorAll('a[href^="http"]')].every(a => a.target === '_blank' && /noopener/.test(a.rel)));

  console.log('== 2. validación del boletín ==');
  d.querySelector('#bol').value = 'hola';
  d.querySelector('#form-inf').dispatchEvent(new w.Event('submit', {cancelable:true}));
  await espera(50);
  t('formato inválido avisa y sugiere el buscador', /formato 15480-13/.test(d.querySelector('#estado').textContent) && !!d.querySelector('#estado a[href="buscador_avanzado.html"]'));
  t('no llamó al servidor con formato inválido', !(w.__urls||[]).length);

  console.log('== 3. armar informe (15480-13) ==');
  d.querySelector('#bol').value = 'Boletín 15480-13';
  d.querySelector('#form-inf').dispatchEvent(new w.Event('submit', {cancelable:true}));
  await espera(300);
  t('llamó a /api/informe con el boletín limpio', (w.__urls||[]).some(u => u === '/api/informe?boletin=15480-13'));
  t('estado listo con conteo de votaciones', /Informe listo/.test(d.querySelector('#estado').textContent) && /100 votaciones/.test(d.querySelector('#estado').textContent));
  t('informe visible y botones imprimir/escuchar', d.querySelector('#informe').style.display !== 'none' && d.querySelector('#btn-imprimir').style.display !== 'none');
  t('título de la página cambia al proyecto', /Informe · /.test(d.title));
  t('deep link actualizado', /#boletin=15480-13/.test(w.location.hash));
  const caps = [...d.querySelectorAll('#cuerpo section.cap')];
  t('11 capítulos en orden (portada + 10, incl. documentos oficiales)', caps.length === 11 && caps.map(s=>s.id).join(',') === 'portada,ficha,tramitacion,camara,senado,indicaciones,vetos,urgencias,documentos,normas,fuentes', caps.map(s=>s.id).join(','));
  t('índice lateral con enlace a cada capítulo', caps.every(s => d.querySelector(`#indice a[href="#${s.id}"]`)));
  const portada = d.querySelector('#portada').textContent;
  t('portada: nombre, boletín, ley y estado', /Pensiones/i.test(portada) && /15480-13/.test(portada) && /21\.735/.test(portada) && /Publicad/i.test(portada));
  t('portada: KPIs (votaciones, trámites, urgencias)', /100/.test(portada) && /77/.test(portada) && /29/.test(portada));
  t('barra de progreso: etapa final marcada', d.querySelectorAll('#portada .progreso .done').length >= 4);
  const ficha = d.querySelector('#ficha').textContent;
  t('ficha: iniciativa, ingreso, ministerios/materias', /mensaje/i.test(ficha) && /2022|Ministerio/.test(ficha) && /Pensiones/i.test(ficha));
  const tram = d.querySelector('#tramitacion');
  t('recorrido: pasos con fecha y explicación en simple', tram.querySelectorAll('.paso-tr, .tr-item, li').length >= 5 && /Aquí empieza su camino|presentado oficialmente/.test(tram.textContent));

  console.log('== 4. votaciones de la Cámara por trámite ==');
  const cam = d.querySelector('#camara');
  t('capítulos por trámite (Primer y Tercer)', /Primer Trámite/.test(cam.textContent) && /Tercer Trámite/.test(cam.textContent));
  const vots = cam.querySelectorAll('.vot');
  t('6 votaciones renderizadas (recorte)', vots.length === 6, vots.length);
  t('cada votación: fecha, resultado y conteo', [...vots].every(v => /\d{2}[-\/]\d{2}[-\/]\d{4}|\d{4}-\d{2}-\d{2}/.test(v.textContent) && /Aprobad|Rechazad/.test(v.textContent)));
  t('explicación en simple en cada votación', [...vots].every(v => v.querySelector('.simple')));
  t('quórum explicado en palabras', /votos|mayoría/.test(cam.querySelector('.simple').textContent));
  console.log('== 4b. contraer / desplegar cada votación ==');
  t('cada votación tiene cabecera plegable y cuerpo', [...vots].every(v => v.querySelector('.cab[role=button]') && v.querySelector('.vot-body')));
  t('contraída se ve una sola línea en negrita: fecha · trámite · tipo (ej. 2024-01-24 · Primer Trámite · Particular)', [...vots].every(v => { const l = v.querySelector('.cab b.cab-linea'); return l && /^\d{4}-\d{2}-\d{2} · .+ · .+/.test(l.textContent.trim()); }), vots[0].querySelector('.cab').textContent);
  t('contraída muestra chevron ▸ y el resultado', [...vots].every(v => v.querySelector('.cab .chev').textContent === '▸' && /Aprobad|Rechazad/.test(v.querySelector('.cab .res').textContent)));
  t('el texto oficial largo queda dentro del detalle', [...vots].every(v => v.querySelector('.vot-body .cab-titulo')));
  t('votaciones de Cámara contraídas de entrada', [...vots].every(v => v.querySelector('.vot-body').style.display === 'none'));
  vots[0].querySelector('.cab').click(); await espera(20);
  t('un clic en el título despliega (chevron ▾)', vots[0].querySelector('.vot-body').style.display !== 'none' && vots[0].querySelector('.chev').textContent === '▾' && vots[0].querySelector('.cab').getAttribute('aria-expanded') === 'true');
  vots[0].querySelector('.cab').click(); await espera(20);
  t('otro clic la contrae', vots[0].querySelector('.vot-body').style.display === 'none');
  const barra = cam.querySelector('.plegar-todo');
  t('botones Desplegar/Contraer todas en el capítulo', barra && barra.querySelectorAll('button').length === 2 && /6/.test(barra.textContent));
  barra.querySelector('button[data-a="1"]').click(); await espera(20);
  t('Desplegar todas abre las 6', [...vots].every(v => v.querySelector('.vot-body').style.display !== 'none'));
  barra.querySelector('button[data-a="0"]').click(); await espera(20);
  t('Contraer todas cierra las 6', [...vots].every(v => v.querySelector('.vot-body').style.display === 'none'));
  barra.querySelector('button[data-a="1"]').click(); await espera(20);
  t('al imprimir se muestra todo (CSS print)', /@media print\{[\s\S]*\.vot-body\{display:block !important/.test(html));
  const btn = cam.querySelector('.btn-det');
  t('botón "ver cómo votó cada diputad@" en todas', cam.querySelectorAll('.btn-det').length === 6);
  btn.click(); await espera(50);
  const caja = d.getElementById(btn.dataset.det);
  t('un clic despliega el voto nominal', caja.style.display !== 'none' && caja.textContent.length > 500);
  t('nominal agrupado por bancada con nombres', /a favor|en contra/i.test(caja.textContent) && caja.querySelectorAll('.nom-item, .nombre, li, span').length > 50);
  btn.click(); await espera(20);
  t('segundo clic oculta', caja.style.display === 'none');
  t('glosario marcado en el cuerpo', d.querySelectorAll('#cuerpo .glos').length > 0);

  console.log('== 5. Senado, indicaciones, vetos, urgencias, normas, fuentes ==');
  const sen = d.querySelector('#senado');
  t('Senado: votación con tema y conteo', sen.querySelectorAll('.vot').length === 1 && /general/i.test(sen.textContent));
  t('todas las votaciones del informe (incl. vetos) parten contraídas', [...d.querySelectorAll('#senado .vot, #vetos .vot, #indicaciones .vot')].every(v => v.querySelector('.vot-body').style.display === 'none'));
  sen.querySelector('.vot .cab').click(); await espera(20);
  t('Senado: votación también plegable', sen.querySelector('.vot-body').style.display !== 'none');
  const bs = sen.querySelector('.btn-det'); bs.click(); await espera(50);
  t('Senado: nominal por senador/a', d.getElementById(bs.dataset.det).textContent.length > 100);
  t('indicaciones: sección con mensaje claro cuando no hay', /indicaciones/i.test(d.querySelector('#indicaciones').textContent) && /no|ningun|sin/i.test(d.querySelector('#indicaciones').textContent));
  const vet = d.querySelector('#vetos').textContent;
  t('vetos: explica qué es un veto', /veto/i.test(vet) && /Presidente/.test(vet));
  t('vetos: muestra el oficio "no hacer uso de la facultad de veto" con fecha y explicación', /facultad de veto/.test(vet) && /03-03-2025|03\/03\/2025/.test(vet) && /NO vetará/.test(vet));
  const urg = d.querySelector('#urgencias').textContent;
  t('urgencias: lista con tipo y plazo explicado', /urgencia/i.test(urg) && /\d+ días|plazo/i.test(urg));
  const nor = d.querySelector('#normas');
  t('normas: cita de ley con artículo y enlace oficial LeyChile', nor.querySelectorAll('a[href*="leychile"], a[href*="bcn.cl"]').length >= 1 || /No se detectaron|no cita/i.test(nor.textContent));
  const fu = d.querySelector('#fuentes');
  t('fuentes: enlaces oficiales Cámara y Senado en pestaña nueva', fu.querySelector('a[href*="camara.cl"][target=_blank]') && fu.querySelector('a[href*="senado.cl"][target=_blank]'));
  t('fuentes: fecha de generación y aviso de no almacenamiento', /Nada se almacena/.test(fu.textContent));
  t('todos los enlaces externos del informe abren en pestaña nueva', [...d.querySelectorAll('#cuerpo a[href^="http"]')].every(a => a.target === '_blank' && /noopener/.test(a.rel)));
  t('sin "undefined"/"null"/NaN visibles', !/undefined|null|NaN/.test(d.querySelector('#cuerpo').textContent));
  t('sin instrucciones técnicas en el informe', !/python3|gen_|\.json|hito/.test(d.querySelector('#cuerpo').textContent));

  console.log('== 5b. documentos oficiales leídos en memoria (segundo plano) ==');
  t('el informe se muestra antes de terminar de leer documentos', d.querySelector('#informe').style.display !== 'none');
  t('llamó a /api/documentos con boletín y pid', (w.__urls||[]).some(u => /\/api\/documentos\?boletin=15480-13&pid=16006/.test(u)));
  await espera(150);
  const dc = d.querySelector('#doc-cuerpo');
  t('KPIs: documentos publicados, leídos, leyes citadas', dc.querySelectorAll('.kpi').length === 3 && /24/.test(dc.textContent) && /le[ií]dos ahora/.test(dc.textContent));
  const cards = [...dc.querySelectorAll('.doc-card')];
  t('una tarjeta por documento leído (5) con etiqueta y fecha', cards.length === 5 && cards.every(c => c.querySelector('.doc-tag')));
  t('orden: veto primero, luego mensaje, luego informes', cards.map(c => c.dataset.tipo).join(',') === 'VETO,INICIATIVA,INFORMEPLEY,INFORMEPLEY,INFORMEPLEY');
  const cv = cards[0];
  t('veto: resumen en simple y cada observación con su artículo y qué propone', /3 observaciones/.test(cv.textContent) && /AL ARTÍCULO 32/.test(cv.textContent) && /Propone eliminar/.test(cv.textContent));
  t('veto: fundamento del Presidente por observación (anatocismo, olvido financiero)', /anatocismo/i.test(cv.textContent) && /olvido financiero/i.test(cv.textContent));
  t('veto: firmantes', /KAST/.test(cv.textContent) && /Ministro de Hacienda/.test(cv.textContent));
  const ci = cards[1];
  t('mensaje original: qué problema busca resolver y qué propone', /problema busca resolver/i.test(ci.textContent) && /crecimiento/i.test(ci.textContent) && /propone/i.test(ci.textContent));
  const cinf = cards[2];
  t('informe de comisión: quiénes expusieron y cómo votó la comisión', /expusieron/i.test(cinf.textContent) && /votó la comisión/i.test(cinf.textContent) && /votos a favor|aprobada|rechazada/i.test(cinf.textContent));
  t('cada tarjeta indica cuántos caracteres se leyeron en memoria y el formato', cards.every(c => /Leído en memoria: [\d\.]+ caracteres \((PDF|DOCX|DOC)\)/.test(c.textContent)));
  t('leyes citadas con enlace oficial (LeyChile/BCN) en pestaña nueva', cards.some(c => c.querySelector('.doc-citas a[target=_blank][rel=noopener][href*="bcn.cl"], .doc-citas a[target=_blank][rel=noopener][href*="leychile"]')));
  t('botón para abrir el documento oficial en camara.cl (pestaña nueva)', cards.every(c => c.querySelector('a.btn-oficial[href*="camara.cl/verDoc"][target=_blank][rel=noopener]')));
  t('lista de otros documentos publicados no leídos', /Otros 3 documentos/.test(dc.textContent));
  t('aviso: leídos en el momento, nada se guarda', /No se guarda ning[úu]n archivo/.test(dc.textContent));
  t('capítulo 6: el texto exacto del oficio de veto se integra junto a las votaciones del veto', /Qué dice exactamente el oficio de veto/.test(d.querySelector('#doc-veto').textContent) && /AL ARTÍCULO 40/.test(d.querySelector('#doc-veto').textContent));
  t('capítulo 1: la ficha suma "según el mensaje o moción original"', /Según el mensaje o moción original/.test(d.querySelector('#doc-iniciativa').textContent) && /problema busca resolver/i.test(d.querySelector('#doc-iniciativa').textContent));
  t('índice muestra cuántos documentos se leyeron', /5/.test((d.querySelector('#indice a[href="#documentos"] .n')||{}).textContent||''));
  const co = cards[4];
  t('documento escaneado: aviso de OCR con páginas leídas, confianza y "sin enviarlo a terceros"', co.querySelector('.ocr-aviso') && /12 de 41 páginas/.test(co.textContent) && /88%/.test(co.textContent) && /sin enviarlo a terceros/.test(co.textContent));
  t('documento escaneado: indica que el texto vino de la copia del Senado', /copia publicada por el Senado/.test(co.textContent));
  t('citas leídas por OCR marcadas "por confirmar"', /por confirmar/.test(co.querySelector('.doc-citas').textContent) && !!co.querySelector('.por-confirmar'));
  t('el análisis del documento OCR igual se muestra (objetivo, votación en comisión)', /Fortalecer la fiscalización/.test(co.textContent) && /7 votos a favor/.test(co.textContent));
  t('los documentos con texto normal NO llevan aviso de OCR', cards.slice(0,4).every(c => !c.querySelector('.ocr-aviso')));
  t('sin undefined/null en documentos', !/undefined|null|NaN/.test(dc.textContent));
  const E = cargar(html, {hash:'#boletin=15480-13', sinDocs:true}); await espera(400);
  t('si los documentos fallan, el informe sigue completo y solo ese capítulo avisa con Reintentar', E.doc.querySelector('#informe').style.display !== 'none' && E.doc.querySelectorAll('#cuerpo section.cap').length === 11 && /No se pudieron leer los documentos/.test(E.doc.querySelector('#doc-cuerpo').textContent) && !!E.doc.querySelector('#btn-re-doc'));

  console.log('== 5c. recolector de documentos (python, sin red): extracción y análisis ==');
  const py = require('child_process').spawnSync('python3', ['test_documentos.py'], {encoding:'utf8', cwd: __dirname});
  const rs = (py.stdout||'').trim();
  t('DOCX de veto: 2 observaciones (reemplazar/eliminar), fundamento por artículo, firmantes, resumen', /^\[true/.test(rs), rs + (py.stderr||'').slice(-300));
  t('PDF: extrae texto y detecta la materia del oficio', /^\[true, true/.test(rs));
  t('rechaza descargar desde dominios no oficiales', /^\[true, true, true/.test(rs));
  t('convierte fechas "12 Ago. 2026" a ISO', /^\[true, true, true, true/.test(rs));
  t('informe de comisión: objetivo, expositores y votación en comisión', /^\[true, true, true, true, true/.test(rs), rs);
  t('OCR local: un PDF escaneado (imagen) se convierte en texto y se analiza como veto (2 observaciones, ley 18.010)', /^\[true, true, true, true, true, true/.test(rs), rs);
  t('normalización OCR: "ARTiCULO", "ley No", "Republica" quedan corregidos', rs === '[true, true, true, true, true, true, true]', rs);

  console.log('== 5d. todos los documentos en dos tandas + borrado de memoria al cerrar ==');
  {
    const T = cargar(html, {hash:'#boletin=15480-13', dosTandas:true}); await espera(700);
    const urls = T.win.__urls || [];
    t('pidió la primera tanda y luego el resto (tanda=2)', urls.some(u => /\/api\/documentos\?boletin=15480-13&pid=16006$/.test(u)) && urls.some(u => /tanda=2/.test(u)), urls.join(' | '));
    const dc = T.doc.querySelector('#doc-cuerpo');
    t('el comparado de la segunda tanda aparece en el capítulo 8', /Comparado de prueba/.test(dc.textContent));
    t('el enlace de un documento del Senado dice senado.cl', /senado\.cl ↗/.test(dc.textContent));
    t('ya no queda aviso de "leyendo los otros" tras la segunda tanda', !dc.querySelector('#doc-pendientes'));
    t('el índice suma los documentos de ambas tandas', (T.doc.querySelector('#indice a[href="#documentos"] .n')||{}).textContent === '6');
    t('aviso ciudadano: los documentos se eliminan de la memoria al cerrar', /se eliminan de la memoria del servidor/.test(dc.textContent));
    // cambiar de proyecto o cerrar la pestaña → aviso al servidor para borrar la RAM
    T.win.navigator.sendBeacon = (u) => { T.win.__beacon = (T.win.__beacon||[]).concat(String(u)); return true; };
    T.win.dispatchEvent(new T.win.Event('pagehide'));
    t('al cerrar la página avisa al servidor para eliminar los documentos', (T.win.__beacon||[]).some(u => /\/api\/documentos\/cerrar\?boletin=15480-13&pid=16006/.test(u)), JSON.stringify(T.win.__beacon));
    T.win.dispatchEvent(new T.win.Event('pagehide'));
    t('no repite el aviso si ya no hay nada abierto', (T.win.__beacon||[]).length === 1);
  }
  console.log('== 6. índice, imprimir, ejemplos, dark ==');
  d.querySelector('#indice a[href="#vetos"]').click(); await espera(20);
  t('clic en índice marca capítulo activo', d.querySelector('#indice a[href="#vetos"]').classList.contains('on'));
  d.querySelector('#btn-imprimir').click(); t('botón imprimir llama a window.print', w.__printed === true);
  t('hay estilos de impresión', /@media print/.test(html));
  d.querySelector('#dark-toggle').click(); await espera(20);
  t('modo oscuro se activa y se guarda', d.body.classList.contains('dark') && w.localStorage.getItem('eps_dark') === '1');
  d.querySelector('#dark-toggle').click(); await espera(20);
  t('vuelve a claro', !d.body.classList.contains('dark'));

  console.log('== 7. deep link y errores ==');
  const B = cargar(html, {hash:'#boletin=15480-13'}); await espera(300);
  t('deep link #boletin= arma el informe solo', B.doc.querySelector('#informe').style.display !== 'none' && B.errs.length === 0, JSON.stringify(B.errs.slice(0,2)));
  const C = cargar(html, {hash:'#boletin=99999-99'}); await espera(200);
  t('boletín inexistente: aviso claro y botón Reintentar', /No se pudo armar/.test(C.doc.querySelector('#estado').textContent) && !!C.doc.querySelector('#btn-re'));
  const D = cargar(html, {hash:'#boletin=15480-13', falla:true}); await espera(200);
  t('sin servidor: explica que necesita el modo en vivo', /modo en vivo/.test(D.doc.querySelector('#estado').textContent));
  D.doc.querySelector('#btn-re').click(); await espera(50);
  t('Reintentar vuelve a llamar', (D.win.__urls||[]).length >= 2);

  console.log(`\nRESULTADO INFORME: ${pass} ok, ${fail} fallos`);
  process.exit(fail ? 1 : 0);
})();
