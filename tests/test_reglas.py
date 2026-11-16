"""Pruebas del motor de reglas (reglas.py).  HU-03, HU-05 y HU-10.

Esto es lo más importante del proyecto: el semáforo (Bajo / Medio / Alto) lo
deciden estas reglas, no la IA.
"""
from collections import Counter

import pandas as pd
import pytest

import reglas
from reglas import (
    REGLAS, INDICE_ALTO, INDICE_MEDIO, COBERTURA_MINIMA,
    calcular_riesgo, calcular_curso, copiar_reglas,
)


def puntos_regla(id_regla, valor):
    """Puntos que suma UNA regla para UN valor (evalúa la regla aislada)."""
    regla = next(r for r in REGLAS if r["id"] == id_regla)
    resultado = calcular_riesgo(pd.Series({regla["variable"]: valor}), [regla])
    return resultado["puntaje"]


def regla_simple(id_, variable, puntos, dimension="D"):
    """Regla de juguete para probar cortes del índice con números redondos."""
    return {"id": id_, "nombre": id_, "dimension": dimension, "variable": variable,
            "sentido": "mayor", "unidad": "", "umbral_leve": 1, "puntos_leve": puntos,
            "umbral_grave": None, "puntos_grave": None, "activa": True}


# ---------------------------------------------------------------------------
# La tabla de reglas en sí
# ---------------------------------------------------------------------------
class TestTablaDeReglas:
    def test_hay_12_reglas_en_6_dimensiones(self):
        assert len(REGLAS) == 12
        assert len({r["dimension"] for r in REGLAS}) == 6

    def test_los_id_son_unicos_y_van_de_R01_a_R12(self):
        assert [r["id"] for r in REGLAS] == [f"R{i:02d}" for i in range(1, 13)]

    def test_puntaje_maximo_total_es_39(self):
        """Si alguien cambia un peso sin querer, este número cambia y avisa."""
        assert sum(reglas._peso_maximo(r) for r in REGLAS) == 39

    def test_todas_las_reglas_estan_activas_por_defecto(self):
        assert all(r["activa"] for r in REGLAS)

    @pytest.mark.parametrize("regla", REGLAS, ids=lambda r: r["id"])
    def test_cada_regla_tiene_los_campos_necesarios(self, regla):
        for campo in ("id", "nombre", "dimension", "variable", "sentido", "umbral_leve", "puntos_leve"):
            assert campo in regla
        assert regla["sentido"] in ("menor", "mayor")

    @pytest.mark.parametrize("regla", [r for r in REGLAS if r["umbral_grave"] is not None],
                             ids=lambda r: r["id"])
    def test_el_tramo_grave_es_mas_severo_que_el_leve(self, regla):
        if regla["sentido"] == "menor":
            assert regla["umbral_grave"] < regla["umbral_leve"]
        else:
            assert regla["umbral_grave"] > regla["umbral_leve"]
        assert regla["puntos_grave"] >= regla["puntos_leve"]

    def test_solo_R02_es_regla_critica(self):
        assert [r["id"] for r in REGLAS if r.get("critica")] == ["R02"]

    def test_parametros_de_la_matriz_de_riesgo(self):
        assert (INDICE_MEDIO, INDICE_ALTO, COBERTURA_MINIMA) == (15, 30, 0.5)
        assert reglas.ESCALAMIENTO_DIMENSIONES == {3: "Medio", 5: "Alto"}


# ---------------------------------------------------------------------------
# Bordes de cada regla (el error típico es confundir < con <=)
# ---------------------------------------------------------------------------
BORDES = [
    # (regla, valor, puntos esperados)
    ("R01", 75.0, 0), ("R01", 74.9, 2), ("R01", 60.0, 2), ("R01", 59.9, 4),
    ("R02", 4, 0), ("R02", 5, 2), ("R02", 9, 2), ("R02", 10, 4),
    ("R03", 4, 0), ("R03", 5, 1), ("R03", 9, 1), ("R03", 10, 2),
    ("R04", 6.0, 0), ("R04", 5.9, 2), ("R04", 4.5, 2), ("R04", 4.4, 4),
    ("R05", 1, 0), ("R05", 2, 2), ("R05", 3, 4),
    ("R06", 0, 0), ("R06", 1, 1), ("R06", 2, 3),
    ("R07", 1, 0), ("R07", 2, 2), ("R07", 3, 2), ("R07", 4, 4),
    ("R08", 6, 0), ("R08", 7, 1), ("R08", 14, 1), ("R08", 15, 3),
    ("R09", -10, 0), ("R09", -10.1, 1), ("R09", -20, 1), ("R09", -20.1, 3),
    ("R10", -1.0, 0), ("R10", -1.1, 1), ("R10", -2.0, 1), ("R10", -2.1, 3),
    ("R11", 0, 0), ("R11", 1, 1), ("R11", 2, 1), ("R11", 3, 2),
    ("R12", 0, 0), ("R12", 1, 3),
]


