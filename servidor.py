#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
El Poder en Simple — MODO EN VIVO, SIN BASE DE DATOS.

Cubre los DOS poderes: Legislativo (camara.cl / datos abiertos vía Mirada al
Congreso) y Ejecutivo (bcn.cl + InfoLobby del Consejo para la Transparencia).
Cada vez que el navegador pide datos, este servidor los descarga EN EL MOMENTO
desde las fuentes oficiales. Todo vive únicamente en memoria RAM (dict CACHE);
al detener el servidor no queda ningún dato guardado.
"""
import json, re, time, threading, urllib.request, urllib.parse, gzip, io, ssl
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import os as _os
import os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

PUERTO = 8070
TTL_CACHE = 15 * 60          # segundos que viven los datos en RAM (luego se re-descargan)
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
NS = {'c': 'http://opendata.camara.cl/camaradiputados/v1'}

CACHE = {}                   # <-- "base de datos" efímera: solo RAM
LOCK = threading.Lock()

# ------------------------- utilidades de red -------------------------
def http_get(url, timeout=30, tries=2):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                return data.decode('utf-8', 'ignore')
        except Exception as e:
            last = e; time.sleep(1)
    raise last

def http_get_bytes(url, timeout=60, tries=2, max_bytes=25_000_000):
    """GET binario (PDF/DOCX oficiales). Se mantiene solo en memoria; nunca se escribe en disco."""
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read(max_bytes)
                if r.headers.get('Content-Encoding') == 'gzip':
                    data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                return data, (r.headers.get('Content-Type') or ''), (r.headers.get('Content-Disposition') or '')
        except Exception as e:
            last = e; time.sleep(1)
    raise last

def http_post_json(url, payload, timeout=40, tries=2):
    body = json.dumps(payload).encode()
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers={
                'User-Agent': UA, 'Content-Type': 'application/json', 'Accept-Encoding': 'gzip'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
                return data
        except Exception as e:
            last = e; time.sleep(1)
    raise last

TTL_FALLO = 5 * 60           # si una fuente falló, no se reintenta durante 5 min (evita esperas largas repetidas)

def cached(key, fn, fresh=False):
    """Devuelve el valor vivo de RAM; si no existe o venció, lo descarga al momento.
       Un fallo también se recuerda (poco tiempo) para que una fuente caída no frene toda la página en cada visita."""
    with LOCK:
        hit = CACHE.get(key)
        if hit and not fresh and time.time() - hit['t'] < TTL_CACHE:
            if 'err' in hit:
                if time.time() - hit['t'] < TTL_FALLO:
                    raise hit['err']
            else:
                hit['cached'] = True
                return hit['v']
    try:
        v = fn()
    except Exception as e:
        with LOCK:
            CACHE[key] = {'err': e, 't': time.time()}
        raise
    with LOCK:
        CACHE[key] = {'v': v, 't': time.time(), 'cached': False}
    return v

def olvidar(prefijo):
    """Borra de la RAM todo lo que empiece con ese prefijo (p. ej. los documentos de un proyecto al cerrar su ficha)."""
    with LOCK:
        claves = [k for k in CACHE if k.startswith(prefijo)]
        for k in claves:
            del CACHE[k]
    import gc; gc.collect()
    return len(claves)

def de_latin1(s):
    return s.encode('latin-1', 'ignore').decode('unicode_escape') if '\\x' in s else s

# ------------------------- fuentes en vivo -------------------------
def src_diputados_camara():
    """Padrón oficial de 155 diputad@s desde camara.cl (en vivo)."""
    h = http_get('https://www.camara.cl/diputados/diputados.aspx')
    arts = re.findall(r'<article class="grid-2">(.*?)</article>', h, re.S)
    out = {}
    for a in arts:
        pid = re.search(r'detalle/mociones\.aspx\?prmID=(\d+)', a)
        nom = re.search(r'<h4><a[^>]*>\s*(?:Sra?\. )?([^<]+?)\s*</a></h4>', a)
        par = re.search(r'Partido:\s*([^<]+?)\s*</p>', a)
        dis = re.search(r'Distrito:\s*N°(\d+)', a)
        if pid and nom:
            out[pid.group(1)] = {'nombre': nom.group(1), 'partido': (par.group(1).strip() if par else ''),
                                 'distrito': dis.group(1) if dis else ''}
    return out

PARTIDO_GRUPO = {
    'UDI': 'UDI', 'RN': 'RN/EVO', 'EVOP': 'RN/EVO', 'EVOPOLI': 'RN/EVO',
    'PREP': 'Republicanos', 'PREPUBLICANO': 'Republicanos', 'PNL': 'PNL',
    'FA': 'Frente Amplio', 'CS': 'Frente Amplio', 'RD': 'Frente Amplio',
    'PC': 'Comunistas', 'FRVS': 'Comunistas', 'AH': 'Comunistas',
    'PS': 'PS/PL/PR', 'PL': 'PS/PL/PR', 'PR': 'PS/PL/PR', 'PRSD': 'PS/PL/PR', 'RAD': 'PS/PL/PR',
    'PPD': 'PPD', 'PDC': 'DC', 'DC': 'DC', 'PDG': 'PDG',
    'SC': 'Social Cristiano', 'DEM': 'Demócratas/Amarillos', 'AMAR': 'Demócratas/Amarillos',
}
def grupo_de(partido):
    return PARTIDO_GRUPO.get((partido or '').strip().upper(), 'Independientes')

def src_asistencia(diputados):
    """Asistencia en vivo desde el servicio de datos abiertos (vía Mirada al Congreso)."""
    raw = http_post_json('https://www.miradaalcongreso.com/api/inasistenciasgeneral', {'periodo': '2026-2030'})
    d = json.loads(raw)['entries']
    rows = []
    for it in d['inasistencias']:
        did = str(it['id_congreso']); info = diputados.get(did, {})
        rows.append({'id': did, 'nombre': info.get('nombre', f'Diputad@ {did}'),
                     'partido': info.get('partido', ''), 'grupo': grupo_de(info.get('partido', '')),
                     'inas': it['inasistencias'], 'inas_ef': it['inasistencias_efectivas'],
                     'asist': round(it['asistencia']*100, 1), 'asist_ef': round(it['asistencia_efectiva']*100, 1)})
    return {'total_sesiones': d['total'], 'fecha': d['fecha'], 'rows': rows}

def src_gastos():
    """Gastos en vivo: prueba el mes más reciente disponible (se publica con un mes de desfase)."""
    hoy = date.today(); meses = []
    for k in range(1, 7):
        m = hoy.month - k; y = hoy.year
        while m <= 0: m += 12; y -= 1
        meses.append(f'{y}-{m:02d}')
    for mes in meses:
        try:
            raw = http_post_json('https://www.miradaalcongreso.com/api/gastos', {'periodo': mes}, timeout=30)
            d = json.loads(raw)
            entries = d.get('entries')
            if isinstance(entries, list) and entries:
                return {'mes': mes, 'entries': entries}
        except Exception:
            continue
    raise RuntimeError('No hay gastos publicados aún')

def num(x):
    try: return float(str(x).split(';')[0].replace('.', ''))
    except Exception: return 0.0

def consolidar_gastos(entries):
    gmap = {}
    for g in entries:
        did = str(g['diputadoId']); per = op = 0; na = 0
        for k, v in g.items():
            if k.startswith('ASESOR:'): per += num(v); na += 1
            elif k != 'diputadoId': op += num(v)
        gmap[did] = {'g_per': round(per), 'g_op': round(op), 'g_tot': round(per+op), 'n_ases': na}
    return gmap

def src_votaciones(diputados):
    """Votaciones del año en vivo desde el XML oficial + 2 votaciones destacadas con detalle."""
    anio = date.today().year
    raw = http_post_json('https://www.miradaalcongreso.com/api/votacionesxano', {'param': anio})
    root = ET.fromstring(raw)
    data = []
    for v in root.findall('c:Votacion', NS):
        def g(t):
            e = v.find('c:'+t, NS); return (e.text or '').strip() if e is not None else ''
        data.append({'id': g('Id'), 'desc': g('Descripcion'), 'fecha': g('Fecha'),
                     'si': int(g('TotalSi') or 0), 'no': int(g('TotalNo') or 0), 'abst': int(g('TotalAbstencion') or 0),
                     'resultado': g('Resultado'), 'tipo': g('Tipo')})
    from collections import Counter
    tipos = Counter(v['tipo'] for v in data)
    res = Counter(v['resultado'] for v in data)
    meses = Counter(v['fecha'][:7] for v in data)
    NOMB = {'01':'Ene','02':'Feb','03':'Mar','04':'Abr','05':'May','06':'Jun','07':'Jul','08':'Ago','09':'Sep','10':'Oct','11':'Nov','12':'Dic'}
    meses_list = [{'m': k, 'v': v, 'label': NOMB[k[5:]]} for k, v in sorted(meses.items())]

    # destacados: última votación de ley con boletín + la más reñida del año
    cands = sorted([d for d in data if d['desc'].startswith('Boletín')], key=lambda d: d['fecha'])
    sel = [cands[-1]] if cands else []
    leys = [d for d in data if d['tipo'] == 'Proyecto de Ley' and d['si']+d['no'] >= 80]
    leys.sort(key=lambda d: abs(d['si']-d['no']))
    for d in leys:
        if d['id'] not in {s['id'] for s in sel}:
            sel.append(d); break
    destacadas = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        fut = {ex.submit(detalle_votacion, s, diputados): s for s in sel}
        for f in fut:
            try: destacadas.append(f.result())
            except Exception as e: print('destacada error:', e)
    destacadas.sort(key=lambda d: d['fecha'])

    # proyectos con más votaciones (nombres en vivo)
    desc_count = Counter(d['desc'] for d in data if d['desc'].startswith('Boletín'))
    proyectos = []
    def nombre_bol(b):
        try:
            r = http_post_json('https://www.miradaalcongreso.com/api/votaciones', {'param': b}, timeout=25)
            rr = ET.fromstring(r)
            n = rr.find('c:Nombre', NS)
            return (n.text or '').strip() if n is not None and n.text else None
        except Exception:
            return None
    top = [(b.replace('Boletín N° ', ''), n) for b, n in desc_count.most_common(10)][:6]
    with ThreadPoolExecutor(max_workers=6) as ex:
        nombres = list(ex.map(lambda t: nombre_bol(t[0]), top))
    for (b, n), nom in zip(top, nombres):
        if nom: proyectos.append({'boletin': b, 'nombre': nom, 'votaciones': desc_count['Boletín N° '+b]})

    # ---- proyectos clave: del mes más reciente y de todo el año ----
    mes_id = max((d['fecha'][:7] for d in data), default=None)
    pk = {'mes_label': '', 'anio': str(anio), 'mes': [], 'anio_lista': []}
    if mes_id:
        def _agg(vrows):
            g = {}
            for r in vrows:
                if not r['desc'].startswith('Boletín'): continue
                b = r['desc'].replace('Boletín N° ', '')
                g.setdefault(b, []).append(r)
            out = []
            for b, vs in g.items():
                ap = sum(1 for x in vs if x['resultado'] == 'Aprobado')
                re = sum(1 for x in vs if x['resultado'] == 'Rechazado')
                vs.sort(key=lambda x: x['fecha'])
                out.append({'boletin': b, 'nombre': None, 'n': len(vs), 'aprobadas': ap,
                            'rechazadas': re, 'ultimo': vs[-1]['resultado'], 'ultima_fecha': vs[-1]['fecha'][:10]})
            out.sort(key=lambda o: -o['n'])
            return out
        mes_rows = _agg([d for d in data if d['fecha'].startswith(mes_id)])[:6]
        anio_rows = _agg(data)[:6]
        faltan = sorted({o['boletin'] for o in mes_rows + anio_rows
                         if o['boletin'] not in {p['boletin'] for p in proyectos}})
        with ThreadPoolExecutor(max_workers=6) as ex:
            ns = list(ex.map(nombre_bol, faltan))
        extra = {b: n for b, n in zip(faltan, ns) if n}
        conocido = {p['boletin']: p['nombre'] for p in proyectos}
        for o in mes_rows + anio_rows:
            o['nombre'] = conocido.get(o['boletin']) or extra.get(o['boletin'])
        NOMB = {'01':'Enero','02':'Febrero','03':'Marzo','04':'Abril','05':'Mayo','06':'Junio',
                '07':'Julio','08':'Agosto','09':'Septiembre','10':'Octubre','11':'Noviembre','12':'Diciembre'}
        pk = {'mes_label': f"{NOMB[mes_id[5:]]} {mes_id[:4]}", 'anio': str(anio),
              'mes': [o for o in mes_rows if o['nombre']][:5],
              'anio_lista': [o for o in anio_rows if o['nombre']][:5]}

    return {'total': len(data), 'aprobadas': res.get('Aprobado', 0), 'rechazadas': res.get('Rechazado', 0),
            'tipos': dict(tipos), 'meses': meses_list, 'proyectos': proyectos[:8],
            'proyectos_clave': pk, '_filas': data,
            'destacadas': destacadas, 'anio': anio}

def detalle_votacion(s, diputados):
    raw = http_post_json('https://www.miradaalcongreso.com/api/votacionesDetalle', {'param': int(s['id'])})
    root = ET.fromstring(raw)
    OP = {'1': 'si', '0': 'no', '2': 'abst'}
    agg = {}
    for v in root.find('c:Votos', NS).findall('c:Voto', NS):
        op = OP.get(v.find('c:OpcionVoto', NS).attrib.get('Valor'))
        idc = v.find('c:Diputado', NS).find('c:Id', NS).text
        if not op: continue
        g = grupo_de(diputados.get(str(idc), {}).get('partido', ''))
        agg.setdefault(g, {'si': 0, 'no': 0, 'abst': 0})[op] += 1
    # nombre del proyecto (si es boletín)
    titulo = s['desc']
    if s['desc'].startswith('Boletín'):
        try:
            r = http_post_json('https://www.miradaalcongreso.com/api/votaciones',
                               {'param': s['desc'].replace('Boletín N° ', '')}, timeout=25)
            rr = ET.fromstring(r)
            n = rr.find('c:Nombre', NS)
            if n is not None and n.text: titulo = (n.text or '').strip() + f" ({s['desc']})"
        except Exception: pass
    return {'titulo': titulo, 'fecha': s['fecha'][:10], 'ref': f"{s['desc']} · {s['fecha'][:10]}",
            'resultado': s['resultado'], 'totales': {'si': s['si'], 'no': s['no'], 'abst': s['abst']},
            'por_grupo': agg}

def src_senado():
    """Elección de la presidencia del Senado: se descarga el código vivo de la página oficial de Mirada al Congreso."""
    h = http_get('https://www.miradaalcongreso.com/presidenciasenado')
    m = re.search(r'/_next/static/chunks/pages/presidenciasenado[^"]+\.js', h)
    if not m: raise RuntimeError('no encontré el chunk del senado')
    js = http_get('https://www.miradaalcongreso.com' + m.group(0))
    js = re.sub(r'\\x([0-9a-fA-F]{2})', lambda x: chr(int(x.group(1), 16)), js)
    start = js.find('et={')
    i = js.find('{', start); depth = 0; end = None
    for j in range(i, len(js)):
        if js[j] == '{': depth += 1
        elif js[j] == '}':
            depth -= 1
            if depth == 0: end = j+1; break
    raw = re.sub(r'([{,])([A-ZÁÉÍÓÚÑa-záéíóúñÑ][A-Za-zÁÉÍÓÚÑñ\- ]*?):', r'\1"\2":', js[i:end])
    votos = json.loads(raw)
    from collections import Counter
    c = Counter(votos.values())
    return {'votos': votos,
            'resultado': [
                {'nombre': 'Paulina Núñez', 'votos': c.get('Paulina Núñez', 0), 'color': '#1976d2'},
                {'nombre': 'Alejandro Kusanovic', 'votos': c.get('Alejandro Kusanovic', 0), 'color': '#388e3c'},
                {'nombre': 'Abstención', 'votos': c.get('Abstención', 0), 'color': '#ab47bc'}]}

def src_mesa_camara():
    """Mesa directiva vigente: leída en vivo desde camara.cl."""
    h = http_get('https://www.camara.cl/camara/mesa_directiva.aspx')
    sec = h[h.find('Autoridades que conforman la Mesa'):h.find('Descargar archivo')]
    nombres = re.findall(r'<a href="/diputados/detalle[^>]*>\s*(?:<h5>|<h4>)?\s*(?:Sra?\. )?([A-ZÁÉÍÓÚÑa-záéíóúñA-ZÁÉÍÓÚÑ .]+?)\s*</a>', sec)
    cargos = re.findall(r'(Presidente|Primer Vicepresidente|Segunda Vicepresidenta|Segundo Vicepresidente)', sec)
    return list(zip([c.strip() for c in cargos], nombres)) if cargos else []

def src_votos_recientes():
    """Cómo votó cada diputad@ en las últimas leyes (detalle oficial de cada votación)."""
    anio = date.today().year
    raw = http_post_json('https://www.miradaalcongreso.com/api/votacionesxano', {'param': anio})
    root = ET.fromstring(raw)
    filas = []
    for v in root.findall('c:Votacion', NS):
        def g(t):
            e = v.find('c:'+t, NS); return (e.text or '').strip() if e is not None else ''
        filas.append({'id': g('Id'), 'desc': g('Descripcion'), 'fecha': g('Fecha'),
                      'resultado': g('Resultado'), 'tipo': g('Tipo')})
    leys = [f for f in filas if f['tipo'] == 'Proyecto de Ley' and f['desc'].startswith('Boletín')]
    leys.sort(key=lambda f: f['fecha'], reverse=True)
    sel = leys[:12]

    def det(s):
        try:
            raw = http_post_json('https://www.miradaalcongreso.com/api/votacionesDetalle', {'param': int(s['id'])})
            root2 = ET.fromstring(raw)
            OP = {'1': 'S', '0': 'N', '2': 'A'}
            votos = {}
            nv = root2.find('c:Votos', NS)
            for vo in (nv.findall('c:Voto', NS) if nv is not None else []):
                op = OP.get(vo.find('c:OpcionVoto', NS).attrib.get('Valor'))
                idc = vo.find('c:Diputado', NS).find('c:Id', NS).text
                if op:
                    votos[str(idc)] = op
            titulo = s['desc']
            try:
                r = http_post_json('https://www.miradaalcongreso.com/api/votaciones',
                                   {'param': s['desc'].replace('Boletín N° ', '')}, timeout=25)
                n = ET.fromstring(r).find('c:Nombre', NS)
                if n is not None and n.text:
                    titulo = (n.text or '').strip()
            except Exception:
                pass
            return {'ref': s['desc'].replace('Boletín N° ', ''), 'fecha': s['fecha'][:10],
                    'resultado': s['resultado'], 'titulo': titulo, 'votos': votos}
        except Exception:
            return None

    out = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(det, sel):
            if r:
                out.append(r)
    out.sort(key=lambda r: r['fecha'], reverse=True)
    # una sola votación por proyecto (la más reciente): más variedad para la ciudadanía
    vistos, unicos = set(), []
    for r in out:
        if r['ref'] in vistos:
            continue
        vistos.add(r['ref']); unicos.append(r)
    return unicos

def src_gastos_historico():
    """Gasto total mensual de la Cámara en los últimos meses publicados (Transparencia)."""
    hoy = date.today()
    cand = []
    for k in range(1, 13):
        m = hoy.month - k; y = hoy.year
        while m <= 0: m += 12; y -= 1
        cand.append(f'{y}-{m:02d}')

    def uno(mes):
        try:
            raw = http_post_json('https://www.miradaalcongreso.com/api/gastos', {'periodo': mes}, timeout=30)
            entries = json.loads(raw).get('entries')
            if not isinstance(entries, list) or not entries:
                return None
            tot = 0
            for g in entries:
                for k2, v in g.items():
                    if k2 != 'diputadoId':
                        tot += num(v)
            return {'mes': mes, 'total': round(tot), 'n': len(entries)}
        except Exception:
            return None

    out = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(uno, cand):
            if r:
                out.append(r)
    out.sort(key=lambda r: r['mes'])
    return out[-6:]

# ------------------------- noticias del día (fuentes oficiales) -------------------------
MESES_ES_NUM = {'enero':'01','febrero':'02','marzo':'03','abril':'04','mayo':'05','junio':'06',
                'julio':'07','agosto':'08','septiembre':'09','octubre':'10','noviembre':'11','diciembre':'12'}
MESES_ABREV = {'ene':'01','feb':'02','mar':'03','abr':'04','may':'05','jun':'06',
               'jul':'07','ago':'08','sep':'09','sept':'09','oct':'10','nov':'11','dic':'12'}

def http_get_noverify(url, timeout=20):
    """GET con verificación SSL relajada (prensa.presidencia.cl tiene certificado defectuoso)."""
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        data = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
        return data.decode('utf-8', 'ignore')

def _dedupe_cap(items, n=6):
    vistos, un = set(), []
    for it in items:
        if it['url'] in vistos:
            continue
        vistos.add(it['url']); un.append(it)
    return un[:n]

def noticias_camara():
    h = http_get('https://www.camara.cl/cms/', timeout=25)
    items = []
    for m in re.finditer(r'<a\s+href="(https://www\.camara\.cl/cms/(\d{4})/(\d{2})/(\d{2})/[^"]+)"[^>]*>([\s\S]{0,600}?)</a>', h):
        url, a, mm, dd, inner = m.groups()
        tit = re.sub(r'<[^>]+>', ' ', inner); tit = re.sub(r'\s+', ' ', tit).strip()
        if len(tit) < 15:
            continue
        items.append({'titulo': tit[:200], 'fecha': f'{a}-{mm}-{dd}', 'url': url})
    items.sort(key=lambda x: x['fecha'], reverse=True)
    return _dedupe_cap(items)

def noticias_senado():
    h = http_get('https://www.senado.cl/comunicaciones/noticias', timeout=25)
    partes = re.split(r'<a\s[^>]*href="(/comunicaciones/noticias/[^"]+)"', h)
    items = []
    for i in range(1, len(partes)-1, 2):
        slug, bloq = partes[i], partes[i+1][:2500]
        tit = re.search(r'<h[23][^>]*>\s*([^<]{15,250})', bloq)
        if not tit:
            continue
        fch = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+(\d{4})', bloq)
        fecha = ''
        if fch:
            mm = MESES_ES_NUM.get(fch.group(2).lower(), '')
            if mm:
                fecha = f'{fch.group(3)}-{mm}-{int(fch.group(1)):02d}'
        items.append({'titulo': tit.group(1).strip()[:200], 'fecha': fecha, 'url': 'https://www.senado.cl'+slug})
    return _dedupe_cap(items)

def noticias_gobierno():
    h = http_get_noverify('https://prensa.presidencia.cl/')
    items = []
    pat = r"<a\s+href=['\"]((?:comunicado|fotonoticia|declaracion)\.aspx\?id=\d+)['\"][^>]*>([\s\S]{15,400}?)</a>"
    for m in re.finditer(pat, h):
        href, inner = m.groups()
        tit = re.sub(r'<[^>]+>', ' ', inner); tit = re.sub(r'\s+', ' ', tit).strip()
        if len(tit) < 15:
            continue
        # fecha: "10 SEPT. 2026" en el bloque siguiente (si existe)
        fecha = ''
        sig = h[m.end():m.end()+1200]
        fch = re.search(r'(\d{1,2})\s+([A-Za-zÑñ]{3,5})\.?\s+(\d{4})', sig)
        if fch:
            mm = MESES_ABREV.get(fch.group(2).lower().rstrip('.'), '')
            if mm:
                fecha = f'{fch.group(3)}-{mm}-{int(fch.group(1)):02d}'
        items.append({'titulo': tit[:200], 'fecha': fecha, 'url': 'https://prensa.presidencia.cl/'+href})
    return _dedupe_cap(items)

def src_noticias():
    """Titulares del día desde 3 fuentes oficiales: Cámara, Senado y Presidencia."""
    out = {'camara': [], 'senado': [], 'gobierno': []}
    with ThreadPoolExecutor(max_workers=3) as ex:
        f_cam = ex.submit(noticias_camara)
        f_sen = ex.submit(noticias_senado)
        f_gob = ex.submit(noticias_gobierno)
        for clave, f in (('camara', f_cam), ('senado', f_sen), ('gobierno', f_gob)):
            try:
                out[clave] = f.result()
            except Exception as e:
                print(f'noticias {clave}:', e)
    return out

# ------------------------- gobierno (poder ejecutivo) -------------------------
MAPA_SUBSE_MIN = {
 'SUBSECRETARÍA DEL INTERIOR': 'Ministerio del Interior',
 'SUBSECRETARÍA DE RELACIONES EXTERIORES': 'Ministerio de Relaciones Exteriores',
 'SUBSECRETARIA PARA LAS FUERZAS ARMADAS': 'Ministerio de Defensa Nacional',
 'SUBSECRETARÍA DE HACIENDA': 'Ministerio de Hacienda',
 'SUBSECRETARÍA GENERAL DE LA PRESIDENCIA': 'Ministerio Secretaría General de la Presidencia',
 'SUBSECRETARIA GENERAL DE GOBIERNO': 'Ministerio Secretaría General de Gobierno',
 'SUBSECRETARÍA DE ECONOMÍA': 'Ministerio de Economía, Fomento y Turismo',
 'SUBSECRETARIA DE EVALUACIÓN SOCIAL': 'Ministerio de Desarrollo Social y Familia',
 'SUBSECRETARÍA DE EDUCACIÓN': 'Ministerio de Educación',
 'SUBSECRETARÍA DE JUSTICIA': 'Ministerio de Justicia y Derechos Humanos',
 'SUBSECRETARÍA DEL TRABAJO': 'Ministerio del Trabajo y Previsión Social',
 'SUBSECRETARÍA DE OBRAS PÚBLICAS': 'Ministerio de Obras Públicas',
 'SUBSECRETARIA DE TRANSPORTES': 'Ministerio de Transportes y Telecomunicaciones',
 'SUBSECRETARÍA DE SALUD PÚBLICA': 'Ministerio de Salud',
 'SUBSECRETARIA DE VIVIENDA Y URBANISMO': 'Ministerio de Vivienda y Urbanismo',
 'SUBSECRETARÍA DE AGRICULTURA': 'Ministerio de Agricultura',
 'SUBSECRETARÍA DE MINERÍA': 'Ministerio de Minería',
 'SUBSECRETARÍA DE BIENES NACIONALES': 'Ministerio de Bienes Nacionales',
 'SUBSECRETARIA DE ENERGÍA': 'Ministerio de Energía',
 'SUBSECRETARÍA DEL MEDIO AMBIENTE': 'Ministerio del Medio Ambiente',
 'SUBSECRETARIA DEL DEPORTE': 'Ministerio del Deporte',
 'Subsecretaría de la Mujer y la Equidad de Género': 'Ministerio de la Mujer y la Equidad de Género',
 'Subsecretaria de las Culturas y las Artes': 'Ministerio de las Culturas, las Artes y el Patrimonio',
 'Subsecretaría de Ciencia, Tecnología, Conocimiento e Innovación': 'Ministerio de Ciencia, Tecnología, Conocimiento e Innovación',
 'Subsecretaría de Seguridad Pública': 'Ministerio de Seguridad Pública',
}

def _sparql_infolobby(q, timeout=150):
    url = 'http://datos.infolobby.cl/sparql?query=' + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as x:
        return json.loads(x.read().decode('utf-8', 'replace'))

def src_gobierno():
    """Gobierno en vivo: Presidente (BCN Historia Política) + gabinete (InfoLobby,
    registro oficial de la Ley del Lobby del Consejo para la Transparencia)."""
    # --- Presidente de la República (fuente oficial: bcn.cl) ---
    pres = None
    try:
        h = http_get('https://www.bcn.cl/historiapolitica/presidentes_de_la_republica')
        txt = re.sub(r'<[^>]+>', '|', h); txt = re.sub(r'\|+', '|', txt); txt = re.sub(r'\s+', ' ', txt)
        m = re.search(r'\|\s*([^|]{6,60}?)\s*[\s|]*\s*Presidente de la República, desde el (11 de marzo de \d{4}) a la fecha', txt)
        if m:
            pres = {'nombre': m.group(1).strip(), 'desde': m.group(2).strip(),
                    'cargo': 'Presidente de la República',
                    'fuente': 'https://www.bcn.cl/historiapolitica/presidentes_de_la_republica'}
    except Exception as e:
        print('gobierno/presidente error:', e)

    # --- Gabinete (InfoLobby: cada ministerio registra a su ministro/a como sujeto pasivo) ---
    q1 = ('PREFIX cplt: <http://datos.infolobby.cl/ontologia/cplt#> '
          'PREFIX foaf: <http://xmlns.com/foaf/0.1/> '
          'SELECT ?nombre ?cargo ?inst ?reg WHERE { GRAPH <http://datos.infolobby.cl/infolobby> { '
          '?p a cplt:Pasivo ; foaf:name ?nombre ; cplt:descripcion ?cargo ; cplt:registradoPor ?inst ; cplt:fechaRegistro ?reg . '
          'FILTER(CONTAINS(?cargo,"Ministro") || CONTAINS(?cargo,"Ministra")) } } LIMIT 1000')
    filas = _sparql_infolobby(q1)['results']['bindings']
    cods = sorted({b['inst']['value'].split('/')[-1] for b in filas})
    values = ' '.join(f'<http://datos.infolobby.cl/infolobby/institucion/{c}>' for c in cods)
    q2 = ('PREFIX foaf: <http://xmlns.com/foaf/0.1/> SELECT ?i ?n WHERE { GRAPH <http://datos.infolobby.cl/infolobby> { '
          f'VALUES ?i {{ {values} }} . ?i foaf:name ?n }} }}')
    inst = {b['i']['value'].split('/')[-1]: b['n']['value'].strip()
            for b in _sparql_infolobby(q2, timeout=60)['results']['bindings']}
    cod2min = {c: MAPA_SUBSE_MIN[n] for c, n in inst.items() if n in MAPA_SUBSE_MIN}
    best = {}
    for b in filas:
        cod = b['inst']['value'].split('/')[-1]
        if cod not in cod2min:
            continue
        cargo = b['cargo']['value'].strip()
        if not re.match(r'^Ministr[oa]', cargo) or 'Subrogante' in cargo:
            continue
        reg = b['reg']['value'][:10]
        minn = cod2min[cod]
        if minn not in best or reg > best[minn]['registro']:
            nom = ' '.join(w.title() if w.isupper() else w for w in b['nombre']['value'].strip().split())
            best[minn] = {'ministro': nom, 'cargo': cargo, 'registro': reg,
                          'subrogante': bool(re.search(r'\(S\)|\(s\)|\(A\)', cargo))}
    gabinete = [{'ministerio': k, **v} for k, v in sorted(best.items())]
    return {'presidente': pres, 'gabinete': gabinete,
            'fuente_gabinete': 'https://www.infolobby.cl (Consejo para la Transparencia · Ley del Lobby)',
            'nota': 'Registro oficial de sujetos pasivos de la Ley del Lobby. "(S)" = subrogante: ejerce el cargo temporalmente.'}

# ------------------------- proyectos por período (ambos poderes) -------------------------
def src_leyes_promulgadas():
    """Leyes promulgadas (acto del Gobierno): servicio oficial de LeyChile (BCN)."""
    raw = http_get('https://servicios-leychile.bcn.cl/portada/get_ultimas_leyes_publicadas?cantidad=300', timeout=60)
    leyes = json.loads(raw)
    for l in leyes:
        d, m, a = l['fecha_publicacion'].split('-')
        l['_fecha'] = f'{a}-{m}-{d}'
    leyes.sort(key=lambda l: l['_fecha'], reverse=True)
    return leyes

def _nombre_boletin(b):
    try:
        r = http_post_json('https://www.miradaalcongreso.com/api/votaciones', {'param': b}, timeout=25)
        rr = ET.fromstring(r)
        n = rr.find('c:Nombre', NS)
        return (n.text or '').strip() if n is not None and n.text else None
    except Exception:
        return None

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

def proyectos_periodos(data_vot, leyes):
    """El hito más importante de cada período, para ambos poderes.
    Legislativo: el proyecto más votado de la ventana. Ejecutivo: la última ley promulgada."""
    anio = date.today().year
    filas = data_vot.get('_filas') or []
    hoy = date.today()
    lun = hoy - timedelta(days=hoy.weekday())
    dom = lun + timedelta(days=6)
    MESES_C = {'01':'enero','02':'febrero','03':'marzo','04':'abril','05':'mayo','06':'junio',
               '07':'julio','08':'agosto','09':'septiembre','10':'octubre','11':'noviembre','12':'diciembre'}

    def top_leg(ini, fin):
        g = {}
        for r in filas:
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

    # ventana semanal: la semana actual para ambos poderes
    sem_lun, sem_dom, nota_sem = lun, dom, 'esta semana'
    ult_vot = max((r['fecha'][:10] for r in filas), default=None)
    ventanas = [
        {'id': 'semana',   'titulo': '🗓️ Semana',  'rango': fmt_rango(sem_lun, sem_dom), 'nota': nota_sem,
         'ini': sem_lun.isoformat(), 'fin': sem_dom.isoformat()},
        {'id': 'mes',      'titulo': '📅 Mes',     'rango': f"{MESES_C[f'{hoy.month:02d}'].capitalize()} {hoy.year}", 'nota': 'mes actual',
         'ini': f'{hoy.year}-{hoy.month:02d}-01', 'fin': f'{hoy.year}-{hoy.month:02d}-31'},
        {'id': 'semestre', 'titulo': '⏳ Semestre', 'rango': f"jul – dic {hoy.year}", 'nota': 'segundo semestre',
         'ini': f'{hoy.year}-07-01', 'fin': f'{hoy.year}-12-31'},
        {'id': 'anio',     'titulo': '🏆 Año',     'rango': f"ene – dic {hoy.year}", 'nota': f'año {hoy.year}',
         'ini': f'{hoy.year}-01-01', 'fin': f'{hoy.year}-12-31'},
    ]
    if hoy.month <= 6:
        ventanas[2].update({'rango': f"ene – jun {hoy.year}", 'nota': 'primer semestre',
                            'ini': f'{hoy.year}-01-01', 'fin': f'{hoy.year}-06-30'})

    out = []
    for v in ventanas:
        # Legislativo: proyecto más votado del período
        tops = top_leg(v['ini'], v['fin'])
        leg = None
        if tops:
            t = tops[0]
            nombre = _nombre_boletin(t['b']) or f'Boletín {t["b"]}'
            leg = {'boletin': t['b'], 'nombre': nombre, 'n': t['n'],
                   'ult_res': t['ult_res'], 'ult_fecha': '-'.join(t['ult_fecha'].split('-')[::-1]),
                   'candidatos': len(tops)}
        # Ejecutivo: última ley promulgada del período
        en = [l for l in leyes if v['ini'] <= l['_fecha'] <= v['fin']]
        eje = None
        if en:
            l = en[0]
            eje = {'ley': f"Ley {l['nro_norma']}", 'titulo': _titular(l['titulo_norma']),
                   'fecha': l['fecha_publicacion'], 'organismo': _titular(l.get('organismo', '')),
                   'link': l.get('historia_ley') or f"https://www.bcn.cl/leychile/navegar?idNorma={l['idNorma']}",
                   'total': len(en)}
        out.append({'id': v['id'], 'titulo': v['titulo'], 'rango': v['rango'], 'nota': v['nota'],
                    'legislativo': leg, 'ejecutivo': eje})
    return {'ventanas': out, 'ultima_fecha_vot': ult_vot,
            'criterio_legislativo': 'el proyecto con más votaciones registradas en la Sala durante el período',
            'criterio_ejecutivo': 'la ley promulgada más reciente del período (las leyes las firma el Presidente)',
            'fuente_ejecutivo': 'LeyChile · Biblioteca del Congreso Nacional'}

# ------------------------- agregador en vivo -------------------------
def armar_todo(fresh=False):
    t0 = time.time()
    meta = {'fetched_at': datetime.now().isoformat(timespec='seconds'),
            'persistencia': 'SOLO MEMORIA RAM — nada se guarda en disco; al detener el servidor los datos desaparecen',
            'cache_ttl_min': TTL_CACHE//60, 'fuentes': {}}
    with ThreadPoolExecutor(max_workers=12) as ex:
        f_dip = ex.submit(cached, 'diputados_camara', src_diputados_camara, fresh)
        f_sen = ex.submit(cached, 'senado', src_senado, fresh)
        f_mesa = ex.submit(cached, 'mesa_camara', src_mesa_camara, fresh)
        f_gas = ex.submit(cached, 'gastos_raw', src_gastos, fresh)
        f_gob = ex.submit(cached, 'gobierno', src_gobierno, fresh)
        f_ley = ex.submit(cached, 'leyes_promulgadas', src_leyes_promulgadas, fresh)
        f_ghist = ex.submit(cached, 'gastos_hist', src_gastos_historico, fresh)
        f_vrec = ex.submit(cached, 'votos_recientes', src_votos_recientes, fresh)
        f_not = ex.submit(cached, 'noticias', src_noticias, fresh)
        diputados = f_dip.result()
        meta['fuentes']['Padrón de diputad@s (camara.cl)'] = f'{len(diputados)} diputad@s'
        f_asi = ex.submit(cached, 'asistencia', lambda: src_asistencia(diputados), fresh)
        gastos = f_gas.result()
        gmap = consolidar_gastos(gastos['entries'])
        asist = f_asi.result()
        senado = f_sen.result()
        try:
            mesa = f_mesa.result()
        except Exception as e:                     # camara.cl lento o caído: no se cae todo el tablero
            print('mesa Cámara no disponible:', type(e).__name__, e)
            mesa = []
            try:
                mesa = json.load(open(_p('data_completa.json'))).get('mesas', {}).get('camara', {}).get('autoridades') or []
            except Exception:
                pass
            meta['fuentes']['Mesa de la Cámara (camara.cl)'] = 'sin respuesta ahora; se muestra la última conocida' if mesa else 'no disponible en este momento'
        f_vot = ex.submit(cached, 'votaciones', lambda: src_votaciones(diputados), fresh)
        vot = f_vot.result()
        try:
            gobierno = f_gob.result()
            meta['fuentes']['Gobierno (bcn.cl + InfoLobby)'] = \
                f"{len(gobierno['gabinete'])} ministerios" + (' · presidente OK' if gobierno['presidente'] else '')
        except Exception as e:
            print('gobierno no disponible:', e)
            gobierno = None
            meta['fuentes']['Gobierno (bcn.cl + InfoLobby)'] = 'no disponible en este momento'
        try:
            leyes = f_ley.result()
            meta['fuentes']['Leyes promulgadas (LeyChile)'] = f"{sum(1 for l in leyes if l['_fecha'][:4] == str(date.today().year))} leyes este año"
        except Exception as e:
            print('leyes promulgadas no disponibles:', e)
            leyes = []
            meta['fuentes']['Leyes promulgadas (LeyChile)'] = 'no disponible en este momento'
        try:
            votos_rec = f_vrec.result()
            meta['fuentes']['Detalle de votaciones (voto por diputad@)'] = f"{len(votos_rec)} leyes recientes con voto nominal"
        except Exception as e:
            print('votos recientes no disponibles:', e)
            votos_rec = []
            meta['fuentes']['Detalle de votaciones (voto por diputad@)'] = 'no disponible en este momento'
        try:
            gastos_hist = f_ghist.result()
            meta['fuentes']['Histórico mensual de gastos'] = f"{len(gastos_hist)} meses publicados"
        except Exception as e:
            print('histórico de gastos no disponible:', e)
            gastos_hist = []
            meta['fuentes']['Histórico mensual de gastos'] = 'no disponible en este momento'
        try:
            noticias = f_not.result()
            n_tot = sum(len(v) for v in noticias.values())
            meta['fuentes']['Noticias oficiales del día'] = f"{n_tot} titulares (Cámara {len(noticias['camara'])} · Senado {len(noticias['senado'])} · Presidencia {len(noticias['gobierno'])})"
        except Exception as e:
            print('noticias no disponibles:', e)
            noticias = {'camara': [], 'senado': [], 'gobierno': []}
            meta['fuentes']['Noticias oficiales del día'] = 'no disponible en este momento'
    periodos = proyectos_periodos(vot, leyes)
    vot.pop('_filas', None)

    # merge asistencia + gastos + distrito oficial
    filas = []
    for r in asist['rows']:
        g = gmap.get(r['id'], {'g_per': 0, 'g_op': 0, 'g_tot': 0, 'n_ases': 0})
        filas.append({**r, **g, 'militancia': r['partido'],
                      'distrito': diputados.get(r['id'], {}).get('distrito')})
    MESES = {'01':'Enero','02':'Febrero','03':'Marzo','04':'Abril','05':'Mayo','06':'Junio',
             '07':'Julio','08':'Agosto','09':'Septiembre','10':'Octubre','11':'Noviembre','12':'Diciembre'}
    try:
        mes_legible = f"{MESES[gastos['mes'][5:7]]} {gastos['mes'][:4]}"
    except Exception:
        mes_legible = gastos['mes']
    import statistics
    kpi = {'n_diputados': len(filas), 'total_sesiones': asist['total_sesiones'],
           'fecha_actualizacion': asist['fecha'],
           'asistencia_promedio': round(statistics.mean(x['asist'] for x in filas), 1),
           'asistencia_efectiva_prom': round(statistics.mean(x['asist_ef'] for x in filas), 1),
           'inasistencias_totales': sum(x['inas'] for x in filas),
           'inasistencias_efectivas_totales': sum(x['inas_ef'] for x in filas),
           'gasto_total_camara': sum(x['g_tot'] for x in filas),
           'gasto_promedio': round(statistics.mean(x['g_tot'] for x in filas)) if filas else 0,
           'gasto_personal_total': sum(x['g_per'] for x in filas),
           'gasto_operacional_total': sum(x['g_op'] for x in filas),
           'mes_gastos': mes_legible, 'mes_gastos_id': gastos['mes'], 'periodo': '2026-2030'}
    from collections import defaultdict
    gagg = defaultdict(lambda: {'n': 0, 'asist': [], 'asist_ef': [], 'inas': [], 'inas_ef': [], 'g_tot': 0, 'g_per': 0, 'g_op': 0})
    for r in filas:
        a = gagg[r['grupo']]
        a['n'] += 1; a['asist'].append(r['asist']); a['asist_ef'].append(r['asist_ef'])
        a['inas'].append(r['inas']); a['inas_ef'].append(r['inas_ef'])
        a['g_tot'] += r['g_tot']; a['g_per'] += r['g_per']; a['g_op'] += r['g_op']
    bancadas = [{'grupo': k, 'n': v['n'],
                 'asist': round(sum(v['asist'])/v['n'], 1), 'asist_ef': round(sum(v['asist_ef'])/v['n'], 1),
                 'inas': round(sum(v['inas'])/v['n'], 1), 'inas_ef': round(sum(v['inas_ef'])/v['n'], 1),
                 'g_tot': round(v['g_tot']/v['n']), 'g_per': round(v['g_per']/v['n']), 'g_op': round(v['g_op']/v['n'])}
                for k, v in gagg.items()]
    bancadas.sort(key=lambda b: -b['n'])

    # desglose operacional de toda la Cámara
    cats = defaultdict(float)
    for g in gastos['entries']:
        for k, v in g.items():
            if not k.startswith('ASESOR:') and k != 'diputadoId': cats[k] += num(v)
    desglose = [{'cat': k, 'v': round(v)} for k, v in sorted(cats.items(), key=lambda kv: -kv[1])]

    top_votos = sum(r['votos'] for r in senado['resultado'])
    mesa_out = {'camara': {'autoridades': mesa}, 'senado': {}}

    meta['tiempo_construccion_s'] = round(time.time()-t0, 1)
    return {'kpi': kpi, 'bancadas': bancadas, 'diputados': filas, 'votaciones': vot,
            'destacadas': vot.get('destacadas', []),
            'desglose_op': desglose,
            'senado': {'resultado': senado['resultado'], 'total': top_votos,
                       'vicepresidencia': 'Iván Moreira con 37 votos y 12 abstenciones (senado.cl)'},
            'mesas': mesa_out, 'gobierno': gobierno, 'proyectos_periodos': periodos,
            'votos_leyes': votos_rec, 'gastos_hist': gastos_hist, 'noticias': noticias,
            'fechas_clave': json.load(open(_p('fechas_clave.json'))), 'meta': meta}

# ------------------------- servidor HTTP -------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        try:
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            pass   # el navegador cerró la pestaña antes de recibir la respuesta: no es un error del servidor

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, fmt, *args):
        if not str(args[1] if len(args) > 1 else '').startswith(('200', '302', '304')):
            super().log_message(fmt, *args)

    def do_POST(self):
        # sendBeacon del navegador al cerrar la ficha de un proyecto → borrar sus documentos de la RAM
        if urllib.parse.urlparse(self.path).path == '/api/documentos/cerrar':
            return self.do_GET()
        self._json({'error': 'no disponible'}, 404)

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path in ('/', '/index.html'):
            html = open(_p('dashboard_vivo.html'), 'rb').read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif p.path == '/api/todo':
            fresh = urllib.parse.parse_qs(p.query).get('fresh', ['0'])[0] == '1'
            try:
                self._json(cached('todo', lambda: armar_todo(fresh=fresh), fresh))
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json({'error': str(e)}, 500)
        elif p.path in ('/calendario', '/calendario_votaciones.html'):
            try:
                html = open(_p('calendario_votaciones.html'), 'rb').read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            except FileNotFoundError:
                self.send_response(404); self.end_headers()
        elif p.path in ('/proxima', '/proxima_eleccion.html'):
            try:
                html = open(_p('proxima_eleccion.html'), 'rb').read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            except FileNotFoundError:
                self.send_response(404); self.end_headers()
        elif p.path in ('/elecciones', '/elecciones_chile.html'):
            try:
                html = open(_p('elecciones_chile.html'), 'rb').read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            except FileNotFoundError:
                self.send_response(404); self.end_headers()
        elif p.path in ('/buscador', '/buscador_avanzado.html'):
            try:
                html = open(_p('buscador_avanzado.html'), 'rb').read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(html)))
                self.end_headers()
                self.wfile.write(html)
            except FileNotFoundError:
                self.send_response(404); self.end_headers()
        elif p.path == '/api/buscar':          # buscador avanzado: consulta las fuentes oficiales al momento
            q = urllib.parse.parse_qs(p.query).get('q', [''])[0]
            try:
                import buscador
                self._json(buscador.buscar(q))
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json({'error': str(e), 'resultados': []}, 500)
        elif p.path == '/api/informe':         # informe completo de un proyecto (todas las votaciones nominales, vetos, contexto)
            qs = urllib.parse.parse_qs(p.query)
            try:
                import buscador
                self._json(buscador.informe_proyecto(qs.get('boletin', [''])[0]))
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json({'error': str(e)}, 500)
        elif p.path == '/api/documentos':      # documentos oficiales del proyecto leídos en memoria (informes, oficios, veto, mensaje)
            qs = urllib.parse.parse_qs(p.query)
            bol = qs.get('boletin', [''])[0].strip(); pid = qs.get('pid', [''])[0].strip(); fecha = qs.get('fecha', [''])[0].strip()
            try:
                import documentos, buscador
                if not pid:
                    f = buscador.ficha_proyecto(bol)
                    pid = ((f.get('camara') or {}).get('pid')) or ''
                if not pid:
                    self._json({'error': 'La Cámara no tiene ficha para este boletín; no hay documentos que leer.', 'documentos': []}); return
                tanda = 2 if qs.get('tanda', ['1'])[0] == '2' else 1
                # RAM de corta duración: si dos personas abren el mismo proyecto no se descarga dos veces; se borra al cerrar la ficha
                self._json(cached(f'docs:{pid}:{bol}:{fecha}:{tanda}', lambda: documentos.recolectar(pid, bol, fecha, tanda=tanda)))
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json({'error': str(e), 'documentos': []}, 500)
        elif p.path == '/api/documentos/cerrar':  # la ficha se cerró: se eliminan de la memoria todos los documentos de ese proyecto
            qs = urllib.parse.parse_qs(p.query)
            pid = qs.get('pid', [''])[0].strip(); bol = qs.get('boletin', [''])[0].strip()
            n = (olvidar(f'docs:{pid}:{bol}:') + olvidar(f'docs_lista:{pid}:{bol}')) if pid else 0
            self._json({'eliminados': n, 'mensaje': 'Documentos eliminados de la memoria del servidor.'})
        elif p.path in ('/informe', '/informe_proyecto.html'):   # el informe ahora vive dentro del Buscador avanzado
            self.send_response(302); self.send_header('Location', '/buscador_avanzado.html' + (('?' + p.query) if p.query else '')); self.end_headers()
        elif p.path == '/api/contexto':        # normas/artículos citados en un texto votado → título y texto vigente (LeyChile, en vivo)
            qs = urllib.parse.parse_qs(p.query)
            try:
                import buscador
                self._json(buscador.contexto_texto(qs.get('texto', [''])[0][:4000]))
            except Exception as e:
                self._json({'error': str(e)}, 500)
        elif p.path == '/api/votacion':        # observación completa de una votación (en vivo, sin base de datos)
            qs = urllib.parse.parse_qs(p.query)
            try:
                import buscador
                self._json(buscador.detalle_votacion(qs.get('boletin', [''])[0], qs.get('id', [''])[0]))
            except Exception as e:
                self._json({'error': str(e)}, 500)
        elif p.path == '/api/ficha':           # ficha completa: proyecto/ley (Cámara + Senado) o persona
            qs = urllib.parse.parse_qs(p.query)
            tipo = qs.get('tipo', ['proyecto'])[0]; ref = qs.get('ref', [''])[0]
            try:
                import buscador
                if tipo in ('proyecto', 'ley'):
                    self._json(buscador.ficha_proyecto(ref))
                else:
                    self._json(buscador.ficha_persona(tipo, ref))
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json({'error': str(e)}, 500)
        elif p.path == '/dashboard_congreso.html':   # nombre antiguo → redirige al principal
            self.send_response(301); self.send_header('Location', '/'); self.end_headers()
        elif p.path == '/api/estado':
            with LOCK:
                estado = {k: {'edad_s': round(time.time()-v['t'])} for k, v in CACHE.items()}
            self._json({'cache_ram': estado, 'persistencia': 'RAM (se borra al detener el servidor)'})
        elif p.path in ('/vivo', '/dashboard_vivo.html'):
            self.send_response(302); self.send_header('Location', '/'); self.end_headers()
        else:
            # Archivos estáticos de la raíz (Excel, audio, JSON públicos, imágenes). Solo nombres simples y extensiones permitidas.
            nombre = os.path.basename(urllib.parse.unquote(p.path))
            ext = os.path.splitext(nombre)[1].lower()
            tipos = {'.html': 'text/html; charset=utf-8', '.json': 'application/json; charset=utf-8', '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     '.mp3': 'audio/mpeg', '.txt': 'text/plain; charset=utf-8', '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.csv': 'text/csv; charset=utf-8'}
            ruta = _p(nombre)
            if nombre and '/' not in nombre and ext in tipos and os.path.isfile(ruta) and not nombre.startswith('.') and nombre not in ('INSTRUCTIVO.txt',):
                data = open(ruta, 'rb').read()
                self.send_response(200)
                self.send_header('Content-Type', tipos[ext])
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers(); self.wfile.write(data)
            else:
                self.send_response(404); self.end_headers()

if __name__ == '__main__':
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer.allow_reuse_address = True
    print(f'📡 El Poder en Simple — MODO EN VIVO (sin base de datos)')
    print(f'   Los datos se descargan al momento desde camara.cl / senado.cl / datos abiertos.')
    print(f'   Todo vive en memoria RAM y se borra al detener el servidor.')
    print(f'   → http://0.0.0.0:{PUERTO}/')
    # Precalienta en segundo plano el índice del buscador avanzado (solo RAM) y lo renueva cada 15 min
    def _precalentar():
        while True:
            try:
                import buscador
                buscador.buscar('ley')
            except Exception as e:
                print('precalentado buscador:', e)
            time.sleep(TTL_CACHE - 60)
    threading.Thread(target=_precalentar, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', PUERTO), Handler).serve_forever()
