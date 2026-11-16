"""Pruebas del script de evaluación manual (probar_orientacion.py).  HU-06.

Ese script sirve para revisar con calma la calidad de los textos del modelo real.
Acá se prueba con una IA simulada, en una carpeta temporal (para no ensuciar el proyecto).
"""
import shutil

import pytest

import ia
import probar_orientacion


@pytest.fixture
def carpeta_de_trabajo(tmp_path, raiz, monkeypatch):
    """El script lee datos/alumnos_ficticios.csv y escribe orientaciones_prueba.txt en la carpeta actual."""
    (tmp_path / "datos").mkdir()
    shutil.copy(raiz / "datos" / "alumnos_ficticios.csv", tmp_path / "datos" / "alumnos_ficticios.csv")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def ia_simulada(monkeypatch):
    enviados = []

    def devolucion(paquete):
        enviados.append(paquete)
        return "Conviene acompañar su asistencia. Propongo conversar esta semana."

    monkeypatch.setattr(ia, "disponible", lambda: True)
    monkeypatch.setattr(ia, "devolucion", devolucion)
    return enviados


class TestProbarOrientacion:
    def test_sin_ollama_avisa_y_termina_con_codigo_1(self, carpeta_de_trabajo, monkeypatch, capsys):
        monkeypatch.setattr(ia, "disponible", lambda: False)
        assert probar_orientacion.main([]) == 1
        salida = capsys.readouterr().out
        assert "Ollama no está disponible" in salida and "ollama list" in salida
        assert not (carpeta_de_trabajo / "orientaciones_prueba.txt").exists()

    def test_prueba_a_todos_los_de_nivel_medio_o_alto(self, carpeta_de_trabajo, ia_simulada, capsys):
        assert probar_orientacion.main([]) == 0
        assert "6 estudiante(s)" in capsys.readouterr().out      # 4 Alto + 2 Medio
        assert len(ia_simulada) == 6

    def test_se_puede_elegir_a_quien_probar(self, carpeta_de_trabajo, ia_simulada, capsys):
        assert probar_orientacion.main(["A002", "A005"]) == 0
        assert "2 estudiante(s)" in capsys.readouterr().out

    def test_un_estudiante_de_nivel_bajo_no_se_prueba(self, carpeta_de_trabajo, ia_simulada, capsys):
        assert probar_orientacion.main(["A001"]) == 1
        assert "No hay estudiantes con nivel Medio o Alto" in capsys.readouterr().out
        assert ia_simulada == []

    def test_guarda_el_resultado_completo_en_un_archivo_de_texto(self, carpeta_de_trabajo, ia_simulada):
        probar_orientacion.main(["A002"])
        contenido = (carpeta_de_trabajo / "orientaciones_prueba.txt").read_text(encoding="utf-8")
        assert "=== A002" in contenido
        assert "Conviene acompañar su asistencia." in contenido
        assert "--- datos enviados al modelo ---" in contenido
        assert "Para evaluar cada texto, preguntate:" in contenido     # los criterios de calidad

    def test_el_archivo_guardado_no_contiene_datos_personales(self, carpeta_de_trabajo, ia_simulada):
        probar_orientacion.main([])
        contenido = (carpeta_de_trabajo / "orientaciones_prueba.txt").read_text(encoding="utf-8")
        assert "legajo" not in contenido.lower() and "SATE-" not in contenido

    def test_si_el_modelo_falla_con_uno_sigue_con_los_demas(self, carpeta_de_trabajo, monkeypatch, capsys):
        llamadas = []

        def devolucion(paquete):
            llamadas.append(paquete)
            if len(llamadas) == 1:
                raise TimeoutError("tardó demasiado")
            return "Texto correcto."

        monkeypatch.setattr(ia, "disponible", lambda: True)
        monkeypatch.setattr(ia, "devolucion", devolucion)
        assert probar_orientacion.main([]) == 0
        salida = capsys.readouterr().out
        assert "ERROR: tardó demasiado" in salida
        assert len(llamadas) == 6

    def test_marca_los_textos_que_necesitan_revision(self, carpeta_de_trabajo, monkeypatch, capsys):
        monkeypatch.setattr(ia, "disponible", lambda: True)
        monkeypatch.setattr(ia, "devolucion", lambda p: "Corresponde una sanción.")
        probar_orientacion.main(["A002"])
        salida = capsys.readouterr().out
        assert "una sanción" in salida and "con avisos de revisión: 1 de 1" in salida
