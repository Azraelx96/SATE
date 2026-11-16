"""Configuración común de las pruebas de SATE.

Lo que hace este archivo (pytest lo carga solo, no hay que ejecutarlo):
- Permite que las pruebas encuentren los archivos del proyecto (reglas.py, carga.py...).
- Redirige SIEMPRE la base de datos a una carpeta temporal, para que ninguna
  prueba toque datos/sate.db (la base real).
- Deja listas "fixtures": piezas reutilizables (datos de ejemplo, un archivo falso, etc.).
- Mantiene apagadas las pruebas que necesitan un Ollama real, salvo que se pidan
  con la variable de entorno SATE_TESTS_OLLAMA=1.
"""
import io
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Columnas "sanas": un estudiante sin ninguna señal de riesgo en las 12 reglas.
SANO = {
    "asistencia_pct": 95.0,
    "inasistencias_consecutivas": 0,
    "llegadas_tarde": 0,
    "promedio": 8.0,
    "materias_desaprobadas": 0,
    "evaluaciones_ausente": 0,
    "entregas_sin_presentar": 0,
    "dias_sin_actividad": 0,
    "variacion_asistencia": 0.0,
    "variacion_promedio": 0.0,
    "materias_recursadas": 0,
    "preocupacion_tutor": 0,
}


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "ollama: prueba que usa un Ollama real (solo corre con SATE_TESTS_OLLAMA=1)",
    )


def pytest_collection_modifyitems(config, items):
    if os.getenv("SATE_TESTS_OLLAMA") == "1":
        return
    saltar = pytest.mark.skip(
        reason="Necesita Ollama real. Activala con la variable SATE_TESTS_OLLAMA=1"
    )
    for item in items:
        if item.get_closest_marker("ollama") is not None:
            item.add_marker(saltar)


# ---------------------------------------------------------------------------
# Base de datos: SIEMPRE temporal
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _aislar_bd_real(tmp_path, monkeypatch):
    """Antes de cada prueba, apunta almacenamiento a una carpeta temporal."""
    import almacenamiento

    carpeta = tmp_path / "datos_temporales"
    monkeypatch.setattr(almacenamiento, "CARPETA_DATOS", carpeta)
    monkeypatch.setattr(almacenamiento, "RUTA_BD", carpeta / "sate_prueba.db")


@pytest.fixture
def bd():
    """Módulo almacenamiento con una base temporal ya creada y vacía."""
    import almacenamiento

    almacenamiento.inicializar_bd()
    return almacenamiento


# ---------------------------------------------------------------------------
# Datos de ejemplo
# ---------------------------------------------------------------------------
@pytest.fixture
def raiz():
    return RAIZ


@pytest.fixture
def datos_ficticios():
    """Los 16 estudiantes ficticios del proyecto (datos/alumnos_ficticios.csv)."""
    return pd.read_csv(RAIZ / "datos" / "alumnos_ficticios.csv")


@pytest.fixture
def curso_calculado(datos_ficticios):
    """Los 16 estudiantes ya con el riesgo calculado."""
    from reglas import calcular_curso

    return calcular_curso(datos_ficticios)


@pytest.fixture
def sano():
    """Copia editable de un estudiante sin señales de riesgo."""
    return dict(SANO)


# ---------------------------------------------------------------------------
# Archivos subidos "de mentira" (imitan lo que entrega Streamlit)
# ---------------------------------------------------------------------------
class ArchivoFalso:
    """Imita un archivo subido: tiene .name, .size y .getvalue()."""

    def __init__(self, nombre, contenido):
        self.name = nombre
        self._contenido = contenido if isinstance(contenido, bytes) else contenido.encode("utf-8")
        self.size = len(self._contenido)

    def getvalue(self):
        return self._contenido


@pytest.fixture
def archivo_falso():
    return ArchivoFalso


@pytest.fixture
def excel_en_bytes():
    """Devuelve una función que convierte un DataFrame en los bytes de un .xlsx."""

    def _crear(df):
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False)
        return buffer.getvalue()

    return _crear
