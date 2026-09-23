#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera index.html a partir de los datos reales descargados de miradaalcongreso.com"""
import json
from collections import defaultdict, Counter
from datetime import date

# ---------- datos ----------
import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

master = json.load(open(_p('congreso_data.json')))
destacadas = json.load(open(_p('votaciones_destacadas.json')))
snap = json.load(open(_p('data_completa.json')))  # snapshot verificado (votaciones, desglose, senado)

# Fuentes vivas opcionales en /tmp: si existen y son válidas se usan; si no, snapshot verificado.
def _tmp_valid(p, min_bytes=2000):
    import os
    return os.path.exists(p) and os.path.getsize(p) >= min_bytes

# filas crudas de votaciones: prioridad /tmp (recién descargado) → workspace (persistente)
vots = None
if _tmp_valid('/tmp/votaciones2026.json'):
    try:
        vots = json.load(open('/tmp/votaciones2026.json'))['rows']
    except Exception:
        vots = None
if not vots:
    for _cand in (f'votaciones_{date.today().year}.json', 'votaciones_2026.json'):
        if _tmp_valid(_p(_cand), 10000):
            vots = json.load(open(_p(_cand))); break

# nombres oficiales de boletines: /tmp → workspace
nombres_bol = {}
if _tmp_valid('/tmp/boletines_nombres.json', 10):
    nombres_bol = json.load(open('/tmp/boletines_nombres.json'))
elif _tmp_valid(_p('boletines_nombres.json'), 10):
    nombres_bol = json.load(open(_p('boletines_nombres.json')))

def proyectos_clave(rows, nombres):
    """Los proyectos con más votaciones: del mes más reciente y de todo el año."""
    def agg(vrows):
        g = defaultdict(list)
        for r in vrows:
            if r['desc'].startswith('Boletín'):
                g[r['desc'].replace('Boletín N° ', '')].append(r)
        out = []
        for b, vs in g.items():
            ap = sum(1 for x in vs if x['resultado'] == 'Aprobado')
            re = sum(1 for x in vs if x['resultado'] == 'Rechazado')
            vs.sort(key=lambda x: x['fecha'])
            out.append({'boletin': b, 'nombre': nombres.get(b), 'n': len(vs),
                        'aprobadas': ap, 'rechazadas': re,
                        'ultimo': vs[-1]['resultado'], 'ultima_fecha': vs[-1]['fecha'][:10]})
        out = [o for o in out if o['nombre']]
        out.sort(key=lambda o: -o['n'])
        return out
    mes_id = max(r['fecha'][:7] for r in rows)
    NOMB = {'01':'Enero','02':'Febrero','03':'Marzo','04':'Abril','05':'Mayo','06':'Junio',
            '07':'Julio','08':'Agosto','09':'Septiembre','10':'Octubre','11':'Noviembre','12':'Diciembre'}
    return {'mes_label': f"{NOMB[mes_id[5:]]} {mes_id[:4]}", 'anio': mes_id[:4],
            'mes': agg([r for r in rows if r['fecha'].startswith(mes_id)])[:5],
            'anio_lista': agg(rows)[:5]}

if vots:
    tipos = Counter(v['tipo'] for v in vots)
    resultados = Counter(v['resultado'] for v in vots)
    meses = Counter(v['fecha'][:7] for v in vots)
    meses_list = [{'m': k, 'v': v} for k, v in sorted(meses.items())]
    NOMBRES_MES = {'01':'Ene','02':'Feb','03':'Mar','04':'Abr','05':'May','06':'Jun','07':'Jul','08':'Ago','09':'Sep','10':'Oct','11':'Nov','12':'Dic'}
    for x in meses_list:
        x['label'] = NOMBRES_MES[x['m'][5:]]
    desc_count = Counter(v['desc'] for v in vots if v['desc'].startswith('Boletín'))
    proyectos = []
    for b, n in desc_count.most_common(12):
        num = b.replace('Boletín N° ', '')
        if num in nombres_bol:
            proyectos.append({'boletin': num, 'nombre': nombres_bol[num], 'votaciones': n})
    proyectos = proyectos[:8]
    vot_block = {'total': len(vots), 'aprobadas': resultados.get('Aprobado', 0),
                 'rechazadas': resultados.get('Rechazado', 0), 'tipos': dict(tipos),
                 'meses': meses_list, 'proyectos': proyectos,
                 'proyectos_clave': proyectos_clave(vots, nombres_bol)}
