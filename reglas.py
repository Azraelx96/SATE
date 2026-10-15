"""Motor de reglas de riesgo de abandono (HU-03, HU-05, HU-10).

Diseño genérico: pensado para cualquier instituto, usando solo variables
académicas y de asistencia (sin datos socioeconómicos).

- Cada regla es un diccionario en REGLAS. Para agregar una regla, se agrega un
  diccionario; para descartarla en un instituto, se pone "activa": False.
- Si el instituto no registra una variable (columna ausente o vacía), esa regla
  se omite sin romper nada y sin bajar artificialmente el riesgo.
- La IA NO decide el riesgo: lo calculan estas reglas, que son explicables.
"""
import copy
import pandas as pd

# ---------------------------------------------------------------------------
# REGLAS
# sentido "menor": es peor cuanto MENOR es el valor (ej. asistencia)
# sentido "mayor": es peor cuanto MAYOR es el valor (ej. entregas sin presentar)
# Cada regla tiene un tramo leve y uno grave, con sus puntos.
# "binaria": True -> la variable vale 0 o 1 (no/sí).
# "critica": True -> si llega al tramo grave, el nivel sube a Alto sí o sí.
# ---------------------------------------------------------------------------
REGLAS = [
    # --- Dimensión: Asistencia ---
    {"id": "R01", "nombre": "Asistencia general", "dimension": "Asistencia",
     "variable": "asistencia_pct", "sentido": "menor", "unidad": "%",
     "umbral_leve": 75, "puntos_leve": 2, "umbral_grave": 60, "puntos_grave": 4, "activa": True},
    {"id": "R02", "nombre": "Inasistencias consecutivas (días seguidos)", "dimension": "Asistencia",
     "variable": "inasistencias_consecutivas", "sentido": "mayor", "unidad": " días",
     "umbral_leve": 5, "puntos_leve": 2, "umbral_grave": 10, "puntos_grave": 4,
     "critica": True, "activa": True},
    {"id": "R03", "nombre": "Llegadas tarde en el período", "dimension": "Asistencia",
     "variable": "llegadas_tarde", "sentido": "mayor", "unidad": "",
     "umbral_leve": 5, "puntos_leve": 1, "umbral_grave": 10, "puntos_grave": 2, "activa": True},

    # --- Dimensión: Rendimiento ---
    {"id": "R04", "nombre": "Promedio general", "dimension": "Rendimiento",
     "variable": "promedio", "sentido": "menor", "unidad": "",
     "umbral_leve": 6.0, "puntos_leve": 2, "umbral_grave": 4.5, "puntos_grave": 4, "activa": True},
    {"id": "R05", "nombre": "Materias desaprobadas", "dimension": "Rendimiento",
     "variable": "materias_desaprobadas", "sentido": "mayor", "unidad": "",
     "umbral_leve": 2, "puntos_leve": 2, "umbral_grave": 3, "puntos_grave": 4, "activa": True},
    {"id": "R06", "nombre": "Ausencias a evaluaciones", "dimension": "Rendimiento",
     "variable": "evaluaciones_ausente", "sentido": "mayor", "unidad": "",
     "umbral_leve": 1, "puntos_leve": 1, "umbral_grave": 2, "puntos_grave": 3, "activa": True},

    # --- Dimensión: Compromiso ---
    {"id": "R07", "nombre": "Entregas sin presentar", "dimension": "Compromiso",
     "variable": "entregas_sin_presentar", "sentido": "mayor", "unidad": "",
     "umbral_leve": 2, "puntos_leve": 2, "umbral_grave": 4, "puntos_grave": 4, "activa": True},
    {"id": "R08", "nombre": "Días sin actividad o participación", "dimension": "Compromiso",
     "variable": "dias_sin_actividad", "sentido": "mayor", "unidad": " días",
     "umbral_leve": 7, "puntos_leve": 1, "umbral_grave": 15, "puntos_grave": 3, "activa": True},

    # --- Dimensión: Tendencia (comparación con el período anterior) ---
    {"id": "R09", "nombre": "Caída de asistencia vs. período anterior", "dimension": "Tendencia",
     "variable": "variacion_asistencia", "sentido": "menor", "unidad": " pp",
     "umbral_leve": -10, "puntos_leve": 1, "umbral_grave": -20, "puntos_grave": 3, "activa": True},
    {"id": "R10", "nombre": "Caída de promedio vs. período anterior", "dimension": "Tendencia",
     "variable": "variacion_promedio", "sentido": "menor", "unidad": "",
     "umbral_leve": -1.0, "puntos_leve": 1, "umbral_grave": -2.0, "puntos_grave": 3, "activa": True},

    # --- Dimensión: Trayectoria ---
    {"id": "R11", "nombre": "Materias recursadas", "dimension": "Trayectoria",
     "variable": "materias_recursadas", "sentido": "mayor", "unidad": "",
     "umbral_leve": 1, "puntos_leve": 1, "umbral_grave": 3, "puntos_grave": 2, "activa": True},

    # --- Dimensión: Observación ---
    {"id": "R12", "nombre": "Preocupación registrada por el tutor", "dimension": "Observación",
     "variable": "preocupacion_tutor", "sentido": "mayor", "unidad": "", "binaria": True,
     "umbral_leve": 1, "puntos_leve": 3, "umbral_grave": None, "puntos_grave": None, "activa": True},
]

