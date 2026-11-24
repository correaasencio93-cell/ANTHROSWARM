"""Equivalencia secuencial == paralelo (Anexo A, punto 4)."""
from dataclasses import replace

import pytest

from engine import abrir_motor, ejecutor_paralelo, procesar_secuencial
from logic import crear_estado_inicial, update
from models import SimConfig


@pytest.fixture(scope="module")
def motor():
    with abrir_motor(n_workers=2) as m:
        yield ejecutor_paralelo(m)


def total_comida(s):
    return (sum(f.amount for f in s.foods) + s.nest.food_stored
            + sum(a.has_food for a in s.ants))


@pytest.mark.parametrize("n", [1000, 3000, 5000])
def test_equivalencia_por_tamano(motor, n):
    inicial = crear_estado_inicial(SimConfig(seed=42), n)
    s_seq, s_par = inicial, inicial
    for _ in range(3):
        s_seq = update(s_seq, procesar_secuencial)
        s_par = update(s_par, motor)
        assert s_seq == s_par
    assert len(s_par.ants) == n


def test_equivalencia_con_competencia_por_comida_y_feromonas(motor):
    """Mundo pequeño y comida escasa: muchas hormigas reclaman las últimas
    unidades, hay entregas y se forman feromonas. Se compara tick a tick."""
    cfg = SimConfig(width=400, height=300, seed=3, max_pheromones=150)
    inicial = crear_estado_inicial(cfg, 600)
    inicial = replace(inicial, foods=tuple(replace(f, amount=3) for f in inicial.foods))
    total = total_comida(inicial)

    s_seq, s_par = inicial, inicial
    vio_feromonas = False
    for _ in range(250):
        s_seq = update(s_seq, procesar_secuencial)
        s_par = update(s_par, motor)
        assert s_seq == s_par
        assert total_comida(s_par) == total
        assert len(s_par.pheromones) <= cfg.max_pheromones
        vio_feromonas |= bool(s_par.pheromones)
    assert vio_feromonas
    assert s_par.nest.food_stored > 0


@pytest.mark.parametrize("n_workers", [1, 3, 4])
def test_resultado_no_depende_de_la_cantidad_de_workers(n_workers):
    inicial = crear_estado_inicial(SimConfig(seed=11), 800)
    ref = inicial
    for _ in range(4):
        ref = update(ref, procesar_secuencial)
    s = inicial
    with abrir_motor(n_workers=n_workers) as m:
        for _ in range(4):
            s = update(s, ejecutor_paralelo(m))
    assert s == ref


def test_equivalencia_con_spawn():
    """Con 'spawn' (el método de Windows y macOS) cada worker es un intérprete
    nuevo; el azar por hash((seed, tick, id)) debe dar lo mismo."""
    inicial = crear_estado_inicial(SimConfig(seed=5), 300)
    with abrir_motor(n_workers=2, metodo_inicio="spawn") as m:
        e = ejecutor_paralelo(m)
        assert update(update(inicial, e), e) == update(update(inicial))
