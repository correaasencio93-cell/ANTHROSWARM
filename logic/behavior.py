import math
import random
from dataclasses import replace

from models import Ant, AntState, AntResult, WorldView, Pheromone
from logic.utils import distancia, normalizar_angulo
from logic.movement import mover_hormiga
from logic.food import buscar_comida
from logic.pheromones import seguir_feromonas


def actualizar_hormiga(ant: Ant, vista: WorldView) -> AntResult:
    """
    Actualiza una hormiga utilizando únicamente la información
    de la vista del mundo recibida.
    """

    config = vista.config

    rng = random.Random(hash((config.seed, vista.tick, ant.id)))

    nueva_hormiga = ant
    food_claim_id = None
    delivered = False
    new_pheromone = None

    def girar_y_mover(hormiga: Ant) -> Ant:
        hay_feromona = any(
            feromona.intensity > 0
            and distancia(
                hormiga.x, hormiga.y,
                feromona.x, feromona.y
            ) <= config.sense_radius
            for feromona in vista.pheromones
        )

        if hay_feromona:
            angulo = seguir_feromonas(
                hormiga, vista.pheromones, config
            )
        else:
            giro = rng.uniform(-config.max_turn, config.max_turn)
            angulo = normalizar_angulo(hormiga.angle + giro)

        hormiga = replace(hormiga, angle=angulo)
        return mover_hormiga(hormiga, config)

    if ant.state == AntState.EXPLORING:

        comida = buscar_comida(ant, vista.foods, config)

        if comida is not None:
            angulo = math.atan2(
                comida.y - ant.y,
                comida.x - ant.x
            )

            nueva_hormiga = replace(
                ant,
                angle=normalizar_angulo(angulo),
                state=AntState.COLLECTING,
                target_food_id=comida.id
            )

            nueva_hormiga = mover_hormiga(nueva_hormiga, config)

        else:
            nueva_hormiga = girar_y_mover(ant)

    elif ant.state == AntState.COLLECTING:

        comida = next(
            (
                f for f in vista.foods
                if f.id == ant.target_food_id and f.amount > 0
            ),
            None
        )

        if comida is None:
            hormiga = replace(
                ant,
                state=AntState.EXPLORING,
                has_food=False,
                target_food_id=None
            )
            nueva_hormiga = girar_y_mover(hormiga)

        elif distancia(
            ant.x, ant.y, comida.x, comida.y
        ) <= comida.radius:

            angulo = math.atan2(
                vista.nest.y - ant.y,
                vista.nest.x - ant.x
            )

            nueva_hormiga = replace(
                ant,
                angle=normalizar_angulo(angulo),
                state=AntState.RETURNING,
                has_food=True
            )

            food_claim_id = comida.id

        else:
            angulo = math.atan2(
                comida.y - ant.y,
                comida.x - ant.x
            )

            hormiga = replace(
                ant,
                angle=normalizar_angulo(angulo)
            )

            nueva_hormiga = mover_hormiga(hormiga, config)

    elif ant.state == AntState.RETURNING:

        if distancia(
            ant.x, ant.y,
            vista.nest.x, vista.nest.y
        ) <= vista.nest.radius:

            nueva_hormiga = replace(
                ant,
                angle=normalizar_angulo(ant.angle + math.pi),
                state=AntState.EXPLORING,
                has_food=False,
                target_food_id=None
            )

            delivered = True

        else:
            angulo = math.atan2(
                vista.nest.y - ant.y,
                vista.nest.x - ant.x
            )

            hormiga = replace(
                ant,
                angle=normalizar_angulo(angulo)
            )

            nueva_hormiga = mover_hormiga(hormiga, config)

            if (
                config.deposit_interval > 0
                and (vista.tick + ant.id) % config.deposit_interval == 0
            ):
                new_pheromone = Pheromone(
                    x=ant.x,
                    y=ant.y,
                    intensity=config.pheromone_deposit
                )

    return AntResult(
        ant=nueva_hormiga,
        food_claim_id=food_claim_id,
        delivered=delivered,
        new_pheromone=new_pheromone
    )