else:
    vot_block = snap['votaciones']

# ---- lo más importante por período, para ambos poderes (semana/mes/semestre/año) ----
def proyectos_periodos_est(rows, leyes, nombres):
    from datetime import datetime, timedelta
    hoy = date.today()
    lun = hoy - timedelta(days=hoy.weekday())
    dom = lun + timedelta(days=6)
    MESES_C = {'01':'enero','02':'febrero','03':'marzo','04':'abril','05':'mayo','06':'junio',
               '07':'julio','08':'agosto','09':'septiembre','10':'octubre','11':'noviembre','12':'diciembre'}
    def top_leg(ini, fin):
        g = {}
        for r in rows:
            f = r['fecha'][:10]
            if ini <= f <= fin and r['desc'].startswith('Boletín'):
                g.setdefault(r['desc'].replace('Boletín N° ', ''), []).append(r)
        out = []
        for b, vs in g.items():
            vs.sort(key=lambda x: x['fecha'])
            ult = vs[-1]
            out.append({'b': b, 'n': len(vs), 'margen': abs(ult['si'] - ult['no']),
                        'ult_res': ult['resultado'], 'ult_fecha': ult['fecha'][:10]})
        out.sort(key=lambda o: (-o['n'], o['margen']))
        return out
    def fmt_rango(a, b):
        return f"{a.day} {MESES_C[f'{a.month:02d}'][:3]} – {b.day} {MESES_C[f'{b.month:02d}'][:3]} {b.year}"
    sem_lun, sem_dom, nota_sem = lun, dom, 'esta semana'
    ult_vot = max((r['fecha'][:10] for r in rows), default=None)
    ventanas = [
        {'id':'semana','titulo':'🗓️ Semana','rango':fmt_rango(sem_lun,sem_dom),'nota':nota_sem,
         'ini':sem_lun.isoformat(),'fin':sem_dom.isoformat()},
        {'id':'mes','titulo':'📅 Mes','rango':f"{MESES_C[f'{hoy.month:02d}'].capitalize()} {hoy.year}",'nota':'mes actual',
         'ini':f'{hoy.year}-{hoy.month:02d}-01','fin':f'{hoy.year}-{hoy.month:02d}-31'},
        {'id':'semestre','titulo':'⏳ Semestre','rango':f"jul – dic {hoy.year}",'nota':'segundo semestre',
         'ini':f'{hoy.year}-07-01','fin':f'{hoy.year}-12-31'},
        {'id':'anio','titulo':'🏆 Año','rango':f"ene – dic {hoy.year}",'nota':f'año {hoy.year}',
         'ini':f'{hoy.year}-01-01','fin':f'{hoy.year}-12-31'},
    ]
    if hoy.month <= 6:
        ventanas[2].update({'rango':f"ene – jun {hoy.year}",'nota':'primer semestre',
                            'ini':f'{hoy.year}-01-01','fin':f'{hoy.year}-06-30'})
    def _titular(txt):
        STOP = {'de', 'del', 'la', 'las', 'el', 'los', 'y', 'a', 'en', 'con', 'por', 'un', 'una', 'sobre', 'para', 'al'}
        words = []
        for i, w in enumerate(txt.split()):
            if w.isupper():
                lw = w.lower().capitalize()
                words.append(lw if (i == 0 or lw.lower() not in STOP) else w.lower())
            else:
                words.append(w)
        return ' '.join(words)
    out = []
    for v in ventanas:
        tops = top_leg(v['ini'], v['fin'])
        leg = None
        if tops:
            t = tops[0]
            leg = {'boletin': t['b'], 'nombre': nombres.get(t['b'], f'Boletín {t["b"]}'), 'n': t['n'],
                   'ult_res': t['ult_res'], 'ult_fecha': '-'.join(t['ult_fecha'].split('-')[::-1]),
                   'candidatos': len(tops)}
        en = [l for l in leyes if v['ini'] <= l['_fecha'] <= v['fin']]
        eje = None
        if en:
            l = en[0]
            eje = {'ley': f"Ley {l['nro_norma']}", 'titulo': _titular(l['titulo_norma']),
                   'fecha': l['fecha_publicacion'], 'organismo': _titular(l.get('organismo', '')),
                   'link': l.get('historia_ley') or f"https://www.bcn.cl/leychile/navegar?idNorma={l['idNorma']}",
                   'total': len(en)}
        out.append({'id':v['id'],'titulo':v['titulo'],'rango':v['rango'],'nota':v['nota'],
                    'legislativo':leg,'ejecutivo':eje})
    return {'ventanas': out, 'ultima_fecha_vot': ult_vot,
            'criterio_legislativo': 'el proyecto con más votaciones registradas en la Sala durante el período',
            'criterio_ejecutivo': 'la ley promulgada más reciente del período (las leyes las firma el Presidente)',
            'fuente_ejecutivo': 'LeyChile · Biblioteca del Congreso Nacional'}

