import polars as pl


def ejecutar(datos):
    ventas = pl.scan_parquet(datos / "ventas.parquet")
    clientes = pl.scan_parquet(datos / "clientes.parquet")
    return ventas.join(clientes, left_on="cliente_id", right_on="nombre").collect()
