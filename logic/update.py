from models import GameState
from logic.state import crear_vista
from logic.processing import procesar_hormigas
from logic.results import aplicar_resultados


def update(
    state: GameState,
    ejecutor=procesar_hormigas
) -> GameState:
    """
    Actualiza un tick de la simulación.

    1. Crea una vista del mundo.
    2. Procesa las hormigas con el ejecutor seleccionado.
    3. Consolida los resultados.
    """

    vista = crear_vista(state)

    resultados = ejecutor(state.ants, vista)

    return aplicar_resultados(state, resultados)
