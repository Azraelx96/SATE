"""Carga dinámica de datos (HU-01): lectura, mapeo de columnas, limpieza y validación.

Pensado para que cada instituto suba su propio archivo (CSV o Excel) aunque
sus columnas se llamen distinto. El mapeo se sugiere solo (sin IA) y puede
mejorarse con IA; siempre lo confirma una persona antes de calcular.
"""
import io
import re
import unicodedata
import pandas as pd

CAMPOS = {
    "codigo": "Identificador del estudiante (legajo, código o número)",
    "asistencia_pct": "Asistencia (%)",
    "promedio": "Promedio general (escala 0 a 10)",
    "entregas_sin_presentar": "Entregas sin presentar",
    "preocupacion_tutor": "Preocupación del tutor (sí/no)",
    "materias_desaprobadas": "Materias desaprobadas",
    "evaluaciones_ausente": "Ausencias a evaluaciones",
    "llegadas_tarde": "Llegadas tarde",
    "inasistencias_consecutivas": "Inasistencias consecutivas (días seguidos)",
    "dias_sin_actividad": "Días sin actividad o participación",
    "variacion_asistencia": "Variación de asistencia vs. período anterior (puntos %)",
    "variacion_promedio": "Variación de promedio vs. período anterior",
    "materias_recursadas": "Materias recursadas",
}
BINARIOS = {"preocupacion_tutor"}
CONTEOS = ["entregas_sin_presentar", "materias_desaprobadas", "evaluaciones_ausente", "llegadas_tarde",
           "inasistencias_consecutivas", "dias_sin_actividad", "materias_recursadas"]
PALABRAS_PERSONALES = ["nombre", "apellido", "dni", "documento", "mail", "correo", "telefono",
                       "celular", "domicilio", "direccion", "cuil", "cuit"]
EXACTO_CODIGO = {"codigo", "legajo", "matricula", "id", "idalumno", "idestudiante", "nroalumno",
                 "numeroalumno", "nrolegajo", "nrodelegajo", "numerodelegajo"}
EXACTO_PROMEDIO = {"nota", "notas", "calificacion", "calificaciones", "promediogeneral"}

# (campo, grupos, excluir): cada grupo es una lista de fragmentos (alguno debe aparecer)
# y todos los grupos deben cumplirse. Van de lo más específico a lo más general.
PATRONES = [
    ("variacion_asistencia", [["variacion", "caida", "cambio", "evolucion"], ["asistencia", "presentismo"]], []),
    ("variacion_promedio", [["variacion", "caida", "cambio", "evolucion"], ["promedio", "nota"]], []),
    ("inasistencias_consecutivas", [["consecutiv", "seguid"]], []),
    ("evaluaciones_ausente", [["evaluacion", "parcial", "examen"], ["ausen", "falt", "inasist"]], []),
    ("llegadas_tarde", [["tarde", "tardanza", "retraso"]], []),
    ("entregas_sin_presentar", [["entrega", "trabajospracticos"], ["sinpresent", "pendient", "adeud", "nopresent"]], []),
    ("dias_sin_actividad", [["sinactiv", "inactiv", "sinparticip", "sinconex", "ultimaconexion"]], []),
    ("materias_desaprobadas", [["desaprob", "reprob", "aplaz"]], []),
    ("materias_recursadas", [["recurs", "repit"]], []),
    ("preocupacion_tutor", [["preocup", "tutor", "observacion", "alerta"]], []),
    ("asistencia_pct", [["asistencia", "presentismo"]], ["inasist", "consecut", "tarde"]),
    ("promedio", [["promedio", "notamedia"]], []),
]


def normalizar(texto):
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def columnas_personales(columnas):
    """Columnas cuyo nombre sugiere datos personales (nombre, DNI, mail...)."""
    return [c for c in columnas if any(p in normalizar(c) for p in PALABRAS_PERSONALES)]


def sugerir_mapeo(columnas):
    """Sugerencia automática sin IA: {campo: columna del archivo o None}."""
    norm = {c: normalizar(c) for c in columnas}
    personales = set(columnas_personales(columnas))
    usadas, mapeo = set(), {}

    def buscar(pred):
        for c, n in norm.items():
            if c not in usadas and c not in personales and pred(n):
                usadas.add(c)
                return c
        return None

    mapeo["codigo"] = buscar(lambda n: n in EXACTO_CODIGO or "legajo" in n or "codigo" in n)
    for campo, grupos, excluir in PATRONES:
        mapeo[campo] = buscar(lambda n, g=grupos, e=excluir:
                              all(any(f in n for f in grupo) for grupo in g) and not any(x in n for x in e))
        if campo == "promedio" and mapeo[campo] is None:
            mapeo[campo] = buscar(lambda n: n in EXACTO_PROMEDIO)
    return mapeo


