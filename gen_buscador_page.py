#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera buscador_avanzado.html desde template_buscador.html (página estática; la búsqueda usa el servidor en vivo)."""
import shutil, os
SRC = '/home/user/template_buscador.html'; DST = '/home/user/buscador_avanzado.html'
shutil.copyfile(SRC, DST)
print(f'OK buscador_avanzado.html ({os.path.getsize(DST):,} bytes)')
