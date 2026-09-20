# El Poder en Simple — explicador.py
# Traduce a lenguaje ciudadano lo que dice el Congreso en cada votación ("observación") y en cada paso de
# tramitación. Son reglas de lectura del texto oficial: no inventan datos, solo explican qué significa.
import re, unicodedata, html as _html

def _n(s):
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', s).strip()

def _frase(s, maxlen=260):
    s = re.sub(r'\s+', ' ', _html.unescape(s or '')).strip()
    return s if len(s) <= maxlen else s[:maxlen].rsplit(' ', 1)[0] + '…'

_STOP_COM = {'en', 'tanto', 'cuya', 'cuyo', 'que', 'para', 'recaida', 'recaido', 'respecto', 'con', 'del', 'al', 'la', 'las', 'los', 'el', 'y', 'e', 'a', 'por', 'sobre', 'tanto'}
def _comision(t):
    m = re.search(r'comisi[oó]n(?:es)?\s+(?:de\s+|del\s+)?(.+)', t, flags=re.I)
    if not m:
        return ''
    resto = re.split(r'[.;)]|,\s+(?=[a-z])', m.group(1), 1)[0]
    palabras = []
    for w in resto.split():
        wl = _n(w)
        if wl in _STOP_COM and not (wl in ('y', 'e', 'la', 'las', 'los', 'el', 'del', 'de') and palabras and len(palabras) < 6):
            break
        palabras.append(w)
    # quita conectores finales: "Deportes y" → "Deportes"
    while palabras and _n(palabras[-1]) in ('y', 'e', 'la', 'las', 'los', 'el', 'del', 'de'):
        palabras.pop()
    c = ' '.join(palabras).strip()
    if not c or _n(c) in ('unida', 'unidas'):
        return ''
    if _n(c).startswith('mixta'):
        return 'Comisión Mixta'
    # los nombres de comisión empiezan con mayúscula: corta donde empiezan verbos/minúsculas ("la aprobacion en general")
    out = []
    for w in c.split():
        if out and w[0].islower() and _n(w) not in ('y', 'e', 'de', 'del', 'la', 'las', 'los', 'el'):
            break
        out.append(w)
    while out and _n(out[-1]) in ('y', 'e', 'de', 'del', 'la', 'las', 'los', 'el'):
        out.pop()
    return 'Comisión de ' + ' '.join(out) if out else ''

_PARTES = {'articulo': 'el artículo', 'articulos': 'los artículos', 'numeral': 'el numeral', 'numerales': 'los numerales',
           'numero': 'el número', 'numeros': 'los números', 'letra': 'la letra', 'letras': 'las letras', 'literal': 'la letra', 'literales': 'las letras',
           'inciso': 'el inciso', 'incisos': 'los incisos', 'encabezado': 'el encabezado'}
_ORD = {'primero': '1°', 'segundo': '2°', 'tercero': '3°', 'cuarto': '4°', 'quinto': '5°', 'sexto': '6°', 'septimo': '7°', 'octavo': '8°', 'noveno': '9°', 'decimo': '10°', 'final': 'final'}
_REF = r'(?:[0-9]+[°]?\)?(?:\s*(?:bis|ter|quater))?|unico|[a-z]\)|final)'
_PAT = r'\b(articulos?|numeral(?:es)?|numeros?|letras?|literal(?:es)?|incisos?|encabezado)\b(?:\s+(' + _REF + r'(?:\s*(?:,|y|a|al)\s*' + _REF + r')*))?(\s+transitorios?)?'

def _parte(t):
    """Qué parte del proyecto se vota, con su jerarquía: 'la letra b) del número 1 del artículo único'.
    Solo considera lo que va ANTES de 'del proyecto' / 'de la ley' (lo que sigue es la norma que se modifica)."""
    n = _n(t)
    n = re.sub(r'\b(' + '|'.join(_ORD) + r')\b', lambda m: _ORD[m.group(1)], n)
    corte = re.search(r'\b(del proyecto|de la ley|del codigo|del decreto|del mensaje|del texto|de la carta|de la constitucion)\b', n)
    zona = n[:corte.start()] if corte else n
    partes = []
    for m in re.finditer(_PAT, zona):
        tipo, ref, trans = m.group(1), (m.group(2) or '').strip(), bool(m.group(3))
        if tipo == 'encabezado':
            partes.append('el encabezado'); continue
        if not ref:
            continue
        s = f"{_PARTES[tipo]} {ref.replace('unico', 'único').replace(')', '')}"
        if trans:
            s += ' transitorio' + ('s' if tipo.endswith('s') else '')
        partes.append(s)
    if not partes and corte and corte.group(1) == 'del proyecto':
        return ''
    return ' del '.join(partes[:3]).replace(' del el ', ' del ').replace(' del la ', ' de la ').replace(' del los ', ' de los ').replace(' del las ', ' de las ')

