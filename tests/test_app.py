"""Pruebas de la interfaz (app.py), sin abrir el navegador.  HU-01 a HU-06, HU-08, HU-10, HU-12 y HU-13.

Usan AppTest, el simulador que trae Streamlit: "abre" la aplicación en memoria,
hace clic, escribe y lee lo que aparece en pantalla.

La base de datos es temporal (conftest.py) y la IA está simulada: nada de esto
toca datos reales ni necesita Ollama.
"""
import json
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import almacenamiento
import ia

DATOS_EJEMPLO = "Datos de ejemplo (ficticios)"
SUBIR_ARCHIVO = "Subir mi archivo (CSV o Excel)"


# ---------------------------------------------------------------------------
# Preparación
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _entorno_de_la_app(raiz, monkeypatch):
    """La app lee datos/alumnos_ficticios.csv con ruta relativa: hay que estar en la raíz."""
    monkeypatch.chdir(raiz)
    st.cache_data.clear()                         # la app recuerda 10 s si hay IA: se borra
    monkeypatch.setattr(ia, "disponible", lambda: False)   # por defecto, sin IA
    yield
    st.cache_data.clear()


@pytest.fixture
def con_ia(monkeypatch):
    """Simula Ollama disponible. Devuelve la lista de lo que la app le envió."""
    enviados = {"orientacion": [], "resumen": []}

    def devolucion(paquete):
        enviados["orientacion"].append(paquete)
        return enviados.get("respuesta", "Conviene acompañar su asistencia esta semana.")

    def redactar_resumen(agregados):
        enviados["resumen"].append(agregados)
        return "Resumen institucional de prueba."

    monkeypatch.setattr(ia, "disponible", lambda: True)
    monkeypatch.setattr(ia, "devolucion", devolucion)
    monkeypatch.setattr(ia, "redactar_resumen", redactar_resumen)
    st.cache_data.clear()
    return enviados


RUTA_APP = str(Path(__file__).resolve().parent.parent / "app.py")


def abrir():
    return AppTest.from_file(RUTA_APP, default_timeout=60).run()


def metricas(at):
    return {m.label.split(" ", 1)[1]: int(m.value) for m in at.metric}


def elegir_ficha(at, codigo):
    caja = next(s for s in at.selectbox if s.label.startswith("Elegí un código"))
    return caja.select(codigo).run()


def caja_ficha(at):
    return next(s for s in at.selectbox if s.label.startswith("Elegí un código"))


def legajo_de(codigo, origen=""):
    return next(a["legajo"] for a in almacenamiento.listar_alumnos()
                if a["codigo_origen"] == codigo and a["origen"] == origen)


def boton(at, etiqueta):
    return next(b for b in at.button if b.label == etiqueta)


def guardar_observacion(at, texto, preocupacion):
    chk = next(c for c in at.checkbox if c.label.startswith("Registrar preocupación"))
    (chk.check() if preocupacion else chk.uncheck())
    at.text_area[0].set_value(texto)
    return boton(at, "Guardar observación").click().run()


def textos_markdown(at):
    return "\n".join(m.value for m in at.markdown)


# ---------------------------------------------------------------------------
# Arranque y panel del curso (HU-03 y HU-04)
# ---------------------------------------------------------------------------
class TestArranque:
    def test_la_app_arranca_sin_errores(self):
        at = abrir()
        assert not at.exception
        assert at.title[0].value == "SATE — Sistema de Alerta Temprana de Abandono"

    def test_tiene_las_tres_pestanas(self):
        assert [t.label for t in abrir().tabs] == [
            "1. Cargar datos", "2. Panel del curso", "3. Resumen para autoridades"]

    def test_usa_por_defecto_los_datos_de_ejemplo(self):
        at = abrir()
        assert at.radio[0].value == DATOS_EJEMPLO

    def test_los_16_estudiantes_quedan_identificados_con_legajo(self):
        at = abrir()
        assert any("16 estudiantes de esta carga identificados" in c.value for c in at.caption)
        assert len(almacenamiento.listar_alumnos()) == 16

    def test_el_aviso_de_que_es_una_ayuda_y_no_una_decision_esta_visible(self):
        textos = " ".join(c.value for c in abrir().caption)
        assert "no una decisión" in textos and "la IA no lo decide" in textos


