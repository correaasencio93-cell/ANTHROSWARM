import math

from models import (
    Ant, AntState, Food, Nest,
    Pheromone, SimConfig, GameState, WorldView
)


def crear_estado_inicial(
    config: SimConfig,
    n_hormigas: int
) -> GameState:
    """
    Crea el estado inicial de la simulación.
    """

    centro_x = config.width / 2
    centro_y = config.height / 2

    nido = Nest(
        x=centro_x,
        y=centro_y,
        radius=20.0,
        food_stored=0
    )

    hormigas = []

    for i in range(n_hormigas):
        angulo = (2 * math.pi * i) / max(n_hormigas, 1)

        hormigas.append(
            Ant(
                id=i,
                x=centro_x,
                y=centro_y,
                angle=angulo,
                state=AntState.EXPLORING,
                has_food=False,
                target_food_id=None
            )
        )

    comidas = (
        Food(0, config.width * 0.15, config.height * 0.15, 50, 8.0),
        Food(1, config.width * 0.85, config.height * 0.15, 50, 8.0),
        Food(2, config.width * 0.15, config.height * 0.85, 50, 8.0),
        Food(3, config.width * 0.85, config.height * 0.85, 50, 8.0),
    )

    return GameState(
        ants=tuple(hormigas),
        foods=comidas,
        nest=nido,
        pheromones=(),
        config=config,
        tick=0
    )


def crear_vista(state: GameState) -> WorldView:
    """
    Crea una vista inmutable del mundo para procesar las hormigas.
    """

    return WorldView(
        foods=state.foods,
        nest=state.nest,
        pheromones=state.pheromones,
        config=state.config,
        tick=state.tick
    )