def _quorum(q):
    n = _n(q)
    if 'simple' in n: return 'Bastaba la mayoría de l@s presentes (quórum simple).'
    if 'calificado' in n: return 'Necesitaba el voto a favor de la mayoría absoluta de l@s 155 diputad@s en ejercicio: 78 votos (quórum calificado).'
    if 'organic' in n: return 'Necesitaba 4/7 de l@s diputad@s en ejercicio: 89 votos (ley orgánica constitucional).'
    if 'reforma' in n or 'constitu' in n or '2/3' in n or 'dos tercios' in n: return 'Es una reforma constitucional: necesitaba 4/7 (89 votos) o 2/3 (104 votos) según el capítulo.'
    if '3/5' in n or 'tres quintos' in n: return 'Necesitaba 3/5 de l@s diputad@s en ejercicio: 93 votos.'
    return ''

def _resultado(res, si, no, abst, quorum=''):
    r = _n(res)
    if 'aprob' in r:
        return f'Se aprobó con {si} votos a favor, {no} en contra y {abst} abstenciones.'
    if 'rechaz' in r:
        extra = ''
        if quorum and si > no and 'simple' not in _n(quorum):
            extra = ' Aunque tuvo más votos a favor que en contra, no alcanzó el mínimo que exige el quórum especial.'
        return f'Se rechazó: {si} a favor, {no} en contra y {abst} abstenciones.{extra}'
    if 'empate' in r:
        return f'Hubo empate ({si} a {no}); por reglamento se repite la votación.'
    return f'Resultado: {res} ({si} a favor, {no} en contra, {abst} abstenciones).' if res else ''

def _tramite(tr):
    n = _n(tr)
    if 'primer' in n: return 'Es el primer trámite: la Cámara de Diputados es la primera en revisar este proyecto; si lo aprueba, pasa al Senado.'
    if 'segundo' in n: return 'Es el segundo trámite: el proyecto nació en el Senado, que ya lo aprobó, y ahora lo revisa la Cámara.'
    if 'tercer' in n: return 'Es el tercer trámite: la Cámara ya había aprobado el proyecto, el Senado le hizo cambios, y ahora la Cámara decide si acepta esos cambios.'
    if 'mixta' in n: return 'Las dos cámaras no se pusieron de acuerdo; una Comisión Mixta de diputad@s y senador@s propuso una salida y aquí la Cámara la vota.'
    if 'observacion' in n or 'veto' in n: return 'El Presidente de la República devolvió el proyecto con observaciones (veto) y la Cámara vota si las acepta.'
    return ''

def _informe(inf, tramite=''):
    n = _n(inf)
    if 'primer' in n: return 'La comisión especializada ya lo estudió por primera vez (primer informe): la Sala vota la idea general y, si no hubo indicaciones, también el texto.'
    if 'segundo' in n: return 'Es la discusión en detalle (segundo informe): la comisión ya revisó las indicaciones y la Sala vota artículo por artículo.'
    if 'observ' in n: return 'Se votan las observaciones del Presidente.'
    if 'sin informe' in n:
        return 'Se vota directamente en la Sala, sin informe previo de comisión (ocurre, por ejemplo, con los cambios del Senado o cuando hay urgencia).'
    return ''

