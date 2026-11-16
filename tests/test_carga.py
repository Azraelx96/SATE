"""Pruebas de la carga de datos (carga.py).  HU-01, HU-02 y HU-11 (mapeo sin IA).

Los archivos "sucios" se fabrican dentro de cada prueba: no hace falta guardar
planillas de ejemplo en el repositorio.
"""
import numpy as np
import pandas as pd
import pytest

import carga


# ---------------------------------------------------------------------------
# normalizar y columnas personales
# ---------------------------------------------------------------------------
class TestNormalizar:
    @pytest.mark.parametrize("original, esperado", [
        ("Asistencia (%)", "asistencia"),
        ("  Número de Legajo ", "numerodelegajo"),
        ("Días_sin_Actividad", "diassinactividad"),
        ("PROMEDIO", "promedio"),
        ("Año", "ano"),
        (None, "none"),
        (123, "123"),
    ])
    def test_normalizar(self, original, esperado):
        assert carga.normalizar(original) == esperado


class TestColumnasPersonales:
    def test_detecta_nombre_dni_mail_y_telefono(self):
        cols = ["Legajo", "Nombre", "DNI", "Correo electrónico", "Teléfono", "Asistencia", "Domicilio"]
        assert carga.columnas_personales(cols) == ["Nombre", "DNI", "Correo electrónico", "Teléfono", "Domicilio"]

    def test_las_columnas_academicas_no_son_personales(self):
        assert carga.columnas_personales(["Asistencia %", "Promedio", "Materias desaprobadas"]) == []


class TestDetectarColumnasIdentidad:
    def test_dni_nombre_y_apellido_separados(self):
        r = carga.detectar_columnas_identidad(["Legajo", "DNI", "Nombre", "Apellido", "Asistencia"])
        assert r == {"dni": "DNI", "nombre": "Nombre", "apellido": "Apellido", "nombre_completo": None}

    def test_columna_combinada_apellido_y_nombre(self):
        r = carga.detectar_columnas_identidad(["Apellido y Nombre", "Documento"])
        assert r["nombre_completo"] == "Apellido y Nombre"
        assert r["dni"] == "Documento"

    @pytest.mark.parametrize("columna", ["DNI", "dni", "D.N.I.", "Nº DNI", "Documento", "Número de documento"])
    def test_variantes_de_dni(self, columna):
        assert carga.detectar_columnas_identidad([columna])["dni"] == columna

    def test_sin_columnas_personales_devuelve_todo_none(self):
        r = carga.detectar_columnas_identidad(["Legajo", "Asistencia", "Promedio"])
        assert r == {"dni": None, "nombre": None, "apellido": None, "nombre_completo": None}


# ---------------------------------------------------------------------------
# sugerir_mapeo (reconocimiento de columnas sin IA)
# ---------------------------------------------------------------------------
class TestSugerirMapeo:
    def test_reconoce_los_nombres_estandar_del_sistema(self):
        mapeo = carga.sugerir_mapeo(list(carga.CAMPOS))
        assert mapeo == {campo: campo for campo in carga.CAMPOS}

    def test_reconoce_nombres_habituales_de_un_instituto(self):
        columnas = ["Legajo", "Apellido y Nombre", "DNI", "Asistencia %", "Promedio general",
                    "Entregas pendientes", "Materias desaprobadas", "Inasistencias"]
        m = carga.sugerir_mapeo(columnas)
        assert m["codigo"] == "Legajo"
        assert m["asistencia_pct"] == "Asistencia %"
        assert m["promedio"] == "Promedio general"
        assert m["entregas_sin_presentar"] == "Entregas pendientes"
        assert m["materias_desaprobadas"] == "Materias desaprobadas"

    def test_lo_que_no_encuentra_queda_en_none(self):
        m = carga.sugerir_mapeo(["Legajo", "Asistencia"])
        assert m["promedio"] is None and m["llegadas_tarde"] is None

    def test_nunca_asigna_una_columna_personal(self):
        m = carga.sugerir_mapeo(["Nombre", "DNI", "Apellido", "Asistencia"])
        assert m["codigo"] is None
        assert "Nombre" not in m.values() and "DNI" not in m.values()

    def test_inasistencias_no_se_confunde_con_asistencia(self):
        m = carga.sugerir_mapeo(["Inasistencias totales"])
        assert m["asistencia_pct"] is None

    def test_nota_sola_se_interpreta_como_promedio(self):
        assert carga.sugerir_mapeo(["Nota"])["promedio"] == "Nota"

    def test_una_columna_no_se_asigna_a_dos_campos(self):
        m = carga.sugerir_mapeo(["Legajo", "Asistencia", "Promedio", "Caída de asistencia", "Tutor"])
        usadas = [c for c in m.values() if c]
        assert len(usadas) == len(set(usadas))

    def test_variacion_se_distingue_del_valor_base(self):
        m = carga.sugerir_mapeo(["Asistencia", "Variación de asistencia", "Promedio", "Variación de promedio"])
        assert m["asistencia_pct"] == "Asistencia"
        assert m["variacion_asistencia"] == "Variación de asistencia"
        assert m["promedio"] == "Promedio"
        assert m["variacion_promedio"] == "Variación de promedio"


