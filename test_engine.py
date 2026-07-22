import engine
import os

folder = r'C:\Users\gus_j\Documents\SHCP\EFIARTES\informes semestrales ejemplos EFIARTES'
files = [
    'Informe Semestral (Teatro).pdf',
    'Informe Semestral (Danza) 2.pdf',
    'Informe Semestral (Musica).pdf',
]
# Try finding Musica
all_files = os.listdir(folder)
musica = [x for x in all_files if 'sica' in x and '2' not in x]
if musica:
    files[2] = musica[0]

for fname in files:
    path = os.path.join(folder, fname)
    if not os.path.exists(path):
        print(f"No encontrado: {fname}")
        continue
    r = engine.process_report(path)
    print(f"--- {fname} ---")
    print(f"  Disciplina: {r['discipline']}")
    print(f"  Proyecto:   {r['rev_nombre_proyecto']}")
    print(f"  ERPI:       {r['rev_nombre_erpi']}")
    print(f"  Etapa:      {r['rev_etapa']}")
    print(f"  Numero:     {r['rev_numero_informe']}")
    print(f"  Periodo:    {r['rev_periodo']}")
    print(f"  Inicio:     {r['rev_fecha_inicio']}")
    print(f"  Status:     {r['status']}")
    print()