_OTROS = {
    'acusacion constitucional': ('Es una acusación constitucional: la Cámara vota si acusa a una autoridad (ministro, juez, intendente, etc.) por infringir la Constitución o las leyes. Si se aprueba, la autoridad queda suspendida y el Senado actúa como jurado.', 'Acusación constitucional'),
    'creacion comision investigadora': ('Se vota crear una comisión investigadora: un grupo de diputad@s que fiscalizará actos del Gobierno o de un servicio público sobre un tema concreto. Necesita el apoyo de al menos 2/5 de la Cámara (62 votos).', 'Crear una comisión investigadora'),
    'informe comision investigadora': ('Se vota el informe final de una comisión investigadora: sus conclusiones y propuestas sobre lo fiscalizado. Aprobarlo significa que la Cámara las hace suyas y las envía a las autoridades.', 'Informe de comisión investigadora'),
    'cambio de tramite': ('Se vota un cambio en el camino del proyecto: por ejemplo, enviarlo a otra comisión o cambiar el orden en que se estudia.', 'Cambio de trámite'),
    'otros': ('Votación de la Sala que no es un proyecto de ley: puede ser un procedimiento (plazos, orden del día, permisos), un homenaje u otro acuerdo interno de la Cámara.', 'Acuerdo o procedimiento de la Sala'),
}

