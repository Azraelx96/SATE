"""SATE — Sistema de Alerta Temprana de Abandono. Ejecutar con: streamlit run app.py"""
from pathlib import Path

import pandas as pd
import streamlit as st
import almacenamiento

import carga
import ia
import resumen
from reglas import (calcular_curso, copiar_reglas, INDICE_MEDIO, INDICE_ALTO, ESCALAMIENTO_DIMENSIONES)

st.set_page_config(page_title="SATE", page_icon="📋", layout="wide")
informe_bd = almacenamiento.inicializar_bd()
st.title("SATE — Sistema de Alerta Temprana de Abandono")
st.caption("Prototipo. Las alertas son una ayuda para el tutor, no una decisión. "
           "El nivel de riesgo lo calculan reglas explicables; la IA no lo decide.")

COLORES = {"Alto": "🔴", "Medio": "🟡", "Bajo": "🟢", "Sin datos suficientes": "⚪"}
ORDEN = {"Alto": 0, "Medio": 1, "Bajo": 2, "Sin datos suficientes": 3}
NINGUNA, AUTO = "(no disponible)", "(generar códigos automáticos)"
ORIGEN_EJEMPLO = ""  # los datos de ejemplo usan el origen vacío (mantiene los legajos ya creados)


def aplicar_mapeo(mapeo, columnas):
    """Carga una sugerencia de mapeo en los selectores."""
    for campo in carga.CAMPOS:
        col = mapeo.get(campo)
        st.session_state[f"map_{campo}"] = col if col in columnas else (AUTO if campo == "codigo" else NINGUNA)


def cb_ia(columnas):
    try:
        aplicar_mapeo(ia.sugerir_mapeo(columnas, carga.CAMPOS), columnas)
        st.session_state["ia_msg"] = ("ok", "La IA sugirió el mapeo. Revisalo antes de continuar.")
    except Exception as e:  # noqa: BLE001
        st.session_state["ia_msg"] = ("error", f"No se pudo usar la IA: {e}")


def preparar_datos(datos, identidades, grupo):
    """
    Asigna a cada estudiante su legajo permanente (base de datos) y suma la
    preocupación que el tutor haya guardado, que alimenta la regla R12.
    """
    legajos = almacenamiento.sincronizar_alumnos(identidades, origen=grupo)
    datos = datos.copy()
    datos["legajo"] = legajos

    guardadas = almacenamiento.obtener_observaciones(legajos)
    if guardadas or "preocupacion_tutor" in datos.columns:
        desde_archivo = datos["preocupacion_tutor"] if "preocupacion_tutor" in datos.columns else None
        efectiva = []
        for i, legajo in enumerate(legajos):
            if legajo in guardadas:  # lo que guardó el tutor manda sobre el archivo
                efectiva.append(1.0 if guardadas[legajo]["preocupacion_tutor"] else 0.0)
            else:
                efectiva.append(float("nan") if desde_archivo is None else desde_archivo.iloc[i])
        serie = pd.Series(efectiva, index=datos.index, dtype="float64")
        if serie.notna().any():
            datos["preocupacion_tutor"] = serie
        else:
            datos = datos.drop(columns=["preocupacion_tutor"], errors="ignore")
    return datos


