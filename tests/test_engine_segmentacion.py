import pytest

from engine import limites_segmentos, segmentar_hormigas


def test_sobrantes_van_a_los_primeros_segmentos():
    segs = segmentar_hormigas(tuple(range(10)), 3)
    assert [len(s) for s in segs] == [4, 3, 3]
    assert segs == ((0, 1, 2, 3), (4, 5, 6), (7, 8, 9))


@pytest.mark.parametrize("n", [0, 1, 2, 7, 100, 1001, 5000])
@pytest.mark.parametrize("k", [1, 2, 3, 4, 8, 16])
def test_concatenar_segmentos_devuelve_el_original(n, k):
    datos = tuple(range(n))
    segs = segmentar_hormigas(datos, k)
    assert tuple(x for s in segs for x in s) == datos
    assert all(isinstance(s, tuple) and s for s in segs)        # sin vacíos
    tam = [len(s) for s in segs]
    if tam:
        assert max(tam) - min(tam) <= 1                         # equilibrado
        assert tam == sorted(tam, reverse=True)                 # sobrantes al inicio
    assert len(segs) == min(n, k)


def test_mas_segmentos_que_hormigas():
    assert segmentar_hormigas((1, 2), 5) == ((1,), (2,))


def test_lista_vacia():
    assert segmentar_hormigas((), 4) == ()
    assert limites_segmentos(0, 4) == ()


@pytest.mark.parametrize("k", [0, -1])
def test_segmentos_invalidos(k):
    with pytest.raises(ValueError):
        segmentar_hormigas((1, 2, 3), k)
