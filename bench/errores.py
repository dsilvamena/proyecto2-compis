"""Detección de errores: el mismo error escrito en el DSL y en Polars a mano.

    python bench/errores.py
    docker compose run --rm bench python bench/errores.py

Cada caso de bench/errores/casos/ tiene un programa .etl y su equivalente .py en Polars
(una función ejecutar(datos) que devuelve un DataFrame). Ambos se ejecutan sobre los
mismos datos pequeños y se registra cuándo se detecta el error:

- DSL: "compilación" si compile_source lo reporta sin leer datos, "ejecución" si lo
  reporta el runtime, "no detectado" si el programa termina.
- Polars: "ejecución" si lanza una excepción, "silencioso" si devuelve un resultado.

Resultado en bench/resultados/errores.csv.
"""
import csv
import importlib.util
from pathlib import Path
import sys
import tempfile
import warnings

import polars as pl

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH.parent))
from etl_dsl.api import compile_source, run_source  # noqa: E402

CASOS = BENCH / "errores" / "casos"
SALIDA = BENCH / "resultados" / "errores.csv"
COLUMNAS = ["caso", "descripcion", "dsl_momento", "dsl_codigo", "dsl_mensaje",
            "polars_momento", "polars_detalle"]


def crear_datos(carpeta: Path) -> None:
    """Ventas con un canal y dos montos faltantes y un descuento 0; clientes con nombre de texto."""
    pl.DataFrame({
        "id": [1, 2, 3, 4, 5, 6],
        "cliente_id": [10, 10, 20, 20, 30, 30],
        "canal": ["web", "tienda", None, "web", "web", "tienda"],
        "monto": [120.0, None, 80.0, 300.0, None, 50.0],
        "descuento": [0.1, 0.0, 0.2, 0.0, 0.1, 0.05],
    }).write_parquet(carpeta / "ventas.parquet")
    pl.DataFrame({
        "codigo": [10, 20, 30],
        "nombre": ["Ana", "Luis", "Rosa"],
        "region": ["Lima", "Cusco", "Lima"],
    }).write_parquet(carpeta / "clientes.parquet")


def descripcion(programa: str) -> str:
    return programa.splitlines()[0].removeprefix("//").strip()


def dsl(programa: str, datos: Path) -> dict:
    compilado = compile_source(programa)
    if compilado["diagnostics"]:
        d = compilado["diagnostics"][0]
        return {"dsl_momento": "compilación", "dsl_codigo": d["code"], "dsl_mensaje": d["message"]}
    ejecutado = run_source(programa, base_dir=datos, root=datos)
    if ejecutado["diagnostics"]:
        d = ejecutado["diagnostics"][0]
        return {"dsl_momento": "ejecución", "dsl_codigo": d["code"], "dsl_mensaje": d["message"]}
    return {"dsl_momento": "no detectado", "dsl_codigo": "", "dsl_mensaje": ""}


def polars(archivo: Path, datos: Path) -> dict:
    spec = importlib.util.spec_from_file_location(archivo.stem, archivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resultado = modulo.ejecutar(datos)
    except Exception as exc:  # cualquier fallo cuenta como detección en ejecución
        mensaje = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        return {"polars_momento": "ejecución", "polars_detalle": f"{type(exc).__name__}: {mensaje}"[:200]}
    return {"polars_momento": "silencioso",
            "polars_detalle": f"{resultado.height} filas, columnas {resultado.columns}"}


def main() -> int:
    filas = []
    with tempfile.TemporaryDirectory() as tmp:
        datos = Path(tmp)
        crear_datos(datos)
        for programa in sorted(CASOS.glob("*.etl")):
            texto = programa.read_text(encoding="utf-8")
            fila = {"caso": programa.stem, "descripcion": descripcion(texto),
                    **dsl(texto, datos), **polars(programa.with_suffix(".py"), datos)}
            filas.append(fila)
            print(f"{fila['caso']:34s} DSL: {fila['dsl_momento']:12s} {fila['dsl_codigo']:22s} "
                  f"Polars: {fila['polars_momento']:10s} {fila['polars_detalle'][:60]}")
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=COLUMNAS)
        escritor.writeheader()
        escritor.writerows(filas)
    resumen = {}
    for fila in filas:
        resumen[fila["dsl_momento"], fila["polars_momento"]] = resumen.get(
            (fila["dsl_momento"], fila["polars_momento"]), 0) + 1
    print("\n(DSL, Polars): casos")
    for clave, n in sorted(resumen.items()):
        print(f"  {clave}: {n}")
    print(f"Resultados en {SALIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
