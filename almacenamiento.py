"""
Almacenamiento local de SATE (SQLite).

Qué guarda:
- Alumnos, cada uno con un legajo permanente (SATE-000001, SATE-000002...).
- Una observación docente por alumno, asociada al LEGAJO y no al código del
  archivo: los códigos automáticos (E001, E002...) dependen del orden de las
  filas y pueden cambiar de una carga a otra, el legajo no.

Cómo reconoce a un alumno:
- Si el archivo trae DNI, el DNI es la identidad. El código del archivo es solo
  una etiqueta de esa carga, así que el mismo alumno se reconoce aunque esté en
  otra fila o en otro archivo.
- Si no trae DNI (datos ficticios), la identidad es (origen, código).

Nota: versión de prototipo para datos ficticios. Guarda DNI y nombres tal como
llegan. Antes de usar datos reales hay que revisar esa decisión.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


CARPETA_DATOS = Path(__file__).resolve().parent / "datos"
RUTA_BD = CARPETA_DATOS / "sate.db"

MAX_OBSERVACION = 1000
GUARDAR_NOMBRES = True  # Si es False, nombre y apellido no se guardan.


def _ahora():
    return datetime.now().astimezone().isoformat(timespec="seconds")


@contextmanager
def conectar():
    """
    Abre una conexión a la base de datos.

    Al salir del bloque `with` confirma los cambios (o los revierte si hubo un
    error) y SIEMPRE cierra la conexión.
    """
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)

    conexion = sqlite3.connect(RUTA_BD)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")

    try:
        with conexion:
            yield conexion
    finally:
        conexion.close()


# ---------------------------------------------------------------------------
# Creación y migración de tablas
# ---------------------------------------------------------------------------

def inicializar_bd():
    """
    Crea las tablas si no existen y migra una base anterior sin borrar nada.

    Se puede llamar todas las veces que haga falta. Devuelve un informe con las
    observaciones de la tabla antigua que se pasaron al sistema por legajo.
    """
    with conectar() as conexion:

        # Tabla anterior (observaciones por código). Se conserva sin cambios.
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

        # Columna nueva: de qué curso o archivo viene el código.
        columnas = {fila["name"] for fila in conexion.execute("PRAGMA table_info(alumnos)")}
        if "origen" not in columnas:
            conexion.execute("ALTER TABLE alumnos ADD COLUMN origen TEXT NOT NULL DEFAULT ''")

        conexion.execute("CREATE INDEX IF NOT EXISTS idx_alumnos_dni ON alumnos(dni_normalizado)")
        conexion.execute("CREATE INDEX IF NOT EXISTS idx_alumnos_codigo ON alumnos(origen, codigo_origen)")

        # Observaciones nuevas: una por legajo.
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS observaciones (
                legajo TEXT PRIMARY KEY REFERENCES alumnos(legajo),
                preocupacion_tutor INTEGER NOT NULL DEFAULT 0
                    CHECK (preocupacion_tutor IN (0, 1)),
                observacion TEXT NOT NULL DEFAULT '',
                actualizado_en TEXT NOT NULL,
                migrada INTEGER NOT NULL DEFAULT 0
            )
            """
        )

        return _migrar_observaciones(conexion)


def _migrar_observaciones(conexion):
    """
    Pasa las observaciones de la tabla anterior (por código) a la nueva (por legajo).

    Solo migra una observación si su código corresponde a UN único alumno.
    Las ambiguas quedan en la tabla anterior y se cuentan en el informe.
    Las migradas se marcan con migrada = 1 para que se puedan revisar.
    """
    migradas = 0
    sin_asignar = 0

    antiguas = conexion.execute(
        "SELECT codigo, preocupacion_tutor, observacion, actualizado_en FROM seguimiento_docente"
    ).fetchall()

    for fila in antiguas:
        legajos = [
            r["legajo"]
            for r in conexion.execute(
                "SELECT legajo FROM alumnos WHERE codigo_origen = ? AND legajo IS NOT NULL",
                (fila["codigo"],),
            )
        ]

        if len(legajos) != 1:
            sin_asignar += 1
            continue

        ya_existe = conexion.execute(
            "SELECT 1 FROM observaciones WHERE legajo = ?", (legajos[0],)
        ).fetchone()
        if ya_existe:
            continue

        conexion.execute(
            """
            INSERT INTO observaciones
                (legajo, preocupacion_tutor, observacion, actualizado_en, migrada)
            VALUES (?, ?, ?, ?, 1)
            """,
            (legajos[0], fila["preocupacion_tutor"], fila["observacion"], fila["actualizado_en"]),
        )
        migradas += 1

    return {"observaciones_migradas": migradas, "observaciones_sin_asignar": sin_asignar}


