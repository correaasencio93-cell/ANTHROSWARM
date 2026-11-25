import dataclasses
from functools import reduce

import pytest

from ui.timestep import (
    DT_PASO,
    MAX_PASOS_POR_CUADRO,
    EstadoTiempo,
    aplicar_pasos,
    avanzar_tiempo,
)


def simular(fps, segundos, multiplicador, en_pausa=False):
    """Simula `segundos` de tiempo real dibujando a `fps`; devuelve el total de pasos."""
    dt_real = 1.0 / fps

    def cuadro(acc, _):
        estado, total = acc
        r = avanzar_tiempo(estado, dt_real, multiplicador, en_pausa)
        return r.estado, total + r.pasos

    return reduce(cuadro, range(round(fps * segundos)), (EstadoTiempo(), 0))[1]


def test_dt_acordado_es_1_sobre_60():
    assert DT_PASO == 1.0 / 60.0


def test_un_cuadro_a_60_fps_con_1x_da_un_paso():
    r = avanzar_tiempo(EstadoTiempo(), DT_PASO, 1.0, False)
    assert r.pasos == 1
    assert r.estado.acumulador == pytest.approx(0.0, abs=1e-9)
    assert r.atrasado is False


@pytest.mark.parametrize("fps", [30, 60, 120])
def test_los_pasos_por_segundo_no_dependen_de_los_fps(fps):
    assert simular(fps, 1, 1.0) == 60


@pytest.mark.parametrize("multiplicador,esperado", [(0.5, 30), (1.0, 60), (2.0, 120), (4.0, 240)])
def test_multiplicadores_cambian_la_cantidad_de_pasos_no_su_duracion(multiplicador, esperado):
    assert simular(60, 1, multiplicador) == esperado


def test_en_pausa_no_hay_pasos_ni_se_acumula_tiempo():
    inicial = EstadoTiempo(0.004)
    r = avanzar_tiempo(inicial, 10.0, 1.0, True)
    assert r.pasos == 0
    assert r.estado == inicial


def test_al_reanudar_no_hay_rafaga_de_pasos():
    pausado = avanzar_tiempo(EstadoTiempo(), 10.0, 1.0, True).estado
    r = avanzar_tiempo(pausado, DT_PASO, 1.0, False)
    assert r.pasos == 1


def test_el_tope_evita_la_espiral_y_avisa_del_retraso():
    r = avanzar_tiempo(EstadoTiempo(), 1.0, 1.0, False)  # 1 s real en un solo cuadro
    assert r.pasos == MAX_PASOS_POR_CUADRO
    assert r.atrasado is True
    assert 0.0 <= r.estado.acumulador < DT_PASO


def test_el_tiempo_descartado_se_registra_y_no_se_pierde_en_silencio():
    r = avanzar_tiempo(EstadoTiempo(), 1.0, 1.0, False)
    # 1 s = 60 pasos posibles; se ejecutan 8; los otros 52 se contabilizan.
    assert r.descartado == pytest.approx((60 - MAX_PASOS_POR_CUADRO) * DT_PASO)
    assert r.estado.descartado_total == pytest.approx(r.descartado)


def test_el_descartado_total_se_acumula_entre_cuadros():
    r1 = avanzar_tiempo(EstadoTiempo(), 1.0, 1.0, False)
    r2 = avanzar_tiempo(r1.estado, 1.0, 1.0, False)
    assert r2.estado.descartado_total == pytest.approx(r1.descartado + r2.descartado)


def test_sin_retraso_no_se_descarta_nada():
    r = avanzar_tiempo(EstadoTiempo(), DT_PASO * 3, 1.0, False)
    assert r.atrasado is False
    assert r.descartado == 0.0
    assert r.estado.descartado_total == 0.0


@pytest.mark.parametrize("dt_real,mult", [(0.004, 1.0), (0.02, 1.0), (0.5, 1.0), (2.0, 4.0), (0.3, 0.5)])
def test_el_tiempo_se_conserva(dt_real, mult):
    """tiempo que entra = pasos ejecutados + descartado + resto pendiente."""
    previo = EstadoTiempo(0.007)
    r = avanzar_tiempo(previo, dt_real, mult, False)
    entra = previo.acumulador + dt_real * mult
    sale = r.pasos * DT_PASO + r.descartado + r.estado.acumulador
    assert sale == pytest.approx(entra, abs=1e-8)


def test_en_pausa_no_se_descarta_tiempo():
    r = avanzar_tiempo(EstadoTiempo(), 10.0, 1.0, True)
    assert r.descartado == 0.0 and r.atrasado is False


def test_el_tiempo_sobrante_se_conserva_para_el_siguiente_cuadro():
    r1 = avanzar_tiempo(EstadoTiempo(), DT_PASO * 1.5, 1.0, False)
    assert r1.pasos == 1
    r2 = avanzar_tiempo(r1.estado, DT_PASO * 0.5, 1.0, False)
    assert r2.pasos == 1


def test_no_modifica_el_estado_recibido():
    inicial = EstadoTiempo(0.001)
    avanzar_tiempo(inicial, DT_PASO, 1.0, False)
    assert inicial == EstadoTiempo(0.001)


def test_el_estado_es_inmutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        EstadoTiempo().acumulador = 1.0


@pytest.mark.parametrize("dt_real,mult", [(-0.1, 1.0), (0.1, 0.0), (0.1, -1.0)])
def test_argumentos_invalidos(dt_real, mult):
    with pytest.raises(ValueError):
        avanzar_tiempo(EstadoTiempo(), dt_real, mult, False)


def test_aplicar_pasos_repite_la_funcion_n_veces():
    assert aplicar_pasos(0, 5, lambda x: x + 1) == 5
    assert aplicar_pasos((), 3, lambda t: t + (len(t),)) == (0, 1, 2)


def test_aplicar_pasos_con_cero_devuelve_el_mismo_estado():
    estado = (1, 2, 3)
    assert aplicar_pasos(estado, 0, lambda t: t + (9,)) is estado


def test_aplicar_pasos_negativo():
    with pytest.raises(ValueError):
        aplicar_pasos(0, -1, lambda x: x)


# ------------------------------------------------ pasos devueltos / cancelados (ui/runner)
def test_devolver_pasos_los_regresa_al_acumulador_y_no_toca_lo_demas():
    from ui.timestep import EstadoTiempo, devolver_pasos
    e = EstadoTiempo(acumulador=0.002, descartado_total=0.5, cancelado_total=0.25)
    n = devolver_pasos(e, 3, DT_PASO)
    assert n.acumulador == pytest.approx(0.002 + 3 * DT_PASO)
    assert (n.descartado_total, n.cancelado_total) == (0.5, 0.25) and e.acumulador == 0.002


def test_cancelar_pasos_los_registra_sin_tocar_el_acumulador():
    from ui.timestep import EstadoTiempo, cancelar_pasos
    n = cancelar_pasos(EstadoTiempo(0.002, 0.5, 0.25), 4, DT_PASO)
    assert n.cancelado_total == pytest.approx(0.25 + 4 * DT_PASO)
    assert (n.acumulador, n.descartado_total) == (0.002, 0.5)


def test_devolver_y_cancelar_rechazan_cantidades_negativas():
    from ui.timestep import EstadoTiempo, cancelar_pasos, devolver_pasos
    for f in (devolver_pasos, cancelar_pasos):
        with pytest.raises(ValueError):
            f(EstadoTiempo(), -1, DT_PASO)
