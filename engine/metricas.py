"""Métricas de rendimiento del motor.

La medición de tiempo vive aquí (engine/), fuera de update: se mide cuánto
tarda cada llamada completa a update, nunca dentro de logic/ ni de los workers.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from functools import reduce
from typing import Callable

from logic import update
from models import GameState


@dataclass(frozen=True)
class MetricasEjecucion:
    modo: str                         # "secuencial" o "paralelo"
    n_hormigas: int
    n_workers: int
    n_segmentos: int
    nucleos_detectados: int
    ticks: int
    tiempos: tuple[float, ...]        # segundos de cada update
    arranque_pool_s: float = 0.0      # costo único de crear los workers
    feromonas_finales: int = 0

    @property
    def total_s(self) -> float:
        return sum(self.tiempos)

    @property
    def promedio_ms(self) -> float:
        return 1000 * statistics.fmean(self.tiempos) if self.tiempos else 0.0

    @property
    def mediana_ms(self) -> float:
        return 1000 * statistics.median(self.tiempos) if self.tiempos else 0.0

    @property
    def p95_ms(self) -> float:
        orden = sorted(self.tiempos)
        return 1000 * orden[min(len(orden) - 1, int(0.95 * len(orden)))] if orden else 0.0

    @property
    def fps(self) -> float:
        """FPS de la simulación: updates por segundo, sin contar el dibujo."""
        return self.ticks / self.total_s if self.total_s > 0 else float("inf")


def paso_medido(ejecutor: Callable,
                acumulado: tuple[GameState, tuple[float, ...]],
                _=None) -> tuple[GameState, tuple[float, ...]]:
    """Un update cronometrado. Devuelve el estado nuevo y los tiempos + 1."""
    estado, tiempos = acumulado
    t0 = time.perf_counter()
    nuevo = update(estado, ejecutor)
    return nuevo, tiempos + (time.perf_counter() - t0,)


def medir_simulacion(estado: GameState, ejecutor: Callable, ticks: int, *,
                     modo: str, n_workers: int, n_segmentos: int,
                     nucleos_detectados: int,
                     arranque_pool_s: float = 0.0) -> tuple[GameState, MetricasEjecucion]:
    """Aplica `ticks` veces update(state, ejecutor) con reduce y mide cada uno."""
    final, tiempos = reduce(lambda acc, _: paso_medido(ejecutor, acc),
                            range(ticks), (estado, ()))
    return final, MetricasEjecucion(
        modo=modo, n_hormigas=len(final.ants), n_workers=n_workers,
        n_segmentos=n_segmentos, nucleos_detectados=nucleos_detectados,
        ticks=ticks, tiempos=tiempos, arranque_pool_s=arranque_pool_s,
        feromonas_finales=len(final.pheromones))


def aceleracion(secuencial: MetricasEjecucion, paralelo: MetricasEjecucion) -> float:
    """Speedup = tiempo secuencial / tiempo paralelo."""
    return secuencial.total_s / paralelo.total_s if paralelo.total_s > 0 else float("inf")


def eficiencia(secuencial: MetricasEjecucion, paralelo: MetricasEjecucion) -> float:
    """Speedup / workers. 1.0 sería un reparto perfecto."""
    return aceleracion(secuencial, paralelo) / paralelo.n_workers
