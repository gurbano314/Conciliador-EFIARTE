"""
engine.py — Motor de extracción y validación normativa
Revisor de Informes Semestrales EFIARTES
v2.0 — Mejoras: OCR, truncado inteligente, fallbacks robustos
"""

import re
import os
from dataclasses import dataclass, field
from typing import Optional

# Debug flag: set environment variable EFIARTES_DEBUG=1 to enable
DEBUG = os.getenv('EFIARTES_DEBUG') == '1'

# Configure Tesseract path for Windows & PyInstaller
import sys
if hasattr(sys, '_MEIPASS'):
    # Running as PyInstaller executable
    base_dir = sys._MEIPASS
else:
    # Running from source
    base_dir = os.path.dirname(os.path.abspath(__file__))

TESSERACT_PATH = os.path.join(base_dir, 'bin', 'tesseract', 'tesseract.exe')

# Fallback to system installation if local bin doesn't exist
if not os.path.exists(TESSERACT_PATH):
    TESSERACT_PATH = os.getenv('TESSERACT_PATH', r'C:\Program Files\Tesseract-OCR\tesseract.exe')

if os.path.exists(TESSERACT_PATH):
    tesseract_dir = os.path.dirname(TESSERACT_PATH)
    if tesseract_dir not in os.environ.get('PATH', ''):
        os.environ['PATH'] = os.environ.get('PATH', '') + os.pathsep + tesseract_dir
    tessdata = os.path.join(tesseract_dir, 'tessdata')
    if os.path.isdir(tessdata):
        os.environ['TESSDATA_PREFIX'] = tessdata

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# ─────────────────────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────────────────────

DISCIPLINAS = {
    "Teatro":        ["efiteatro", "teatro", "producción teatral", "obra de teatro", "temporada teatral"],
    "Danza":         ["efidanza", "danza", "coreografía", "bailarín", "bailarina", "compañía de danza"],
    "Música":        ["efimusica", "efimúsica", "música", "concierto", "orquesta", "jazz", "ejecución instrumental",
                      "dirección de orquesta", "vocal", "músico"],
    "Artes Visuales":["efiartes visuales", "artes visuales", "exposición", "galería", "curaduría",
                      "muestra", "museografía", "instalación", "intervención"],
    "Libro":         ["efiliteraturas", "libro", "publicación", "obra literaria", "editorial",
                      "edición", "literatura"],
}

ETAPAS = ["producción", "estreno", "circulación nacional", "posproducción", "desarrollo"]

NUMEROS_INFORME = {
    "primero": 1, "primer": 1,
    "segundo": 2,
    "tercero": 3, "tercer": 3,
    "cuarto": 4,
    "quinto": 5,
    "sexto": 6,
    "séptimo": 7, "septimo": 7,
    "octavo": 8,
    "noveno": 9,
    "décimo": 10, "decimo": 10,
}

# Labels that signal the start of a new field — used to truncate captured values
NEXT_LABEL_PATTERNS = [
    r'\bnombre\s+de\s+la\s+(?:erpi|empresa)\b',
    r'\bempresa\s+(?:responsable|productora)\b',
    r'\betapa\s+(?:de\s+desarrollo|del\s+proyecto)\b',
    r'\berpi\b',
    r'\betapa\b',
    r'\bperiodo\s+del\s+informe\b',
    r'\bn[uú]mero\s+del\s+informe\b',
    r'\brecinto\b',
    r'\bfecha\s+de(?:l|\s+inicio)\b',
    r'\bejercicio\s+de\s+los\s+recursos\b',
    r'\bactividades\s+detalladas\b',
    r'\bpor\s+(?:este|medio)\b',
    r'\ba\s+quien\s+corresponda\b',
    r'\bRESUMEN\b',
    r'\bSIGN\b',
    r'\bB\.\s*N[uú]mero\b',
    r'\bC\.\s*Actividades\b',
]

# Minimum chars per page to consider a page has extractable text
MIN_CHARS_PER_PAGE = 40


# ─────────────────────────────────────────────────────────────
# TEXT PREPROCESSING
# ─────────────────────────────────────────────────────────────

