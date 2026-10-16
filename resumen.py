"""Resumen del curso para autoridades (cifras agregadas) y exportación de resultados."""
from collections import Counter
import pandas as pd

ORDEN = ["Alto", "Medio", "Bajo", "Sin datos suficientes"]


def agregados(df, reglas):
    nombres = {r["id"]: r["nombre"] for r in reglas}
    dims = Counter(d for ds in df["dimensiones"] for d in ds)
    top = Counter(f["regla"] for fs in df["factores"] for f in fs).most_common(5)
    return {
        "total_estudiantes": int(len(df)),
        "estudiantes_por_nivel": {n: int((df["nivel"] == n).sum()) for n in ORDEN},
        "estudiantes_con_alerta_por_dimension": dict(dims.most_common()),
        "reglas_mas_frecuentes": [{"regla": nombres.get(i, i), "estudiantes": c} for i, c in top],
    }


def texto_resumen(ag):
    n = ag["total_estudiantes"]
    lineas = [f"Se analizaron **{n}** estudiantes."]
    for nivel in ORDEN:
        c = ag["estudiantes_por_nivel"][nivel]
        if c:
            lineas.append(f"- **{nivel}:** {c} ({100 * c / n:.0f} %)")
    if ag["estudiantes_con_alerta_por_dimension"]:
        d = ", ".join(f"{k} ({v})" for k, v in ag["estudiantes_con_alerta_por_dimension"].items())
        lineas.append(f"\nDimensiones con más estudiantes en alerta: {d}.")
    if ag["reglas_mas_frecuentes"]:
        r = "; ".join(f"{x['regla']} ({x['estudiantes']})" for x in ag["reglas_mas_frecuentes"])
        lineas.append(f"\nSeñales más frecuentes: {r}.")
    lineas.append("\n*Es una guía para priorizar el acompañamiento, no una decisión. "
                  "Los umbrales del prototipo no están validados.*")
    return "\n".join(lineas)


def exportar(df):
    orden = {n: i for i, n in enumerate(ORDEN)}
    t = pd.DataFrame({
        "codigo": df["codigo"], "nivel": df["nivel"], "indice": df["indice"], "puntaje": df["puntaje"],
        "dimensiones_con_alerta": df["dimensiones"].map(", ".join),
        "factores": df["factores"].map(lambda fs: " | ".join(f["texto"] for f in fs)),
        "nota": df["nota"],
    })
    t = t.sort_values(["nivel", "indice"], key=lambda s: s.map(orden) if s.name == "nivel" else -s.fillna(0))
    return t.to_csv(index=False).encode("utf-8-sig")
