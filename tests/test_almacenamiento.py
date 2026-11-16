"""Pruebas del almacenamiento local (almacenamiento.py).  HU-02, HU-08 y HU-13.

IMPORTANTE: gracias a conftest.py, todas estas pruebas usan una base de datos
temporal. Nunca tocan datos/sate.db.
"""
import sqlite3

import numpy as np
import pytest

import almacenamiento as alm


# ---------------------------------------------------------------------------
# Seguridad de las propias pruebas y conexión
# ---------------------------------------------------------------------------
class TestAislamiento:
    def test_las_pruebas_no_usan_la_base_real(self, bd, raiz):
        assert alm.RUTA_BD != raiz / "datos" / "sate.db"
        assert "sate_prueba.db" in str(alm.RUTA_BD)

    def test_la_base_temporal_se_crea_en_el_primer_uso(self):
        assert not alm.RUTA_BD.exists()
        alm.inicializar_bd()
        assert alm.RUTA_BD.exists()


class TestConectar:
    def test_cierra_la_conexion_al_salir(self, bd):
        """Regresión: conexiones que quedaban abiertas."""
        with alm.conectar() as conexion:
            conexion.execute("SELECT 1")
        with pytest.raises(sqlite3.ProgrammingError):
            conexion.execute("SELECT 1")

    def test_confirma_los_cambios_si_todo_sale_bien(self, bd):
        with alm.conectar() as c:
            c.execute("INSERT INTO alumnos (codigo_origen, creado_en) VALUES ('X', 'hoy')")
        with alm.conectar() as c:
            assert c.execute("SELECT COUNT(*) FROM alumnos").fetchone()[0] == 1

    def test_revierte_los_cambios_si_hay_un_error(self, bd):
        with pytest.raises(RuntimeError):
            with alm.conectar() as c:
                c.execute("INSERT INTO alumnos (codigo_origen, creado_en) VALUES ('X', 'hoy')")
                raise RuntimeError("falla a mitad de camino")
        with alm.conectar() as c:
            assert c.execute("SELECT COUNT(*) FROM alumnos").fetchone()[0] == 0

    def test_las_claves_foraneas_estan_activadas(self, bd):
        with pytest.raises(sqlite3.IntegrityError):
            with alm.conectar() as c:
                c.execute("INSERT INTO observaciones (legajo, actualizado_en) VALUES ('NO-EXISTE', 'hoy')")

    def test_preocupacion_solo_acepta_0_o_1(self, bd):
        legajo = alm.registrar_alumno(codigo_origen="A1")
        with pytest.raises(sqlite3.IntegrityError):
            with alm.conectar() as c:
                c.execute("INSERT INTO observaciones (legajo, preocupacion_tutor, actualizado_en) "
                          "VALUES (?, 2, 'hoy')", (legajo,))


class TestInicializar:
    def test_se_puede_llamar_muchas_veces(self):
        alm.inicializar_bd()
        alm.inicializar_bd()
        alm.registrar_alumno(codigo_origen="A1")
        alm.inicializar_bd()
        assert len(alm.listar_alumnos()) == 1   # no borra nada

    def test_crea_las_tablas_esperadas(self, bd):
        with alm.conectar() as c:
            tablas = {f["name"] for f in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"alumnos", "observaciones", "seguimiento_docente"} <= tablas

    def test_el_informe_tiene_las_dos_cuentas(self):
        assert alm.inicializar_bd() == {"observaciones_migradas": 0, "observaciones_sin_asignar": 0}


# ---------------------------------------------------------------------------
# Reconocer alumnos y legajos (HU-02)
# ---------------------------------------------------------------------------
class TestNormalizarDni:
    @pytest.mark.parametrize("entrada, esperado", [
        ("30.111.222", "30111222"),
        ("30111222", "30111222"),
        (" 30111222 ", "30111222"),
        (30111222, "30111222"),
        (30111222.0, "30111222"),        # así llega un DNI desde Excel
        (np.int64(30111222), "30111222"),
        ("DNI 30111222", "30111222"),
        (None, None),
        ("", None),
        ("sin dato", None),
    ])
    def test_normalizar_dni(self, entrada, esperado):
        assert alm._normalizar_dni(entrada) == esperado


