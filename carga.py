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
                 "numeroalumno", "nrolegajo", "nrodelegajo", "numerodelegajo", "nro", "n", "num", "numero"}
EXACTO_PROMEDIO = {"nota", "notas", "calificacion", "calificaciones", "promediogeneral"}

# (campo, grupos, excluir): cada grupo es una lista de fragmentos (alguno debe aparecer)
# y todos los grupos deben cumplirse. Van de lo más específico a lo más general.
#
# Punto 6: sinónimos ampliados. Para sumar los de un instituto nuevo, agregá el
# fragmento (en minúsculas, sin tildes ni espacios) en el grupo que corresponda.
PATRONES = [
    ("variacion_asistencia", [["variacion", "caida", "cambio", "evolucion", "diferencia", "dif"],
                              ["asistencia", "presentismo", "asist"]], []),
    ("variacion_promedio", [["variacion", "caida", "cambio", "evolucion", "diferencia", "dif"],
                            ["promedio", "nota", "calif"]], []),
    ("inasistencias_consecutivas", [["consecutiv", "seguid", "corrid", "continu"]], []),
    ("evaluaciones_ausente", [["evaluacion", "parcial", "examen", "eval"],
                              ["ausen", "falt", "inasist", "nosepresent", "nopresent"]], []),
    ("llegadas_tarde", [["tarde", "tardanza", "retraso", "impuntual"]], []),
    ("entregas_sin_presentar", [["entrega", "trabajospracticos", "tps", "tp", "actividades", "tareas"],
                                ["sinpresent", "pendient", "adeud", "nopresent", "sinentreg", "noentreg", "faltant"]],
     []),
    ("dias_sin_actividad", [["sinactiv", "inactiv", "sinparticip", "sinconex", "sinconect", "ultimaconexion",
                             "sinentrar", "sinacceso", "noentra", "noingresa", "siningres"]], []),
    ("materias_desaprobadas", [["desaprob", "reprob", "aplaz", "previas", "nodaprob"]], []),
    ("materias_recursadas", [["recurs", "repit", "recursa"]], []),
    ("preocupacion_tutor", [["preocup", "tutor", "observacion", "alerta"]], []),
    ("asistencia_pct", [["asistencia", "presentismo", "asist", "presencia"]],
     ["inasist", "consecut", "tarde", "variacion", "cambio", "caida"]),
    ("promedio", [["promedio", "notamedia", "notafinal", "calificacionfinal", "notagral"]], []),
]

# Punto 4: columnas que ya son resultados calculados (de otro sistema o de una
# corrida anterior). Nunca se usan como datos de entrada.
CALCULADAS = ["puntaje", "indice", "riesgo", "clasificacion", "semaforo", "reglasactiv",
              "dimensionescon", "estadodeevaluacion", "nivelsate"]

# Nombres exactos que, solos, indican una columna con el nombre del estudiante.
NOMBRES_SUELTOS = {"alumno", "alumna", "alumnoa", "alumnos", "estudiante", "estudiantes", "nombredelalumno",
                   "nombredelestudiante"}

# Palabras con que empiezan las filas de totales y notas al pie (punto 3).
INICIO_PIE = ("total", "promediodelcurso", "promediogeneraldelcurso", "promedios", "nota", "notas", "fuente",
              "observacionesgenerales", "elaborado", "firma", "referencias", "aclaracion")

EXTENSIONES_EXCEL = (".xlsx", ".xlsm", ".xls")
FILAS_A_REVISAR = 30  # el encabezado se busca en las primeras 30 filas


def normalizar(texto):
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t)


def es_personal(columna):
    n = normalizar(columna)
    return n in NOMBRES_SUELTOS or any(p in n for p in PALABRAS_PERSONALES)


def columnas_personales(columnas):
    """Columnas cuyo nombre sugiere datos personales (nombre, DNI, mail...)."""
    return [c for c in columnas if es_personal(c)]


def es_calculada(columna):
    n = normalizar(columna)
    return any(p in n for p in CALCULADAS)