def preprocess_text(text: str) -> str:
    """Normalize PDF extracted text.
    - Replace line‑breaks that split words (e.g., hyphenated words) with nothing.
    - Collapse remaining newlines into spaces so that multi‑line titles are treated as one line.
    """
    # Join lines broken by hyphenation or simple split without losing spaces
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    # Replace remaining newlines with a single space
    text = re.sub(r"\n+", " ", text)
    return text


def _truncate_at_next_label(value: str) -> str:
    """Truncate a captured field value when a known next-field label appears."""
    if not value:
        return value
    best_pos = len(value)
    for pat in NEXT_LABEL_PATTERNS:
        m = re.search(pat, value, re.IGNORECASE)
        if m and m.start() > 0:
            best_pos = min(best_pos, m.start())
    result = value[:best_pos].strip()
    # Remove trailing punctuation
    result = re.sub(r'[\s:—\-–.,;]+$', '', result).strip()
    return result if result else value


# ─────────────────────────────────────────────────────────────
# TEXT EXTRACTION + OCR
# ─────────────────────────────────────────────────────────────

def _try_ocr_page(page, lang: str = "spa") -> str:
    """Attempt OCR using PyTesseract with Max RGB filtering first (removes highlighters), then fallback to PyMuPDF."""
    text = _try_pytesseract_page(page, lang)
    if text and len(text.strip()) > 10:
        return text
    
    # Fallback to PyMuPDF built-in OCR
    try:
        tp = page.get_textpage_ocr(language=lang, dpi=300, full=True)
        text = page.get_text(textpage=tp)
        if DEBUG:
            print(f"  DEBUG PyMuPDF OCR page: got {len(text)} chars")
        return text
    except Exception as e:
        if DEBUG:
            print(f"  DEBUG PyMuPDF OCR failed for page: {e}")
        return ""


def _try_pytesseract_page(page, lang: str = "spa") -> str:
    """Fallback OCR using pytesseract + PIL with Max RGB filtering."""
    try:
        import pytesseract
        import numpy as np
        from PIL import Image
        
        # Add tesseract to PATH to avoid WinError 2
        tesseract_dir = os.path.dirname(TESSERACT_PATH)
        if tesseract_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] += os.pathsep + tesseract_dir
            
        if os.path.exists(TESSERACT_PATH):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
            
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Apply Max RGB filter: removes bright colored highlighters (orange, yellow, green)
        # while keeping black text intact
        arr = np.array(img)
        max_arr = np.max(arr, axis=2)
        img_max = Image.fromarray(max_arr)
        
        text = pytesseract.image_to_string(img_max, lang=lang)
        if DEBUG:
            print(f"  DEBUG pytesseract (Max RGB) page: got {len(text)} chars")
        return text
    except Exception as e:
        if DEBUG:
            print(f"  DEBUG pytesseract failed: {e}")
        return ""


def extract_text(pdf_path: str) -> str:
    """Extrae texto completo de un PDF usando PyMuPDF, con fallback a OCR para páginas escaneadas."""
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) no está instalado.")
    try:
        doc = fitz.open(pdf_path)
        pages_text = []
        ocr_used = False

        for page_num, page in enumerate(doc):
            text = page.get_text()

            # If the page has very little text, try OCR
            if len(text.strip()) < MIN_CHARS_PER_PAGE:
                if DEBUG:
                    print(f"  DEBUG: Page {page_num+1} has only {len(text.strip())} chars, attempting OCR...")
                ocr_text = _try_ocr_page(page)
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text
                    ocr_used = True

            pages_text.append(text)

        doc.close()

        full_text = "\n".join(pages_text)
        if ocr_used and DEBUG:
            print(f"  DEBUG: OCR was used for this document. Total text: {len(full_text)} chars")
        return full_text
    except Exception as e:
        return f"[ERROR al leer PDF: {e}]"


def get_page_count(pdf_path: str) -> int:
    """Retorna el número de páginas del PDF."""
    if fitz is None:
        return 0
    try:
        doc = fitz.open(pdf_path)
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────
# DETECCIÓN DE DISCIPLINA
# ─────────────────────────────────────────────────────────────

