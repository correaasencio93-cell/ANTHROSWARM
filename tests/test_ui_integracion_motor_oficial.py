"""INTEGRACIÓN CON EL MOTOR OFICIAL (repositorio, commit 12e22a1: models/ y logic/ de Mike, engine/ de Jean).

Estas pruebas usan engine/, logic/ y models/ TAL COMO ESTÁN EN EL REPOSITORIO; no hay datos de prueba
inventados para el motor. Si esas carpetas no están en el proyecto, se omiten (no fallan). Si un
contrato oficial cambia, lo que falle señala exactamente qué actualizar en ui/adapter.py.
"""
import math
import multiprocessing
import os
import threading
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("models")
pytest.importorskip("logic")
pytest.importorskip("engine")

from dataclasses import replace  # noqa: E402

import main as juego  # noqa: E402
from models import AntState, Pheromone  # noqa: E402
from ui import adapter  # noqa: E402
from ui.controls import BOTONES  # noqa: E402
from ui.snapshot import EstadoHormigaVista as E  # noqa: E402
from ui.timestep import DT_PASO  # noqa: E402


def estado(n=300, mundo=None):
    return adapter.crear_estado_inicial(n, mundo)


# ------------------------------------------------------------ contratos leídos
def test_el_dt_lo_da_el_motor_y_coincide_con_el_dt_aprobado():
    assert adapter.dt_paso(estado(10)) == pytest.approx(DT_PASO) == pytest.approx(1 / 60)


def test_snapshot_del_estado_inicial():
    e = estado(300)
    s = adapter.a_snapshot(e)
    assert (s.ancho_mundo, s.alto_mundo) == (float(e.config.width), float(e.config.height))
    assert len(s.hormigas) == 300 and all(h.estado is E.EXPLORANDO for h in s.hormigas)
    assert len(s.fuentes) == len(e.foods) and all(f.cantidad == f.cantidad_inicial for f in s.fuentes)
    assert all(f.radio == e.foods[i].radius for i, f in enumerate(s.fuentes))
    assert (s.hormiguero.x, s.hormiguero.y, s.hormiguero.radio) == (e.nest.x, e.nest.y, e.nest.radius)
    assert s.entregadas == 0


def test_una_fuente_que_el_motor_elimina_sigue_en_el_snapshot_con_cantidad_cero():
    e0 = estado(20)
    assert len(e0.foods) >= 2
    sin_la_primera = replace(e0, foods=e0.foods[1:])               # como si se hubiera agotado
    s = adapter.a_snapshot(sin_la_primera, e0)
    assert len(s.fuentes) == len(e0.foods)
    assert (s.fuentes[0].x, s.fuentes[0].y, s.fuentes[0].cantidad) == (e0.foods[0].x, e0.foods[0].y, 0)
    assert s.fuentes[0].cantidad_inicial == e0.foods[0].amount


def test_las_dos_capas_de_feromona_siguen_previstas_pero_solo_hay_datos_de_regreso():
    s = adapter.a_snapshot(estado(50))
    assert s.feromona_exploracion is None                      # el motor oficial tiene un solo tipo de feromona
    assert s.feromona_regreso is not None and set(s.feromona_regreso.intensidades) == {0.0}


def test_recolectada_es_none_sin_estado_inicial_de_referencia_y_cero_al_empezar():
    e = estado(50)
    assert adapter.a_snapshot(e).recolectada_total is None      # sin referencia no se puede saber
    assert adapter.a_snapshot(e, e).recolectada_total == 0


def test_recolectada_coincide_con_entregadas_mas_hormigas_en_camino_con_el_motor_real():
    """Verifica contra logic/results.py la lectura 'inicial - restante' (cada reclamo aceptado resta 1)."""
    e0 = adapter.crear_estado_inicial(1000)
    paso, e = _paso_secuencial(), e0
    verificados = 0
    for i in range(260):
        e = paso(e)
        if i % 20 == 19:
            en_camino = sum(1 for a in e.ants if a.has_food)
            s = adapter.a_snapshot(e, e0)
            assert s.recolectada_total == s.entregadas + en_camino
            verificados += s.recolectada_total
    assert verificados > 0                                      # hubo recolección: la prueba no es vacía


