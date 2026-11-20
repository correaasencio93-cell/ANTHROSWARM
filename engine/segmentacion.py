"""Segmentación de hormigas.

Estrategia: partición equilibrada por bloques contiguos. Con n hormigas y k
segmentos, cada bloque tiene n // k hormigas y los primeros n % k bloques
tienen una más. Se conserva el orden original y no hay bloques vacíos.
"""
from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")


def limites_segmentos(n_elementos: int, n_segmentos: int) -> tuple[tuple[int, int], ...]:
    """Rangos [inicio, fin) de cada segmento.

    El inicio del segmento i es i * base + min(i, resto): los primeros `resto`
    segmentos ya recibieron un elemento extra cada uno.
    """
    if n_segmentos < 1:
        raise ValueError(f"n_segmentos debe ser >= 1 (recibido {n_segmentos})")
    if n_elementos < 0:
        raise ValueError(f"n_elementos no puede ser negativo (recibido {n_elementos})")
    k = min(n_segmentos, n_elementos)
    if k == 0:
        return ()
    base, resto = divmod(n_elementos, k)
    inicio = lambda i: i * base + min(i, resto)  # noqa: E731
    return tuple((inicio(i), inicio(i + 1)) for i in range(k))


def segmentar_hormigas(ants: Sequence[T], n_segmentos: int) -> tuple[tuple[T, ...], ...]:
    """Divide `ants` en hasta `n_segmentos` tuplas contiguas y ordenadas.

    Garantía: concatenar los segmentos devuelve exactamente `tuple(ants)`.
    """
    ants = tuple(ants)
    return tuple(ants[i:j] for i, j in limites_segmentos(len(ants), n_segmentos))
