import polars as pl


def ejecutar(datos):
    return pl.scan_parquet(datos / "ventas.parquet").with_columns(monto=pl.col("monto") * (1 - pl.col("descuento"))).collect()
