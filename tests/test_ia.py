"""Pruebas de la integración con la IA (ia.py).  HU-06, HU-11 y HU-12.

Casi todas usan un "Ollama de mentira" (ClienteFalso): así corren en cualquier
computadora, sin modelo instalado y en una fracción de segundo.

Las pruebas marcadas con @pytest.mark.ollama usan el Ollama REAL. Están
apagadas por defecto; se activan con la variable SATE_TESTS_OLLAMA=1.
"""
import json
from types import SimpleNamespace

import pytest

import carga
import ia
import orientacion
from reglas import calcular_curso, copiar_reglas


# ---------------------------------------------------------------------------
# Ollama de mentira
# ---------------------------------------------------------------------------
class ClienteFalso:
    """Imita al cliente de Ollama y recuerda todo lo que se le envió."""

    def __init__(self, respuesta="Texto de prueba.", modelos=None, error=None):
        self.respuesta = respuesta
        self.modelos = modelos if modelos is not None else []
        self.error = error
        self.llamadas = []

    def chat(self, model, messages, options):
        if self.error:
            raise self.error
        self.llamadas.append({"model": model, "messages": messages, "options": options})
        return {"message": {"content": self.respuesta}}

    def list(self):
        if self.error:
            raise self.error
        return SimpleNamespace(models=self.modelos)


def modelo(nombre):
    return SimpleNamespace(model=nombre)


@pytest.fixture
def falso(monkeypatch):
    """Instala un ClienteFalso y lo devuelve para poder configurarlo."""
    cliente = ClienteFalso()
    monkeypatch.setattr(ia, "_cliente", lambda: cliente)
    monkeypatch.setattr(ia, "MODELO", "qwen2.5:7b")
    return cliente


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
class TestConfiguracion:
    def test_hay_modelo_y_direccion_configurados(self):
        assert isinstance(ia.MODELO, str) and ia.MODELO
        assert ia.OLLAMA_HOST.startswith("http")

    def test_el_cliente_usa_la_direccion_configurada_y_timeout_de_120_segundos(self, monkeypatch):
        recibido = {}

        def cliente_falso(**kwargs):
            recibido.update(kwargs)
            return "cliente"

        monkeypatch.setattr(ia.ollama, "Client", cliente_falso)
        monkeypatch.setattr(ia, "OLLAMA_HOST", "http://servidor:1234")
        assert ia._cliente() == "cliente"
        assert recibido == {"host": "http://servidor:1234", "timeout": 120}


# ---------------------------------------------------------------------------
# disponible()
# ---------------------------------------------------------------------------
class TestDisponible:
    def test_true_si_el_modelo_esta_instalado(self, falso):
        falso.modelos = [modelo("qwen2.5:7b")]
        assert ia.disponible() is True

    @pytest.mark.parametrize("posicion", [0, 1, 2])
    def test_revisa_todos_los_modelos_no_solo_el_ultimo(self, falso, posicion):
        """Regresión: antes solo se miraba el último modelo de la lista."""
        lista = [modelo("llama3:8b"), modelo("mistral:7b"), modelo("gemma:2b")]
        lista[posicion] = modelo("qwen2.5:7b")
        falso.modelos = lista
        assert ia.disponible() is True

    def test_false_si_el_modelo_no_esta_instalado(self, falso):
        falso.modelos = [modelo("llama3:8b")]
        assert ia.disponible() is False

    def test_false_si_no_hay_ningun_modelo(self, falso):
        assert ia.disponible() is False

    def test_false_si_esta_instalada_otra_version_del_mismo_modelo(self, falso):
        falso.modelos = [modelo("qwen2.5:7b")]
        ia.MODELO = "qwen2.5:14b"
        assert ia.disponible() is False

    def test_acepta_el_nombre_sin_etiqueta(self, falso):
        falso.modelos = [modelo("qwen2.5:7b")]
        ia.MODELO = "qwen2.5"
        assert ia.disponible() is True

    def test_acepta_versiones_viejas_de_ollama_que_usan_name_en_vez_de_model(self, falso):
        falso.modelos = [SimpleNamespace(name="qwen2.5:7b")]
        assert ia.disponible() is True

    def test_false_y_sin_romper_si_ollama_esta_apagado(self, falso, capsys):
        falso.error = ConnectionError("conexión rechazada")
        assert ia.disponible() is False
        assert "Error al comprobar Ollama" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _llamar
