#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
actualizar_datos.py — Refresca los datos de la VERSIÓN PUBLICADA (estática) desde las fuentes oficiales.

La página publicada en Netlify no tiene servidor Python, así que no puede descargar en vivo: lo que ve el
público es lo que quedó incrustado en los HTML al generarlos. Este script trae los datos frescos usando
exactamente las mismas funciones del modo en vivo (servidor.py) y los deja en los archivos JSON que leen
los generadores. Después, `bash publicar.sh` regenera las páginas y las sube al repositorio; Netlify
publica el commit automáticamente.

Principios:
  · Sin base de datos: los JSON son solo el "molde" de la página publicada, no un histórico.
  · Cada fuente es independiente: si una falla, se conserva el archivo anterior y se avisa. Nunca se deja
    la página rota por una fuente caída.
  · Todo se puede ejecutar a mano (python3 actualizar_datos.py) o programado (GitHub Actions, .github/workflows).

Salida: actualizacion_estado.json con qué se actualizó, qué falló y cuándo (lo lee el generador para
mostrar "datos al día ..." en la página).
"""
import json, os, sys, time, traceback
from datetime import datetime, date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import servidor as S


def _p(n):
    return os.path.join(BASE_DIR, n)


def guardar(nombre, datos, minimo=1):
    """Escribe el JSON solo si el dato nuevo es razonable (no vacío); si no, conserva el anterior."""
    if datos is None or (hasattr(datos, '__len__') and len(datos) < minimo):
        raise ValueError(f'dato vacío o insuficiente para {nombre}')
    tmp = _p(nombre + '.tmp')
    json.dump(datos, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False)
    os.replace(tmp, _p(nombre))
    return os.path.getsize(_p(nombre))


def paso(nombre, fn, estado):
    t0 = time.time()
    try:
        r = fn()
        estado['ok'][nombre] = {'detalle': r, 'seg': round(time.time() - t0, 1)}
        print(f'  ✔ {nombre}: {r} ({time.time()-t0:.1f}s)', flush=True)
    except Exception as e:
        estado['fallos'][nombre] = f'{type(e).__name__}: {str(e)[:160]}'
        print(f'  ✘ {nombre}: {type(e).__name__}: {str(e)[:120]} — se conserva el archivo anterior', flush=True)
        if os.environ.get('DEBUG'):
            traceback.print_exc()


# ------------------------------------------------------------------ fuentes
def act_todo():
    """Descarga el mismo paquete que ve el modo en vivo (servidor.armar_todo) y lo reparte en los JSON
    que leen los generadores. Si el paquete completo falla, no se toca ningún archivo."""
    todo = S.armar_todo(fresh=True)
    res = {}
    # 1) congreso_data.json: kpi + bancadas + diputados (asistencia y gastos)
    if len(todo.get('diputados') or []) >= 100:
        # Mantener el esquema histórico que leen los generadores (asist_prom, g_prom, bancada, coalicion)
        try:
            prev = json.load(open(_p('congreso_data.json')))
            extra = {d['id']: d for d in prev.get('diputados', [])}
        except Exception:
            extra = {}
        for d in todo['diputados']:
            e = extra.get(d['id'], {})
            d.setdefault('bancada', e.get('bancada', d.get('grupo')))
            d.setdefault('coalicion', e.get('coalicion', ''))
        for b in todo['bancadas']:
            for k, k2 in (('asist', 'asist_prom'), ('asist_ef', 'asist_ef_prom'), ('inas', 'inas_prom'), ('inas_ef', 'inas_ef_prom'),
                          ('g_tot', 'g_prom'), ('g_per', 'g_per_prom'), ('g_op', 'g_op_prom')):
                if k in b and k2 not in b:
                    b[k2] = b[k]
            if 'g_prom' in b and 'n' in b:
                b['g_tot'] = round(b['g_prom'] * b['n'])
        guardar('congreso_data.json', {'kpi': todo['kpi'], 'bancadas': todo['bancadas'], 'diputados': todo['diputados']})
        res['diputados'] = len(todo['diputados'])
    # 2) data_completa.json: snapshot completo (votaciones, senado, mesas, gobierno, etc.)
    snap = json.load(open(_p('data_completa.json')))
    for k in ('kpi', 'bancadas', 'diputados', 'votaciones', 'destacadas', 'desglose_op', 'senado', 'mesas',
              'proyectos_periodos', 'votos_leyes', 'gastos_hist', 'noticias', 'meta'):
        v = todo.get(k)
        if v not in (None, [], {}):
            snap[k] = v
    if todo.get('gobierno'):
        snap['gobierno'] = todo['gobierno']
    guardar('data_completa.json', snap)
    # 3) archivos individuales que usan los generadores
    if todo.get('gobierno') and len(todo['gobierno'].get('gabinete') or []) >= 10:
        guardar('gobierno_snapshot.json', todo['gobierno']); res['ministerios'] = len(todo['gobierno']['gabinete'])
    if todo.get('votos_leyes'):
        guardar('votos_leyes.json', todo['votos_leyes']); res['votos_leyes'] = len(todo['votos_leyes'])
    if todo.get('gastos_hist'):
        guardar('gastos_hist.json', todo['gastos_hist']); res['gastos_hist'] = len(todo['gastos_hist'])
    if todo.get('noticias') and any(todo['noticias'].values()):
        guardar('noticias.json', todo['noticias']); res['noticias'] = sum(len(v) for v in todo['noticias'].values())
    dest = [{'id': int(d.get('id', 0) or 0), 'titulo': d.get('titulo', ''), 'ref': d.get('ref', ''), 'resultado': d.get('resultado', ''),
             'totales': d['totales'], 'por_bancada': d['por_bancada']} for d in (todo.get('destacadas') or []) if d.get('por_bancada') and d.get('totales')]
    if dest:
        guardar('votaciones_destacadas.json', dest); res['destacadas'] = len(dest)
    vot = todo.get('votaciones') or {}
    if vot.get('proyectos'):
        nombres = json.load(open(_p('boletines_nombres.json'))) if os.path.exists(_p('boletines_nombres.json')) else {}
        for p in vot['proyectos']:
            if p.get('boletin') and p.get('nombre'):
                nombres[p['boletin']] = p['nombre']
        guardar('boletines_nombres.json', nombres)
    return res


def act_votaciones_filas():
    """Filas crudas de todas las votaciones del año → votaciones_<año>.json (tarjetas de proyectos y períodos)."""
    import xml.etree.ElementTree as ET
    anio = date.today().year
    raw = S.http_post_json('https://www.miradaalcongreso.com/api/votacionesxano', {'param': anio})
    root = ET.fromstring(raw)
    filas = []
    for v in root.findall('c:Votacion', S.NS):
        def g(t):
            e = v.find('c:' + t, S.NS); return (e.text or '').strip() if e is not None else ''
        filas.append({'id': g('Id'), 'desc': g('Descripcion'), 'fecha': g('Fecha'), 'si': int(g('TotalSi') or 0),
                      'no': int(g('TotalNo') or 0), 'abst': int(g('TotalAbstencion') or 0), 'resultado': g('Resultado'), 'tipo': g('Tipo')})
    if len(filas) < 50:
        raise ValueError(f'solo {len(filas)} votaciones')
    guardar(f'votaciones_{anio}.json', filas)
    return f"{len(filas)} votaciones · última {max(f['fecha'] for f in filas)[:10]}"


def act_leyes():
    l = S.src_leyes_promulgadas()
    guardar('leyes_promulgadas.json', l, minimo=5)
    return f'{len(l)} leyes'


def main(solo=None):
    print(f'== Actualización de datos · {datetime.now():%Y-%m-%d %H:%M} ==', flush=True)
    estado = {'inicio': datetime.now().isoformat(timespec='seconds'), 'ok': {}, 'fallos': {}}
    pasos = [('paquete en vivo (asistencia, gastos, votaciones, Senado, Gobierno, noticias)', act_todo),
             ('votaciones del año (filas)', act_votaciones_filas), ('leyes promulgadas', act_leyes)]
    for nombre, fn in pasos:
        if solo and solo not in nombre:
            continue
        paso(nombre, fn, estado)
    estado['fin'] = datetime.now().isoformat(timespec='seconds')
    estado['fecha_datos'] = date.today().isoformat()
    json.dump(estado, open(_p('actualizacion_estado.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"== {len(estado['ok'])} fuentes actualizadas, {len(estado['fallos'])} conservadas del anterior ==", flush=True)
    return 0 if estado['ok'] else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
