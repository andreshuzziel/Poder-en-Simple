#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hornea elecciones_geografia.json: la geografía real de Chile convertida a paths SVG,
lista para el molde de la página (sin base de datos: un ZIP, un JSON, un HTML).

Fuentes (descarga única, cacheada en /tmp):
  · Trazado comunal: github.com/alvaroparedesl/geochile (geojson/chile.geojson, rama
    master; 343 comunas continentales con NOM_COM y geometría).
  · Cómuna → distrito electoral 2025: se DERIVA del ZIP oficial de diputados
    (PRELIMINARES_DIPUTADOS.zip, 28 XLSX uno por distrito, cada fila de mesa trae
    columna `distrito` + `comuna`). Es la nómina DPA/Servel vigente, sin copiar a mano.

Notas de datos:
  · Los atributos DISTRITO/CIRCUN del geojson están obsoletos (pre-2018, 1-59) y
    Ñuble sigue etiquetada como Biobío → se IGNORAN; el vínculo es por NOMBRE de
    comuna normalizado contra la nómina del ZIP.
  · Ñuble := distrito 19 (las 21 comunas del viejo Biobío oriente).
  · Sin polígono en geochile: Isla de Pascua y Juan Fernández (D7) y Río Verde (D28)
    → quedan como chip/nota en el mapa, como siempre.