@pytest.mark.parametrize("id_regla, valor, esperado", BORDES,
                         ids=[f"{r}_{v}" for r, v, _ in BORDES])
def test_bordes_de_cada_regla(id_regla, valor, esperado):
    assert puntos_regla(id_regla, valor) == esperado


# ---------------------------------------------------------------------------
# Cortes del índice y niveles (HU-03)
# ---------------------------------------------------------------------------
class TestNiveles:
    @pytest.mark.parametrize("puntos, nivel", [
        (0, "Bajo"), (14.9, "Bajo"), (15, "Medio"), (29.9, "Medio"), (30, "Alto"), (100, "Alto"),
    ])
    def test_cortes_del_indice(self, puntos, nivel):
        # Dos reglas que suman 100 puntos en total: el índice es justo "puntos".
        pares = [regla_simple("A", "a", puntos), regla_simple("B", "b", 100 - puntos)]
        resultado = calcular_riesgo(pd.Series({"a": 1, "b": 0}), pares)
        assert resultado["indice"] == pytest.approx(puntos)
        assert resultado["nivel"] == nivel

    def test_estudiante_sano_es_bajo_con_indice_cero(self, sano):
        r = calcular_riesgo(pd.Series(sano))
        assert (r["nivel"], r["indice"], r["puntaje"], r["maximo"]) == ("Bajo", 0.0, 0, 39)
        assert r["factores"] == [] and r["dimensiones"] == [] and r["nota"] == ""

    def test_estudiante_en_el_peor_caso_suma_los_39_puntos(self):
        peor = pd.Series({
            "asistencia_pct": 0, "inasistencias_consecutivas": 30, "llegadas_tarde": 30,
            "promedio": 0, "materias_desaprobadas": 9, "evaluaciones_ausente": 9,
            "entregas_sin_presentar": 9, "dias_sin_actividad": 90,
            "variacion_asistencia": -90, "variacion_promedio": -9,
            "materias_recursadas": 9, "preocupacion_tutor": 1,
        })
        r = calcular_riesgo(peor)
        assert (r["puntaje"], r["indice"], r["nivel"]) == (39, 100.0, "Alto")
        assert len(r["dimensiones"]) == 6


# ---------------------------------------------------------------------------
# Escalamiento por amplitud y regla crítica
# ---------------------------------------------------------------------------
# Una señal mínima (1 punto) en cada dimensión, para tener poco índice y muchas dimensiones.
SENALES_MINIMAS = [
    ("llegadas_tarde", 5),           # Asistencia
    ("evaluaciones_ausente", 1),     # Rendimiento
    ("dias_sin_actividad", 7),       # Compromiso
    ("variacion_asistencia", -11),   # Tendencia
    ("materias_recursadas", 1),      # Trayectoria
]


def estudiante_con_senales(sano, cantidad):
    fila = dict(sano)
    for variable, valor in SENALES_MINIMAS[:cantidad]:
        fila[variable] = valor
    return calcular_riesgo(pd.Series(fila))


class TestEscalamiento:
    def test_dos_dimensiones_no_escalan(self, sano):
        r = estudiante_con_senales(sano, 2)
        assert len(r["dimensiones"]) == 2
        assert r["nivel"] == "Bajo" and r["nota"] == ""

    def test_tres_dimensiones_suben_a_medio_aunque_el_indice_sea_bajo(self, sano):
        r = estudiante_con_senales(sano, 3)
        assert r["indice"] < INDICE_MEDIO
        assert r["nivel"] == "Medio"
        assert "3 dimensiones" in r["nota"]

    def test_cuatro_dimensiones_siguen_en_medio_no_en_alto(self, sano):
        """Ajuste calibrado: 4 dimensiones NO alcanzan para Alto."""
        r = estudiante_con_senales(sano, 4)
        assert len(r["dimensiones"]) == 4
        assert r["nivel"] == "Medio"

    def test_cinco_dimensiones_suben_a_alto(self, sano):
        r = estudiante_con_senales(sano, 5)
        assert r["indice"] < INDICE_MEDIO
        assert r["nivel"] == "Alto"
        assert "5 dimensiones" in r["nota"]

    def test_regla_critica_en_tramo_grave_da_alto(self, sano):
        sano["inasistencias_consecutivas"] = 10
        r = calcular_riesgo(pd.Series(sano))
        assert r["indice"] < INDICE_MEDIO          # por puntos sería Bajo...
        assert r["nivel"] == "Alto"                # ...pero la regla crítica lo sube
        assert "regla crítica" in r["nota"]

    def test_regla_critica_en_tramo_leve_no_sube_el_nivel(self, sano):
        sano["inasistencias_consecutivas"] = 9
        assert calcular_riesgo(pd.Series(sano))["nivel"] == "Bajo"

    def test_una_regla_grave_no_critica_no_sube_el_nivel(self, sano):
        sano["asistencia_pct"] = 40  # R01 grave, pero no es crítica
        r = calcular_riesgo(pd.Series(sano))
        assert r["puntaje"] == 4 and r["nivel"] == "Bajo"


