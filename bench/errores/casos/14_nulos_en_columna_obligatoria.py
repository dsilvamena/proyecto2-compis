import polars as pl


def ejecutar(datos):
    return pl.scan_parquet(datos / "ventas.parquet").group_by("cliente_id").agg(total=pl.col("monto").sum()).collect()