def paso_carga(archivo):
    """Lee el archivo, deja confirmar el mapeo de columnas y devuelve los datos limpios."""
    try:
        crudo = carga.leer_archivo(archivo)
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo leer el archivo: {e}")
        return None
    columnas = list(crudo.columns)
    firma = f"{archivo.name}-{archivo.size}"
    if st.session_state.get("firma") != firma or "map_codigo" not in st.session_state:
        st.session_state["firma"] = firma
        st.session_state.pop("ia_msg", None)
        aplicar_mapeo(carga.sugerir_mapeo(columnas), columnas)

    st.success(f"Archivo leído: {len(crudo)} filas y {len(columnas)} columnas.")
    personales = carga.columnas_personales(columnas)
    if personales:
        st.warning("Estas columnas parecen datos personales: se usan solo para reconocer a cada estudiante "
                   "(legajo) y **no entran al cálculo del riesgo**: " + ", ".join(personales))

    st.markdown("#### Relacioná las columnas de tu archivo con los datos del sistema")
    c1, c2 = st.columns([3, 2])
    with c2:
        st.button("✨ Sugerir con IA", on_click=cb_ia, args=(columnas,), disabled=not ia.disponible())
        st.caption("Se envían a la IA solo los **nombres de las columnas**, nunca los datos de los estudiantes."
                   if ia.disponible() else
                   "Ollama no está disponible o el modelo configurado no está instalado. "
                    "Podés continuar utilizando el mapeo automático básico.")
        if "ia_msg" in st.session_state:
            tipo, msg = st.session_state["ia_msg"]
            (st.success if tipo == "ok" else st.error)(msg)
    with c1:
        st.caption("Dejá en «(no disponible)» lo que tu instituto no registra: esa regla simplemente no se aplica.")
        for campo, desc in carga.CAMPOS.items():
            opciones = ([AUTO] if campo == "codigo" else [NINGUNA]) + columnas
            st.selectbox(desc, opciones, key=f"map_{campo}")

    elegido = {campo: st.session_state[f"map_{campo}"] for campo in carga.CAMPOS}
    usadas = [c for c in elegido.values() if c not in (NINGUNA, AUTO)]
    if len(usadas) != len(set(usadas)):
        st.error("Hay una misma columna asignada a más de un dato. Corregilo para continuar.")
        return None
    if elegido["codigo"] in personales:
        st.warning("La columna elegida como identificador parece un nombre o DNI y se mostraría en pantalla. "
                   "Conviene elegir «generar códigos automáticos».")
    mapeo = {k: v for k, v in elegido.items() if v not in (NINGUNA, AUTO)}
    if not [k for k in mapeo if k != "codigo"]:
        st.info("Elegí al menos una columna con datos para calcular el riesgo.")
        return None

    if len(mapeo) - ("codigo" in mapeo) < 3:
        st.warning("Con menos de 3 datos el índice es muy brusco y poco confiable. Conviene sumar más columnas.")
    grupo = st.text_input("Curso o nombre del grupo", value=Path(archivo.name).stem, key=f"grupo_{firma}",
                          help="Distingue códigos iguales de cursos distintos. Si el archivo trae DNI, "
                               "el estudiante se reconoce por DNI aunque cambie de curso o de fila.")
    limpio, avisos, identidades = carga.limpiar_con_identidades(
        crudo, mapeo, generar_codigos=(elegido["codigo"] == AUTO))
    with st.expander(f"Informe de calidad de datos ({len(avisos)} aviso(s))", expanded=bool(avisos)):
        for a in avisos or ["Sin observaciones."]:
            st.write("•", a)
        st.caption("Vista previa de los datos que se usarán (solo columnas mapeadas):")
        st.dataframe(limpio.head(), width="stretch", hide_index=True)
    return limpio, identidades, grupo.strip()


tab_datos, tab_panel, tab_resumen = st.tabs(["1. Cargar datos", "2. Panel del curso", "3. Resumen para autoridades"])

with tab_datos:
    fuente = st.radio("Origen de los datos", ["Datos de ejemplo (ficticios)", "Subir mi archivo (CSV o Excel)"],
                      horizontal=True)
    datos, identidades, grupo = None, None, ORIGEN_EJEMPLO
    if fuente.startswith("Datos"):
        datos = pd.read_csv("datos/alumnos_ficticios.csv")
        identidades = [{"codigo_origen": c} for c in datos["codigo"]]
        st.info("Usando 16 estudiantes ficticios. Pasá a «Subir mi archivo» para probar con los datos de tu instituto.")
    else:
        st.caption("Idealmente el archivo ya viene con un código o legajo en lugar de nombres. "
                   "Los datos académicos se procesan en memoria. En la base local (datos/sate.db) se guardan "
                   "el legajo de cada estudiante, su DNI y nombre si vienen en el archivo, y las observaciones que escribas.")
        archivo = st.file_uploader("Archivo .csv o .xlsx", type=["csv", "xlsx"])
        if archivo is not None:
            resultado = paso_carga(archivo)
            if resultado is not None:
                datos, identidades, grupo = resultado

