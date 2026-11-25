"""Pruebas de humo de la capa Pygame, SIN ventana (controlador SDL "dummy").

Los datos de aquí son sintéticos y solo sirven para comprobar que el dibujo y el
Game Loop funcionan; no representan al motor real.
"""
import os
from types import SimpleNamespace

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402
import pytest  # noqa: E402

import main as juego  # noqa: E402
from tests.bench_render import crear_snapshot_sintetico  # noqa: E402
from ui import adapter  # noqa: E402
from ui.assets import (construir_fondo, crear_sprites_hormigas, generar_decoraciones,  # noqa: E402
                       cargar_fuentes)
from ui.interface import ALTO_VENTANA, ANCHO_ESCENARIO, EstadoUI  # noqa: E402
from ui.panel import construir_lineas_panel  # noqa: E402
from ui.renderer import (construir_superficie_panel, dibujar_escenario, mundo_a_pantalla,  # noqa: E402
                         rect_mundo, superficie_feromona)
from ui.snapshot import CapaFeromonaVista, MetricasVista  # noqa: E402


@pytest.fixture(scope="module")
def pantalla():
    pygame.init()
    sup = pygame.display.set_mode((1280, 720))
    yield sup
    pygame.quit()


def test_mundo_a_pantalla_es_pura_y_escala_por_eje():
    assert mundo_a_pantalla(0, 0, 100, 100) == (0, 0)
    assert mundo_a_pantalla(50, 50, 100, 100) == (ANCHO_ESCENARIO // 2, ALTO_VENTANA // 2)
    assert mundo_a_pantalla(10, 10, 100, 100, (100, 200, 300, 400)) == (130, 240)


def test_rect_mundo_conserva_la_proporcion_y_se_centra():
    assert rect_mundo(960, 720) == (0, 0, 960, 720)                 # misma proporción: ocupa todo
    x, y, w, h = rect_mundo(1280, 720)                              # mundo más ancho: franjas arriba/abajo
    assert (x, w) == (0, 960) and h == 540 and y == 90
    x, y, w, h = rect_mundo(400, 800)                               # mundo más alto: franjas a los lados
    assert (y, h) == (0, 720) and w == 360 and x == 300
    assert abs(rect_mundo(1280, 720)[2] / rect_mundo(1280, 720)[3] - 1280 / 720) < 0.01


def test_las_decoraciones_son_deterministas_y_quedan_dentro():
    a = generar_decoraciones(960, 720, semilla=1)
    assert a == generar_decoraciones(960, 720, semilla=1)
    assert a != generar_decoraciones(960, 720, semilla=2)
    assert all(0 <= d.x <= 960 and 0 <= d.y <= 720 for d in a)


def test_el_fondo_se_construye_con_el_tamano_del_escenario(pantalla):
    assert construir_fondo(ANCHO_ESCENARIO, ALTO_VENTANA).get_size() == (ANCHO_ESCENARIO, ALTO_VENTANA)


def test_la_capa_de_feromonas_es_translucida_y_escalada(pantalla):
    capa = CapaFeromonaVista(2, 1, (0.0, 1.0))
    sup = superficie_feromona(capa, (255, 0, 0), (100, 50))
    assert sup.get_size() == (100, 50)
    assert sup.get_at((2, 25)).a < sup.get_at((97, 25)).a   # celda vacía vs celda intensa
    assert sup.get_at((97, 25)).a > 100


def test_dibujar_la_escena_cambia_los_pixeles(pantalla):
    fondo, sprites = construir_fondo(ANCHO_ESCENARIO, ALTO_VENTANA), crear_sprites_hormigas()
    dibujar_escenario(pantalla, fondo, None, sprites)
    solo_fondo = pygame.image.tobytes(pantalla, "RGB")
    dibujar_escenario(pantalla, fondo, crear_snapshot_sintetico(500), sprites)
    assert pygame.image.tobytes(pantalla, "RGB") != solo_fondo


def test_el_panel_se_construye_con_el_tamano_correcto(pantalla):
    lineas = construir_lineas_panel(None, MetricasVista(), EstadoUI(), None, 0.0)
    assert construir_superficie_panel(cargar_fuentes(), lineas, EstadoUI()).get_size() == (320, 720)


# ------------------------------------------------------------------ Game Loop
# Estos tests usan DOBLES DE PRUEBA del adaptador (SimpleNamespace): solo comprueban el cableado
# del Game Loop con el simulador asíncrono. No son el motor ni datos de la simulación.
from contextlib import contextmanager  # noqa: E402

from tests.bench_render import crear_snapshot_sintetico as _snap  # noqa: E402,F811
from ui.adapter import Conexion  # noqa: E402
from ui.controls import BOTONES  # noqa: E402


def _centro(boton_id):
    x, y, w, h = next(b for b in BOTONES if b.id == boton_id).rect
    return x + w // 2, y + h // 2


def _clic(boton_id):
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=_centro(boton_id), button=1))


