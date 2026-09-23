# El Poder en Simple — "Resumen al oído": guion + audio de la semana, generado automáticamente desde los datos oficiales.
# Uso: python3 gen_audio_resumen.py            (se ejecuta en publicar.sh; el audio anterior se reemplaza)
#      python3 gen_audio_resumen.py --forzar   (aunque el audio actual tenga menos de 7 días)
# Requiere: pip install edge-tts   (voz neural en español de Chile; sin API key). Si falla, se conserva el audio anterior.
import os, sys, json, re, asyncio
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
def _p(n): return os.path.join(BASE_DIR, n)

AUDIO = _p('audio_resumen.mp3')
GUION = _p('audio_resumen.txt')
VOZ = os.environ.get('VOZ_RESUMEN', 'es-CL-LorenzoNeural')
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']


def _lee(n, default):
    try:
        return json.load(open(_p(n), encoding='utf-8'))
    except Exception:
        return default


def _fecha_larga(d):
    return f'{d.day} de {MESES[d.month - 1]}'


def _num(n):
    return f'{n:,}'.replace(',', '.')


def _en_simple(nombre):
    """'Modifica la ley N° 20.370...' → 'modifica la ley 20.370...'; 'Para la reconstrucción…' → 'busca la reconstrucción…'."""
    n = nombre.strip()
    n = re.sub(r'N[°º]\s*', '', n)
    n = n[0].lower() + n[1:]
    if n.startswith('para '):
        n = 'busca ' + n[5:]
    if n.startswith('sobre '):
        n = 'trata ' + n
    return n


def armar_guion():
    hoy = date.today()
    lun = hoy - timedelta(days=hoy.weekday()); dom = lun + timedelta(days=6)
    # semana "de cierre": si es lunes/martes hablamos de la semana pasada, que ya terminó
    if hoy.weekday() <= 1:
        lun, dom = lun - timedelta(days=7), dom - timedelta(days=7)
    ini, fin = lun.isoformat(), dom.isoformat()

    vots = _lee(f'votaciones_{hoy.year}.json', None) or _lee('votaciones_2026.json', [])
    nombres = dict(_lee('boletines_nombres.json', {}))
    for b, info in (_lee('calendario_votaciones.json', {}).get('proyectos') or {}).items():
        if isinstance(info, dict) and info.get('n') and b not in nombres:
            nombres[b] = info['n']
    for pr in ((_lee('data_completa.json', {}).get('votaciones') or {}).get('proyectos') or []):
        if pr.get('boletin') and pr.get('nombre') and pr['boletin'] not in nombres:
            nombres[pr['boletin']] = pr['nombre']
    congreso = _lee('congreso_data.json', {})
    leyes = _lee('leyes_promulgadas.json', [])
    gob = _lee('gobierno_snapshot.json', {})
    noticias = _lee('noticias.json', {})

    sem = [r for r in vots if ini <= r['fecha'][:10] <= fin]
    partes = [f'Hola. Este es el resumen al oído de El Poder en Simple, con lo más importante del Congreso y el Gobierno '
              f'entre el {_fecha_larga(lun)} y el {_fecha_larga(dom)}.']

    # --- Cámara: votaciones de la semana
    if sem:
        apro = sum(1 for r in sem if 'aprob' in r['resultado'].lower()); rech = len(sem) - apro
        dias = sorted({r['fecha'][:10] for r in sem})
        partes.append(f'La Cámara de Diputadas y Diputados votó {len(sem)} veces en {len(dias)} {"día" if len(dias) == 1 else "días"} de sesión: '
                      f'{apro} votaciones aprobadas y {rech} rechazadas.')
        g = {}
        for r in sem:
            if r['desc'].startswith('Boletín'):
                g.setdefault(r['desc'].replace('Boletín N° ', ''), []).append(r)
        top = sorted(g.items(), key=lambda kv: (-len(kv[1]), abs(kv[1][-1]['si'] - kv[1][-1]['no'])))[:3]
        for b, vs in top:
            vs.sort(key=lambda x: x['fecha']); u = vs[-1]
            nombre = nombres.get(b) or f'el proyecto del boletín {b}'
            nombre = re.sub(r'\s+', ' ', nombre).strip().rstrip('.')
            if len(nombre) > 160:
                nombre = nombre[:157].rsplit(' ', 1)[0] + '…'
            res = 'se aprobó' if 'aprob' in u['resultado'].lower() else 'se rechazó'
            conocido = b in nombres
            partes.append(f'{"Sobre el proyecto que " + _en_simple(nombre) if conocido else "Sobre " + nombre}: hubo {len(vs)} {"votación" if len(vs) == 1 else "votaciones"}; '
                          f'la última {res} con {u["si"]} votos a favor y {u["no"]} en contra.')
        cerrado = min(sem, key=lambda r: abs(r['si'] - r['no']))
        if abs(cerrado['si'] - cerrado['no']) <= 5 and len(sem) > 3:
            partes.append(f'La votación más reñida terminó {cerrado["si"]} a {cerrado["no"]}.')
    else:
        partes.append('Esta semana la Cámara de Diputadas y Diputados no registró votaciones en Sala'
                      + (': el Congreso estuvo en semana distrital o en receso.' if hoy.month != 2 else ': febrero es el mes de receso legislativo.'))

    # --- asistencia
    kpi = congreso.get('kpi') or {}
    if kpi.get('asistencia_promedio'):
        partes.append(f'En lo que va del período, la asistencia promedio a la Sala es de {str(kpi["asistencia_promedio"]).replace(".", ",")} por ciento '
                      f'en {kpi.get("total_sesiones", 0)} sesiones.')

    # --- leyes publicadas
    nuevas = [l for l in leyes if ini <= str(l.get('_fecha') or l.get('fecha') or '')[:10] <= fin]
    if nuevas:
        partes.append(f'Se {"publicó" if len(nuevas) == 1 else "publicaron"} {len(nuevas)} {"ley nueva" if len(nuevas) == 1 else "leyes nuevas"} en el Diario Oficial.')
        for l in nuevas[:2]:
            t = re.sub(r'\s+', ' ', str(l.get('titulo') or l.get('nombre') or '')).strip().rstrip('.')
            if t:
                partes.append(f'Entre ellas, la ley {l.get("numero") or ""}: {t[0].lower() + t[1:]}.'.replace('ley :', 'ley:'))

    # --- Gobierno
    pres = (gob.get('presidente') or {}).get('nombre') if isinstance(gob.get('presidente'), dict) else gob.get('presidente')
    ng = (noticias or {}).get('gobierno') or []
    if ng:
        t = re.sub(r'\s+', ' ', str(ng[0].get('titulo') or '')).strip().rstrip('.')
        if t:
            t = re.sub(r'^S\.E\. el ', 'El ', t)
            partes.append(f'Desde el Gobierno, lo último informado oficialmente: {t}.')
    ns = (noticias or {}).get('senado') or []
    if ns:
        t = re.sub(r'\s+', ' ', str(ns[0].get('titulo') or '')).strip().rstrip('.')
        if t:
            partes.append(f'Y en el Senado: {t}.')

    partes.append('Todo esto, con el detalle de cómo votó cada diputada y diputado, lo encuentras en El Poder en Simple. '
                  'Este resumen es informativo, no oficial, y se renueva cada semana con datos de la Cámara, el Senado y el Gobierno.')
    txt = ' '.join(partes)
    txt = re.sub(r'\s+', ' ', txt).replace(' ,', ',').replace('..', '.')
    return txt, lun, dom


