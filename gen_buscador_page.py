#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera buscador_avanzado.html desde template_buscador.html (página estática; la búsqueda usa el servidor en vivo)."""
import shutil, os
import os as _os
BASE_DIR = _os.path.dirname(_os.path.abspath(__file__))  # carpeta del proyecto (portátil: funciona en cualquier equipo o servidor)
def _p(nombre): return _os.path.join(BASE_DIR, nombre)

SRC = _p('template_buscador.html'); DST = _p('buscador_avanzado.html')
shutil.copyfile(SRC, DST)
print(f'OK buscador_avanzado.html ({os.path.getsize(DST):,} bytes)')