pp_block = None
if vots:
    import os as _os
    leyes_p = []
    if _os.path.exists(_p('leyes_promulgadas.json')):
        leyes_p = json.load(open(_p('leyes_promulgadas.json')))
        for l in leyes_p:
            d, m, a = l['fecha_publicacion'].split('-')
            l['_fecha'] = f'{a}-{m}-{d}'
        leyes_p.sort(key=lambda l: l['_fecha'], reverse=True)
    pp_block = proyectos_periodos_est(vots, leyes_p, nombres_bol)

if _tmp_valid('/tmp/gastos.json'):
    gastos_raw = json.load(open('/tmp/gastos.json'))['entries']
    op_total = defaultdict(float)
    for g in gastos_raw:
        for k, v in g.items():
            if k.startswith('ASESOR:') or k == 'diputadoId':
                continue
            try:
                op_total[k] += float(str(v).split(';')[0].replace('.', ''))
            except ValueError:
                pass
    desglose = [{'cat': k, 'v': round(v)} for k, v in sorted(op_total.items(), key=lambda kv: -kv[1])]
else:
    desglose = snap['desglose_op']

senado_block = snap['senado']

dips = master['diputados']
kpi = master['kpi']

# promedios de asistencia efectiva por bancada
banc = defaultdict(list)
for r in dips:
    banc[r['grupo']].append(r)
bancadas = []
for g, rows in banc.items():
    n = len(rows)
    bancadas.append({
        'grupo': g, 'n': n,
        'asist': round(sum(x['asist'] for x in rows)/n, 1),
        'asist_ef': round(sum(x['asist_ef'] for x in rows)/n, 1),
        'inas': round(sum(x['inas'] for x in rows)/n, 1),
        'inas_ef': round(sum(x['inas_ef'] for x in rows)/n, 1),
        'g_tot': round(sum(x['g_tot'] for x in rows)/n),
        'g_per': round(sum(x['g_per'] for x in rows)/n),
        'g_op': round(sum(x['g_op'] for x in rows)/n),
    })
bancadas.sort(key=lambda b: -b['n'])

PADRON_DISTRITOS = json.load(open(_p('padron_distritos.json')))

def _fila_dip(r):
    d = {k: r[k] for k in ('id','nombre','militancia','grupo','asist','asist_ef','inas','inas_ef','g_tot','g_per','g_op','n_ases')}
    d['distrito'] = PADRON_DISTRITOS.get(str(r['id']))
    return d