# ---------------------------------------------------------------------------
# Datos faltantes y "Sin datos suficientes"
# ---------------------------------------------------------------------------
class TestDatosFaltantes:
    def test_fila_vacia_es_sin_datos_suficientes(self):
        r = calcular_riesgo(pd.Series(dtype=float))
        assert r["nivel"] == "Sin datos suficientes"
        assert r["puntaje"] is None and r["indice"] is None and r["factores"] == []

    def test_sin_reglas_activas_es_sin_datos_suficientes(self, sano):
        assert calcular_riesgo(pd.Series(sano), [])["nivel"] == "Sin datos suficientes"

    def test_justo_50_por_ciento_de_cobertura_si_calcula(self):
        pares = [regla_simple("A", "a", 50), regla_simple("B", "b", 50)]
        r = calcular_riesgo(pd.Series({"a": 1}), pares)   # solo se evalúa A: 50/100
        assert r["nivel"] != "Sin datos suficientes"

    def test_menos_de_50_por_ciento_de_cobertura_no_calcula(self):
        pares = [regla_simple("A", "a", 49), regla_simple("B", "b", 51)]
        r = calcular_riesgo(pd.Series({"a": 1}), pares)   # 49/100
        assert r["nivel"] == "Sin datos suficientes"

    def test_valor_vacio_omite_la_regla_y_baja_el_maximo(self, sano):
        sano["promedio"] = float("nan")
        r = calcular_riesgo(pd.Series(sano))
        assert r["maximo"] == 35  # 39 menos los 4 puntos de R04
        assert r["nivel"] == "Bajo"

    def test_columna_ausente_no_deja_a_todos_sin_datos(self, sano):
        """Regresión: antes, con pocas variables TODOS quedaban 'sin datos'."""
        pocas = ["asistencia_pct", "promedio", "entregas_sin_presentar", "preocupacion_tutor"]
        df = pd.DataFrame([{k: sano[k] for k in pocas}])
        r = calcular_curso(df).iloc[0]
        assert r["nivel"] == "Bajo"
        assert r["maximo"] == 15  # R01(4) + R04(4) + R07(4) + R12(3)

    def test_con_pocas_columnas_el_calculo_directo_si_queda_sin_datos(self, sano):
        """Contraste: sin el filtro de calcular_curso la cobertura no alcanza."""
        pocas = ["asistencia_pct", "promedio", "entregas_sin_presentar", "preocupacion_tutor"]
        r = calcular_riesgo(pd.Series({k: sano[k] for k in pocas}))
        assert r["nivel"] == "Sin datos suficientes"


# ---------------------------------------------------------------------------
# Reglas activadas / desactivadas (HU-10)
# ---------------------------------------------------------------------------
class TestActivarDesactivar:
    def test_regla_desactivada_no_suma_ni_cuenta_en_el_maximo(self, sano):
        sano["asistencia_pct"] = 10          # dispararía R01 grave (4 puntos)
        copia = copiar_reglas()
        next(r for r in copia if r["id"] == "R01")["activa"] = False
        r = calcular_riesgo(pd.Series(sano), copia)
        assert r["puntaje"] == 0
        assert r["maximo"] == 35
        assert all(f["regla"] != "R01" for f in r["factores"])

    def test_copiar_reglas_no_modifica_el_original(self):
        copia = copiar_reglas()
        copia[0]["activa"] = False
        copia[0]["umbral_leve"] = 1
        assert REGLAS[0]["activa"] is True
        assert REGLAS[0]["umbral_leve"] == 75

    def test_se_puede_agregar_una_regla_nueva_sin_tocar_el_motor(self):
        nueva = regla_simple("R99", "falta_extra", 5)
        r = calcular_riesgo(pd.Series({"falta_extra": 3}), [nueva])
        assert r["puntaje"] == 5 and r["factores"][0]["regla"] == "R99"


