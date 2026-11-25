"""Estado de la interfaz (inmutable) y reglas puras para cambiarlo.

Cada evento del usuario se traduce a una Accion; `aplicar_accion` recibe el estado
actual y devuelve uno NUEVO. No usa pygame ni conoce el motor.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum, auto

# --- Distribución de la ventana (aprobada: 1280x720) ---
ANCHO_VENTANA: int = 1280
ALTO_VENTANA: int = 720
ANCHO_PANEL: int = 320
ANCHO_ESCENARIO: int = ANCHO_VENTANA - ANCHO_PANEL  # 960
MARGEN: int = 16
FPS_OBJETIVO: int = 60  # límite de dibujo; NO define la velocidad de la simulación

# --- Valores permitidos ---
# Nombres propios de la interfaz. El adaptador (adapter.py) los traducirá al
# contrato real de Jean Pierre cuando exista.
MODO_SECUENCIAL: str = "secuencial"
MODO_PARALELO: str = "paralelo"
MODOS: tuple[str, ...] = (MODO_SECUENCIAL, MODO_PARALELO)
MULTIPLICADORES: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0)


@dataclass(frozen=True)
class EstadoUI:
    """Estado de los controles.

    `reinicios` es un contador: cada vez que sube, el Game Loop sabe que debe
    pedir un estado inicial nuevo al motor (compara con el valor del cuadro anterior).
    """
    modo: str = MODO_SECUENCIAL
    en_pausa: bool = False
    multiplicador: float = 1.0
    reinicios: int = 0


class TipoAccion(Enum):
    ALTERNAR_PAUSA = auto()
    REINICIAR = auto()
    FIJAR_VELOCIDAD = auto()
    FIJAR_MODO = auto()


@dataclass(frozen=True)
class Accion:
    """Algo que el usuario pidió. `valor` solo se usa en FIJAR_VELOCIDAD y FIJAR_MODO."""
    tipo: TipoAccion
    valor: float | str | None = None


def aplicar_accion(estado: EstadoUI, accion: Accion) -> EstadoUI:
    """Devuelve un EstadoUI nuevo con la acción aplicada (el original no cambia)."""
    match accion.tipo:
        case TipoAccion.ALTERNAR_PAUSA:
            return replace(estado, en_pausa=not estado.en_pausa)
        case TipoAccion.REINICIAR:
            # Solo avisa del reinicio; pausa, velocidad y modo se conservan.
            return replace(estado, reinicios=estado.reinicios + 1)
        case TipoAccion.FIJAR_VELOCIDAD:
            if accion.valor not in MULTIPLICADORES:
                raise ValueError(f"Velocidad no permitida: {accion.valor!r}")
            return replace(estado, multiplicador=float(accion.valor))
        case TipoAccion.FIJAR_MODO:
            if accion.valor not in MODOS:
                raise ValueError(f"Modo no permitido: {accion.valor!r}")
            return replace(estado, modo=accion.valor)
    raise ValueError(f"Acción desconocida: {accion!r}")


def texto_estado(estado: EstadoUI) -> str:
    """Etiqueta de la cabecera del panel."""
    return "PAUSADO" if estado.en_pausa else "EN MARCHA"
