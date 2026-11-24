import math

from models import (
    Ant, AntState, Food, Nest, Pheromone,
    SimConfig, WorldView, AntResult, GameState
)
from logic import (
    buscar_comida, mover_hormiga, seguir_feromonas,
    evaporar_feromonas, limitar_feromonas,
    actualizar_hormiga, aplicar_resultados,
    crear_estado_inicial, crear_vista
)


def crear_hormiga(
    id=0, x=10, y=10, angle=0,
    state=AntState.EXPLORING,
    has_food=False, target_food_id=None
):
    return Ant(
        id=id, x=x, y=y, angle=angle,
        state=state, has_food=has_food,
        target_food_id=target_food_id
    )


def crear_vista_prueba(
    hormiga=None, comidas=(), nido=None,
    feromonas=(), config=None, tick=0
):
    if config is None:
        config = SimConfig(
            width=100, height=100,
            speed=60, dt=1 / 60,
            sense_radius=50
        )

    if nido is None:
        nido = Nest(50, 50, 5, 0)

    return WorldView(
        foods=comidas,
        nest=nido,
        pheromones=feromonas,
        config=config,
        tick=tick
    )


def test_buscar_comida_mas_cercana():
    ant = crear_hormiga()
    foods = (
        Food(1, 30, 10, 5, 2),
        Food(2, 15, 10, 5, 2),
        Food(3, 12, 10, 5, 2),
    )
    config = SimConfig(sense_radius=50)

    resultado = buscar_comida(ant, foods, config)

    assert resultado.id == 3


def test_buscar_comida_ignora_comida_agotada():
    ant = crear_hormiga()
    foods = (
        Food(1, 11, 10, 0, 2),
        Food(2, 20, 10, 5, 2),
    )
    config = SimConfig(sense_radius=50)

    resultado = buscar_comida(ant, foods, config)

    assert resultado.id == 2


def test_buscar_comida_devuelve_none_si_no_hay_comida_cercana():
    ant = crear_hormiga()
    foods = (Food(1, 500, 500, 5, 2),)
    config = SimConfig(sense_radius=10)

    assert buscar_comida(ant, foods, config) is None


def test_mover_hormiga_avanza_segun_velocidad_y_tiempo():
    ant = crear_hormiga(x=10, y=10, angle=0)
    config = SimConfig(speed=60, dt=1 / 60)

    resultado = mover_hormiga(ant, config)

    assert resultado.x == 11
    assert resultado.y == 10
    assert ant.x == 10


def test_mover_hormiga_respeta_limite_del_mundo():
    ant = crear_hormiga(x=99.5, y=50, angle=0)
    config = SimConfig(
        width=100, height=100,
        speed=120, dt=1 / 60
    )

    resultado = mover_hormiga(ant, config)

    assert resultado.x == 100
    assert resultado.angle != ant.angle


def test_seguir_feromonas_sin_feromonas_conserva_angulo():
    ant = crear_hormiga(angle=1.2)
    config = SimConfig(sense_radius=20)

    resultado = seguir_feromonas(ant, (), config)

    assert resultado == ant.angle


def test_seguir_feromonas_sigue_direccion_de_feromona():
    ant = crear_hormiga(x=10, y=10, angle=0)
    feromonas = (Pheromone(10, 20, 5),)
    config = SimConfig(sense_radius=50, follow_gain=1)

    resultado = seguir_feromonas(ant, feromonas, config)

    assert math.isclose(resultado, math.pi / 2)


def test_evaporar_feromonas_reduce_intensidad():
    feromonas = (Pheromone(10, 10, 1.0),)
    config = SimConfig(evaporation=0.2, min_intensity=0.1)

    resultado = evaporar_feromonas(feromonas, config)

    assert math.isclose(resultado[0].intensity, 0.8)


def test_evaporar_feromonas_elimina_las_debiles():
    feromonas = (Pheromone(10, 10, 0.1),)
    config = SimConfig(evaporation=0.5, min_intensity=0.1)

    resultado = evaporar_feromonas(feromonas, config)

    assert resultado == ()


def test_limitar_feromonas_respeta_maximo():
    feromonas = tuple(
        Pheromone(i, i, 1.0) for i in range(5)
    )
    config = SimConfig(max_pheromones=2)

    resultado = limitar_feromonas(feromonas, config)

    assert len(resultado) == 2
    assert resultado == feromonas[-2:]


def test_explorando_encuentra_comida_y_pasa_a_collecting():
    ant = crear_hormiga(x=10, y=10)
    foods = (Food(1, 20, 10, 5, 2),)
    vista = crear_vista_prueba(comidas=foods)

    resultado = actualizar_hormiga(ant, vista)

    assert resultado.ant.state == AntState.COLLECTING
    assert resultado.ant.target_food_id == 1
    assert resultado.ant.x > ant.x
    assert resultado.food_claim_id is None


def test_collecting_reclama_comida_y_pasa_a_returning():
    ant = crear_hormiga(
        x=20, y=10,
        state=AntState.COLLECTING,
        target_food_id=1
    )
    foods = (Food(1, 20, 10, 5, 2),)
    vista = crear_vista_prueba(comidas=foods)

    resultado = actualizar_hormiga(ant, vista)

    assert resultado.ant.state == AntState.RETURNING
    assert resultado.ant.has_food is True
    assert resultado.food_claim_id == 1
    assert resultado.delivered is False


