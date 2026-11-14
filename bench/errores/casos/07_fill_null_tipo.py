import polars as pl


def ejecutar(datos):
    return pl.scan_parquet(datos / "ventas.parquet").with_columns(pl.col("canal").fill_null(0)).collect()
