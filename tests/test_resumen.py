"""Pruebas del resumen para autoridades (resumen.py).  HU-12.

Las cifras agregadas son lo único que se le envía a la IA para redactar el resumen
institucional, y el CSV exportado es lo único que sale del sistema hacia afuera.
"""
import io
import json
from collections import Counter

import pandas as pd
import pytest

import resumen
from reglas import copiar_reglas


@pytest.fixture
def ag(curso_calculado):
    return resumen.agregados(curso_calculado, copiar_reglas())


class TestAgregados:
    def test_total_de_estudiantes(self, ag):
        assert ag["total_estudiantes"] == 16

    def test_estudiantes_por_nivel(self, ag):
        assert ag["estudiantes_por_nivel"] == {"Alto": 4, "Medio": 2, "Bajo": 9, "Sin datos suficientes": 1}

    def test_los_niveles_suman_el_total(self, ag):
        assert sum(ag["estudiantes_por_nivel"].values()) == ag["total_estudiantes"]

    def test_alertas_por_dimension_coinciden_con_el_calculo(self, ag, curso_calculado):
        esperado = Counter(d for ds in curso_calculado["dimensiones"] for d in ds)
        assert ag["estudiantes_con_alerta_por_dimension"] == dict(esperado)

    def test_las_dimensiones_vienen_ordenadas_de_mas_a_menos_alertas(self, ag):
        valores = list(ag["estudiantes_con_alerta_por_dimension"].values())
        assert valores == sorted(valores, reverse=True)

    def test_reglas_mas_frecuentes_son_como_maximo_cinco_y_ordenadas(self, ag):
        top = ag["reglas_mas_frecuentes"]
        assert 1 <= len(top) <= 5
        conteos = [x["estudiantes"] for x in top]
        assert conteos == sorted(conteos, reverse=True)

    def test_las_reglas_se_nombran_con_su_nombre_y_no_con_su_id(self, ag):
        nombres = {r["nombre"] for r in copiar_reglas()}
        assert all(x["regla"] in nombres for x in ag["reglas_mas_frecuentes"])

    def test_ningun_conteo_supera_el_total_de_estudiantes(self, ag):
        assert all(x["estudiantes"] <= ag["total_estudiantes"] for x in ag["reglas_mas_frecuentes"])

    def test_regla_desconocida_se_muestra_con_su_id(self, curso_calculado):
        sin_nombres = [r for r in copiar_reglas() if r["id"] != "R01"]
        ag2 = resumen.agregados(curso_calculado, sin_nombres)
        etiquetas = {x["regla"] for x in ag2["reglas_mas_frecuentes"]}
        assert "R01" in etiquetas          # no falla: usa el ID cuando falta el nombre
        assert "Asistencia general" not in etiquetas

    def test_no_expone_codigos_ni_datos_individuales(self, ag):
        """Esto es lo que recibe la IA: nada que identifique a un estudiante."""
        texto = json.dumps(ag, ensure_ascii=False)
        assert not any(f"A0{i:02d}" in texto for i in range(1, 17))
        assert set(ag) == {"total_estudiantes", "estudiantes_por_nivel",
                           "estudiantes_con_alerta_por_dimension", "reglas_mas_frecuentes"}

    def test_se_puede_convertir_a_json(self, ag):
        json.dumps(ag)


