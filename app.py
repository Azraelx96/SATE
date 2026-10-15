"""Panel del curso (HU-03, HU-04, HU-05, HU-10). Ejecutar con: streamlit run app.py"""
import pandas as pd
import streamlit as st
from reglas import (calcular_curso, copiar_reglas, NIVELES, INDICE_MEDIO, INDICE_ALTO,
                    ESCALAMIENTO_DIMENSIONES)

st.set_page_config(page_title="SATE", page_icon="📋", layout="wide")
st.title("SATE — Sistema de Alerta Temprana de Abandono")
st.caption("Prototipo con datos ficticios. Las alertas son una ayuda para el tutor, no una decisión.")

COLORES = {"Alto": "🔴", "Medio": "🟡", "Bajo": "🟢", "Sin datos suficientes": "⚪"}
ORDEN = {"Alto": 0, "Medio": 1, "Bajo": 2, "Sin datos suficientes": 3}

# --- Configuración de reglas (HU-10): cada instituto activa las que usa ---
datos_crudos = pd.read_csv("datos/alumnos_ficticios.csv")
reglas = copiar_reglas()
with st.sidebar:
    st.header("Reglas activas")
    st.caption("Desactivá las reglas cuyo dato tu instituto no registra. Se aplican solo en esta sesión.")
    for r in reglas:
        falta = r["variable"] not in datos_crudos.columns
        r["activa"] = st.checkbox(f"{r['id']} · {r['nombre']}" + (" (sin datos)" if falta else ""),
                                  value=True, key=r["id"], disabled=falta)

df = calcular_curso(datos_crudos, reglas)

with st.expander("¿Cómo se calcula el riesgo?"):
    st.markdown(
        f"Cada regla suma puntos según su tramo (leve o grave). El **índice** es el puntaje "
        f"sobre el máximo posible de las reglas que se pudieron evaluar (0-100). "
        f"**Medio** desde {INDICE_MEDIO}, **Alto** desde {INDICE_ALTO}. "
        f"Además, el nivel sube a Medio si hay alertas en {min(ESCALAMIENTO_DIMENSIONES)} dimensiones, "
        f"a Alto si hay en {max(ESCALAMIENTO_DIMENSIONES)}, o si se llega al tramo grave de una regla crítica."
    )
    st.dataframe(pd.DataFrame([{
        "ID": r["id"], "Regla": r["nombre"], "Dimensión": r["dimension"],
        "Leve": r["umbral_leve"], "Pts leve": r["puntos_leve"],
        "Grave": r["umbral_grave"], "Pts grave": r["puntos_grave"],
        "Crítica": "sí" if r.get("critica") else "", "Activa": "sí" if r["activa"] else "no",
    } for r in reglas]), width="stretch", hide_index=True)

# --- Resumen por nivel ---
cols = st.columns(4)
for col, nivel in zip(cols, ["Alto", "Medio", "Bajo", "Sin datos suficientes"]):
    col.metric(f"{COLORES[nivel]} {nivel}", int((df["nivel"] == nivel).sum()))

# --- HU-04: listado ordenado por riesgo, con filtro ---
st.subheader("Panel del curso")
filtro = st.radio("Filtrar por nivel", ["Todos"] + list(ORDEN), horizontal=True)
vista = df if filtro == "Todos" else df[df["nivel"] == filtro]
vista = vista.sort_values(["nivel", "indice"], key=lambda s: s.map(ORDEN) if s.name == "nivel" else -s.fillna(0))

tabla = pd.DataFrame({
    "Código": vista["codigo"],
    "Nivel": vista["nivel"].map(lambda n: f"{COLORES[n]} {n}"),
    "Índice (0-100)": vista["indice"],
    "Dimensiones con alerta": vista["dimensiones"].map(lambda d: ", ".join(d)),
})
st.dataframe(tabla, width="stretch", hide_index=True)

# --- HU-05: desglose de factores de un estudiante ---
st.subheader("Ficha de estudiante")
if len(vista):
    codigo = st.selectbox("Elegí un código de estudiante", vista["codigo"])
    fila = df[df["codigo"] == codigo].iloc[0]
    st.markdown(f"### {codigo} — {COLORES[fila['nivel']]} {fila['nivel']}")
    if fila["indice"] is not None and pd.notna(fila["indice"]):
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
    st.button("Generar orientación IA (próximamente)", disabled=True)
else:
    st.info("No hay estudiantes en este nivel.")
