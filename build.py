import PyInstaller.__main__
import os
import shutil

# Ensure we're in the right directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Clean up previous builds if they exist
for folder in ['build', 'dist']:
    if os.path.exists(folder):
        shutil.rmtree(folder)

print("Iniciando empaquetado con PyInstaller...")

PyInstaller.__main__.run([
    'main_qt.py',                     # Script principal
    '--name=RevisorEFIARTES',         # Nombre del ejecutable
    '--windowed',                     # No mostrar consola
    '--add-data=bin/tesseract;bin/tesseract',  # Incluir Tesseract mini
    '--noconfirm',                    # Sobrescribir sin preguntar
    '--clean',                        # Limpiar cache
])

print("Empaquetado completado. El ejecutable está en la carpeta 'dist'.")
