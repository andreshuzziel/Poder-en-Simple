# -*- coding: utf-8 -*-
"""
documentos.py — Recolector de DOCUMENTOS OFICIALES de un proyecto de ley (sin base de datos).

Cuando alguien abre un proyecto o una votación, este módulo:
  1. Lista los documentos publicados por la Cámara de Diputadas y Diputados para ese proyecto
     (informes de comisión, oficios, boletines de indicaciones, veto/observaciones del Presidente
     y el mensaje o moción original), leyendo las pestañas públicas de camara.cl.
  2. Descarga en MEMORIA los más relevantes (PDF, DOCX o DOC), les extrae el texto y arma
     información en simple: de qué trata, idea matriz, texto de cada observación del veto,
     cómo votó la comisión, quiénes expusieron, leyes citadas (motor de citas de buscador.py).
  3. Devuelve todo como dict para /api/documentos. Nada se escribe en disco; la caché es en RAM
     y de corta duración (misma política que el resto del sitio).

Fuentes: https://www.camara.cl/legislacion/ProyectosDeLey/{informes,oficios,indicaciones,veto}.aspx
         https://www.camara.cl/verDoc.aspx?prmID=<id>&prmTIPO=<TIPO>
         alternativa (mismos ids): https://www.senado.cl/appsenado/index.php?mo=tramitacion&ac=getDocto&iddocto=<id>&tipodoc=<info|oficio|indicacion|veto|mensaje_mocion>
OCR: si un PDF es imagen, se reconoce localmente con RapidOCR (onnxruntime) + PyMuPDF, máx. OCR_MAX_PAGINAS páginas.
"""
import re, io, zipfile, struct, html as html_mod
from concurrent.futures import ThreadPoolExecutor

import servidor as S

BASE = 'https://www.camara.cl/legislacion/ProyectosDeLey/'
DOC = 'https://www.camara.cl/verDoc.aspx?prmID={id}&prmTIPO={tipo}'
DOMINIOS_OK = ('www.camara.cl', 'camara.cl', 'www.senado.cl', 'tramitacion.senado.cl', 'www.bcn.cl',
               'www.leychile.cl', 'www.diariooficial.interior.gob.cl')
MAX_TXT = 400_000       # caracteres de texto por documento que se conservan en RAM
MAX_DOCS = 8            # documentos de la PRIMERA tanda (los más relevantes); la segunda tanda lee el resto
SEN_XML = 'https://tramitacion.senado.cl/wspublico/tramitacion.php?boletin={bol}'

MESES = {'ene': '01', 'feb': '02', 'mar': '03', 'abr': '04', 'may': '05', 'jun': '06', 'jul': '07',
         'ago': '08', 'sep': '09', 'sept': '09', 'oct': '10', 'nov': '11', 'dic': '12'}


def _fecha_iso(s):
    """'12 Ago. 2026' → '2026-08-12'."""
    m2 = re.match(r'\s*(\d{1,2})/(\d{1,2})/(\d{4})', s or '')
    if m2:
        return f'{m2.group(3)}-{int(m2.group(2)):02d}-{int(m2.group(1)):02d}'
    m = re.match(r'\s*(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})', s or '')
    if not m:
        return (s or '').strip()
    mes = MESES.get(m.group(2).lower()[:4].rstrip('.'), MESES.get(m.group(2).lower()[:3], '01'))
    return f'{m.group(3)}-{mes}-{int(m.group(1)):02d}'


def _limpia(s):
    s = html_mod.unescape(re.sub(r'<[^>]+>', ' ', s or ''))
    return re.sub(r'\s+', ' ', s).strip()


# ---------------------------------------------------------------- 1. LISTADO
def _tabla(pagina, pid, bol):
    """Lee una pestaña (informes/oficios/indicaciones/veto) y devuelve filas con su documento."""
    url = f'{BASE}{pagina}.aspx?prmID={pid}&prmBOLETIN={bol}'
    t = S.http_get(url, timeout=40)
    i = t.find('link_veto')
    seg = t[i:] if i > 0 else t
    seg = re.sub(r'<script.*?</script>', '', seg, flags=re.S)
    filas = []
    cab = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', seg, re.S):
        celdas = re.findall(r'<t([dh])[^>]*>(.*?)</t[dh]>', tr, re.S)
        if not celdas:
            continue
        if celdas[0][0] == 'h':
            cab = [_limpia(c[1]) for c in celdas]
            continue
        m = re.search(r'verDoc\.aspx\?prmID=(\d+)&(?:amp;)?prmTIPO=(\w+)', tr)
        if not m:
            continue
        vals = [_limpia(c[1]) for c in celdas]
        fila = {cab[k].lower() if k < len(cab) else f'c{k}': v for k, v in enumerate(vals)}
        filas.append({'doc_id': m.group(1), 'doc_tipo': m.group(2), 'url': DOC.format(id=m.group(1), tipo=m.group(2)),
                      'fecha': _fecha_iso(fila.get('fecha', '')), 'etapa': fila.get('etapa', ''),
                      'titulo': fila.get('informe') or fila.get('oficio') or fila.get('indicación') or fila.get('indicacion')
                                or fila.get('mensaje') or fila.get('descripción') or fila.get('descripcion') or '',
                      'origen': fila.get('origen', '') or fila.get('emisor', ''),
                      'fuente': pagina})
    return filas


