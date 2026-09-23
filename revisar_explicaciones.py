# El Poder en Simple — revisar_explicaciones.py
# Revisión humana periódica del explicador: imprime una muestra aleatoria de votaciones con
# (1) el texto oficial, (2) la explicación automática, para anotar errores y corregir explicador.py.
# Uso: python3 revisar_explicaciones.py [cantidad=20] [semilla]
import json, random, sys, textwrap, explicador

import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
random.seed(sys.argv[2] if len(sys.argv) > 2 else None)
cal = json.load(open(_p('calendario_votaciones.json'), encoding='utf-8'))
muestra = random.sample(cal['votaciones'], min(n, len(cal['votaciones'])))
for i, v in enumerate(muestra, 1):
    o = v.get('obs') or {}
    r = explicador.explicar_votacion(o.get('articulo'), o.get('tramite'), o.get('informe'), v.get('quorum'), v['resultado'],
                                     v['si'], v['no'], v['abst'], v['tipo'], v.get('titulo'), v['desc'])
    print(f"\n#{i} · votación {v['id']} · {v['fecha']} · {v['tipo']} · {v['desc']}")
    print('  OFICIAL :', textwrap.shorten(o.get('articulo') or '(sin observación)', 400))
    print('  TITULAR :', r['titular'])
    print('  SIMPLE  :', textwrap.fill(r['que'], 110, subsequent_indent='            '))
    print('  AHORA   :', r['consecuencia'])
    print('  ¿OK? [ ] sí  [ ] no → anota el error en INSTRUCTIVO.txt (sección 8) y agrega el caso a test_buscador_jsdom.js')
