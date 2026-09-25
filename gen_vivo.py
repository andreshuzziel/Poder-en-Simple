#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera dashboard_vivo.html a partir de template_dashboard.html:
convierte el dashboard estático en la versión EN VIVO (descarga al momento, sin base de datos)."""

import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

tpl = open(_p('template_dashboard.html'), encoding='utf-8').read()

# 1) Datos embebidos -> fetch en vivo
old = "const DATA = /*__DATA__*/;"
new = """let DATA = null;
async function cargarEnVivo(silencioso){
  const ov = document.getElementById('overlay');
  const err = document.getElementById('errbox');
  if(!silencioso){ ov.style.display = 'flex'; err.style.display='none'; }
  try{
    const r = await fetch('/api/todo');
    if(!r.ok) throw new Error('HTTP '+r.status);
    DATA = await r.json();
    ov.style.display='none';
    document.getElementById('momento').textContent = 'los datos se actualizan solos cada 15 minutos';
  }catch(e){
    if(silencioso){ console.warn('auto-refresco falló; se mantienen los datos anteriores', e); return; }
    ov.style.display='none'; err.style.display='block';
    err.innerHTML = '<b>No se pudo descargar en vivo.</b><br>'+e.message+
      '<br><button onclick="location.reload()" style="margin-top:8px;padding:8px 14px;border:none;border-radius:8px;background:#1d3a8f;color:#fff;cursor:pointer">Reintentar</button>';
    return;
  }
}"""
assert old in tpl
tpl = tpl.replace(old, new, 1)

# 2) Envolver todo el render en render() y arrancar tras la descarga
tpl = tpl.replace("/* ---------- KPIs principales ---------- */",
                  "function render(){\n/* ---------- KPIs principales ---------- */", 1)
boot = """
} // fin render

(async function(){
  await cargarEnVivo();
  if(DATA){ render(); if(window.pintarEsencial) window.pintarEsencial(); }
  // Auto-refresco silencioso cada 15 min: misma lógica "sin base de datos" —
  // vuelve a descargar al momento, mantiene todo solo en RAM y re-rota los proyectos.
  setInterval(async ()=>{ await cargarEnVivo(true); if(DATA){ render(); if(window.pintarEsencial) window.pintarEsencial(); } }, 15*60*1000);
})();
</script>"""
tpl = tpl.replace("</script>", boot, 1)

# 3) Overlay de carga + mensaje de error
overlay = """
<div id="overlay" style="display:none;position:fixed;inset:0;background:rgba(20,30,70,.92);z-index:99;align-items:center;justify-content:center;flex-direction:column;color:#fff;text-align:center;padding:20px">
  <div style="font-size:44px">📡</div>
  <div style="font-size:20px;font-weight:800;margin-top:12px">Descargando datos en vivo…</div>
  <div style="margin-top:8px;color:#dbe4ff;max-width:520px;font-size:14px">Consultando las fuentes oficiales de ambos poderes (camara.cl, Senado, BCN e InfoLobby) en este momento. Nada queda guardado: al cerrar, los datos desaparecen.</div>
  <div style="margin-top:18px;width:200px;height:5px;background:rgba(255,255,255,.2);border-radius:3px;overflow:hidden">
    <div style="width:40%;height:100%;background:#ffd75e;border-radius:3px;animation:slide 1.2s infinite"></div>
  </div>
</div>
<style>@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(420%)}}</style>
<div id="errbox" style="display:none;position:fixed;inset:0;background:rgba(20,30,70,.95);z-index:99;align-items:center;justify-content:center;flex-direction:column;color:#fff;text-align:center;padding:30px"></div>
"""
tpl = tpl.replace('<header class="hero">', overlay + '\n<header class="hero">', 1)

# 4) Insignia de actualización -> indicador en vivo
tpl = tpl.replace('<span class="badge">🗓️ Actualizado al 17 de septiembre de 2026</span>',
                  '<span class="badge">📡 Datos en vivo · <span id="momento">descargando…</span></span>', 1)

# 5) Pie de página: sin base de datos
tpl = tpl.replace('Este tablero es un resumen educativo.',
                  'Este tablero funciona <b>sin base de datos</b>: cada vez que lo abres descarga la información al momento desde las fuentes oficiales y la mantiene solo en memoria; mientras está abierto se vuelve a actualizar solo cada 15 minutos, y al cerrar la página todo se elimina. Este tablero es un resumen educativo.', 1)

# ---------- ajustes específicos de la versión en vivo ----------
# a) destacadas: el servidor entrega por_grupo
tpl = tpl.replace('v.por_bancada', '(v.por_bancada||v.por_grupo)', 1)

# b) MESAS: versión leída en vivo desde camara.cl
ini = tpl.find('/* ---------- MESAS DIRECTIVAS (verificadas) ---------- */')
fin = tpl.find('/* ---------- ASISTENCIA ---------- */')
assert ini > 0 and fin > ini
vivo_mesas = """/* ---------- MESAS DIRECTIVAS (leídas en vivo) ---------- */
(function(){
  const m = DATA.mesas;
  const filasCam = (m.camara.autoridades||[]).map(([cargo,nombre])=>`<p style="font-size:14.5px;color:var(--texto2);margin-top:4px"><b>${cargo}:</b> ${nombre}</p>`).join('');
  const s = DATA.senado;
  $('#cards-mesas').innerHTML = `
    <div class="card">
      <h3>🏛️ Cámara de Diputadas y Diputados <span class="chip aprobado">✔ leído de camara.cl</span></h3>
      ${filasCam || '<p class="nota-metodo">No disponible en este momento</p>'}
      <p class="nota-metodo mt">Estos nombres se acaban de leer de la página oficial de la Cámara, en este mismo instante.</p>
    </div>
    <div class="card">
      <h3>🏛️ Senado <span class="chip aprobado">✔ elección verificada</span></h3>
      <p style="font-size:20px;font-weight:800;color:var(--azul)">${s.resultado[0].nombre} (RN)</p>
      <p class="nota-metodo">Presidenta del Senado · electa con ${s.resultado[0].votos} votos</p>
      <p style="font-size:14.5px;color:var(--texto2);margin-top:6px"><b>Vicepresidente:</b> ${s.vicepresidencia}</p>
      <p class="nota-metodo mt">Resultado de la votación del 11 de marzo de 2026, al inicio del período.</p>
    </div>`;
})();

