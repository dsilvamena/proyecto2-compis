import polars as pl


def ejecutar(datos):
    return pl.scan_parquet(datos / "ventas.parquet").with_columns(monto_final=pl.coalesce("monto")).collect()
