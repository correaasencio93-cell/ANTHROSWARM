from models import Ant, Food, SimConfig
from logic.utils import distancia


def buscar_comida(
    ant: Ant,
    foods: tuple[Food, ...],
    config: SimConfig
) -> Food | None:
    """
    Busca la comida disponible más cercana dentro del radio de percepción.
    """

    comidas_cercanas = [
        comida
        for comida in foods
        if comida.amount > 0
        and distancia(ant.x, ant.y, comida.x, comida.y) <= config.sense_radius
    ]

    if not comidas_cercanas:
        return None

    return min(
        comidas_cercanas,
        key=lambda comida: (
            distancia(ant.x, ant.y, comida.x, comida.y),
            comida.id
        )
    )
