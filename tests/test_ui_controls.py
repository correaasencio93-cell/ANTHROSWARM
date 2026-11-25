import itertools
import subprocess
import sys
from pathlib import Path

import pytest

from ui.controls import (
    ALTO_BOTON,
    BOTONES,
    X_PANEL,
    accion_para_clic,
    accion_para_tecla,
    boton_activo,
    boton_en,
    contiene,
    etiqueta_boton,
)
from ui.interface import (
    ALTO_VENTANA,
    ANCHO_VENTANA,
    MARGEN,
    MODO_PARALELO,
    MODOS,
    MULTIPLICADORES,
    Accion,
    EstadoUI,
    TipoAccion,
)

RAIZ = Path(__file__).resolve().parents[1]


def centro(rect):
    x, y, w, h = rect
    return x + w // 2, y + h // 2


def por_id(identificador):
    return next(b for b in BOTONES if b.id == identificador)


def test_hay_un_boton_por_cada_control_aprobado():
    assert len(BOTONES) == 2 + len(MULTIPLICADORES) + len(MODOS)
    assert len({b.id for b in BOTONES}) == len(BOTONES)


def test_los_botones_quedan_dentro_del_panel_y_de_la_ventana():
    for b in BOTONES:
        x, y, w, h = b.rect
        assert x >= X_PANEL
        assert x + w <= ANCHO_VENTANA - MARGEN
        assert y >= 0 and y + h <= ALTO_VENTANA - MARGEN


def test_los_botones_no_se_superponen():
    for a, b in itertools.combinations(BOTONES, 2):
        ax, ay, aw, ah = a.rect
        bx, by, bw, bh = b.rect
        separados = ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay
        assert separados, f"{a.id} y {b.id} se superponen"


def test_los_botones_son_suficientemente_grandes():
    assert all(b.rect[3] >= ALTO_BOTON >= 44 for b in BOTONES)


def test_clic_en_el_centro_de_cada_boton_devuelve_su_accion():
    for b in BOTONES:
        assert boton_en(centro(b.rect)) == b
        assert accion_para_clic(centro(b.rect)) == b.accion


def test_clic_fuera_de_los_botones_no_hace_nada():
    assert accion_para_clic((100, 100)) is None   # en el escenario
    assert accion_para_clic((X_PANEL, 10)) is None  # cabecera del panel


def test_contiene_incluye_el_borde_inicial_y_excluye_el_final():
    assert contiene((10, 10, 5, 5), (10, 10)) is True
    assert contiene((10, 10, 5, 5), (14, 14)) is True
    assert contiene((10, 10, 5, 5), (15, 15)) is False


def test_atajos_de_teclado():
    assert accion_para_tecla("space") == Accion(TipoAccion.ALTERNAR_PAUSA)
    assert accion_para_tecla("r") == Accion(TipoAccion.REINICIAR)
    assert accion_para_tecla("x") is None


def test_resaltado_inicial():
    e = EstadoUI()
    activos = {b.id for b in BOTONES if boton_activo(b, e)}
    assert activos == {"vel_1", "modo_secuencial"}


def test_resaltado_sigue_al_estado():
    e = EstadoUI(modo=MODO_PARALELO, en_pausa=True, multiplicador=4.0)
    activos = {b.id for b in BOTONES if boton_activo(b, e)}
    assert activos == {"pausa", "vel_4", "modo_paralelo"}


def test_la_etiqueta_de_pausa_cambia_a_reanudar():
    assert etiqueta_boton(por_id("pausa"), EstadoUI(en_pausa=False)) == "Pausa"
    assert etiqueta_boton(por_id("pausa"), EstadoUI(en_pausa=True)) == "Reanudar"
    assert etiqueta_boton(por_id("vel_2"), EstadoUI()) == "2×"


def test_los_modulos_puros_no_importan_pygame():
    codigo = ("import sys, ui.timestep, ui.interface, ui.controls; "
              "assert 'pygame' not in sys.modules")
    resultado = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ,
                               capture_output=True, text=True)
    assert resultado.returncode == 0, resultado.stderr
