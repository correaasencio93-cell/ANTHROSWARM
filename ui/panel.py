"""Contenido y posición de las líneas del panel de estadísticas (sin pygame).

Todo es texto calculado a partir de datos reales: el snapshot, las métricas del
motor, el estado de la interfaz, los FPS medidos por el reloj y el simulador
asíncrono (ritmo y tiempo descartado). Si un dato no está disponible se muestra
"—"; nunca se inventa un número.

"Entregas" es el contador acumulado de entregas (la entrega es un evento, no un
estado de la hormiga). "Recolectada" son las unidades que salieron de las fuentes
(comida inicial - restante): incluye las ya entregadas y las que van en camino al
hormiguero; es "—" si el adaptador no tiene el estado inicial para calcularla.
"""
from __future__ import annotations

from dataclasses import dataclass

from ui.interface import EstadoUI
from ui.snapshot import (
    EstadoHormigaVista,
    MetricasVista,
    RenderSnapshot,
    comida_disponible,
    contar_por_estado,
)

SIN_DATO: str = "—"

Y_INICIO_ESTADISTICAS: int = 60
ALTO_TITULO: int = 24
ALTO_FILA: int = 21
SEPARACION_SECCIONES: int = 8


@dataclass(frozen=True)
class LineaPanel:
    tipo: str          # "titulo" o "fila"
    etiqueta: str
    valor: str = ""


def _entero(n: int | None) -> str:
    """1000 -> '1.000' (separador de miles español); None -> '—'."""
    return SIN_DATO if n is None else f"{n:,}".replace(",", ".")


def _decimal(x: float | None, sufijo: str, decimales: int = 1) -> str:
    return SIN_DATO if x is None else f"{x:.{decimales}f} {sufijo}"


def construir_lineas_panel(snapshot: RenderSnapshot | None,
                           metricas: MetricasVista,
                           estado_ui: EstadoUI,
                           fps: float | None,
                           descartado_total: float,
                           ritmo: float | None = None) -> tuple[LineaPanel, ...]:
    hormigas = None if snapshot is None else snapshot.hormigas
    conteo = None if hormigas is None else contar_por_estado(hormigas)

    def por_estado(estado: EstadoHormigaVista) -> str:
        return SIN_DATO if conteo is None else _entero(conteo[estado])

    return (
        LineaPanel("titulo", "Simulación"),
        LineaPanel("fila", "Modo", estado_ui.modo.capitalize()),
        LineaPanel("fila", "Hormigas", SIN_DATO if hormigas is None else _entero(len(hormigas))),
        LineaPanel("fila", "Explorando", por_estado(EstadoHormigaVista.EXPLORANDO)),
        LineaPanel("fila", "Recolectando", por_estado(EstadoHormigaVista.RECOLECTANDO)),
        LineaPanel("fila", "Regresando", por_estado(EstadoHormigaVista.REGRESANDO)),
        LineaPanel("fila", "Entregas", SIN_DATO if snapshot is None else _entero(snapshot.entregadas)),
        LineaPanel("titulo", "Comida"),
        LineaPanel("fila", "Disponible", SIN_DATO if snapshot is None else _entero(comida_disponible(snapshot))),
        LineaPanel("fila", "Recolectada", SIN_DATO if snapshot is None else _entero(snapshot.recolectada_total)),
        LineaPanel("titulo", "Rendimiento"),
        LineaPanel("fila", "FPS", SIN_DATO if fps is None else f"{fps:.0f}"),
        LineaPanel("fila", "Actualización", _decimal(metricas.ms_por_paso, "ms/paso")),
        LineaPanel("fila", "Workers", _entero(metricas.workers)),
        LineaPanel("fila", "Núcleos CPU", _entero(metricas.nucleos)),
        LineaPanel("fila", "Ritmo real", SIN_DATO if ritmo is None else f"{ritmo * 100:.0f} %"),
        LineaPanel("fila", "Descartado", f"{descartado_total:.2f} s"),
    )


def posiciones_panel(lineas: tuple[LineaPanel, ...]) -> tuple[int, ...]:
    """Coordenada y de cada línea, de arriba abajo."""
    def avance(l: LineaPanel) -> int:
        return ALTO_TITULO if l.tipo == "titulo" else ALTO_FILA

    ys: list[int] = []
    y = Y_INICIO_ESTADISTICAS
    for i, linea in enumerate(lineas):
        if linea.tipo == "titulo" and i > 0:
            y += SEPARACION_SECCIONES
        ys.append(y)
        y += avance(linea)
    return tuple(ys)


def borde_inferior(lineas: tuple[LineaPanel, ...]) -> int:
    """Primera coordenada y libre bajo la última línea (debe quedar sobre los controles)."""
    ys = posiciones_panel(lineas)
    ultimo = lineas[-1]
    return ys[-1] + (ALTO_TITULO if ultimo.tipo == "titulo" else ALTO_FILA)