if datos is None:
    for t in (tab_panel, tab_resumen):
        with t:
            st.info("Primero cargá los datos en la pestaña 1.")
    st.stop()

try:
    datos = preparar_datos(datos, identidades, grupo)
except ValueError as e:
    st.error(f"No se pudo identificar a los estudiantes: {e}")
    st.stop()
with tab_datos:
    st.caption(f"✔ {len(datos)} estudiantes de esta carga identificados con legajo permanente · "
               f"{len(almacenamiento.listar_alumnos())} registrados en la base de datos.")

# --- Reglas activas (HU-10): cada instituto activa las que usa ---
reglas = copiar_reglas()
with st.sidebar:
    st.header("Reglas activas")
    st.caption("Desactivá las reglas que no correspondan a tu instituto. Se aplican solo en esta sesión.")
    for r in reglas:
        falta = r["variable"] not in datos.columns
        r["activa"] = st.checkbox(f"{r['id']} · {r['nombre']}" + (" (sin datos)" if falta else ""),
                                  value=True, key=r["id"], disabled=falta)
    if informe_bd["observaciones_migradas"] or informe_bd["observaciones_sin_asignar"]:
        st.divider()
        st.caption(f"Base anterior: {informe_bd['observaciones_migradas']} observación(es) migradas, "
                   f"{informe_bd['observaciones_sin_asignar']} sin asignar.")

df = calcular_curso(datos, reglas)
obs_db = almacenamiento.obtener_observaciones(df["legajo"])


def marca_obs(legajo):
    o = obs_db.get(legajo)
    return "" if o is None else ("📝" if o["observacion"] else "") + ("⚠" if o["preocupacion_tutor"] else "")


