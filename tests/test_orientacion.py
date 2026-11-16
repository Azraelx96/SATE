"""Pruebas de la orientación para la tutoría (orientacion.py).  HU-06.

Dos funciones clave:
- armar_paquete: decide QUÉ datos se le envían al modelo (privacidad).
- revisar_texto: revisa lo que devolvió el modelo y avisa si algo merece atención.
"""
import json

import pandas as pd
import pytest

import orientacion
from orientacion import armar_paquete, revisar_texto, MAX_PALABRAS
from reglas import calcular_curso, copiar_reglas


def fila_de(curso, codigo):
    return curso[curso["codigo"] == codigo].iloc[0]


# ---------------------------------------------------------------------------
# armar_paquete
# ---------------------------------------------------------------------------
class TestArmarPaquete:
    def test_trae_exactamente_estos_campos(self, curso_calculado):
        p = armar_paquete(fila_de(curso_calculado, "A002"), copiar_reglas())
        assert set(p) == {"nivel", "indice", "dimensiones_con_alerta", "dimensiones_sin_alerta",
                          "factores_de_riesgo", "nota_del_sistema"}

    def test_contiene_el_resultado_ya_calculado_por_las_reglas(self, curso_calculado):
        fila = fila_de(curso_calculado, "A002")
        p = armar_paquete(fila, copiar_reglas())
        assert p["nivel"] == "Alto"
        assert p["indice"] == pytest.approx(84.6)
        assert p["dimensiones_con_alerta"] == sorted(fila["dimensiones"])
        assert p["factores_de_riesgo"] == [f["texto"] for f in fila["factores"]]

    def test_nunca_incluye_nombre_dni_legajo_codigo_ni_observaciones(self, curso_calculado):
        """El test de privacidad más importante: lo que sale hacia la IA."""
        fila = fila_de(curso_calculado, "A002").copy()
        fila["legajo"] = "SATE-000123"
        fila["nombre"] = "Juan Carlos"
        fila["apellido"] = "Pérez"
        fila["dni"] = "30123456"
        fila["observacion"] = "TEXTO SECRETO DEL TUTOR"
        texto = json.dumps(armar_paquete(fila, copiar_reglas()), ensure_ascii=False)
        for dato in ("SATE-000123", "Juan", "Pérez", "30123456", "TEXTO SECRETO", "A002"):
            assert dato not in texto

    def test_la_nota_del_sistema_es_none_cuando_no_hay_nota(self, curso_calculado):
        assert armar_paquete(fila_de(curso_calculado, "A002"), copiar_reglas())["nota_del_sistema"] is None

    def test_la_nota_del_sistema_se_incluye_cuando_existe(self, curso_calculado):
        fila = fila_de(curso_calculado, "A004").copy()
        fila["nota"] = "Nivel elevado a Medio: hay alertas en 4 dimensiones a la vez."
        assert armar_paquete(fila, copiar_reglas())["nota_del_sistema"].startswith("Nivel elevado")

    def test_dimensiones_sin_alerta_son_las_evaluadas_que_no_dieron_alerta(self, curso_calculado):
        fila = fila_de(curso_calculado, "A007")        # solo Asistencia con alerta
        p = armar_paquete(fila, copiar_reglas())
        assert p["dimensiones_con_alerta"] == ["Asistencia"]
        assert set(p["dimensiones_sin_alerta"]) == {"Compromiso", "Observación", "Rendimiento",
                                                    "Trayectoria", "Tendencia"}
        assert p["dimensiones_sin_alerta"] == sorted(p["dimensiones_sin_alerta"])

    def test_una_dimension_sin_datos_no_se_presenta_como_fortaleza(self, curso_calculado):
        """Solo puede haber 'fortaleza' si los datos la respaldan."""
        fila = fila_de(curso_calculado, "A011")
        fila = fila.copy()
        fila["promedio"] = float("nan")     # sin promedio ni R05/R06: Rendimiento puede quedar sin evaluar
        fila["materias_desaprobadas"] = float("nan")
        fila["evaluaciones_ausente"] = float("nan")
        p = armar_paquete(fila, copiar_reglas())
        assert "Rendimiento" not in p["dimensiones_sin_alerta"]
        assert "Rendimiento" not in p["dimensiones_con_alerta"]

    def test_una_regla_desactivada_no_cuenta_como_dimension_evaluada(self, curso_calculado):
        reglas = copiar_reglas()
        for r in reglas:
            if r["dimension"] == "Asistencia":
                r["activa"] = False
        p = armar_paquete(fila_de(curso_calculado, "A001"), reglas)
        assert "Asistencia" not in p["dimensiones_sin_alerta"]

    def test_estudiante_sano_tiene_todas_las_dimensiones_sin_alerta(self, curso_calculado):
        p = armar_paquete(fila_de(curso_calculado, "A001"), copiar_reglas())
        assert p["dimensiones_con_alerta"] == []
        assert len(p["dimensiones_sin_alerta"]) == 6

    def test_el_paquete_se_puede_convertir_a_json(self, curso_calculado):
        json.dumps(armar_paquete(fila_de(curso_calculado, "A005"), copiar_reglas()))

    def test_tipos_de_datos(self, curso_calculado):
        p = armar_paquete(fila_de(curso_calculado, "A002"), copiar_reglas())
        assert isinstance(p["nivel"], str) and isinstance(p["indice"], float)
        assert all(isinstance(t, str) for t in p["factores_de_riesgo"])