Salida: {fuente, ancho, alto, celdas:[{n, di, re, p, c}], centros_di, centros_re,
comuna_distrito}. Proyección: mercator simple → viewBox 460×H real (ratio país),
simplificación Douglas-Peucker a 0.9 px y coordenadas enteras.
"""
import json
import os
import re as _re
import unicodedata
import urllib.request
import zipfile

# FIJADO al commit 6e6684f (2025): si alguien mueve la rama master, el trazado no cambia solo
import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

GEO_SHA = '6e6684f3a53f0e2615c3b56306f735590995ef7e'
GEO_URL = f'https://raw.githubusercontent.com/alvaroparedesl/geochile/{GEO_SHA}/geojson/chile.geojson'
ZIP_URL = 'https://www.servel.cl/wp-content/uploads/2025/11/PRELIMINARES_DIPUTADOS.zip'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
CACHE = '/tmp/geochile'
ZIP_CACHE = '/tmp/servel_zip'
SALIDA = _p('elecciones_geografia.json')

ANCHO = 460            # país estrecho: alto real ≈ 5.1× ancho; no se deforma
EPS_PX = 0.9           # umbral de simplificación en píxeles del viewBox
ALTO_MAX = 3200        # techo de seguridad (no llega a aplicar con el ratio real)

# distrito electoral 2025 → región (clave exacta que usa el molde en MAPA_ROWS)
DI2RE = {1: 'Arica y Parinacota', 2: 'Tarapacá', 3: 'Antofagasta', 4: 'Atacama',
         5: 'Coquimbo', 6: 'Valparaíso', 7: 'Valparaíso', 8: 'Metropolitana',
         9: 'Metropolitana', 10: 'Metropolitana', 11: 'Metropolitana', 12: 'Metropolitana',
         13: 'Metropolitana', 14: 'Metropolitana', 15: "O'Higgins", 16: "O'Higgins",
         17: 'Maule', 18: 'Maule', 19: 'Ñuble', 20: 'Biobío', 21: 'Biobío',
         22: 'La Araucanía', 23: 'La Araucanía', 24: 'Los Ríos', 25: 'Los Lagos',
         26: 'Los Lagos', 27: 'Aysén', 28: 'Magallanes'}

# geochile → nómina Servel (diferencias de grafía)
NOMBUSCA = {'paiguano': 'paihuano', 'llaillay': 'llay llay', 'marchihue': 'marchigue',
            'treguaco': 'trehuaco', 'cabo de hornos': 'cabo de hornos(ex navarino)'}


def norm(s):
    s = unicodedata.normalize('NFD', str(s))
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return ' '.join(s.lower().replace("'", ' ').replace('-', ' ').split())


def bajar(url, destino, binario=True):
    if os.path.exists(destino) and os.path.getsize(destino) > 1000:
        return
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
    open(destino, 'wb' if binario else 'w').write(data)
    print(f'  descargado {os.path.basename(destino)}: {len(data)//1024} KB')


def comuna_a_distrito():
    """comuna_normalizada → distrito. Fuentes, en orden: la caché de /tmp, el propio
    elecciones_geografia.json ya horneado (así /tmp puede borrarse sin costo), y si
    nada existe, se deriva de los 28 XLSX oficiales."""
    cache = f'{CACHE}/com2di_servel.json'
    if os.path.exists(cache):
        return {k: int(v) for k, v in json.load(open(cache)).items()}, False
    if os.path.exists(SALIDA):
        try:
            cd = json.load(open(SALIDA)).get('comuna_distrito') or {}
            if len(cd) >= 340:  # solo nóminas completas: una hornada parcial no debe envenenar la caché
                print('  nómina recuperada del propio elecciones_geografia.json (sin re-parsear Servel)')
                return {k: int(v) for k, v in cd.items()}, True
        except Exception:
            pass
    ruta = f'{ZIP_CACHE}/diputados.zip'
    if not os.path.exists(ruta) or os.path.getsize(ruta) <= 1000:
        bajar(ZIP_URL, ruta)
    from openpyxl import load_workbook
    z = zipfile.ZipFile(ruta)
    m = {}
    for nom in z.namelist():
        if not nom.endswith('.xlsx'):
            continue
        wb = load_workbook(__import__('io').BytesIO(z.read(nom)), read_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        cabeza = [str(c).strip().lower() if c else '' for c in next(it)]
        ci, di = cabeza.index('comuna'), cabeza.index('distrito')
        for fila in it:
            com, dis = fila[ci], fila[di]
            if not com:
                continue
            mm = _re.search(r'(\d+)', str(dis or ''))
            if mm:
                m.setdefault(norm(com), int(mm.group(1)))
        wb.close()
        print(f'    · {nom}: {len(m)} comunas acumuladas')
    json.dump(m, open(cache, 'w'), ensure_ascii=False)
    return m, False


# --- geometría -------------------------------------------------------------
def dp(puntos, eps):
    """Douglas-Peucker iterativo sobre anillo [(x,y)...] abierto."""
    if len(puntos) < 4:
        return puntos
    keep = [False] * len(puntos)
    keep[0] = keep[-1] = True
    pila = [(0, len(puntos) - 1)]
    e2 = eps * eps
    while pila:
        i, j = pila.pop()
        if j - i < 2:
            continue
        x1, y1 = puntos[i]
        x2, y2 = puntos[j]
        dx, dy = x2 - x1, y2 - y1
        d2 = dx * dx + dy * dy or 1e-12
        mejor, dist = -1, -1.0
        for k in range(i + 1, j):
            px, py = puntos[k]
            t = ((px - x1) * dx + (py - y1) * dy) / d2
            t = max(0.0, min(1.0, t))
            qx, qy = x1 + t * dx, y1 + t * dy
            dk = (px - qx) ** 2 + (py - qy) ** 2
            if dk > dist:
                dist, mejor = dk, k
        if dist > e2:
            keep[mejor] = True
            pila.append((i, mejor))
            pila.append((mejor, j))
    return [p for p, k in zip(puntos, keep) if k]


def _anillo_area(pts):
    a = 0.0
    for i in range(len(pts) - 1):
        a += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
    return abs(a) / 2.0


def _centroido(pts):
    sx = sy = a = 0.0
    for i in range(len(pts) - 1):
        cr = pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
        a += cr
        sx += (pts[i][0] + pts[i + 1][0]) * cr
        sy += (pts[i][1] + pts[i + 1][1]) * cr
    if abs(a) < 1e-9:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    return sx / (3 * a), sy / (3 * a)


def main():
    geo_ruta = f'{CACHE}/chile.geojson'
    bajar(GEO_URL, geo_ruta)
    gj = json.load(open(geo_ruta))
    com2di, desde_geografia = comuna_a_distrito()
    print(f'nómina Servel: {len(com2di)} comunas')

    # 1) proyectar todo (mercator y → arriba), medir bbox cruda
    def proy(lon, lat):
        import math
        x = lon
        y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 180.0 / math.pi
        return x, y

    polig = []
    for ft in gj['features']:
        pr = ft['properties']
        name = str(pr.get('NOM_COM', '')).strip()
        geoms = ft['geometry']['geometries'] if ft['geometry']['type'] == 'GeometryCollection' else [ft['geometry']]
        anillos = []
        for g in geoms:
            if not g or g['type'] not in ('Polygon', 'MultiPolygon'):
                continue
            poligonos = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
            for pol in poligonos:              # pol = lista de anillos de un polígono
                an = [[proy(px, py) for px, py in ring] for ring in pol[:4]]  # máx 4 anillos
                anillos.extend(an)
        if anillos:
            polig.append((name, anillos))

    xs = [p[0] for _, an in polig for a in an for p in a]
    ys = [p[1] for _, an in polig for a in an for p in a]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    esc = ANCHO / (x1 - x0)
    alto = int(round((y1 - y0) * esc))
    if alto > ALTO_MAX:
        esc *= ALTO_MAX / alto
        alto = ALTO_MAX

    # 2) simplificar + cuantizar + paths (latitud máxima queda arriba)
    celdas = []
    sin_di = []
    for name, anillos in polig:
        nk = norm(name)
        if not desde_geografia:
            nk = NOMBUSCA.get(nk, nk)   # las aliases solo aplican contra la grafía del ZIP
        di = com2di.get(nk)
        if di is None:
            sin_di.append(name)
            di = 0
        re_ = DI2RE.get(di, 'Metropolitana') if di else 'Metropolitana'
        parts, mayor = [], (0.0, (0, 0))
        miny = maxy = None
        cuña_antartica = any(p[1] < -84 for an in anillos for p in an)  # lat. cruda: la cuña llega al polo
        for an in anillos:
            pts = [(round((px - x0) * esc), round((y1 - py) * esc)) for px, py in an]
            gx = [p[0] for p in pts]
            gy = [p[1] for p in pts]
            diag = ((max(gx) - min(gx)) ** 2 + (max(gy) - min(gy)) ** 2) ** 0.5
            eps = min(EPS_PX, max(0.02, diag * 0.02))   # comunas diminutas: simplificar menos
            pts = dp(pts, eps)
            if len(pts) < 4:
                pts = dp([(x, y) for x, y in zip((round((px - x0) * esc) for px, py in an),
                                                  (round((y1 - py) * esc) for px, py in an))], 0.01)
            if len(pts) < 4:
                continue
            s = 'M ' + ' L '.join(f'{int(round(x))} {int(round(y))}' for x, y in pts[:-1]) + ' Z'
            parts.append(s)
            ar = _anillo_area(pts)
            ys_ = [q[1] for q in pts]
            miny = min(ys_) if miny is None else min(miny, min(ys_))
            maxy = max(ys_) if maxy is None else max(maxy, max(ys_))
            if ar > mayor[0]:
                mayor = (ar, _centroido(pts))
        if not parts:
            print('    [descartada por simplificación:', name, ']')
            continue
        celda = {'n': name, 'di': di, 're': re_,
                 'p': ' '.join(parts), 'c': [int(mayor[1][0]), int(mayor[1][1])]}
        if cuña_antartica:
            celda['an'] = 1   # reclamación antártica: recortable en el molde (botón 🧊)
        celdas.append(celda)

    alto_corto = max((max(int(v) for v in _re.findall(r'-?\d+', c['p'])[1::2]) for c in celdas if not c.get('an')), default=alto) + 3
    # 3) centros de etiqueta: la comuna de mayor bounding box de cada grupo
    def mejor_centro(clave):
        grupos = {}
        for c in celdas:
            if c['di']:
                grupos.setdefault(c[clave], []).append(c)
        # área ≈ longitud del path (proxy barato): usamos el bbox del anillo mayor
        out = {}
        for k, lista in grupos.items():
            def tam(c):
                nums = [int(v) for v in _re.findall(r'-?\d+', c['p'])]
                return (max(nums[0::2]) - min(nums[0::2])) * (max(nums[1::2]) - min(nums[1::2]))
            elegido = max(lista, key=tam)
            out[str(k)] = elegido['c']
        return out

    comuna_distrito = {norm(c['n']): c['di'] for c in celdas if c['di']}
    out = {
        'fuente': ('Trazado comunal: geochile (alvaroparedesl, geojson/chile.geojson) · '
                   'comuna→distrito 2025: XLSX oficiales preliminares Diputados del Servel · '
                   'Ñuble derivada del D19 · sin polígono: Isla de Pascua, Juan Fernández, Río Verde '
                   '(quedan como chip/nota) · simplificación Douglas-Peucker 0.9px · proyección mercator'),
        'ancho': int(round((x1 - x0) * esc)),
        'alto': alto,
        'alto_corto': int(alto_corto),   # viewBox útil sin el rectángulo antártico
        'celdas': celdas,
        'centros_di': mejor_centro('di'),
        'centros_re': mejor_centro('re'),
        'comuna_distrito': {k: v for k, v in sorted(comuna_distrito.items())},
    }
    json.dump(out, open(SALIDA, 'w'), ensure_ascii=False)
    ok = sum(1 for c in celdas if c['di'])
    print(f'OK {SALIDA}: {ok} comunas · viewBox {out["ancho"]}×{alto} · '
          f'{os.path.getsize(SALIDA)//1024} KB · sin distrito asignado: '
          f'{", ".join(sorted(set(sin_di))) if sin_di else "ninguna"}')


if __name__ == '__main__':
    main()
