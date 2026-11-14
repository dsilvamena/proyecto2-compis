import polars as pl


def ejecutar(datos):
    return pl.scan_parquet(datos / "ventas.parquet").filter(pl.col("mnto") > 100).collect()
