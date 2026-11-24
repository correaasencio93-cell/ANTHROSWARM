"""Ejemplo de integración del motor sin interfaz gráfica.

Hace lo mismo que debe hacer main.py, pero sin Pygame:
    python -m ejemplos.main_consola --modo paralelo --hormigas 3000 --ticks 100
"""
from __future__ import annotations

import argparse
import time
from functools import reduce

from engine import abrir_motor, ejecutor_paralelo, procesar_secuencial
from logic import crear_estado_inicial, update
from models import SimConfig


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--modo", choices=("secuencial", "paralelo"), default="paralelo")
    p.add_argument("--hormigas", type=int, default=1000)
    p.add_argument("--ticks", type=int, default=100)
    p.add_argument("--workers", type=int, default=None)
    a = p.parse_args()

    inicial = crear_estado_inicial(SimConfig(), a.hormigas)

    with abrir_motor(n_workers=a.workers) as motor:
        ejecutores = {"secuencial": procesar_secuencial,
                      "paralelo": ejecutor_paralelo(motor)}
        ejecutor = ejecutores[a.modo]
        t0 = time.perf_counter()
        final = reduce(lambda s, _: update(s, ejecutor), range(a.ticks), inicial)
        dt = time.perf_counter() - t0

    print(f"{a.modo}: {a.ticks} frames en {dt:.2f} s ({a.ticks / dt:.1f} FPS) | "
          f"tick {final.tick} | comida en el nido {final.nest.food_stored} | "
          f"feromonas {len(final.pheromones)}")


if __name__ == "__main__":      # obligatorio con multiprocessing (spawn)
    main()
