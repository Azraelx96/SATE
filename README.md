# SATE — Sistema de Alerta Temprana de Abandono

Prototipo de sistema de alerta temprana que identifica estudiantes en riesgo de abandono a partir de datos de un curso, pensado como futuro apoyo para las tutorías del instituto.

> **Estado: prototipo.** Funciona con datos ficticios. Todavía no fue validado con datos reales ni con un tutor.

## Qué hace

- Calcula un **nivel de riesgo** (Bajo, Medio, Alto) para cada estudiante mediante reglas explícitas.
- Muestra un **panel del curso** ordenado de mayor a menor riesgo, con filtro por nivel.
- Muestra una **ficha por estudiante** que explica qué reglas se activaron y por qué.
- Permite activar o desactivar reglas desde el panel lateral, para adaptarlo a cada instituto.
- Identifica a los estudiantes por **código** (A001, A002…), sin nombres.

Las alertas son una ayuda para priorizar a quién contactar. La decisión siempre es del tutor.

## Cómo calcula el riesgo

El motor está en `reglas.py` y es **genérico**: usa solo variables académicas y de asistencia (sin datos socioeconómicos) que cualquier instituto suele registrar. Cada regla es un diccionario en la lista `REGLAS`; para agregar una se suma un diccionario y para descartarla se pone `"activa": False` (o se destilda en el panel lateral de la app).

**12 reglas en 6 dimensiones**, cada una con tramo leve y grave:

| Dimensión | Reglas |
|---|---|
| Asistencia | R01 asistencia general · R02 inasistencias consecutivas (crítica) · R03 llegadas tarde |
| Rendimiento | R04 promedio · R05 materias desaprobadas · R06 ausencias a evaluaciones |
| Compromiso | R07 entregas sin presentar · R08 días sin actividad o participación |
| Tendencia | R09 caída de asistencia vs. período anterior · R10 caída de promedio vs. período anterior |
| Trayectoria | R11 materias recursadas |
| Observación | R12 preocupación registrada por el tutor |

**Puntaje e índice.** Cada regla suma puntos según su tramo (máximo 39 con todas activas). El **índice (0-100)** es el puntaje sobre el máximo de las reglas que se pudieron evaluar, de modo que un dato faltante no baja artificialmente el riesgo.

**Matriz de riesgo.** Índice menor a 15 → **Bajo**; de 15 a 29 → **Medio**; 30 o más → **Alto**. El nivel se **escala** si hay alertas en 3 o más dimensiones a la vez (mínimo Medio) o en 5 o más (mínimo Alto), y pasa a Alto si se llega al tramo grave de una regla crítica (10 o más días de inasistencia seguidos). Si no se pudo evaluar al menos el 50 % del peso de las reglas activas, el estudiante queda como **Sin datos suficientes**.

Si el instituto no registra una variable, basta con no incluir esa columna en el CSV: la regla se excluye y no cuenta para el cálculo. Si la columna existe pero un estudiante tiene el dato vacío, esa regla no se evalúa para él.

Los umbrales y puntos son valores iniciales y **no están validados**: deben ajustarse con el tutor del curso. Aun sin datos socioeconómicos, algunas variables (por ejemplo llegadas tarde) pueden correlacionar con condiciones de vida del estudiante, por eso las alertas se usan para acompañar y nunca para sancionar.

## Rol de la inteligencia artificial

El nivel de riesgo **lo calculan las reglas, no la IA**. La IA (Claude, vía API de Anthropic) está prevista como asistente que, a partir de un resultado ya calculado, redacte un resumen y sugerencias de acompañamiento para el tutor (historia de usuario HU-06). A la IA se le enviará únicamente el código del estudiante y los factores de riesgo, nunca el nombre real. Si el servicio de IA falla, el panel sigue funcionando completo.

**Estado actual:** la conexión con la IA todavía no está implementada; el botón correspondiente está deshabilitado.

## Requisitos

- Python 3.13 (se recomienda esta versión; con versiones muy nuevas algunas librerías pueden no tener instalador disponible)
- Git

## Instalación (Windows)

```
py install 3.13
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

En macOS o Linux, el entorno virtual se usa con `.venv/bin/python` en lugar de `.venv\Scripts\python`.

## Ejecutar

Panel del curso:

```
.venv\Scripts\python -m streamlit run app.py
```

Se abre en el navegador en `http://localhost:8501`. Para detenerla, `Ctrl+C` en la terminal.

Solo el cálculo de riesgo, por terminal:

```
.venv\Scripts\python reglas.py
```

## Estructura del proyecto

```
SATE/
├── app.py                         # Interfaz (Streamlit): panel y ficha
├── reglas.py                      # Motor de reglas de riesgo
├── datos/
│   └── alumnos_ficticios.csv      # 16 estudiantes inventados
├── requirements.txt               # Librerías
├── .env.example                   # Modelo del archivo de clave de API
└── .gitignore
```

## Personalizar

- **Reglas:** la lista `REGLAS` está al comienzo de `reglas.py` (umbrales, puntos, dimensión y si son críticas).
- **Estudiantes:** una fila por estudiante en `datos/alumnos_ficticios.csv`. Código único, punto decimal (`7.5`, no `7,5`) y espacio vacío para datos faltantes. Columnas: `codigo, asistencia_pct, promedio, entregas_sin_presentar, preocupacion_tutor, materias_desaprobadas, evaluaciones_ausente, llegadas_tarde, inasistencias_consecutivas, dias_sin_actividad, variacion_asistencia, variacion_promedio, materias_recursadas`.

## Privacidad

- El repositorio es privado.
- Este repositorio contiene **solo datos ficticios**.
- `.env` (clave de API) y `datos_reales/` están excluidos en `.gitignore` y no deben subirse nunca.
- Cada persona que use la función de IA necesita su propia clave de API, guardada en su `.env` (ver `.env.example`).

## Uso de IA en el desarrollo

Este proyecto se desarrolló con asistencia de **Claude** (Anthropic), usado en la planificación, la redacción de historias de usuario, el diseño técnico y la generación del código inicial. El equipo revisa y ajusta el material generado. El detalle está en la documentación del proyecto.

## Próximos pasos

- Conectar la IA para generar orientación al tutor (HU-06).
- Registrar intervenciones de acompañamiento (HU-08).
- Carga de datos por parte de los docentes (HU-01).
- Validar los umbrales con el tutor del curso y con datos reales.
