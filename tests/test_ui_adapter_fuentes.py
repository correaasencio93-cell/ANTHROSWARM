"""Fuentes agotadas en el adaptador. Usa estados DE PRUEBA (SimpleNamespace): no depende del motor."""
from types import SimpleNamespace as NS

from ui import adapter


def fuente(i, x, y, cantidad, radio=12.0):
    return NS(id=i, x=x, y=y, amount=cantidad, radius=radio)


def estado(foods):
    return NS(config=NS(width=960, height=720, pheromone_deposit=1.0),
              nest=NS(x=480.0, y=360.0, radius=20.0, food_stored=0),
              foods=tuple(foods), ants=(), pheromones=())


def test_una_fuente_agotada_sigue_apareciendo_con_cantidad_cero_en_su_posicion_original():
    inicial = estado([fuente(1, 100, 100, 50), fuente(2, 700, 500, 30, radio=15.0)])
    actual = estado([fuente(2, 700, 500, 12, radio=15.0)])           # la 1 se agotó y el motor la eliminó
    s = adapter.a_snapshot(actual, inicial)
    assert len(s.fuentes) == 2
    agotada, viva = s.fuentes
    assert (agotada.x, agotada.y, agotada.cantidad, agotada.cantidad_inicial, agotada.radio) == (100, 100, 0, 50, 12.0)
    assert (viva.cantidad, viva.cantidad_inicial, viva.radio) == (12, 30, 15.0)


def test_se_conserva_el_orden_original_y_todas_agotadas_siguen_dibujandose():
    inicial = estado([fuente(i, 10 * i, 10 * i, 5) for i in (3, 1, 2)])
    s = adapter.a_snapshot(estado([]), inicial)
    assert [f.x for f in s.fuentes] == [30, 10, 20] and all(f.cantidad == 0 for f in s.fuentes)


def test_sin_referencia_usa_el_propio_estado():
    e = estado([fuente(1, 5, 5, 9)])
    s = adapter.a_snapshot(e)
    assert [(f.cantidad, f.cantidad_inicial) for f in s.fuentes] == [(9, 9)]


def test_una_fuente_que_no_estaba_en_la_referencia_no_se_pierde():
    s = adapter.a_snapshot(estado([fuente(1, 5, 5, 9), fuente(7, 50, 50, 4)]), estado([fuente(1, 5, 5, 9)]))
    assert [f.x for f in s.fuentes] == [5, 50]


def test_la_comida_disponible_no_cuenta_las_agotadas():
    from ui.snapshot import comida_disponible
    s = adapter.a_snapshot(estado([fuente(2, 1, 1, 7)]), estado([fuente(1, 9, 9, 50), fuente(2, 1, 1, 10)]))
    assert comida_disponible(s) == 7 and len(s.fuentes) == 2
