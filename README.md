# SATE — Sistema de Alerta Temprana de Abandono

Prototipo de un sistema de alerta temprana que identifica estudiantes en riesgo de abandono a partir de los datos de cursada, pensado como apoyo para las tutorías de un instituto.

> **Estado: prototipo.** Funciona con datos ficticios. Todavía no fue validado con datos reales ni con un tutor, y no tiene inicio de sesión.

## Para qué sirve

Reúne en un solo lugar los datos que ya se registran (asistencia, notas, entregas y observaciones docentes), calcula con **reglas claras** un nivel de riesgo para cada estudiante (Bajo, Medio o Alto) y **explica por qué**. Sirve para llegar a tiempo con el acompañamiento y para ordenar el trabajo de tutoría según prioridad.

El sistema **no decide por nadie**: las alertas orientan el acompañamiento y nunca se usan para sancionar. La decisión y el contacto con el estudiante son siempre humanos.

## Hacia dónde apunta (versión final propuesta)

Estas ideas **no están implementadas**; son la dirección del proyecto:

- **Conexión con la base de datos del instituto**, para que los datos se actualicen solos y desaparezca el ciclo de exportar, limpiar y subir planillas.
- **Inicio de sesión y roles**, para que cada persona vea solo lo que le corresponde.
- **Alertas que se recalculan solas** cuando se registra asistencia o una nota.
- **Historial de intervenciones** con fecha y autor, y comparación entre períodos.

| Rol | Cómo lo usaría |
|---|---|
| Docente | Consulta las alertas de sus estudiantes y deja observaciones. |
| Tutor | Trabaja con un panel ordenado por prioridad, registra su seguimiento y prepara las entrevistas con ayuda de la IA. |
| Coordinación | Compara cursos y períodos, ajusta los umbrales y detecta casos sin seguimiento. |
| Dirección | Consulta el resumen institucional con cifras agregadas. |
| Administración | Gestiona usuarios, permisos y la conexión con los datos. |

Todo esto depende de que la institución autorice el acceso a sus datos y de que su sistema lo permita técnicamente.

## Qué hace hoy

- **Carga dinámica de datos:** se sube un archivo CSV o Excel aunque sus columnas se llamen distinto. La app sugiere sola a qué dato corresponde cada columna (con IA local opcional) y una persona lo confirma antes de calcular.
- **Control de calidad:** avisa de lo que no pudo interpretar (valores inválidos, filas repetidas, asistencia expresada de 0 a 1, etc.). Lo que no se puede interpretar se deja vacío: nunca se inventan valores.
- **Semáforo de riesgo** por estudiante, con **12 reglas** explicables.
- **Panel del curso** ordenado de mayor a menor riesgo, con filtro por nivel, legajo y marca de observaciones.
- **Ficha del estudiante** con el desglose de las reglas que se activaron.
- **Legajo permanente** para cada estudiante: la misma persona se reconoce aunque cambie de fila, de archivo o de curso.
- **Observaciones del docente:** una caja de texto y un check de preocupación en cada ficha, guardados en una base de datos local. La preocupación guardada **alimenta la regla R12** del semáforo.
- **Resumen para autoridades** con cifras agregadas (redactable con IA) y descarga de resultados en CSV.
- **Reglas activables:** desde el panel lateral se desactivan las reglas que el instituto no usa.

## Botón «Generar orientación para la tutoría» (pendiente)

Hoy el botón aparece en la ficha pero está **deshabilitado**; la función que redacta el texto existe en `ia.py` y falta conectarla.

Está pensado como una herramienta para el **tutor**, no para el estudiante: al revisar a alguien con nivel Medio o Alto, el modelo de IA local redacta una orientación breve (una fortaleza si los datos la respaldan, un aspecto a acompañar y una acción concreta) para ayudar a preparar la entrevista.

- Recibe el nivel, el índice y los factores de riesgo. **No recibe nombre ni DNI.**
- Se muestra con la leyenda «sugerencia generada por IA: la decisión final es del tutor».
- **No** conversa con el estudiante, **no** cambia el nivel de riesgo, **no** diagnostica y **no** propone sanciones.