def explicar_votacion(texto, tramite='', informe='', quorum='', resultado='', si=0, no=0, abst=0, tipo_proyecto='', nombre_proyecto='', descripcion=''):
    """Devuelve {'que': qué se vota en simple, 'contexto': trámite/informe, 'quorum': ..., 'resultado': ..., 'texto': párrafo unido}."""
    t = _html.unescape(texto or '').strip()
    n = _n(t)
    parte = _parte(t)
    com = _comision(t)
    que = ''
    dsc = re.sub(r'^\d+-', '', _n(descripcion))
    if _n(tipo_proyecto) == 'otros' and dsc in _OTROS and not t:
        que = _OTROS[dsc][0]
        rr = _resultado(resultado, si, no, abst, quorum)
        ap = 'aprob' in _n(resultado)
        cons = '¿Y ahora? ' + ({'acusacion constitucional': 'La autoridad queda suspendida de sus funciones y el Senado decidirá si es culpable.' if ap else 'La acusación se rechaza y la autoridad sigue en su cargo.',
                              'creacion comision investigadora': 'La comisión se forma y tendrá un plazo para citar autoridades, pedir documentos y emitir un informe.' if ap else 'La comisión no se crea.',
                              'informe comision investigadora': 'Las conclusiones se envían al Gobierno y a los organismos competentes (Contraloría, Fiscalía) para que actúen.' if ap else 'La Cámara no respalda las conclusiones de la comisión.',
                              'cambio de tramite': 'El proyecto sigue por el nuevo camino acordado.' if ap else 'El proyecto sigue su camino original.'}.get(dsc, 'La Sala continúa con su trabajo según lo acordado.' if ap else 'La propuesta no prospera.'))
        tit = f"{_OTROS[dsc][1]} · {'Aprobado' if ap else 'Rechazado'} {si}-{no}"
        return {'que': que, 'contexto': '', 'quorum': _quorum(quorum), 'resultado': rr, 'consecuencia': cons, 'propuesta': '', 'titular': tit,
                'texto': ' '.join(x for x in [que, rr, cons] if x)}
    if 'proyecto de resolucion' in _n(tipo_proyecto) or n.startswith('en votacion el proyecto de resolucion') or 'proyecto de resolucion' in n:
        que = 'No es una ley: es un proyecto de resolución, una petición formal de la Cámara al Gobierno u otra autoridad para que haga algo. No obliga, pero fija una postura política.'
    elif 'proyecto de acuerdo' in n or 'proyecto de acuerdo' in _n(tipo_proyecto):
        if 'tratado' in n or 'convenio' in n or 'acuerdo entre' in n or 'aprueba el' in n:
            que = 'Se vota si Chile aprueba un tratado o convenio internacional: el Congreso no puede cambiarle el texto, solo aceptarlo o rechazarlo completo.'
        else:
            que = 'Es un proyecto de acuerdo: la Cámara manifiesta una postura o pide algo a una autoridad. No crea una ley.'
    elif 'inadmisibil' in n:
        que = 'No se vota el fondo: se vota si una indicación (propuesta de cambio) puede o no discutirse. La Mesa la declaró inadmisible (por ejemplo, porque solo el Presidente puede proponer gasto público) y alguien reclamó; la Sala decide si esa declaración se mantiene.'
    elif 'observacion' in n and 'presidente' in n:
        que = 'Se vota una observación (veto) del Presidente de la República al texto que el Congreso ya había aprobado: si se acepta, la ley queda con el cambio que pide el Presidente.'
    elif 'comision mixta' in n and ('proposicion' in n or 'informe' in n):
        que = 'Se vota la propuesta de la Comisión Mixta para resolver las diferencias entre la Cámara y el Senado. Si ambas cámaras la aprueban, el proyecto queda despachado.'
    elif re.search(r'\b(enmiendas?|modificaciones)\b.*\bsenado\b', n) or ('senado' in n and 'incorporad' in n):
        detalle = ''
        m = re.search(r'(reemplaza|sustituye|agrega|incorpora|suprime|elimina|modifica|intercala)\s+(.*?)(?=[.;,]|$)', n)
        if m:
            accion = {'reemplaza': 'reemplaza', 'sustituye': 'reemplaza', 'agrega': 'agrega', 'incorpora': 'agrega', 'suprime': 'elimina', 'elimina': 'elimina', 'modifica': 'cambia', 'intercala': 'agrega'}[m.group(1)]
            detalle = f' En concreto, el Senado {accion} {_frase(m.group(2), 140)}.'
        que = 'Se vota si la Cámara acepta los cambios que el Senado le hizo al proyecto que ella ya había aprobado.' + detalle + \
              ' Si los acepta, el proyecto queda listo para ser ley; si los rechaza, va a una Comisión Mixta.'
    elif 'indicacion' in n:
        m = re.search(r'indicaci[oó]n(?:es)?(?: renovada)?(?: de (?:l[ao]s? )?(?:diputad[oa]s?|senador(?:a|es|as)?|ejecutivo|s\.e\. el presidente de la republica)?\s*([^,]*?))?(?:,| para| que| al| a fin)', t, flags=re.I)
        quien = (m.group(1) or '').strip(' ,') if m else ''
        m2 = re.search(r'(?:para|que)\s+(agregar|incorporar|reemplazar|sustituir|suprimir|eliminar|modificar|intercalar|introducir)\s+(.*?)(?=[.;]|$)', t, flags=re.I)
        cambio = f' Propone {m2.group(1).lower()} {_frase(m2.group(2), 160)}.' if m2 else ''
        renov = ' Se llama "renovada" porque la comisión la había rechazado y un grupo de parlamentari@s pidió que la Sala la vote de nuevo.' if 'renovada' in n or 'renovacion' in n else ''
        que = f'Se vota una indicación, es decir, una propuesta para cambiar el texto del proyecto{(" presentada por " + quien) if quien else ""}.{cambio}{renov}'
    elif parte and ('sugerido' in n or 'propuesto' in n or 'terminos' in n):
        que = f'Se vota {parte} del proyecto, con la redacción que propuso la {com or "comisión"}.'
        if 'votacion separada' in n:
            que += ' Se vota aparte porque un@ parlamentari@ pidió pronunciarse sobre esta parte por separado, en vez de junto con el resto.'
        if 'quorum' in n:
            que += ' Se vota por separado porque esta parte exige un quórum especial (más votos que una ley común).'
    elif parte:
        que = f'Se vota {parte} del proyecto.'
        if 'votacion separada' in n:
            que += ' Alguien pidió votarlo aparte del resto del texto.'
        if 'transitorio' in parte:
            que += ' Los artículos transitorios regulan cómo y cuándo entra en vigencia la ley (plazos, etapas, situaciones ya en curso).'
    elif 'en general' in n or 'idea de legislar' in n:
        que = 'Se vota "en general": si la Cámara está de acuerdo con la idea de legislar sobre este tema. Aún no se vota el detalle de cada artículo.'
    elif 'en particular' in n:
        que = 'Se vota "en particular": el detalle del texto, artículo por artículo.'
    elif not t:
        inf = _n(informe); trn = _n(tramite)
        if 'primer' in inf:
            que = 'Se vota "en general": si la Cámara está de acuerdo con la idea de legislar sobre este tema. Si nadie propuso cambios, en la misma votación queda aprobado también el texto.'
        elif 'segundo' in inf:
            que = 'Se vota el resto del texto del proyecto: todos los artículos que nadie pidió votar por separado, con la redacción que propuso la comisión.'
        elif 'tercer' in trn:
            que = 'Se vota si la Cámara acepta los cambios que le hizo el Senado al proyecto (la fuente oficial no detalla cuáles).'
        elif 'mixta' in trn:
            que = 'Se vota la propuesta de la Comisión Mixta para resolver las diferencias entre la Cámara y el Senado.'
        elif 'sin informe' in inf:
            que = 'Se vota el proyecto directamente en la Sala, sin informe previo de comisión (suele ocurrir con proyectos simples o con urgencia).'
        else:
            que = 'Se vota el proyecto completo tal como viene de la comisión (la fuente oficial no detalla una parte específica).'
    else:
        que = 'Se vota: ' + _frase(t, 220)
    if nombre_proyecto and 'resolución' not in que and 'tratado' not in que and 'proyecto de acuerdo' not in que:
        que = f'Este proyecto busca: “{_frase(nombre_proyecto, 170)}”. ' + que
    ctx = ' '.join(x for x in [_tramite(tramite), _informe(informe, tramite)] if x)
    qq = _quorum(quorum)
    rr = _resultado(resultado, si, no, abst, quorum)
    clase = _clase(n, tipo_proyecto, que)
    cons = _consecuencia(n, resultado, tramite, informe, parte, clase, si, no, quorum)
    prop = _texto_propuesto(t) if clase not in ('tratado', 'resolucion', 'acuerdo') else ''
    tit = _titular(que, parte, resultado, si, no, n, clase, quorum)
    return {'que': que, 'contexto': ctx, 'quorum': qq, 'resultado': rr, 'consecuencia': cons, 'propuesta': prop, 'titular': tit,
            'texto': ' '.join(x for x in [que, ctx, qq, rr, cons] if x)}

