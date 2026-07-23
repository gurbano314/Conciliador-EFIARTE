import sys
sys.path.insert(0, r'C:\Users\gus_j\.gemini\antigravity\scratch\revisor_efiartes')
import fitz
from PIL import Image
import pytesseract
import os

tesseract_dir = r"C:\Program Files\Tesseract-OCR"
os.environ["PATH"] += os.pathsep + tesseract_dir
pytesseract.pytesseract.tesseract_cmd = os.path.join(tesseract_dir, "tesseract.exe")

pdf_path = r'C:\Users\gus_j\Documents\SHCP\EFIARTES\informes semestrales ejemplos EFIARTES\Informe Semestral (Teatro) 2.pdf'

doc = fitz.open(pdf_path)
page = doc[0]
pix = page.get_pixmap(dpi=300)
img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

# Use RED channel to drop orange highlights
r, g, b = img.split()
text = pytesseract.image_to_string(r, lang="spa")
print("OCR TEXT (RED CHANNEL):")
print(text[:1000])