class TestLegajos:
    def test_los_legajos_son_correlativos_y_permanentes(self, bd):
        assert alm.registrar_alumno(codigo_origen="A1") == "SATE-000001"
        assert alm.registrar_alumno(codigo_origen="A2") == "SATE-000002"
        assert alm.registrar_alumno(codigo_origen="A1") == "SATE-000001"

    @pytest.mark.parametrize("dni_nuevo", ["30.111.222", " 30111222 ", 30111222, 30111222.0, "30111222"])
    def test_el_mismo_dni_en_cualquier_formato_es_el_mismo_legajo(self, bd, dni_nuevo):
        primero = alm.registrar_alumno(codigo_origen="A1", dni="30111222")
        assert alm.registrar_alumno(codigo_origen="A1", dni=dni_nuevo) == primero

    def test_el_dni_reconoce_al_alumno_aunque_cambie_de_codigo_y_de_curso(self, bd):
        a = alm.registrar_alumno(codigo_origen="A1", dni="30111222", origen="1A")
        b = alm.registrar_alumno(codigo_origen="ZZ9", dni="30111222", origen="2B")
        assert a == b
        assert len(alm.listar_alumnos()) == 1

    def test_dnis_distintos_son_personas_distintas_aunque_compartan_codigo(self, bd):
        a = alm.registrar_alumno(codigo_origen="A1", dni="30111222", origen="1A")
        b = alm.registrar_alumno(codigo_origen="A1", dni="30333444", origen="1A")
        assert a != b

    def test_sin_dni_el_mismo_codigo_y_origen_es_la_misma_persona(self, bd):
        assert alm.registrar_alumno(codigo_origen="A1", origen="1A") == \
               alm.registrar_alumno(codigo_origen="A1", origen="1A")

    def test_sin_dni_el_mismo_codigo_en_otro_curso_es_otra_persona(self, bd):
        a = alm.registrar_alumno(codigo_origen="A1", origen="1A")
        b = alm.registrar_alumno(codigo_origen="A1", origen="2B")
        assert a != b

    def test_el_dni_que_aparece_despues_completa_el_registro_sin_cambiar_el_legajo(self, bd):
        sin_dni = alm.registrar_alumno(codigo_origen="A1", origen="1A")
        con_dni = alm.registrar_alumno(codigo_origen="A1", dni="30111222", nombre="Ana",
                                       apellido="Pérez", origen="1A")
        assert sin_dni == con_dni
        ficha = alm.obtener_alumno_por_legajo(sin_dni)
        assert ficha["dni_normalizado"] == "30111222"
        assert (ficha["nombre"], ficha["apellido"]) == ("Ana", "Pérez")
        assert len(alm.listar_alumnos()) == 1

    def test_sin_codigo_ni_dni_da_error_claro(self, bd):
        with pytest.raises(ValueError, match="código de origen o el DNI"):
            alm.registrar_alumno()

    def test_codigo_vacio_cuenta_como_faltante(self, bd):
        with pytest.raises(ValueError):
            alm.registrar_alumno(codigo_origen="   ")

    def test_se_puede_registrar_solo_con_dni(self, bd):
        legajo = alm.registrar_alumno(dni="30111222")
        assert legajo.startswith("SATE-")

    def test_guardar_nombres_apagado_no_guarda_nombre_ni_apellido(self, bd, monkeypatch):
        monkeypatch.setattr(alm, "GUARDAR_NOMBRES", False)
        legajo = alm.registrar_alumno(codigo_origen="A1", nombre="Ana", apellido="Pérez")
        ficha = alm.obtener_alumno_por_legajo(legajo)
        assert ficha["nombre"] is None and ficha["apellido"] is None

    def test_guardar_nombres_encendido_los_guarda(self, bd):
        legajo = alm.registrar_alumno(codigo_origen="A1", nombre="Ana", apellido="Pérez")
        ficha = alm.obtener_alumno_por_legajo(legajo)
        assert (ficha["nombre"], ficha["apellido"]) == ("Ana", "Pérez")


