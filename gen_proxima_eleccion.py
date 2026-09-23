"""El Poder en Simple — PRÓXIMA ELECCIÓN (genérico, listo para rellenar).

Lee proxima_eleccion.json (configuración editable a mano), descarga los ZIP del
Servel que estén indicados en cada cargo, los agrega por ámbito (región/distrito/
comuna/circunscripción) y escribe proxima_eleccion_resultados.json.

- Cargos SIN 'zip' quedan como "esperando datos": la página muestra el estado.
- Nada persistente: los ZIP se descargan a /tmp y solo queda el snapshot JSON.
- Formato de columnas configurable en el JSON (por si el Servel las renombra).
"""
import zipfile, io, json, re, urllib.request, gzip, datetime, os, sys

import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
CONF = os.environ.get('PROXIMA_CONF', _p('proxima_eleccion.json'))
DEST = os.environ.get('PROXIMA_DEST', _p('proxima_eleccion_resultados.json'))
CACHE = '/tmp/servel_zip_proxima'
os.makedirs(CACHE, exist_ok=True)


def descargar(cid, url):
    ruta = f'{CACHE}/{cid}.zip'
    if os.path.exists(ruta) and os.path.getsize(ruta) > 1000:
        return ruta
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
    open(ruta, 'wb').write(data)
    print(f'  descargado {cid}: {len(data)//1024} KB')
    return ruta


def es_fila_resumen(nombre):
    n = (nombre or '').strip().upper()
    return (n.startswith('TOTAL') or n in ('VOTOS NULOS', 'VOTOS BLANCOS', 'VOTOS EN BLANCO')
            or 'SUFRAGIOS' in n or 'SUMA CALCULADA' in n or n in ('NAN', 'NONE', ''))


def normaliza_col(c):
    c = str(c).strip().lower()
    c = re.sub(r'[áàä]', 'a', c); c = re.sub(r'[éèë]', 'e', c); c = re.sub(r'[íìï]', 'i', c)
    c = re.sub(r'[óòö]', 'o', c); c = re.sub(r'[úùü]', 'u', c)
    return re.sub(r'[^a-z0-9]+', '_', c).strip('_')


def leer_zip(ruta):
    import pandas as pd
    z = zipfile.ZipFile(ruta)
    dfs = []
    for nom in z.namelist():
        if not nom.lower().endswith(('.xlsx', '.xls', '.csv')):
            continue
        raw = z.read(nom)
        if nom.lower().endswith('.csv'):
            df = pd.read_csv(io.BytesIO(raw), sep=None, engine='python')
        else:
            df = pd.read_excel(io.BytesIO(raw), engine='openpyxl')
        df.columns = [normaliza_col(c) for c in df.columns]
        df['_archivo'] = nom
        dfs.append(df)
        print(f'    · {nom}: {len(df)} filas · columnas: {list(df.columns)[:12]}')
    return dfs