def _adaptador_de_prueba(llamadas, disponible=True):
    snap = _snap(50)

    @contextmanager
    def abrir(n_workers=None):
        llamadas.append(("abrir", n_workers))
        try:
            yield Conexion(
                pasos={"secuencial": lambda e: e + 1, "paralelo": lambda e: e + 10},
                workers={"secuencial": 1, "paralelo": 2}, nucleos=4)
        finally:
            llamadas.append(("cerrar",))

    return SimpleNamespace(
        DISPONIBLE=disponible,
        abrir=abrir,
        crear_estado_inicial=lambda n, mundo=None: llamadas.append(("inicial", n, mundo)) or 0,
        dt_paso=lambda estado: 1.0 / 60.0,
        a_snapshot=lambda estado, referencia=None: snap,
        metricas=lambda conexion, modo, ms: MetricasVista(workers=conexion.workers[modo],
                                                          nucleos=conexion.nucleos, ms_por_paso=ms),
    )


def test_sin_motor_el_loop_corre_y_no_simula_nada():
    r = juego.ejecutar(adaptador=_adaptador_de_prueba([], disponible=False), max_cuadros=5)
    assert r.cuadros == 5 and r.pasos_ejecutados == 0 and r.estado_motor is None and r.error is None


def test_el_adaptador_real_declara_si_el_motor_esta_en_la_carpeta():
    import importlib.util
    esperado = all(importlib.util.find_spec(m) is not None for m in ("engine", "logic", "models"))
    assert adapter.DISPONIBLE is esperado


def test_con_motor_de_prueba_la_simulacion_avanza_y_se_cierra_en_orden():
    llamadas = []
    r = juego.ejecutar(n_hormigas=77, adaptador=_adaptador_de_prueba(llamadas), max_cuadros=40, n_workers=3)
    assert llamadas[0] == ("abrir", 3) and llamadas[-1] == ("cerrar",)
    assert ("inicial", 77, None) in llamadas
    assert r.pasos_ejecutados > 0 and r.estado_motor == r.pasos_ejecutados   # +1 por cada paso secuencial


def test_el_mundo_pedido_llega_al_motor_sin_tocarlo():
    llamadas = []
    juego.ejecutar(n_hormigas=5, adaptador=_adaptador_de_prueba(llamadas), max_cuadros=10, mundo=(960, 720))
    assert ("inicial", 5, (960, 720)) in llamadas


def test_pausa_por_teclado_detiene_los_pasos():
    pygame.init()
    pygame.display.set_mode((1280, 720))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    r = juego.ejecutar(adaptador=_adaptador_de_prueba([]), max_cuadros=30)
    assert r.estado_ui.en_pausa is True
    assert r.pasos_ejecutados == 0


def test_cambiar_de_modo_con_el_boton_continua_con_la_otra_funcion_de_paso():
    pygame.init()
    pygame.display.set_mode((1280, 720))
    _clic("modo_paralelo")
    r = juego.ejecutar(adaptador=_adaptador_de_prueba([]), max_cuadros=60)
    assert r.estado_ui.modo == "paralelo" and r.modo_ultimo_paso == "paralelo"
    # Cada paso paralelo suma 10 y cada secuencial 1, sobre el MISMO estado (sin reiniciar):
    # si hubo al menos un paso paralelo, el estado supera al número de pasos.
    assert r.pasos_ejecutados > 0 and r.estado_motor > r.pasos_ejecutados


def test_reiniciar_crea_un_estado_nuevo_en_una_generacion_nueva():
    llamadas = []
    pygame.init()
    pygame.display.set_mode((1280, 720))
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
    r = juego.ejecutar(n_hormigas=10, adaptador=_adaptador_de_prueba(llamadas), max_cuadros=30)
    assert r.estado_ui.reinicios == 1
    assert llamadas.count(("inicial", 10, None)) == 2


def test_un_error_del_simulador_se_muestra_y_no_cuelga_la_ventana():
    llamadas = []
    adaptador = _adaptador_de_prueba(llamadas)

    @contextmanager
    def abrir_roto(n_workers=None):
        def paso(e):
            raise RuntimeError("fallo de prueba")
        yield Conexion(pasos={"secuencial": paso, "paralelo": paso}, workers={"secuencial": 1, "paralelo": 1}, nucleos=1)

    adaptador.abrir = abrir_roto
    r = juego.ejecutar(adaptador=adaptador, max_cuadros=40)
    assert r.error == "RuntimeError: fallo de prueba" and r.cuadros == 40
