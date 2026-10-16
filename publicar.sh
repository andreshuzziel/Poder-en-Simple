#!/usr/bin/env bash
# Actualiza datos desde fuentes oficiales, regenera todas las páginas, corre pruebas y deja un commit.
# Uso: ./publicar.sh            (falla si alguna prueba falla → no se hace commit)
set -euo pipefail
cd "$(dirname "$0")"
echo "== 1/4 Datos =="
python3 actualizar_datos.py
echo "== 2/4 Páginas =="
python3 gen_audio_resumen.py || true
python3 gen_dashboard.py
python3 gen_vivo.py
python3 gen_excel.py
python3 gen_calendario.py && python3 gen_calendario_page.py
python3 gen_buscador_page.py
python3 gen_proxima_page.py
python3 gen_elecciones_page.py
echo "== 3/4 Pruebas =="
NP="${NODE_PATH:-/tmp/jst/node_modules}"
if [ -d "$NP/jsdom" ]; then
  for t in test_*_jsdom.js; do
    if out=$(NODE_PATH="$NP" node "$t" 2>&1); then
      echo "  ✔ $t"
    else
      echo "  ✘ $t"
      echo "$out"
      exit 1
    fi
  done
else
  echo "  (jsdom no instalado: pruebas omitidas)"
fi
echo "== 4/4 Commit =="
git add -A
if git diff --cached --quiet; then echo "Sin cambios."; else
  git -c user.name="${GIT_NAME:-actualizador}" -c user.email="${GIT_EMAIL:-actualizador@poderensimple}" \
    commit -qm "Actualización automática de datos $(date +'%Y-%m-%d %H:%M')" && echo "Commit listo."
fi
