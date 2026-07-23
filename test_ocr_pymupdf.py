import sys
sys.path.insert(0, r'C:\Users\gus_j\.gemini\antigravity\scratch\revisor_efiartes')
import fitz
from PIL import Image
import os

pdf_path = r'C:\Users\gus_j\Documents\SHCP\EFIARTES\informes semestrales ejemplos EFIARTES\Informe Semestral (Teatro) 2.pdf'

doc = fitz.open(pdf_path)
page = doc[0]
pix = page.get_pixmap(dpi=300)
img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

# Use RED channel to drop orange highlights
r, g, b = img.split()
img_byte_arr = r.tobytes()

# Create a grayscale pixmap from the red channel
gray_pix = fitz.Pixmap(fitz.csGRAY, pix.width, pix.height, img_byte_arr, False)

# Create a new temp PDF doc and insert the image
temp_doc = fitz.open()
temp_page = temp_doc.new_page(width=pix.width, height=pix.height)
temp_page.insert_image(temp_page.rect, pixmap=gray_pix)

# Run OCR
text = temp_page.get_textpage_ocr(language="spa", dpi=300, full=True).extractText()
print("OCR TEXT:")
print(text[:1000])
