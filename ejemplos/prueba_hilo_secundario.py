"""Prueba: el motor paralelo usado desde un hilo secundario (como en la interfaz).

    python -m ejemplos.prueba_hilo_secundario

Comprueba con multiprocessing "spawn" (el de Windows):
  A) motor abierto en el hilo principal y usado desde un hilo secundario,
     mientras el hilo principal sigue respondiendo (como Pygame);
  B) motor abierto y cerrado dentro del hilo secundario;
  C) usar el ejecutor después de cerrar el motor da ValueError (no se cuelga).
En A y B el estado final debe ser == al del modo secuencial.
"""
from __future__ import annotations

import queue
import threading
import time
from functools import reduce

from engine import abrir_motor, ejecutor_paralelo, procesar_secuencial
from logic import crear_estado_inicial, crear_vista, update
from models import SimConfig

TICKS = 10


def simular(ejecutor, inicial, salida: queue.Queue) -> None:
    salida.put(reduce(lambda s, _: update(s, ejecutor), range(TICKS), inicial))


def main() -> None:
    inicial = crear_estado_inicial(SimConfig(seed=9), 2000)
    esperado = reduce(lambda s, _: update(s, procesar_secuencial), range(TICKS), inicial)

    # A) abierto en el hilo principal, usado desde el secundario
    with abrir_motor(metodo_inicio="spawn") as motor:
        q: queue.Queue = queue.Queue()
        hilo = threading.Thread(target=simular, args=(ejecutor_paralelo(motor), inicial, q))
        hilo.start()
        latidos = 0
        while hilo.is_alive():          # el hilo principal sigue libre, como la UI
            latidos += 1
            time.sleep(0.01)
        hilo.join()
        print(f"A) principal -> secundario: igual al secuencial = {q.get() == esperado}"
              f" | el hilo principal respondió {latidos} veces mientras tanto")

    # B) todo dentro del hilo secundario
    def hilo_b(q: queue.Queue) -> None:
        with abrir_motor(metodo_inicio="spawn") as m:
            simular(ejecutor_paralelo(m), inicial, q)

    q = queue.Queue()
    hilo = threading.Thread(target=hilo_b, args=(q,))
    hilo.start()
    hilo.join()
    print(f"B) todo en el secundario:   igual al secuencial = {q.get() == esperado}")

    # C) usar el ejecutor con el motor ya cerrado
    with abrir_motor(metodo_inicio="spawn") as motor:
        ejecutor = ejecutor_paralelo(motor)
    try:
        ejecutor(inicial.ants, crear_vista(inicial))
        print("C) ERROR: debía fallar")
    except ValueError as e:
        print(f"C) usar tras cerrar:        ValueError ({e}) -> correcto")


if __name__ == "__main__":      # obligatorio con spawn
    main()
