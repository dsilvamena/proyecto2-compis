import polars as pl


def ejecutar(datos):
    return pl.scan_parquet(datos / "ventas.parquet").filter(pl.col("monto") == None).collect()  # noqa: E711