## Cómo calcula el riesgo

El motor está en `reglas.py` y es **genérico**: usa solo variables académicas y de asistencia (sin datos socioeconómicos). Cada regla es un diccionario en la lista `REGLAS`; para agregar una se suma un diccionario y para descartarla se pone `"activa": False` (o se destilda en el panel lateral).

| Dimensión | Reglas |
|---|---|
| Asistencia | R01 asistencia general · R02 inasistencias consecutivas (crítica) · R03 llegadas tarde |
| Rendimiento | R04 promedio · R05 materias desaprobadas · R06 ausencias a evaluaciones |
| Compromiso | R07 entregas sin presentar · R08 días sin actividad o participación |
| Tendencia | R09 caída de asistencia · R10 caída de promedio (vs. período anterior) |
| Trayectoria | R11 materias recursadas |
| Observación | R12 preocupación registrada por el tutor |

**Puntaje e índice.** Cada regla suma puntos según su tramo, leve o grave (máximo 39 con todas activas). El **índice (0-100)** es el puntaje sobre el máximo de las reglas que se pudieron evaluar, de modo que un dato faltante no baja artificialmente el riesgo.

**Matriz de riesgo.** Índice menor a 15 → **Bajo**; de 15 a 29 → **Medio**; 30 o más → **Alto**. El nivel sube si hay alertas en 3 o más dimensiones (mínimo Medio) o en 5 o más (mínimo Alto), y pasa a Alto si se llega al tramo grave de una regla crítica (10 o más días de inasistencia seguidos). Si no se pudo evaluar al menos el 50 % del peso de las reglas activas, el estudiante queda como **Sin datos suficientes**.

Si el instituto no registra una variable, basta con no incluir esa columna: la regla se excluye y no cuenta para el cálculo.

Los umbrales y puntos son valores iniciales y **no están validados**: deben ajustarse con el tutor del curso. Aun sin datos socioeconómicos, algunas variables (por ejemplo, llegadas tarde) pueden relacionarse con las condiciones de vida del estudiante, por eso las alertas se usan para acompañar y nunca para sancionar.

## Inteligencia artificial local (Ollama)

