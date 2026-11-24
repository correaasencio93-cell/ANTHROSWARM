import math
from dataclasses import replace

from models import Ant, SimConfig
from logic.utils import normalizar_angulo


def mover_hormiga(ant: Ant, config: SimConfig) -> Ant:
    """
    Mueve una hormiga según su ángulo, velocidad y tiempo.
    También controla los límites del mundo.
    """

    distancia_recorrida = config.speed * config.dt

    nuevo_x = ant.x + distancia_recorrida * math.cos(ant.angle)
    nuevo_y = ant.y + distancia_recorrida * math.sin(ant.angle)

    nuevo_angulo = ant.angle

    if nuevo_x < 0:
        nuevo_x = 0.0
        nuevo_angulo = math.pi - nuevo_angulo

    elif nuevo_x > config.width:
        nuevo_x = float(config.width)
        nuevo_angulo = math.pi - nuevo_angulo

    if nuevo_y < 0:
        nuevo_y = 0.0
        nuevo_angulo = -nuevo_angulo

    elif nuevo_y > config.height:
        nuevo_y = float(config.height)
        nuevo_angulo = -nuevo_angulo

    nuevo_angulo = normalizar_angulo(nuevo_angulo)

    return replace(
        ant,
        x=nuevo_x,
        y=nuevo_y,
        angle=nuevo_angulo
    )
