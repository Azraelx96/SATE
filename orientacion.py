"""
Orientación para la tutoría (HU-06).

Este módulo hace dos cosas, ambas alrededor de la llamada a la IA:
- armar_paquete(): decide EXACTAMENTE qué datos del estudiante se le envían al modelo.
- revisar_texto(): revisa lo que devolvió el modelo y avisa si algo merece atención.

La IA nunca decide el nivel de riesgo: el paquete lleva un resultado ya calculado
por las reglas. Nunca se envían nombre, DNI, legajo ni el texto de las observaciones.
"""
import json
import re
import unicodedata

import pandas as pd

MAX_PALABRAS = 150

# Palabras que, si aparecen, conviene que una persona revise el texto.
PALABRAS_A_REVISAR = {
    "una sanción": ["sanción", "sanciones", "sancionar", "expulsión", "expulsar", "suspensión", "amonestación"],
    "un diagnóstico": ["depresión", "ansiedad", "trastorno", "diagnóstico", "patología", "adicción"],
    "una certeza sobre el abandono": ["abandonará", "va a abandonar", "seguro que abandona", "inevitable"],
}


def _sin_acentos(texto):
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()


def armar_paquete(fila, reglas):
    """
    Arma lo que se le envía al modelo para un estudiante (fila de calcular_curso).

    Incluye el resultado ya calculado y también qué dimensiones se evaluaron SIN
    alertas, para que el modelo pueda nombrar una fortaleza solo cuando los datos
    la respaldan. No incluye nombre, DNI, legajo ni observaciones.
    """
    evaluadas = {
        r["dimension"]
        for r in reglas
        if r.get("activa", True) and r["variable"] in fila.index and pd.notna(fila[r["variable"]])
    }
    con_alerta = set(fila["dimensiones"])

    return {
        "nivel": str(fila["nivel"]),
        "indice": float(fila["indice"]),
        "dimensiones_con_alerta": sorted(con_alerta),
        "dimensiones_sin_alerta": sorted(evaluadas - con_alerta),
        "factores_de_riesgo": [f["texto"] for f in fila["factores"]],
        "nota_del_sistema": str(fila["nota"]) if fila["nota"] else None,
    }


def _numeros(texto):
    return {n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", str(texto))}


def revisar_texto(texto, paquete):
    """Devuelve una lista de avisos (vacía si no hay nada que señalar). Es una ayuda, no una garantía."""
    avisos = []
    texto = (texto or "").strip()

    if not texto:
        return ["La IA devolvió un texto vacío."]

    palabras = len(texto.split())
    if palabras > MAX_PALABRAS:
        avisos.append(f"El texto es más largo de lo esperado ({palabras} palabras).")

    limpio = _sin_acentos(texto)
    for motivo, lista in PALABRAS_A_REVISAR.items():
        hallada = next((p for p in lista if _sin_acentos(p) in limpio), None)
        if hallada:
            avisos.append(f"Menciona {motivo} («{hallada}»): revisalo antes de usarlo.")

    inventadas = sorted(_numeros(texto) - _numeros(json.dumps(paquete, ensure_ascii=False)))
    if inventadas:
        avisos.append("Incluye cifras que no figuran en los datos del estudiante ("
                      + ", ".join(inventadas) + "): verificá que no sean inventadas.")

    return avisos
