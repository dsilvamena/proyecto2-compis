"""Expresividad: tamaño de cada tarea de bench/tareas/ en sus cuatro versiones.

    python bench/expresividad.py

Por cada archivo cuenta, sin comentarios ni líneas en blanco:
- lineas: líneas con código.
- tokens: tokens léxicos. El DSL usa el scanner del compilador; Python, el módulo
  tokenize (sin saltos de línea, indentación ni comentarios); SQL, palabras, números,
  cadenas, parámetros $x y símbolos.

Las versiones en Python incluyen los imports y la definición de ejecutar(), porque
también hay que escribirlos. Resultado en bench/resultados/expresividad.csv.
"""
import csv
import io
from pathlib import Path
import re
import sys
import tokenize

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH.parent))
from etl_dsl import scan  # noqa: E402

TAREAS = BENCH / "tareas"
SALIDA = BENCH / "resultados" / "expresividad.csv"
VERSIONES = {"dsl": "programa.etl", "polars": "polars_manual.py",
             "pandas": "pandas_manual.py", "duckdb": "consulta.sql"}
COMENTARIO = {"dsl": "//", "polars": "#", "pandas": "#", "duckdb": "--"}
TOKEN_SQL = re.compile(r"'[^']*'|\$\w+|\w+|[^\s\w]")
PYTHON_IGNORADOS = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                    tokenize.DEDENT, tokenize.ENDMARKER, tokenize.ENCODING}


def lineas_de_codigo(texto: str, comentario: str) -> int:
    """Líneas que tienen algo además de un comentario. Ninguna tarea tiene la marca de
    comentario dentro de una cadena, así que basta con cortar en la marca."""
    return sum(1 for linea in texto.splitlines() if linea.split(comentario, 1)[0].strip())


def tokens(texto: str, version: str) -> int:
    if version == "dsl":
        return len(scan(texto))
    if version == "duckdb":
        sin_comentarios = "\n".join(linea.split("--", 1)[0] for linea in texto.splitlines())
        return len(TOKEN_SQL.findall(sin_comentarios))
    return sum(1 for t in tokenize.generate_tokens(io.StringIO(texto).readline)
               if t.type not in PYTHON_IGNORADOS)


def main() -> int:
    filas = []
    for tarea in sorted(p for p in TAREAS.iterdir() if p.is_dir()):
        for version, archivo in VERSIONES.items():
            texto = (tarea / archivo).read_text(encoding="utf-8")
            filas.append({"tarea": tarea.name, "version": version,
                          "lineas": lineas_de_codigo(texto, COMENTARIO[version]),
                          "tokens": tokens(texto, version)})
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SALIDA, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=["tarea", "version", "lineas", "tokens"])
        escritor.writeheader()
        escritor.writerows(filas)
    for fila in filas:
        print(f"{fila['tarea']:20s} {fila['version']:7s} líneas={fila['lineas']:3d} tokens={fila['tokens']:4d}")
    print(f"Resultados en {SALIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
