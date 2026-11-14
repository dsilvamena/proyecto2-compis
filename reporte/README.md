# Reporte

Artículo en formato ACM SIGPLAN (`acmart`). Las tablas, figuras y cifras de la evaluación
están en `generado/` y salen de `bench/analisis.py`; no se editan a mano.

```bash
# 1. Regenerar tablas y figuras (desde la raíz del repositorio)
docker compose run --rm bench sh -c "python bench/errores.py && python bench/expresividad.py && python bench/analisis.py"

# 2. Compilar el PDF con TeX Live (desde la raíz del repositorio)
docker run --rm -v "$PWD:/doc" -w /doc/reporte texlive/texlive:latest latexmk -pdf main.tex
```

En PowerShell, reemplazar `$PWD` por `${PWD}`. Con una instalación local de LaTeX basta
`latexmk -pdf main.tex` dentro de `reporte/`. El resultado es `reporte/main.pdf`.
