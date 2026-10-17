"""SATE — Sistema de Alerta Temprana de Abandono. Ejecutar con: streamlit run app.py"""
import pandas as pd
import streamlit as st
import almacenamiento

import carga
import ia
import resumen
from reglas import (calcular_curso, copiar_reglas, INDICE_MEDIO, INDICE_ALTO, ESCALAMIENTO_DIMENSIONES)

st.set_page_config(page_title="SATE", page_icon="📋", layout="wide")
almacenamiento.inicializar_bd()
st.title("SATE — Sistema de Alerta Temprana de Abandono")
st.caption("Prototipo. Las alertas son una ayuda para el tutor, no una decisión. "
           "El nivel de riesgo lo calculan reglas explicables; la IA no lo decide.")

COLORES = {"Alto": "🔴", "Medio": "🟡", "Bajo": "🟢", "Sin datos suficientes": "⚪"}
ORDEN = {"Alto": 0, "Medio": 1, "Bajo": 2, "Sin datos suficientes": 3}
NINGUNA, AUTO = "(no disponible)", "(generar códigos automáticos)"


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
        st.warning("Estas columnas parecen datos personales y **no se usan**: " + ", ".join(personales))

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
    limpio, avisos = carga.limpiar(crudo, mapeo, generar_codigos=(elegido["codigo"] == AUTO))
    with st.expander(f"Informe de calidad de datos ({len(avisos)} aviso(s))", expanded=bool(avisos)):
        for a in avisos or ["Sin observaciones."]:
            st.write("•", a)
        st.caption("Vista previa de los datos que se usarán (solo columnas mapeadas):")
        st.dataframe(limpio.head(), width="stretch", hide_index=True)
    return limpio


tab_datos, tab_panel, tab_resumen = st.tabs(["1. Cargar datos", "2. Panel del curso", "3. Resumen para autoridades"])

with tab_datos:
    origen = st.radio("Origen de los datos", ["Datos de ejemplo (ficticios)", "Subir mi archivo (CSV o Excel)"],
                      horizontal=True)
    datos = None
    if origen.startswith("Datos"):
        datos = pd.read_csv("datos/alumnos_ficticios.csv")
        st.info("Usando 16 estudiantes ficticios. Pasá a «Subir mi archivo» para probar con los datos de tu instituto.")
    else:
        st.caption("Idealmente el archivo ya viene con un código o legajo en lugar de nombres. "
                   "Los datos se procesan en memoria y no se guardan en el proyecto.")
        archivo = st.file_uploader("Archivo .csv o .xlsx", type=["csv", "xlsx"])
        if archivo is not None:
            datos = paso_carga(archivo)

if datos is None:
    for t in (tab_panel, tab_resumen):
        with t:
            st.info("Primero cargá los datos en la pestaña 1.")
    st.stop()

# --- Reglas activas (HU-10): cada instituto activa las que usa ---
reglas = copiar_reglas()
with st.sidebar:
    st.header("Reglas activas")
    st.caption("Desactivá las reglas que no correspondan a tu instituto. Se aplican solo en esta sesión.")
    for r in reglas:
        falta = r["variable"] not in datos.columns
        r["activa"] = st.checkbox(f"{r['id']} · {r['nombre']}" + (" (sin datos)" if falta else ""),
                                  value=True, key=r["id"], disabled=falta)

df = calcular_curso(datos, reglas)

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
        "Código": vista["codigo"],
        "Nivel": vista["nivel"].map(lambda n: f"{COLORES[n]} {n}"),
        "Índice (0-100)": vista["indice"],
        "Dimensiones con alerta": vista["dimensiones"].map(lambda d: ", ".join(d)),
    }), width="stretch", hide_index=True)

    st.subheader("Ficha de estudiante")
    if len(vista):
        codigo = st.selectbox("Elegí un código de estudiante", vista["codigo"])
        fila = df[df["codigo"] == codigo].iloc[0]
        st.markdown(f"### {codigo} — {COLORES[fila['nivel']]} {fila['nivel']}")
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