_SEN_A_CAM = {'info': 'INFORMEPLEY', 'oficio': 'OFICIOPLEY', 'indicacion': 'INDICACIONPLEY', 'veto': 'VETO',
              'mensaje_mocion': 'INICIATIVA', 'compa': 'COMPARADO'}


def _senado_docs(bol):
    """Documentos que publica el Senado para el mismo boletín (XML abierto). Usa los mismos identificadores que la Cámara."""
    num = bol.split('-')[0]
    x = S.http_get(SEN_XML.format(bol=num), timeout=40)
    out = []
    for m in re.finditer(r'<(LINK_[A-Z_]+|link_mensaje_mocion)>\s*([^<]+?)\s*</\1>', x):
        url = m.group(2).replace('&amp;', '&')
        mi = re.search(r'iddocto=(\d+)', url); mt = re.search(r'tipodoc=(\w+)', url)
        if not (mi and mt):
            continue
        tipo = _SEN_A_CAM.get(mt.group(1))
        if not tipo:
            continue
        # contexto: el registro <informe>/<oficio>/<indicaciones>/<comparado> que contiene el enlace
        ini = max(x.rfind('<' + tag + '>', 0, m.start()) for tag in ('informe', 'oficio', 'indicaciones', 'comparado', 'iniciativa', 'observaciones'))
        ctx = x[max(0, ini):m.start()]
        fecha = re.findall(r'<FECHA(?:INFORME)?>\s*([^<]+)<', ctx)
        etapa = re.findall(r'<(?:ETAPA|ETAPDESCRIPCION)>\s*([^<]+)<', ctx)
        desc = re.findall(r'<(?:TRAMITE|DESCRIPCION|DESCRIPCIONTRAMITE|COMPARADO)>\s*([^<]+)<', ctx)
        cam_url = DOC.format(id=mi.group(1), tipo=tipo)
        out.append({'doc_id': mi.group(1), 'doc_tipo': tipo, 'url': cam_url if tipo != 'COMPARADO' else url,
                    'fecha': _fecha_iso(fecha[-1]) if fecha else '', 'etapa': _limpia(etapa[-1]) if etapa else '',
                    'titulo': _limpia(desc[-1]) if desc else ('Texto comparado' if tipo == 'COMPARADO' else 'Mensaje o moción original (texto con que se presentó el proyecto)' if tipo == 'INICIATIVA' else ''),
                    'origen': 'Senado', 'fuente': 'senado'})
    return out


def _iniciativa(pid):
    """Enlace al mensaje/moción original (pestaña tramitación)."""
    try:
        t = S.http_get(f'{BASE}tramitacion.aspx?prmID={pid}', timeout=40)
        m = re.search(r'verDoc\.aspx\?prmID=(\d+)&(?:amp;)?prmTIPO=INICIATIVA', t)
        if m:
            return {'doc_id': m.group(1), 'doc_tipo': 'INICIATIVA', 'url': DOC.format(id=m.group(1), tipo='INICIATIVA'),
                    'fecha': '', 'etapa': 'Ingreso', 'titulo': 'Mensaje o moción original (texto con que se presentó el proyecto)',
                    'origen': '', 'fuente': 'iniciativa'}
    except Exception:
        pass
    return None


def listar_documentos(pid, bol):
    """Todos los documentos oficiales del proyecto en la Cámara, con su tipo y fecha."""
    docs, errores = [], []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {pg: ex.submit(_tabla, pg, pid, bol) for pg in ('informes', 'oficios', 'indicaciones', 'veto')}
        fi = ex.submit(_iniciativa, pid)
        for pg, f in futs.items():
            try:
                docs += f.result()
            except Exception as e:
                errores.append(f'{pg}: {type(e).__name__}')
        try:
            ini = fi.result()
            if ini:
                docs.append(ini)
        except Exception:
            pass
    # Senado: la misma tramitación publica sus propios enlaces (informes, oficios, indicaciones, comparados, mensaje)
    try:
        docs += _senado_docs(bol)
    except Exception as e:
        errores.append(f'senado: {type(e).__name__}')
    vistos, unicos = set(), []
    for d in docs:
        k = (d['doc_id'], d['doc_tipo'])
        if k not in vistos:
            vistos.add(k); unicos.append(d)
    return unicos, errores