class TestSincronizarAlumnos:
    def test_devuelve_los_legajos_en_el_mismo_orden(self, bd):
        legajos = alm.sincronizar_alumnos([{"codigo_origen": "A1"}, {"codigo_origen": "A2"},
                                           {"codigo_origen": "A3"}], origen="1A")
        assert legajos == ["SATE-000001", "SATE-000002", "SATE-000003"]

    def test_cargar_dos_veces_el_mismo_archivo_no_duplica_alumnos(self, bd):
        lista = [{"codigo_origen": "A1"}, {"codigo_origen": "A2"}]
        primera = alm.sincronizar_alumnos(lista, origen="1A")
        segunda = alm.sincronizar_alumnos(lista, origen="1A")
        assert primera == segunda
        assert len(alm.listar_alumnos()) == 2

    def test_mismo_dni_en_otra_fila_o_archivo_da_el_mismo_legajo(self, bd):
        primera = alm.sincronizar_alumnos([{"codigo_origen": "A1", "dni": "30111222"}], origen="1A")
        segunda = alm.sincronizar_alumnos([{"codigo_origen": "Z9", "dni": "30.111.222"}], origen="otro")
        assert primera == segunda

    def test_mismo_codigo_en_otro_curso_son_personas_distintas(self, bd):
        a = alm.sincronizar_alumnos([{"codigo_origen": "A1"}], origen="1A")
        b = alm.sincronizar_alumnos([{"codigo_origen": "A1"}], origen="2B")
        assert a != b

    def test_cada_alumno_puede_traer_su_propio_origen(self, bd):
        a, b = alm.sincronizar_alumnos([{"codigo_origen": "A1", "origen": "1A"},
                                        {"codigo_origen": "A1", "origen": "2B"}])
        assert a != b

    def test_es_todo_o_nada_si_una_fila_falla_no_se_guarda_ninguna(self, bd):
        lista = [{"codigo_origen": "A1"}, {"codigo_origen": "A2"}, {}]
        with pytest.raises(ValueError, match="Fila 3"):
            alm.sincronizar_alumnos(lista, origen="1A")
        assert alm.listar_alumnos() == []

    def test_lista_vacia_devuelve_lista_vacia(self, bd):
        assert alm.sincronizar_alumnos([]) == []

    def test_dos_filas_con_el_mismo_dni_en_la_misma_carga_comparten_legajo(self, bd):
        a, b = alm.sincronizar_alumnos([{"codigo_origen": "A1", "dni": "30111222"},
                                        {"codigo_origen": "A9", "dni": "30111222"}])
        assert a == b


class TestPrivacidadDeListados:
    def test_listar_alumnos_no_expone_datos_personales(self, bd):
        alm.registrar_alumno(codigo_origen="A1", dni="30111222", nombre="Ana", apellido="Pérez")
        fila = alm.listar_alumnos()[0]
        assert set(fila) == {"legajo", "codigo_origen", "origen", "creado_en"}

    def test_obtener_alumno_por_legajo_inexistente_o_vacio(self, bd):
        assert alm.obtener_alumno_por_legajo("SATE-999999") is None
        assert alm.obtener_alumno_por_legajo("") is None
        assert alm.obtener_alumno_por_legajo(None) is None


# ---------------------------------------------------------------------------
# Observaciones (HU-08 y HU-13)
# ---------------------------------------------------------------------------
@pytest.fixture
def dos_alumnos(bd):
    a = alm.registrar_alumno(codigo_origen="A1")
    b = alm.registrar_alumno(codigo_origen="A2")
    return a, b


