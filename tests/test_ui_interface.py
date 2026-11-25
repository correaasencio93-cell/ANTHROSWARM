import dataclasses

import pytest

from ui.interface import (
    ANCHO_ESCENARIO,
    ANCHO_PANEL,
    ANCHO_VENTANA,
    MODO_PARALELO,
    MODO_SECUENCIAL,
    MULTIPLICADORES,
    Accion,
    EstadoUI,
    TipoAccion,
    aplicar_accion,
    texto_estado,
)


def test_estado_inicial():
    e = EstadoUI()
    assert (e.modo, e.en_pausa, e.multiplicador, e.reinicios) == (MODO_SECUENCIAL, False, 1.0, 0)


def test_la_ventana_se_reparte_en_escenario_y_panel():
    assert ANCHO_ESCENARIO + ANCHO_PANEL == ANCHO_VENTANA
    assert (ANCHO_ESCENARIO, ANCHO_PANEL) == (960, 320)


def test_alternar_pausa_dos_veces_vuelve_al_inicio():
    inicial = EstadoUI()
    pausado = aplicar_accion(inicial, Accion(TipoAccion.ALTERNAR_PAUSA))
    assert pausado.en_pausa is True
    assert aplicar_accion(pausado, Accion(TipoAccion.ALTERNAR_PAUSA)) == inicial


def test_aplicar_accion_no_modifica_el_estado_original():
    inicial = EstadoUI()
    aplicar_accion(inicial, Accion(TipoAccion.ALTERNAR_PAUSA))
    assert inicial == EstadoUI()


def test_el_estado_es_inmutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        EstadoUI().en_pausa = True


@pytest.mark.parametrize("m", MULTIPLICADORES)
def test_fijar_velocidad_permitida(m):
    assert aplicar_accion(EstadoUI(), Accion(TipoAccion.FIJAR_VELOCIDAD, m)).multiplicador == m


@pytest.mark.parametrize("m", [3.0, 0, -1.0, None, "2"])
def test_fijar_velocidad_no_permitida(m):
    with pytest.raises(ValueError):
        aplicar_accion(EstadoUI(), Accion(TipoAccion.FIJAR_VELOCIDAD, m))


def test_fijar_modo():
    e = aplicar_accion(EstadoUI(), Accion(TipoAccion.FIJAR_MODO, MODO_PARALELO))
    assert e.modo == MODO_PARALELO


def test_fijar_modo_no_permitido():
    with pytest.raises(ValueError):
        aplicar_accion(EstadoUI(), Accion(TipoAccion.FIJAR_MODO, "cuantico"))


def test_reiniciar_sube_el_contador_y_conserva_lo_demas():
    antes = EstadoUI(modo=MODO_PARALELO, en_pausa=True, multiplicador=4.0)
    despues = aplicar_accion(antes, Accion(TipoAccion.REINICIAR))
    assert despues.reinicios == antes.reinicios + 1
    assert (despues.modo, despues.en_pausa, despues.multiplicador) == (MODO_PARALELO, True, 4.0)


def test_texto_estado():
    assert texto_estado(EstadoUI(en_pausa=False)) == "EN MARCHA"
    assert texto_estado(EstadoUI(en_pausa=True)) == "PAUSADO"