# ---------------------------------------------------------------------------
# Observaciones (por legajo)
# ---------------------------------------------------------------------------

def _exigir_legajo(conexion, legajo):
    if not legajo:
        raise ValueError("El legajo del estudiante es obligatorio.")

    existe = conexion.execute(
        "SELECT 1 FROM alumnos WHERE legajo = ?", (str(legajo).strip(),)
    ).fetchone()
    if existe is None:
        raise ValueError(f"El legajo {legajo} no está registrado.")


def obtener_observacion(legajo):
    """Devuelve la observación de un alumno (vacía si todavía no tiene)."""
    with conectar() as conexion:
        _exigir_legajo(conexion, legajo)
        fila = conexion.execute(
            """
            SELECT legajo, preocupacion_tutor, observacion, actualizado_en, migrada
            FROM observaciones
            WHERE legajo = ?
            """,
            (str(legajo).strip(),),
        ).fetchone()

    if fila is None:
        return {
            "legajo": str(legajo).strip(),
            "preocupacion_tutor": False,
            "observacion": "",
            "actualizado_en": None,
            "migrada": False,
        }

    return {
        "legajo": fila["legajo"],
        "preocupacion_tutor": bool(fila["preocupacion_tutor"]),
        "observacion": fila["observacion"],
        "actualizado_en": fila["actualizado_en"],
        "migrada": bool(fila["migrada"]),
    }


def guardar_observacion(legajo, preocupacion_tutor, observacion):
    """Guarda o actualiza la observación de un alumno. Devuelve la fecha de guardado."""
    observacion = (observacion or "").strip()

    if len(observacion) > MAX_OBSERVACION:
        raise ValueError(f"La observación no puede superar los {MAX_OBSERVACION} caracteres.")

    actualizado_en = _ahora()

    with conectar() as conexion:
        _exigir_legajo(conexion, legajo)
        conexion.execute(
            """
            INSERT INTO observaciones
                (legajo, preocupacion_tutor, observacion, actualizado_en, migrada)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(legajo) DO UPDATE SET
                preocupacion_tutor = excluded.preocupacion_tutor,
                observacion = excluded.observacion,
                actualizado_en = excluded.actualizado_en,
                migrada = 0
            """,
            (str(legajo).strip(), int(bool(preocupacion_tutor)), observacion, actualizado_en),
        )

    return actualizado_en


def obtener_observaciones(legajos):
    """
    Devuelve las observaciones de varios alumnos de una sola vez.

    Resultado: {legajo: {"preocupacion_tutor": bool, "observacion": str, ...}}.
    Solo incluye a quienes tienen una observación guardada. Sirve, por ejemplo,
    para marcar en el panel qué alumnos ya tienen notas.
    """
    legajos = [str(x).strip() for x in legajos if x]
    resultado = {}

    with conectar() as conexion:
        for i in range(0, len(legajos), 500):
            grupo = legajos[i:i + 500]
            marcas = ",".join("?" * len(grupo))
            filas = conexion.execute(
                f"""
                SELECT legajo, preocupacion_tutor, observacion, actualizado_en, migrada
                FROM observaciones
                WHERE legajo IN ({marcas})
                """,
                grupo,
            ).fetchall()

            for fila in filas:
                resultado[fila["legajo"]] = {
                    "preocupacion_tutor": bool(fila["preocupacion_tutor"]),
                    "observacion": fila["observacion"],
                    "actualizado_en": fila["actualizado_en"],
                    "migrada": bool(fila["migrada"]),
                }

    return resultado


# ---------------------------------------------------------------------------
# Alumnos y legajos
# ---------------------------------------------------------------------------

def _normalizar_dni(dni):
    """Deja solo los dígitos del DNI (sin puntos, espacios ni '.0' de Excel)."""
    if dni is None:
        return None

    texto = str(dni).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]

    digitos = "".join(c for c in texto if c.isdigit())
    return digitos or None