def _texto_propuesto(t):
    """Si la observación trae entre comillas el texto que se propone (indicaciones, artículos nuevos), lo separa
    para mostrarlo como 'así quedaría' frente al 'así dice hoy' que aporta LeyChile."""
    m = re.search(r'[“"]\s*(Art[ií]culo[^”"]{40,}|[^”"]{80,})\s*[”"]', t or '')
    if not m:
        return ''
    s = re.sub(r'\s+', ' ', m.group(1)).strip()
    # descartar cuando la cita es solo el nombre del proyecto ("Modifica la ley N° ... para ...")
    if re.match(r'(modifica|crea|establece|regula|aprueba|prorroga|dispone|sanciona|declara|otorga|faculta|autoriza|fija|perfecciona|fortalece|reconoce|aumenta|tipifica|incorpora|introduce)\b', _n(s)) and len(s) < 260:
        return ''
    return s

def _clase(n, tipo_proyecto, que):
    tp = _n(tipo_proyecto); q = _n(que)
    if 'inadmisibil' in n: return 'inadmisibilidad'
    if 'tratado' in q or 'tratado' in n or 'convenio' in n: return 'tratado'
    if 'proyecto de resolucion' in n or 'resolucion' in tp: return 'resolucion'
    if 'proyecto de acuerdo' in n or 'acuerdo' in tp: return 'acuerdo'
    if 'observacion' in n and 'presidente' in n: return 'veto'
    if 'comision mixta' in n: return 'mixta'
    if re.search(r'\b(enmiendas?|modificaciones)\b.*\bsenado\b', n) or ('senado' in n and 'incorporad' in n): return 'senado'
    if 'indicacion' in n: return 'indicacion'
    if 'en general' in q: return 'general'
    return 'parte'

