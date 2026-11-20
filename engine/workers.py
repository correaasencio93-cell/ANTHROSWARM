"""Configuración de workers y función que ejecuta cada worker.

Todo lo que se envía al pool está definido a nivel de módulo para que se pueda
serializar con pickle (Anexo A, punto 6).
"""
from __future__ import annotations

import os
import signal

from logic import procesar_hormigas
from models import Ant, AntResult, WorldView


def nucleos_totales() -> int:
    """Núcleos lógicos totales de la máquina (dato técnico pedido en la rúbrica)."""
    return max(1, os.cpu_count() or 1)


def detectar_nucleos() -> int:
    """Núcleos que este proceso puede usar realmente.

    En Linux respeta la afinidad de CPU (contenedores, taskset); en otros
    sistemas usa os.cpu_count(). Nunca devuelve menos de 1.
    """
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def configurar_workers(n_workers: int | None = None) -> int:
    """Cantidad de procesos a usar.

    None -> todos los núcleos detectados. Un valor explícito se respeta
    (puede superar los núcleos, útil para pruebas) pero debe ser >= 1.
    """
    if n_workers is None:
        return detectar_nucleos()
    if not isinstance(n_workers, int) or n_workers < 1:
        raise ValueError(f"n_workers debe ser un entero >= 1 (recibido {n_workers!r})")
    return n_workers


def inicializar_worker() -> None:
    """Se ejecuta una vez al crear cada worker.

    Los workers ignoran Ctrl+C: la interrupción la maneja el proceso principal,
    que cierra el pool de forma ordenada. Así no aparecen trazas repetidas de
    KeyboardInterrupt por cada worker.
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def worker_listo(_: int = 0) -> int:
    """Tarea vacía para confirmar que un worker ya arrancó e importó logic/."""
    return os.getpid()


def procesar_segmento(segmento: tuple[Ant, ...],
                      vista: WorldView) -> tuple[AntResult, ...]:
    """Wrapper del worker: solo llama a procesar_hormigas de logic/.

    No contiene lógica de comportamiento, no dibuja y no toca variables globales.
    """
    return procesar_hormigas(segmento, vista)