# ---------------------------------------------------------------------------
class TestLlamar:
    def test_envia_el_mensaje_de_sistema_y_el_del_usuario(self, falso):
        ia._llamar("SISTEMA", "USUARIO")
        envio = falso.llamadas[0]
        assert envio["model"] == "qwen2.5:7b"
        assert envio["messages"] == [{"role": "system", "content": "SISTEMA"},
                                     {"role": "user", "content": "USUARIO"}]

    def test_temperatura_baja_por_defecto(self, falso):
        ia._llamar("s", "u")
        assert falso.llamadas[0]["options"] == {"temperature": 0.2}

    def test_las_opciones_recibidas_pisan_las_por_defecto(self, falso):
        ia._llamar("s", "u", options={"temperature": 0, "num_predict": 50})
        assert falso.llamadas[0]["options"] == {"temperature": 0, "num_predict": 50}

    def test_devuelve_el_texto_sin_espacios_sobrantes(self, falso):
        falso.respuesta = "\n  Hola mundo  \n"
        assert ia._llamar("s", "u") == "Hola mundo"

    def test_si_ollama_falla_la_excepcion_sube_para_que_la_interfaz_la_muestre(self, falso):
        falso.error = TimeoutError("se agotó el tiempo")
        with pytest.raises(TimeoutError):
            ia._llamar("s", "u")


# ---------------------------------------------------------------------------
# sugerir_mapeo (HU-11)
# ---------------------------------------------------------------------------
COLUMNAS = ["Legajo", "Asist %", "Prom"]
CAMPOS = {"codigo": "Identificador", "asistencia_pct": "Asistencia (%)", "promedio": "Promedio"}


def mapear(falso, respuesta, columnas=COLUMNAS, campos=CAMPOS):
    falso.respuesta = respuesta
    return ia.sugerir_mapeo(columnas, campos)


class TestSugerirMapeo:
    def test_respuesta_json_limpia(self, falso):
        r = mapear(falso, '{"codigo": "Legajo", "asistencia_pct": "Asist %", "promedio": "Prom"}')
        assert r == {"codigo": "Legajo", "asistencia_pct": "Asist %", "promedio": "Prom"}

    def test_json_dentro_de_un_bloque_markdown(self, falso):
        r = mapear(falso, '```json\n{"codigo": "Legajo", "promedio": "Prom"}\n```')
        assert r == {"codigo": "Legajo", "asistencia_pct": None, "promedio": "Prom"}

    def test_json_con_texto_alrededor(self, falso):
        r = mapear(falso, 'Claro, acá va: {"codigo": "Legajo"} ¡Espero que sirva!')
        assert r["codigo"] == "Legajo"

    def test_los_campos_que_la_ia_no_menciona_quedan_en_none(self, falso):
        r = mapear(falso, '{"codigo": "Legajo"}')
        assert r == {"codigo": "Legajo", "asistencia_pct": None, "promedio": None}

    def test_columna_inventada_se_descarta(self, falso):
        r = mapear(falso, '{"codigo": "Legajo", "promedio": "Nota final inventada"}')
        assert r["promedio"] is None and r["codigo"] == "Legajo"

    def test_campo_inventado_se_ignora(self, falso):
        r = mapear(falso, '{"codigo": "Legajo", "color_favorito": "Prom"}')
        assert "color_favorito" not in r

    def test_una_columna_repetida_solo_se_asigna_al_primer_campo(self, falso):
        r = mapear(falso, '{"codigo": "Legajo", "asistencia_pct": "Legajo"}')
        assert r["codigo"] == "Legajo" and r["asistencia_pct"] is None

    @pytest.mark.parametrize("valor", ["null", "123", '["Prom"]', "true"])
    def test_valores_que_no_son_texto_se_descartan(self, falso, valor):
        r = mapear(falso, f'{{"promedio": {valor}}}')
        assert r["promedio"] is None

    def test_el_resultado_siempre_tiene_todos_los_campos(self, falso):
        assert set(mapear(falso, "{}")) == set(CAMPOS)

    @pytest.mark.parametrize("respuesta", ["No sé cómo ayudarte.", "[1, 2, 3]", "} mal {", ""])
    def test_sin_json_valido_da_un_error_claro(self, falso, respuesta):
        with pytest.raises(ValueError):
            mapear(falso, respuesta)

    def test_json_mal_formado_da_error(self, falso):
        with pytest.raises(ValueError):
            mapear(falso, '{"codigo": Legajo}')

    def test_solo_se_envian_nombres_de_columnas_y_descripciones_de_campos(self, falso):
        mapear(falso, "{}")
        envio = falso.llamadas[0]
        assert envio["messages"][0]["content"] == ia.SYSTEM_MAPEO
        assert json.loads(envio["messages"][1]["content"]) == {
            "columnas_disponibles": COLUMNAS, "campos_admitidos": CAMPOS}
        assert envio["options"] == {"temperature": 0}

    def test_funciona_con_los_campos_reales_del_sistema(self, falso):
        falso.respuesta = json.dumps({"codigo": "Legajo", "asistencia_pct": "Asist %"})
        r = ia.sugerir_mapeo(COLUMNAS, carga.CAMPOS)
        assert set(r) == set(carga.CAMPOS)
        assert r["asistencia_pct"] == "Asist %"