with tab_panel:
    with st.expander("¿Cómo se calcula el riesgo?"):
        st.markdown(
            f"Cada regla suma puntos según su tramo (leve o grave). El **índice** es el puntaje sobre el máximo "
            f"posible de las reglas que se pudieron evaluar (0-100). **Medio** desde {INDICE_MEDIO}, **Alto** desde "
            f"{INDICE_ALTO}. Además, el nivel sube a Medio con alertas en {min(ESCALAMIENTO_DIMENSIONES)} dimensiones, "
            f"a Alto con {max(ESCALAMIENTO_DIMENSIONES)}, o si se llega al tramo grave de una regla crítica.")
        st.dataframe(pd.DataFrame([{
            "ID": r["id"], "Regla": r["nombre"], "Dimensión": r["dimension"],
            "Leve": r["umbral_leve"], "Pts leve": r["puntos_leve"],
            "Grave": r["umbral_grave"], "Pts grave": r["puntos_grave"],
            "Crítica": "sí" if r.get("critica") else "", "Activa": "sí" if r["activa"] else "no",
        } for r in reglas]), width="stretch", hide_index=True)

    cols = st.columns(4)
    for col, nivel in zip(cols, ORDEN):
        col.metric(f"{COLORES[nivel]} {nivel}", int((df["nivel"] == nivel).sum()))

    st.subheader("Panel del curso")
    filtro = st.radio("Filtrar por nivel", ["Todos"] + list(ORDEN), horizontal=True)
    vista = df if filtro == "Todos" else df[df["nivel"] == filtro]
    vista = vista.sort_values(["nivel", "indice"],
                              key=lambda s: s.map(ORDEN) if s.name == "nivel" else -s.fillna(0))
    st.dataframe(pd.DataFrame({
        "Legajo": vista["legajo"],
        "Código": vista["codigo"],
        "Nivel": vista["nivel"].map(lambda n: f"{COLORES[n]} {n}"),
        "Índice (0-100)": vista["indice"],
        "Dimensiones con alerta": vista["dimensiones"].map(lambda d: ", ".join(d)),
        "Obs.": vista["legajo"].map(marca_obs),
    }), width="stretch", hide_index=True)

    st.subheader("Ficha de estudiante")
    if len(vista):
        # La selección se recuerda por código (no por posición): al guardar una observación el
        # índice cambia y la lista se reordena, pero la ficha tiene que seguir siendo la misma.
        codigos = list(vista["codigo"])
        previo = st.session_state.get("ficha_codigo")
        codigo = st.selectbox("Elegí un código de estudiante", codigos,
                              index=codigos.index(previo) if previo in codigos else 0)
        st.session_state["ficha_codigo"] = codigo
        fila = df[df["codigo"] == codigo].iloc[0]
        st.markdown(f"### {codigo} — {COLORES[fila['nivel']]} {fila['nivel']}")
        legajo = fila["legajo"]
        alumno = almacenamiento.obtener_alumno_por_legajo(legajo) or {}
        nombre = " ".join(x for x in (alumno.get("nombre"), alumno.get("apellido")) if x)
        st.caption(f"Legajo {legajo}" + (f" · {nombre}" if nombre else ""))
        if pd.notna(fila["indice"]):
            st.write(f"Puntaje {fila['puntaje']:.0f} de {fila['maximo']:.0f} evaluables → índice {fila['indice']}")
        if fila["nota"]:
            st.info(fila["nota"])
        por_dim = {}
        for f in fila["factores"]:
            por_dim.setdefault(f["dimension"], []).append(f)
        for dim, factores in por_dim.items():
            st.markdown(f"**{dim}**")
            for f in factores:
                st.write(f"• {f['texto']}")
        if not fila["factores"] and fila["nivel"] == "Bajo":
            st.write("Ninguna regla se activó.")

        # --- Observaciones del docente (se guardan por legajo en la base de datos) ---
        st.markdown("#### 📝 Observaciones del docente")
        mensaje = st.session_state.pop("flash_obs", None)
        if mensaje:
            st.success(mensaje)
        guardada = obs_db.get(legajo)
        if guardada is not None:
            marca = f"Última actualización: {guardada['actualizado_en']}"
            if guardada["migrada"]:
                marca += " · migrada de la base anterior: conviene revisarla"
            st.caption(marca)
        previa = fila.get("preocupacion_tutor")
        marcada = guardada["preocupacion_tutor"] if guardada is not None else (pd.notna(previa) and previa == 1)
        with st.form(key=f"form_obs_{legajo}"):
            preocupa = st.checkbox("Registrar preocupación del tutor (suma a la regla R12 del semáforo)",
                                   value=bool(marcada))
            texto = st.text_area("Observación", value=guardada["observacion"] if guardada else "",
                                 max_chars=almacenamiento.MAX_OBSERVACION, height=120,
                                 help="Una observación por estudiante. Evitá datos sensibles (salud, situación familiar).")
            enviar = st.form_submit_button("Guardar observación")
        if enviar:
            try:
                almacenamiento.guardar_observacion(legajo, preocupa, texto)
                st.session_state["flash_obs"] = f"Observación de {legajo} guardada."
                st.rerun()
            except ValueError as e:
                st.error(str(e))

        st.button("Generar orientación IA para este estudiante (próximamente)", disabled=True)
    else:
        st.info("No hay estudiantes en este nivel.")

with tab_resumen:
    ag = resumen.agregados(df, reglas)
    st.markdown(resumen.texto_resumen(ag))
    st.download_button("⬇ Descargar resultados (CSV)", resumen.exportar(df), "resultados_sate.csv", "text/csv")
    st.warning("El archivo descargado contiene el nivel de riesgo de cada código: tratalo como información sensible.")

    st.markdown("#### Redacción con IA")
    if ia.disponible():
        st.caption("Se envían a la IA solo las cifras agregadas de arriba, sin códigos ni datos individuales.")
        if st.button("✨ Redactar resumen con IA"):
            try:
                with st.spinner("Redactando..."):
                    st.session_state["resumen_ia"] = ia.redactar_resumen(ag)
            except Exception as e:  # noqa: BLE001
                st.error(f"No se pudo usar la IA: {e}")
        if "resumen_ia" in st.session_state:
            st.markdown(st.session_state["resumen_ia"])
            st.caption("Texto generado por IA: revisalo antes de compartirlo.")
    else:
        st.info("Para utilizar esta función, iniciá Ollama y verificá que "
                "el modelo configurado esté instalado.")