def _consecuencia(n, resultado, tramite='', informe='', parte='', clase='parte', si=0, no=0, quorum=''):
    """Qué pasa ahora con el proyecto, según lo votado y el resultado."""
    r = _n(resultado); trn = _n(tramite)
    if not r:
        return ''
    ap = 'aprob' in r
    nota_q = ' (tuvo más votos a favor que en contra, pero no llegó al mínimo del quórum especial)' if (not ap and si > no) else ''
    if clase == 'inadmisibilidad':
        return '¿Y ahora? ' + ('La Sala mantuvo la inadmisibilidad: esa propuesta de cambio no se discute.' if ap else 'La Sala revirtió la decisión: la propuesta de cambio sí podrá votarse.')
    if clase in ('resolucion', 'acuerdo'):
        return '¿Y ahora? ' + ('La petición se envía formalmente a la autoridad correspondiente, que no está obligada a cumplirla.' if ap else 'La petición no se envía.')
    if clase == 'tratado':
        return '¿Y ahora? ' + ('El tratado sigue su camino (Senado o promulgación) para que Chile quede obligado por él.' if ap else 'Chile no ratifica el tratado por ahora.')
    if clase == 'veto':
        return '¿Y ahora? ' + ('El cambio pedido por el Presidente queda incorporado a la ley.' if ap else 'La Cámara rechazó la observación; el Congreso puede insistir en su texto original con 2/3 de los votos.')
    if clase == 'mixta' or 'mixta' in trn:
        return '¿Y ahora? ' + ('Si el Senado también la aprueba, el proyecto queda despachado al Presidente para ser ley.' if ap else 'Al rechazar la propuesta, no hay ley en los puntos en disputa (salvo insistencia del Presidente con quórum especial).')
    if clase == 'senado' or 'tercer' in trn:
        return '¿Y ahora? ' + ('Con los cambios del Senado aceptados, el proyecto queda despachado por el Congreso y pasa al Presidente para promulgarlo.' if ap else 'Al rechazar los cambios del Senado' + nota_q + ', el proyecto va a una Comisión Mixta de diputad@s y senador@s para buscar un acuerdo.')
    if clase == 'indicacion':
        return '¿Y ahora? ' + ('La propuesta de cambio se incorpora al texto del proyecto.' if ap else 'La propuesta de cambio se descarta' + nota_q + '; el texto sigue como venía de la comisión.')
    if parte:
        P = parte[0].upper() + parte[1:]
        sigue = ' hacia el Senado.' if 'primer' in trn else (' de vuelta al Senado, que revisará las diferencias.' if 'segundo' in trn else '.')
        return '¿Y ahora? ' + (f'{P} queda dentro del proyecto, que sigue su trámite{sigue}' if ap else f'{P} se cae{nota_q}: no formará parte del proyecto.')
    if clase == 'general' or 'primer' in _n(informe):
        return '¿Y ahora? ' + ('La idea de legislar fue aprobada: ahora se discuten y votan los detalles.' if ap else 'La idea de legislar fue rechazada' + nota_q + ': el proyecto no puede volver a presentarse hasta dentro de un año.')
    sigue = ' hacia el Senado.' if 'primer' in trn else (' de vuelta al Senado.' if 'segundo' in trn else '.')
    return '¿Y ahora? ' + (f'El proyecto sigue su trámite{sigue}' if ap else 'El proyecto se detiene en este punto' + nota_q + '.')

def _titular(que, parte, resultado, si, no, n, clase='parte', quorum=''):
    """Una sola línea con lo esencial, para el listado y el inicio del recuadro."""
    r = _n(resultado)
    res = ('Aprobado' if 'aprob' in r else 'Rechazado' if 'rechaz' in r else (resultado or '')) + (f' {si}-{no}' if (si or no) else '')
    if 'rechaz' in r and si > no:
        res += ' (no alcanzó el quórum)'
    base = {'inadmisibilidad': 'Se decide si una propuesta de cambio puede discutirse', 'veto': 'Veto del Presidente', 'mixta': 'Propuesta de la Comisión Mixta',
            'senado': 'Cambios hechos por el Senado', 'indicacion': 'Propuesta de cambio al texto (indicación)', 'tratado': 'Tratado internacional',
            'resolucion': 'Petición al Gobierno (no es ley)', 'acuerdo': 'Proyecto de acuerdo (no es ley)', 'general': 'Idea de legislar (votación en general)'}.get(clase)
    if not base:
        if parte: base = parte[0].upper() + parte[1:] + (' (votado aparte)' if 'separada' in n else '')
        elif 'en general' in que.lower(): base = 'Idea de legislar (votación en general)'
        elif 'resto del texto' in que: base = 'Resto del texto del proyecto'
        else: base = 'Texto del proyecto'
    return f'{base} · {res}'.strip(' ·')