class TestPanel:
    def test_los_contadores_por_nivel(self):
        assert metricas(abrir()) == {"Alto": 4, "Medio": 2, "Bajo": 9, "Sin datos suficientes": 1}

    def panel(self, at):
        return next(d.value for d in at.dataframe if "Legajo" in d.value.columns)

    def test_el_listado_tiene_a_los_16_con_las_columnas_esperadas(self):
        tabla = self.panel(abrir())
        assert list(tabla.columns) == ["Legajo", "Código", "Nivel", "Índice (0-100)",
                                       "Dimensiones con alerta", "Obs."]
        assert len(tabla) == 16

    def test_ordenado_de_mayor_a_menor_riesgo(self):
        tabla = self.panel(abrir())
        assert tabla["Código"].iloc[0] == "A005"           # el de mayor índice
        assert tabla["Nivel"].iloc[0].endswith("Alto")
        assert tabla["Código"].iloc[-1] == "A016"          # "Sin datos" al final
        niveles = [n.split(" ", 1)[1] for n in tabla["Nivel"]]
        orden = {"Alto": 0, "Medio": 1, "Bajo": 2, "Sin datos suficientes": 3}
        assert [orden[n] for n in niveles] == sorted(orden[n] for n in niveles)

    @pytest.mark.parametrize("nivel, cantidad", [("Alto", 4), ("Medio", 2), ("Bajo", 9),
                                                 ("Sin datos suficientes", 1)])
    def test_filtrar_por_nivel(self, nivel, cantidad):
        at = abrir()
        filtro = next(r for r in at.radio if r.label == "Filtrar por nivel")
        filtro.set_value(nivel).run()
        tabla = self.panel(at)
        assert len(tabla) == cantidad
        assert all(n.endswith(nivel) for n in tabla["Nivel"])

    def test_el_listado_no_muestra_nombres_ni_dni(self):
        tabla = self.panel(abrir())
        assert not {"Nombre", "Apellido", "DNI"} & set(tabla.columns)


# ---------------------------------------------------------------------------
# Ficha de estudiante y desglose (HU-05)
# ---------------------------------------------------------------------------
class TestFicha:
    def test_la_ficha_arranca_con_el_estudiante_de_mayor_riesgo(self):
        assert caja_ficha(abrir()).value == "A005"

    def test_muestra_nivel_puntaje_y_factores_con_su_umbral(self):
        at = abrir()
        elegir_ficha(at, "A002")
        md = textos_markdown(at)
        assert "### A002 — 🔴 Alto" in md
        assert "Puntaje 33 de 39 evaluables → índice 84.6" in md
        assert "Asistencia general: 58% (por debajo de 60%, tramo grave) → +4" in md

    def test_agrupa_los_factores_por_dimension(self):
        at = abrir()
        elegir_ficha(at, "A002")
        md = textos_markdown(at)
        for dimension in ("**Asistencia**", "**Rendimiento**", "**Compromiso**"):
            assert dimension in md

    def test_estudiante_sin_alertas_lo_dice(self):
        at = abrir()
        elegir_ficha(at, "A001")
        assert "Ninguna regla se activó." in textos_markdown(at)

    def test_estudiante_sin_datos_suficientes_muestra_la_nota(self):
        at = abrir()
        elegir_ficha(at, "A016")
        assert "Faltan datos para calcular el riesgo." in [i.value for i in at.info]

    def test_muestra_el_legajo_permanente(self):
        at = abrir()
        elegir_ficha(at, "A002")
        assert any(c.value.startswith(f"Legajo {legajo_de('A002')}") for c in at.caption)