def detect_discipline(text: str) -> str:
    """
    Detecta la disciplina artística del informe.
    Retorna el nombre de la disciplina o 'No identificada'.
    """
    text_lower = text.lower()
    scores: dict[str, int] = {d: 0 for d in DISCIPLINAS}
    for disciplina, keywords in DISCIPLINAS.items():
        for kw in keywords:
            count = text_lower.count(kw.lower())
            scores[disciplina] += count
    best = max(scores, key=lambda d: scores[d])
    return best if scores[best] > 0 else "No identificada"


# ─────────────────────────────────────────────────────────────
# EXTRACCIÓN DE CAMPOS
# ─────────────────────────────────────────────────────────────

def _find_after_label(text: str, patterns: list[str], max_chars: int = 120) -> Optional[str]:
    """
    Busca el texto que sigue a una etiqueta (label) en el texto.
    Retorna el fragmento encontrado o None.
    """
    text_lower = text.lower()
    for pat in patterns:
        m = re.search(pat, text_lower)
        if m:
            # Capturar texto después del match hasta fin de línea o max_chars
            start = m.end()
            snippet = text[start:start + max_chars].strip()
            # Limpiar separadores comunes
            snippet = re.sub(r'^[\s:—\-–]+', '', snippet)
            # Tomar solo la primera línea significativa
            lines = [l.strip() for l in snippet.splitlines() if l.strip()]
            if lines:
                return lines[0][:100]
    return None


