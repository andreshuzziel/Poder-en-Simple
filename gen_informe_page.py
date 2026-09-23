# El Poder en Simple — genera informe_proyecto.html (dashboard "Informe completo de un proyecto").
# Página estática; los datos se piden en vivo a /api/informe (sin base de datos).
import shutil
import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

shutil.copyfile(_p('template_informe.html'), _p('informe_proyecto.html'))
import os; print(f"OK informe_proyecto.html ({os.path.getsize(_p('informe_proyecto.html')):,} bytes)")