def test_collecting_si_desaparece_comida_vuelve_a_exploring():
    ant = crear_hormiga(
        state=AntState.COLLECTING,
        target_food_id=99
    )
    vista = crear_vista_prueba()

    resultado = actualizar_hormiga(ant, vista)

    assert resultado.ant.state == AntState.EXPLORING
    assert resultado.ant.target_food_id is None
    assert resultado.ant.has_food is False


def test_returning_llega_al_nido_y_entrega_comida():
    ant = crear_hormiga(
        x=51, y=50,
        state=AntState.RETURNING,
        has_food=True
    )
    nido = Nest(50, 50, 5, 0)
    vista = crear_vista_prueba(nido=nido)

    resultado = actualizar_hormiga(ant, vista)

    assert resultado.ant.state == AntState.EXPLORING
    assert resultado.ant.has_food is False
    assert resultado.delivered is True


def test_returning_deposita_feromona_en_intervalo():
    ant = crear_hormiga(
        id=0, x=10, y=10,
        state=AntState.RETURNING,
        has_food=True
    )
    config = SimConfig(
        width=100, height=100,
        speed=60, dt=1 / 60,
        deposit_interval=1,
        pheromone_deposit=2
    )
    vista = crear_vista_prueba(
        nido=Nest(50, 50, 5, 0),
        config=config,
        tick=0
    )

    resultado = actualizar_hormiga(ant, vista)

    assert resultado.new_pheromone is not None
    assert resultado.new_pheromone.x == 10
    assert resultado.new_pheromone.y == 10
    assert resultado.new_pheromone.intensity == 2


def test_crear_estado_inicial_distribuye_hormigas_y_comida():
    config = SimConfig(width=200, height=100)

    estado = crear_estado_inicial(config, 4)

    assert len(estado.ants) == 4
    assert len(estado.foods) == 4
    assert estado.nest.x == 100
    assert estado.nest.y == 50
    assert estado.tick == 0


def test_crear_vista_conserva_datos_del_estado():
    estado = crear_estado_inicial(SimConfig(), 3)

    vista = crear_vista(estado)

    assert vista.ants if hasattr(vista, "ants") else True
    assert vista.foods == estado.foods
    assert vista.nest == estado.nest
    assert vista.pheromones == estado.pheromones
    assert vista.tick == estado.tick


def test_aplicar_resultados_prioriza_hormigas_por_id():
    config = SimConfig(evaporation=0, max_pheromones=10)
    hormigas = tuple(
        crear_hormiga(
            id=i,
            state=AntState.RETURNING,
            has_food=True
        )
        for i in range(3)
    )
    estado = GameState(
        ants=hormigas,
        foods=(Food(1, 20, 20, 2, 2),),
        nest=Nest(50, 50, 5, 0),
        pheromones=(),
        config=config,
        tick=0
    )

    resultados = tuple(
        AntResult(
            ant=hormiga,
            food_claim_id=1,
            delivered=False,
            new_pheromone=None
        )
        for hormiga in reversed(hormigas)
    )

    nuevo_estado = aplicar_resultados(estado, resultados)

    assert [ant.id for ant in nuevo_estado.ants] == [0, 1, 2]
    assert nuevo_estado.ants[0].state == AntState.RETURNING
    assert nuevo_estado.ants[1].state == AntState.RETURNING
    assert nuevo_estado.ants[2].state == AntState.EXPLORING
    assert nuevo_estado.ants[2].has_food is False
    assert nuevo_estado.foods == ()
    assert estado.foods[0].amount == 2


def test_aplicar_resultados_actualiza_entregas_y_tick():
    config = SimConfig(evaporation=0)
    ant = crear_hormiga(
        state=AntState.EXPLORING
    )
    estado = GameState(
        ants=(ant,),
        foods=(),
        nest=Nest(50, 50, 5, 3),
        pheromones=(),
        config=config,
        tick=4
    )
    resultado = AntResult(
        ant=ant,
        food_claim_id=None,
        delivered=True,
        new_pheromone=None
    )

    nuevo_estado = aplicar_resultados(estado, (resultado,))

    assert nuevo_estado.nest.food_stored == 4
    assert nuevo_estado.tick == 5
    assert estado.nest.food_stored == 3
    assert estado.tick == 4


def test_aplicar_resultados_limita_feromonas():
    config = SimConfig(
        evaporation=0,
        min_intensity=0.01,
        max_pheromones=2
    )
    ant = crear_hormiga()
    feromonas = (
        Pheromone(1, 1, 1),
        Pheromone(2, 2, 1),
    )
    estado = GameState(
        ants=(ant,),
        foods=(),
        nest=Nest(50, 50, 5, 0),
        pheromones=feromonas,
        config=config,
        tick=0
    )
    resultado = AntResult(
        ant=ant,
        food_claim_id=None,
        delivered=False,
        new_pheromone=Pheromone(3, 3, 1)
    )

    nuevo_estado = aplicar_resultados(estado, (resultado,))

    assert len(nuevo_estado.pheromones) == 2
    assert nuevo_estado.pheromones[-1] == Pheromone(3, 3, 1)