def extract_fields(text: str) -> dict:
    """
    Extrae los campos normativos del texto del informe.
    Retorna un dict con los campos encontrados.
    """
    fields = {
        "nombre_proyecto":    None,
        "nombre_erpi":        None,
        "etapa":              None,
        "numero_informe":     None,
        "numero_informe_int": None,
        "periodo":            None,
        "fecha_inicio_recursos": None,
        "menciona_adjuntos":  False,
        "actividades_texto":  "",
        "texto_completo":     text,
    }

    # Preprocess text to handle line breaks before extraction
    proc_text = preprocess_text(text)

    # ── Nombre del proyecto ──────────────────────────────────
    fields["nombre_proyecto"] = _find_after_label(proc_text, [
        r"nombre\s+del\s+proyecto\s*:?\s*",
        r"t[ií]tulo\s+del\s+proyecto\s*:?\s*",
        r"proyecto\s+de\s+inversi[óo]n\s+denominado\s+",
        r"proyecto\s+denominado\s+",
    ])
    if fields["nombre_proyecto"]:
        fields["nombre_proyecto"] = _truncate_at_next_label(fields["nombre_proyecto"])

    if DEBUG:
        print('DEBUG: nombre_proyecto after primary extraction:', fields["nombre_proyecto"])

    # Fallback: text in guillemets «...» or curly quotes "..."
    if not fields["nombre_proyecto"]:
        m = re.search(
            r'[\u00ab\u201c\u201d"]'
            r'([A-ZÁÉÍÓÚÑ][^\u00bb\u201c\u201d"]{3,200})'
            r'[\u00bb\u201c\u201d"]',
            proc_text
        )
        if m:
            candidate = m.group(1).replace('\n', ' ').replace('\r', ' ').strip()
            # Skip if it looks like a date/month, a short fragment, or ERPI info
            if (not re.search(r"erpi|empresa", candidate, re.IGNORECASE)
                    and len(candidate) > 8
                    and not re.match(r'^(?:ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)\s+\d{4}$', candidate, re.IGNORECASE)):
                fields["nombre_proyecto"] = _truncate_at_next_label(candidate)

    # Fallback: "del proyecto TITLE" with caps
    if not fields["nombre_proyecto"]:
        m = re.search(
            r"del\s+proyecto\s+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s,]{5,120})[.\n]",
            proc_text
        )
        if m:
            candidate = m.group(1).strip()
            if not re.search(r"erpi|empresa", candidate, re.IGNORECASE):
                fields["nombre_proyecto"] = _truncate_at_next_label(candidate)

    # Fallback for Libro-style: ALL-CAPS title after "INFORME SEMESTRAL N - MONTH YYYY"
    if not fields["nombre_proyecto"]:
        m = re.search(
            r"INFORME\s+SEMESTRAL\s*\d*\s*[-–]?\s*"
            r"(?:ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)"
            r"\s*\d{2,4}\s+"
            r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9\s]{5,120}?)(?:\s{2,}|\s+Por\s+medio)",
            proc_text
        )
        if m:
            candidate = m.group(1).strip()
            upper_ratio = sum(1 for c in candidate if c.isupper()) / max(len(candidate.replace(' ', '')), 1)
            if upper_ratio > 0.6 and len(candidate) > 10:
                fields["nombre_proyecto"] = candidate

    # Fallback: "del proyecto TITLE." repeated in body text
    if not fields["nombre_proyecto"]:
        m = re.search(
            r"del\s+proyecto\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9\s,]{5,120}?)\.",
            proc_text
        )
        if m:
            candidate = m.group(1).strip()
            upper_ratio = sum(1 for c in candidate if c.isupper()) / max(len(candidate.replace(' ', '')), 1)
            if upper_ratio > 0.5 and len(candidate) > 10:
                fields["nombre_proyecto"] = _truncate_at_next_label(candidate)

    # Fallback: "proyecto TITLE." with capitalized word
    if not fields["nombre_proyecto"]:
        m = re.search(
            r"proyecto\s+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s]{5,120})[.,]",
            proc_text
        )
        if m:
            candidate = m.group(1).strip()
            if not re.search(r"erpi|empresa", candidate, re.IGNORECASE):
                fields["nombre_proyecto"] = _truncate_at_next_label(candidate)

    # Quality filter: reject low-quality OCR captures
    if fields["nombre_proyecto"]:
        pn = fields["nombre_proyecto"]
        # Count special characters (non-alphanumeric, non-space, non-accented)
        special_chars = sum(1 for c in pn if not c.isalnum() and c not in ' áéíóúñÁÉÍÓÚÑ.,:-')
        alpha_chars = sum(1 for c in pn if c.isalpha())
        # Reject if too short, too many special chars, or no alphabetic content
        if len(pn) < 5 or alpha_chars < 3 or (special_chars > len(pn) * 0.3):
            if DEBUG:
                print(f'DEBUG: Rejecting low-quality nombre_proyecto: "{pn}"')
            fields["nombre_proyecto"] = None

    # ── Nombre de la ERPI ────────────────────────────────────
    erpi_raw = _find_after_label(proc_text, [
        r"empresa\s+responsable\s+del\s+proyecto\s+de\s+inversi[óo]n\s*:",
        r"empresa\s+responsable\s*:",
        r"nombre\s+de\s+la\s+erpi\s*:?\s*",
        r"empresa\s+productora\s*:\s*",
        r"(?<![a-z])erpi\s*:\s*",
    ])
    if erpi_raw:
        erpi_raw = _truncate_at_next_label(erpi_raw)
        erpi_raw = re.sub(r'[\.,;:\-—]+$', '', erpi_raw).strip()
        if erpi_raw:
            fields["nombre_erpi"] = erpi_raw

    # Fallback: "suscrito C. <NOMBRE> representante legal"
    if not fields["nombre_erpi"]:
        m = re.search(
            r"suscr[ií]t[oa]\s+C\.\s+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s]{3,80})\s+representante\s+legal",
            proc_text, re.IGNORECASE
        )
        if m:
            fields["nombre_erpi"] = m.group(1).strip()

    # Fallback: "<NAME>\nRepresentante Legal" (Libro-style, no label)
    if not fields["nombre_erpi"]:
        # Search in raw text (with newlines) for name on line before "Representante Legal"
        m = re.search(
            r"(?:_{2,}\s*\n\s*)?([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s]{5,80}?)\s*\n\s*Representante\s+Legal",
            text, re.IGNORECASE
        )
        if m:
            candidate = m.group(1).strip()
            # Ensure it looks like a name (2-5 words, not too long)
            words = candidate.split()
            if 2 <= len(words) <= 8:
                fields["nombre_erpi"] = candidate

    # Fallback: "nombre de la empresa productora: X" (alternate wording)
    if not fields["nombre_erpi"]:
        erpi_raw2 = _find_after_label(proc_text, [
            r"nombre\s+de\s+la\s+empresa\s+productora\s*:\s*",
            r"empresa\s+de\s+producci[óo]n\s*:\s*",
        ])
        if erpi_raw2:
            fields["nombre_erpi"] = _truncate_at_next_label(erpi_raw2)

    # Fallback: "*NAME AC" or "NAME, A.C." pattern in text (Teatro 3 style)
    if not fields["nombre_erpi"]:
        m = re.search(
            r'\*([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s]{3,60})\s+(?:A\.?C\.?|S\.?A\.?|S\.?C\.?)',
            proc_text
        )
        if m:
            fields["nombre_erpi"] = m.group(1).strip() + " " + m.group(0).split()[-1]

    # Fallback: "a nombre de NAME A.C." pattern
    if not fields["nombre_erpi"]:
        m = re.search(
            r'a\s+nombre\s+de\s+([A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ\s.,]{3,80}(?:A\.?C\.?|S\.?A\.?|S\.?C\.?))',
            proc_text, re.IGNORECASE
        )
        if m:
            fields["nombre_erpi"] = m.group(1).strip()

    # ── Etapa ────────────────────────────────────────────────
    etapa_val = _find_after_label(proc_text, [
        r"etapa\s+de\s+desarrollo\s+del\s+proyecto\s+de\s+inversi[óo]n\s*:\s*",
        r"etapa\s+de\s+desarrollo\s+del\s+proyecto\s*:\s*",
        r"etapa\s+del\s+proyecto\s+de\s+inversi[óo]n\s*:\s*",
        r"etapa\s+del\s+proyecto\s*:\s*",
        r"etapa\s+de\s+desarrollo\s*:\s*",
    ])
    if etapa_val:
        etapa_val = _truncate_at_next_label(etapa_val)
        fields["etapa"] = etapa_val[:120]
    else:
        # Fallback: table-style "ETAPA DEL PROYECTO <value>"
        etapa_val2 = _find_after_label(proc_text, [
            r"etapa\s+del\s*\n?\s*proyecto\s*:?\s*",
        ])
        if etapa_val2:
            etapa_val2 = _truncate_at_next_label(etapa_val2)
            fields["etapa"] = etapa_val2[:120]

    if not fields.get("etapa"):
        # Buscar etapa directamente en texto
        text_lower = text.lower()
        for etapa in ETAPAS:
            if etapa in text_lower:
                fields["etapa"] = etapa.capitalize()
                break

    # ── Número del informe ───────────────────────────────────
    # Busca "N informe semestral" o "Nto. informe semestral"
    m = re.search(
        r'(primer|primero|segundo|tercero|tercer|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno|d[eé]cimo)'
        r'[o]?\s+informe\s+semestral',
        text, re.IGNORECASE
    )
    if m:
        num_word = m.group(1).lower()
        fields["numero_informe"] = m.group(0).strip()
        fields["numero_informe_int"] = NUMEROS_INFORME.get(num_word, None)
    else:
        # Busca "Xo. Informe semestral" o "No. X informe semestral"
        m2 = re.search(r'(\d+)[o°ª]?\s*\.?\s*informe\s+semestral', text, re.IGNORECASE)
        if m2:
            fields["numero_informe"] = m2.group(0).strip()
            fields["numero_informe_int"] = int(m2.group(1))

    # Fallback: "INFORME SEMESTRAL N" in header style
    if not fields["numero_informe"]:
        m3 = re.search(r'INFORME\s+SEMESTRAL\s+(\d+)', text)
        if m3:
            fields["numero_informe"] = m3.group(0).strip()
            fields["numero_informe_int"] = int(m3.group(1))

    # Also search preprocessed text for ordinal + informe
    if not fields["numero_informe"]:
        m4 = re.search(
            r'(primer|primero|segundo|tercero|tercer|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno|d[eé]cimo)'
            r'[o]?\s+informe\s+semestral',
            proc_text, re.IGNORECASE
        )
        if m4:
            num_word = m4.group(1).lower()
            fields["numero_informe"] = m4.group(0).strip()
            fields["numero_informe_int"] = NUMEROS_INFORME.get(num_word, None)

    # ── Período ──────────────────────────────────────────────
    m = re.search(
        r'(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)'
        r'\s*(?:-|–|de|del|,|a)?\s*(20\d{2})',
        text, re.IGNORECASE
    )
    if m:
        fields["periodo"] = f"{m.group(1).capitalize()} {m.group(2)}"
    else:
        # Buscar período en formato "Jun-26" o "Ene 2025"
        m2 = re.search(r'(ene|jan|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)[a-z]*[\s\-–,]+(20\d{2}|\d{2})', text, re.IGNORECASE)
        if m2:
            fields["periodo"] = m2.group(0).strip()

    # Fallback: "FECHA DEL INFORME DD/MM/YYYY" (table format)
    if not fields["periodo"]:
        m3 = re.search(r'FECHA\s+DEL\s*\n?\s*INFORME\s*:?\s*(\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4})', proc_text, re.IGNORECASE)
        if m3:
            fields["periodo"] = m3.group(1).strip()

    # ── Fecha de inicio de recursos ──────────────────────────
    DATE_PAT = r'(\d{1,2}\s+de\s+\w+\s+(?:de\s+)?20\d{2}|\d{1,2}[/\-]\d{1,2}[/\-]20\d{2})'
    fecha_inicio = None

    # Search in both raw and preprocessed text
    for search_text in [text, proc_text]:
        if fecha_inicio:
            break
        for pat in [
            r"fecha\s+de\s+inicio\s+de\s+(?:aplicaci[oó]n|los\s+recursos).{0,60}" + DATE_PAT,
            r"inicio\s+de\s+(?:la\s+)?aplicaci[oó]n.{0,60}" + DATE_PAT,
            r"se\s+inici[oó]\s+la\s+aplicaci[oó]n.{0,80}" + DATE_PAT,
            r"inicio\s+de\s+aplicaci[oó]n\s+de\s+recursos.{0,40}:\s*" + DATE_PAT,
            r"fecha\s+de\s+inicio.{0,60}" + DATE_PAT,
            r"se\s+inici[oó].{0,80}" + DATE_PAT,
        ]:
            m = re.search(pat, search_text, re.IGNORECASE)
            if m:
                fecha_inicio = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
                break

    # Also try label-based search on preprocessed text
    if not fecha_inicio:
        raw = _find_after_label(proc_text, [
            r"fecha\s+de\s+inicio\s+de\s+(?:aplicaci[oó]n\s+de\s+)?recursos\s*:?\s*",
            r"inicio\s+de\s+aplicaci[oó]n\s+de\s+recursos\s*:?\s*",
            r"fecha\s+de\s+inicio\s+de\s+aplicaci[oó]n\s*:?\s*",
        ])
        if raw:
            dm = re.search(DATE_PAT, raw, re.IGNORECASE)
            if dm:
                fecha_inicio = dm.group(0)

    # Fallback: "El día DD de MES de YYYY se inició" pattern
    if not fecha_inicio:
        m = re.search(
            r'(?:el\s+)?(?:día\s+)?' + DATE_PAT + r'.{0,40}(?:se\s+inici[oó]|fue\s+realizada)',
            proc_text, re.IGNORECASE
        )
        if m:
            fecha_inicio = m.group(1)

    fields["fecha_inicio_recursos"] = fecha_inicio

    # ── Menciona documentos adjuntos ─────────────────────────
    adj_patterns = [
        r'se\s+adjunt[ao]', r'se\s+acompa[ñn]', r'documentos\s+complementarios',
        r'estados?\s+de\s+cuenta', r'comprobante', r'cartel\s+adjunto',
        r'se\s+incluye', r'se\s+anexa[n]?', r'ver\s+anexo',
        r'se\s+subie(?:ron|ó)', r'hiperv[ií]nculo', r'carpeta\s+comprobable',
        r'evidencia\s+fotogr[áa]fica', r'se\s+anexa(?:n)?\s+im[áa]genes',
        r'adjunto\s+encontrar', r'v[ée]ase\s+anexo',
        r'se\s+adjunta\s+como\s+anexo', r'anexo\s+\d',
        r'carpeta\s+de\s+(?:evidencia|comprobantes|respaldo)',
        r'drive\.google\.com', r'dropbox\.com',
    ]
    fields["menciona_adjuntos"] = any(
        re.search(p, text, re.IGNORECASE) for p in adj_patterns
    )
    # Also check preprocessed text
    if not fields["menciona_adjuntos"]:
        fields["menciona_adjuntos"] = any(
            re.search(p, proc_text, re.IGNORECASE) for p in adj_patterns
        )

    # ── Texto de actividades ─────────────────────────────────
    act_keywords = [
        "ensayo", "actividad", "presenta", "función", "funciones",
        "realizad", "producci", "grabaci", "difusi", "administrati",
        "cronograma", "pago", "honorario", "contrato", "creativ",
        "remontaje", "temporada", "gira", "estreno",
    ]
    lines = text.split('\n')
    act_lines = []
    for line in lines:
        line_l = line.lower()
        if any(kw in line_l for kw in act_keywords) and len(line.strip()) > 20:
            act_lines.append(line.strip())
    fields["actividades_texto"] = "\n".join(act_lines[:20])  # Máximo 20 líneas

    return fields


