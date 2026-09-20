#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
El Poder en Simple — BUSCADOR AVANZADO (motor).
Busca por palabras clave en la Cámara de Diputados, el Senado y el Gobierno
CONSULTANDO LAS FUENTES OFICIALES EN EL MOMENTO. Sin base de datos: todo vive
en la RAM del servidor mientras está encendido (mismo caché efímero que el
resto del modo en vivo) y se descarta al apagarlo.

Fuentes:
  · Cámara (datos abiertos vía Mirada al Congreso): votaciones del año, ficha de
    proyecto por boletín, voto nominal de cada diputad@.
  · Senado (tramitacion.senado.cl/wspublico): ficha de tramitación por boletín,
    votaciones con voto nominal de cada senador/a, nómina de senador@s vigentes.
  · Gobierno: gabinete + presidente (BCN/InfoLobby), leyes promulgadas (LeyChile),
    noticias oficiales (Cámara, Senado, Presidencia).
"""
import re, json, unicodedata, html as html_mod
import xml.etree.ElementTree as ET
from datetime import date
from concurrent.futures import ThreadPoolExecutor

import servidor as S   # reutiliza http_get / http_post_json / cached / fuentes vivas

NS = S.NS
SEN_BASE = 'https://tramitacion.senado.cl/wspublico/'

# ----------------------------------------------------------------- utilidades
def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', s).strip()

STOP = {'de', 'la', 'el', 'los', 'las', 'del', 'y', 'en', 'que', 'a', 'un', 'una', 'por', 'para', 'con', 'ley', 'proyecto', 'sobre', 'al',
        'ministro', 'ministra', 'ministerio', 'diputado', 'diputada', 'senador', 'senadora', 'presidente', 'gobierno'}

def tokens(q):
    """Palabras clave útiles (sin conectores ni cargos genéricos; números sueltos solo si son de boletín/ley)."""
    if es_boletin(q) or es_numero_ley(q):
        return []
    return [t for t in re.findall(r'[a-z0-9]+', norm(q)) if t not in STOP and len(t) >= 3]

def _raiz(k):
    # raíz simple para plurales/femeninos: pensiones→pension, ministras→ministr
    k = re.sub(r'(ciones|iones)$', 'cion', k)
    return re.sub(r'(es|as|os|s|a|o)$', '', k) if len(k) > 5 else k

def puntaje(texto, toks, q):
    """TODAS las palabras clave deben aparecer (como palabra o raíz); la frase exacta suma."""
    if not toks:
        return 0
    t = norm(texto)
    for k in toks:
        if k not in t and _raiz(k) not in t:
            return 0
    frase = norm(q)
    return len(toks) * 10 + (25 if frase and frase in t else 0)

def es_boletin(q):
    m = re.search(r'(\d{3,5})\s*[-–]\s*(\d{1,2})', q)
    if m:
        return f'{m.group(1)}-{m.group(2)}'
    m = re.fullmatch(r'\s*(\d{4,5})\s*', q)
    return m.group(1) if m else None

def es_numero_ley(q):
    m = re.search(r'ley\s*(?:n[°º]?\s*)?(\d{1,2})[.,]?(\d{3})', norm(q))
    return f'{m.group(1)}{m.group(2)}' if m else None

def txt(e, tag, ns=True):
    x = e.find(('c:' + tag) if ns else tag, NS if ns else None)
    return (x.text or '').strip() if x is not None and x.text else ''

def simple(nombre):
    """Título de proyecto en lenguaje ciudadano (quita jerga inicial)."""
    s = re.sub(r'^(proyecto de (ley|reforma constitucional|acuerdo)[,\s]*(que|en|sobre)?\s*)', '', nombre or '', flags=re.I).strip()
    return (s[:1].upper() + s[1:]) if s else nombre

# ----------------------------------------------------------------- índice vivo (RAM)
def _padron():
    return S.cached('diputados', S.src_diputados_camara)

def _senadores():
    def fn():
        x = S.http_get(SEN_BASE + 'senadores_vigentes.php', timeout=30)
        root = ET.fromstring(x)
        out = []
        for s in root.findall('senador'):
            g = lambda t: (s.findtext(t) or '').strip()
            nombre = f"{g('PARLNOMBRE')} {g('PARLAPELLIDOPATERNO')} {g('PARLAPELLIDOMATERNO')}".strip()
            out.append({'id': g('PARLID'), 'nombre': nombre, 'apellido': g('PARLAPELLIDOPATERNO'),
                        'partido': g('PARTIDO'), 'region': g('REGION'), 'circ': g('CIRCUNSCRIPCION'),
                        'url': g('CURRICULUM') or 'https://www.senado.cl/senadores/listado-de-senadores'})
        return out
    return S.cached('senadores_vigentes', fn)

def _votaciones_anio():
    """Todas las votaciones de la Cámara del año (título de proyecto resuelto en vivo)."""
    def fn():
        anio = date.today().year
        raw = S.http_post_json('https://www.miradaalcongreso.com/api/votacionesxano', {'param': anio})
        root = ET.fromstring(raw)
        rows = []
        for v in root.findall('c:Votacion', NS):
            rows.append({'id': txt(v, 'Id'), 'desc': txt(v, 'Descripcion'), 'fecha': txt(v, 'Fecha')[:10],
                         'si': int(txt(v, 'TotalSi') or 0), 'no': int(txt(v, 'TotalNo') or 0),
                         'abst': int(txt(v, 'TotalAbstencion') or 0), 'resultado': txt(v, 'Resultado'), 'tipo': txt(v, 'Tipo')})
        # proyectos distintos del año → nombre oficial (en paralelo, solo una vez por boletín)
        bols = sorted({r['desc'].replace('Boletín N° ', '').replace('Boletín N°', '').strip() for r in rows if r['desc'].startswith('Boletín')})
        nombres = {}
        def nom(b):
            try:
                r = S.http_post_json('https://www.miradaalcongreso.com/api/votaciones', {'param': b}, timeout=25)
                e = ET.fromstring(r)
                return b, {'nombre': txt(e, 'Nombre'), 'pid': txt(e, 'Id'), 'ingreso': txt(e, 'FechaIngreso')[:10], 'tipo': txt(e, 'TipoIniciativa')}
            except Exception:
                return b, None
        with ThreadPoolExecutor(max_workers=10) as ex:
            for b, info in ex.map(nom, bols):
                if info:
                    nombres[b] = info
        return {'votaciones': rows, 'proyectos': nombres}
    return S.cached('busq_votaciones_anio', fn)

def _senado_recientes():
    """Proyectos con movimiento en el Congreso en los últimos 30 días (servicio del Senado; incluye los que nacen en el Senado)."""
    def fn():
        from datetime import timedelta
        desde = (date.today() - timedelta(days=29)).strftime('%d/%m/%Y')
        x = S.http_get(SEN_BASE + f'tramitacion.php?fecha={desde}', timeout=170)
        root = ET.fromstring(x)
        out = {}
        for p in root.findall('proyecto'):
            d = p.find('descripcion')
            if d is None:
                continue
            g = lambda tag: (d.findtext(tag) or '').strip()
            bol = g('boletin')
            if not bol:
                continue
            tr = p.findall('tramitacion/tramite')
            ult = tr[-1] if tr else None
            out[bol] = {'titulo': g('titulo'), 'ingreso': g('fecha_ingreso'), 'iniciativa': g('iniciativa'), 'origen': g('camara_origen'),
                        'urgencia': g('urgencia_actual'), 'etapa': g('etapa'), 'ley': g('leynro'), 'estado': g('estado'),
                        'ultimo': ((ult.findtext('FECHA') or '').strip() + ' · ' + (ult.findtext('DESCRIPCIONTRAMITE') or '').strip()[:110]) if ult is not None else '',
                        'materias': [(m.findtext('DESCRIPCION') or '').strip() for m in p.findall('materias/materia')]}
        return out
    return S.cached('busq_senado_recientes', fn)

def _boletin_de_ley(num):
    """Boletín de una ley publicada, si el Senado la registra entre los proyectos con movimiento reciente."""
    try:
        for bol, info in _senado_recientes().items():
            if info['ley'].replace('Ley N° ', '').replace('.', '').strip() == str(num):
                return bol
    except Exception:
        pass
    return ''

def _leyes():
    return S.cached('leyes', S.src_leyes_promulgadas)

def _gobierno():
    return S.cached('gobierno', S.src_gobierno)

def _noticias():
    return S.cached('noticias', S.src_noticias)

# ----------------------------------------------------------------- BUSCAR
def buscar(q, limite=60):
    q = (q or '').strip()
    toks = tokens(q)
    res = []
    if not q:
        return {'q': q, 'resultados': [], 'nota': 'Escribe una palabra clave, un número de boletín o de ley.'}

    # 0) boletín exacto → resultado directo (aunque no esté en el año)
    b = es_boletin(q)
    if b:
        res.append({'tipo': 'proyecto', 'origen': 'congreso', 'ref': b, 'titulo': f'Proyecto de ley boletín {b}',
                    'detalle': 'Abrir la ficha completa con su tramitación y votaciones en ambas cámaras', 'fecha': '', 'estado': '', 'score': 1000})
    nl = es_numero_ley(q)

    # 1) proyectos y votaciones de la Cámara (año en curso)
    try:
        va = _votaciones_anio()
        for bol, info in va['proyectos'].items():
            sc = puntaje(info['nombre'] + ' ' + bol, toks, q) + (500 if nl and False else 0)
            if (b and bol.startswith(b)) or sc:
                vs = [v for v in va['votaciones'] if v['desc'].endswith(bol)]
                ult = max(vs, key=lambda v: v['fecha']) if vs else None
                res.append({'tipo': 'proyecto', 'origen': 'camara', 'ref': bol, 'titulo': simple(info['nombre']),
                            'detalle': f"{info['tipo'] or 'Proyecto'} · ingresó {info['ingreso']} · {len(vs)} votación(es) este año en la Cámara",
                            'fecha': ult['fecha'] if ult else info['ingreso'], 'estado': (ult['resultado'] if ult else ''), 'score': sc + 5})
    except Exception as e:
        res.append({'tipo': 'aviso', 'origen': 'camara', 'titulo': 'La Cámara no respondió en este momento', 'detalle': str(e)[:120], 'score': -1})

    # 1b) proyectos con movimiento reciente en el Congreso (Senado: incluye los que nacen allí)
    try:
        ya = {r.get('ref') for r in res if r['tipo'] == 'proyecto'}
        for bol, info in _senado_recientes().items():
            if bol in ya:
                # enriquecer el resultado de la Cámara con la etapa oficial
                for r in res:
                    if r.get('ref') == bol and r['tipo'] == 'proyecto' and info['etapa']:
                        r['estado'] = info['etapa'][:48]; r['detalle'] += (' · Ley ' + info['ley'].replace('Ley N° ', '')) if info['ley'] else ''
                continue
            sc = puntaje(info['titulo'] + ' ' + bol + ' ' + ' '.join(info['materias']), toks, q)
            if nl and info['ley'].replace('Ley N° ', '').replace('.', '') == nl:
                sc += 950
            if (b and bol.startswith(b)) or sc:
                res.append({'tipo': 'proyecto', 'origen': 'senado' if 'Senado' in info['origen'] else 'camara', 'ref': bol, 'titulo': simple(info['titulo']),
                            'detalle': f"{info['iniciativa'] or 'Proyecto'} · ingresó {info['ingreso']} · origen {info['origen']}" + (f" · Ley {info['ley'].replace('Ley N° ','')}" if info['ley'] else '') + (f" · último paso: {info['ultimo']}" if info['ultimo'] else ''),
                            'fecha': info['ingreso'], 'estado': info['etapa'][:48], 'score': sc + 4})
    except Exception as e:
        res.append({'tipo': 'aviso', 'origen': 'senado', 'titulo': 'El Senado no respondió en este momento', 'detalle': str(e)[:120], 'score': -1})

    # 2) leyes promulgadas (LeyChile)
    try:
        for l in _leyes() or []:
            num = str(l.get('nro_norma', '')); tit = l.get('titulo_norma', ''); ident = l.get('identif_norma', '')
            t = f"Ley {num} {tit} {ident}"
            sc = puntaje(t, toks, q)
            if nl and num == nl:
                sc += 900
            if sc:
                res.append({'tipo': 'ley', 'origen': 'gobierno', 'ref': num, 'titulo': f"Ley {num[:2]}.{num[2:]}: {tit.capitalize()}",
                            'detalle': (ident.split(' / ')[-1].title() if ' / ' in ident else 'Ley publicada') + ' · publicada el ' + (l.get('fecha_publicacion') or ''),
                            'fecha': l.get('fecha_publicacion', ''), 'estado': 'Publicada',
                            'url': f"https://www.bcn.cl/leychile/navegar?idNorma={l.get('idNorma','')}", 'historia': l.get('historia_ley', ''),
                            'boletin': _boletin_de_ley(num), 'score': sc})
    except Exception:
        pass

    # 3) personas: diputad@s
    try:
        pad = _padron()
        for did, d in (pad.items() if isinstance(pad, dict) else ((x['id'], x) for x in pad)):
            d = dict(d, id=did)
            t = f"{d.get('nombre','')} {d.get('partido','')} {d.get('grupo','')} distrito {d.get('distrito','')}"
            sc = puntaje(t, toks, q)
            if sc:
                res.append({'tipo': 'diputado', 'origen': 'camara', 'ref': str(d.get('id')), 'titulo': d.get('nombre', ''),
                            'detalle': f"Diputad@ · {d.get('partido','')} · Distrito {d.get('distrito','')}", 'fecha': '', 'estado': 'En ejercicio', 'score': sc})
    except Exception:
        pass

    # 4) personas: senador@s
    try:
        for s in _senadores():
            t = f"{s['nombre']} {s['partido']} {s['region']} circunscripcion {s['circ']}"
            sc = puntaje(t, toks, q)
            if sc:
                res.append({'tipo': 'senador', 'origen': 'senado', 'ref': s['id'], 'titulo': s['nombre'],
                            'detalle': f"Senador/a · {s['partido']} · {s['region']}", 'fecha': '', 'estado': 'En ejercicio', 'url': s['url'], 'score': sc})
    except Exception:
        pass

    # 5) gobierno: presidente + ministr@s (las palabras de cargo cuentan aquí)
    qn = norm(q)
    cargo_gob = any(w in qn for w in ('ministr', 'gobierno', 'gabinete', 'presidente'))
    try:
        g = _gobierno()
        pres = g.get('presidente', {})
        if pres and (puntaje(f"presidente {pres.get('nombre','')}", toks, q) or (not toks and 'presidente' in qn)):
            res.append({'tipo': 'autoridad', 'origen': 'gobierno', 'ref': 'presidente', 'titulo': pres.get('nombre', ''), 'detalle': 'Presidente de la República',
                        'fecha': pres.get('desde', ''), 'estado': 'En ejercicio', 'url': pres.get('fuente', ''), 'score': puntaje(f"presidente {pres.get('nombre','')}", toks, q) + 20})
        for m in g.get('gabinete', []):
            t = f"{m.get('ministerio','')} {m.get('ministro','')} {m.get('cargo','')}"
            sc = puntaje(t, toks, q) or (30 if (not toks and cargo_gob) else 0)
            if sc and cargo_gob:
                sc += 40
            if sc:
                res.append({'tipo': 'autoridad', 'origen': 'gobierno', 'ref': m.get('ministerio', ''), 'titulo': m.get('ministro', ''),
                            'detalle': m.get('cargo') or m.get('ministerio', ''), 'fecha': '', 'estado': 'En ejercicio', 'url': m.get('url', ''), 'score': sc})
    except Exception:
        pass

    # 6) noticias oficiales del día
    try:
        for org, lst in (_noticias() or {}).items():
            for n in lst:
                sc = puntaje(n.get('titulo', '') + ' ' + n.get('resumen', ''), toks, q)
                if sc:
                    res.append({'tipo': 'noticia', 'origen': {'camara': 'camara', 'senado': 'senado'}.get(org, 'gobierno'), 'ref': n.get('url', ''),
                                'titulo': n.get('titulo', ''), 'detalle': n.get('resumen', '')[:180], 'fecha': n.get('fecha', ''), 'estado': 'Noticia oficial', 'url': n.get('url', ''), 'score': sc})
    except Exception:
        pass

    res.sort(key=lambda r: (-r.get('score', 0), r.get('fecha', '')), reverse=False)
    res = [r for r in res if r.get('score', 0) != 0]
    return {'q': q, 'total': len(res), 'resultados': res[:limite],
            'fuentes': 'Cámara de Diputados (datos abiertos) · Senado (tramitacion.senado.cl) · LeyChile/BCN · Presidencia — consultadas en este momento, sin base de datos.'}

# ----------------------------------------------------------------- FICHA DE PROYECTO / LEY
OP = {'1': 'S', '0': 'N', '2': 'A'}

def _votos_camara(vid):
    raw = S.http_post_json('https://www.miradaalcongreso.com/api/votacionesDetalle', {'param': int(vid)}, timeout=40)
    root = ET.fromstring(raw)
    votos = {}
    nv = root.find('c:Votos', NS)
    for vo in (nv.findall('c:Voto', NS) if nv is not None else []):
        op = OP.get(vo.find('c:OpcionVoto', NS).attrib.get('Valor'))
        idc = vo.find('c:Diputado', NS).find('c:Id', NS).text
        if op:
            votos[str(idc)] = op
    return votos

def _senado_tramitacion(bol_num):
    x = S.http_get(SEN_BASE + f'tramitacion.php?boletin={bol_num}', timeout=40)
    root = ET.fromstring(x)
    p = root.find('proyecto')
    if p is None:
        return None
    d = p.find('descripcion')
    g = lambda t: (d.findtext(t) or '').strip() if d is not None else ''
    tram = []
    for t in p.findall('tramitacion/tramite'):
        tram.append({'fecha': (t.findtext('FECHA') or '').strip(), 'sesion': (t.findtext('SESION') or '').strip(),
                     'que': (t.findtext('DESCRIPCIONTRAMITE') or '').strip(), 'etapa': (t.findtext('ETAPDESCRIPCION') or '').strip(),
                     'camara': (t.findtext('CAMARATRAMITE') or '').strip()})
    autores = [(a.findtext('PARLAMENTARIO') or '').strip() for a in p.findall('autores/autor')]
    urg = []
    for u in p.findall('urgencias/urgencia'):
        urg.append({'tipo': (u.findtext('TIPO') or '').strip(), 'ingreso': (u.findtext('FECHAINGRESO') or '').strip(), 'retiro': (u.findtext('FECHARETIRO') or '').strip()})
    materias = [(m.findtext('DESCRIPCION') or '').strip() for m in p.findall('materias/materia')]
    return {'boletin': g('boletin'), 'titulo': g('titulo'), 'ingreso': g('fecha_ingreso'), 'iniciativa': g('iniciativa'),
            'origen': g('camara_origen'), 'urgencia': g('urgencia_actual'), 'etapa': g('etapa'), 'subetapa': g('subetapa'),
            'ley': g('leynro'), 'diario_oficial': g('diariooficial'), 'estado': g('estado'), 'tramites': tram,
            'autores': [a for a in autores if a], 'urgencias': urg, 'materias': [m for m in materias if m],
            'url': f'https://www.senado.cl/appsenado/templates/tramitacion/index.php?boletin_ini={bol_num}'}

def _senado_votaciones(bol_num):
    x = S.http_get(SEN_BASE + f'votaciones.php?boletin={bol_num}', timeout=40)
    root = ET.fromstring(x)
    out = []
    for v in root.findall('votacion'):
        g = lambda t: (v.findtext(t) or '').strip()
        votos = []
        for vo in v.findall('DETALLE_VOTACION/VOTO'):
            votos.append({'n': (vo.findtext('PARLAMENTARIO') or '').strip(), 'v': {'Si': 'S', 'No': 'N', 'Abstencion': 'A', 'Abstención': 'A', 'Pareo': 'P'}.get((vo.findtext('SELECCION') or '').strip(), 'X')})
        out.append({'sesion': g('SESION'), 'fecha': g('FECHA'), 'tema': g('TEMA'), 'si': int(g('SI') or 0), 'no': int(g('NO') or 0),
                    'abst': int(g('ABSTENCION') or 0), 'pareo': int(g('PAREO') or 0), 'quorum': g('QUORUM'), 'tipo': g('TIPOVOTACION'),
                    'etapa': g('ETAPA'), 'votos': votos})
    return out

def ficha_proyecto(bol):
    """Ficha completa de un proyecto/ley: Cámara (con voto por diputad@) + Senado (con voto por senador/a)."""
    bol = bol.strip().replace('.', '')
    bol_num = bol.split('-')[0]
    out = {'boletin': bol, 'camara': None, 'senado': None, 'senado_votaciones': [], 'errores': []}

    def camara():
        r = S.http_post_json('https://www.miradaalcongreso.com/api/votaciones', {'param': bol}, timeout=40)
        e = ET.fromstring(r)
        vots = []
        for v in e.findall('c:Votaciones/c:VotacionProyectoLey', NS):
            vots.append({'id': txt(v, 'Id'), 'fecha': txt(v, 'Fecha')[:10], 'si': int(txt(v, 'TotalSi') or 0), 'no': int(txt(v, 'TotalNo') or 0),
                         'abst': int(txt(v, 'TotalAbstencion') or 0), 'quorum': txt(v, 'Quorum'), 'resultado': txt(v, 'Resultado'),
                         'tipo': txt(v, 'TipoVotacionProyectoLey') or txt(v, 'Tipo'), 'articulo': txt(v, 'Articulo'),
                         'tramite': txt(v, 'TramiteConstitucional'), 'tramite_regl': txt(v, 'TramiteReglamentario')})
        vots.sort(key=lambda v: v['fecha'])
        autores = []
        for a in e.findall('c:Autores/c:ParlamentarioAutor', NS) + e.findall('c:Autores/c:Diputado', NS):
            n = ' '.join(x for x in [txt(a, 'Nombre'), txt(a, 'ApellidoPaterno'), txt(a, 'ApellidoMaterno')] if x)
            if not n:
                d = a.find('c:Diputado', NS)
                if d is not None:
                    n = ' '.join(x for x in [txt(d, 'Nombre'), txt(d, 'ApellidoPaterno'), txt(d, 'ApellidoMaterno')] if x)
            if n:
                autores.append(n)
        mins = [txt(m, 'Nombre') for m in e.findall('c:MinisteriosPatrocinantes/c:Ministerio', NS)]
        mats = [txt(m, 'Nombre') for m in e.findall('c:Materias/c:Materia', NS)]
        pid = txt(e, 'Id')
        return {'pid': pid, 'boletin': txt(e, 'NumeroBoletin') or bol, 'nombre': txt(e, 'Nombre'), 'titulo_simple': simple(txt(e, 'Nombre')),
                'ingreso': txt(e, 'FechaIngreso')[:10], 'iniciativa': txt(e, 'TipoIniciativa'), 'origen': txt(e, 'CamaraOrigen'),
                'autores': autores, 'ministerios': [m for m in mins if m], 'materias': [m for m in mats if m],
                'admisible': txt(e, 'Admisible'), 'votaciones': vots,
                'url': f'https://www.camara.cl/legislacion/proyectosdeley/tramitacion.aspx?prmID={pid}' if pid else 'https://www.camara.cl/legislacion/proyectosdeley/proyectosdeley.aspx'}

    with ThreadPoolExecutor(max_workers=3) as ex:
        fc, fs, fv = ex.submit(camara), ex.submit(_senado_tramitacion, bol_num), ex.submit(_senado_votaciones, bol_num)
        for k, f in (('camara', fc), ('senado', fs), ('senado_votaciones', fv)):
            try:
                out[k] = f.result()
            except Exception as e:
                out['errores'].append(f'{k}: {str(e)[:120]}')

    # voto nominal de diputad@s en las últimas 6 votaciones de la Cámara (las demás quedan con totales)
    if out['camara'] and out['camara']['votaciones']:
        padron = _padron()
        pad = padron if isinstance(padron, dict) else {str(d['id']): d for d in padron}
        ult = out['camara']['votaciones'][-6:]
        with ThreadPoolExecutor(max_workers=6) as ex:
            for v, votos in zip(ult, ex.map(lambda v: _safe(_votos_camara, v['id']) or {}, ult)):
                v['votos'] = votos
        out['diputados'] = {str(k): {'n': d.get('nombre', ''), 'g': S.grupo_de(d.get('partido', '')) if hasattr(S, 'grupo_de') else d.get('partido', ''), 'p': d.get('partido', ''), 'dist': d.get('distrito', '')} for k, d in pad.items()}

    # senador@s vigentes (para partido/región en la ficha)
    try:
        out['senadores'] = _senadores()
    except Exception:
        out['senadores'] = []

    # ley publicada
    ley = (out['senado'] or {}).get('ley') or ''
    m = re.search(r'(\d{1,2})[.,]?(\d{3})', ley)
    if m:
        out['ley'] = {'numero': f'{m.group(1)}.{m.group(2)}', 'diario_oficial': (out['senado'] or {}).get('diario_oficial', ''),
                      'url': f'https://www.bcn.cl/leychile/consulta/listado_n_sel?_grupo_aporte=&sub=&agr=2&comp=&npag=1&itemsporpagina=10&totalitems=&tipoviene=4&seleccionado=0&taxo=&tipoNorma=&str=Ley+{m.group(1)}{m.group(2)}'}
    return out

def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None

# ----------------------------------------------------------------- FICHA DE PERSONA
def ficha_persona(tipo, ref):
    if tipo == 'diputado':
        padron = _padron(); pad = padron if isinstance(padron, dict) else {str(d['id']): d for d in padron}
        d = pad.get(str(ref))
        if not d:
            return {'error': 'Diputad@ no encontrad@ en el padrón vigente'}
        out = {'tipo': 'diputado', 'persona': d,
               'url': f"https://www.camara.cl/diputados/detalle/biografia.aspx?prmId={ref}",
               'url_mociones': f"https://www.camara.cl/diputados/detalle/mociones.aspx?prmID={ref}",
               'url_gastos': f"https://www.camara.cl/diputados/detalle/gastosoperacionales.aspx?prmId={ref}"}
        try:
            asis = S.cached('asistencia', lambda: S.src_asistencia(pad))
            rows = asis.get('rows', asis) if isinstance(asis, dict) else asis
            out['asistencia'] = next((a for a in rows if str(a.get('id')) == str(ref)), None)
            out['total_sesiones'] = asis.get('total_sesiones') if isinstance(asis, dict) else None
        except Exception:
            out['asistencia'] = None
        try:
            va = _votaciones_anio()
            recientes = [v for v in va['votaciones'] if v['desc'].startswith('Boletín') and v['tipo'] == 'Proyecto de Ley']
            recientes.sort(key=lambda v: v['fecha'], reverse=True)
            recientes = recientes[:8]
            votos = []
            with ThreadPoolExecutor(max_workers=8) as ex:
                for v, det in zip(recientes, ex.map(lambda v: _safe(_votos_camara, v['id']) or {}, recientes)):
                    b = v['desc'].replace('Boletín N° ', '').strip()
                    votos.append({'boletin': b, 'titulo': simple((va['proyectos'].get(b) or {}).get('nombre') or v['desc']), 'fecha': v['fecha'],
                                  'voto': det.get(str(ref), 'X'), 'resultado': v['resultado']})
            out['votos_recientes'] = votos
        except Exception:
            out['votos_recientes'] = []
        return out
    if tipo == 'senador':
        s = next((x for x in _senadores() if x['id'] == str(ref)), None)
        if not s:
            return {'error': 'Senador/a no encontrad@'}
        return {'tipo': 'senador', 'persona': s, 'url': s['url'],
                'nota': 'El voto de cada senador/a aparece en la ficha de cada proyecto (pestaña Senado).'}
    if tipo == 'autoridad':
        g = _gobierno()
        if ref == 'presidente':
            return {'tipo': 'autoridad', 'persona': g.get('presidente', {}), 'url': g.get('presidente', {}).get('fuente', 'https://prensa.presidencia.cl/')}
        m = next((m for m in g.get('gabinete', []) if m.get('ministerio') == ref), None)
        return {'tipo': 'autoridad', 'persona': m or {}, 'url': (m or {}).get('url', 'https://www.gob.cl/ministerios/')}
    return {'error': 'tipo desconocido'}

if __name__ == '__main__':
    import sys
    q = ' '.join(sys.argv[1:]) or 'pensiones'
    r = buscar(q)
    print(json.dumps({'total': r.get('total'), 'top': r['resultados'][:8]}, ensure_ascii=False, indent=1))