# ---------------------------------------------------------------------------
# Reglas activas (HU-10)
# ---------------------------------------------------------------------------
class TestReglasActivas:
    def test_hay_12_reglas_y_todas_empiezan_activas(self):
        at = abrir()
        assert [c.key for c in at.sidebar.checkbox] == [f"R{i:02d}" for i in range(1, 13)]
        assert all(c.value for c in at.sidebar.checkbox)

    def test_desactivar_una_regla_la_saca_del_calculo(self):
        at = abrir()
        elegir_ficha(at, "A008")
        assert "Puntaje 18 de 39 evaluables" in textos_markdown(at)
        at.sidebar.checkbox(key="R12").uncheck().run()          # sin la preocupación del tutor
        assert not at.exception
        # R12 sumaba 3 puntos y pesaba 3 en el máximo: ahora son 15 de 36.
        assert "Puntaje 15 de 36 evaluables" in textos_markdown(at)
        tabla_reglas = next(d.value for d in at.dataframe if "Regla" in d.value.columns)
        assert tabla_reglas.loc[tabla_reglas["ID"] == "R12", "Activa"].iloc[0] == "no"

    def test_sin_ninguna_regla_activa_todos_quedan_sin_datos_suficientes(self):
        at = abrir()
        for chk in at.sidebar.checkbox:
            chk.uncheck()
        at.run()
        assert metricas(at) == {"Alto": 0, "Medio": 0, "Bajo": 0, "Sin datos suficientes": 16}

    def test_la_tabla_de_reglas_muestra_umbrales_y_reglas_criticas(self):
        at = abrir()
        t = next(d.value for d in at.dataframe if "Regla" in d.value.columns)
        assert len(t) == 12
        assert t.loc[t["ID"] == "R02", "Crítica"].iloc[0] == "sí"
        assert t.loc[t["ID"] == "R01", "Leve"].iloc[0] == 75


# ---------------------------------------------------------------------------
# Observaciones del docente (HU-08 y HU-13)
# ---------------------------------------------------------------------------
class TestObservaciones:
    def test_guardar_una_observacion_la_persiste_en_la_base(self):
        at = abrir()
        elegir_ficha(at, "A010")
        guardar_observacion(at, "Conversar sobre las entregas.", preocupacion=False)
        guardada = almacenamiento.obtener_observacion(legajo_de("A010"))
        assert guardada["observacion"] == "Conversar sobre las entregas."
        assert guardada["preocupacion_tutor"] is False

    def test_muestra_el_mensaje_de_confirmacion(self):
        at = abrir()
        elegir_ficha(at, "A010")
        guardar_observacion(at, "Nota.", preocupacion=False)
        assert any(f"Observación de {legajo_de('A010')} guardada." in s.value for s in at.success)

    def test_la_ficha_no_salta_a_otro_estudiante_al_guardar(self):
        """Regresión: al guardar cambiaba el orden de la lista y la ficha saltaba."""
        at = abrir()
        elegir_ficha(at, "A010")
        # La preocupación sube el índice de A010 (Medio → Alto) y reordena el panel.
        guardar_observacion(at, "Seguimiento semanal.", preocupacion=True)
        assert caja_ficha(at).value == "A010"
        assert "### A010 — 🔴 Alto" in textos_markdown(at)

    def test_marcar_preocupacion_suma_a_la_regla_R12_y_sube_el_semaforo(self):
        at = abrir()
        antes = metricas(at)
        elegir_ficha(at, "A007")                              # Bajo, con 3 puntos
        guardar_observacion(at, "", preocupacion=True)        # +3 de R12 → Medio
        despues = metricas(at)
        assert despues["Medio"] == antes["Medio"] + 1
        assert despues["Bajo"] == antes["Bajo"] - 1

    def test_desmarcar_la_preocupacion_la_quita_del_calculo(self):
        at = abrir()
        elegir_ficha(at, "A007")
        guardar_observacion(at, "", preocupacion=True)
        guardar_observacion(at, "", preocupacion=False)
        assert metricas(at)["Medio"] == 2

    def test_la_observacion_de_un_estudiante_no_aparece_en_otro(self):
        at = abrir()
        elegir_ficha(at, "A010")
        guardar_observacion(at, "Solo para A010.", preocupacion=True)
        elegir_ficha(at, "A001")                              # A001 no tiene preocupación en el archivo
        assert at.text_area[0].value == ""
        assert next(c for c in at.checkbox if c.label.startswith("Registrar")).value is False

    def test_el_panel_marca_con_iconos_a_quienes_tienen_observacion(self):
        at = abrir()
        elegir_ficha(at, "A010")
        guardar_observacion(at, "Con nota.", preocupacion=True)
        tabla = next(d.value for d in at.dataframe if "Legajo" in d.value.columns)
        assert tabla.loc[tabla["Código"] == "A010", "Obs."].iloc[0] == "📝⚠"
        assert tabla.loc[tabla["Código"] == "A001", "Obs."].iloc[0] == ""

    def test_la_observacion_sobrevive_a_cerrar_y_volver_a_abrir_la_app(self):
        at = abrir()
        elegir_ficha(at, "A010")
        guardar_observacion(at, "Esto no se pierde.", preocupacion=False)
        nueva_sesion = abrir()
        elegir_ficha(nueva_sesion, "A010")
        assert nueva_sesion.text_area[0].value == "Esto no se pierde."

    def test_los_legajos_no_se_duplican_al_recargar(self):
        abrir()
        abrir()
        assert len(almacenamiento.listar_alumnos()) == 16