DATA = {
    'kpi': kpi,
    'bancadas': bancadas,
    'diputados': [_fila_dip(r) for r in dips],
    'votaciones': vot_block,
    'destacadas': destacadas,
    'desglose_op': desglose,
    'senado': senado_block,
    'gobierno': json.load(open(_p('gobierno_snapshot.json'))),
    'proyectos_periodos': pp_block,
    'fechas_clave': json.load(open(_p('fechas_clave.json'))),
    'mesas': {
        'camara': {
            'presidente': 'Jorge Alessandri (UDI)',
            'detalle': 'Electo el 11 de marzo de 2026 con 78 votos, frente a Pamela Jiles (PDG, 75) y Juan Marcelo Valenzuela (1).',
            'vice1': 'Felipe Camaño (Ind-DC) · 1er Vicepresidente',
            'vice2': 'Ximena Ossandón (RN) · 2ª Vicepresidenta',
        },
        'senado': {
            'presidenta': 'Paulina Núñez (RN)',
            'detalle': 'Electa el 11 de marzo de 2026 con 39 votos, frente a Alejandro Kusanovic (2) y 9 abstenciones.',
            'vice': 'Iván Moreira (UDI) · Vicepresidente',
        },
    },
}

# ---------- votos por diputad@ y gasto histórico (en vivo, con respaldo en snapshot) ----------
def extras_en_vivo():
    import sys as _s
    _s.path.insert(0, BASE_DIR)
    import servidor
    votos, ghist = [], []
    try:
        votos = servidor.src_votos_recientes()
    except Exception as e:
        print('votos recientes en vivo fallaron:', e)
    if not votos:
        try: votos = json.load(open(_p('votos_leyes.json')))
        except Exception: pass
    try:
        ghist = servidor.src_gastos_historico()
    except Exception as e:
        print('histórico de gastos en vivo falló:', e)
    if not ghist:
        try: ghist = json.load(open(_p('gastos_hist.json')))
        except Exception: pass
    if votos: json.dump(votos, open(_p('votos_leyes.json'), 'w'), ensure_ascii=False)
    if ghist: json.dump(ghist, open(_p('gastos_hist.json'), 'w'), ensure_ascii=False)
    return votos, ghist

def noticias_en_vivo():
    import sys as _s
    _s.path.insert(0, BASE_DIR)
    import servidor
    nots = {'camara': [], 'senado': [], 'gobierno': []}
    try:
        nots = servidor.src_noticias()
    except Exception as e:
        print('noticias en vivo fallaron:', e)
    if not any(nots.values()):
        try: nots = json.load(open(_p('noticias.json')))
        except Exception: pass
    if any(nots.values()):
        json.dump(nots, open(_p('noticias.json'), 'w'), ensure_ascii=False)
    return nots

VOTOS_LEYES, GASTOS_HIST = extras_en_vivo()
DATA['votos_leyes'] = VOTOS_LEYES
DATA['gastos_hist'] = GASTOS_HIST
DATA['noticias'] = noticias_en_vivo()

html = open(_p('template_dashboard.html'), encoding='utf-8').read()
html = html.replace('/*__DATA__*/', json.dumps(DATA, ensure_ascii=False))

# ---------- audio resumen (si existe) ----------
import base64, os, re as _re
AUDIO = _p('audio_resumen.mp3')
MESES_ES = {1:'ene',2:'feb',3:'mar',4:'abr',5:'may',6:'jun',7:'jul',8:'ago',9:'sep',10:'oct',11:'nov',12:'dic'}
if os.path.exists(AUDIO):
    b64 = base64.b64encode(open(AUDIO, 'rb').read()).decode()
    html = html.replace('__AUDIO_SRC__', 'data:audio/mpeg;base64,' + b64)
    from datetime import datetime
    m = datetime.fromtimestamp(os.path.getmtime(AUDIO))
    html = html.replace('__AUDIO_FECHA__', m.strftime('%Y-%m-%d'))
    html = html.replace('__AUDIO_NOTA__',
        f'🎙️ Voz sintética generada el <b>{m.day} de {MESES_ES[m.month]} de {m.year}</b> a partir de los datos oficiales. '
        'Se renueva solo cada semana con los datos nuevos; el audio anterior se elimina y reemplaza automáticamente.')
else:
    html = _re.sub(r'<div class="card" id="card-audio"[\s\S]*?</div>\s*', '', html, count=1)
    html = html.replace('__AUDIO_FECHA__','').replace('__AUDIO_NOTA__','')
    print('aviso: sin audio_resumen.mp3, tarjeta de audio omitida')

open(_p('index.html'), 'w', encoding='utf-8').write(html)
print('OK index.html', len(html), 'bytes')
