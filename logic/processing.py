from models import Ant, AntResult, WorldView
from logic.behavior import actualizar_hormiga


def procesar_hormigas(
    ants: tuple[Ant, ...],
    vista: WorldView
) -> tuple[AntResult, ...]:
    """
    Procesa todas las hormigas utilizando la misma vista del mundo.
    """

    resultados = tuple(
        actualizar_hormiga(ant, vista)
        for ant in ants
    )

    return resultados