class TestTextoResumen:
    def test_menciona_el_total_y_los_niveles_con_porcentaje(self, ag):
        t = resumen.texto_resumen(ag)
        assert "Se analizaron **16** estudiantes." in t
        assert "- **Alto:** 4 (25 %)" in t
        assert "- **Medio:** 2 (12 %)" in t       # 12,5 % se redondea a 12 (redondeo de Python)
        assert "- **Bajo:** 9 (56 %)" in t
        assert "- **Sin datos suficientes:** 1 (6 %)" in t

    def test_los_niveles_vienen_en_orden_de_gravedad(self, ag):
        t = resumen.texto_resumen(ag)
        assert t.index("**Alto:**") < t.index("**Medio:**") < t.index("**Bajo:**")

    def test_no_muestra_niveles_con_cero_estudiantes(self):
        ag0 = {"total_estudiantes": 3,
               "estudiantes_por_nivel": {"Alto": 0, "Medio": 0, "Bajo": 3, "Sin datos suficientes": 0},
               "estudiantes_con_alerta_por_dimension": {}, "reglas_mas_frecuentes": []}
        t = resumen.texto_resumen(ag0)
        assert "**Bajo:** 3 (100 %)" in t
        assert "**Alto:**" not in t and "**Sin datos" not in t
        assert "Dimensiones con más estudiantes" not in t and "Señales más frecuentes" not in t

    def test_incluye_dimensiones_y_senales_mas_frecuentes(self, ag):
        t = resumen.texto_resumen(ag)
        assert "Dimensiones con más estudiantes en alerta:" in t
        assert "Señales más frecuentes:" in t

    def test_aclara_que_es_una_guia_y_que_los_umbrales_no_estan_validados(self, ag):
        t = resumen.texto_resumen(ag)
        assert "guía para priorizar el acompañamiento" in t
        assert "no están validados" in t


class TestExportar:
    @pytest.fixture
    def tabla(self, curso_calculado):
        datos = resumen.exportar(curso_calculado)
        return datos, pd.read_csv(io.BytesIO(datos))

    def test_es_un_csv_utf8_con_bom_para_que_excel_lea_bien_los_acentos(self, tabla):
        datos, _ = tabla
        assert isinstance(datos, bytes) and datos.startswith(b"\xef\xbb\xbf")

    def test_columnas_exportadas(self, tabla):
        _, t = tabla
        assert list(t.columns) == ["codigo", "nivel", "indice", "puntaje",
                                   "dimensiones_con_alerta", "factores", "nota"]

    def test_no_exporta_datos_personales(self, curso_calculado):
        df = curso_calculado.copy()
        df["nombre"], df["dni"], df["legajo"] = "Ana", "30111222", "SATE-000001"
        texto = resumen.exportar(df).decode("utf-8-sig")
        assert "Ana" not in texto and "30111222" not in texto and "SATE-000001" not in texto

    def test_tiene_una_fila_por_estudiante(self, tabla):
        _, t = tabla
        assert len(t) == 16 and t["codigo"].is_unique

    def test_orden_alto_primero_y_dentro_del_nivel_de_mayor_a_menor_indice(self, tabla):
        _, t = tabla
        assert t["codigo"].tolist()[:4] == ["A005", "A002", "A013", "A008"]
        assert set(t["codigo"].tolist()[4:6]) == {"A004", "A010"}      # Medio (empatan en 23,1)
        assert t["nivel"].tolist()[6:15] == ["Bajo"] * 9

    def test_sin_datos_suficientes_va_al_final(self, tabla):
        _, t = tabla
        assert t["codigo"].iloc[-1] == "A016"
        assert t["nivel"].iloc[-1] == "Sin datos suficientes"

    def test_los_factores_se_separan_con_barra_vertical(self, tabla):
        _, t = tabla
        a005 = t[t["codigo"] == "A005"].iloc[0]
        assert " | " in a005["factores"]
        assert "Asistencia general" in a005["factores"]

    def test_las_dimensiones_se_separan_con_coma(self, tabla):
        _, t = tabla
        assert "Asistencia" in t[t["codigo"] == "A002"].iloc[0]["dimensiones_con_alerta"]
        assert "," in t[t["codigo"] == "A002"].iloc[0]["dimensiones_con_alerta"]

    def test_los_acentos_sobreviven_a_la_exportacion(self, curso_calculado):
        assert "Observación" in resumen.exportar(curso_calculado).decode("utf-8-sig")