def columnas_calculadas(columnas):
    """Columnas que parecen resultados ya calculados (índice, clasificación...): no se usan como datos."""
    return [c for c in columnas if es_calculada(c) and not es_personal(c)]

def detectar_columnas_identidad(columnas):
    """
    Detecta columnas personales para identificar alumnos internamente.
    Estas columnas no entran al cálculo del riesgo.

    Devuelve las claves: dni, nombre, apellido y nombre_completo (para columnas
    como «Apellido y Nombre», donde ambos datos vienen juntos).
    """
    resultado = {"dni": None, "nombre": None, "apellido": None, "nombre_completo": None}

    nombres_completos = {
        "apellidoynombre", "apellidoynombres", "apellidosynombres", "apellidosynombre",
        "nombreyapellido", "nombresyapellidos", "apellidonombre", "nombrecompleto",
    } | NOMBRES_SUELTOS

    for columna in columnas:
        n = normalizar(columna)

        if resultado["dni"] is None and (n in {"documento", "numerodedocumento"} or "dni" in n):
            resultado["dni"] = columna
        elif resultado["nombre_completo"] is None and n in nombres_completos:
            resultado["nombre_completo"] = columna
        elif resultado["nombre"] is None and n in {"nombre", "nombres"}:
            resultado["nombre"] = columna
        elif resultado["apellido"] is None and n in {"apellido", "apellidos"}:
            resultado["apellido"] = columna

    return resultado


def sugerir_mapeo(columnas):
    """Sugerencia automática sin IA: {campo: columna del archivo o None}."""
    norm = {c: normalizar(c) for c in columnas}
    personales = set(columnas_personales(columnas)) | set(columnas_calculadas(columnas))
    usadas, mapeo = set(), {}

    def buscar(pred):
        for c, n in norm.items():
            if c not in usadas and c not in personales and pred(n):
                usadas.add(c)
                return c
        return None

    mapeo["codigo"] = buscar(lambda n: n in EXACTO_CODIGO or "legajo" in n or "codigo" in n or "matricula" in n)
    for campo, grupos, excluir in PATRONES:
        mapeo[campo] = buscar(lambda n, g=grupos, e=excluir:
                              all(any(f in n for f in grupo) for grupo in g) and not any(x in n for x in e))
        if campo == "promedio" and mapeo[campo] is None:
            mapeo[campo] = buscar(lambda n: n in EXACTO_PROMEDIO)
    return mapeo


# ---------------------------------------------------------------------------
# Lectura flexible (puntos 1, 2, 3, 5 y 7): cada instituto arma el Excel a su
# manera. Se lee la hoja entera como una grilla "cruda" (sin suponer nada) y
# después se busca dónde está la tabla.
# ---------------------------------------------------------------------------

def _es_excel(nombre):
    return nombre.lower().endswith(EXTENSIONES_EXCEL)


def _vacia(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip())


def _grilla_desde_filas(filas):
    ancho = max((len(f) for f in filas), default=0)
    return pd.DataFrame([list(f) + [None] * (ancho - len(f)) for f in filas], dtype=object)


