"""
audit_all_pdfs.py - Auditoria completa de extraccion contra los 10 PDFs de ejemplo.
Imprime:
  1) Primeros 2500 chars del texto extraido (para diagnostico de regex)
  2) Campos extraidos
  3) Checklist status
"""
import sys, os, json, glob

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add engine directory to path
engine_dir = r"C:\Users\gus_j\.gemini\antigravity\scratch\revisor_efiartes"
sys.path.insert(0, engine_dir)

from engine import extract_text, extract_fields, detect_discipline, run_checklist, global_status, preprocess_text

PDF_DIR = r"C:\Users\gus_j\Documents\SHCP\EFIARTES\informes semestrales ejemplos EFIARTES"

pdfs = sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf")))
print(f"Encontrados {len(pdfs)} PDFs\n")

results = []

for i, pdf_path in enumerate(pdfs):
    fname = os.path.basename(pdf_path)
    print("=" * 80)
    print(f"[{i+1}/{len(pdfs)}] {fname}")
    print("=" * 80)

    raw_text = extract_text(pdf_path)
    proc_text = preprocess_text(raw_text)

    # Show first 2500 chars of preprocessed text for diagnosis
    print("\n--- TEXTO PREPROCESADO (primeros 2500 chars) ---")
    print(proc_text[:2500])
    print("--- FIN TEXTO ---\n")

    fields = extract_fields(raw_text)
    discipline = detect_discipline(raw_text)
    checklist = run_checklist(fields)
    status = global_status(checklist)

    extracted = {
        "nombre_proyecto": fields.get("nombre_proyecto"),
        "nombre_erpi": fields.get("nombre_erpi"),
        "etapa": fields.get("etapa"),
        "numero_informe": fields.get("numero_informe"),
        "numero_informe_int": fields.get("numero_informe_int"),
        "periodo": fields.get("periodo"),
        "fecha_inicio_recursos": fields.get("fecha_inicio_recursos"),
        "menciona_adjuntos": fields.get("menciona_adjuntos"),
        "disciplina": discipline,
        "status_global": status,
    }

    print("--- CAMPOS EXTRAIDOS ---")
    for k, v in extracted.items():
        if isinstance(v, bool):
            marker = "[OK]" if v else "[--]"
        elif v is None:
            marker = "[MISS]"
        else:
            marker = "[OK]"
        print(f"  {marker} {k}: {v}")

    print("\n--- CHECKLIST ---")
    for item in checklist:
        icon = {"ok": "[OK]", "warn": "[WARN]", "fail": "[FAIL]", "manual": "[MAN]"}.get(item.status, "[?]")
        print(f"  {icon} {item.id} {item.descripcion}: {item.detalle[:80]}")

    print()
    results.append({"file": fname, **extracted})

# Summary table
print("\n" + "=" * 80)
print("RESUMEN DE EXTRACCION")
print("=" * 80)
header = f"{'Archivo':<45} {'Proy':>4} {'ERPI':>4} {'Etap':>4} {'#Inf':>4} {'Peri':>4} {'Fech':>4} {'Adj':>4} {'Disc':>15} {'St':>4}"
print(header)
print("-" * len(header))
for r in results:
    row = (
        f"{r['file'][:44]:<45}"
        f" {'Y' if r['nombre_proyecto'] else 'N':>4}"
        f" {'Y' if r['nombre_erpi'] else 'N':>4}"
        f" {'Y' if r['etapa'] else 'N':>4}"
        f" {'Y' if r['numero_informe'] else 'N':>4}"
        f" {'Y' if r['periodo'] else 'N':>4}"
        f" {'Y' if r['fecha_inicio_recursos'] else 'N':>4}"
        f" {'Y' if r['menciona_adjuntos'] else 'N':>4}"
        f" {r['disciplina']:>15}"
        f" {r['status_global']:>4}"
    )
    print(row)

# Count successes
total = len(results)
print("\n--- TASA DE EXITO POR CAMPO ---")
for campo in ["nombre_proyecto", "nombre_erpi", "etapa", "numero_informe", "periodo", "fecha_inicio_recursos"]:
    hits = sum(1 for r in results if r[campo])
    print(f"  {campo}: {hits}/{total} ({100*hits//total}%)")