# ----------------------------------------------------------------- PASOS DE TRAMITACIÓN (Senado / Cámara)
def explicar_tramite(que, etapa='', camara=''):
    """Explica un paso de la tramitación oficial ("Cuenta de proyecto. Pasa a Comisión de...")."""
    t = _html.unescape(que or '').strip(); n = _n(t)
    cam = 'el Senado' if 'senado' in _n(camara) else ('la Cámara de Diputados' if 'diputad' in _n(camara) else 'la cámara')
    sala = 'del Senado' if cam == 'el Senado' else 'de ' + cam
    com = _comision(t)
    if n.startswith('ingreso de proyecto'):
        return f'El proyecto fue presentado oficialmente en {cam}. Aquí empieza su camino.'
    if 'cuenta de proyecto' in n or ('cuenta' in n and 'pasa a comision' in n):
        return f'Se informó a la Sala {sala} que llegó el proyecto y se envió a la {com or "comisión correspondiente"} para que lo estudie en detalle antes de votarlo.'
    if 'comunica' in n and 'aprobacion en general' in n:
        return f'Se avisó a la {com or "comisión"} que la Sala aprobó la idea de legislar y se le devolvió el proyecto para revisar las indicaciones.'
    if 'primer informe' in n and 'cuenta' not in n:
        return f'La {com or "comisión"} terminó su primer estudio y entregó su informe con una propuesta de texto. Ahora la Sala puede votar la idea de legislar.'
    if 'segundo informe' in n and 'cuenta' not in n:
        return f'La {com or "comisión"} revisó las indicaciones (propuestas de cambio) y entregó su segundo informe. Ahora la Sala vota el detalle, artículo por artículo.'
    if 'queda para tabla' in n:
        return 'La Sala ya recibió el informe: el proyecto queda en la lista de asuntos listos para votarse.'
    if 'urgencia' in n:
        tipo = 'discusión inmediata (6 días)' if 'inmediata' in n else ('suma urgencia (15 días)' if 'suma' in n else ('urgencia simple (30 días)' if 'simple' in n else 'urgencia'))
        if 'retira' in n:
            return f'El Gobierno retiró la urgencia: ya no hay plazo obligado para despacharlo.'
        return f'El Gobierno pidió apurar el proyecto con {tipo}: la cámara debería despacharlo dentro de ese plazo.'
    if 'aprobado en general' in n or ('discusion general' in n and 'aprobado' in n):
        return f'La Sala {sala} aprobó la idea de legislar (votación "en general"). Ahora se pueden proponer cambios al detalle.'
    if 'rechazado' in n and 'general' in n:
        return f'La Sala {sala} rechazó la idea de legislar: el proyecto no sigue, salvo que insista la otra cámara.'
    if 'discusion particular' in n or 'aprobado en particular' in n:
        return f'La Sala {sala} votó el texto en detalle (artículo por artículo) y lo aprobó. Terminó su trabajo en esta etapa.'
    if 'oficio de ley a camara revisora' in n or 'camara revisora' in n:
        otra = 'al Senado' if 'diputad' in _n(camara) else 'a la Cámara de Diputados'
        return f'{cam[0].upper()+cam[1:]} envió el texto aprobado {otra}, que ahora deberá revisarlo desde cero.'
    if 'oficio de ley al ejecutivo' in n or 'ejecutivo' in n and 'oficio' in n:
        return 'El Congreso terminó: el texto aprobado por ambas cámaras se envió al Presidente de la República para que lo promulgue (o lo vete).'
    if 'tribunal constitucional' in n:
        return 'Antes de ser ley, el Tribunal Constitucional revisa que el texto respete la Constitución (control obligatorio para ciertas normas o por reclamo de parlamentari@s).'
    if 'promulg' in n:
        return 'El Presidente firmó la promulgación: la ley existe oficialmente y solo falta publicarla.'
    if 'diario oficial' in n or 'publica' in n:
        return 'La ley fue publicada en el Diario Oficial: desde ese momento rige (salvo que ella misma fije otra fecha).'
    if 'comision mixta' in n:
        return 'Las dos cámaras no coincidieron en el texto; se forma una Comisión Mixta (diputad@s y senador@s) para buscar un acuerdo.'
    if 'comunica' in n and 'aprobacion en general' in n:
        return f'Se avisó a la {com or "comisión"} que la Sala aprobó la idea de legislar y se le devolvió el proyecto para revisar las indicaciones.'
    if 'indicacion' in n and ('plazo' in n or 'ingreso' in n):
        return 'Se presentaron indicaciones: propuestas concretas de cambio al texto, que la comisión deberá analizar.'
    if 'archiv' in n:
        return 'El proyecto fue archivado: llevaba mucho tiempo sin avanzar y se cierra su tramitación (podría desarchivarse más adelante).'
    if 'retir' in n:
        return 'Quien presentó el proyecto lo retiró: deja de tramitarse.'
    if 'oficio' in n:
        return f'{cam[0].upper()+cam[1:]} envió una comunicación oficial (oficio) a otra institución sobre este proyecto.'
    if 'cuenta' in n:
        return f'Se informó a la Sala {sala} de un documento recibido sobre este proyecto: {_frase(t, 160)}'
    return ''


