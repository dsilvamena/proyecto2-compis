import polars as pl


def ejecutar(datos):
    return pl.scan_parquet(datos / "ventas.parquet").with_columns(razon=pl.col("monto") / pl.col("descuento")).collect()
