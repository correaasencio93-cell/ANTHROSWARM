import math

from models import Ant, Pheromone, SimConfig
from logic.utils import normalizar_angulo, diferencia_angular


def seguir_feromonas(
    ant: Ant,
    pheromones: tuple[Pheromone, ...],
    config: SimConfig
) -> float:
    """
    Calcula la dirección que debe seguir la hormiga
    según la intensidad de las feromonas cercanas.
    """

    suma_x = 0.0
    suma_y = 0.0

    for feromona in pheromones:
        distancia = math.hypot(
            feromona.x - ant.x,
            feromona.y - ant.y
        )

        if distancia <= config.sense_radius and feromona.intensity > 0:
            peso = feromona.intensity / max(distancia, 1.0)

            suma_x += peso * math.cos(
                math.atan2(feromona.y - ant.y, feromona.x - ant.x)
            )
            suma_y += peso * math.sin(
                math.atan2(feromona.y - ant.y, feromona.x - ant.x)
            )

    if suma_x == 0.0 and suma_y == 0.0:
        return ant.angle

    direccion = math.atan2(suma_y, suma_x)

    diferencia = diferencia_angular(direccion, ant.angle)

    nuevo_angulo = ant.angle + config.follow_gain * diferencia

    return normalizar_angulo(nuevo_angulo)


def evaporar_feromonas(
    pheromones: tuple[Pheromone, ...],
    config: SimConfig
) -> tuple[Pheromone, ...]:
    """
    Reduce la intensidad de las feromonas y elimina las débiles.
    """

    resultado = []

    for feromona in pheromones:
        nueva_intensidad = feromona.intensity * (1 - config.evaporation)

        if nueva_intensidad >= config.min_intensity:
            resultado.append(
                Pheromone(
                    x=feromona.x,
                    y=feromona.y,
                    intensity=nueva_intensidad
                )
            )

    return tuple(resultado)


def limitar_feromonas(
    pheromones: tuple[Pheromone, ...],
    config: SimConfig
) -> tuple[Pheromone, ...]:
    """
    Limita la cantidad máxima de feromonas almacenadas.
    """

    return pheromones[-config.max_pheromones:]
