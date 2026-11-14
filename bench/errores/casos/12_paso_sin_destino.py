import polars as pl


def ejecutar(datos):
    ventas = pl.scan_parquet(datos / "ventas.parquet").with_columns(pl.col("monto").fill_null(0))
    resultado = ventas.collect()
    ventas.filter(pl.col("monto") > 100)  # se construye y nunca se usa
    return resultado