def test_hay_cuatro_fuentes_y_el_estado_inicial_es_el_oficial():
    e = estado(10)
    assert len(e.foods) == 4 and all(f.amount == 50 for f in e.foods)
    assert (e.config.width, e.config.height) == (800, 600) and e.tick == 0


def test_la_cuadricula_de_feromonas_suma_y_recorta():
    e = estado(5)
    puntos = (Pheromone(5, 5, 0.4), Pheromone(6, 6, 0.4), Pheromone(7, 7, 0.9),   # misma celda: 1.7 -> recorta a 1.0
              Pheromone(25, 5, 0.25))
    s = adapter.a_snapshot(replace(e, pheromones=puntos))
    capa, columnas = s.feromona_regreso, s.feromona_regreso.columnas
    assert capa.intensidades[0] == pytest.approx(1.0)
    assert capa.intensidades[2] == pytest.approx(0.25)         # x=25 -> columna 2 con celdas de 10
    assert sum(1 for v in capa.intensidades if v > 0) == 2
    celda = adapter.CELDA_FEROMONA                             # el tamaño del mundo lo da SimConfig del motor
    assert columnas == math.ceil(e.config.width / celda) and capa.filas == math.ceil(e.config.height / celda)


def test_los_tres_estados_del_motor_se_traducen_y_uno_desconocido_falla_claro():
    e = estado(3)
    ants = tuple(replace(a, state=st) for a, st in zip(e.ants, (AntState.EXPLORING, AntState.COLLECTING, AntState.RETURNING)))
    s = adapter.a_snapshot(replace(e, ants=ants))
    assert [h.estado for h in s.hormigas] == [E.EXPLORANDO, E.RECOLECTANDO, E.REGRESANDO]
    with pytest.raises(ValueError, match="Estado de hormiga desconocido"):
        adapter.a_snapshot(replace(e, ants=(replace(e.ants[0], state="TELETRANSPORTANDO"),)))


# ------------------------------------------------- compatibilidad de coordenadas
@pytest.mark.parametrize("mundo", [None, (960, 720)])
def test_las_coordenadas_del_motor_caen_dentro_del_mundo_que_se_dibuja(mundo):
    """Compatibilidad 960x720 / 1280x720: con ambos tamaños todo queda dentro de [0,ancho]x[0,alto]."""
    e = estado(200, mundo)
    paso = _paso_secuencial()
    for _ in range(120):
        e = paso(e)
        w, h = e.config.width, e.config.height
        assert all(0 <= a.x <= w and 0 <= a.y <= h for a in e.ants)
        assert all(0 <= f.x <= w and 0 <= f.y <= h for f in e.foods)
        assert 0 <= e.nest.x <= w and 0 <= e.nest.y <= h
    if mundo:
        assert (e.config.width, e.config.height) == mundo


def _paso_secuencial():
    from functools import partial
    from engine import procesar_secuencial
    from logic import update
    return partial(update, ejecutor=procesar_secuencial)


# ------------------------------------------------------------- motor abierto
def test_abrir_entrega_los_dos_modos_y_ambos_producen_el_mismo_estado():
    with adapter.abrir(n_workers=2) as c:
        assert set(c.pasos) == {"secuencial", "paralelo"}
        assert (c.workers["secuencial"], c.workers["paralelo"]) == (1, 2) and c.nucleos >= 1
        e0 = estado(150)
        seq, par = e0, e0
        for _ in range(3):
            seq, par = c.pasos["secuencial"](seq), c.pasos["paralelo"](par)
        assert seq == par and type(seq) is type(par)           # mismo GameState: se puede cambiar de modo
        assert seq.tick == 3 and e0.tick == 0                  # el original no se modificó


def test_el_pool_se_cierra_al_salir_del_with():
    with adapter.abrir(n_workers=2) as c:
        procesos = list(c.pasos["paralelo"].keywords["ejecutor"].keywords["pool"]._pool)
        assert all(p.is_alive() for p in procesos)
    assert all(not p.is_alive() for p in procesos)


