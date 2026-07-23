import sys
sys.path.insert(0, r'C:\Users\gus_j\.gemini\antigravity\scratch\revisor_efiartes')
import fitz
import numpy as np
from PIL import Image
import pytesseract
import os

pdf_path = r'C:\Users\gus_j\Documents\SHCP\EFIARTES\informes semestrales ejemplos EFIARTES\Informe Semestral (Teatro) 2.pdf'
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

doc = fitz.open(pdf_path)
page = doc[0]
pix = page.get_pixmap(dpi=300)
img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

# Use RED channel
r, g, b = img.split()
pytesseract.tesseract_cmd = TESSERACT_PATH
text = pytesseract.image_to_string(r, lang="spa")
print(text[:1000])
