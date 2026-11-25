"""RenderSnapshot: estructura inmutable EXCLUSIVA de presentación.

Es lo único que el renderizador sabe del simulador. Contiene solo lo necesario para
DIBUJAR (posiciones, estado visual, cantidades, intensidades ya normalizadas), no
reglas ni comportamiento. Quien la rellena desde el GameState real es adapter.py;
este módulo no importa nada del motor y no duplica su lógica.

Los campos opcionales valen None cuando el motor todavía no entrega ese dato; el
panel muestra "—" en ese caso. Nunca se rellenan con valores inventados.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class EstadoHormigaVista(Enum):
    """Estado de una hormiga tal como se dibuja (nombres propios de la interfaz)."""
    EXPLORANDO = "explorando"
    RECOLECTANDO = "recolectando"
    REGRESANDO = "regresando"
    ENTREGANDO = "entregando"


@dataclass(frozen=True, slots=True)
class HormigaVista:
    x: float
    y: float
    estado: EstadoHormigaVista


@dataclass(frozen=True, slots=True)
class HormigueroVista:
    x: float
    y: float
    radio: float


@dataclass(frozen=True, slots=True)
class FuenteVista:
    x: float
    y: float
    cantidad: int
    cantidad_inicial: int
    radio: float = 12.0   # en unidades del mundo; el adaptador lo toma del motor


@dataclass(frozen=True, slots=True)
class CapaFeromonaVista:
    """Cuadrícula de intensidades 0.0-1.0, por filas (fila 0 arriba).

    La normalización a 0-1 la hace el adaptador; aquí solo se valida el tamaño.
    """
    columnas: int
    filas: int
    intensidades: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.columnas < 1 or self.filas < 1:
            raise ValueError("La cuadrícula debe tener al menos 1 columna y 1 fila")
        if len(self.intensidades) != self.columnas * self.filas:
            raise ValueError(
                f"Se esperaban {self.columnas * self.filas} intensidades "
                f"y llegaron {len(self.intensidades)}")


@dataclass(frozen=True)
class RenderSnapshot:
    ancho_mundo: float
    alto_mundo: float
    hormiguero: HormigueroVista
    fuentes: tuple[FuenteVista, ...]
    hormigas: tuple[HormigaVista, ...]
    feromona_exploracion: CapaFeromonaVista | None = None
    feromona_regreso: CapaFeromonaVista | None = None
    entregadas: int | None = None          # entregas acumuladas (evento, no un estado de hormiga)
    recolectada_total: int | None = None   # None mientras Mike no confirme cómo se contabiliza


@dataclass(frozen=True)
class MetricasVista:
    """Métricas que debe entregar el motor; None = todavía no disponible."""
    workers: int | None = None
    nucleos: int | None = None
    ms_por_paso: float | None = None


def contar_por_estado(hormigas: Iterable[HormigaVista]) -> dict[EstadoHormigaVista, int]:
    """Cuenta hormigas por estado. Solo LEE; el dict devuelto es nuevo en cada llamada."""
    conteo = Counter(h.estado for h in hormigas)
    return {estado: conteo.get(estado, 0) for estado in EstadoHormigaVista}


def comida_disponible(snapshot: RenderSnapshot) -> int:
    """Suma de la comida que queda en las fuentes (lectura del snapshot)."""
    return sum(f.cantidad for f in snapshot.fuentes)
