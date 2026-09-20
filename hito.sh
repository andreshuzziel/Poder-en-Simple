#!/usr/bin/env bash
# Hito seguro — El Poder en Simple
# Regenera la página electoral, corre TODOS los tests jsdom (tablero electoral +
# dashboard principal) y SOLO si están verdes commitea todo el repo
# (backup sin base de datos: git es el "checkpoint").
set -e
cd "$(dirname "$0")"

echo '→ regenerando elecciones_chile.html…'
python3 gen_elecciones_page.py
echo '→ regenerando proxima_eleccion.html…'
python3 gen_proxima_page.py
python3 gen_buscador_page.py

# entorno jsdom: reutiliza si ya existe en /tmp/jst o /tmp/jstest
if [ -d /tmp/jstest/node_modules/jsdom ]; then JST=/tmp/jstest
elif [ -d /tmp/jst/node_modules/jsdom ]; then JST=/tmp/jst
else
  mkdir -p /tmp/jst
  (cd /tmp/jst && npm install jsdom --silent)
  JST=/tmp/jst
fi

echo '→ tests del tablero electoral…'
NODE_PATH=$JST/node_modules node test_mapa_jsdom.js | tail -1
NODE_PATH=$JST/node_modules node test_mapa_jsdom.js > /dev/null

echo '→ tests del dashboard principal…'
NODE_PATH=$JST/node_modules node test_dashboard_jsdom.js | tail -1
NODE_PATH=$JST/node_modules node test_dashboard_jsdom.js > /dev/null

echo '→ tests de la próxima elección…'
NODE_PATH=$JST/node_modules node test_proxima_jsdom.js | tail -1
NODE_PATH=$JST/node_modules node test_proxima_jsdom.js > /dev/null

echo '→ tests del calendario de votaciones…'
NODE_PATH=$JST/node_modules node test_calendario_jsdom.js | tail -1
NODE_PATH=$JST/node_modules node test_calendario_jsdom.js > /dev/null

echo '→ tests del buscador avanzado…'
NODE_PATH=$JST/node_modules node test_buscador_jsdom.js | tail -1
NODE_PATH=$JST/node_modules node test_buscador_jsdom.js > /dev/null

# repo git: se inicializa solo la primera vez
if [ ! -d .git ]; then
  git init -q
  echo '→ repo git inicializado'
fi
git config user.name  >/dev/null 2>&1 || git config user.name  "El Poder en Simple"
git config user.email >/dev/null 2>&1 || git config user.email "hito@elpoderensimple.local"

git add -A
if git diff --cached --quiet; then
  echo '✔ todo verde; sin cambios que commitear'
else
  git commit -q -m "hito $(date '+%Y-%m-%d %H:%M') · $(git diff --cached --shortstat | sed 's/^ *//;s/[,;] */ /g')"
  echo "✔ hito commiteado: $(git log -1 --format='%s')"
fi