"""
tpl = tpl[:ini] + vivo_mesas + tpl[fin:]

# c) textos estáticos -> dinámicos
tpl = tpl.replace("nota:'asesores + operación · mayo 2026'", "nota:'asesores + operación · '+k.mes_gastos")
tpl = tpl.replace('<h3>🏅 Los que más asisten <span class="nota-metodo">(de 69 sesiones)</span></h3>',
                  '<h3>🏅 Los que más asisten <span class="nota-metodo" id="lbl-ses"></span></h3>')
tpl = tpl.replace("$('#rank-mas-asist').innerHTML = mk(mas, 'var(--verde)');",
                  "$('#rank-mas-asist').innerHTML = mk(mas, 'var(--verde)'); $('#lbl-ses').textContent = `(de ${DATA.kpi.total_sesiones} sesiones)`;")
tpl = tpl.replace('Datos de <b>mayo de 2026</b>.', 'Datos de <b id="lbl-mes">…</b>.')
tpl = tpl.replace("$('#txt-gasto-total').textContent =", "$('#lbl-mes').textContent = k.mes_gastos; $('#txt-gasto-total').textContent =")
tpl = tpl.replace('entre enero y septiembre de 2026.', 'entre enero y septiembre de <span id="lbl-anio"></span>.')
tpl = tpl.replace("$('#kpis-vot').innerHTML = [", "$('#lbl-anio').textContent = DATA.votaciones.anio; $('#kpis-vot').innerHTML = [")

# d) nota senado sin mención al Excel
tpl = tpl.replace("En el archivo Excel adjunto puedes ver cómo votó cada uno de los 50 senadores.",
                  "Estos números se descargaron en vivo recién; puedes verlos también en senado.cl.")

# e) sección verificación: redacción en vivo
tpl = tpl.replace('Antes de publicar este tablero, cada dato fue cruzado contra los sitios oficiales del Congreso: <b>camara.cl</b>, <b>senado.cl</b>, los <b>datos abiertos oficiales</b> (opendata.camara.cl) y la <b>BCN</b>. Esto fue lo que verificamos:',
                  'Cada vez que abres esta página, el sistema vuelve a consultar las fuentes oficiales (<b>camara.cl</b>, <b>senado.cl</b> y los <b>datos abiertos</b> de la Cámara). Estas fueron las constataciones realizadas sobre los datos:')

# f) botón re-descargar
tpl = tpl.replace('<a href="#glosario">📖 Glosario</a>',
                  '<a href="#glosario">📖 Glosario</a>\n    <a href="javascript:location.reload()" style="background:#eef4ff;color:var(--azul)">🔄 Re-descargar ahora</a>')

# ---------- audio resumen (si existe) ----------
import base64, os, re as _re
AUDIO = _p('audio_resumen.mp3')
MESES_ES = {1:'ene',2:'feb',3:'mar',4:'abr',5:'may',6:'jun',7:'jul',8:'ago',9:'sep',10:'oct',11:'nov',12:'dic'}
if os.path.exists(AUDIO):
    b64 = base64.b64encode(open(AUDIO, 'rb').read()).decode()
    tpl = tpl.replace('__AUDIO_SRC__', 'data:audio/mpeg;base64,' + b64)
    from datetime import datetime
    m = datetime.fromtimestamp(os.path.getmtime(AUDIO))
    tpl = tpl.replace('__AUDIO_FECHA__', m.strftime('%Y-%m-%d'))
    tpl = tpl.replace('__AUDIO_NOTA__',
        f'🎙️ Voz sintética generada el <b>{m.day} de {MESES_ES[m.month]} de {m.year}</b> a partir de los datos oficiales. '
        'Se renueva solo cada semana con los datos nuevos; el audio anterior se elimina y reemplaza automáticamente.')
else:
    tpl = _re.sub(r'<div class="card" id="card-audio"[\s\S]*?</div>\s*', '', tpl, count=1)
    tpl = tpl.replace('__AUDIO_FECHA__','').replace('__AUDIO_NOTA__','')
    print('aviso: sin audio_resumen.mp3, tarjeta de audio omitida')

open(_p('dashboard_vivo.html'), 'w', encoding='utf-8').write(tpl)
print('OK dashboard_vivo.html', len(tpl), 'bytes')
