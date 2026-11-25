"""Paso de tiempo fijo (fixed timestep) con acumulador.

Hay dos relojes separados:
  * el reloj de pantalla (FPS): variable, solo afecta al dibujo;
  * el reloj de simulación: avanza en pasos de duración constante (DT_PASO).

El multiplicador de velocidad (0.5x, 1x, 2x, 4x) NO cambia la duración del paso:
solo cambia qué tan rápido se llena el acumulador, es decir, cuántos pasos
idénticos se ejecutan por segundo real.

Este módulo no usa pygame, no lee ningún reloj y no conoce el motor: recibe el
tiempo real ya medido y devuelve cuántos pasos lógicos hay que ejecutar.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import reduce
from typing import Callable, TypeVar

T = TypeVar("T")

# Duración del paso lógico, en segundos. Valor acordado: 1/60 (diseño técnico de Mike).
# Coincide con SimConfig.dt de models/ (Mike), que el adaptador lee del estado.
# No cambiar a 1/30 sin consultarlo con él.
DT_PASO: float = 1.0 / 60.0

# Tope de pasos por cuadro. Es una protección de la interfaz (no del motor): si el
# motor tarda más que el tiempo real, sin tope el acumulador crecería sin fin y la
# ventana se congelaría.
MAX_PASOS_POR_CUADRO: int = 8

# Tolerancia numérica: evita que 1/60 s reales cuenten como 0 pasos por error de
# redondeo de los decimales.
_EPSILON: float = 1e-9


@dataclass(frozen=True)
class EstadoTiempo:
    """Tiempo (en segundos de simulación) acumulado que aún no se convirtió en pasos.

    `descartado_total` suma todo el tiempo de simulación que NO se pudo ejecutar
    porque se alcanzó el tope de pasos por cuadro. Nunca se pierde en silencio:
    queda registrado aquí y la interfaz lo muestra.

    `cancelado_total` suma el tiempo de simulación de pasos que ya se habían calculado
    pero se abandonaron porque el estado al que pertenecían dejó de existir (reinicio
    o cierre). Es otro motivo distinto del retraso, y tampoco se pierde en silencio.
    """
    acumulador: float = 0.0
    descartado_total: float = 0.0
    cancelado_total: float = 0.0


@dataclass(frozen=True)
class ResultadoTiempo:
    """Resultado de un cuadro.

    Cuando `atrasado` es True, `descartado` indica cuántos segundos de simulación
    se dejaron de ejecutar en este cuadro (la simulación no sigue el ritmo real).
    """
    estado: EstadoTiempo
    pasos: int
    atrasado: bool
    descartado: float = 0.0


def avanzar_tiempo(estado: EstadoTiempo,
                   dt_real: float,
                   multiplicador: float,
                   en_pausa: bool,
                   dt_paso: float = DT_PASO,
                   max_pasos: int = MAX_PASOS_POR_CUADRO) -> ResultadoTiempo:
    """Convierte el tiempo real de un cuadro en un número de pasos lógicos.

    Función pura: mismos argumentos, mismo resultado; no modifica `estado`.
    En pausa no se acumula tiempo, para que al reanudar no haya una ráfaga de pasos.
    """
    if dt_real < 0:
        raise ValueError(f"dt_real no puede ser negativo (recibido {dt_real})")
    if multiplicador <= 0:
        raise ValueError(f"multiplicador debe ser > 0 (recibido {multiplicador})")
    if dt_paso <= 0:
        raise ValueError(f"dt_paso debe ser > 0 (recibido {dt_paso})")
    if max_pasos < 1:
        raise ValueError(f"max_pasos debe ser >= 1 (recibido {max_pasos})")

    if en_pausa:
        return ResultadoTiempo(estado, 0, False)

    acumulado = estado.acumulador + dt_real * multiplicador
    pasos_posibles = int((acumulado + _EPSILON) // dt_paso)
    pasos = min(pasos_posibles, max_pasos)
    atrasado = pasos_posibles > max_pasos

    # Comportamiento ante el tope (definido, no silencioso):
    #  * se ejecutan `max_pasos` pasos;
    #  * los pasos que no caben NO se acumulan (si se acumularan, el retraso
    #    crecería sin fin: "espiral de la muerte"); su duración se contabiliza
    #    en `descartado` y se suma a `descartado_total`;
    #  * `atrasado` avisa a la interfaz para mostrar el aviso de retraso.
    descartado = (pasos_posibles - pasos) * dt_paso
    resto = max(0.0, acumulado - pasos_posibles * dt_paso)  # fracción de paso pendiente
    nuevo_estado = replace(estado, acumulador=resto, descartado_total=estado.descartado_total + descartado)
    return ResultadoTiempo(nuevo_estado, pasos, atrasado, descartado)


def aplicar_pasos(estado: T, n_pasos: int, paso: Callable[[T], T]) -> T:
    """Aplica `paso` n veces al estado y devuelve el estado final.

    `paso` es la función de actualización del motor (se pasa como argumento, así
    este módulo no depende de ningún contrato todavía). Se expresa con reduce:
    cada iteración recibe el estado anterior y devuelve uno nuevo.
    """
    if n_pasos < 0:
        raise ValueError(f"n_pasos no puede ser negativo (recibido {n_pasos})")
    return reduce(lambda acumulado, _: paso(acumulado), range(n_pasos), estado)


def devolver_pasos(estado: EstadoTiempo, n_pasos: int, dt_paso: float) -> EstadoTiempo:
    """Devuelve al acumulador `n_pasos` que se calcularon pero no llegaron a ejecutarse.

    Se usa al pausar: el estado sigue siendo el mismo, así que esos pasos se ejecutarán
    al reanudar. Función pura.
    """
    if n_pasos < 0:
        raise ValueError(f"n_pasos no puede ser negativo (recibido {n_pasos})")
    return replace(estado, acumulador=estado.acumulador + n_pasos * dt_paso)


def cancelar_pasos(estado: EstadoTiempo, n_pasos: int, dt_paso: float) -> EstadoTiempo:
    """Registra `n_pasos` abandonados (reinicio o cierre) en `cancelado_total`. Función pura."""
    if n_pasos < 0:
        raise ValueError(f"n_pasos no puede ser negativo (recibido {n_pasos})")
    return replace(estado, cancelado_total=estado.cancelado_total + n_pasos * dt_paso)
