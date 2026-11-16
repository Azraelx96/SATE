# Pruebas automáticas de SATE

Esta carpeta contiene todas las pruebas automáticas del proyecto. Usan **pytest**.
La guía completa, explicada paso a paso, está en el documento Word que acompaña esta carpeta.

## Cómo ejecutarlas (resumen)

Desde la carpeta principal del proyecto (la que tiene `app.py`), con el entorno virtual activado:

```
python -m pip install -r tests/requirements-test.txt
python -m pytest tests
```

O con doble clic en `tests/ejecutar_tests.bat`.

## Qué hay adentro

| Archivo | Qué prueba | Historias |
|---|---|---|
| `test_reglas.py` | El motor de reglas: puntos, bordes, niveles, escalamiento | HU-03, HU-05, HU-10 |
| `test_carga.py` | Lectura de CSV/Excel, limpieza e identidades | HU-01, HU-02, HU-11 |
| `test_almacenamiento.py` | Base de datos: legajos, DNI, observaciones | HU-02, HU-08, HU-13 |
| `test_orientacion.py` | Qué se envía a la IA y cómo se revisa lo que responde | HU-06 |
| `test_ia.py` | La conexión con Ollama (simulada) y la privacidad | HU-06, HU-11, HU-12 |
| `test_resumen.py` | Resumen para autoridades y CSV exportado | HU-12 |
| `test_app.py` | La pantalla completa, sin abrir el navegador | HU-01 a HU-13 |
| `test_probar_orientacion.py` | El script de evaluación manual de la IA | HU-06 |
| `test_proyecto.py` | Salud general: importaciones, `.gitignore`, dependencias | — |
| `conftest.py` | Piezas compartidas. Redirige la base de datos a una carpeta temporal |  |
| `pytest.ini`, `.coveragerc` | Configuración |  |

## Reglas de oro

- Las pruebas **nunca tocan** `datos/sate.db` (la base real): usan una temporal.
- Las pruebas con **Ollama real** están apagadas. Para activarlas: `set SATE_TESTS_OLLAMA=1` (Windows) y volver a ejecutar.
- Si una prueba falla después de un cambio en el código, **no se borra la prueba**: primero se averigua si el cambio fue intencional.
