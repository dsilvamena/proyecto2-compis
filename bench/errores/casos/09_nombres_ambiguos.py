import polars as pl


def ejecutar(datos):
    return pl.scan_parquet(datos / "ventas.parquet").with_columns(Monto=pl.col("monto") * 2).collect()