# ---------------------------------------------------------------------------
# leer_archivo (HU-01): CSV, Excel, separadores y codificaciones
# ---------------------------------------------------------------------------
class TestLeerArchivo:
    def test_csv_con_comas(self, archivo_falso):
        df = carga.leer_archivo(archivo_falso("a.csv", "codigo,asistencia\nA1,80\nA2,70\n"))
        assert list(df.columns) == ["codigo", "asistencia"] and len(df) == 2

    def test_csv_con_punto_y_coma(self, archivo_falso):
        df = carga.leer_archivo(archivo_falso("a.csv", "codigo;asistencia\nA1;80\n"))
        assert list(df.columns) == ["codigo", "asistencia"]

    def test_csv_con_tabuladores(self, archivo_falso):
        df = carga.leer_archivo(archivo_falso("a.csv", "codigo\tasistencia\nA1\t80\n"))
        assert list(df.columns) == ["codigo", "asistencia"]

    def test_csv_con_decimales_con_coma_se_lee_como_texto_y_se_limpia_despues(self, archivo_falso):
        df = carga.leer_archivo(archivo_falso("a.csv", "codigo;promedio\nA1;7,5\nA2;6,5\n"))
        assert df["promedio"].tolist() == ["7,5", "6,5"]

    def test_csv_en_latin1_con_acentos(self, archivo_falso):
        contenido = "Apellido;Asistencia\nPérez;80\nGómez;70\n".encode("latin-1")
        df = carga.leer_archivo(archivo_falso("a.csv", contenido))
        assert df["Apellido"].tolist() == ["Pérez", "Gómez"]

    def test_csv_utf8_con_bom_no_ensucia_el_primer_nombre_de_columna(self, archivo_falso):
        contenido = "﻿codigo,asistencia\nA1,80\n".encode("utf-8")
        assert list(carga.leer_archivo(archivo_falso("a.csv", contenido)).columns) == ["codigo", "asistencia"]

    def test_los_nombres_de_columna_se_recortan(self, archivo_falso):
        df = carga.leer_archivo(archivo_falso("a.csv", " codigo , asistencia \nA1,80\n"))
        assert list(df.columns) == ["codigo", "asistencia"]

    def test_excel_xlsx(self, archivo_falso, excel_en_bytes):
        original = pd.DataFrame({"codigo": ["A1", "A2"], "asistencia": [80, 70]})
        df = carga.leer_archivo(archivo_falso("curso.xlsx", excel_en_bytes(original)))
        assert df["codigo"].tolist() == ["A1", "A2"]

    def test_la_extension_en_mayusculas_tambien_es_excel(self, archivo_falso, excel_en_bytes):
        original = pd.DataFrame({"codigo": ["A1"], "asistencia": [80]})
        df = carga.leer_archivo(archivo_falso("CURSO.XLSX", excel_en_bytes(original)))
        assert len(df) == 1

    def test_archivo_vacio_da_error_en_lugar_de_colgarse(self, archivo_falso):
        with pytest.raises(Exception):
            carga.leer_archivo(archivo_falso("vacio.csv", b""))

    def test_csv_solo_con_encabezados_devuelve_cero_filas(self, archivo_falso):
        df = carga.leer_archivo(archivo_falso("a.csv", "codigo,asistencia\n"))
        assert len(df) == 0