# ---------------------------------------------------------------------------
# Desglose de factores (HU-05)
# ---------------------------------------------------------------------------
class TestDesglose:
    def test_cada_factor_trae_regla_dimension_puntos_y_texto(self, sano):
        sano["asistencia_pct"] = 58
        factor = calcular_riesgo(pd.Series(sano))["factores"][0]
        assert set(factor) == {"regla", "dimension", "puntos", "texto"}
        assert factor["regla"] == "R01" and factor["dimension"] == "Asistencia" and factor["puntos"] == 4

    def test_texto_de_regla_con_valor_menor(self, sano):
        sano["asistencia_pct"] = 58
        texto = calcular_riesgo(pd.Series(sano))["factores"][0]["texto"]
        assert texto == "Asistencia general: 58% (por debajo de 60%, tramo grave) → +4"

    def test_texto_de_regla_con_valor_mayor(self, sano):
        sano["inasistencias_consecutivas"] = 10
        texto = calcular_riesgo(pd.Series(sano))["factores"][0]["texto"]
        assert "10 días" in texto and "igual o mayor a 10 días" in texto and "tramo grave" in texto

    def test_texto_de_regla_binaria_no_muestra_umbral(self, sano):
        sano["preocupacion_tutor"] = 1
        factor = next(f for f in calcular_riesgo(pd.Series(sano))["factores"] if f["regla"] == "R12")
        assert factor["texto"] == "Preocupación registrada por el tutor → +3"

    def test_el_puntaje_es_la_suma_de_los_factores(self, curso_calculado):
        for _, fila in curso_calculado.iterrows():
            if fila["nivel"] != "Sin datos suficientes":
                assert fila["puntaje"] == sum(f["puntos"] for f in fila["factores"])


# ---------------------------------------------------------------------------
# calcular_curso (HU-03): columnas nuevas y datos originales intactos
# ---------------------------------------------------------------------------
class TestCalcularCurso:
    def test_agrega_las_columnas_de_riesgo(self, datos_ficticios):
        out = calcular_curso(datos_ficticios)
        for campo in ("puntaje", "maximo", "indice", "nivel", "dimensiones", "factores", "nota"):
            assert campo in out.columns
        assert len(out) == len(datos_ficticios)

    def test_no_modifica_el_dataframe_original(self, datos_ficticios):
        columnas_antes = list(datos_ficticios.columns)
        calcular_curso(datos_ficticios)
        assert list(datos_ficticios.columns) == columnas_antes

    def test_el_nivel_solo_toma_valores_validos(self, curso_calculado):
        validos = {"Bajo", "Medio", "Alto", "Sin datos suficientes"}
        assert set(curso_calculado["nivel"]) <= validos


# ---------------------------------------------------------------------------
# Regresión con el CSV ficticio: la "verdad conocida" documentada del proyecto
# ---------------------------------------------------------------------------
ESPERADO_CSV = {
    "A001": "Bajo", "A002": "Alto", "A003": "Bajo", "A004": "Medio", "A005": "Alto",
    "A006": "Bajo", "A007": "Bajo", "A008": "Alto", "A009": "Bajo", "A010": "Medio",
    "A011": "Bajo", "A012": "Bajo", "A013": "Alto", "A014": "Bajo", "A015": "Bajo",
    "A016": "Sin datos suficientes",
}


class TestRegresionCsvFicticio:
    def test_distribucion_4_alto_2_medio_9_bajo_1_sin_datos(self, curso_calculado):
        conteo = Counter(curso_calculado["nivel"])
        assert conteo == {"Alto": 4, "Medio": 2, "Bajo": 9, "Sin datos suficientes": 1}

    def test_nivel_de_cada_estudiante(self, curso_calculado):
        obtenido = dict(zip(curso_calculado["codigo"], curso_calculado["nivel"]))
        assert obtenido == ESPERADO_CSV

    @pytest.mark.parametrize("codigo, indice", [
        ("A002", 84.6), ("A005", 97.4), ("A008", 46.2), ("A013", 71.4), ("A004", 23.1), ("A010", 23.1),
    ])
    def test_indice_de_los_casos_mas_importantes(self, curso_calculado, codigo, indice):
        fila = curso_calculado[curso_calculado["codigo"] == codigo].iloc[0]
        assert fila["indice"] == pytest.approx(indice)

    def test_estudiante_con_columnas_vacias_evalua_menos_peso(self, curso_calculado):
        a011 = curso_calculado[curso_calculado["codigo"] == "A011"].iloc[0]
        assert a011["maximo"] == 28   # le faltan R01, R02 y R09 (4 + 4 + 3)

    def test_el_csv_ficticio_tiene_las_columnas_que_espera_el_sistema(self, datos_ficticios):
        import carga
        assert list(datos_ficticios.columns) == list(carga.CAMPOS)
        assert len(datos_ficticios) == 16
        assert datos_ficticios["codigo"].is_unique