def explicar_votacion_senado(v):
    """Explica una votación de la Sala del Senado (tramitacion.senado.cl): tipo, etapa, quórum, pareos y resultado."""
    tema = _html.unescape(v.get('tema') or ''); n = _n(tema); tipo = _n(v.get('tipo') or ''); etapa = _n(v.get('etapa') or '')
    si, no, ab, pa = int(v.get('si') or 0), int(v.get('no') or 0), int(v.get('abst') or 0), int(v.get('pareo') or 0)
    if 'general' in tipo or 'en general' in n:
        que = 'El Senado votó "en general": si está de acuerdo con la idea de legislar sobre este proyecto. El detalle de cada artículo se vota después.'
        if 'articulos que no fueron objeto de indicaciones' in n:
            que += ' En la misma votación se dieron por aprobados los artículos a los que nadie propuso cambios.'
    elif 'particular' in tipo or 'en particular' in n:
        parte = _parte(tema)
        que = f'El Senado votó en detalle {parte + " " if parte else ""}del proyecto (discusión particular).'
    elif 'mixta' in n:
        que = 'El Senado votó la propuesta de la Comisión Mixta para zanjar las diferencias con la Cámara de Diputados.'
    elif 'veto' in n or 'observacion' in n:
        que = 'El Senado votó las observaciones (veto) del Presidente de la República al texto ya aprobado.'
    elif 'insist' in n:
        que = 'El Senado votó si insiste en su texto frente al desacuerdo con la Cámara.'
    else:
        que = 'Votación de la Sala del Senado sobre este proyecto.'
    if 'segundo tramite' in etapa:
        que += ' El proyecto venía aprobado por la Cámara de Diputados; el Senado actúa como cámara revisora.'
    elif 'primer tramite' in etapa:
        que += ' El proyecto nació en el Senado; después pasará a la Cámara de Diputados.'
    elif 'tercer tramite' in etapa:
        que += ' Es el tercer trámite: el Senado decide si acepta los cambios que hizo la Cámara.'
    q = _n(v.get('quorum') or '')
    qq = ''
    if q in ('q.s.', 'qs', 'simple') or 'simple' in q: qq = 'Bastaba la mayoría de l@s senador@s presentes (quórum simple).'
    elif 'q.c' in q or 'calificado' in q: qq = 'Necesitaba la mayoría absoluta de l@s 50 senador@s en ejercicio: 26 votos (quórum calificado).'
    elif 'l.o.c' in q or 'organic' in q: qq = 'Necesitaba 4/7 de l@s senador@s en ejercicio: 29 votos (ley orgánica constitucional).'
    elif 'r.c' in q or 'reforma' in q: qq = 'Reforma constitucional: necesitaba 4/7 (29 votos) o 2/3 (34 votos) según el capítulo.'
    res = f'Resultado: {"aprobado" if si > no else "rechazado"} con {si} a favor, {no} en contra y {ab} abstenciones.'
    if pa:
        res += f' Hubo {pa} pareo{"s" if pa > 1 else ""}: senador@s de posiciones opuestas que acuerdan no votar para que la ausencia de uno no cambie el resultado.'
    return ' '.join(x for x in [que, qq, res] if x)
