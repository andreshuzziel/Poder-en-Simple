// Tests del INFORME COMPLETO DE PROYECTO (informe_proyecto.html)
// Simula el servidor en vivo (fetch) con una respuesta real recortada de /api/informe?boletin=15480-13 (pensiones, Ley 21.735).
const fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');
let pass = 0, fail = 0;
const t = (name, cond, extra='') => { if (cond) { pass++; console.log('  ✔', name); } else { fail++; console.log('  ✘', name, extra); } };
const espera = ms => new Promise(r => setTimeout(r, ms));
const FIX = JSON.parse(fs.readFileSync(__dirname + '/test_informe_fixture.json', 'utf8'));

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
        return { json: async () => body, ok: true };
      };
    }});
  return { doc: dom.window.document, win: dom.window, errs };
}

(async () => {
  const html = fs.readFileSync('/home/user/informe_proyecto.html', 'utf8');
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
  t('10 capítulos en orden (portada + 9)', caps.length === 10 && caps.map(s=>s.id).join(',') === 'portada,ficha,tramitacion,camara,senado,indicaciones,vetos,urgencias,normas,fuentes', caps.map(s=>s.id).join(','));
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
  t('cada votación tiene botón de plegado y cuerpo', [...vots].every(v => v.querySelector('.btn-plegar') && v.querySelector('.vot-body')));
  t('votaciones de Cámara contraídas de entrada', [...vots].every(v => v.querySelector('.vot-body').style.display === 'none'));
  vots[0].querySelector('.cab').click(); await espera(20);
  t('un clic en el título despliega', vots[0].querySelector('.vot-body').style.display !== 'none' && /Ocultar/.test(vots[0].querySelector('.btn-plegar').textContent) && vots[0].querySelector('.btn-plegar').getAttribute('aria-expanded') === 'true');
  vots[0].querySelector('.btn-plegar').click(); await espera(20);
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
