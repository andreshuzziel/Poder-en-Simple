#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fusiona la SEGUNDA VUELTA presidencial (balotaje 14-D-2025) en el snapshot
elecciones_resultados.json — sin tocar ninguna otra clave ni conexión.

Descarga (con caché en /tmp/servel_zip, como gen_elecciones.py) el ZIP oficial
https://www.servel.cl/wp-content/uploads/2025/12/Datos_SegundaVotacion.zip, que trae
dos XLSX con las actas mesa a mesa: En_Chile y En_Extranjero (mismo esquema de columnas
que la 1ª vuelta presidencial). Agrega: total país, por región (16, con Ñuble) y por
país en el extranjero, incluidos nulos/blancos/participación/mesas, y escribe la clave
DATA['segunda_vuelta'] que consume el molde. Sin base de datos: JSON en disco nada más.
"""
import datetime
import gzip
import io
import json
import os
import urllib.request
import zipfile

import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36'
URL = 'https://www.servel.cl/wp-content/uploads/2025/12/Datos_SegundaVotacion.zip'
CACHE = '/tmp/servel_zip'
SNAP = _p('elecciones_resultados.json')

RE_KEY = {  # región del ZIP (sin tildes ni prefijos) → clave del molde
    'arica y parinacota': 'Arica y Parinacota',
    'tarapaca': 'Tarapacá',
    'antofagasta': 'Antofagasta',
    'atacama': 'Atacama',
    'coquimbo': 'Coquimbo',
    'valparaiso': 'Valparaíso',
    'metropolitana de santiago': 'Metropolitana',
    'metropolitana': 'Metropolitana',
    'libertador general bernardo o\'higgins': "O'Higgins",
    "o'higgins": "O'Higgins",
    'maule': 'Maule',
    'nuble': 'Ñuble',
    'biobio': 'Biobío',
    'la araucania': 'La Araucanía',
    'los rios': 'Los Ríos',
    'los lagos': 'Los Lagos',
    'aysen del general carlos ibanez del campo': 'Aysén',
    'aysen': 'Aysén',
    'magallanes y de la antartica chilena': 'Magallanes',
    'magallanes': 'Magallanes',
}


def sin_tildes(s):
    import unicodedata
    s = unicodedata.normalize('NFD', str(s))
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def clave_region(txt):
    t = sin_tildes(str(txt)).strip().upper()
    if t.startswith('DEL '):
        t = t[4:]
    elif t.startswith('DE '):
        t = t[3:]
    if t.startswith('METROPOLITANA'):
        t = 'METROPOLITANA DE SANTIAGO'
    k = RE_KEY.get(t.lower())
    if not k:
        raise SystemExit(f'[gen_2v] región desconocida en el ZIP: {txt!r}')
    return k


def descargar():
    ruta = f'{CACHE}/segunda.zip'
    if os.path.exists(ruta) and os.path.getsize(ruta) > 1000:
        return ruta
    os.makedirs(CACHE, exist_ok=True)
    req = urllib.request.Request(URL, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=300) as r:
        data = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            data = gzip.GzipFile(fileobj=io.BytesIO(data)).read()
    open(ruta, 'wb').write(data)
    print(f'  descargado 2ª vuelta: {len(data)//1024} KB')
    return ruta


def resumen_bloque(cand, df_completo, col_mesas='cod_mesa', col_electores='electores'):
    """cand: filas de candidatos (sin nulos/blancos). df_completo: incluye filas de resumen."""
    import pandas as pd
    total_validos = int(cand['votos'].sum())
    nulos = int(df_completo.loc[df_completo['nomb'] == 'VOTOS NULOS', 'votos'].sum())
    blancos = int(df_completo.loc[df_completo['nomb'].isin(['VOTOS BLANCOS', 'VOTOS EN BLANCO']), 'votos'].sum())
    mesas = int(cand[col_mesas].nunique())
    electores = int(cand.groupby(col_mesas)[col_electores].first().sum())
    gp = cand.groupby('nombre')['votos'].sum().sort_values(ascending=False)
    candidatos = [{'nombre': n, 'votos': int(v), 'pct': round(v / total_validos * 100, 2) if total_validos else 0}
                  for n, v in gp.items()]
    return {'mesas': mesas, 'electores': electores, 'total_validos': total_validos,
            'nulos': nulos, 'blancos': blancos, 'candidatos': candidatos}


def main():
    import pandas as pd
    z = zipfile.ZipFile(descargar())
    bloques = {}
    for nom in z.namelist():
        if not nom.endswith('.xlsx'):
            continue
        df = pd.read_excel(io.BytesIO(z.read(nom)))
        colv = 'votos_preliminares' if 'votos_preliminares' in df.columns else 'votos'
        colm = 'electores' if 'electores' in df.columns else 'electores_mesa'
        df['votos'] = pd.to_numeric(df[colv], errors='coerce').fillna(0)
        df['nomb'] = df['nombre_candidato'].astype(str).str.strip().str.upper()
        df['nombre'] = df['nombre_candidato'].astype(str).str.strip().str.title()
        cand = df[~df['nomb'].str.startswith(('TOTAL', 'VOTOS')) & ~df['nomb'].str.contains('SUFRAGIOS')].copy()
        tipo = 'extranjero' if 'extranjero' in nom.lower() else 'chile'
        bloques[tipo] = (cand, df, colm)

    cand, df, colm = bloques['chile']
    chile = resumen_bloque(cand, df, col_electores=colm)
    por_region = {}
    for reg, sub in cand.groupby('region'):
        pas = df[df['region'] == reg]
        r = resumen_bloque(sub, pas, col_electores=colm)
        r['ganador'] = r['candidatos'][0]['nombre'] if r['candidatos'] else None
        por_region[clave_region(reg)] = r
    chile['por_region'] = por_region

    cand_e, df_e, colm_e = bloques['extranjero']
    extr = resumen_bloque(cand_e, df_e, col_electores=colm_e)
    top = {}
    for pais, sub in cand_e.groupby('pais'):
        m = int(sub['votos'].sum())
        gp = sub.groupby('nombre')['votos'].sum().sort_values(ascending=False)
        top[str(pais).title()] = {'votos': m, 'candidatos': [
            {'nombre': n, 'votos': int(v), 'pct': round(v / m * 100, 2) if m else 0} for n, v in gp.items()]}
    extr['top_paises'] = dict(sorted(top.items(), key=lambda kv: -kv[1]['votos']))

    # totales del país = chile + extranjero (nulo/blanco extranjero también cuentan)
    for k in ('mesas', 'electores', 'total_validos', 'nulos', 'blancos'):
        chile[k] = chile[k] + extr[k]
    gp = pd.concat([cand, cand_e]).groupby('nombre')['votos'].sum().sort_values(ascending=False)
    tv = int(gp.sum())
    generales = [{'nombre': n, 'votos': int(v), 'pct': round(v / tv * 100, 2)} for n, v in gp.items()]

    sv = {'fuente': {'archivo': URL, 'organismo': 'Servel',
                     'tipo': 'Resultados preliminares Segunda Votación Presidencial 14-D-2025',
                     'descargado': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')},
          'mesas': chile['mesas'], 'electores': chile['electores'], 'total_validos': tv,
          'nulos': chile['nulos'], 'blancos': chile['blancos'],
          'candidatos': generales, 'chile': chile, 'extranjero': extr}

    data = json.load(open(SNAP))
    # padrón nacional: la suma mesa a mesa del ZIP viene parcial (mesas anuladas /
    # datos a medio cargar); la referencia del balotaje es el padrón oficial 2025.
    # Las cifras POR REGIÓN siguen con su padrón de mesas (mismo criterio que 1ª vuelta).
    sv['electores'] = 17766436
    data['segunda_vuelta'] = sv
    json.dump(data, open(SNAP, 'w'), ensure_ascii=False)
    print(f'OK {SNAP} · segunda_vuelta fusionada')
    for c in generales:
        print(f'   {c["nombre"]}: {c["votos"]:,} ({c["pct"]:.2f}%)')
    print(f'   mesas {chile["mesas"]:,} · electores {chile["electores"]:,} · nulos {chile["nulos"]:,} · blancos {chile["blancos"]:,}')
    print(f'   regiones: {len(por_region)} · extranjero votos válidos: {extr["total_validos"]:,}')


if __name__ == '__main__':
    main()
