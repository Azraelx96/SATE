"""
Prueba rápida de la orientación con IA sobre los datos de ejemplo.

Sirve para evaluar la calidad del modelo y ajustar el prompt (SYSTEM_DEVOLUCION en ia.py).

Uso (desde la carpeta del proyecto, con Ollama abierto):
    python probar_orientacion.py              prueba a todos los estudiantes con nivel Medio o Alto
    python probar_orientacion.py A002 A005    prueba solo esos códigos

El resultado completo (lo que se envía y lo que responde el modelo) queda en
orientaciones_prueba.txt para poder revisarlo con calma.
"""
import sys
import time

import pandas as pd

import ia
import orientacion
from reglas import calcular_curso, copiar_reglas

CRITERIOS = """Para evaluar cada texto, preguntate:
  1. ¿Usa solo los datos recibidos, sin inventar hechos, cifras ni causas?
  2. ¿Tiene 3 o 4 oraciones, en español natural?
  3. ¿Evita diagnósticos, sanciones y certezas sobre el abandono?
  4. ¿Nombra una fortaleza SOLO si los datos la respaldan?
  5. ¿Propone una acción concreta y realista que un tutor podría hacer?
  6. ¿Está escrito para el tutor y habla del estudiante en tercera persona?"""


def main(codigos):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not ia.disponible():
        print("Ollama no está disponible o el modelo configurado no está instalado.")
        print(f"Modelo configurado: {ia.MODELO} (servidor: {ia.OLLAMA_HOST})")
        print("Abrí Ollama y comprobá con:  ollama list")
        return 1

    reglas = copiar_reglas()
    df = calcular_curso(pd.read_csv("datos/alumnos_ficticios.csv"), reglas)
    candidatos = df[df["nivel"].isin(["Alto", "Medio"])]
    if codigos:
        candidatos = candidatos[candidatos["codigo"].isin(codigos)]
    if candidatos.empty:
        print("No hay estudiantes con nivel Medio o Alto para esos códigos.")
        return 1

    print(f"Modelo: {ia.MODELO} | {len(candidatos)} estudiante(s)\n")
    registro, tiempos, con_avisos = [], [], 0

    for _, fila in candidatos.iterrows():
        paquete = orientacion.armar_paquete(fila, reglas)
        inicio = time.time()
        try:
            texto = ia.devolucion(paquete).strip()
        except Exception as error:  # noqa: BLE001
            print(f"[{fila['codigo']}] ERROR: {error}\n")
            continue
        segundos = time.time() - inicio
        tiempos.append(segundos)
        avisos = orientacion.revisar_texto(texto, paquete)
        con_avisos += bool(avisos)

        bloque = [f"=== {fila['codigo']} · nivel {fila['nivel']} · {segundos:.0f} s ===", texto]
        bloque += [f"  ⚠ {a}" for a in avisos] or ["  (sin avisos de revisión)"]
        print("\n".join(bloque) + "\n")
        registro.append("\n".join(bloque) + "\n\n--- datos enviados al modelo ---\n"
                        + str(paquete) + "\n")

    if tiempos:
        print(f"Tiempo promedio: {sum(tiempos) / len(tiempos):.0f} s | con avisos de revisión: {con_avisos} de {len(tiempos)}\n")
        print(CRITERIOS)
        with open("orientaciones_prueba.txt", "w", encoding="utf-8") as archivo:
            archivo.write("\n\n".join(registro) + "\n\n" + CRITERIOS + "\n")
        print("\nGuardado en orientaciones_prueba.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