# ---------------------------------------------------------------------------
# Orientación con IA (HU-06)
# ---------------------------------------------------------------------------
class TestOrientacionConIA:
    def boton_orientacion(self, at):
        return next(b for b in at.button if b.label.startswith("✨ Generar orientación"))

    def test_sin_ia_el_boton_esta_deshabilitado_y_se_explica_por_que(self):
        at = abrir()
        assert self.boton_orientacion(at).disabled is True
        assert any("IA no disponible" in c.value for c in at.caption)

    def test_con_ia_el_boton_esta_habilitado_para_nivel_alto(self, con_ia):
        at = abrir()
        assert self.boton_orientacion(at).disabled is False

    @pytest.mark.parametrize("codigo", ["A001", "A016"])
    def test_para_nivel_bajo_o_sin_datos_el_boton_esta_deshabilitado(self, con_ia, codigo):
        at = abrir()
        elegir_ficha(at, codigo)
        assert self.boton_orientacion(at).disabled is True
        assert any("Medio o Alto" in c.value for c in at.caption)

    def test_para_nivel_medio_el_boton_esta_habilitado(self, con_ia):
        at = abrir()
        elegir_ficha(at, "A004")
        assert self.boton_orientacion(at).disabled is False

    def test_al_hacer_clic_muestra_el_texto_de_la_ia_con_su_aclaracion(self, con_ia):
        at = abrir()
        self.boton_orientacion(at).click().run()
        assert "Conviene acompañar su asistencia esta semana." in textos_markdown(at)
        assert any("decisión final es del tutor" in i.value for i in at.info)
        assert any(c.value.startswith("Modelo:") for c in at.caption)

    def test_a_la_ia_no_le_llegan_nombre_dni_legajo_ni_codigo(self, con_ia):
        at = abrir()
        elegir_ficha(at, "A002")
        self.boton_orientacion(at).click().run()
        enviado = json.dumps(con_ia["orientacion"], ensure_ascii=False)
        assert con_ia["orientacion"], "la IA debería haber recibido un paquete"
        for secreto in ("A002", legajo_de("A002"), "SATE-"):
            assert secreto not in enviado

    def test_si_el_texto_menciona_una_sancion_se_muestra_un_aviso(self, con_ia):
        con_ia["respuesta"] = "Habría que evaluar una sanción."
        at = abrir()
        self.boton_orientacion(at).click().run()
        assert any("una sanción" in w.value for w in at.warning)

    def test_si_la_ia_falla_el_desglose_de_reglas_sigue_disponible(self, con_ia, monkeypatch):
        """HU-06: 'Mantiene la explicación basada en reglas ante fallos'."""
        def falla(paquete):
            raise ConnectionError("Ollama se cayó")

        monkeypatch.setattr(ia, "devolucion", falla)
        at = abrir()
        self.boton_orientacion(at).click().run()
        assert not at.exception
        assert any("No se pudo generar la orientación" in e.value for e in at.error)
        assert "Asistencia general" in textos_markdown(at)     # el desglose sigue ahí


# ---------------------------------------------------------------------------
# Resumen para autoridades (HU-12)
# ---------------------------------------------------------------------------
class TestResumen:
    def test_muestra_las_cifras_agregadas(self):
        md = textos_markdown(abrir())
        assert "Se analizaron **16** estudiantes." in md
        assert "- **Alto:** 4 (25 %)" in md

    def test_ofrece_descargar_el_csv_y_advierte_que_es_informacion_sensible(self):
        at = abrir()
        assert len(at.get("download_button")) == 1
        assert any("información sensible" in w.value for w in at.warning)

    def test_sin_ia_explica_como_activarla(self):
        at = abrir()
        assert any("iniciá Ollama" in i.value for i in at.info)

    def test_con_ia_redacta_el_resumen_enviando_solo_cifras_agregadas(self, con_ia):
        at = abrir()
        boton(at, "✨ Redactar resumen con IA").click().run()
        assert "Resumen institucional de prueba." in textos_markdown(at)
        enviado = con_ia["resumen"][0]
        assert enviado["total_estudiantes"] == 16
        assert not any(f"A0{i:02d}" in json.dumps(enviado) for i in range(1, 17))

    def test_si_la_ia_falla_al_redactar_el_resumen_no_se_rompe_la_app(self, con_ia, monkeypatch):
        def falla(agregados):
            raise TimeoutError("demasiado lento")

        monkeypatch.setattr(ia, "redactar_resumen", falla)
        at = abrir()
        boton(at, "✨ Redactar resumen con IA").click().run()
        assert not at.exception
        assert any("No se pudo usar la IA" in e.value for e in at.error)