# ---------------------------------------------------------------------------
# redactar_resumen (HU-12) y devolucion (HU-06)
# ---------------------------------------------------------------------------
class TestRedactarResumen:
    def test_envia_las_cifras_agregadas_y_devuelve_el_texto(self, falso):
        falso.respuesta = "Resumen listo."
        agregados = {"total_estudiantes": 16, "estudiantes_por_nivel": {"Alto": 4}}
        assert ia.redactar_resumen(agregados) == "Resumen listo."
        envio = falso.llamadas[0]
        assert envio["messages"][0]["content"] == ia.SYSTEM_RESUMEN
        assert json.loads(envio["messages"][1]["content"]) == agregados


class TestDevolucion:
    def test_envia_el_paquete_como_json_sin_escapar_los_acentos(self, falso):
        falso.respuesta = "Orientación."
        paquete = {"nivel": "Alto", "dimensiones_con_alerta": ["Observación"]}
        assert ia.devolucion(paquete) == "Orientación."
        envio = falso.llamadas[0]
        assert envio["messages"][0]["content"] == ia.SYSTEM_DEVOLUCION
        assert "Observación" in envio["messages"][1]["content"]
        assert json.loads(envio["messages"][1]["content"]) == paquete


# ---------------------------------------------------------------------------
# Las instrucciones (prompts) fijan las reglas éticas: si alguien las borra, avisa
# ---------------------------------------------------------------------------
class TestInstruccionesDeLaIA:
    @pytest.mark.parametrize("fragmento", [
        "tercera persona", "3 o 4 oraciones", "no inventes", "No realices diagnósticos",
        "No sugieras sanciones", "No modifiques el nivel de riesgo", "No presentes el nivel de riesgo como una certeza",
    ])
    def test_prompt_de_orientacion(self, fragmento):
        assert fragmento.lower() in ia.SYSTEM_DEVOLUCION.lower()

    @pytest.mark.parametrize("fragmento", [
        "180 palabras", "No inventes", "No identifiques", "No recomiendes sanciones",
        "umbrales del prototipo todavía deben validarse", "No afirmes que el sistema predice con certeza",
    ])
    def test_prompt_de_resumen(self, fragmento):
        assert fragmento.lower() in ia.SYSTEM_RESUMEN.lower()

    @pytest.mark.parametrize("fragmento", ["exclusivamente con un objeto JSON", "null", "No inventes columnas"])
    def test_prompt_de_mapeo(self, fragmento):
        assert fragmento.lower() in ia.SYSTEM_MAPEO.lower()