El nivel de riesgo **lo calculan las reglas, no la IA**: así el resultado es reproducible y cada alerta tiene una razón verificable. La IA es **opcional** y corre en tu propia computadora con [Ollama](https://ollama.com), sin enviar datos a servicios externos. Se usa para:

- **Reconocer las columnas** del archivo. Recibe solo los nombres de las columnas, nunca datos de estudiantes.
- **Redactar el resumen para autoridades.** Recibe solo cifras agregadas.
- *(Pendiente)* **Orientación para la tutoría**, descrita arriba.

**Configuración:**

1. Instalá Ollama desde ollama.com y dejalo abierto.
2. Descargá un modelo, por ejemplo: `ollama pull qwen2.5:7b`. Los modelos de 7 mil millones de parámetros necesitan varios GB de memoria; si tu computadora es modesta, probá con uno más liviano.
3. Copiá `.env.example` como `.env` y completá:

```
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

Sin Ollama, el reconocimiento básico de columnas, el cálculo del semáforo y el resumen numérico funcionan igual. Los modelos livianos pueden redactar en español con menos calidad y equivocarse, por eso **todo texto generado debe ser revisado por una persona**.

## Base de datos

Se crea sola en `datos/sate.db` (SQLite). Guarda únicamente lo que debe persistir entre sesiones:

| Tabla | Qué guarda |
|---|---|
| `alumnos` | Legajo permanente (SATE-000001…), código del archivo, grupo de origen, y DNI y nombre si vienen en el archivo. |
| `observaciones` | Una por estudiante, asociada a su legajo: texto, preocupación del tutor y fecha de actualización. |
| `seguimiento_docente` | Tabla de la primera versión (por código). Se conserva y se migra sola a `observaciones` cuando es posible. |

Los datos académicos (asistencia, notas, entregas) **no se guardan**: se leen del archivo cargado. Con DNI, el DNI identifica a la persona; sin DNI, la identidad es el par (grupo, código). Abrir un archivo registra a sus estudiantes en la base.

## Requisitos

- Python 3.13 (se recomienda esta versión; con versiones muy nuevas algunas librerías pueden no tener instalador disponible).
- Git.
- Ollama (opcional, solo para las funciones de IA).

## Instalación (Windows)

```
py install 3.13
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

En macOS o Linux, el entorno virtual se usa con `.venv/bin/python` en lugar de `.venv\Scripts\python`.

## Ejecutar

**Con doble clic:** abrí `iniciar_sate.bat`, que está en la carpeta del proyecto.

**Desde la terminal:**

```
.venv\Scripts\python -m streamlit run app.py
```

Se abre en el navegador en `http://localhost:8501`. Para detenerla: `Ctrl+C` en la terminal, o cerrar la ventana del `.bat`.

Solo el cálculo de riesgo, por terminal: `.venv\Scripts\python reglas.py`

## Estructura del proyecto

```
SATE/
├── app.py                         # Interfaz: carga, panel, ficha, observaciones y resumen
├── carga.py                       # Lectura, mapeo de columnas, limpieza e identidades
├── reglas.py                      # Motor de reglas de riesgo
├── almacenamiento.py              # Base de datos: legajos y observaciones
├── ia.py                          # IA local con Ollama (mapeo y resumen)
├── resumen.py                     # Cifras agregadas y exportación de resultados
├── iniciar_sate.bat               # Inicia la aplicación con doble clic
├── datos/alumnos_ficticios.csv    # 16 estudiantes inventados (datos de ejemplo)
├── requirements.txt               # Librerías
├── .env.example                   # Modelo de configuración
└── README.md
```

## Datos de prueba

- `datos/alumnos_ficticios.csv` se usa como datos de ejemplo al abrir la app.
- Para probar la carga de un archivo propio, subí un CSV o Excel desde la pestaña «Cargar datos». Un Excel de prueba con 10 personajes (`alumnos_prueba_blackclover.xlsx`) sirve para ver cómo se reconocen las columnas de nombre y DNI.
- Cada archivo CSV de ejemplo tiene una fila por estudiante, con punto decimal (`7.5`, no `7,5`) y el espacio vacío para datos faltantes.

## Personalizar

- **Reglas:** la lista `REGLAS` está al comienzo de `reglas.py` (umbrales, puntos, dimensión y si son críticas).
- **Modelo de IA:** variable `OLLAMA_MODEL` en `.env`.

## Privacidad

- El repositorio es privado y contiene **solo datos ficticios**.
- `.env`, `datos_reales/` y las bases de datos (`*.db`) están excluidos en `.gitignore` y no deben subirse nunca.
- La base local guarda el DNI y el nombre sin cifrar. Es aceptable con datos ficticios, pero **hay que revisarlo antes de usar datos reales**.
- Antes de usar datos reales hace falta la autorización de la institución y definir consentimiento, dónde se aloja la base y quién accede.

## Pruebas

El motor de reglas, la carga de archivos, la base de datos y la interfaz se probaron en un entorno de ejecución con herramientas automáticas, incluida una copia de la base real. Las funciones de IA se probaron **solo con un servidor Ollama simulado, no con un modelo real**. Estas pruebas verifican que el sistema es coherente y explicable; no miden la capacidad real de detectar abandono, que requiere comparar las alertas con casos reales.

## Uso de IA en el desarrollo

Este proyecto se desarrolló con asistencia de **Claude** (Anthropic), usado en la planificación, la redacción de historias de usuario, el diseño técnico, la generación y revisión del código y de la documentación. El equipo revisa y ajusta el material generado. El detalle está en la documentación del proyecto.

## Próximos pasos

- Conectar el botón de orientación para la tutoría con la IA local.
- Historial de intervenciones con tipo de contacto y fecha (hoy hay una observación por estudiante).
- Inicio de sesión, roles y registro de accesos.
- Conexión con la base de datos del instituto, si lo permite su sistema.
- Validar los umbrales con el tutor del curso y con datos reales.
- Cifrar o reemplazar el DNI guardado antes de usar datos reales.