def listar_hojas(archivo):
    """Nombres de las hojas de un Excel (lista vacía para CSV)."""
    nombre = archivo.name.lower()
    if not _es_excel(nombre):
        return []
    if nombre.endswith(".xls"):
        return list(pd.ExcelFile(io.BytesIO(archivo.getvalue()), engine="xlrd").sheet_names)
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(archivo.getvalue()), read_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def leer_grilla(archivo, hoja=None):
    """
    Devuelve (grilla, combinadas). La grilla es la hoja tal cual, desde la celda A1,
    sin encabezados. `combinadas` son las celdas combinadas como tuplas 0-based
    (fila_ini, col_ini, fila_fin, col_fin); solo se conocen en .xlsx/.xlsm.
    """
    nombre = archivo.name.lower()
    datos = archivo.getvalue()
    if nombre.endswith(".xls"):
        g = pd.read_excel(io.BytesIO(datos), sheet_name=hoja or 0, header=None, engine="xlrd", dtype=object)
        return g.astype(object).where(g.notna(), None), []
    if _es_excel(nombre):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(datos), data_only=True)  # data_only: valor de las fórmulas
        ws = wb[hoja] if hoja else wb.worksheets[0]
        filas = [list(f) for f in ws.iter_rows(min_row=1, min_col=1, values_only=True)]
        combinadas = [(r.min_row - 1, r.min_col - 1, r.max_row - 1, r.max_col - 1) for r in ws.merged_cells.ranges]
        return _grilla_desde_filas(filas), combinadas
    # CSV: separador y codificación detectados; las filas pueden tener largo distinto
    import csv
    texto = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = datos.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ValueError("No se pudo leer el archivo CSV.")
    lineas = texto.splitlines()
    muestra = "\n".join(lineas[:50])
    try:
        sep = csv.Sniffer().sniff(muestra, delimiters=";,\t|").delimiter
    except csv.Error:
        sep = ";" if muestra.count(";") > muestra.count(",") else ","
    return _grilla_desde_filas(list(csv.reader(lineas, delimiter=sep))), []


def _vocabulario():
    frag = {f for _, grupos, _ in PATRONES for g in grupos for f in g if len(f) >= 4}
    frag |= {p for p in PALABRAS_PERSONALES if len(p) >= 3}
    frag |= {"legajo", "codigo", "matricula"}
    return frag


def _puntaje_fila(valores, vocab):
    """Cuántas celdas de la fila parecen nombres de columna conocidos."""
    textos = [v for v in valores if isinstance(v, str) and v.strip()]
    if len(textos) < 2:  # un título o una nota ocupan una sola celda
        return 0
    numeros = sum(1 for v in valores if isinstance(v, (int, float)) and not isinstance(v, bool) and not pd.isna(v))
    aciertos = 0
    for t in textos:
        n = normalizar(t)
        if n in EXACTO_CODIGO or n in NOMBRES_SUELTOS or any(f in n for f in vocab):
            aciertos += 1
    return aciertos - numeros  # una fila de encabezados casi no tiene números


def detectar_encabezado(grilla):
    """
    Índice (0-based) de la fila que más se parece a una fila de encabezados, y
    su puntaje. Si ninguna fila tiene al menos 2 nombres reconocibles, devuelve
    la primera fila con 3 o más celdas de texto (o la fila 0).
    """
    vocab = _vocabulario()
    mejor, puntaje = None, 0
    for i in range(min(FILAS_A_REVISAR, len(grilla))):
        p = _puntaje_fila(list(grilla.iloc[i]), vocab)
        if p > puntaje:
            mejor, puntaje = i, p
    if mejor is not None and puntaje >= 2:
        return mejor, puntaje
    for i in range(min(FILAS_A_REVISAR, len(grilla))):
        if sum(isinstance(v, str) and bool(v.strip()) for v in grilla.iloc[i]) >= 3:
            return i, 0
    return 0, 0


def elegir_hoja(archivo):
    """Punto 2: la hoja cuyo encabezado reconoce más columnas (o la primera)."""
    hojas = listar_hojas(archivo)
    if len(hojas) <= 1:
        return hojas[0] if hojas else None
    mejor, puntaje = hojas[0], -1
    for h in hojas:
        grilla, _ = leer_grilla(archivo, h)
        _, p = detectar_encabezado(grilla)
        if p > puntaje:
            mejor, puntaje = h, p
    return mejor


def _letra(i):
    letras = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        letras = chr(65 + r) + letras
    return letras