# ---------------------------------------------------------------------------
# Privacidad de punta a punta (lo que REALMENTE viaja hacia el modelo)
# ---------------------------------------------------------------------------
class TestPrivacidadDeExtremoAExtremo:
    def test_la_orientacion_nunca_envia_datos_personales_al_modelo(self, falso, datos_ficticios):
        df = datos_ficticios.copy()
        df["legajo"] = [f"SATE-{i:06d}" for i in range(1, 17)]
        df["nombre"] = "Nombre Secreto"
        df["apellido"] = "Apellido Secreto"
        df["dni"] = "30999888"
        df["observacion"] = "OBSERVACION CONFIDENCIAL"
        reglas = copiar_reglas()
        curso = calcular_curso(df, reglas)
        for _, fila in curso[curso["nivel"].isin(["Alto", "Medio"])].iterrows():
            falso.llamadas.clear()
            ia.devolucion(orientacion.armar_paquete(fila, reglas))
            enviado = json.dumps(falso.llamadas[0]["messages"], ensure_ascii=False)
            for secreto in ("Nombre Secreto", "Apellido Secreto", "30999888",
                            "OBSERVACION CONFIDENCIAL", fila["legajo"], fila["codigo"]):
                assert secreto not in enviado

    def test_el_resumen_nunca_envia_codigos_de_estudiantes(self, falso, curso_calculado):
        import resumen
        ia.redactar_resumen(resumen.agregados(curso_calculado, copiar_reglas()))
        enviado = json.dumps(falso.llamadas[0]["messages"], ensure_ascii=False)
        assert not any(f"A0{i:02d}" in enviado for i in range(1, 17))

    def test_el_mapeo_nunca_envia_filas_de_datos(self, falso, datos_ficticios):
        falso.respuesta = "{}"
        ia.sugerir_mapeo(list(datos_ficticios.columns), carga.CAMPOS)
        enviado = falso.llamadas[0]["messages"][1]["content"]
        assert "A002" not in enviado and "4.2" not in enviado

    def test_flujo_completo_con_revision_del_texto_devuelto(self, falso, curso_calculado):
        """Paquete → IA falsa → revisión: un texto con sanción y cifra inventada se marca."""
        reglas = copiar_reglas()
        fila = curso_calculado[curso_calculado["codigo"] == "A002"].iloc[0]
        paquete = orientacion.armar_paquete(fila, reglas)
        falso.respuesta = "Habría que aplicar una sanción: tiene 77 faltas."
        texto = ia.devolucion(paquete)
        avisos = orientacion.revisar_texto(texto, paquete)
        assert len(avisos) == 2


# ---------------------------------------------------------------------------
# Pruebas con Ollama REAL (apagadas por defecto)
# ---------------------------------------------------------------------------
@pytest.mark.ollama
class TestConOllamaReal:
    @pytest.fixture(autouse=True)
    def _requiere_ollama(self):
        if not ia.disponible():
            pytest.skip(f"Ollama no responde o falta el modelo {ia.MODELO}")

    def test_mapeo_real_devuelve_solo_columnas_existentes(self):
        columnas = ["Legajo", "Apellido y Nombre", "% de asistencia", "Promedio general",
                    "Entregas pendientes"]
        r = ia.sugerir_mapeo(columnas, carga.CAMPOS)
        assert set(r) == set(carga.CAMPOS)
        usadas = [c for c in r.values() if c]
        assert set(usadas) <= set(columnas)
        assert len(usadas) == len(set(usadas))

    def test_orientacion_real_para_un_estudiante_en_nivel_alto(self, curso_calculado):
        reglas = copiar_reglas()
        fila = curso_calculado[curso_calculado["codigo"] == "A002"].iloc[0]
        paquete = orientacion.armar_paquete(fila, reglas)
        texto = ia.devolucion(paquete)
        avisos = orientacion.revisar_texto(texto, paquete)
        print("\n--- TEXTO DEL MODELO ---\n", texto, "\n--- AVISOS ---\n", avisos)
        assert texto.strip()

    def test_resumen_real(self, curso_calculado):
        import resumen
        texto = ia.redactar_resumen(resumen.agregados(curso_calculado, copiar_reglas()))
        print("\n--- RESUMEN DEL MODELO ---\n", texto)
        assert texto.strip()