# ─────────────────────────────────────────────────────────────
# CHECKLIST NORMATIVO
# ─────────────────────────────────────────────────────────────

STATUS_OK    = "ok"      # Verde
STATUS_WARN  = "warn"    # Amarillo — posible pero incierto
STATUS_FAIL  = "fail"    # Rojo — no encontrado
STATUS_MANUAL = "manual" # Gris — requiere revisión manual

@dataclass
class CheckItem:
    id: str
    descripcion: str
    status: str       # ok | warn | fail | manual
    detalle: str = "" # Texto explicativo


def run_checklist(fields: dict, numero_informe_int: Optional[int] = None) -> list[CheckItem]:
    """
    Ejecuta las reglas de cumplimiento normativo y retorna la lista de items.
    """
    items: list[CheckItem] = []
    text = fields.get("texto_completo", "")

    # R1 — Nombre del proyecto
    if fields.get("nombre_proyecto"):
        items.append(CheckItem("R1", "Nombre del proyecto", STATUS_OK,
                               f'Encontrado: «{fields["nombre_proyecto"][:60]}»'))
    else:
        items.append(CheckItem("R1", "Nombre del proyecto", STATUS_FAIL,
                               "No se encontró el nombre del proyecto en el texto."))

    # R2 — Nombre de la ERPI
    if fields.get("nombre_erpi"):
        items.append(CheckItem("R2", "Nombre de la ERPI", STATUS_OK,
                               f'Encontrado: «{fields["nombre_erpi"][:60]}»'))
    else:
        items.append(CheckItem("R2", "Nombre de la ERPI", STATUS_FAIL,
                               "No se encontró el nombre de la ERPI."))

    # R3 — Etapa de desarrollo
    if fields.get("etapa"):
        items.append(CheckItem("R3", "Etapa de desarrollo", STATUS_OK,
                               f'Etapa: {fields["etapa"]}'))
    else:
        items.append(CheckItem("R3", "Etapa de desarrollo", STATUS_WARN,
                               "No se identificó claramente la etapa (Producción/Estreno/Circulación)."))

    # R4 — Número y período del informe
    has_num = bool(fields.get("numero_informe"))
    has_per = bool(fields.get("periodo"))
    if has_num and has_per:
        items.append(CheckItem("R4", "Número y período del informe", STATUS_OK,
                               f'{fields["numero_informe"]} — {fields["periodo"]}'))
    elif has_num or has_per:
        det = fields.get("numero_informe") or fields.get("periodo") or ""
        items.append(CheckItem("R4", "Número y período del informe", STATUS_WARN,
                               f"Solo se encontró uno de los dos: {det}"))
    else:
        items.append(CheckItem("R4", "Número y período del informe", STATUS_FAIL,
                               "No se encontró el número ni el período del informe."))

    # R5 — Actividades detalladas
    act_text = fields.get("actividades_texto", "")
    word_count = len(text.split())
    if len(act_text) > 100 or word_count > 200:
        items.append(CheckItem("R5", "Actividades detalladas", STATUS_OK,
                               f"Se detectaron actividades en el texto ({word_count} palabras)."))
    elif word_count > 80:
        items.append(CheckItem("R5", "Actividades detalladas", STATUS_WARN,
                               "El texto es breve. Verificar si hay suficiente detalle de actividades."))
    else:
        items.append(CheckItem("R5", "Actividades detalladas", STATUS_FAIL,
                               "El texto es muy breve para contener actividades detalladas."))

    # R6 — Fecha de inicio de recursos (obligatoria solo en el 1er informe)
    num_inf = fields.get("numero_informe_int") or numero_informe_int
    if num_inf == 1 or num_inf is None:
        # Es el primero o no se sabe
        if fields.get("fecha_inicio_recursos"):
            items.append(CheckItem("R6", "Fecha de inicio de aplicación de recursos", STATUS_OK,
                                   f'Fecha: {fields["fecha_inicio_recursos"][:60]}'))
        elif num_inf == 1:
            items.append(CheckItem("R6", "Fecha de inicio de aplicación de recursos", STATUS_FAIL,
                                   "Es el 1er informe semestral y no se encontró la fecha de inicio de recursos."))
        else:
            items.append(CheckItem("R6", "Fecha de inicio de aplicación de recursos", STATUS_WARN,
                                   "No se pudo determinar si es el 1er informe. Verificar si aplica."))
    else:
        # No es el primer informe, regla no aplica
        items.append(CheckItem("R6", "Fecha de inicio de recursos (N/A)", STATUS_OK,
                               f"No requerida para el informe #{num_inf}."))

    # R7 — Menciona documentos adjuntos
    if fields.get("menciona_adjuntos"):
        items.append(CheckItem("R7", "Documentos complementarios mencionados", STATUS_OK,
                               "Se menciona la inclusión de documentos de respaldo."))
    else:
        items.append(CheckItem("R7", "Documentos complementarios mencionados", STATUS_WARN,
                               "No se detecta mención explícita de documentos adjuntos de respaldo."))

    # R8 — Firma del representante legal (manual)
    items.append(CheckItem("R8", "Firma del representante legal", STATUS_MANUAL,
                           "Verificación manual requerida."))

    # R9 — Identificación oficial adjunta (manual)
    items.append(CheckItem("R9", "Identificación oficial adjunta", STATUS_MANUAL,
                           "Verificación manual requerida."))

    return items


