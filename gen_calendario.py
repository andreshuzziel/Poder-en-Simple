#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera calendario_votaciones.json: todas las votaciones de 2026 con el
voto nominal de cada diputad@ (a favor S / en contra N / abstención A; el resto =
ausente) + la ficha oficial de cada proyecto (qué dice, quién lo presentó, enlace
al Congreso). Sin base de datos: JSON en disco.

Fuentes (Mirada al Congreso sobre datos abiertos oficiales de la Cámara):
  · api/votacionesxano     → todas las votaciones del año
  · api/votacionesDetalle  → voto de cada diputad@ en una votación (param=id)
  · api/votaciones         → ficha del proyecto por boletín: nombre, Id interno de
                             camara.cl, iniciativa (moción/mensaje), autores, fecha
                             de ingreso y qué se votó en cada trámite (materias,
                             artículo, trámite constitucional/reglamentario, quórum)
"""
import json
import explicador, time, datetime, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

NS = {'c': 'http://opendata.camara.cl/camaradiputados/v1'}
UA = {'Content-Type': 'application/json',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126 Safari/537.36'}
SALIDA = '/home/user/calendario_votaciones.json'
ANIO = 2026


def post(url, payload, timeout=30, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=UA)
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception as e:
            last = e
            time.sleep(1 + i)
    raise last


def votaciones_anio():
    raw = post('https://www.miradaalcongreso.com/api/votacionesxano', {'param': ANIO}, timeout=60)
    root = ET.fromstring(raw)
    filas = []
    for v in root.findall('c:Votacion', NS):
        def g(t):
            e = v.find('c:' + t, NS)
            return (e.text or '').strip() if e is not None else ''
        filas.append({'id': g('Id'), 'desc': g('Descripcion'), 'fecha': g('Fecha'),
                      'resultado': g('Resultado'), 'tipo': g('Tipo'),
                      'si': int(g('TotalSi') or 0), 'no': int(g('TotalNo') or 0),
                      'abst': int(g('TotalAbstencion') or 0)})
    return filas


def detalle_nominal(v):
    """Devuelve (id, {'S':[ids],'N':[ids],'A':[ids]}) o (id, None)."""
    try:
        raw = post('https://www.miradaalcongreso.com/api/votacionesDetalle', {'param': int(v['id'])})
        root = ET.fromstring(raw)
        nv = root.find('c:Votos', NS)
        OP = {'1': 'S', '0': 'N', '2': 'A'}
        out = {'S': [], 'N': [], 'A': []}
        if nv is not None:
            for vo in nv.findall('c:Voto', NS):
                op = OP.get(vo.find('c:OpcionVoto', NS).attrib.get('Valor'))
                idc = vo.find('c:Diputado', NS).find('c:Id', NS).text
                if op and idc:
                    out[op].append(str(idc))
        return v['id'], out
    except Exception as e:
        print(f'    [fallo detalle {v["id"]}: {e}]', flush=True)
        return v['id'], None


def info_proyecto(bol):
    """Ficha oficial del boletín: nombre, Id camara.cl, iniciativa, autores,
    ingreso, y qué se votó en cada votación del proyecto (por fecha)."""
    try:
        r = post('https://www.miradaalcongreso.com/api/votaciones', {'param': bol}, timeout=25, tries=2)
        root = ET.fromstring(r)

        def txt(tag):
            e = root.find('c:' + tag, NS)
            return (e.text or '').strip() if e is not None else ''

        ti = root.find('c:TipoIniciativa', NS)
        autores = []
        for pa in root.findall('c:Autores/c:ParlamentarioAutor', NS):
            d = pa.find('c:Diputado', NS)
            if d is not None:
                partes = [d.find('c:Nombre', NS), d.find('c:ApellidoPaterno', NS), d.find('c:ApellidoMaterno', NS)]
                nom = ' '.join((x.text or '').strip() for x in partes if x is not None and x.text).strip()
                if nom:
                    autores.append(nom)
        vot = {}
        for vp in root.findall('c:Votaciones/c:VotacionProyectoLey', NS):
            def g2(t):
                e = vp.find('c:' + t, NS)
                return (e.text or '').strip() if e is not None else ''
            partes = [g2('Materias'), g2('TramiteConstitucional'), g2('TramiteReglamentario'), g2('Articulo')]
            que = ' · '.join(p for p in partes if p)          # texto COMPLETO de la observación oficial (sin recortar)
            vot[g2('Fecha')[:16]] = {'que': que or None, 'quorum': g2('Quorum') or None,
                                     'obs': {'materias': g2('Materias') or None, 'tramite': g2('TramiteConstitucional') or None,
                                             'informe': g2('TramiteReglamentario') or None, 'articulo': g2('Articulo') or None}}
        return {'n': txt('Nombre') or None, 'cid': txt('Id') or None,
                'ini': (ti.text or '').strip() if ti is not None else '',
                'aut': autores[:15], 'ing': txt('FechaIngreso')[:10] or None,
                'origen': txt('CamaraOrigen') or None, 'vot': vot}
    except Exception as e:
        print(f'    [fallo ficha {bol}: {e}]', flush=True)
        return None


def main():
    print('1/4 votaciones del año…', flush=True)
    filas = votaciones_anio()
    print(f'  {len(filas)} votaciones', flush=True)
    leys = [f for f in filas if f['tipo'] == 'Proyecto de Ley' and f['desc'].startswith('Boletín')]
    print(f'2/4 votos nominales de {len(leys)} votaciones de ley…', flush=True)
    nominales, ok = {}, 0
    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(detalle_nominal, v): v for v in leys}
        for fut in as_completed(futs):
            vid, votos = fut.result()
            nominales[vid] = votos
            ok += votos is not None
            if ok % 100 == 0:
                print(f'  …{ok}/{len(leys)}', flush=True)
    print(f'  nominales OK: {ok}/{len(leys)}', flush=True)
    print('3/4 fichas oficiales de los proyectos…', flush=True)
    bols = sorted({f['desc'].replace('Boletín N° ', '') for f in filas if f['desc'].startswith('Boletín')})
    proyectos = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(info_proyecto, b): b for b in bols}
        for fut in as_completed(futs):
            b = futs[fut]
            try:
                proyectos[b] = fut.result()
            except Exception:
                proyectos[b] = None
    con_ficha = sum(1 for p in proyectos.values() if p and p.get('n'))
    print(f'  con ficha oficial: {con_ficha}/{len(bols)}', flush=True)
    out = {'fuente': {'organismo': 'Cámara de Diputadas y Diputados (datos abiertos oficiales, vía Mirada al Congreso)',
                      'anio': ANIO,
                      'descargado': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
                      'enlace_base': 'https://www.camara.cl/legislacion/proyectosdeley/tramitacion.aspx?prmID=',
                      'nota': 'S = a favor · N = en contra · A = abstención; l@s demás diputad@s en ejercicio no votaron (ausencia/pareo)'},
           'votaciones': [], 'proyectos': {}}
    for b, p in proyectos.items():
        if p and p.get('n'):
            out['proyectos'][b] = {k: p[k] for k in ('n', 'cid', 'ini', 'aut', 'ing', 'origen') if p.get(k)}
    for f in filas:
        bol = f['desc'].replace('Boletín N° ', '') if f['desc'].startswith('Boletín') else None
        p = proyectos.get(bol) or {}
        vm = (p.get('vot') or {}).get(f['fecha'][:16]) or {}
        out['votaciones'].append({
            'id': f['id'], 'fecha': f['fecha'][:10], 'tipo': f['tipo'],
            'resultado': f['resultado'], 'desc': f['desc'],
            'boletin': bol, 'titulo': p.get('n'),
            'si': f['si'], 'no': f['no'], 'abst': f['abst'],
            'nominal': nominales.get(f['id']),
            'que': vm.get('que'), 'quorum': vm.get('quorum'), 'obs': vm.get('obs'),
            'exp': explicador.explicar_votacion((vm.get('obs') or {}).get('articulo'), (vm.get('obs') or {}).get('tramite'),
                                                (vm.get('obs') or {}).get('informe'), vm.get('quorum'), f['resultado'],
                                                f['si'], f['no'], f['abst'], f['tipo'], p.get('n'))})
        out['votaciones'][-1]['exp'].pop('texto', None)   # 'texto' repite los otros campos: no se guarda
    json.dump(out, open(SALIDA, 'w'), ensure_ascii=False)
    print(f'OK {SALIDA} · {len(out["votaciones"])} votaciones · '
          f'{sum(1 for v in out["votaciones"] if v["nominal"])} con voto nominal · '
          f'{len(out["proyectos"])} proyectos con ficha y enlace oficial', flush=True)


if __name__ == '__main__':
    main()
