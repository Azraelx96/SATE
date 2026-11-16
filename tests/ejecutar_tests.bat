@echo off
rem Ejecuta TODAS las pruebas automaticas de SATE con doble clic.
rem Esta en la carpeta tests; se mueve solo a la carpeta del proyecto.

cd /d "%~dp0.."
title Pruebas de SATE

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=py"
)

echo.
echo Ejecutando las pruebas de SATE... (tarda unos 15 segundos)
echo.

"%PY%" -m pytest tests

echo.
echo ------------------------------------------------------------
echo Si arriba dice "passed" en verde y no hay "failed" en rojo,
echo el proyecto funciona como se espera.
echo ------------------------------------------------------------
pause
