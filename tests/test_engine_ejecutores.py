import pickle
from dataclasses import FrozenInstanceError

import pytest

from engine import (
    ErrorConsolidacion, abrir_motor, configurar_workers, detectar_nucleos,
    ejecutor_paralelo, nucleos_totales, procesar_secuencial, procesar_segmento,
    validar_resultados,
)
from logic import crear_estado_inicial, crear_vista, procesar_hormigas, update
from models import SimConfig


@pytest.fixture(scope="module")
def estado():
    return crear_estado_inicial(SimConfig(seed=7), 500)


@pytest.fixture(scope="module")
def motor():
    with abrir_motor(n_workers=2) as m:
        yield m


# --------------------------------------------------------------- workers
def test_nucleos():
    assert nucleos_totales() >= detectar_nucleos() >= 1


def test_configurar_workers():
    assert configurar_workers(None) == detectar_nucleos()
    assert configurar_workers(3) == 3
    for malo in (0, -2, "2", 1.5):
        with pytest.raises(ValueError):
            configurar_workers(malo)


def test_procesar_segmento_solo_delega_en_logic(estado):
    vista = crear_vista(estado)
    assert procesar_segmento(estado.ants, vista) == procesar_hormigas(estado.ants, vista)


# ------------------------------------------------------- contrato ejecutor
@pytest.mark.parametrize("n_workers,n_segmentos", [(1, 1), (2, 2), (2, 7), (3, 3), (4, 16)])
def test_un_resultado_por_hormiga_y_en_orden(estado, n_workers, n_segmentos):
    vista = crear_vista(estado)
    with abrir_motor(n_workers=n_workers, n_segmentos=n_segmentos) as m:
        res = ejecutor_paralelo(m)(estado.ants, vista)
    assert len(res) == len(estado.ants)
    assert [r.ant.id for r in res] == [a.id for a in estado.ants]
    assert res == procesar_secuencial(estado.ants, vista)


def test_sin_hormigas(motor, estado):
    assert ejecutor_paralelo(motor)((), crear_vista(estado)) == ()


def test_validar_detecta_faltantes_y_desorden(estado):
    vista = crear_vista(estado)
    res = procesar_secuencial(estado.ants[:5], vista)
    with pytest.raises(ErrorConsolidacion):
        validar_resultados(estado.ants[:5], res[:4])
    with pytest.raises(ErrorConsolidacion):
        validar_resultados(estado.ants[:5], (res[1], res[0]) + res[2:])
    assert validar_resultados(estado.ants[:5], res) == res


def test_estado_original_intacto(motor, estado):
    copia = pickle.loads(pickle.dumps(estado))
    nuevo = update(estado, ejecutor_paralelo(motor))
    assert estado == copia
    assert nuevo is not estado and nuevo.tick == estado.tick + 1


def test_motor_es_inmutable(motor):
    with pytest.raises(FrozenInstanceError):
        motor.n_workers = 99


# ----------------------------------------------------- ciclo de vida del pool
def test_pool_se_reutiliza_entre_frames(estado):
    with abrir_motor(n_workers=2) as m:
        ejecutor = ejecutor_paralelo(m)
        pids = sorted(p.pid for p in m.pool._pool)
        s = estado
        for _ in range(5):
            s = update(s, ejecutor)
        assert sorted(p.pid for p in m.pool._pool) == pids


def test_cierre_ordenado(estado):
    with abrir_motor(n_workers=2) as m:
        procesos = list(m.pool._pool)
        assert all(p.is_alive() for p in procesos)
    assert all(not p.is_alive() for p in procesos)
    with pytest.raises(ValueError):                 # Pool cerrado
        ejecutor_paralelo(m)(estado.ants, crear_vista(estado))


def test_error_dentro_del_with_termina_workers(estado):
    with pytest.raises(ZeroDivisionError):
        with abrir_motor(n_workers=2) as m:
            procesos = list(m.pool._pool)
            update(estado, ejecutor_paralelo(m))
            1 / 0
    assert all(not p.is_alive() for p in procesos)


def test_parametros_invalidos():
    with pytest.raises(ValueError):
        with abrir_motor(n_workers=0):
            pass
    with pytest.raises(ValueError):
        with abrir_motor(n_workers=2, n_segmentos=0):
            pass
