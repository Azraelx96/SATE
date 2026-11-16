@echo off
rem Ejecuta las pruebas y genera un informe de cobertura (que parte del codigo se probo).
rem Al terminar abre el informe en el navegador.

cd /d "%~dp0.."
title Pruebas de SATE con informe de cobertura

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=py"
)

set "COVERAGE_FILE=tests\.coverage"

echo.
echo Ejecutando las pruebas de SATE y midiendo la cobertura...
echo.

"%PY%" -m pytest tests --cov=. --cov-config=tests/.coveragerc --cov-report=term --cov-report=html:tests/informe_cobertura

echo.
echo Abriendo el informe en el navegador...
start "" "tests\informe_cobertura\index.html"

echo.
pause
