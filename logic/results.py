from dataclasses import replace

from models import GameState, AntState, AntResult
from logic.pheromones import evaporar_feromonas, limitar_feromonas


def aplicar_resultados(
    state: GameState,
    resultados: tuple[AntResult, ...]
) -> GameState:
    """
    Consolida los resultados de todas las hormigas de forma determinista.
    """

    resultados_ordenados = sorted(
        resultados,
        key=lambda resultado: resultado.ant.id
    )

    comidas_disponibles = {
        comida.id: comida.amount
        for comida in state.foods
    }

    comidas_reclamadas = {
        comida_id: 0
        for comida_id in comidas_disponibles
    }

    hormigas_actualizadas = []

    feromonas_nuevas = []

    entregas = 0

    for resultado in resultados_ordenados:

        hormiga = resultado.ant

        if resultado.food_claim_id is not None:

            comida_id = resultado.food_claim_id

            if (
                comida_id in comidas_disponibles
                and comidas_reclamadas[comida_id]
                < comidas_disponibles[comida_id]
            ):
                comidas_reclamadas[comida_id] += 1

            else:
                hormiga = replace(
                    hormiga,
                    state=AntState.EXPLORING,
                    has_food=False,
                    target_food_id=None
                )

        if resultado.delivered:
            entregas += 1

        if resultado.new_pheromone is not None:
            feromonas_nuevas.append(resultado.new_pheromone)

        hormigas_actualizadas.append(hormiga)

    comidas_actualizadas = tuple(
        replace(
            comida,
            amount=comida.amount - comidas_reclamadas[comida.id]
        )
        for comida in state.foods
        if comida.amount - comidas_reclamadas[comida.id] > 0
    )

    nuevo_nido = replace(
        state.nest,
        food_stored=state.nest.food_stored + entregas
    )

    feromonas_evaporadas = evaporar_feromonas(
        state.pheromones,
        state.config
    )

    feromonas_consolidadas = (
        feromonas_evaporadas + tuple(feromonas_nuevas)
    )

    feromonas_limitadas = limitar_feromonas(
        feromonas_consolidadas,
        state.config
    )

    return replace(
        state,
        ants=tuple(hormigas_actualizadas),
        foods=comidas_actualizadas,
        nest=nuevo_nido,
        pheromones=feromonas_limitadas,
        tick=state.tick + 1
    )