# ---------------------------------------------------------------------------
# Conversión de valores
# ---------------------------------------------------------------------------
class TestAUnNumero:
    def test_porcentaje_coma_decimal_y_vacios(self):
        serie = pd.Series(["85%", "7,5", "-", "s/d", "", "N/A", "10"])
        num, invalidos = carga._a_numero(serie)
        assert num.iloc[0] == 85 and num.iloc[1] == 7.5 and num.iloc[6] == 10
        assert num.iloc[2:6].isna().all()
        assert invalidos == 0  # los marcadores de "sin dato" no cuentan como error

    def test_texto_no_interpretable_se_cuenta_como_invalido(self):
        num, invalidos = carga._a_numero(pd.Series(["ocho", "9"]))
        assert pd.isna(num.iloc[0]) and num.iloc[1] == 9
        assert invalidos == 1


class TestABinario:
    @pytest.mark.parametrize("texto", ["Sí", "si", "S", "yes", "TRUE", "verdadero", "1", "x", "X"])
    def test_valores_que_significan_si(self, texto):
        valor, _ = carga._a_binario(pd.Series([texto]))
        assert valor.iloc[0] == 1.0

    @pytest.mark.parametrize("texto", ["No", "n", "false", "Falso", "0"])
    def test_valores_que_significan_no(self, texto):
        valor, _ = carga._a_binario(pd.Series([texto]))
        assert valor.iloc[0] == 0.0

    def test_vacio_queda_vacio_sin_contar_como_error(self):
        valor, invalidos = carga._a_binario(pd.Series(["", None]))
        assert valor.isna().all() and invalidos == 0

    def test_texto_ambiguo_queda_vacio_y_se_cuenta_como_error(self):
        valor, invalidos = carga._a_binario(pd.Series(["quizás"]))
        assert pd.isna(valor.iloc[0]) and invalidos == 1

    def test_numeros_de_excel_1_y_0(self):
        valor, _ = carga._a_binario(pd.Series([1.0, 0.0]))
        assert valor.tolist() == [1.0, 0.0]


# ---------------------------------------------------------------------------
# limpiar (HU-01)
# ---------------------------------------------------------------------------
def limpio(df, mapeo, **kw):
    return carga.limpiar(df, mapeo, **kw)


