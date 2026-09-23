# El Poder en Simple — genera calendario_votaciones.html
# Sin bases de datos: snapshot calendario_votaciones.json + padrón compacto de diputados.
import json

import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

with open(_p('template_calendario.html'), encoding='utf-8') as f:
    tpl = f.read()
with open(_p('calendario_votaciones.json'), encoding='utf-8') as f:
    cal = json.load(f)
dc = json.load(open(_p('data_completa.json'), encoding='utf-8'))
cal['diputados'] = {str(d['id']): {'n': d['nombre'], 'g': d['grupo']} for d in dc['diputados']}

data = json.dumps(cal, ensure_ascii=False)
html = tpl.replace('/*__DATA__*/', data)
assert 'const DATA = {' in html, 'no se inyectó el JSON'
assert '__DATA__' not in html, 'quedó marcador sin reemplazar'
with open(_p('calendario_votaciones.html'), 'w', encoding='utf-8') as f:
    f.write(html)
print(f'OK calendario_votaciones.html ({len(html):,} bytes)')