def agregar(dfs, cols, ambito):
    """Agrega por ámbito (columna 'ambito') + resumen nacional por pacto."""
    import pandas as pd
    df = pd.concat(dfs, ignore_index=True)
    faltan = [v for v in (cols['candidato'], cols['votos']) if v not in df.columns]
    if faltan:
        raise SystemExit(f'Columnas no encontradas {faltan}. Disponibles: {list(df.columns)}. Ajusta "columnas" en {CONF}.')
    for opc in ('pacto', 'partido', 'electo', 'mesa', 'electores'):
        if cols[opc] not in df.columns:
            df[cols[opc]] = None
    if ambito not in df.columns:
        df[ambito] = 'Nacional'
    df['votos'] = pd.to_numeric(df[cols['votos']], errors='coerce').fillna(0)
    df['nombre'] = df[cols['candidato']].astype(str).str.strip().str.title()
    up = df[cols['candidato']].astype(str).str.upper().str.strip()
    zonas = {}
    for zona, sub in df.groupby(df[ambito].astype(str).str.strip().str.title()):
        nulos = int(sub.loc[up.loc[sub.index] == 'VOTOS NULOS', 'votos'].sum())
        blancos = int(sub.loc[up.loc[sub.index].isin(['VOTOS BLANCOS', 'VOTOS EN BLANCO']), 'votos'].sum())
        cand = sub[~sub[cols['candidato']].map(es_fila_resumen)]
        if cand.empty:
            continue
        mesas = int(cand[cols['mesa']].nunique()) if cand[cols['mesa']].notna().any() else 0
        try:
            electores = int(cand.groupby(cols['mesa'])[cols['electores']].first().sum())
        except Exception:
            electores = 0
        gp = cand.groupby(['nombre', cols['pacto'], cols['partido']], dropna=False).agg(
            votos=('votos', 'sum'), electo=(cols['electo'], 'max')).reset_index().sort_values('votos', ascending=False)
        tv = int(gp['votos'].sum())
        pactos = cand.groupby(cols['pacto'], dropna=False)['votos'].sum().sort_values(ascending=False)
        zonas[zona] = {
            'mesas': mesas, 'electores': electores, 'total_validos': tv, 'nulos': nulos, 'blancos': blancos,
            'pactos': [{'pacto': str(p), 'votos': int(v), 'pct': round(v/tv*100, 2) if tv else 0} for p, v in pactos.items()],
            'electos': [r['nombre'] for _, r in gp.iterrows() if r['electo'] == 1],
            'candidatos': [{'nombre': r['nombre'], 'pacto': str(r[cols['pacto']]), 'partido': str(r[cols['partido']]),
                            'votos': int(r['votos']), 'pct': round(r['votos']/tv*100, 2) if tv else 0,
                            'electo': bool(r['electo'] == 1)} for _, r in gp.head(12).iterrows()],
        }
    cand = df[~df[cols['candidato']].map(es_fila_resumen)]
    tv = int(cand['votos'].sum())
    gp = cand.groupby(cols['pacto'], dropna=False)['votos'].sum().sort_values(ascending=False)
    esc = cand[cand[cols['electo']] == 1].groupby(cols['pacto'])['nombre'].nunique()
    resumen = [{'pacto': str(p), 'votos': int(v), 'pct': round(v/tv*100, 2) if tv else 0,
                'escanos': int(esc.get(p, 0))} for p, v in gp.items()]
    def _k(z):
        m = re.search(r'(\d+)', z); return (0, int(m.group(1)), z) if m else (1, 0, z)
    return {'zonas': dict(sorted(zonas.items(), key=lambda kv: _k(kv[0]))), 'resumen_nacional': resumen, 'total_validos': tv,
            'mesas': int(cand[cols['mesa']].nunique()) if cand[cols['mesa']].notna().any() else 0}


def main():
    conf = json.load(open(CONF, encoding='utf-8'))
    out = {k: conf[k] for k in ('nombre', 'fecha', 'estado', 'descripcion', 'pagina_servel') if k in conf}
    out['segunda_vuelta_fecha'] = conf.get('segunda_vuelta_fecha')
    out['generado'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    out['cargos'] = []
    for c in conf['cargos']:
        item = {k: c.get(k) for k in ('id', 'nombre', 'emoji', 'ambito', 'ambito_nombre', 'explica')}
        item['zip'] = c.get('zip') or ''
        if not item['zip']:
            item['estado'] = 'esperando'
            print(f'· {c["nombre"]}: sin ZIP todavía (esperando datos del Servel)')
        else:
            try:
                print(f'· {c["nombre"]}: descargando…')
                item['datos'] = agregar(leer_zip(descargar(c['id'], c['zip'])), conf['columnas'], c['ambito'])
                item['estado'] = 'con_datos'
                print(f'  OK {len(item["datos"]["zonas"])} {c["ambito_nombre"]}(es) · {item["datos"]["total_validos"]:,} votos válidos')
            except Exception as e:
                item['estado'] = 'error'; item['error'] = str(e)[:300]
                print(f'  ERROR: {e}')
        out['cargos'].append(item)
    json.dump(out, open(DEST, 'w', encoding='utf-8'), ensure_ascii=False)
    print('OK', DEST)


if __name__ == '__main__':
    main()