# ---------------------------------------------------------------- 2. EXTRACCIÓN DE TEXTO (en RAM)
def _texto_docx(raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    x = z.read('word/document.xml').decode('utf-8', 'ignore')
    x = re.sub(r'</w:p>', '\n', x)
    x = re.sub(r'<w:tab/>', ' ', x)
    x = re.sub(r'<w:br[^>]*/>', '\n', x)
    x = re.sub(r'<[^>]+>', '', x)
    x = re.sub(r'HYPERLINK\s+"[^"]*"', '', x)
    return html_mod.unescape(x)


def _texto_pdf(raw, max_pags=120):
    import pypdf
    r = pypdf.PdfReader(io.BytesIO(raw))
    out = []
    for p in r.pages[:max_pags]:
        try:
            out.append(p.extract_text() or '')
        except Exception:
            out.append('')
    return '\n'.join(out)


def _texto_doc(raw):
    """Word 97-2003 (.doc): lee la tabla de piezas del texto (FIB + Clx). Sin dependencias externas."""
    import olefile
    ole = olefile.OleFileIO(io.BytesIO(raw))
    wd = ole.openstream('WordDocument').read()
    flags = struct.unpack('<H', wd[0x0A:0x0C])[0]
    tabla = '1Table' if (flags & 0x0200) else '0Table'
    if not ole.exists(tabla):
        tabla = '0Table' if ole.exists('0Table') else '1Table'
    tb = ole.openstream(tabla).read()
    fcClx, lcbClx = struct.unpack('<II', wd[0x01A2:0x01AA])
    clx = tb[fcClx:fcClx + lcbClx]
    pos = 0
    while pos < len(clx) and clx[pos] == 0x01:            # Prc (propiedades) → saltar
        cb = struct.unpack('<H', clx[pos + 1:pos + 3])[0]; pos += 3 + cb
    if pos >= len(clx) or clx[pos] != 0x02:
        raise ValueError('sin tabla de piezas')
    lcb = struct.unpack('<I', clx[pos + 1:pos + 5])[0]
    plc = clx[pos + 5:pos + 5 + lcb]
    n = (lcb - 4) // 12
    cps = [struct.unpack('<I', plc[i * 4:i * 4 + 4])[0] for i in range(n + 1)]
    partes = []
    for i in range(n):
        pcd = plc[(n + 1) * 4 + i * 8:(n + 1) * 4 + i * 8 + 8]
        fc = struct.unpack('<I', pcd[2:6])[0]
        comp = bool(fc & 0x40000000); fc &= 0x3FFFFFFF
        largo = cps[i + 1] - cps[i]
        if comp:
            partes.append(wd[fc // 2:fc // 2 + largo].decode('cp1252', 'ignore'))
        else:
            partes.append(wd[fc:fc + largo * 2].decode('utf-16-le', 'ignore'))
    txt = ''.join(partes)
    txt = txt.replace('\r', '\n').replace('\x07', ' ').replace('\x0b', '\n')
    return re.sub(r'[\x00-\x08\x0c\x0e-\x1f]', '', txt)


def extraer_texto(raw, content_type=''):
    """Detecta el formato por la firma binaria y extrae texto. Devuelve (texto, formato)."""
    if raw[:4] == b'%PDF':
        return _texto_pdf(raw), 'pdf'
    if raw[:2] == b'PK':
        return _texto_docx(raw), 'docx'
    if raw[:4] == b'\xd0\xcf\x11\xe0':
        return _texto_doc(raw), 'doc'
    if b'<html' in raw[:2000].lower():
        return _limpia(raw.decode('utf-8', 'ignore')), 'html'
    return '', 'desconocido'


SEN_DOC = 'https://www.senado.cl/appsenado/index.php?mo=tramitacion&ac=getDocto&iddocto={id}&tipodoc={tipo}'
SEN_TIPO = {'INFORMEPLEY': 'info', 'OFICIOPLEY': 'oficio', 'INDICACIONPLEY': 'indicacion', 'VETO': 'veto', 'INICIATIVA': 'mensaje_mocion', 'COMPARADO': 'compa'}
OCR_MAX_PAGINAS = 12      # páginas escaneadas que se reconocen por consulta (≈ 4 s cada una)
OCR_DPI = 170
_OCR = {'motor': None}


def url_alternativa(doc):
    """Misma pieza publicada por el Senado (mismos identificadores). Sirve cuando la copia de la Cámara es imagen o falla."""
    tipo = SEN_TIPO.get(doc.get('doc_tipo', ''))
    if tipo and doc.get('doc_id'):
        return SEN_DOC.format(id=doc['doc_id'], tipo=tipo)
    return ''


def _motor_ocr():
    if _OCR['motor'] is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR['motor'] = RapidOCR()
    return _OCR['motor']


def _normaliza_ocr(txt):
    """Corrige errores típicos del OCR en documentos legales para que los analizadores los entiendan."""
    reglas = [
        (r'ART[iíÍI1l][CG]ULO', 'ARTÍCULO'), (r'\bart[iíI1l]culo', 'artículo'), (r'\bArt[iíI1l]culo', 'Artículo'),
        (r'FUNDAMENTOS?DE ?LAS ?OBSERVACIONES', 'FUNDAMENTO DE LAS OBSERVACIONES'), (r'LAS ?OBSERVACIONES', 'LAS OBSERVACIONES'),
        (r'\bN[o°º]\s*(\d)', r'N° \1'), (r'\bley N[o°º]', 'ley N°'), (r'Republica', 'República'), (r'Codigo', 'Código'),
        (r'Constitucion', 'Constitución'), (r'Comision', 'Comisión'), (r'votacion', 'votación'), (r'Votacion', 'Votación'),
        (r'indicacion', 'indicación'), (r'observacion', 'observación'), (r'Observacion', 'Observación'),
    ]
    for a, b in reglas:
        txt = re.sub(a, b, txt)
    return txt


def ocr_pdf(raw, max_paginas=OCR_MAX_PAGINAS):
    """Reconoce el texto de un PDF escaneado (imagen) página por página, en memoria. Devuelve (texto, info)."""
    import pymupdf as fitz, numpy as np
    motor = _motor_ocr()
    d = fitz.open(stream=raw, filetype='pdf')
    total = d.page_count
    partes, confs = [], []
    for i, pg in enumerate(d):
        if i >= max_paginas:
            break
        pix = pg.get_pixmap(dpi=OCR_DPI, colorspace=fitz.csGRAY)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
        res, _ = motor(arr)
        lineas = []
        for r in (res or []):
            try:
                lineas.append(str(r[1])); confs.append(float(r[2]))
            except Exception:
                pass
        partes.append('\n'.join(lineas))
    txt = _normaliza_ocr('\n'.join(partes))
    conf = round(sum(confs) / len(confs), 3) if confs else 0.0
    return txt, {'ocr': True, 'ocr_paginas': min(total, max_paginas), 'ocr_total_paginas': total, 'ocr_confianza': conf}


def descargar_texto(url):
    """Descarga en RAM un documento oficial (solo dominios oficiales) y devuelve su texto."""
    host = re.sub(r'^https?://([^/]+).*$', r'\1', url)
    if host not in DOMINIOS_OK:
        raise ValueError('dominio no oficial')
    raw, ct, cd = S.http_get_bytes(url, timeout=90)
    txt, fmt = extraer_texto(raw, ct)
    nombre = ''
    m = re.search(r'filename="?([^";]+)', cd or '')
    if m:
        nombre = html_mod.unescape(m.group(1)).strip()
    txt = re.sub(r'[ \t\xa0]+', ' ', txt)
    txt = re.sub(r'\n\s*\n+', '\n', txt).strip()
    escaneado = fmt == 'pdf' and len(txt) < max(200, 25 * _n_paginas_pdf(raw))
    return {'texto': txt[:MAX_TXT], 'formato': fmt, 'bytes': len(raw), 'nombre': nombre,
            'caracteres': len(txt), 'escaneado': escaneado, '_raw': raw if escaneado else None}


def _n_paginas_pdf(raw):
    try:
        import pypdf
        return len(pypdf.PdfReader(io.BytesIO(raw)).pages)
    except Exception:
        return 1


def obtener_texto(doc):
    """Texto de un documento con tres intentos, en orden:
       1) copia de la Cámara; 2) si es imagen o falla, la misma pieza en el Senado (suele tener texto);
       3) si sigue siendo imagen, OCR local (reconocimiento óptico) limitado a las primeras páginas."""
    intentos = []
    info = None
    try:
        info = descargar_texto(doc['url']); info['fuente_texto'] = 'camara'
    except Exception as e:
        intentos.append(f'camara: {type(e).__name__}')
    alt = url_alternativa(doc)
    if alt and (info is None or info.get('escaneado') or info['caracteres'] < 200):
        try:
            info2 = descargar_texto(alt); info2['fuente_texto'] = 'senado'; info2['url_alternativa'] = alt
            if info is None or info2['caracteres'] > max(200, info['caracteres']):
                if info is not None:
                    info2['_raw_camara'] = info.get('_raw')
                info = info2
        except Exception as e:
            intentos.append(f'senado: {type(e).__name__}')
    if info is None:
        raise RuntimeError('; '.join(intentos) or 'sin texto')
    if info.get('escaneado') and info.get('_raw'):
        try:
            txt, oi = ocr_pdf(info['_raw'])
            if len(txt) > 100:
                txt = re.sub(r'[ \t\xa0]+', ' ', txt); txt = re.sub(r'\n\s*\n+', '\n', txt).strip()
                info.update(oi); info['texto'] = txt[:MAX_TXT]; info['caracteres'] = len(txt); info['fuente_texto'] += '+ocr'
        except Exception as e:
            info['ocr_error'] = f'{type(e).__name__}: {str(e)[:80]}'
    info.pop('_raw', None); info.pop('_raw_camara', None)
    info['intentos'] = intentos
    return info


# ---------------------------------------------------------------- 3. INFORMACIÓN EN SIMPLE
def _seccion(txt, inicio_re, fin_re, max_chars=2500):
    m = re.search(inicio_re, txt, re.I | re.M)
    if not m:
        return ''
    resto = txt[m.end():]
    f = re.search(fin_re, resto, re.I | re.M) if fin_re else None
    seg = resto[:f.start()] if f else resto[:max_chars]
    return seg.strip()[:max_chars]


def _oraciones(s, n=3):
    partes = re.split(r'(?<=[\.;])\s+(?=[A-ZÁÉÍÓÚÑ])', s.strip())
    return ' '.join(p.strip() for p in partes[:n] if p.strip())


def analizar_informe(txt):
    """Informe de comisión: idea matriz/objetivo, asistencia/expositores, votación en comisión, constancias."""
    out = {}
    obj = _seccion(txt, r'\n\s*(?:I\.?\s*)?(?:OBJETIVOS?|IDEA(?:S)? MATRI(?:Z|CES)|OBJETIVO DEL PROYECTO|IDEA MATRIZ O FUNDAMENTAL)[^\n]*\n',
                   r'\n\s*(?:II\.?|CONSTANCIAS|NORMAS DE (?:CAR[ÁA]CTER|QU[ÓO]RUM)|ANTECEDENTES|ASISTENCIA)\b', 1800)
    if obj:
        out['objetivo'] = obj
    asis = _seccion(txt, r'\n\s*(?:ASISTENCIA|ASISTIERON|A (?:una o m[áa]s de )?las sesiones)[^\n]*\n?', r'\n\s*(?:ANTECEDENTES|I{1,3}\.|OBJETIVO|DISCUSI[ÓO]N)\b', 2500)
    if asis:
        out['asistencia'] = asis
    inv = re.findall(r'(?:Ministr[oa]|Subsecretari[oa]|Director[a]?|Presidente|Presidenta|Gerente|Profesor[a]?|Investigador[a]?|Abogad[oa]|Asesor[a]?|Economista)[^\n\.;,]{3,80}?(?:,|\s)\s*(?:señor|señora|don|doña|Sr\.|Sra\.)\s+[A-ZÁÉÍÓÚÑ][^\n\.;,]{3,60}', txt)
    if inv:
        vistos, lista = set(), []
        for x in inv:
            k = re.sub(r'\s+', ' ', x).strip()
            if k.lower() not in vistos:
                vistos.add(k.lower()); lista.append(k)
        out['expositores'] = lista[:25]
    vot = re.findall(r'((?:Puest[oa]s? en votaci[óo]n|Sometid[oa]s? a votaci[óo]n|En votaci[óo]n|Votaron a favor|Fue aprobad[oa]|Result[óo] aprobad[oa]|Se aprob[óo]|Se rechaz[óo]|Fue rechazad[oa])[^\n]{10,420})', txt)
    if vot:
        out['votaciones_comision'] = [re.sub(r'\s+', ' ', v).strip() for v in vot[:20]]
    quo = _seccion(txt, r'\n\s*(?:NORMAS DE (?:CAR[ÁA]CTER ORG[ÁA]NICO|QU[ÓO]RUM)[^\n]*)\n', r'\n\s*(?:[IVX]+\.|CONSTANCIAS|ANTECEDENTES|ASISTENCIA|DISCUSI[ÓO]N)\b', 900)
    if quo:
        out['quorum'] = quo
    cs = _seccion(txt, r'\n\s*(?:CONSULTA(?:S)? (?:A LA )?EXCMA\.? CORTE SUPREMA|CORTE SUPREMA)[^\n]*\n', r'\n\s*(?:[IVX]+\.|CONSTANCIAS|ANTECEDENTES|ASISTENCIA|DISCUSI[ÓO]N)\b', 600)
    if cs:
        out['corte_suprema'] = cs
    return out


def analizar_veto(txt):
    """Oficio de observaciones del Presidente: fundamento general y cada observación con su texto."""
    out = {}
    fund = _seccion(txt, r'(?:^|\n)\s*(?:FUNDAMENTOS? DE LAS OBSERVACIONES|FUNDAMENTOS?)[^\n]*\n', r'\n\s*(?:LAS OBSERVACIONES|OBSERVACIONES|CONTENIDO DE LAS OBSERVACIONES|En raz[óo]n de lo anterior|En m[ée]rito)', 60000)
    if not fund:
        fund = _seccion(txt, r'(?:ANTECEDENTES|LA INICIATIVA Y EL PROYECTO)[^\n]*\n', r'\n\s*(?:LAS OBSERVACIONES|OBSERVACIONES|En m[ée]rito)', 3000)
    if fund:
        out['fundamento'] = re.sub(r'\s+', ' ', fund)
    # cuerpo de observaciones: "AL ARTÍCULO 32 / Para suprimirlo." o "OBSERVACIÓN N° 1 ..." o "1) Para ..."
    ini = re.search(r'(?:^|\n)\s*(?:LAS OBSERVACIONES|OBSERVACIONES)\s*\n', txt)
    cuerpo = '\n' + (txt[ini.end():] if ini else txt)
    fin = re.search(r'\n\s*Dios guarde', cuerpo)
    if fin:
        cuerpo = cuerpo[:fin.start()]
    marcas = [(m.start(), m.group(0)) for m in re.finditer(r'\n\s*(?:AL\s+(?:NUEVO\s+)?ART[ÍI]CULO\s+[\w°º]+[^\n]*|AL\s+(?:INCISO|NUMERAL|LITERAL|EP[ÍI]GRAFE|T[ÍI]TULO)[^\n]*|ART[ÍI]CULO\s+[\w°º]+\s*(?:TRANSITORIO)?[^\n]*(?:nuevo)?|OBSERVACI[ÓO]N\s*(?:N[°º]\s*)?\d+[^\n]*|\d{1,2}[\)\.\-]\s+(?:Para|Al|Ag|Sup|Reemp|Interc|Elim|Modif|Incorp|Sust)[^\n]*)', cuerpo)]
    lista = []
    for k, (pos, cab) in enumerate(marcas):
        hasta = marcas[k + 1][0] if k + 1 < len(marcas) else len(cuerpo)
        bloque = cuerpo[pos:hasta].strip()
        lineas = [l.strip() for l in bloque.split('\n') if l.strip()]
        if not lineas:
            continue
        titulo = lineas[0][:200]
        texto = ' '.join(lineas[1:])[:2500] if len(lineas) > 1 else ''
        que = ''
        tl = (texto or titulo).lower()
        if 'suprim' in tl or 'elimin' in tl:
            que = 'Propone eliminar esa parte del texto aprobado por el Congreso.'
        elif 'reemplaz' in tl or 'sustit' in tl:
            que = 'Propone reemplazar esa parte por un texto nuevo.'
        elif 'agreg' in tl or 'incorpor' in tl or 'intercal' in tl or 'nuevo' in tl:
            que = 'Propone agregar un texto que el Congreso no había aprobado.'
        elif 'modific' in tl:
            que = 'Propone modificar la redacción de esa parte.'
        lista.append({'numero': k + 1, 'titulo': titulo, 'texto': texto, 'en_simple': que})
    # fundamento por artículo: "Al artículo 32: sobre ..." dentro de la sección de fundamentos
    fund_txt = out.get('fundamento', '')
    if fund_txt:
        out['fundamento'] = fund_txt[:2500]
    if fund_txt and lista:
        partes = re.split(r'(?=Al (?:nuevo )?art[íi]culo\s+[\w°º]+\s*(?:transitorio)?\s*:)', fund_txt, flags=re.I)
        for o in lista:
            m = re.search(r'ART[ÍI]CULO\s+([\w°º]+)', o['titulo'], re.I)
            if not m:
                continue
            num = m.group(1).lower().rstrip('°º')
            for pz in partes:
                if re.match(r'Al (?:nuevo )?art[íi]culo\s+' + re.escape(num) + r'\b', pz.strip(), re.I):
                    o['fundamento'] = pz.strip()[:3000]
                    break
    if lista:
        out['observaciones'] = lista[:60]
        tipos = {'eliminar': 0, 'reemplazar': 0, 'agregar': 0, 'modificar': 0}
        for o in lista:
            for kk in tipos:
                if kk in o['en_simple']:
                    tipos[kk] += 1
        out['resumen'] = f"El Presidente formuló {len(lista)} {'observaciones' if len(lista) != 1 else 'observación'}: " + ', '.join(f'{v} para {k}' for k, v in tipos.items() if v) + '.'
    firma = re.search(r'Dios guarde a V\.E\.[^\n]*\n((?:[^\n]+\n?){1,6})', txt)
    if firma:
        out['firman'] = [re.sub(r'\s+', ' ', l).strip() for l in firma.group(1).split('\n') if l.strip()][:6]
    return out


def analizar_iniciativa(txt):
    """Mensaje o moción: problema que busca resolver, fundamentos y objetivos, en las palabras del autor."""
    out = {}
    fund = _seccion(txt, r'\n\s*(?:I\.?\s*)?(?:FUNDAMENTOS?|ANTECEDENTES(?: GENERALES)?|CONSIDERANDO)[^\n]*\n', r'\n\s*(?:I{2,3}\.?\s*)?(?:OBJETIVOS?|CONTENIDO|IDEA MATRIZ|PROYECTO DE LEY|POR TANTO|En m[ée]rito)', 3000)
    if fund:
        out['fundamentos'] = fund
    obj = _seccion(txt, r'\n\s*(?:I{1,3}\.?\s*)?(?:OBJETIVOS?(?: DEL PROYECTO)?|IDEA MATRIZ|CONTENIDO DEL PROYECTO)[^\n]*\n', r'\n\s*(?:I{2,4}V?\.?\s*)?(?:CONTENIDO|PROYECTO DE LEY|POR TANTO|En m[ée]rito|ART[ÍI]CULO)', 2500)
    if obj:
        out['objetivos'] = obj
    if not fund and not obj:
        cuerpo = re.sub(r'\s+', ' ', txt[:6000])
        i = cuerpo.find('Honorable')
        out['resumen'] = _oraciones(cuerpo[i:] if i >= 0 else cuerpo, 6)[:1500]
    return out


def analizar_oficio(txt):
    out = {}
    mat = re.search(r'MAT\.?\s*:\s*([^\n]{5,300})', txt)
    if mat:
        out['materia'] = mat.group(1).strip()
    de = re.search(r'\bDE\s*:\s*([^\n]{3,160})', txt)
    a = re.search(r'\bA\s*:\s*([^\n]{3,160})', txt)
    if de:
        out['de'] = de.group(1).strip()
    if a:
        out['para'] = a.group(1).strip()
    cuerpo = re.sub(r'\s+', ' ', txt[:5000])
    out['resumen'] = _oraciones(cuerpo[cuerpo.find(':') + 1:] if ':' in cuerpo[:400] else cuerpo, 5)[:1200]
    return out


def analizar_indicaciones(txt):
    """Boletín de indicaciones: cuántas hay y quién las presentó."""
    out = {}
    aut = re.findall(r'(?:Del|De la|De los|De las|De l[oa]s)\s+(?:Honorables?\s+)?(?:Senador(?:es|a|as)?|Diputad[oa]s?|Presidente de la Rep[úu]blica|Ejecutivo)[^\n]{0,200}', txt)
    if aut:
        conteo = {}
        for a in aut:
            k = re.sub(r'\s+', ' ', a).strip()[:160]
            conteo[k] = conteo.get(k, 0) + 1
        out['autores'] = sorted(conteo.items(), key=lambda x: -x[1])[:20]
        out['n_indicaciones_aprox'] = len(aut)
    arts = re.findall(r'\n\s*(ART[ÍI]CULO\s+[\dº°]+[^\n]{0,80})', txt)
    if arts:
        out['articulos_tocados'] = list(dict.fromkeys(re.sub(r'\s+', ' ', a).strip() for a in arts))[:40]
    return out


TIPOS = {
    'INFORMEPLEY': ('📘 Informe de comisión', 'Documento en que la comisión especializada explica qué estudió, a quién escuchó, cómo votó cada artículo y qué texto propone a la Sala.'),
    'OFICIOPLEY': ('✉️ Oficio', 'Comunicación formal entre cámaras, con el Presidente o con un ministerio (por ejemplo, el texto aprobado que se envía a la otra cámara o una respuesta oficial).'),
    'INDICACIONPLEY': ('✏️ Boletín de indicaciones', 'Listado de las propuestas concretas de cambio al texto, con quién las presentó.'),
    'VETO': ('🖋️ Observaciones del Presidente (veto)', 'Oficio en que el Presidente de la República propone cambiar, agregar o eliminar partes del texto aprobado por el Congreso, explicando por qué.'),
    'INICIATIVA': ('📄 Mensaje o moción original', 'El texto con que se presentó el proyecto: el problema que busca resolver, sus fundamentos y el articulado inicial.'),
    'COMPARADO': ('📊 Texto comparado', 'Cuadro que pone lado a lado la ley vigente, el texto del proyecto y los cambios propuestos, para ver exactamente qué cambia.'),
}


def analizar(doc, info):
    tipo = doc['doc_tipo']
    txt = info['texto']
    if tipo == 'INFORMEPLEY':
        return analizar_informe(txt)
    if tipo == 'VETO':
        return analizar_veto(txt)
    if tipo == 'INICIATIVA':
        return analizar_iniciativa(txt)
    if tipo == 'INDICACIONPLEY':
        return analizar_indicaciones(txt)
    return analizar_oficio(txt)


def _prioridad(d, fecha_ref=''):
    """Qué documentos bajar primero: veto, iniciativa, informes (más recientes primero), indicaciones, oficios."""
    orden = {'VETO': 0, 'INICIATIVA': 1, 'INFORMEPLEY': 2, 'COMPARADO': 3, 'INDICACIONPLEY': 4, 'OFICIOPLEY': 5}
    cerca = 0
    if fecha_ref and d.get('fecha'):
        try:
            from datetime import date
            a = date.fromisoformat(fecha_ref); b = date.fromisoformat(d['fecha'])
            cerca = abs((a - b).days)
        except Exception:
            cerca = 0
    return (orden.get(d['doc_tipo'], 9), cerca, d.get('fecha', '') and -int(d['fecha'].replace('-', '') or 0))


def recolectar(pid, bol, fecha_ref='', max_docs=MAX_DOCS, con_citas=True, tanda=1):
    """Punto de entrada: lista + descarga + análisis + citas. Todo en RAM.
       tanda=1 → los max_docs más relevantes (respuesta rápida); tanda=2 → TODOS los demás documentos del proyecto;
       max_docs=0 → todo de una vez."""
    from datetime import date
    docs, errores = listar_documentos(pid, bol)
    ordenados = sorted(docs, key=lambda d: _prioridad(d, fecha_ref))
    if not max_docs:
        elegidos = ordenados
    elif tanda == 2:
        elegidos = ordenados[max_docs:]
    else:
        elegidos = ordenados[:max_docs]
    salida = []

    def uno(d):
        try:
            info = obtener_texto(d)
            an = analizar(d, info) if info['texto'] else {}
            citas = []
            if con_citas and info['texto']:
                try:
                    import buscador as B
                    ctx = B.contexto_texto(info['texto'][:60000])
                    citas = ctx.get('citas', [])[:12]
                except Exception:
                    citas = []
            if info.get('ocr'):
                for c in citas:
                    c['por_confirmar'] = True
            r = dict(d); r.update({'formato': info['formato'], 'bytes': info['bytes'], 'caracteres': info['caracteres'],
                                   'nombre_archivo': info['nombre'], 'escaneado': info['escaneado'] and not info.get('ocr'),
                                   'fuente_texto': info.get('fuente_texto', ''), 'url_alternativa': info.get('url_alternativa', ''),
                                   'ocr': bool(info.get('ocr')), 'ocr_paginas': info.get('ocr_paginas', 0), 'ocr_total_paginas': info.get('ocr_total_paginas', 0),
                                   'ocr_confianza': info.get('ocr_confianza', 0), 'ocr_error': info.get('ocr_error', ''),
                                   'analisis': an, 'citas': citas,
                                   'extracto': re.sub(r'\s+', ' ', info['texto'][:1200])})
            return r
        except Exception as e:
            r = dict(d); r.update({'error': f'{type(e).__name__}: {str(e)[:120]}'})
            return r

    with ThreadPoolExecutor(max_workers=6) as ex:
        salida = list(ex.map(uno, elegidos))
    for d in salida:
        d['etiqueta'], d['que_es'] = TIPOS.get(d['doc_tipo'], ('📎 Documento', 'Documento oficial del proyecto.'))
    resto = [] if (tanda == 2 or not max_docs) else [dict(d, etiqueta=TIPOS.get(d['doc_tipo'], ('📎 Documento', ''))[0]) for d in ordenados[max_docs:]]
    n_ok = sum(1 for d in salida if not d.get('error'))
    return {'boletin': bol, 'pid': pid, 'fecha_ref': fecha_ref, 'total_documentos': len(docs), 'analizados': n_ok, 'tanda': tanda,
            'pendientes': len(resto) if tanda == 1 and max_docs else 0,
            'documentos': salida, 'otros': resto, 'errores': errores, 'generado': date.today().isoformat(),
            'nota': 'Documentos descargados en el momento desde camara.cl (o su copia en senado.cl), leídos en memoria y descartados al terminar. Si un documento es una imagen escaneada, se reconoce su texto con OCR local en el mismo servidor, sin enviarlo a terceros. No se guarda ningún archivo.'}


if __name__ == '__main__':
    import sys, json, time
    pid = sys.argv[1] if len(sys.argv) > 1 else '18872'
    bol = sys.argv[2] if len(sys.argv) > 2 else '18216-05'
    t0 = time.time()
    r = recolectar(pid, bol)
    print(json.dumps({k: v for k, v in r.items() if k != 'documentos'}, ensure_ascii=False, indent=1)[:1500])
    for d in r['documentos']:
        print('\n==', d['etiqueta'], d['fecha'], d['etapa'], d.get('formato'), d.get('caracteres'), d.get('error', ''))
        for k, v in (d.get('analisis') or {}).items():
            print('  ·', k, ':', (json.dumps(v, ensure_ascii=False)[:400]))
        print('  · citas:', [c.get('cita') for c in d.get('citas', [])][:8])
    print('\n%.1f s' % (time.time() - t0))
