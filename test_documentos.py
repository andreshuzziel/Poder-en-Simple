# -*- coding: utf-8 -*-
"""Pruebas sin red del recolector de documentos oficiales (documentos.py). Imprime una lista JSON de booleanos."""
import documentos as D, io, zipfile, json

# 1. DOCX sintético de un oficio de veto
buf = io.BytesIO(); z = zipfile.ZipFile(buf, 'w')
ps = ['FUNDAMENTO DE LAS OBSERVACIONES', 'Al artículo 5: sobre el plazo. El plazo es corto.', 'LAS OBSERVACIONES',
      'AL ARTÍCULO 5', 'Para reemplazarlo por el siguiente: Artículo 5.- El plazo será de 60 días.', 'AL ARTÍCULO 9', 'Para suprimirlo.',
      'Dios guarde a V.E.,', 'NOMBRE PRESIDENTE', 'Presidente de la República']
z.writestr('word/document.xml', '<w:document><w:body>' + ''.join(f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in ps) + '</w:body></w:document>'); z.close()
txt, fmt = D.extraer_texto(buf.getvalue())
v = D.analizar_veto(txt)
ok1 = (fmt == 'docx' and len(v['observaciones']) == 2 and 'reemplazar' in v['observaciones'][0]['en_simple']
       and 'eliminar' in v['observaciones'][1]['en_simple'] and v['observaciones'][0].get('fundamento', '').startswith('Al artículo 5')
       and v['firman'][0] == 'NOMBRE PRESIDENTE' and '2 observaciones' in v['resumen'])

# 2. PDF mínimo
import pypdf
w = pypdf.PdfWriter(); pg = w.add_blank_page(width=300, height=300)
from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject
font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
pg[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): w._add_object(font)})})
cs = DecodedStreamObject(); cs.set_data(b'BT /F1 12 Tf 10 100 Td (MAT.: Informa) Tj ET'); pg[NameObject('/Contents')] = w._add_object(cs)
out = io.BytesIO(); w.write(out); pdf = out.getvalue()
t2, f2 = D.extraer_texto(pdf)
ok2 = f2 == 'pdf' and 'Informa' in t2 and D.analizar_oficio(t2).get('materia', '').startswith('Informa')

# 3. dominio no oficial rechazado
try:
    D.descargar_texto('https://ejemplo.com/x.pdf'); ok3 = False
except ValueError:
    ok3 = True

# 4. fechas
ok4 = D._fecha_iso('12 Ago. 2026') == '2026-08-12' and D._fecha_iso('05 Sept. 2025') == '2025-09-05'

# 5. informe de comisión sintético
inf = ('INFORME DE LA COMISIÓN\nI. OBJETIVO\nMejorar las pensiones de todos.\nII. CONSTANCIAS\n'
       'Asistieron el Ministro de Hacienda, señor Juan Pérez.\nPuesta en votación la indicación 1, fue aprobada por 3 votos a favor.\n')
a = D.analizar_informe(inf)
ok5 = a.get('objetivo', '').startswith('Mejorar') and any('Juan Pérez' in x for x in a.get('expositores', [])) and len(a.get('votaciones_comision', [])) == 1

# 6. OCR local sobre un PDF escaneado sintético (3 páginas imagen)
try:
    import pymupdf as fitz
    src = fitz.open()
    for s in ["FORMULA OBSERVACIONES AL PROYECTO.\nFUNDAMENTO DE LAS OBSERVACIONES\nAl artículo 32: sobre el plazo. Es muy corto.",
              "LAS OBSERVACIONES\nAL ARTÍCULO 32\nPara suprimirlo.\nAL ARTÍCULO 39\nPara reemplazarlo por otro.",
              "Modifica el artículo 9 de la ley N° 18.010.\nDios guarde a V.E.,\nNOMBRE PRESIDENTE\nPresidente de la República"]:
        pg = src.new_page(width=595, height=842); pg.insert_text((50, 80), s, fontsize=13, fontname='helv')
    scan = fitz.open()
    for pg in src:
        img = pg.get_pixmap(dpi=120).tobytes('png'); q = scan.new_page(width=595, height=842); q.insert_image(q.rect, stream=img)
    raw = scan.tobytes()
    plano, fmt = D.extraer_texto(raw)
    txt, oi = D.ocr_pdf(raw)
    v = D.analizar_veto(txt)
    import buscador as B
    citas = [c['cita'] for c in B.citas_en_texto(txt)]
    ok6 = (fmt == 'pdf' and len(plano) < 50 and oi['ocr'] and oi['ocr_paginas'] == 3 and oi['ocr_confianza'] > 0.6
           and len(v.get('observaciones', [])) == 2 and 'Ley N° 18.010' in citas)
except Exception as e:
    ok6 = False
# 7. normalización de errores típicos de OCR
n = D._normaliza_ocr('AL ARTiCULO 32\nModifica el articulo 9 de la ley No 18.010. Presidente de la Republica')
ok7 = 'AL ARTÍCULO 32' in n and 'artículo 9 de la ley N° 18.010' in n and 'República' in n
print(json.dumps([ok1, ok2, ok3, ok4, ok5, ok6, ok7]))