def _nombres_columnas(grilla, fila, combinadas):
    """
    Nombres de columna de la fila de encabezados. Si la fila de arriba tiene
    celdas combinadas que agrupan columnas («Asistencia» sobre «%», «Tardanzas»...),
    se combinan los dos niveles: «Asistencia %», «Asistencia Tardanzas».
    """
    ancho = grilla.shape[1]
    hijos = [None if _vacia(v) else str(v).strip() for v in grilla.iloc[fila]]
    padres = [None] * ancho
    dos_niveles = False
    for (f0, c0, f1, c1) in combinadas:
        valor = grilla.iat[f0, c0] if f0 < len(grilla) and c0 < ancho else None
        if _vacia(valor):
            continue
        if f0 == fila - 1 and f1 == fila - 1 and c1 > c0:  # grupo horizontal encima del encabezado
            dos_niveles = True
            for c in range(c0, min(c1, ancho - 1) + 1):
                padres[c] = str(valor).strip()
        elif f0 < fila <= f1:  # celda combinada vertical que incluye la fila de encabezados
            for c in range(c0, min(c1, ancho - 1) + 1):
                hijos[c] = hijos[c] or str(valor).strip()
    nombres = []
    for c in range(ancho):
        partes = [x for x in ((padres[c] if dos_niveles else None), hijos[c]) if x]
        if len(partes) == 2 and normalizar(partes[0]) in normalizar(partes[1]):
            partes = partes[1:]
        nombres.append(" ".join(partes) if partes else "")
    # nombres únicos y nunca vacíos
    vistos, unicos = {}, []
    for c, n in enumerate(nombres):
        n = n or f"Columna {_letra(c)}"
        if n in vistos:
            vistos[n] += 1
            n = f"{n} ({vistos[n]})"
        else:
            vistos[n] = 1
        unicos.append(n)
    return unicos, dos_niveles


def construir_tabla(grilla, combinadas, fila):
    """
    Arma la tabla a partir de la fila de encabezados (0-based) y la limpia:
    columnas y filas vacías, filas de totales y notas al pie, encabezados repetidos.
    Devuelve (DataFrame, avisos).
    """
    avisos = []
    nombres, dos_niveles = _nombres_columnas(grilla, fila, combinadas)
    datos = grilla.iloc[fila + 1:].copy()
    datos.columns = nombres
    if dos_niveles:
        avisos.append("El encabezado ocupa dos filas (con celdas combinadas): se unieron ambos niveles "
                      "en el nombre de cada columna.")

    # Columnas: se quitan las que no tienen nombre ni datos.
    sin_datos = [c for c in datos.columns if datos[c].map(_vacia).all()]
    quitar = [c for c in sin_datos if c.startswith("Columna ")]
    datos = datos.drop(columns=quitar)

    # Filas totalmente vacías.
    vacias = datos.apply(lambda f: all(_vacia(v) for v in f), axis=1)
    datos = datos[~vacias]

    # Filas que repiten el encabezado (pasa al exportar con «repetir títulos»).
    repetido = datos.apply(lambda f: sum(str(v).strip() == c for c, v in f.items() if not _vacia(v)) >= 3, axis=1)
    if repetido.sum():
        avisos.append(f"Se descartaron {int(repetido.sum())} fila(s) que repetían los encabezados.")
    datos = datos[~repetido]

    # Totales, notas al pie y filas-separador («Comisión B»): una sola celda con
    # texto en una tabla ancha, o una fila que empieza con «Total», «Nota»...
    def es_pie(f):
        llenas = [v for v in f if not _vacia(v)]
        if not llenas:
            return False
        primera = normalizar(llenas[0])
        if primera.startswith(INICIO_PIE):
            return True
        return len(llenas) == 1 and isinstance(llenas[0], str) and datos.shape[1] >= 4

    pie = datos.apply(es_pie, axis=1)
    if pie.sum():
        avisos.append(f"Se descartaron {int(pie.sum())} fila(s) de totales, notas o separadores "
                      "(no son estudiantes).")
    datos = datos[~pie]

    datos = datos.reset_index(drop=True).infer_objects()
    return datos, avisos


