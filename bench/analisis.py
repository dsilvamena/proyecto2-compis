"""Tablas y gráficos del reporte a partir de las mediciones.

    python bench/analisis.py                        # todas las corridas de bench/resultados/
    python bench/analisis.py --corridas A B --salida reporte/generado

Entradas:
- bench/resultados/<corrida>/tiempos.csv, de bench/run.py. Si una escala se midió en
  más de una corrida, se usa la que tiene más mediciones correctas de esa escala (y, si
  empatan, la corrida con más mediciones en total); las demás sirven para comparar
  equipos.
- bench/resultados/expresividad.csv (bench/expresividad.py).
- bench/resultados/errores.csv (bench/errores.py).

Salida en --salida: tablas/*.tex (booktabs), figuras/*.pdf y cifras.tex, con macros para
las cifras que el texto del reporte cita. En --web, el JSON que dibuja la página de
benchmarks del entorno web (etl_dsl/web/static/benchmarks.html). Por cada (escala, tarea, configuración) se
usan la mediana y el rango intercuartílico (RIC) de las repeticiones; los intervalos de
confianza de las razones son bootstrap del 95 % sobre la razón de medianas.
"""
import argparse
import json
from pathlib import Path
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BENCH = Path(__file__).resolve().parent
RESULTADOS = BENCH / "resultados"
WEB_JSON = BENCH.parent / "etl_dsl" / "web" / "static" / "benchmarks.json"
SEMILLA = 2026
REMUESTREOS = 10_000

TAREAS = ["resumen_precios", "ingreso_descuento", "ingreso_por_pedido", "limpieza_pedidos", "devoluciones"]
NOMBRE_TAREA = {"resumen_precios": "Resumen de precios", "ingreso_descuento": "Ingreso por descuento",
                "ingreso_por_pedido": "Ingreso por pedido", "limpieza_pedidos": "Limpieza de pedidos",
                "devoluciones": "Devoluciones"}
SISTEMAS = ["dsl", "polars", "duckdb", "pandas"]
NOMBRE = {"dsl": "DSL", "polars": "Polars", "duckdb": "DuckDB", "pandas": "Pandas"}
# Paleta categórica de referencia (orden fijo) y un marcador por sistema para impresión en gris.
COLOR = {"dsl": "#2a78d6", "polars": "#eb6834", "duckdb": "#1baf7a", "pandas": "#eda100"}
MARCADOR = {"dsl": "o", "polars": "s", "duckdb": "^", "pandas": "D"}
ARCHIVO_VERSION = {"dsl": "programa.etl", "polars": "polars_manual.py", "pandas": "pandas_manual.py",
                   "duckdb": "consulta.sql"}
PASES = ["dsl-O0", "dsl-constantes", "dsl-filtros", "dsl-codigo_muerto", "dsl"]
NOMBRE_PASE = {"dsl-O0": "O0", "dsl-constantes": "constantes", "dsl-filtros": "filtros",
               "dsl-codigo_muerto": "código muerto", "dsl": "todos"}
TINTA, TINTA_2, REJILLA = "#0b0b0b", "#52514e", "#e4e3df"


# Datos