def _registrar(conexion, codigo_origen, dni, nombre, apellido, origen):
    """Reconoce o crea un alumno usando una conexión ya abierta. Devuelve el legajo."""
    codigo_origen = str(codigo_origen or "").strip() or None
    origen = str(origen or "").strip()
    dni_normalizado = _normalizar_dni(dni)
    nombre = str(nombre or "").strip() or None
    apellido = str(apellido or "").strip() or None

    if not GUARDAR_NOMBRES:
        nombre = apellido = None

    if not codigo_origen and not dni_normalizado:
        raise ValueError("Falta el código de origen o el DNI del alumno.")

    if dni_normalizado:
        # 1. El DNI manda: reconoce al alumno aunque cambie su código o su fila.
        alumno = conexion.execute(
            "SELECT id, legajo, codigo_origen FROM alumnos WHERE dni_normalizado = ?",
            (dni_normalizado,),
        ).fetchone()

        if alumno is not None:
            if codigo_origen and not alumno["codigo_origen"]:
                conexion.execute(
                    "UPDATE alumnos SET codigo_origen = ?, origen = ? WHERE id = ?",
                    (codigo_origen, origen, alumno["id"]),
                )
            return alumno["legajo"]

        # 2. Alumno cargado antes sin DNI: se le completa el DNI.
        if codigo_origen:
            alumno = conexion.execute(
                """
                SELECT id, legajo FROM alumnos
                WHERE origen = ? AND codigo_origen = ?
                  AND COALESCE(dni_normalizado, '') = ''
                ORDER BY id LIMIT 1
                """,
                (origen, codigo_origen),
            ).fetchone()

            if alumno is not None:
                conexion.execute(
                    """
                    UPDATE alumnos
                    SET dni_normalizado = ?,
                        nombre = COALESCE(nombre, ?),
                        apellido = COALESCE(apellido, ?)
                    WHERE id = ?
                    """,
                    (dni_normalizado, nombre, apellido, alumno["id"]),
                )
                return alumno["legajo"]

    else:
        # Sin DNI: la identidad es (origen, código).
        alumno = conexion.execute(
            """
            SELECT legajo FROM alumnos
            WHERE origen = ? AND codigo_origen = ?
            ORDER BY id LIMIT 1
            """,
            (origen, codigo_origen),
        ).fetchone()

        if alumno is not None:
            return alumno["legajo"]

    # 3. Alumno nuevo: el legajo se arma con el id que asigna la base de datos.
    cursor = conexion.execute(
        """
        INSERT INTO alumnos
            (codigo_origen, dni_normalizado, nombre, apellido, origen, creado_en)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (codigo_origen, dni_normalizado, nombre, apellido, origen, _ahora()),
    )
    legajo = f"SATE-{cursor.lastrowid:06d}"
    conexion.execute("UPDATE alumnos SET legajo = ? WHERE id = ?", (legajo, cursor.lastrowid))
    return legajo


def registrar_alumno(codigo_origen=None, dni=None, nombre=None, apellido=None, origen=""):
    """Reconoce o registra un alumno y devuelve su legajo permanente."""
    with conectar() as conexion:
        return _registrar(conexion, codigo_origen, dni, nombre, apellido, origen)


def sincronizar_alumnos(alumnos, origen=""):
    """
    Reconoce o registra a todos los alumnos de una carga y devuelve sus legajos,
    en el mismo orden en que llegaron.

    Recibe una lista de diccionarios con: codigo_origen, dni, nombre, apellido
    (y opcionalmente origen). Es todo o nada: si un alumno no se puede
    identificar, no se guarda ninguno.
    """
    legajos = []

    with conectar() as conexion:
        for numero, alumno in enumerate(alumnos, start=1):
            try:
                legajo = _registrar(
                    conexion,
                    alumno.get("codigo_origen"),
                    alumno.get("dni"),
                    alumno.get("nombre"),
                    alumno.get("apellido"),
                    alumno.get("origen", origen),
                )
            except ValueError as error:
                raise ValueError(f"Fila {numero}: {error}") from error

            legajos.append(legajo)

    return legajos


def obtener_alumno_por_legajo(legajo):
    """Obtiene un alumno mediante su legajo permanente."""
    if not legajo:
        return None

    with conectar() as conexion:
        fila = conexion.execute(
            """
            SELECT id, legajo, codigo_origen, origen, dni_normalizado,
                   nombre, apellido, creado_en
            FROM alumnos
            WHERE legajo = ?
            """,
            (str(legajo).strip(),),
        ).fetchone()

    return dict(fila) if fila else None


def listar_alumnos():
    """Devuelve los alumnos registrados sin exponer sus datos personales."""
    with conectar() as conexion:
        filas = conexion.execute(
            """
            SELECT legajo, codigo_origen, origen, creado_en
            FROM alumnos
            ORDER BY id
            """
        ).fetchall()

    return [dict(fila) for fila in filas]
