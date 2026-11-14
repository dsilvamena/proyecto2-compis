# Corrida del laboratorio, PC 1

- Comando: `python bench/todo.py --sf 1 10 20 30 --limite 1800 --borrar-datos`.
- Equipo: Intel Core Ultra 9 285K, 64 GB de RAM; Docker limitado a 31 GB por WSL.
  Es el mismo hardware que la corrida `2026-11-13_14-01_f96690b55f40`, cuyo
  `entorno.json` registra las versiones.
- Se detuvo a mano al empezar SF 30, porque esa escala la midió la otra PC. Por eso
  no hay zip, `entorno.json` ni `verificacion.txt`, y las 5 filas de `sf=30` están
  incompletas: el análisis no las usa.
- `log.txt` es la salida de la terminal y empieza en la medición 12.
- La escala SF 1 se midió en las dos PCs. La mediana de la razón PC 2 / PC 1 es 0.98
  (rango de 0.80 a 1.07).