class TestObservaciones:
    def test_sin_observacion_devuelve_valores_vacios(self, dos_alumnos):
        a, _ = dos_alumnos
        assert alm.obtener_observacion(a) == {
            "legajo": a, "preocupacion_tutor": False, "observacion": "",
            "actualizado_en": None, "migrada": False,
        }

    def test_guardar_y_leer(self, dos_alumnos):
        a, _ = dos_alumnos
        fecha = alm.guardar_observacion(a, True, "Faltó dos semanas por viaje.")
        o = alm.obtener_observacion(a)
        assert o["observacion"] == "Faltó dos semanas por viaje."
        assert o["preocupacion_tutor"] is True
        assert o["actualizado_en"] == fecha and o["migrada"] is False

    def test_guardar_de_nuevo_actualiza_y_no_duplica(self, dos_alumnos):
        a, _ = dos_alumnos
        alm.guardar_observacion(a, False, "primera")
        alm.guardar_observacion(a, True, "segunda")
        assert alm.obtener_observacion(a)["observacion"] == "segunda"
        with alm.conectar() as c:
            assert c.execute("SELECT COUNT(*) FROM observaciones").fetchone()[0] == 1

    def test_la_observacion_de_un_alumno_no_aparece_en_otro(self, dos_alumnos):
        """Regresión: observaciones que se mezclaban entre estudiantes."""
        a, b = dos_alumnos
        alm.guardar_observacion(a, True, "solo para A1")
        assert alm.obtener_observacion(b)["observacion"] == ""
        assert alm.obtener_observacion(b)["preocupacion_tutor"] is False

    def test_limite_de_1000_caracteres(self, dos_alumnos):
        a, _ = dos_alumnos
        alm.guardar_observacion(a, False, "x" * 1000)                # justo en el límite: se guarda
        with pytest.raises(ValueError, match="1000"):
            alm.guardar_observacion(a, False, "x" * 1001)
        assert len(alm.obtener_observacion(a)["observacion"]) == 1000   # la anterior sigue intacta

    def test_los_espacios_de_los_bordes_no_cuentan_para_el_limite(self, dos_alumnos):
        a, _ = dos_alumnos
        alm.guardar_observacion(a, False, "  " + "x" * 1000 + "  ")
        assert len(alm.obtener_observacion(a)["observacion"]) == 1000

    def test_observacion_vacia_o_none_se_guarda_como_texto_vacio(self, dos_alumnos):
        a, _ = dos_alumnos
        alm.guardar_observacion(a, True, None)
        assert alm.obtener_observacion(a)["observacion"] == ""

    def test_legajo_inexistente_da_error(self, bd):
        with pytest.raises(ValueError, match="no está registrado"):
            alm.guardar_observacion("SATE-999999", False, "hola")
        with pytest.raises(ValueError, match="no está registrado"):
            alm.obtener_observacion("SATE-999999")

    def test_legajo_vacio_da_error(self, bd):
        with pytest.raises(ValueError, match="obligatorio"):
            alm.guardar_observacion("", False, "hola")
        with pytest.raises(ValueError, match="obligatorio"):
            alm.obtener_observacion(None)

    def test_el_legajo_se_acepta_con_espacios_alrededor(self, dos_alumnos):
        a, _ = dos_alumnos
        alm.guardar_observacion(f"  {a}  ", False, "ok")
        assert alm.obtener_observacion(a)["observacion"] == "ok"

    def test_preocupacion_acepta_valores_truthy_y_falsy(self, dos_alumnos):
        a, _ = dos_alumnos
        alm.guardar_observacion(a, 1, "")
        assert alm.obtener_observacion(a)["preocupacion_tutor"] is True
        alm.guardar_observacion(a, 0, "")
        assert alm.obtener_observacion(a)["preocupacion_tutor"] is False

    def test_la_observacion_acompana_al_legajo_aunque_cambie_el_codigo(self, bd):
        legajo = alm.registrar_alumno(codigo_origen="E001", dni="30111222")
        alm.guardar_observacion(legajo, True, "seguimiento")
        # En otra carga el mismo alumno llega con otro código y en otra fila:
        mismo = alm.registrar_alumno(codigo_origen="E007", dni="30111222")
        assert mismo == legajo
        assert alm.obtener_observacion(mismo)["observacion"] == "seguimiento"


