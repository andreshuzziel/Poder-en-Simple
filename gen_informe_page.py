# El Poder en Simple — genera informe_proyecto.html (dashboard "Informe completo de un proyecto").
# Página estática; los datos se piden en vivo a /api/informe (sin base de datos).
import shutil
shutil.copyfile('/home/user/template_informe.html', '/home/user/informe_proyecto.html')
import os; print(f"OK informe_proyecto.html ({os.path.getsize('/home/user/informe_proyecto.html'):,} bytes)")
