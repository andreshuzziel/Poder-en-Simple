# El Poder en Simple — genera proxima_eleccion.html a partir de template_proxima.html
# + proxima_eleccion_resultados.json (si no existe, se construye desde proxima_eleccion.json
# en estado "esperando"). Sin bases de datos.
import json, os, subprocess, sys
import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

RES = _p('proxima_eleccion_resultados.json')
if not os.path.exists(RES):
    subprocess.run([sys.executable, _p('gen_proxima_eleccion.py')], check=True)
tpl = open(_p('template_proxima.html'), encoding='utf-8').read()
data = open(RES, encoding='utf-8').read()
json.loads(data)
html = tpl.replace('/*__DATA__*/', data)
assert 'const DATA = {' in html
open(_p('proxima_eleccion.html'), 'w', encoding='utf-8').write(html)
print(f'OK proxima_eleccion.html ({len(html):,} bytes)')