# ---------------------------------------------------------------------------
# Carga de un archivo propio (HU-01 y HU-02), de punta a punta
# ---------------------------------------------------------------------------
CSV_CURSO = (
    "Legajo;DNI;Apellido y Nombre;Asistencia %;Promedio general;Entregas pendientes\n"
    "L1;30111222;Pérez Ana;55;4,0;5\n"
    "L2;30333444;Gómez Luis;95;8,5;0\n"
    "L3;30555666;Díaz Eva;80;7;1\n"
).encode("utf-8")


def subir(nombre="curso1.csv", contenido=CSV_CURSO):
    at = abrir()
    at.radio[0].set_value(SUBIR_ARCHIVO).run()
    at.file_uploader[0].upload(nombre, contenido).run()
    return at


class TestCargaDeArchivo:
    def test_sin_archivo_las_otras_pestanas_piden_cargar_datos(self):
        at = abrir()
        at.radio[0].set_value(SUBIR_ARCHIVO).run()
        assert not at.exception
        assert [i.value for i in at.info].count("Primero cargá los datos en la pestaña 1.") == 2

    def test_lee_el_archivo_y_propone_el_mapeo_de_columnas(self):
        at = subir()
        assert not at.exception
        assert any("Archivo leído: 3 filas y 6 columnas." in s.value for s in at.success)
        assert at.selectbox(key="map_codigo").value == "Legajo"
        assert at.selectbox(key="map_asistencia_pct").value == "Asistencia %"
        assert at.selectbox(key="map_promedio").value == "Promedio general"
        assert at.selectbox(key="map_entregas_sin_presentar").value == "Entregas pendientes"

    def test_calcula_el_riesgo_con_los_datos_del_archivo(self):
        at = subir()
        assert metricas(at) == {"Alto": 1, "Medio": 0, "Bajo": 2, "Sin datos suficientes": 0}

    def test_avisa_que_columnas_son_datos_personales(self):
        at = subir()
        aviso = next(w.value for w in at.warning if "datos personales" in w.value)
        assert "DNI" in aviso and "Apellido y Nombre" in aviso and "no entran al cálculo" in aviso

    def test_la_vista_previa_solo_muestra_columnas_mapeadas(self):
        at = subir()
        vista = next(d.value for d in at.dataframe if "asistencia_pct" in d.value.columns)
        assert not {"DNI", "Apellido y Nombre"} & set(vista.columns)

    def test_guarda_dni_y_nombre_en_la_base_para_reconocer_al_estudiante(self):
        subir()
        ficha = almacenamiento.obtener_alumno_por_legajo(legajo_de("L1", origen="curso1"))
        assert ficha["dni_normalizado"] == "30111222"
        assert ficha["nombre"] == "Pérez Ana"

    def test_usa_el_nombre_del_archivo_como_curso(self):
        at = subir("tercero_b.csv")
        assert at.text_input[0].value == "tercero_b"

    def test_el_mismo_dni_en_otro_archivo_es_el_mismo_legajo(self):
        subir("curso1.csv")
        antes = len(almacenamiento.listar_alumnos())
        otro = CSV_CURSO.replace(b"L1;", b"ZZ;")       # cambia el código, no el DNI
        subir("curso2.csv", otro)
        # Los 3 DNI ya existían: no se crean legajos nuevos.
        assert len(almacenamiento.listar_alumnos()) == antes

    def test_un_excel_tambien_se_puede_subir(self, excel_en_bytes):
        import pandas as pd
        df = pd.DataFrame({"Legajo": ["X1", "X2"], "Asistencia": [50, 90], "Promedio": [4, 8],
                           "Entregas pendientes": [5, 0]})
        at = subir("curso.xlsx", excel_en_bytes(df))
        assert not at.exception
        assert metricas(at)["Alto"] == 1

    def test_archivo_ilegible_muestra_un_error_sin_romper_la_app(self):
        at = subir("vacio.csv", b"")
        assert not at.exception
        assert any("No se pudo leer el archivo" in e.value for e in at.error)

    def test_una_columna_asignada_a_dos_datos_se_rechaza(self):
        at = subir()
        at.selectbox(key="map_promedio").select("Asistencia %").run()
        assert any("misma columna asignada a más de un dato" in e.value for e in at.error)

    def test_elegir_una_columna_personal_como_identificador_advierte(self):
        at = subir()
        at.selectbox(key="map_codigo").select("Apellido y Nombre").run()
        assert any("parece un nombre o DNI" in w.value for w in at.warning)

    def test_con_menos_de_3_datos_advierte_que_el_indice_es_poco_confiable(self):
        csv = b"Legajo;Asistencia %\nL1;50\nL2;90\n"
        at = subir("corto.csv", csv)
        assert any("menos de 3 datos" in w.value for w in at.warning)

    def test_el_informe_de_calidad_lista_los_problemas_del_archivo(self):
        csv = (b"Legajo;Asistencia %;Promedio general;Entregas pendientes\n"
               b"L1;150;4;5\nL1;90;8;0\n;80;7;1\nL4;70;ocho;2\n")
        at = subir("sucio.csv", csv)
        avisos = " ".join(m.value for m in at.markdown)
        assert not at.exception
        assert "repetido" in avisos and "sin identificador" in avisos
        assert "fuera de rango" in avisos and "no interpretables" in avisos


