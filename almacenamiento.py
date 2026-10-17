"""
Almacenamiento local de observaciones docentes de SATE.

Versión de prototipo:
- Una observación editable por estudiante.
- Registro de la preocupación docente.
- Fecha de última actualización.
- Persistencia mediante SQLite.
"""

import sqlite3
from pathlib import Path
from datetime import datetime


CARPETA_DATOS = Path(__file__).resolve().parent / "datos"
RUTA_BD = CARPETA_DATOS / "sate.db"


def conectar():
    """Abre una conexión con la base de datos."""
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)

    conexion = sqlite3.connect(RUTA_BD)
    conexion.row_factory = sqlite3.Row

    return conexion

def inicializar_bd():
    """Crea las tablas necesarias si todavía no existen."""
    with conectar() as conexion:

        # Tabla existente: no se elimina ni se reemplaza.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS seguimiento_docente (
                codigo TEXT PRIMARY KEY,
                preocupacion_tutor INTEGER NOT NULL DEFAULT 0
                    CHECK (preocupacion_tutor IN (0, 1)),
                observacion TEXT NOT NULL DEFAULT '',
                actualizado_en TEXT NOT NULL
            )
            """
        )

        # Nueva tabla para identificar permanentemente a los alumnos.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS alumnos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                legajo TEXT UNIQUE,
                codigo_origen TEXT,
                dni_normalizado TEXT,
                nombre TEXT,
                apellido TEXT,
                creado_en TEXT NOT NULL
            )
            """
        )

def obtener_observacion(codigo):
    """Obtiene la observación asociada al código de un estudiante."""
    if not codigo:
        raise ValueError("El código del estudiante es obligatorio.")

    with conectar() as conexion:
        fila = conexion.execute(
            """
            SELECT codigo, preocupacion_tutor,
                   observacion, actualizado_en
            FROM seguimiento_docente
            WHERE codigo = ?
            """,
            (str(codigo),),
        ).fetchone()

    if fila is None:
        return {
            "codigo": str(codigo),
            "preocupacion_tutor": False,
            "observacion": "",
            "actualizado_en": None,
        }

    return {
        "codigo": fila["codigo"],
        "preocupacion_tutor": bool(fila["preocupacion_tutor"]),
        "observacion": fila["observacion"],
        "actualizado_en": fila["actualizado_en"],
    }


def guardar_observacion(codigo, preocupacion_tutor, observacion):
    """Guarda o actualiza la observación de un estudiante."""
    if not codigo:
        raise ValueError("El código del estudiante es obligatorio.")

    observacion = (observacion or "").strip()

    if len(observacion) > 1000:
        raise ValueError(
            "La observación no puede superar los 1000 caracteres."
        )

    actualizado_en = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    with conectar() as conexion:
        conexion.execute(
            """
            INSERT INTO seguimiento_docente (
                codigo,
                preocupacion_tutor,
                observacion,
                actualizado_en
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(codigo) DO UPDATE SET
                preocupacion_tutor = excluded.preocupacion_tutor,
                observacion = excluded.observacion,
                actualizado_en = excluded.actualizado_en
            """,
            (
                str(codigo),
                int(bool(preocupacion_tutor)),
                observacion,
                actualizado_en,
            ),
        )

    return actualizado_en

