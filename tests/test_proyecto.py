"""Pruebas de "salud" del proyecto: que todo se pueda importar y que no se filtren datos reales.

Son rápidas y atrapan descuidos comunes: un archivo con un error de sintaxis,
una dependencia que falta en requirements.txt o una base de datos a punto de
subirse a GitHub por accidente.
"""
import importlib
import re

import pytest

MODULOS = ["reglas", "carga", "almacenamiento", "ia", "orientacion", "resumen", "probar_orientacion"]


@pytest.mark.parametrize("modulo", MODULOS)
def test_cada_modulo_se_puede_importar(modulo):
    importlib.import_module(modulo)


class TestRequirements:
    @pytest.fixture
    def requisitos(self, raiz):
        texto = (raiz / "requirements.txt").read_text(encoding="utf-8")
        return {re.split(r"[<>=!~\[ ]", linea.strip())[0].lower()
                for linea in texto.splitlines() if linea.strip() and not linea.startswith("#")}

    @pytest.mark.parametrize("paquete", ["streamlit", "pandas", "openpyxl", "python-dotenv", "ollama"])
    def test_estan_las_dependencias_que_el_codigo_usa(self, requisitos, paquete):
        assert paquete in requisitos


class TestPrivacidadDelRepositorio:
    @pytest.fixture
    def gitignore(self, raiz):
        return (raiz / ".gitignore").read_text(encoding="utf-8").splitlines()

    def test_la_base_de_datos_real_no_se_sube_a_github(self, gitignore):
        assert "datos/sate.db" in gitignore and "*.db" in gitignore

    def test_el_archivo_env_no_se_sube_a_github(self, gitignore):
        assert ".env" in gitignore

    def test_la_carpeta_de_datos_reales_no_se_sube_a_github(self, gitignore):
        assert "datos_reales/" in gitignore

    def test_el_env_de_ejemplo_no_tiene_claves_secretas(self, raiz):
        texto = (raiz / ".env.example").read_text(encoding="utf-8").lower()
        assert "key" not in texto and "token" not in texto and "password" not in texto
        assert "ollama_host" in texto and "ollama_model" in texto

    def test_los_datos_de_ejemplo_son_ficticios_y_no_traen_datos_personales(self, datos_ficticios):
        import carga
        assert carga.columnas_personales(datos_ficticios.columns) == []

    def test_el_script_de_inicio_existe(self, raiz):
        assert (raiz / "iniciar_sate.bat").exists()
        assert (raiz / "app.py").exists()
