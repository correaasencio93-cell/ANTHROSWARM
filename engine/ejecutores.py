"""Ejecutores secuencial y paralelo.

Ambos cumplen el contrato Ejecutor del Anexo A:
    (ants: tuple[Ant, ...], vista: WorldView) -> tuple[AntResult, ...]
y se usan como  update(state, ejecutor=...).

No hay clases con estado mutable: el Pool se abre y se cierra con un
administrador de contexto (`with abrir_motor() as motor`), sus datos viajan en
una dataclass congelada y el ejecutor paralelo es una aplicación parcial de una
función (functools.partial).
"""
from __future__ import annotations

import multiprocessing as mp
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from itertools import chain
from multiprocessing.pool import Pool
from typing import Callable, Iterator

from logic import procesar_hormigas
from models import Ant, AntResult, WorldView

from .segmentacion import segmentar_hormigas
from .workers import (
    configurar_workers, inicializar_worker, procesar_segmento, worker_listo,
)

Ejecutor = Callable[[tuple[Ant, ...], WorldView], tuple[AntResult, ...]]

# "spawn" es el único método disponible en Windows y el de macOS; usarlo
# también en Linux da el mismo comportamiento en todas las máquinas del equipo
# y evita los bloqueos de fork() cuando el proceso ya tiene hilos (Pygame).
# Su costo (arrancar intérpretes nuevos) se paga una sola vez porque el pool se
# reutiliza. Pase metodo_inicio=None para usar el método por defecto del sistema.
METODO_INICIO_POR_DEFECTO = "spawn"


class ErrorConsolidacion(RuntimeError):
    """Los resultados de los workers no cumplen el contrato del ejecutor."""


def validar_resultados(ants: tuple[Ant, ...],
                       resultados: tuple[AntResult, ...]) -> tuple[AntResult, ...]:
    """Exactamente un AntResult por hormiga y en el mismo orden (por id)."""
    if len(resultados) != len(ants):
        raise ErrorConsolidacion(
            f"Se esperaban {len(ants)} resultados y llegaron {len(resultados)}")
    error = next(((i, a.id, r.ant.id)
                  for i, (a, r) in enumerate(zip(ants, resultados))
                  if a.id != r.ant.id), None)
    if error is not None:
        raise ErrorConsolidacion(
            "Orden roto en la posición {}: hormiga {}, resultado {}".format(*error))
    return resultados


# ------------------------------------------------------------------ secuencial
def procesar_secuencial(ants: tuple[Ant, ...],
                        vista: WorldView) -> tuple[AntResult, ...]:
    """Modo secuencial: un único proceso, misma función que usan los workers."""
    return procesar_hormigas(ants, vista)


# -------------------------------------------------------------------- paralelo
def procesar_paralelo(ants: tuple[Ant, ...], vista: WorldView, *, pool: Pool,
                      n_segmentos: int) -> tuple[AntResult, ...]:
    """Segmenta, reparte (segmento, vista) entre los workers y concatena.

    starmap bloquea hasta que todos los workers terminan (sincronización) y
    devuelve las partes en el orden de los segmentos aunque los workers
    terminen en otro orden, así que el orden de las hormigas se conserva.
    La vista viaja una vez por segmento, no una vez por hormiga.
    """
    if not ants:
        return ()
    segmentos = segmentar_hormigas(ants, n_segmentos)
    partes = pool.starmap(procesar_segmento,
                          [(seg, vista) for seg in segmentos], chunksize=1)
    return validar_resultados(ants, tuple(chain.from_iterable(partes)))


@dataclass(frozen=True)
class Motor:
    """Datos inmutables del motor paralelo abierto."""
    pool: Pool
    n_workers: int
    n_segmentos: int
    metodo_inicio: str


@contextmanager
def abrir_motor(n_workers: int | None = None, n_segmentos: int | None = None,
                metodo_inicio: str | None = METODO_INICIO_POR_DEFECTO) -> Iterator[Motor]:
    """Crea los workers una sola vez, los entrega y los cierra al salir.

    - Al entrar: crea el Pool y espera a que todos los workers estén listos,
      para que el arranque no caiga sobre el primer frame.
    - Durante el `with`: el mismo Pool se reutiliza en cada frame.
    - Al salir sin error: close() + join() (cierre ordenado).
    - Al salir por error o Ctrl+C: terminate() + join() (cierre inmediato).

        with abrir_motor() as motor:
            ejecutor = ejecutor_paralelo(motor)
            state = update(state, ejecutor)
    """
    n = configurar_workers(n_workers)
    if n_segmentos is not None and n_segmentos < 1:
        raise ValueError("n_segmentos debe ser >= 1")
    ctx = mp.get_context(metodo_inicio)
    pool = ctx.Pool(processes=n, initializer=inicializar_worker)
    try:
        pool.map(worker_listo, range(n), chunksize=1)
        yield Motor(pool=pool, n_workers=n, n_segmentos=n_segmentos or n,
                    metodo_inicio=ctx.get_start_method())
    except BaseException:
        pool.terminate()
        raise
    else:
        pool.close()
    finally:
        pool.join()


def ejecutor_paralelo(motor: Motor) -> Ejecutor:
    """Ejecutor (ants, vista) -> resultados que usa los workers de `motor`."""
    return partial(procesar_paralelo, pool=motor.pool, n_segmentos=motor.n_segmentos)
