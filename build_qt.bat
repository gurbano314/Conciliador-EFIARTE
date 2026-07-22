@echo off
REM build_qt.bat — Compila el Revisor EFIARTES en un solo .exe
echo.
echo ============================================
echo  BUILD: Revisor de Informes EFIARTES
echo ============================================
echo.

REM Activar entorno virtual (reusar el del Conciliador)
call ..\conciliador_qt\build_venv_qt\Scripts\activate.bat

echo [1/3] Instalando dependencias...
pip install -q PyQt6 PyMuPDF openpyxl pyinstaller

echo [2/3] Compilando con PyInstaller...
pyinstaller --onedir --windowed ^
  --name "Revisor_EFIARTES" ^
  --add-data "engine.py;." ^
  main_qt.py

echo [3/3] Listo!
echo El ejecutable está en: dist\Revisor_EFIARTES\Revisor_EFIARTES.exe
echo.
pause