# ---------------------------------------------------------------------------
# revisar_texto
# ---------------------------------------------------------------------------
PAQUETE = {
    "nivel": "Alto", "indice": 46.2, "dimensiones_con_alerta": ["Asistencia"],
    "dimensiones_sin_alerta": ["Rendimiento"],
    "factores_de_riesgo": ["Asistencia general: 58% (por debajo de 60%, tramo grave) → +4"],
    "nota_del_sistema": None,
}
TEXTO_BUENO = ("Conviene acompañar su asistencia, que viene baja. "
               "Sería útil conversar con el estudiante esta semana para conocer qué dificultades encuentra.")


class TestRevisarTexto:
    def test_texto_correcto_no_genera_avisos(self):
        assert revisar_texto(TEXTO_BUENO, PAQUETE) == []

    @pytest.mark.parametrize("texto", ["", "   ", None])
    def test_texto_vacio(self, texto):
        assert revisar_texto(texto, PAQUETE) == ["La IA devolvió un texto vacío."]

    def test_limite_de_150_palabras(self):
        assert MAX_PALABRAS == 150
        justo = " ".join(["palabra"] * 150)
        largo = " ".join(["palabra"] * 151)
        assert revisar_texto(justo, PAQUETE) == []
        avisos = revisar_texto(largo, PAQUETE)
        assert len(avisos) == 1 and "151 palabras" in avisos[0]

    @pytest.mark.parametrize("palabra", ["sanción", "Sanción", "SANCION", "sancionar", "expulsión",
                                         "suspensión", "amonestación"])
    def test_detecta_sanciones(self, palabra):
        avisos = revisar_texto(f"Habría que aplicar una {palabra} al estudiante.", PAQUETE)
        assert any("una sanción" in a for a in avisos)

    @pytest.mark.parametrize("palabra", ["depresión", "ansiedad", "Trastorno", "diagnóstico",
                                         "patologia", "adicción"])
    def test_detecta_diagnosticos(self, palabra):
        avisos = revisar_texto(f"Parece haber {palabra} detrás de esto.", PAQUETE)
        assert any("un diagnóstico" in a for a in avisos)

    @pytest.mark.parametrize("frase", ["El estudiante abandonará seguro.", "Va a abandonar el curso.",
                                       "El abandono es inevitable."])
    def test_detecta_certezas_sobre_el_abandono(self, frase):
        avisos = revisar_texto(frase, PAQUETE)
        assert any("una certeza sobre el abandono" in a for a in avisos)

    def test_el_aviso_indica_la_palabra_encontrada(self):
        avisos = revisar_texto("Hay que evaluar una sanción.", PAQUETE)
        assert "«sanción»" in avisos[0]

    def test_detecta_cifras_que_no_estan_en_los_datos(self):
        avisos = revisar_texto("Tiene un 80 % de asistencia y 7 faltas.", PAQUETE)
        aviso = next(a for a in avisos if "cifras" in a)
        assert "80" in aviso and "7" in aviso

    def test_las_cifras_que_si_estan_en_los_datos_no_se_marcan(self):
        assert revisar_texto("Su asistencia es del 58%, por debajo del 60%.", PAQUETE) == []

    def test_coma_y_punto_decimal_se_consideran_la_misma_cifra(self):
        paquete = dict(PAQUETE, factores_de_riesgo=["Promedio general: 4.2 (por debajo de 4.5) → +4"])
        assert revisar_texto("Su promedio es de 4,2.", paquete) == []

    def test_varios_problemas_dan_varios_avisos(self):
        texto = "Merece una sanción, tiene ansiedad y faltó 33 veces."
        avisos = revisar_texto(texto, PAQUETE)
        assert len(avisos) == 3

    def test_devuelve_siempre_una_lista(self):
        assert isinstance(revisar_texto(TEXTO_BUENO, PAQUETE), list)


class TestNumeros:
    def test_extrae_enteros_y_decimales_con_coma_o_punto(self):
        assert orientacion._numeros("7,5 y 7.5 y 12 y 3,25") == {"7.5", "12", "3.25"}

    def test_texto_sin_numeros(self):
        assert orientacion._numeros("sin cifras") == set()
