import polars as pl


def ejecutar(datos):
    # La función promete devolver cliente_id y total, pero nada lo comprueba.
    return pl.scan_parquet(datos / "ventas.parquet").group_by("cliente_id").agg(suma=pl.col("monto").sum()).collect()
