import engine
import os

folder = r'C:\Users\gus_j\Documents\SHCP\EFIARTES\informes semestrales ejemplos EFIARTES'
files = [f for f in os.listdir(folder) if f.lower().endswith('.pdf')]

for fname in files:
    path = os.path.join(folder, fname)
    r = engine.process_report(path)
    print(f"============================================================")
    print(f"ARCHIVO:    {fname}")
    print(f"DISCIPLINA: {r['rev_disciplina']}")
    print(f"PROYECTO:   {r['rev_nombre_proyecto']}")
    print(f"ERPI:       {r['rev_nombre_erpi']}")
    print(f"ETAPA:      {r['rev_etapa']}")
    print(f"Nº INF:     {r['rev_numero_informe']}")
    print(f"PERIODO:    {r['rev_periodo']}")
    print(f"INICIO:     {r['rev_fecha_inicio']}")
    print(f"SEMÁFORO:   {r['status']}")
    print()