def leer_tabla(archivo, hoja=None, fila_encabezado=None):
    """
    Lectura completa y explicada. `fila_encabezado` es 1-based como en Excel
    (None = detectar). Devuelve un diccionario con:
      df, hoja, hojas, fila_encabezado (1-based), detectada (1-based),
      grilla (para la vista previa), avisos y calculadas.
    """
    hojas = listar_hojas(archivo)
    if hoja is None or hoja not in hojas:
        hoja = elegir_hoja(archivo)
    grilla, combinadas = leer_grilla(archivo, hoja)
    if grilla.empty:
        raise ValueError("La hoja está vacía.")
    detectada, _ = detectar_encabezado(grilla)
    fila = detectada if fila_encabezado is None else max(0, min(int(fila_encabezado) - 1, len(grilla) - 1))
    df, avisos = construir_tabla(grilla, combinadas, fila)

    if len(hojas) > 1:
        avisos.insert(0, f"El archivo tiene {len(hojas)} hojas; se usó «{hoja}».")
    if fila > 0:
        avisos.insert(0, f"Los encabezados están en la fila {fila + 1}: se ignoraron las {fila} fila(s) "
                         "de arriba (títulos o notas).")
    calculadas = columnas_calculadas(df.columns)
    if calculadas:
        avisos.append("Columnas con resultados ya calculados que no se usan como datos: " + ", ".join(calculadas))
    return {"df": df, "hoja": hoja, "hojas": hojas, "fila_encabezado": fila + 1, "detectada": detectada + 1,
            "grilla": grilla, "avisos": avisos, "calculadas": calculadas}


def leer_archivo(archivo, hoja=None, fila_encabezado=None):
    """Compatibilidad: devuelve solo el DataFrame (ver leer_tabla)."""
    return leer_tabla(archivo, hoja, fila_encabezado)["df"]


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
        # Excel guarda una celda con formato % como 0,85; hay planillas que mezclan ambos formatos.
        proporcion = (valores > 0) & (valores <= 1)
        if proporcion.sum():
            valores = valores.mask(proporcion, valores * 100)
            todos = int(proporcion.sum()) == int(valores.notna().sum())
            avisos.append(f"«{col}»: " + ("los valores estaban" if todos else f"{int(proporcion.sum())} valor(es) estaban")
                          + " entre 0 y 1; se interpretaron como proporción y se pasaron a %.")
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


def _limpiar_base(crudo, mapeo, generar_codigos=False):
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
    return out.reset_index(drop=True), avisos, list(crudo.index)


def limpiar(crudo, mapeo, generar_codigos=False):
    """Devuelve (DataFrame limpio, lista de avisos). Ver _limpiar_base."""
    out, avisos, _ = _limpiar_base(crudo, mapeo, generar_codigos)
    return out, avisos


def _valor(fila, columna):
    """Valor de una celda, o None si la columna no existe o la celda está vacía."""
    if columna is None:
        return None
    v = fila[columna]
    return None if pd.isna(v) else v


def limpiar_con_identidades(crudo, mapeo, generar_codigos=False):
    """
    Igual que limpiar(), pero además devuelve la identidad de cada estudiante.

    Devuelve (DataFrame limpio, avisos, identidades). `identidades` es una lista
    alineada fila por fila con el DataFrame limpio: cada elemento es un diccionario
    con codigo_origen, dni, nombre y apellido, listo para
    almacenamiento.sincronizar_alumnos(). El DNI y el nombre salen de las columnas
    personales del archivo original; no pasan al DataFrame de datos.
    """
    out, avisos, filas = _limpiar_base(crudo, mapeo, generar_codigos)
    ident = detectar_columnas_identidad(crudo.columns)

    identidades = []
    for codigo, indice in zip(out["codigo"], filas):
        fila = crudo.loc[indice]
        nombre = _valor(fila, ident["nombre"])
        apellido = _valor(fila, ident["apellido"])
        if nombre is None and apellido is None:
            nombre = _valor(fila, ident["nombre_completo"])
        identidades.append({
            "codigo_origen": codigo,
            "dni": _valor(fila, ident["dni"]),
            "nombre": nombre,
            "apellido": apellido,
        })

    return out, avisos, identidades