def global_status(items: list[CheckItem]) -> str:
    """Calcula el semáforo global del informe según los checkitems."""
    statuses = [i.status for i in items if i.status != STATUS_MANUAL]
    if STATUS_FAIL in statuses:
        return STATUS_FAIL
    if STATUS_WARN in statuses:
        return STATUS_WARN
    return STATUS_OK


# ─────────────────────────────────────────────────────────────
# PROCESO COMPLETO DE UN INFORME
# ─────────────────────────────────────────────────────────────

def process_report(pdf_path: str) -> dict:
    """
    Procesa un PDF completo y retorna un dict con toda la información.
    """
    text = extract_text(pdf_path)
    pages = get_page_count(pdf_path)
    fields = extract_fields(text)
    discipline = detect_discipline(text)
    checklist = run_checklist(fields)
    status = global_status(checklist)

    return {
        "path":        pdf_path,
        "filename":    os.path.basename(pdf_path),
        "pages":       pages,
        "text":        text,
        "discipline":  discipline,
        "fields":      fields,
        "checklist":   checklist,
        "status":      status,
        # Campos editables por el revisor (sobreescriben los automáticos)
        "rev_nombre_proyecto":    fields.get("nombre_proyecto") or "",
        "rev_nombre_erpi":        fields.get("nombre_erpi") or "",
        "rev_disciplina":         discipline,
        "rev_etapa":              fields.get("etapa") or "",
        "rev_numero_informe":     fields.get("numero_informe") or "",
        "rev_periodo":            fields.get("periodo") or "",
        "rev_fecha_inicio":       fields.get("fecha_inicio_recursos") or "",
        "rev_firma":              False,   # checkbox manual
        "rev_id_oficial":         False,   # checkbox manual
        "rev_observaciones":      "",
        "rev_dictamen":           "",      # "Correcto" | "Con observaciones" | "Incompleto"
        "rev_revisado":           False,
        "rev_revisor":            "",
    }
