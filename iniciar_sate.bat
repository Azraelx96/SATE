@echo off
rem Inicia la aplicacion SATE con doble clic.
rem Guardar este archivo en la carpeta del proyecto, junto a app.py.

cd /d "%~dp0"
title SATE

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=py"
)

echo.
echo Iniciando SATE...
echo Se abrira en el navegador. Para cerrarla, cerra esta ventana o presiona Ctrl+C.
echo.

"%PY%" -m streamlit run app.py

echo.
echo La aplicacion se detuvo. Si fue por un error, copialo antes de cerrar esta ventana.
pause
