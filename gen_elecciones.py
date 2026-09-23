#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera elecciones_resultados.json a partir de los ZIP oficiales de resultados
preliminares del Servel (Elecciones 2025: Presidente, Diputados y Senadores).
Los ZIP se descargan de servel.cl; nada se guarda más allá del snapshot JSON.

NOTA (versión completa): al escribir el snapshot CONSERVA las claves que este
script no genera (ej. `segunda_vuelta`, `presidencial.por_distrito`), para que
re-ejecutarlo nunca borre lo agregado por gen_segunda_vuelta.py /
gen_presidencia_distritos.py."""
import zipfile, io, json, re, urllib.request, gzip, datetime, os

import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
BASE = 'https://www.servel.cl/wp-content/uploads/2025/11/'
ARCHIVOS = {
    'presidencial': BASE + 'PRELIMINARES_PRESIDENTE_DE_LA_REPUBLICA.zip',
    'diputados': BASE + 'PRELIMINARES_DIPUTADOS.zip',
    'senadores': BASE + 'PRELIMINARES_SENADORES_CIRCUNSCRIPCION.zip',
}
PAGINA_FUENTE = 'https://www.servel.cl/resultados-preliminares-eleccion-presidencial-y-parlamentarias-2025/'
CACHE = '/tmp/servel_zip'
os.makedirs(CACHE, exist_ok=True)

COLS = ['region', 'circunscripcion_senatorial', 'distrito', 'comuna', 'pacto', 'partido',
        'nombre_candidato', 'votos_preliminares', 'electo_nominado', 'cod_mesa', 'electores']

def descargar(clave):
    ruta = f'{CACHE}/{clave}.zip'
    if os.path.exists(ruta) and os.path.getsize(ruta) > 1000:
        return ruta
    url = ARCHIVOS[clave]
    data = None
    for intento in range(4):  # descargas grandes del Servel a veces se cortan (IncompleteRead)
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=600) as r:
                data = r.read()
            zipfile.ZipFile(io.BytesIO(data)).testzip()
            break
        except Exception as e:
            print(f'  intento {intento+1} falló ({type(e).__name__}); reintentando…')
            data = None
    if data is None:
        raise SystemExit(f'No se pudo descargar {url}')
    open(ruta, 'wb').write(data)
    print(f'  descargado {clave}: {len(data)//1024} KB')
    return ruta

def es_fila_resumen(nombre):
    n = (nombre or '').strip().upper()
    return (n.startswith('TOTAL') or n in ('VOTOS NULOS', 'VOTOS BLANCOS', 'VOTOS EN BLANCO')
            or 'SUFRAGIOS' in n or 'SUMA CALCULADA' in n)

def leer_zip(ruta):
    import pandas as pd
    z = zipfile.ZipFile(ruta)
    dfs = []
    for nom in z.namelist():
        df = pd.read_excel(io.BytesIO(z.read(nom)), engine='openpyxl')
        for c in COLS:
            if c not in df.columns:
                df[c] = None
        df = df[COLS]
        df['_archivo'] = nom
        dfs.append(df)
        print(f'    · {nom}: {len(df)} filas')
    return dfs

def num_distrito(txt):
    m = re.search(r'(\d+)', str(txt))
    return int(m.group(1)) if m else None

def agregar_parlamentaria(dfs, campo):
    """Agrega resultados por distrito/circunscripción + resumen nacional por pacto."""
    import pandas as pd
    distritos = {}
    todos = []
    for df in dfs:
        df = df.copy()
        df['votos'] = pd.to_numeric(df['votos_preliminares'], errors='coerce').fillna(0)
        df['nombre'] = df['nombre_candidato'].astype(str).str.strip().str.title()
        nulos = int(df.loc[df['nombre_candidato'].astype(str).str.upper().str.strip() == 'VOTOS NULOS', 'votos'].sum())
        blancos = int(df.loc[df['nombre_candidato'].astype(str).str.upper().str.strip().isin(['VOTOS BLANCOS', 'VOTOS EN BLANCO']), 'votos'].sum())
        cand = df[~df['nombre_candidato'].map(es_fila_resumen)].copy()
        mesas = int(cand['cod_mesa'].nunique())
        electores = int(cand.groupby('cod_mesa')['electores'].first().sum())
        gp = cand.groupby(['nombre', 'pacto', 'partido'], dropna=False).agg(
            votos=('votos', 'sum'), electo=('electo_nominado', 'max'))
        gp = gp.reset_index().sort_values('votos', ascending=False)
        total_validos = int(gp['votos'].sum())
        pactos = cand.groupby('pacto')['votos'].sum().sort_values(ascending=False)
        electos = [r['nombre'] for _, r in gp.iterrows() if r['electo'] == 1]
        key = num_distrito(cand[campo].iloc[0])
        distritos[key] = {
            'mesas': mesas, 'electores': electores, 'total_validos': total_validos,
            'nulos': nulos, 'blancos': blancos,
            'pactos': [{'pacto': str(p), 'votos': int(v),
                        'pct': round(v/total_validos*100, 2) if total_validos else 0} for p, v in pactos.items()],
            'electos': electos,
            'candidatos': [{'nombre': r['nombre'], 'pacto': str(r['pacto']), 'partido': str(r['partido']),
                            'votos': int(r['votos']),
                            'pct': round(r['votos']/total_validos*100, 2) if total_validos else 0,
                            'electo': bool(r['electo'] == 1)} for _, r in gp.iterrows()],
        }
        todos.append(cand)
    todo = pd.concat(todos, ignore_index=True)
    gp = todo.groupby('pacto').agg(votos=('votos', 'sum'),
                                   escaños=('electo_nominado', lambda s: int((s == 1).sum() and todo.loc[s[s == 1].index, 'nombre'].nunique())))
    # escaños reales: candidatos únicos electos por pacto
    elect = todo[todo['electo_nominado'] == 1]
    esc = elect.groupby('pacto')['nombre'].nunique()
    total_validos = int(todo['votos'].sum())
    resumen = [{'pacto': str(p), 'votos': int(gp.loc[p, 'votos']),
                'pct': round(int(gp.loc[p, 'votos'])/total_validos*100, 2),
                'escanos': int(esc.get(p, 0))} for p in gp.sort_values('votos', ascending=False).index]
    return {'distritos': {str(k): v for k, v in sorted(distritos.items())},
            'resumen_nacional': resumen, 'total_validos': total_validos}

def agregar_presidencial(dfs):
    import pandas as pd
    df = pd.concat(dfs, ignore_index=True)
    df['votos'] = pd.to_numeric(df['votos_preliminares'], errors='coerce').fillna(0)
    df['nombre'] = df['nombre_candidato'].astype(str).str.strip().str.title()
    nulos = int(df.loc[df['nombre_candidato'].astype(str).str.upper().str.strip() == 'VOTOS NULOS', 'votos'].sum())
    blancos = int(df.loc[df['nombre_candidato'].astype(str).str.upper().str.strip().isin(['VOTOS BLANCOS', 'VOTOS EN BLANCO']), 'votos'].sum())
    cand = df[~df['nombre_candidato'].map(es_fila_resumen)]
    mesas = int(cand['cod_mesa'].nunique())
    electores = int(cand.groupby('cod_mesa')['electores'].first().sum())
    gp = cand.groupby(['nombre', 'partido', 'pacto'], dropna=False)['votos'].sum().reset_index()
    gp = gp.sort_values('votos', ascending=False)
    total_validos = int(gp['votos'].sum())
    # desglose Chile / extranjero por archivo
    por = {}
    for f in cand['_archivo'].unique():
        sub = cand[cand['_archivo'] == f].groupby('nombre')['votos'].sum()
        por['extranjero' if 'extranjero' in f.lower() else 'chile'] = {k: int(v) for k, v in sub.items()}
    return {'mesas': mesas, 'electores': electores, 'total_validos': total_validos,
            'nulos': nulos, 'blancos': blancos,
            'candidatos': [{'nombre': r['nombre'], 'partido': str(r['partido']), 'pacto': str(r['pacto']),
                            'votos': int(r['votos']),
                            'pct': round(r['votos']/total_validos*100, 2)} for _, r in gp.iterrows()],
            'desglose': por}

def conservar_claves_extra(out, destino):
    """Si el snapshot existente tiene claves/subclaves que este script no genera
    (ej. segunda_vuelta, presidencial.por_distrito), se conservan tal cual."""
    try:
        anterior = json.load(open(destino, encoding='utf-8'))
    except Exception:
        return
    if not isinstance(anterior, dict):
        return
    for k, v in anterior.items():
        if k not in out:
            out[k] = v
            print(f'  → clave existente conservada: {k}')
    prev_pres = anterior.get('presidencial') or {}
    for k, v in prev_pres.items():
        if k not in out['presidencial']:
            out['presidencial'][k] = v
            print(f'  → presidencial.{k} conservada')

def main():
    import pandas as pd  # noqa
    destino = _p('elecciones_resultados.json')
    out = {'fuente': {'organismo': 'Servicio Electoral de Chile (Servel)',
                      'tipo': 'Resultados preliminares (con actas de mesa) · Elecciones del 16 de noviembre de 2025',
                      'pagina': PAGINA_FUENTE,
                      'archivos': ARCHIVOS,
                      'descargado': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')},
           'eleccion': 'presidencial_y_parlamentarias_2025'}
    print('1/3 Presidencial…')
    out['presidencial'] = agregar_presidencial(leer_zip(descargar('presidencial')))
    print('2/3 Diputados…')
    out['diputados'] = agregar_parlamentaria(leer_zip(descargar('diputados')), 'distrito')
    print('3/3 Senadores…')
    out['senadores'] = agregar_parlamentaria(leer_zip(descargar('senadores')), 'circunscripcion_senatorial')
    conservar_claves_extra(out, destino)
    json.dump(out, open(destino, 'w'), ensure_ascii=False)
    print('OK elecciones_resultados.json')
    print('presidencial candidatos:', [(c['nombre'], c['votos'], c['pct']) for c in out['presidencial']['candidatos']])

if __name__ == '__main__':
    main()