# ---------------------------------------------------------------------------
# MATRIZ DE RIESGO (niveles Bajo / Medio / Alto)
# ---------------------------------------------------------------------------
NIVELES = ["Bajo", "Medio", "Alto"]
INDICE_MEDIO = 15      # índice (0-100) desde el cual el nivel es Medio
INDICE_ALTO = 30       # índice (0-100) desde el cual el nivel es Alto
COBERTURA_MINIMA = 0.5  # mínimo de "peso" de reglas evaluables para calcular

# Escalamiento por amplitud: si hay alertas en varias dimensiones a la vez,
# el nivel no puede ser menor al indicado (aunque el índice sea bajo).
ESCALAMIENTO_DIMENSIONES = {3: "Medio", 5: "Alto"}


def _peso_maximo(regla):
    """Máximo de puntos que puede aportar una regla."""
    return regla["puntos_grave"] if regla["puntos_grave"] is not None else regla["puntos_leve"]


def _cumple(regla, valor, umbral):
    if umbral is None:
        return False
    return valor < umbral if regla["sentido"] == "menor" else valor >= umbral


def _texto_factor(regla, valor, tramo, puntos, umbral):
    if regla.get("binaria"):
        return f"{regla['nombre']} → +{puntos}"
    cmp_ = "por debajo de" if regla["sentido"] == "menor" else "igual o mayor a"
    u = regla["unidad"]
    return f"{regla['nombre']}: {valor:g}{u} ({cmp_} {umbral:g}{u}, tramo {tramo}) → +{puntos}"


def _nivel_max(a, b):
    return a if NIVELES.index(a) >= NIVELES.index(b) else b


def calcular_riesgo(fila, reglas=REGLAS):
    """Calcula el riesgo de un estudiante (fila de un DataFrame).

    Devuelve un diccionario con: puntaje, maximo, indice (0-100), nivel,
    dimensiones (afectadas), factores (lista explicativa) y nota (escalamiento).
    """
    activas = [r for r in reglas if r.get("activa", True)]
    peso_total = sum(_peso_maximo(r) for r in activas)
    puntaje, peso_evaluable = 0, 0
    factores, dimensiones, critica = [], set(), False

    for r in activas:
        valor = fila.get(r["variable"], float("nan"))
        if pd.isna(valor):
            continue  # dato no cargado: la regla no se evalúa
        peso_evaluable += _peso_maximo(r)
        if _cumple(r, valor, r["umbral_grave"]):
            tramo, puntos, umbral = "grave", r["puntos_grave"], r["umbral_grave"]
        elif _cumple(r, valor, r["umbral_leve"]):
            tramo, puntos, umbral = "leve", r["puntos_leve"], r["umbral_leve"]
        else:
            continue
        puntaje += puntos
        dimensiones.add(r["dimension"])
        factores.append({"regla": r["id"], "dimension": r["dimension"], "puntos": puntos,
                         "texto": _texto_factor(r, valor, tramo, puntos, umbral)})
        if tramo == "grave" and r.get("critica"):
            critica = True

    if peso_total == 0 or peso_evaluable / peso_total < COBERTURA_MINIMA:
        return {"puntaje": None, "maximo": peso_evaluable, "indice": None,
                "nivel": "Sin datos suficientes", "dimensiones": [],
                "factores": [], "nota": "Faltan datos para calcular el riesgo."}

    indice = round(100 * puntaje / peso_evaluable, 1)
    nivel = "Alto" if indice >= INDICE_ALTO else "Medio" if indice >= INDICE_MEDIO else "Bajo"
    nota = ""

    # Escalamiento por amplitud (varias dimensiones afectadas)
    for minimo, nivel_min in sorted(ESCALAMIENTO_DIMENSIONES.items()):
        if len(dimensiones) >= minimo and _nivel_max(nivel, nivel_min) != nivel:
            nivel = nivel_min
            nota = f"Nivel elevado a {nivel_min}: hay alertas en {len(dimensiones)} dimensiones a la vez."
    # Escalamiento por regla crítica
    if critica and nivel != "Alto":
        nivel = "Alto"
        nota = "Nivel elevado a Alto: se alcanzó el tramo grave de una regla crítica."

    return {"puntaje": puntaje, "maximo": peso_evaluable, "indice": indice, "nivel": nivel,
            "dimensiones": sorted(dimensiones), "factores": factores, "nota": nota}


def calcular_curso(df, reglas=REGLAS):
    """Agrega columnas de riesgo al DataFrame del curso (HU-03).

    Las reglas cuya columna no existe en los datos se excluyen: significa que
    el instituto no registra esa variable, y no por eso ningún estudiante
    queda sin datos suficientes.
    """
    reglas = [r for r in reglas if r["variable"] in df.columns]
    resultados = [calcular_riesgo(fila, reglas) for _, fila in df.iterrows()]
    df = df.copy()
    for campo in ["puntaje", "maximo", "indice", "nivel", "dimensiones", "factores", "nota"]:
        df[campo] = [res[campo] for res in resultados]
    return df


def copiar_reglas():
    """Copia editable de las reglas (para activar/desactivar sin tocar el original)."""
    return copy.deepcopy(REGLAS)


if __name__ == "__main__":
    # Prueba rápida desde la terminal: python reglas.py
    datos = pd.read_csv("datos/alumnos_ficticios.csv")
    out = calcular_curso(datos)
    out["dims"] = out["dimensiones"].map(len)
    print(out[["codigo", "puntaje", "maximo", "indice", "nivel", "dims"]].to_string(index=False))
