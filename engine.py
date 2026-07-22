"""
engine.py — Motor de extracción y validación normativa
Revisor de Informes Semestrales EFIARTES
"""

import re
from dataclasses import dataclass, field
from typing import Optional

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


# ─────────────────────────────────────────────────────────────
# EXTRACCIÓN DE TEXTO
# ─────────────────────────────────────────────────────────────

def extract_text(pdf_path: str) -> str:
    """Extrae texto completo de un PDF usando PyMuPDF."""
    if fitz is None:
        raise ImportError("PyMuPDF (fitz) no está instalado.")
    try:
        doc = fitz.open(pdf_path)
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages)
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

    # --- Nombre del proyecto ---
    fields["nombre_proyecto"] = _find_after_label(text, [
        r"nombre del proyecto\s*:?",
        r"proyecto(?:\s+de\s+inversi[o\u00f3]n)?\s+denominado\s+",
        r"proyecto\s*:\s*",
        r"t[\u00ed]tulo del proyecto\s*:?",
    ])
    # Si no encontrado con etiqueta, busca en mayúsculas entre comillas
    if not fields["nombre_proyecto"]:
        m = re.search(r'[\u00ab\u201c\u201d]([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][^\u00bb\u201c\u201d\n]{3,80})[\u00bb\u201c\u201d]', text)
        if m:
            fields["nombre_proyecto"] = m.group(1).strip()

    # --- Nombre de la ERPI ---
    erpi_raw = _find_after_label(text, [
        r"nombre de la erpi\s*:?",
        r"(?<![a-z])erpi\s*:\s*",
        r"empresa responsable del proyecto de inversi[\u00f3o]n\s*:?",
        r"empresa responsable\s*:?",
        r"empresa\s+productora\s*:?",
    ])
    if erpi_raw:
        # Cortar antes de palabras que indican el inicio de otro campo
        erpi_raw = re.split(r'\bEtapa\b|\bPeriodo\b|\bN\u00famero\b|\bRecinto\b', erpi_raw, flags=re.IGNORECASE)[0]
        erpi_raw = erpi_raw.strip()[:80]
        # Solo guardar si tiene contenido real (al menos 3 chars alfabéticos)
        if len(re.sub(r'[^a-zA-Z\u00c0-\u024f]', '', erpi_raw)) >= 3:
            fields["nombre_erpi"] = erpi_raw

    # --- Etapa ---
    etapa_val = _find_after_label(text, [r"etapa\s*:?\s*", r"etapa de desarrollo\s*:?"])
    if etapa_val:
        # Tomar solo las primeras palabras, limpiar texto extra
        etapa_val = re.split(r'[\n\r]', etapa_val)[0].strip()
        # Si empieza con "del proyecto" o similar, extraer la etapa real
        m_etapa = re.search(
            r'(producci[\u00f3o]n|estreno|circulaci[\u00f3o]n nacional|posproducci[\u00f3o]n|desarrollo)',
            etapa_val, re.IGNORECASE
        )
        fields["etapa"] = m_etapa.group(1).capitalize() if m_etapa else etapa_val[:40]
    else:
        # Buscar etapa directamente en texto
        text_lower = text.lower()
        for etapa in ETAPAS:
            if etapa in text_lower:
                fields["etapa"] = etapa.capitalize()
                break

    # --- Número del informe ---
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

    # --- Período ---
    m = re.search(
        r'(enero|julio)\s*(?:-|–|de|del|,)?\s*(20\d{2})',
        text, re.IGNORECASE
    )
    if m:
        fields["periodo"] = f"{m.group(1).capitalize()} {m.group(2)}"
    else:
        # Buscar período en formato "Jun-26" o "Ene 2025"
        m2 = re.search(r'(ene|jan|jun|jul)[a-z]*[\s\-–,]+(20\d{2}|\d{2})', text, re.IGNORECASE)
        if m2:
            fields["periodo"] = m2.group(0).strip()

    # --- Fecha de inicio de recursos ---
    # Busca fechas explícitas: "el DD de MES de YYYY" o "DD/MM/YYYY"
    DATE_PAT = r'(\d{1,2}\s+de\s+\w+\s+(?:de\s+)?20\d{2}|\d{1,2}[/\-]\d{1,2}[/\-]20\d{2})'
    fecha_inicio = None
    for pat in [
        r"fecha de inicio de (?:aplicaci[o\u00f3]n|los recursos)[^\n]{0,40}" + DATE_PAT,
        r"inicio de (?:la\s+)?aplicaci[o\u00f3]n[^\n]{0,40}" + DATE_PAT,
        r"se inici[o\u00f3][^\n]{0,60}" + DATE_PAT,
        r"inicio de aplicaci[o\u00f3]n de recursos[^\n]{0,30}:\s*" + DATE_PAT,
        r"fecha de inicio[^\n]{0,40}" + DATE_PAT,
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            fecha_inicio = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
            break
    # También busca el patrón con etiqueta simple
    if not fecha_inicio:
        raw = _find_after_label(text, [
            r"fecha de inicio de (?:aplicaci[o\u00f3]n de )?recursos\s*:?",
            r"inicio de aplicaci[o\u00f3]n de recursos\s*:?",
        ])
        if raw:
            # Verificar que hay una fecha real en el texto capturado
            dm = re.search(DATE_PAT, raw, re.IGNORECASE)
            if dm:
                fecha_inicio = dm.group(0)
    fields["fecha_inicio_recursos"] = fecha_inicio

    # --- Menciona documentos adjuntos ---
    adj_patterns = [
        r'se adjunt[ao]', r'se acompa[ñn]', r'documentos complementarios',
        r'estados de cuenta', r'comprobante', r'cartel adjunto',
        r'se incluye', r'se anexa', r'ver anexo',
    ]
    fields["menciona_adjuntos"] = any(
        re.search(p, text, re.IGNORECASE) for p in adj_patterns
    )

    # --- Texto de actividades ---
    # Extraer párrafos que contienen palabras clave de actividades
    act_keywords = [
        "ensayo", "actividad", "presenta", "función", "funciones",
        "realizad", "producci", "grabaci", "difusi", "administrati",
        "cronograma", "pago", "honorario", "contrato", "creativ",
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
    import os
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
