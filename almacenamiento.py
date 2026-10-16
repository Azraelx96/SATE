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
    """Crea la tabla de seguimiento si todavía no existe."""
    with conectar() as conexion:
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