class TestLimpiar:
    def test_archivo_limpio_no_genera_avisos(self):
        crudo = pd.DataFrame({"cod": ["A1", "A2"], "asis": [80, 70], "prom": [7.5, 6.0]})
        out, avisos = limpio(crudo, {"codigo": "cod", "asistencia_pct": "asis", "promedio": "prom"})
        assert avisos == []
        assert out["codigo"].tolist() == ["A1", "A2"]
        assert out["asistencia_pct"].tolist() == [80, 70]

    def test_solo_conserva_las_columnas_mapeadas(self):
        """Minimización de datos: nombre y DNI no pasan al DataFrame de análisis."""
        crudo = pd.DataFrame({"cod": ["A1"], "Nombre": ["Ana"], "DNI": ["30111222"], "asis": [80]})
        out, _ = limpio(crudo, {"codigo": "cod", "asistencia_pct": "asis"})
        assert list(out.columns) == ["codigo", "asistencia_pct"]

    def test_porcentajes_y_comas_decimales(self):
        crudo = pd.DataFrame({"cod": ["A1", "A2"], "asis": ["85,5%", "70%"], "prom": ["7,5", "6,25"]})
        out, avisos = limpio(crudo, {"codigo": "cod", "asistencia_pct": "asis", "promedio": "prom"})
        assert out["asistencia_pct"].tolist() == [85.5, 70.0]
        assert out["promedio"].tolist() == [7.5, 6.25]

    def test_asistencia_entre_0_y_1_se_convierte_a_porcentaje(self):
        crudo = pd.DataFrame({"cod": ["A1", "A2"], "asis": [0.8, 0.95]})
        out, avisos = limpio(crudo, {"codigo": "cod", "asistencia_pct": "asis"})
        assert out["asistencia_pct"].tolist() == pytest.approx([80, 95])
        assert any("proporción" in a for a in avisos)

    @pytest.mark.parametrize("campo, valores, columna_mapeo", [
        ("asistencia_pct", [150, 80], "asis"),
        ("asistencia_pct", [-5, 80], "asis"),
        ("promedio", [11, 7], "prom"),
        ("promedio", [-1, 7], "prom"),
        ("llegadas_tarde", [-3, 2], "tarde"),
    ])
    def test_valores_fuera_de_rango_se_dejan_vacios(self, campo, valores, columna_mapeo):
        crudo = pd.DataFrame({"cod": ["A1", "A2"], columna_mapeo: valores})
        out, avisos = limpio(crudo, {"codigo": "cod", campo: columna_mapeo})
        assert pd.isna(out[campo].iloc[0]) and out[campo].iloc[1] == valores[1]
        assert any("fuera de rango" in a for a in avisos)

    def test_no_se_inventan_valores_donde_la_celda_esta_vacia(self):
        crudo = pd.DataFrame({"cod": ["A1", "A2"], "asis": ["80", ""]})
        out, _ = limpio(crudo, {"codigo": "cod", "asistencia_pct": "asis"})
        assert pd.isna(out["asistencia_pct"].iloc[1])

    def test_identificadores_repetidos_se_descartan_conservando_el_primero(self):
        crudo = pd.DataFrame({"cod": ["A1", "A1", "A2"], "asis": [80, 10, 70]})
        out, avisos = limpio(crudo, {"codigo": "cod", "asistencia_pct": "asis"})
        assert out["codigo"].tolist() == ["A1", "A2"]
        assert out["asistencia_pct"].tolist() == [80, 70]
        assert any("repetido" in a for a in avisos)

    def test_filas_sin_identificador_se_descartan(self):
        crudo = pd.DataFrame({"cod": ["A1", "", None, "A2"], "asis": [80, 60, 50, 70]})
        out, avisos = limpio(crudo, {"codigo": "cod", "asistencia_pct": "asis"})
        assert out["codigo"].tolist() == ["A1", "A2"]
        assert any("sin identificador" in a for a in avisos)

    def test_codigos_numericos_quedan_como_texto_sin_decimales(self):
        crudo = pd.DataFrame({"cod": [101, 102.0, np.nan], "asis": [80, 70, 60]})
        out, _ = limpio(crudo, {"codigo": "cod", "asistencia_pct": "asis"})
        assert out["codigo"].tolist() == ["101", "102"]

    def test_generar_codigos_automaticos(self):
        crudo = pd.DataFrame({"asis": [80, 70, 60]})
        out, avisos = limpio(crudo, {"asistencia_pct": "asis"}, generar_codigos=True)
        assert out["codigo"].tolist() == ["E001", "E002", "E003"]
        assert any("códigos automáticos" in a for a in avisos)

    def test_sin_columna_de_codigo_tambien_genera_codigos(self):
        crudo = pd.DataFrame({"asis": [80, 70]})
        out, _ = limpio(crudo, {"asistencia_pct": "asis"})
        assert out["codigo"].tolist() == ["E001", "E002"]

    def test_columna_sin_ningun_valor_valido_se_omite_con_aviso(self):
        crudo = pd.DataFrame({"cod": ["A1", "A2"], "asis": [80, 70], "prom": ["s/d", "-"]})
        out, avisos = limpio(crudo, {"codigo": "cod", "asistencia_pct": "asis", "promedio": "prom"})
        assert "promedio" not in out.columns
        assert any("se omitió" in a for a in avisos)

    def test_texto_no_interpretable_se_avisa(self):
        crudo = pd.DataFrame({"cod": ["A1", "A2"], "prom": ["ocho", "7"]})
        out, avisos = limpio(crudo, {"codigo": "cod", "promedio": "prom"})
        assert pd.isna(out["promedio"].iloc[0]) and out["promedio"].iloc[1] == 7
        assert any("no interpretables" in a for a in avisos)

    def test_preocupacion_del_tutor_se_convierte_a_1_y_0(self):
        crudo = pd.DataFrame({"cod": ["A1", "A2", "A3"], "tut": ["Sí", "No", ""]})
        out, _ = limpio(crudo, {"codigo": "cod", "preocupacion_tutor": "tut"})
        assert out["preocupacion_tutor"].iloc[:2].tolist() == [1.0, 0.0]
        assert pd.isna(out["preocupacion_tutor"].iloc[2])

    def test_el_indice_del_resultado_arranca_en_cero_aunque_se_descarten_filas(self):
        crudo = pd.DataFrame({"cod": ["", "A1", "A2"], "asis": [1, 80, 70]})
        out, _ = limpio(crudo, {"codigo": "cod", "asistencia_pct": "asis"})
        assert list(out.index) == [0, 1]

    def test_el_resultado_se_puede_usar_directamente_en_el_motor_de_reglas(self):
        from reglas import calcular_curso
        crudo = pd.DataFrame({"cod": ["A1", "A2"], "asis": ["95%", "40%"], "prom": ["8,5", "3,5"],
                              "ent": [0, 5]})
        out, _ = limpio(crudo, {"codigo": "cod", "asistencia_pct": "asis", "promedio": "prom",
                                "entregas_sin_presentar": "ent"})
        niveles = calcular_curso(out)["nivel"].tolist()
        assert niveles == ["Bajo", "Alto"]