def test_metricas_de_la_interfaz():
    with adapter.abrir(n_workers=2) as c:
        m = adapter.metricas(c, "paralelo", 12.5)
    assert (m.workers, m.ms_por_paso) == (2, 12.5) and m.nucleos >= 1
    assert adapter.metricas(c, "secuencial", None).workers == 1


# ------------------------------------------------- Game Loop con el motor oficial
def _clic(boton_id):
    x, y, w, h = next(b for b in BOTONES if b.id == boton_id).rect
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(x + w // 2, y + h // 2), button=1))


def test_game_loop_completo_en_secuencial_con_el_motor_oficial():
    r = juego.ejecutar(n_hormigas=200, max_cuadros=90, n_workers=2)
    assert r.error is None and r.pasos_ejecutados > 0
    assert r.modo_ultimo_paso == "secuencial" and r.estado_motor.tick == r.pasos_ejecutados


def test_game_loop_cambia_a_paralelo_con_el_boton_y_continua_el_mismo_estado():
    pygame.init()
    pygame.display.set_mode((1280, 720))
    _clic("modo_paralelo")
    r = juego.ejecutar(n_hormigas=200, max_cuadros=150, n_workers=2)
    assert r.error is None and r.modo_ultimo_paso == "paralelo"
    assert r.estado_motor.tick == r.pasos_ejecutados           # un solo estado continuo, sin reinicios


# ---------------------------------------------------- equivalencia con el motor oficial
@pytest.mark.parametrize("n", [1000, 3000, 5000])
def test_secuencial_y_paralelo_dan_estados_iguales_con_1000_3000_y_5000_hormigas(n):
    with adapter.abrir(n_workers=2) as c:
        seq = par = adapter.crear_estado_inicial(n)
        for _ in range(20):
            seq, par = c.pasos["secuencial"](seq), c.pasos["paralelo"](par)
            assert seq == par
        assert seq.tick == 20 and len(seq.ants) == n


# ------------------------------------------ Game Loop real: hilos, tamaños, modos y cierre
class Registro:
    """Envuelve logic.update para anotar QUIÉN y CUÁNDO la llama (el motor real se sigue ejecutando)."""
    def __init__(self, monkeypatch, al_llamar=None):
        import logic
        self.llamadas, self._original, self._al_llamar = [], logic.update, al_llamar
        monkeypatch.setattr(logic, "update", self)

    def __call__(self, state, ejecutor=None):
        self.llamadas.append((time.perf_counter(), threading.current_thread().name))
        if self._al_llamar:
            self._al_llamar(len(self.llamadas))
        return self._original(state, ejecutor=ejecutor)


def _post(tipo, **datos):
    pygame.event.post(pygame.event.Event(tipo, **datos))


def test_solo_el_hilo_del_simulador_llama_a_update_y_nunca_el_hilo_principal(monkeypatch):
    registro = Registro(monkeypatch)
    pygame.init()
    pygame.display.set_mode((1280, 720))
    _clic("modo_paralelo")                                      # también en modo paralelo
    r = juego.ejecutar(n_hormigas=150, max_cuadros=70, n_workers=2)
    assert r.error is None and len(registro.llamadas) >= 3
    assert {nombre for _, nombre in registro.llamadas} == {"simulador"}
    assert threading.current_thread().name != "simulador"


@pytest.mark.parametrize("modo", ["secuencial", "paralelo"])
@pytest.mark.parametrize("n", [1000, 3000, 5000])
def test_game_loop_real_con_1000_3000_y_5000_hormigas_en_ambos_modos(n, modo):
    pygame.init()
    pygame.display.set_mode((1280, 720))
    if modo == "paralelo":
        _clic("modo_paralelo")
    r = juego.ejecutar(n_hormigas=n, max_cuadros=90, n_workers=2)
    assert r.error is None and r.modo_ultimo_paso == modo
    assert r.pasos_ejecutados > 0 and r.estado_motor.tick == r.pasos_ejecutados
    assert len(r.estado_motor.ants) == n
    assert multiprocessing.active_children() == []              # los workers se cerraron al salir


def test_las_estadisticas_del_panel_salen_del_gamestate_real():
    from ui.interface import EstadoUI
    from ui.panel import SIN_DATO, construir_lineas_panel
    from ui.snapshot import MetricasVista
    e0 = adapter.crear_estado_inicial(300)
    e = e0
    paso = _paso_secuencial()
    for _ in range(30):
        e = paso(e)
    lineas = construir_lineas_panel(adapter.a_snapshot(e, e0), MetricasVista(workers=1, nucleos=2, ms_por_paso=3.0),
                                    EstadoUI(), 60.0, 0.0, 1.0)
    v = {l.etiqueta: l.valor for l in lineas if l.tipo == "fila"}
    assert v["Hormigas"] == "300" and v["Explorando"] == "300" and v["Entregas"] == "0"
    assert v["Disponible"] == "200" and v["Recolectada"] == "0"      # 4 fuentes x 50, aún sin recolectar
    assert SIN_DATO not in (v["Hormigas"], v["Disponible"], v["Recolectada"])


def test_pausa_reanudacion_reinicio_y_cierre_con_el_motor_real(monkeypatch):
    """Secuencia con el motor real: se pausa, se reanuda, se reinicia y se cierra con QUIT."""
    marcas = {}

    def al_llamar(n):
        if n == 15 and "pausa" not in marcas:
            marcas["pausa"] = time.perf_counter()
            _post(pygame.KEYDOWN, key=pygame.K_SPACE)                          # pausa
            threading.Timer(1.0, lambda: (marcas.setdefault("reanuda", time.perf_counter()),
                                          _post(pygame.KEYDOWN, key=pygame.K_SPACE))).start()
            threading.Timer(2.0, lambda: (marcas.setdefault("reinicio", time.perf_counter()),
                                          _post(pygame.KEYDOWN, key=pygame.K_r))).start()
            threading.Timer(3.2, lambda: _post(pygame.QUIT)).start()           # cierre de la aplicación

    registro = Registro(monkeypatch, al_llamar)
    pygame.init()
    pygame.display.set_mode((1280, 720))
    r = juego.ejecutar(n_hormigas=200, max_cuadros=1000, n_workers=2)          # QUIT corta mucho antes
    t = [x for x, _ in registro.llamadas]
    assert r.cuadros < 1000 and r.error is None                                # el QUIT cerró la aplicación
    assert not [x for x in t if marcas["pausa"] + 0.3 < x < marcas["reanuda"]]  # en pausa no se llama a update
    assert [x for x in t if marcas["reanuda"] + 0.2 < x < marcas["reinicio"]]   # al reanudar vuelve a avanzar
    assert r.estado_ui.reinicios == 1 and r.estado_ui.en_pausa is False
    assert r.estado_motor.tick < len(registro.llamadas)                        # el reinicio creó un estado nuevo
    assert multiprocessing.active_children() == []


def test_cambiar_de_modo_con_el_motor_real_conserva_el_estado_y_las_estadisticas_siguen_actualizando(monkeypatch):
    def al_llamar(n):
        if n == 10:
            _post(pygame.MOUSEBUTTONDOWN, pos=_centro_boton("modo_paralelo"), button=1)
        if n == 40:
            _post(pygame.QUIT)

    registro = Registro(monkeypatch, al_llamar)
    pygame.init()
    pygame.display.set_mode((1280, 720))
    r = juego.ejecutar(n_hormigas=200, max_cuadros=1500, n_workers=2)
    assert r.error is None and r.modo_ultimo_paso == "paralelo" and r.estado_ui.reinicios == 0
    assert r.estado_motor.tick == r.pasos_ejecutados >= 30             # un solo estado continuo, sin reinicios


def _centro_boton(boton_id):
    x, y, w, h = next(b for b in BOTONES if b.id == boton_id).rect
    return x + w // 2, y + h // 2