async def _tts(texto, salida):
    import edge_tts
    com = edge_tts.Communicate(texto, VOZ, rate='+0%')
    await com.save(salida)


def main():
    forzar = '--forzar' in sys.argv
    if os.path.exists(AUDIO) and not forzar:
        edad = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(AUDIO))).days
        # se renueva una vez por semana (o si el audio quedó de otra semana ISO)
        misma_semana = datetime.fromtimestamp(os.path.getmtime(AUDIO)).isocalendar()[:2] == datetime.now().isocalendar()[:2]
        if misma_semana and edad < 7:
            print(f'audio_resumen.mp3 es de esta semana ({edad} días): no se renueva. Usa --forzar para rehacerlo.')
            return 0
    texto, lun, dom = armar_guion()
    print('Guion:', len(texto), 'caracteres')
    tmp = AUDIO + '.nuevo'
    try:
        asyncio.run(_tts(texto, tmp))
        if os.path.getsize(tmp) < 20_000:
            raise RuntimeError('audio demasiado corto')
    except Exception as e:
        print(f'⚠️ No se pudo crear la voz ({type(e).__name__}: {e}); se conserva el audio anterior.')
        if os.path.exists(tmp):
            os.remove(tmp)
        return 0
    if os.path.exists(AUDIO):
        os.remove(AUDIO)                       # el audio anterior se elimina (ciclo semanal)
    os.replace(tmp, AUDIO)
    open(GUION, 'w', encoding='utf-8').write(f'Resumen al oído · semana {lun.isoformat()} a {dom.isoformat()} · generado {date.today().isoformat()}\n\n{texto}\n')
    print(f'OK audio_resumen.mp3 ({os.path.getsize(AUDIO):,} bytes) · semana {lun} – {dom}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