def cargar_tiempos(corridas: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mediciones elegidas (una corrida por escala) y todas las mediciones."""
    todas = []
    for corrida in corridas:
        df = pd.read_csv(corrida / "tiempos.csv")
        df["corrida"] = corrida.name
        todas.append(df)
    todas = pd.concat(todas, ignore_index=True)
    ok = todas[todas.estado == "ok"]
    por_escala = ok.groupby(["sf", "corrida"]).size().rename("n").reset_index()
    por_escala["total"] = por_escala.corrida.map(ok.groupby("corrida").size())
    elegidas = (por_escala.sort_values(["sf", "n", "total"], ascending=[True, False, False])
                .drop_duplicates("sf").set_index("sf").corrida)
    eleccion = todas[todas.corrida == todas.sf.map(elegidas)]
    return eleccion, todas


def resumen(df: pd.DataFrame) -> pd.DataFrame:
    """Mediana, cuartiles y número de repeticiones por (sf, tarea, configuración)."""
    ok = df[df.estado == "ok"]
    g = ok.groupby(["sf", "tarea", "configuracion"])
    return pd.DataFrame({"mediana": g.segundos.median(), "q1": g.segundos.quantile(0.25),
                         "q3": g.segundos.quantile(0.75), "n": g.segundos.size(),
                         "memoria_mb": g.memoria_mb.median(), "compilacion_s": g.compilacion_s.median()})


def razon_ic(a: np.ndarray, b: np.ndarray, azar: np.random.Generator) -> tuple[float, float, float]:
    """Razón de medianas a/b con intervalo bootstrap del 95 %."""
    ia = azar.integers(0, len(a), (REMUESTREOS, len(a)))
    ib = azar.integers(0, len(b), (REMUESTREOS, len(b)))
    remuestreo = np.median(a[ia], axis=1) / np.median(b[ib], axis=1)
    return float(np.median(a) / np.median(b)), *np.percentile(remuestreo, [2.5, 97.5])


def fallas(df: pd.DataFrame) -> pd.DataFrame:
    return df[df.estado != "ok"][["sf", "tarea", "configuracion", "estado"]].drop_duplicates()


# Formato

def seg(x: float) -> str:
    if pd.isna(x):
        return "--"
    return f"{x:.2f}" if x < 10 else f"{x:.1f}"


def num(x: float, decimales: int = 2) -> str:
    return "--" if pd.isna(x) else f"{x:.{decimales}f}"


def escribir(ruta: Path, texto: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    print(f"  {ruta}")


def sf_txt(sf: float) -> str:
    return f"{sf:g}"


# Tablas

def tabla_rendimiento(r: pd.DataFrame, df: pd.DataFrame, azar) -> tuple[str, dict]:
    """Mediana [RIC] por sistema y razón DSL/Polars con IC 95 %, para cada escala."""
    ok = df[df.estado == "ok"]
    sin_memoria = {(f.sf, f.tarea, f.configuracion) for f in fallas(df).itertuples()}
    razones = {}
    filas = []
    escalas = sorted(r.index.get_level_values("sf").unique())
    for tarea in TAREAS:
        for i, sf in enumerate(escalas):
            celdas = [NOMBRE_TAREA[tarea] if i == 0 else "", sf_txt(sf)]
            for s in SISTEMAS:
                if (sf, tarea, s) in r.index:
                    fila = r.loc[(sf, tarea, s)]
                    celdas.append(f"{seg(fila.mediana)} {{\\scriptsize[{seg(fila.q1)}, {seg(fila.q3)}]}}")
                else:
                    celdas.append("sin mem." if (sf, tarea, s) in sin_memoria else "--")
            a = ok[(ok.sf == sf) & (ok.tarea == tarea) & (ok.configuracion == "dsl")].segundos.to_numpy()
            b = ok[(ok.sf == sf) & (ok.tarea == tarea) & (ok.configuracion == "polars")].segundos.to_numpy()
            razon, lo, hi = razon_ic(a, b, azar)
            razones[sf, tarea] = (razon, lo, hi)
            celdas.append(f"{razon:.2f} {{\\scriptsize[{lo:.2f}, {hi:.2f}]}}")
            filas.append(" & ".join(celdas) + r" \\")
        if tarea != TAREAS[-1]:
            filas.append(r"\midrule")
    texto = "\n".join([
        r"\begin{tabular}{@{}llrrrrr@{}}",
        r"\toprule",
        r"Tarea & SF & DSL & Polars & DuckDB & Pandas & DSL/Polars \\",
        r"\midrule",
        *filas,
        r"\bottomrule",
        r"\end{tabular}",
    ])
    return texto, razones


def tabla_optimizaciones(r: pd.DataFrame, sf: float) -> str:
    """Tiempo con cada pase, con y sin el optimizador de Polars, en una escala."""
    filas = []
    for tarea in TAREAS:
        con = [r.loc[(sf, tarea, c)].mediana for c in PASES]
        sin = [r.loc[(sf, tarea, c)].mediana for c in
               ("dsl-O0-sin-opt-polars", "dsl-sin-opt-polars", "polars-sin-opt-polars")]
        filas.append(" & ".join([NOMBRE_TAREA[tarea], *map(seg, con), *map(seg, sin)]) + r" \\")
    return "\n".join([
        r"\begin{tabular}{@{}lrrrrr@{\hspace{1.2em}}rrr@{}}",
        r"\toprule",
        r" & \multicolumn{5}{c}{Optimizador de Polars activo} & \multicolumn{3}{c}{Optimizador de Polars apagado} \\",
        r"\cmidrule(lr){2-6}\cmidrule(l){7-9}",
        r"Tarea & O0 & constantes & filtros & cód.\ muerto & todos & DSL O0 & DSL todos & Polars \\",
        r"\midrule",
        *filas,
        r"\bottomrule",
        r"\end{tabular}",
    ])


def tabla_memoria(r: pd.DataFrame, df: pd.DataFrame, sf: float) -> str:
    sin_memoria = {(f.tarea, f.configuracion) for f in fallas(df[df.sf == sf]).itertuples()}
    filas = []
    for tarea in TAREAS:
        celdas = [NOMBRE_TAREA[tarea]]
        for s in SISTEMAS:
            if (sf, tarea, s) in r.index:
                celdas.append(num(r.loc[(sf, tarea, s)].memoria_mb / 1024, 1))
            else:
                celdas.append(r"$>$31" if (tarea, s) in sin_memoria else "--")
        filas.append(" & ".join(celdas) + r" \\")
    return "\n".join([
        r"\begin{tabular}{@{}lrrrr@{}}",
        r"\toprule",
        r"Tarea & DSL & Polars & DuckDB & Pandas \\",
        r"\midrule",
        *filas,
        r"\bottomrule",
        r"\end{tabular}",
    ])


def tabla_expresividad(ex: pd.DataFrame) -> str:
    filas = []
    for tarea in TAREAS:
        t = ex[ex.tarea == tarea].set_index("version")
        celdas = [NOMBRE_TAREA[tarea]]
        for s in SISTEMAS:
            celdas += [str(t.loc[s].lineas), str(t.loc[s].tokens)]
        filas.append(" & ".join(celdas) + r" \\")
    total = ex.groupby("version")[["lineas", "tokens"]].sum()
    celdas = [r"\textbf{Total}"]
    for s in SISTEMAS:
        celdas += [rf"\textbf{{{total.loc[s].lineas}}}", rf"\textbf{{{total.loc[s].tokens}}}"]
    filas += [r"\midrule", " & ".join(celdas) + r" \\"]
    cabecera = " & ".join(rf"\multicolumn{{2}}{{c}}{{{n}}}" for n in
                          ("DSL", "Polars", "Pandas", "SQL"))
    reglas = "".join(rf"\cmidrule(lr){{{2 + 2 * i}-{3 + 2 * i}}}" for i in range(4))
    return "\n".join([
        r"\begin{tabular}{@{}lrrrrrrrr@{}}",
        r"\toprule",
        rf" & {cabecera} \\",
        reglas,
        "Tarea" + " & lín. & tok." * 4 + r" \\",
        r"\midrule",
        *filas,
        r"\bottomrule",
        r"\end{tabular}",
    ])


def tabla_errores(er: pd.DataFrame) -> str:
    momento = {"compilación": r"\textbf{compilación}", "ejecución": "ejecución",
               "no detectado": "no detectado", "silencioso": r"\emph{silencioso}"}
    filas = []
    for f in er.itertuples():
        numero = f.caso.split("_", 1)[0]
        codigo = f.dsl_codigo.replace("_", r"\_") if isinstance(f.dsl_codigo, str) else ""
        dsl = momento[f.dsl_momento] + (rf" {{\scriptsize\texttt{{{codigo}}}}}" if codigo else "")
        descripcion = f.descripcion.replace("_", r"\_").replace("==", r"\texttt{==}")
        filas.append(rf"{numero} & {descripcion} & {dsl} & {momento[f.polars_momento]} \\")
    return "\n".join([
        r"\begin{tabular}{@{}rp{0.46\linewidth}p{0.25\linewidth}l@{}}",
        r"\toprule",
        r"\# & Error & DSL & Polars \\",
        r"\midrule",
        *filas,
        r"\bottomrule",
        r"\end{tabular}",
    ])


# Figuras

def estilo() -> None:
    plt.rcParams.update({
        "font.family": "serif", "font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5,
        "legend.fontsize": 7, "xtick.labelsize": 7, "ytick.labelsize": 7,
        "axes.edgecolor": TINTA_2, "axes.labelcolor": TINTA, "xtick.color": TINTA_2,
        "ytick.color": TINTA_2, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": REJILLA, "grid.linewidth": 0.6, "lines.linewidth": 1.4,
        "pdf.fonttype": 42, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
    })


def guardar(fig, ruta: Path) -> None:
    fig.savefig(ruta)
    plt.close(fig)
    print(f"  {ruta}")


def figura_escalabilidad(r: pd.DataFrame, df: pd.DataFrame, ruta: Path) -> None:
    escalas = sorted(r.index.get_level_values("sf").unique())
    sin_memoria = {(f.sf, f.tarea, f.configuracion) for f in fallas(df).itertuples()}
    fig, ejes = plt.subplots(1, len(TAREAS), figsize=(7.0, 1.75), sharex=True)
    for eje, tarea in zip(ejes, TAREAS):
        for s in SISTEMAS:
            puntos = [(sf, r.loc[(sf, tarea, s)]) for sf in escalas if (sf, tarea, s) in r.index]
            if not puntos:
                continue
            x = [p[0] for p in puntos]
            y = np.array([p[1].mediana for p in puntos])
            err = np.array([[p[1].mediana - p[1].q1 for p in puntos], [p[1].q3 - p[1].mediana for p in puntos]])
            eje.errorbar(x, y, yerr=err, color=COLOR[s], marker=MARCADOR[s], markersize=3.2,
                         capsize=1.5, elinewidth=0.8, label=NOMBRE[s])
            # Escalas en que el sistema se quedó sin memoria: una cruz en el borde superior.
            caidas = [sf for sf in escalas if (sf, tarea, s) in sin_memoria]
            if caidas:
                eje.plot(caidas, [0.97] * len(caidas), transform=eje.get_xaxis_transform(),
                         linestyle="none", marker="x", markersize=4, markeredgewidth=1.2,
                         color=COLOR[s], clip_on=False)
        eje.set_yscale("log")
        eje.set_xticks(escalas, [sf_txt(sf) for sf in escalas])
        eje.minorticks_off()
        eje.set_title(NOMBRE_TAREA[tarea], color=TINTA)
        eje.set_xlabel("Factor de escala")
    ejes[0].set_ylabel("Segundos (mediana)")
    manijas, etiquetas = ejes[0].get_legend_handles_labels()
    fig.legend(manijas, etiquetas, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.1))
    fig.tight_layout(w_pad=0.6)
    guardar(fig, ruta)


def figura_relativa(razones: dict, ruta: Path) -> None:
    """DSL/Polars por escala: cuánto cuesta el DSL frente a Polars escrito a mano."""
    escalas = sorted({sf for sf, _ in razones})
    fig, eje = plt.subplots(figsize=(3.3, 2.0))
    marcadores = ["o", "s", "^", "D", "v"]
    colores = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
    for tarea, color, marcador in zip(TAREAS, colores, marcadores):
        y = np.array([razones[sf, tarea] for sf in escalas])
        eje.errorbar(escalas, y[:, 0], yerr=[y[:, 0] - y[:, 1], y[:, 2] - y[:, 0]], color=color,
                     marker=marcador, markersize=3.2, capsize=1.5, elinewidth=0.8, label=NOMBRE_TAREA[tarea])
    eje.axhline(1, color=TINTA_2, linewidth=0.8, linestyle="--")
    eje.set_xticks(escalas, [sf_txt(sf) for sf in escalas])
    eje.minorticks_off()
    eje.set_xlabel("Factor de escala")
    eje.set_ylabel("Tiempo DSL / Polars a mano")
    eje.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, fontsize=6.5)
    guardar(fig, ruta)


def figura_memoria(r: pd.DataFrame, ruta: Path) -> None:
    escalas = sorted(r.index.get_level_values("sf").unique())
    fig, ejes = plt.subplots(1, len(TAREAS), figsize=(7.0, 1.6), sharey=True)
    for eje, tarea in zip(ejes, TAREAS):
        for s in SISTEMAS:
            puntos = [(sf, r.loc[(sf, tarea, s)].memoria_mb / 1024) for sf in escalas if (sf, tarea, s) in r.index]
            if puntos:
                eje.plot(*zip(*puntos), color=COLOR[s], marker=MARCADOR[s], markersize=3.2, label=NOMBRE[s])
        eje.set_xticks(escalas, [sf_txt(sf) for sf in escalas])
        eje.minorticks_off()
        eje.set_title(NOMBRE_TAREA[tarea], color=TINTA)
        eje.set_xlabel("Factor de escala")
    ejes[0].set_ylabel("Memoria pico (GB)")
    manijas, etiquetas = ejes[0].get_legend_handles_labels()
    fig.legend(manijas, etiquetas, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.12))
    fig.tight_layout(w_pad=0.6)
    guardar(fig, ruta)


def puntos_por_fila(eje, series, etiquetas_y) -> None:
    """Gráfico de puntos horizontal: una fila por tarea y un punto por serie, desplazados
    verticalmente para que no se tapen. `series` es [(nombre, color, marcador, valores, ic)],
    con `valores` alineados a las filas (NaN si falta) e `ic` None o [(lo, hi)]."""
    n = len(series)
    desplazamiento = np.linspace(0.22, -0.22, n) if n > 1 else [0.0]
    filas = np.arange(len(etiquetas_y))[::-1]
    for (nombre, color, marcador, valores, ic), dy in zip(series, desplazamiento):
        y = filas + dy
        valores = np.asarray(valores, dtype=float)
        if ic is not None:
            for yi, (lo, hi) in zip(y, ic):
                eje.plot([lo, hi], [yi, yi], color=color, linewidth=1.2, solid_capstyle="round")
        eje.plot(valores, y, linestyle="none", marker=marcador, markersize=4.2, color=color,
                 markeredgecolor="white", markeredgewidth=0.6, label=nombre)
    eje.set_yticks(filas, etiquetas_y)
    eje.tick_params(axis="y", length=0)
    eje.set_ylim(-0.6, len(etiquetas_y) - 0.4)
    eje.grid(axis="y", visible=False)


def figura_panorama(r: pd.DataFrame, df: pd.DataFrame, razones: dict, sf: float, ruta: Path) -> None:
    """Cada sistema medido en veces el tiempo de Polars a mano, en una escala."""
    sin_memoria = {(f.tarea, f.configuracion) for f in fallas(df[df.sf == sf]).itertuples()}
    polars = {t: r.loc[(sf, t, "polars")].mediana for t in TAREAS}

    def relativo(s):
        return [r.loc[(sf, t, s)].mediana / polars[t] if (sf, t, s) in r.index else np.nan for t in TAREAS]

    series = [(NOMBRE["dsl"], COLOR["dsl"], MARCADOR["dsl"], [razones[sf, t][0] for t in TAREAS],
               [razones[sf, t][1:] for t in TAREAS]),
              (NOMBRE["duckdb"], COLOR["duckdb"], MARCADOR["duckdb"], relativo("duckdb"), None),
              (NOMBRE["pandas"], COLOR["pandas"], MARCADOR["pandas"], relativo("pandas"), None)]
    fig, eje = plt.subplots(figsize=(3.3, 2.05))
    eje.axvline(1, color=COLOR["polars"], linewidth=1.4)
    eje.text(1, len(TAREAS) - 0.45, " Polars a mano", color=TINTA_2, fontsize=6.5, va="bottom", ha="left")
    puntos_por_fila(eje, series, [NOMBRE_TAREA[t] for t in TAREAS])
    eje.set_xscale("log")
    marcas = [0.5, 1, 2, 5, 10, 20]
    eje.set_xticks(marcas, [f"{m:g}×" for m in marcas])
    eje.minorticks_off()
    eje.set_xlim(0.45, 24)
    # Valor del DSL junto a su punto; Pandas sin memoria se indica en el borde derecho.
    for fila, t in zip(np.arange(len(TAREAS))[::-1], TAREAS):
        razon, _, hi = razones[sf, t]
        eje.text(hi * 1.08, fila + 0.22, f"{razon:.2f}", fontsize=6, color=TINTA, va="center")
        if (t, "pandas") in sin_memoria:
            eje.text(23, fila - 0.22, "Pandas: sin memoria", fontsize=6, color=TINTA_2, va="center", ha="right")
    eje.set_xlabel(f"Veces el tiempo de Polars a mano (SF {sf_txt(sf)})")
    eje.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.45, 1.04), ncol=3, fontsize=6.5,
               handletextpad=0.2, columnspacing=1.0)
    guardar(fig, ruta)


def figura_optimizaciones(r: pd.DataFrame, sf: float, ruta: Path) -> None:
    """Cuánto más lento queda el programa al quitar cada capa de optimización."""
    def cociente(a, b):
        return [r.loc[(sf, t, a)].mediana / r.loc[(sf, t, b)].mediana for t in TAREAS]

    series = [("Sin los pases del DSL", COLOR["dsl"], "o", cociente("dsl-O0", "dsl"), None),
              ("Sin los pases, sin optimizador de Polars", "#86b6ef", "D",
               cociente("dsl-O0-sin-opt-polars", "dsl-sin-opt-polars"), None),
              ("Sin el optimizador de Polars", COLOR["polars"], "s", cociente("dsl-sin-opt-polars", "dsl"), None)]
    fig, eje = plt.subplots(figsize=(3.3, 2.05))
    eje.axvline(1, color=TINTA_2, linewidth=0.8, linestyle="--")
    puntos_por_fila(eje, series, [NOMBRE_TAREA[t] for t in TAREAS])
    eje.set_xscale("log")
    marcas = [0.8, 1, 1.5, 2, 3, 5]
    eje.set_xticks(marcas, [f"{m:g}×" for m in marcas])
    eje.minorticks_off()
    eje.set_xlim(0.75, 6.5)
    eje.set_xlabel(f"Veces más lento que con la optimización (SF {sf_txt(sf)})")
    eje.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.4, 1.02), ncol=1, fontsize=6.5,
               handletextpad=0.3, labelspacing=0.25)
    guardar(fig, ruta)


def figura_errores(er: pd.DataFrame, ruta: Path) -> None:
    """Cuándo se detecta cada error del corpus, en el DSL y en Polars."""
    categorias = [("compilación", "Al compilar", COLOR["dsl"], None),
                  ("ejecución", "Al ejecutar", "#86b6ef", None),
                  ("silencioso", "No se detecta", "#d6d5d0", "////")]
    momentos = {"DSL": er.dsl_momento.replace("no detectado", "silencioso"), "Polars": er.polars_momento}
    fig, eje = plt.subplots(figsize=(3.3, 0.95))
    for fila, (sistema, momento) in enumerate(momentos.items()):
        cuenta = momento.value_counts()
        inicio = 0
        for clave, etiqueta, color, trama in categorias:
            n = int(cuenta.get(clave, 0))
            if not n:
                continue
            eje.barh(1 - fila, n, left=inicio, height=0.62, color=color, hatch=trama,
                     edgecolor="white", linewidth=1.5, label=etiqueta)
            eje.text(inicio + n / 2, 1 - fila, str(n), ha="center", va="center", fontsize=7,
                     color="white" if clave == "compilación" else TINTA, fontweight="bold")
            inicio += n
    manijas, etiquetas = eje.get_legend_handles_labels()
    unicas = dict(zip(etiquetas, manijas))
    eje.legend(unicas.values(), unicas.keys(), frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0),
               ncol=3, fontsize=6.5, handlelength=1.2, columnspacing=1.0)
    eje.set_yticks([1, 0], list(momentos))
    eje.tick_params(axis="y", length=0)
    eje.set_xlim(0, len(er))
    eje.set_xticks(range(0, len(er) + 1, 4))
    eje.set_xlabel(f"Errores del corpus (de {len(er)})")
    eje.grid(axis="y", visible=False)
    guardar(fig, ruta)


# Cifras citadas en el texto

def macros(valores: dict) -> str:
    return "".join(rf"\newcommand{{\{nombre}}}{{{valor}}}" + "\n" for nombre, valor in valores.items())


def cifras(r, df, todas, razones, ex, er, sf_max) -> dict[str, str]:
    """Cifras que cita el texto, ya formateadas; salen como macros y en el JSON de la web."""
    c = {}
    sf_min = min(sf for sf, _ in razones)
    # DSL frente a Polars en la escala mayor, sin la tarea de limpieza.
    otras = [razones[sf_max, t][0] for t in TAREAS if t != "limpieza_pedidos"]
    c["SFmax"], c["SFmin"] = sf_txt(sf_max), sf_txt(sf_min)
    c["dslPolarsMin"] = f"{(min(otras) - 1) * 100:.0f}"
    c["dslPolarsMax"] = f"{(max(otras) - 1) * 100:.0f}"
    c["limpiezaRazon"] = f"{razones[sf_max, 'limpieza_pedidos'][0]:.1f}"
    c["limpiezaRazonMin"] = f"{razones[sf_min, 'limpieza_pedidos'][0]:.1f}"
    pandas = [r.loc[(sf_max, t, "pandas")].mediana / r.loc[(sf_max, t, "dsl")].mediana
              for t in TAREAS if (sf_max, t, "pandas") in r.index]
    c["pandasMin"], c["pandasMax"] = f"{min(pandas):.1f}", f"{max(pandas):.1f}"
    compilacion = df[(df.estado == "ok") & df.compilacion_s.notna()].compilacion_s
    c["compilacionMs"] = f"{compilacion.median() * 1000:.0f}"
    # Reproducibilidad: misma escala medida en dos corridas.
    ok = todas[todas.estado == "ok"]
    repetidas = ok.groupby("sf").corrida.nunique()
    repetidas = repetidas[repetidas > 1]
    if len(repetidas):
        sf = repetidas.index[0]
        m = ok[ok.sf == sf].groupby(["corrida", "tarea", "configuracion"]).segundos.median().unstack(0).dropna()
        razon = m.iloc[:, 0] / m.iloc[:, 1]
        c["reproSF"], c["reproMediana"] = sf_txt(sf), f"{razon.median():.2f}"
        c["reproMin"], c["reproMax"] = f"{razon.min():.2f}", f"{razon.max():.2f}"
    total = ex.groupby("version").tokens.sum()
    c["tokensVsPolars"] = f"{(1 - total['dsl'] / total['polars']) * 100:.0f}"
    c["tokensVsPandas"] = f"{(1 - total['dsl'] / total['pandas']) * 100:.0f}"
    cuenta = er.groupby("dsl_momento").size()
    silenciosos = er.polars_momento == "silencioso"
    c["erroresTotal"] = str(len(er))
    c["erroresCompilacion"] = str(cuenta.get("compilación", 0))
    c["erroresEjecucion"] = str(cuenta.get("ejecución", 0))
    c["erroresNoDetectados"] = str(cuenta.get("no detectado", 0))
    c["erroresSilenciososPolars"] = str(int(silenciosos.sum()))
    c["erroresSilenciososDetectados"] = str(int((silenciosos & (er.dsl_momento != "no detectado")).sum()))
    c["mediciones"] = str(int((df.estado == "ok").sum()))
    c["repeticiones"] = str(int(df[df.estado == "ok"].repeticion.max()))
    return c


# Datos de la página interactiva del entorno web

def tablas_leidas(tarea: str) -> list[str]:
    """Tablas de TPC-H que lee el programa del DSL (sus Parquet de entrada, sin las salidas)."""
    programa = (BENCH / "tareas" / tarea / "programa.etl").read_text(encoding="utf-8")
    return list(dict.fromkeys(re.findall(r'"(\w+)\.parquet"', programa)))


def tamanos_datos(escalas: list[float], medidos: dict[float, dict]) -> list[dict]:
    """Filas por tabla y bytes en Parquet de cada escala. Las escalas sin entorno.json se
    estiman a partir de la escala medida más cercana, porque TPC-H crece linealmente con
    el factor de escala; esas filas llevan estimado=True."""
    if not medidos:
        return []
    salida = []
    for sf in escalas:
        base_sf = sf if sf in medidos else min(medidos, key=lambda m: abs(m - sf))
        base = medidos[base_sf]
        factor = sf / base_sf
        tablas = {t: round(n * factor) for t, n in base["tablas"].items()}
        salida.append({"sf": sf, "estimado": base_sf != sf, "tablas": tablas,
                       "bytes": round(sum(base["bytes"].values()) * factor)})
    return salida


def datos_web(r, df, razones, ex, er, valores, corridas) -> dict:
    """Todo lo que dibuja benchmarks.html, en un JSON autocontenido."""
    filas = [{"sf": sf, "tarea": t, "config": c, "mediana": round(f.mediana, 5), "q1": round(f.q1, 5),
              "q3": round(f.q3, 5), "memoria_gb": round(f.memoria_mb / 1024, 3)}
             for (sf, t, c), f in r.iterrows()]
    entorno, medidos = {}, {}
    for corrida in corridas:
        ruta = corrida / "entorno.json"
        if ruta.exists():
            leido = json.loads(ruta.read_text(encoding="utf-8"))
            entorno = entorno or leido
            for d in leido.get("datos", {}).values():
                medidos[float(d["sf"])] = d
    escalas = sorted(r.index.get_level_values("sf").unique())
    return {
        "datos": tamanos_datos(escalas, medidos),
        "escalas": escalas,
        "tareas": [{"id": t, "nombre": NOMBRE_TAREA[t], "tablas": tablas_leidas(t)} for t in TAREAS],
        "sistemas": [{"id": s, "nombre": NOMBRE[s]} for s in SISTEMAS],
        "corridas": {sf_txt(sf): c for sf, c in df.groupby("sf").corrida.first().items()},
        "tiempos": filas,
        "fallas": fallas(df).rename(columns={"configuracion": "config"}).to_dict("records"),
        "razones": [{"sf": sf, "tarea": t, "razon": round(v[0], 4), "lo": round(v[1], 4), "hi": round(v[2], 4)}
                    for (sf, t), v in sorted(razones.items())],
        "expresividad": ex.to_dict("records"),
        "codigo": {t: {v: (BENCH / "tareas" / t / archivo).read_text(encoding="utf-8").strip()
                       for v, archivo in ARCHIVO_VERSION.items()} for t in TAREAS},
        "errores": er.to_dict("records"),
        "cifras": valores,
        "entorno": {k: entorno.get(k) for k in ("cpu", "hilos", "memoria_total_gb", "python", "versiones")},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corridas", nargs="+", type=Path,
                        default=sorted(p.parent for p in RESULTADOS.glob("*/tiempos.csv")))
    parser.add_argument("--salida", type=Path, default=BENCH.parent / "reporte" / "generado")
    parser.add_argument("--web", type=Path, default=WEB_JSON,
                        help="JSON de la página de benchmarks del entorno web")
    args = parser.parse_args(argv)
    if not args.corridas:
        parser.error("no hay corridas en bench/resultados/; correr bench/todo.py")
    df, todas = cargar_tiempos(args.corridas)
    r = resumen(df)
    ex = pd.read_csv(RESULTADOS / "expresividad.csv")
    er = pd.read_csv(RESULTADOS / "errores.csv").fillna("")
    sf_max = max(r.index.get_level_values("sf"))
    azar = np.random.default_rng(SEMILLA)

    print("Escala -> corrida:")
    for sf, corrida in df.groupby("sf").corrida.first().items():
        print(f"  SF {sf_txt(sf)}: {corrida}")
    tablas, figuras = args.salida / "tablas", args.salida / "figuras"
    rendimiento, razones = tabla_rendimiento(r, df, azar)
    escribir(tablas / "rendimiento.tex", rendimiento)
    escribir(tablas / "optimizaciones.tex", tabla_optimizaciones(r, sf_max))
    escribir(tablas / "memoria.tex", tabla_memoria(r, df, sf_max))
    escribir(tablas / "expresividad.tex", tabla_expresividad(ex))
    escribir(tablas / "errores.tex", tabla_errores(er))
    valores = cifras(r, df, todas, razones, ex, er, sf_max)
    escribir(args.salida / "cifras.tex", macros(valores))
    figuras.mkdir(parents=True, exist_ok=True)
    estilo()
    figura_escalabilidad(r, df, figuras / "escalabilidad.pdf")
    figura_relativa(razones, figuras / "relativo.pdf")
    figura_memoria(r, figuras / "memoria.pdf")
    figura_panorama(r, df, razones, sf_max, figuras / "panorama.pdf")
    figura_optimizaciones(r, sf_max, figuras / "optimizaciones.pdf")
    figura_errores(er, figuras / "errores.pdf")
    web = datos_web(r, df, razones, ex, er, valores, args.corridas)
    escribir(args.web, json.dumps(web, ensure_ascii=False, separators=(",", ":"),
                                     default=lambda v: v.item()))  # escalares de NumPy
    resumen_csv = r.reset_index()
    resumen_csv["corrida"] = resumen_csv.sf.map(df.groupby("sf").corrida.first())
    resumen_csv.to_csv(args.salida / "resumen.csv", index=False, float_format="%.6g")
    print(f"  {args.salida / 'resumen.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
