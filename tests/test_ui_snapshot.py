import dataclasses

import pytest

from ui.controls import Y_TITULO_CONTROLES
from ui.interface import MODO_PARALELO, EstadoUI
from ui.panel import (
    SIN_DATO,
    Y_INICIO_ESTADISTICAS,
    borde_inferior,
    construir_lineas_panel,
    posiciones_panel,
)
from ui.snapshot import (
    CapaFeromonaVista,
    EstadoHormigaVista as E,
    FuenteVista,
    HormigaVista,
    HormigueroVista,
    MetricasVista,
    RenderSnapshot,
    comida_disponible,
    contar_por_estado,
)


def snapshot_minimo(**extra):
    """Datos de PRUEBA para tests (no provienen del motor)."""
    return RenderSnapshot(
        ancho_mundo=100, alto_mundo=100,
        hormiguero=HormigueroVista(50, 50, 5),
        fuentes=(FuenteVista(10, 10, 30, 50), FuenteVista(90, 90, 20, 20)),
        hormigas=(HormigaVista(1, 1, E.EXPLORANDO), HormigaVista(2, 2, E.EXPLORANDO),
                  HormigaVista(3, 3, E.REGRESANDO), HormigaVista(4, 4, E.RECOLECTANDO)),
        **extra)


def valores(lineas):
    return {l.etiqueta: l.valor for l in lineas if l.tipo == "fila"}


def test_contar_por_estado_incluye_todos_los_estados():
    conteo = contar_por_estado(snapshot_minimo().hormigas)
    assert conteo == {E.EXPLORANDO: 2, E.RECOLECTANDO: 1, E.REGRESANDO: 1, E.ENTREGANDO: 0}


def test_comida_disponible_suma_las_fuentes():
    assert comida_disponible(snapshot_minimo()) == 50


def test_las_estructuras_son_inmutables():
    s = snapshot_minimo()
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.ancho_mundo = 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.hormigas[0].x = 9
    assert isinstance(s.hormigas, tuple) and isinstance(s.fuentes, tuple)


def test_capa_valida_su_tamano():
    assert CapaFeromonaVista(2, 2, (0.0, 0.1, 0.2, 0.3)).columnas == 2
    with pytest.raises(ValueError):
        CapaFeromonaVista(2, 2, (0.0, 0.1, 0.2))
    with pytest.raises(ValueError):
        CapaFeromonaVista(0, 2, ())


def test_sin_motor_el_panel_muestra_guion_y_no_inventa_numeros():
    v = valores(construir_lineas_panel(None, MetricasVista(), EstadoUI(), None, 0.0))
    for etiqueta in ("Hormigas", "Explorando", "Recolectando", "Regresando", "Entregas",
                     "Disponible", "Recolectada", "FPS", "Actualización", "Workers", "Núcleos CPU"):
        assert v[etiqueta] == SIN_DATO, etiqueta
    assert v["Modo"] == "Secuencial"


def test_contadores_no_entregados_por_el_motor_quedan_en_guion():
    v = valores(construir_lineas_panel(snapshot_minimo(), MetricasVista(), EstadoUI(), 60.0, 0.0))
    assert v["Entregas"] == SIN_DATO and v["Recolectada"] == SIN_DATO
    assert v["Hormigas"] == "4" and v["Explorando"] == "2" and v["Disponible"] == "50"


def test_valores_reales_se_formatean():
    s = snapshot_minimo(entregadas=1234, recolectada_total=1234)
    m = MetricasVista(workers=8, nucleos=12, ms_por_paso=3.5)
    v = valores(construir_lineas_panel(s, m, EstadoUI(modo=MODO_PARALELO), 59.6, 1.234))
    assert v["Entregas"] == "1.234"
    assert v["Workers"] == "8" and v["Núcleos CPU"] == "12"
    assert v["Actualización"] == "3.5 ms/paso"
    assert v["FPS"] == "60" and v["Modo"] == "Paralelo" and v["Descartado"] == "1.23 s"


def test_las_estadisticas_caben_sobre_los_controles():
    lineas = construir_lineas_panel(None, MetricasVista(), EstadoUI(), None, 0.0)
    assert posiciones_panel(lineas)[0] == Y_INICIO_ESTADISTICAS
    assert borde_inferior(lineas) <= Y_TITULO_CONTROLES


def test_el_ritmo_real_se_muestra_solo_cuando_hay_medicion():
    sin = valores(construir_lineas_panel(None, MetricasVista(), EstadoUI(), None, 0.0))
    con = valores(construir_lineas_panel(None, MetricasVista(), EstadoUI(), None, 0.0, ritmo=0.214))
    assert sin["Ritmo real"] == SIN_DATO
    assert con["Ritmo real"] == "21 %"


def test_recolectada_sigue_pendiente_hasta_que_el_motor_la_entregue():
    s = snapshot_minimo(entregadas=7)          # recolectada_total=None: Mike aún no lo confirma
    v = valores(construir_lineas_panel(s, MetricasVista(), EstadoUI(), 60.0, 0.0))
    assert v["Entregas"] == "7" and v["Recolectada"] == SIN_DATO


def test_la_fuente_de_comida_trae_su_radio():
    assert FuenteVista(1, 2, 3, 4).radio > 0
    assert FuenteVista(1, 2, 3, 4, radio=15.0).radio == 15.0