class TestObservacionesEnLote:
    def test_devuelve_solo_a_quienes_tienen_observacion(self, dos_alumnos):
        a, b = dos_alumnos
        alm.guardar_observacion(a, True, "nota")
        r = alm.obtener_observaciones([a, b])
        assert list(r) == [a]
        assert r[a]["preocupacion_tutor"] is True and r[a]["observacion"] == "nota"

    def test_ignora_legajos_vacios(self, dos_alumnos):
        a, _ = dos_alumnos
        alm.guardar_observacion(a, False, "nota")
        assert list(alm.obtener_observaciones(["", None, a])) == [a]

    def test_lista_vacia(self, bd):
        assert alm.obtener_observaciones([]) == {}

    def test_funciona_con_mas_de_500_legajos(self, bd):
        """El código consulta de a 500: hay que probar que no pierde a nadie."""
        legajos = alm.sincronizar_alumnos([{"codigo_origen": f"A{i}"} for i in range(620)], origen="x")
        alm.guardar_observacion(legajos[0], True, "primero")
        alm.guardar_observacion(legajos[499], False, "quinientos")
        alm.guardar_observacion(legajos[500], True, "quinientos uno")
        alm.guardar_observacion(legajos[-1], True, "último")
        r = alm.obtener_observaciones(legajos)
        assert len(r) == 4
        assert r[legajos[-1]]["observacion"] == "último"
        assert r[legajos[500]]["observacion"] == "quinientos uno"


# ---------------------------------------------------------------------------
# Migración de la tabla anterior (por código) a la nueva (por legajo)
# ---------------------------------------------------------------------------
def insertar_antigua(codigo, preocupacion, texto):
    with alm.conectar() as c:
        c.execute("INSERT INTO seguimiento_docente (codigo, preocupacion_tutor, observacion, actualizado_en) "
                  "VALUES (?, ?, ?, '2026-01-01T10:00:00')", (codigo, preocupacion, texto))


class TestMigracion:
    def test_migra_la_observacion_cuando_el_codigo_corresponde_a_un_solo_alumno(self, bd):
        legajo = alm.registrar_alumno(codigo_origen="A1", origen="1A")
        insertar_antigua("A1", 1, "vieja")
        informe = alm.inicializar_bd()
        assert informe == {"observaciones_migradas": 1, "observaciones_sin_asignar": 0}
        o = alm.obtener_observacion(legajo)
        assert o["observacion"] == "vieja" and o["preocupacion_tutor"] is True and o["migrada"] is True

    def test_no_migra_si_el_codigo_es_ambiguo(self, bd):
        alm.registrar_alumno(codigo_origen="A1", origen="1A")
        alm.registrar_alumno(codigo_origen="A1", origen="2B")      # mismo código, dos personas
        insertar_antigua("A1", 0, "ambigua")
        assert alm.inicializar_bd() == {"observaciones_migradas": 0, "observaciones_sin_asignar": 1}

    def test_no_migra_si_no_hay_ningun_alumno_con_ese_codigo(self, bd):
        insertar_antigua("FANTASMA", 0, "huérfana")
        assert alm.inicializar_bd()["observaciones_sin_asignar"] == 1

    def test_no_pisa_una_observacion_nueva_ya_guardada(self, bd):
        legajo = alm.registrar_alumno(codigo_origen="A1", origen="1A")
        alm.guardar_observacion(legajo, False, "la nueva")
        insertar_antigua("A1", 1, "la vieja")
        alm.inicializar_bd()
        assert alm.obtener_observacion(legajo)["observacion"] == "la nueva"

    def test_migrar_dos_veces_no_duplica(self, bd):
        alm.registrar_alumno(codigo_origen="A1", origen="1A")
        insertar_antigua("A1", 0, "vieja")
        alm.inicializar_bd()
        assert alm.inicializar_bd() == {"observaciones_migradas": 0, "observaciones_sin_asignar": 0}

    def test_al_editar_una_observacion_migrada_deja_de_estar_marcada_como_migrada(self, bd):
        legajo = alm.registrar_alumno(codigo_origen="A1", origen="1A")
        insertar_antigua("A1", 0, "vieja")
        alm.inicializar_bd()
        alm.guardar_observacion(legajo, False, "revisada")
        assert alm.obtener_observacion(legajo)["migrada"] is False
