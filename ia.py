"""
Integración local de SATE con Ollama.

La IA asiste en el mapeo de columnas y la redacción de resúmenes.
El cálculo del riesgo corresponde exclusivamente a reglas.py.
"""

import json
import os
import re

import ollama
from dotenv import load_dotenv


# Cargar las variables definidas en .env.
load_dotenv()

OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    "http://localhost:11434",
).strip()

MODELO = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:7b",
).strip()


SYSTEM_DEVOLUCION = """
Sos un asistente de apoyo docente del sistema SATE.

Tu tarea es redactar una orientación breve, respetuosa y útil
para acompañar la trayectoria educativa de un estudiante.

Reglas obligatorias:
- Escribí en español rioplatense.
- Usá entre 3 y 4 oraciones.
- Mencioná una fortaleza únicamente si los datos la respaldan.
- Indicá un aspecto que conviene acompañar.
- Proponé una acción concreta y realista.
- No inventes datos, causas ni circunstancias personales.
- No realices diagnósticos.
- No presentes el nivel de riesgo como una certeza.
- No modifiques el nivel de riesgo calculado por las reglas.
- No sugieras sanciones ni medidas discriminatorias.
- El objetivo es priorizar el acompañamiento educativo.
"""


SYSTEM_MAPEO = """
Sos un asistente que ayuda a mapear columnas de un archivo educativo.

Recibirás los nombres de las columnas y los campos admitidos por SATE.

Respondé exclusivamente con un objeto JSON.
Usá como claves los nombres exactos de los campos admitidos.
Usá como valores los nombres exactos de las columnas proporcionadas.
Si no podés identificar un campo, asignale null.
No inventes columnas ni campos.
No agregues explicaciones fuera del JSON.
"""


SYSTEM_RESUMEN = """
Sos un asistente que redacta resúmenes institucionales de SATE.

Recibirás exclusivamente indicadores agregados del curso.

Reglas obligatorias:
- Escribí en español rioplatense.
- Redactá un resumen claro y conciso.
- Utilizá únicamente los datos proporcionados.
- No inventes cifras, tendencias ni causas.
- No identifiques ni intentes identificar estudiantes.
- No afirmes que el sistema predice con certeza el abandono.
- Recordá que las alertas orientan el acompañamiento educativo.
- Indicá que los umbrales del prototipo todavía deben validarse.
- No recomiendes sanciones.
- No superes las 180 palabras.
"""


def _cliente():
    """Crea un cliente de Ollama con la dirección configurada."""
    return ollama.Client(host=OLLAMA_HOST)


def disponible():
    """
    Comprueba si Ollama responde y si el modelo configurado está instalado.

    Devuelve True si ambas condiciones se cumplen.
    """
    try:
        cliente = _cliente()
        respuesta = cliente.list()
        # La biblioteca de Ollama devuelve un objeto ListResponse.
        # Accedemos a su atributo models
        modelos = respuesta.models

        nombres = set()

        for modelo in modelos:
            nombre = (
                getattr(modelo, "model", None) 
                or getattr(modelo, "name", None)
                )
            
        if nombre:
                    nombres.add(nombre)

        return MODELO in nombres

    except Exception as error: 
        print(f"Error al comprobar Ollama: {error}") 
    return False


def _llamar(sistema, usuario, options=None):
    """
    Ejecuta una solicitud al modelo local.

    Si Ollama no responde, lanza una excepción para que la interfaz
    pueda informar del problema sin detener toda la aplicación.
    """
    cliente = _cliente()

    parametros = {
        "temperature": 0.2,
    }

    if options:
        parametros.update(options)

    respuesta = cliente.chat(
        model=MODELO,
        messages=[
            {
                "role": "system",
                "content": sistema,
            },
            {
                "role": "user",
                "content": usuario,
            },
        ],
        options=parametros,
    )

    return respuesta["message"]["content"].strip()


def sugerir_mapeo(columnas, campos):
    """
    Sugiere un mapeo entre los campos SATE y las columnas del archivo.

    Recibe nombres de columnas y descripciones de campos.
    No necesita enviar las filas del archivo a la IA.

    Devuelve un diccionario:
        {campo: columna o None}
    """
    campos_json = {
        campo: descripcion
        for campo, descripcion in campos.items()
    }

    usuario = json.dumps(
        {
            "columnas_disponibles": list(columnas),
            "campos_admitidos": campos_json,
        },
        ensure_ascii=False,
    )

    respuesta = _llamar(
        SYSTEM_MAPEO,
        usuario,
        options={
            "temperature": 0,
        },
    )

    # Admitir respuestas JSON que el modelo haya encerrado
    # accidentalmente en un bloque Markdown.
    texto = respuesta.strip()

    texto = re.sub(
        r"^```(?:json)?\s*",
        "",
        texto,
        flags=re.IGNORECASE,
    )

    texto = re.sub(
        r"\s*```$",
        "",
        texto,
    )

    # Buscar el objeto JSON si hay texto adicional.
    inicio = texto.find("{")
    fin = texto.rfind("}")

    if inicio == -1 or fin == -1 or fin < inicio:
        raise ValueError(
            "La IA no devolvió un objeto JSON válido para el mapeo."
        )

    datos = json.loads(texto[inicio:fin + 1])

    if not isinstance(datos, dict):
        raise ValueError(
            "El resultado del mapeo no tiene el formato esperado."
        )

    columnas_validas = set(columnas)
    campos_validos = set(campos)

    resultado = {
        campo: None
        for campo in campos
    }

    columnas_usadas = set()

    for campo, columna in datos.items():
        if campo not in campos_validos:
            continue

        if not isinstance(columna, str):
            continue

        if columna not in columnas_validas:
            continue

        if columna in columnas_usadas:
            continue

        resultado[campo] = columna
        columnas_usadas.add(columna)

    return resultado


def redactar_resumen(agregados):
    """
    Redacta un resumen institucional a partir de cifras agregadas.

    No recibe el DataFrame completo de estudiantes.
    """
    usuario = json.dumps(
        agregados,
        ensure_ascii=False,
    )

    return _llamar(
        SYSTEM_RESUMEN,
        usuario,
    )


def devolucion(paquete: dict):
    """
    Redacta una orientación individual a partir de un paquete
    previamente preparado por la aplicación.

    El llamador debe limitar los datos enviados a los estrictamente
    necesarios y evitar nombres, DNI y otros identificadores directos.
    """
    usuario = json.dumps(
        paquete,
        ensure_ascii=False,
    )

    return _llamar(
        SYSTEM_DEVOLUCION,
        usuario,
    )