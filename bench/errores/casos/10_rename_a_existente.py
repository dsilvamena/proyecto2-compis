import polars as pl


def ejecutar(datos):
    return pl.scan_parquet(datos / "ventas.parquet").rename({"monto": "canal"}).collect()