# ---------------------------------------------------------------------------
# Reconocimiento de columnas con IA (HU-11)
# ---------------------------------------------------------------------------
CSV_COLUMNAS_RARAS = b"Col A;Col B;Col C\nL1;50;4\nL2;90;8\n"


class TestMapeoConIA:
    def test_sin_ia_el_boton_esta_deshabilitado_y_se_puede_seguir_con_el_mapeo_basico(self):
        at = subir("raro.csv", CSV_COLUMNAS_RARAS)
        assert boton(at, "✨ Sugerir con IA").disabled is True
        assert any("mapeo automático básico" in c.value for c in at.caption)

    def test_el_mapeo_basico_no_reconoce_columnas_con_nombres_raros(self):
        at = subir("raro.csv", CSV_COLUMNAS_RARAS)
        assert at.selectbox(key="map_asistencia_pct").value == "(no disponible)"

    def test_con_ia_el_boton_aplica_el_mapeo_sugerido(self, con_ia, monkeypatch):
        monkeypatch.setattr(ia, "sugerir_mapeo", lambda columnas, campos: {
            "codigo": "Col A", "asistencia_pct": "Col B", "promedio": "Col C"})
        at = subir("raro.csv", CSV_COLUMNAS_RARAS)
        assert boton(at, "✨ Sugerir con IA").disabled is False
        boton(at, "✨ Sugerir con IA").click().run()
        assert at.selectbox(key="map_codigo").value == "Col A"
        assert at.selectbox(key="map_asistencia_pct").value == "Col B"
        assert at.selectbox(key="map_promedio").value == "Col C"
        assert any("La IA sugirió el mapeo" in s.value for s in at.success)

    def test_a_la_ia_solo_se_le_envian_los_nombres_de_las_columnas(self, con_ia, monkeypatch):
        recibido = {}

        def sugerir(columnas, campos):
            recibido["columnas"] = list(columnas)
            return {}

        monkeypatch.setattr(ia, "sugerir_mapeo", sugerir)
        at = subir("raro.csv", CSV_COLUMNAS_RARAS)
        boton(at, "✨ Sugerir con IA").click().run()
        assert recibido["columnas"] == ["Col A", "Col B", "Col C"]
        assert any("nombres de las columnas" in c.value and "nunca los datos" in c.value for c in at.caption)

    def test_si_la_ia_falla_se_avisa_y_se_conserva_el_mapeo_anterior(self, con_ia, monkeypatch):
        def falla(columnas, campos):
            raise ValueError("La IA no devolvió un objeto JSON válido para el mapeo.")

        monkeypatch.setattr(ia, "sugerir_mapeo", falla)
        at = subir("raro.csv", CSV_COLUMNAS_RARAS)
        boton(at, "✨ Sugerir con IA").click().run()
        assert not at.exception
        assert any("No se pudo usar la IA" in e.value for e in at.error)