def registrar_alumno(
    codigo_origen=None,
    dni=None,
    nombre=None,
    apellido=None,
):
    """
    Registra un alumno y devuelve su legajo permanente.

    Reconoce:
    - Alumnos ficticios por su código de origen.
    - Alumnos reales por su DNI.

    Si no puede identificar al alumno con seguridad,
    no crea un registro nuevo.
    """

    codigo_origen = str(codigo_origen or "").strip() or None
    nombre = str(nombre or "").strip() or None
    apellido = str(apellido or "").strip() or None

    # Normalizar el DNI para evitar diferencias por puntos o espacios.
    dni_normalizado = None

    if dni is not None:
        dni_texto = str(dni).strip()

        if dni_texto.endswith(".0"):
            dni_texto = dni_texto[:-2]

        dni_texto = "".join(
            caracter for caracter in dni_texto
            if caracter.isdigit()
        )

        if dni_texto:
            dni_normalizado = dni_texto

    if not codigo_origen and not dni_normalizado:
        raise ValueError(
            "No se puede registrar al alumno sin un código de origen "
            "o un DNI válido."
        )

    creado_en = datetime.now().astimezone().isoformat(
        timespec="seconds"
    )

    with conectar() as conexion:

        # 1. Buscar por código de origen.
        if codigo_origen:
            alumno = conexion.execute(
                """
                SELECT id, legajo, dni_normalizado
                FROM alumnos
                WHERE codigo_origen = ?
                """,
                (codigo_origen,),
            ).fetchone()

            if alumno is not None:
                # Evitar asociar un código existente a otro DNI.
                dni_guardado = alumno["dni_normalizado"]

                if (
                    dni_guardado
                    and dni_normalizado
                    and dni_guardado != dni_normalizado
                ):
                    raise ValueError(
                        "El código de origen ya está asociado "
                        "a otro DNI."
                    )

                return alumno["legajo"]

        # 2. Buscar por DNI.
        if dni_normalizado:
            alumno = conexion.execute(
                """
                SELECT id, legajo, codigo_origen
                FROM alumnos
                WHERE dni_normalizado = ?
                """,
                (dni_normalizado,),
            ).fetchone()

            if alumno is not None:
                # No asociar un código de origen diferente
                # a un alumno ya identificado.
                codigo_guardado = alumno["codigo_origen"]

                if (
                    codigo_guardado
                    and codigo_origen
                    and codigo_guardado != codigo_origen
                ):
                    raise ValueError(
                        "El DNI ya está asociado a otro código "
                        "de origen. Se requiere revisar la identidad."
                    )

                return alumno["legajo"]

        # 3. Generar un nuevo legajo permanente.
        ultimo = conexion.execute(
            """
            SELECT COALESCE(MAX(id), 0) + 1 AS siguiente
            FROM alumnos
            """
        ).fetchone()

        nuevo_id = ultimo["siguiente"]
        legajo = f"SATE-{nuevo_id:06d}"

        conexion.execute(
            """
            INSERT INTO alumnos (
                id,
                legajo,
                codigo_origen,
                dni_normalizado,
                nombre,
                apellido,
                creado_en
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nuevo_id,
                legajo,
                codigo_origen,
                dni_normalizado,
                nombre,
                apellido,
                creado_en,
            ),
        )

    return legajo

def obtener_alumno_por_legajo(legajo):
            """Obtiene un alumno mediante su legajo permanente.""" 
            if not legajo: 
                return None 
            with conectar() as conexion: 
                fila = conexion.execute( 
                    """ SELECT id, legajo, codigo_origen,
                    dni_normalizado, nombre, apellido, creado_en
                    FROM alumnos 
                    WHERE legajo = ? 
                    """, (str(legajo).strip(),), 
                    ).fetchone()
                 
            return dict(fila) if fila else None 

def listar_alumnos(): 
    """Devuelve los alumnos registrados sin exponer sus datos personales.""" 
    with conectar() as conexion:
         filas = conexion.execute( 
             """ SELECT legajo, codigo_origen, creado_en 
             FROM alumnos ORDER BY id """ 
             ).fetchall() 
         
         return [dict(fila) for fila in filas]
def sincronizar_alumnos(alumnos):
    """
    Registra o reconoce alumnos y devuelve sus legajos permanentes.

    Recibe una lista de diccionarios con:
    codigo_origen, dni, nombre y apellido.

    Si un alumno no puede identificarse de forma segura,
    se detiene el proceso para evitar asignaciones incorrectas.
    """
    legajos = []

    for alumno in alumnos:
        try:
            legajo = registrar_alumno(
                codigo_origen=alumno.get("codigo_origen"),
                dni=alumno.get("dni"),
                nombre=alumno.get("nombre"),
                apellido=alumno.get("apellido"),
            )
        except ValueError as error:
            raise ValueError(
                f"No se pudo identificar al alumno: {error}"
            ) from error

        legajos.append(legajo)

    return legajos