# ---------------------------------------------------------------------------
# limpiar_con_identidades (HU-02): quién es quién, sin mezclar datos personales
# ---------------------------------------------------------------------------
class TestLimpiarConIdentidades:
    def crudo(self):
        return pd.DataFrame({
            "Legajo": ["A1", "A2"],
            "DNI": [30111222, 30333444],
            "Nombre": ["Ana", "Luis"],
            "Apellido": ["Pérez", "Gómez"],
            "Asistencia": [80, 70],
        })

    def test_devuelve_una_identidad_por_fila_alineada(self):
        out, avisos, ident = carga.limpiar_con_identidades(
            self.crudo(), {"codigo": "Legajo", "asistencia_pct": "Asistencia"})
        assert len(ident) == len(out) == 2
        assert [i["codigo_origen"] for i in ident] == ["A1", "A2"]
        assert [int(i["dni"]) for i in ident] == [30111222, 30333444]
        assert (ident[0]["nombre"], ident[0]["apellido"]) == ("Ana", "Pérez")

    def test_los_datos_personales_no_pasan_al_dataframe_de_analisis(self):
        out, _, _ = carga.limpiar_con_identidades(
            self.crudo(), {"codigo": "Legajo", "asistencia_pct": "Asistencia"})
        assert list(out.columns) == ["codigo", "asistencia_pct"]

    def test_columna_combinada_apellido_y_nombre(self):
        crudo = pd.DataFrame({"Legajo": ["A1"], "Apellido y Nombre": ["Pérez, Ana"], "Asistencia": [80]})
        _, _, ident = carga.limpiar_con_identidades(crudo, {"codigo": "Legajo", "asistencia_pct": "Asistencia"})
        assert ident[0]["nombre"] == "Pérez, Ana" and ident[0]["apellido"] is None

    def test_sin_columnas_personales_las_identidades_solo_traen_el_codigo(self):
        crudo = pd.DataFrame({"Legajo": ["A1"], "Asistencia": [80]})
        _, _, ident = carga.limpiar_con_identidades(crudo, {"codigo": "Legajo", "asistencia_pct": "Asistencia"})
        assert ident == [{"codigo_origen": "A1", "dni": None, "nombre": None, "apellido": None}]

    def test_celdas_personales_vacias_quedan_en_none(self):
        crudo = pd.DataFrame({"Legajo": ["A1"], "DNI": [np.nan], "Nombre": [None], "Asistencia": [80]})
        _, _, ident = carga.limpiar_con_identidades(crudo, {"codigo": "Legajo", "asistencia_pct": "Asistencia"})
        assert ident[0]["dni"] is None and ident[0]["nombre"] is None

    def test_si_se_descartan_filas_las_identidades_siguen_alineadas(self):
        """Regresión: filas repetidas o vacías no deben desfasar los DNI."""
        crudo = pd.DataFrame({
            "Legajo": ["A1", "", "A1", "A2"],
            "DNI": [1, 2, 3, 4],
            "Asistencia": [80, 70, 60, 50],
        })
        out, _, ident = carga.limpiar_con_identidades(crudo, {"codigo": "Legajo", "asistencia_pct": "Asistencia"})
        assert out["codigo"].tolist() == ["A1", "A2"]
        assert [int(i["dni"]) for i in ident] == [1, 4]
        assert [i["codigo_origen"] for i in ident] == ["A1", "A2"]

    def test_con_codigos_automaticos_cada_identidad_lleva_su_codigo(self):
        crudo = pd.DataFrame({"DNI": [10, 20], "Asistencia": [80, 70]})
        out, _, ident = carga.limpiar_con_identidades(crudo, {"asistencia_pct": "Asistencia"},
                                                      generar_codigos=True)
        assert [i["codigo_origen"] for i in ident] == ["E001", "E002"]
        assert [int(i["dni"]) for i in ident] == [10, 20]