def leer_archivo(archivo):
    """Lee un CSV (separador y codificación detectados) o un Excel (.xlsx, primera hoja)."""
    nombre = archivo.name.lower()
    if nombre.endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(archivo.getvalue()))
    else:
        datos = archivo.getvalue()
        df = None
        for enc in ("utf-8-sig", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(datos), sep=None, engine="python", encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        if df is None:
            raise ValueError("No se pudo leer el archivo CSV.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _texto(serie):
    """Serie como texto sin NaN (los vacíos pasan a ''), compatible con pandas 2 y 3."""
    return serie.where(serie.notna(), "").astype(str).str.strip()


def _a_numero(serie):
    txt = _texto(serie)
    vacio = txt.str.lower().isin(["", "nan", "none", "-", "s/d", "sd", "n/a", "na"])
    limpio = txt.str.replace("%", "", regex=False).str.replace(",", ".", regex=False).str.strip()
    num = pd.to_numeric(limpio.where(~vacio), errors="coerce")
    return num, int((num.isna() & ~vacio).sum())


def _a_binario(serie):
    txt = _texto(serie).str.lower()
    vacio = txt.isin(["", "nan", "none"])
    txt = txt.map(lambda t: unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode())
    res = pd.Series(float("nan"), index=serie.index)
    res[txt.isin({"si", "s", "yes", "y", "true", "verdadero", "1", "1.0", "x"})] = 1.0
    res[txt.isin({"no", "n", "false", "falso", "0", "0.0"})] = 0.0
    return res, int((res.isna() & ~vacio).sum())


def _validar_rango(campo, valores, col, avisos):
    if campo == "asistencia_pct":
        mx = valores.max()
        if pd.notna(mx) and 0 < mx <= 1:
            valores = valores * 100
            avisos.append(f"«{col}»: los valores estaban entre 0 y 1; se interpretaron como proporción y se pasaron a %.")
        fuera = (valores < 0) | (valores > 100)
    elif campo == "promedio":
        fuera = (valores < 0) | (valores > 10)
    elif campo in CONTEOS:
        fuera = valores < 0
    else:
        return valores
    if fuera.sum():
        avisos.append(f"«{col}»: {int(fuera.sum())} valor(es) fuera de rango se dejaron vacíos (no se evalúan).")
        valores = valores.mask(fuera)
    return valores


def limpiar(crudo, mapeo, generar_codigos=False):
    """Devuelve (DataFrame limpio, lista de avisos).

    Solo conserva las columnas mapeadas (minimización de datos). Lo que no se
    puede interpretar se deja vacío: nunca se inventan valores.
    """
    avisos = []
    if generar_codigos or not mapeo.get("codigo"):
        codigos = pd.Series([f"E{i:03d}" for i in range(1, len(crudo) + 1)], index=crudo.index)
        avisos.append("Se generaron códigos automáticos por orden de fila (E001, E002…). "
                      "Conservá el archivo original para saber a qué estudiante corresponde cada código.")
    else:
        col = crudo[mapeo["codigo"]]
        if pd.api.types.is_numeric_dtype(col):
            col = col.map(lambda v: "" if pd.isna(v) else str(int(v)) if float(v).is_integer() else str(v))
        codigos = _texto(col)

    vacio = codigos.isin(["", "nan", "None"])
    dup = codigos.duplicated(keep="first") & ~vacio
    if vacio.sum():
        avisos.append(f"{int(vacio.sum())} fila(s) sin identificador se descartaron.")
    if dup.sum():
        avisos.append(f"{int(dup.sum())} fila(s) con identificador repetido se descartaron (se conservó la primera).")
    keep = ~vacio & ~dup
    crudo, codigos = crudo.loc[keep], codigos.loc[keep]

    out = pd.DataFrame({"codigo": codigos})
    for campo, col in mapeo.items():
        if campo == "codigo" or not col:
            continue
        valores, invalidos = (_a_binario if campo in BINARIOS else _a_numero)(crudo[col])
        if invalidos:
            avisos.append(f"«{col}»: {invalidos} valor(es) no interpretables se dejaron vacíos.")
        valores = _validar_rango(campo, valores, col, avisos)
        if valores.notna().sum() == 0:
            avisos.append(f"«{col}» no tiene valores válidos y se omitió: su regla no se aplicará.")
            continue
        out[campo] = valores
    return out.reset_index(drop=True), avisos
