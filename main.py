"""Punto de entrada de ANTHROSWARM: ventana de Pygame y Game Loop.

Ejecutar desde la carpeta del proyecto:
    python main.py
    python main.py --hormigas 3000 --workers 4
    python main.py --mundo 960x720        (tamaño de mundo pedido al motor; por defecto el suyo)

ARQUITECTURA (la simulación NO corre en este hilo):
    with adaptador.abrir():              # procesos del motor paralelo: se crean una vez y se cierran al salir
        with iniciar_simulador(...):     # hilo que ejecuta los pasos de dt fijo (ui/runner.py)
            Game Loop (este hilo)        # solo eventos, dibujo y lectura NO bloqueante del último resultado

Cada cuadro:
  1. leer eventos (efecto externo) -> acciones -> nuevo EstadoUI (funciones puras);
  2. si cambió algo, enviar una Orden inmutable al simulador;
  3. tomar el último Resultado (si es de la generación vigente) y convertirlo a RenderSnapshot;
  4. dibujar y limitar los FPS. Los FPS de dibujo y los pasos de simulación son independientes.

Si faltan engine/, logic/ o models/, la ventana abre igual (escenario y controles) con un aviso
visible y sin simular nada. Nunca se inventan datos.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import dataclass
from functools import reduce
from types import ModuleType
from typing import Any

import pygame

from ui import adapter
from ui.assets import cargar_fuentes, construir_fondo, crear_sprites_hormigas
from ui.controls import accion_para_clic, accion_para_tecla
from ui.interface import (
    ALTO_VENTANA,
    ANCHO_ESCENARIO,
    ANCHO_VENTANA,
    FPS_OBJETIVO,
    EstadoUI,
    aplicar_accion,
)
from ui.panel import construir_lineas_panel
from ui.renderer import (
    COLOR_AVISO,
    COLOR_PAUSA,
    construir_superficie_panel,
    dibujar_banner,
    dibujar_escenario,
)
from ui.runner import Orden, enviar_orden, es_vigente, iniciar_simulador, leer_resultado, ms_del_modo, sesion_motor
from ui.snapshot import MetricasVista, RenderSnapshot

TITULO_VENTANA = "ANTHROSWARM — Simulador de enjambre de hormigas"
N_HORMIGAS_POR_DEFECTO = 1000
REFRESCO_PANEL_S = 0.25      # el panel se recalcula 4 veces por segundo
RITMO_MINIMO_SIN_AVISO = 0.9


@dataclass(frozen=True)
class ResumenEjecucion:
    cuadros: int
    estado_ui: EstadoUI
    pasos_ejecutados: int
    tiempo_descartado: float
    estado_motor: Any
    modo_ultimo_paso: str | None
    error: str | None


def leer_eventos(eventos) -> tuple[bool, tuple]:
    """Traduce eventos de Pygame a (salir, acciones). Solo lee los eventos."""
    salir = any(e.type == pygame.QUIT for e in eventos)
    acciones = tuple(
        a for a in (
            accion_para_tecla(pygame.key.name(e.key)) if e.type == pygame.KEYDOWN
            else accion_para_clic(e.pos) if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1
            else None
            for e in eventos)
        if a is not None)
    return salir, acciones


def orden_de(estado_ui: EstadoUI) -> Orden:
    """EstadoUI -> Orden para el simulador (la generación es el contador de reinicios)."""
    return Orden(estado_ui.reinicios, estado_ui.modo, estado_ui.en_pausa, estado_ui.multiplicador)


def ejecutar(n_hormigas: int = N_HORMIGAS_POR_DEFECTO,
             adaptador: ModuleType = adapter,
             max_cuadros: int | None = None,
             n_workers: int | None = None,
             mundo: tuple[int, int] | None = None) -> ResumenEjecucion:
    """Game Loop. `adaptador` es inyectable (pruebas); `max_cuadros` solo se usa en pruebas."""
    pygame.init()
    pantalla = pygame.display.set_mode((ANCHO_VENTANA, ALTO_VENTANA))
    pygame.display.set_caption(TITULO_VENTANA)
    reloj = pygame.time.Clock()
    fondo = construir_fondo(ANCHO_ESCENARIO, ALTO_VENTANA)
    sprites = crear_sprites_hormigas()
    fuentes = cargar_fuentes()

    estado_ui = EstadoUI()
    ultima_orden: Orden | None = None
    ultimo = None                       # último Resultado vigente recibido
    snapshot: RenderSnapshot | None = None
    secuencia_dibujada = 0
    error: str | None = None
    cuadros, tiempo, ultimo_refresco = 0, 0.0, -REFRESCO_PANEL_S
    lineas, estado_ui_panel, clave_panel, superficie_panel = (), None, None, None

    try:
        with ExitStack() as pila:
            sim = conexion = None
            if adaptador.DISPONIBLE:
                # Cierre: primero el hilo del simulador y después los procesos. Si el hilo no termina,
                # el pool NO se cierra y se lanza SimuladorNoTerminoError (ver ui/runner.sesion_motor).
                conexion, sim = pila.enter_context(sesion_motor(
                    abrir=lambda: adaptador.abrir(n_workers),
                    iniciar=lambda c: iniciar_simulador(
                        crear_estado=lambda: adaptador.crear_estado_inicial(n_hormigas, mundo),
                        pasos=c.pasos,
                        dt_de_estado=adaptador.dt_paso,
                        orden_inicial=orden_de(estado_ui))))
                ultima_orden = orden_de(estado_ui)

            corriendo = True
            while corriendo:
                tiempo += reloj.tick(FPS_OBJETIVO) / 1000.0

                # 1-2. Eventos -> estado de interfaz -> orden al simulador
                salir, acciones = leer_eventos(pygame.event.get())
                corriendo = not salir
                estado_ui = reduce(aplicar_accion, acciones, estado_ui)
                if sim is not None and orden_de(estado_ui) != ultima_orden:
                    ultima_orden = orden_de(estado_ui)
                    enviar_orden(sim, ultima_orden)

                # 3. Último resultado (no bloquea) -> snapshot. Se descartan los obsoletos.
                if sim is not None:
                    nuevo = leer_resultado(sim)
                    if nuevo is not None:
                        if nuevo.error is not None:
                            error = nuevo.error
                        elif es_vigente(nuevo, estado_ui.reinicios):
                            ultimo = nuevo
                    if ultimo is not None and ultimo.secuencia != secuencia_dibujada:
                        snapshot = adaptador.a_snapshot(ultimo.estado, ultimo.estado_inicial)
                        secuencia_dibujada = ultimo.secuencia

                # 4. Panel (4 Hz o al cambiar los controles) y dibujo
                if tiempo - ultimo_refresco >= REFRESCO_PANEL_S or estado_ui != estado_ui_panel:
                    metricas = (adaptador.metricas(conexion, estado_ui.modo, ms_del_modo(ultimo, estado_ui.modo))
                                if conexion is not None else MetricasVista())
                    lineas = construir_lineas_panel(
                        snapshot, metricas, estado_ui, reloj.get_fps() or None,
                        0.0 if ultimo is None else ultimo.descartado_total,
                        None if ultimo is None else ultimo.ritmo)
                    ultimo_refresco, estado_ui_panel = tiempo, estado_ui
                if (lineas, estado_ui) != clave_panel:
                    superficie_panel = construir_superficie_panel(fuentes, lineas, estado_ui)
                    clave_panel = (lineas, estado_ui)

                dibujar_escenario(pantalla, fondo, snapshot, sprites)
                y_aviso = 16
                avisos = []
                if sim is None:
                    avisos.append("MOTOR NO DISPONIBLE — faltan engine/, logic/ o models/ (ver ui/adapter.py)")
                elif error is not None:
                    avisos.append(f"ERROR DEL SIMULADOR: {error[:70]}")
                elif ultimo is None:
                    avisos.append("Preparando simulación…")
                elif ultimo.ritmo is not None and ultimo.ritmo < RITMO_MINIMO_SIN_AVISO and not estado_ui.en_pausa:
                    avisos.append(f"Simulación al {ultimo.ritmo * 100:.0f} % del tiempo real (se descarta tiempo)")
                for texto in avisos:
                    dibujar_banner(pantalla, fuentes.normal, texto, COLOR_AVISO, y_aviso)
                    y_aviso += 40
                if estado_ui.en_pausa:
                    dibujar_banner(pantalla, fuentes.seccion, "PAUSA", COLOR_PAUSA, ALTO_VENTANA - 60)
                pantalla.blit(superficie_panel, (ANCHO_ESCENARIO, 0))
                pygame.display.flip()

                cuadros += 1
                if max_cuadros is not None and cuadros >= max_cuadros:
                    corriendo = False

    finally:
        pygame.quit()
    return ResumenEjecucion(
        cuadros, estado_ui,
        0 if ultimo is None else ultimo.pasos,
        0.0 if ultimo is None else ultimo.descartado_total,
        None if ultimo is None else ultimo.estado,
        None if ultimo is None else ultimo.modo,
        error)


def leer_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ANTHROSWARM — simulador de enjambre de hormigas")
    parser.add_argument("--hormigas", type=int, default=N_HORMIGAS_POR_DEFECTO,
                        help="cantidad de hormigas (1000, 3000 o 5000 en las pruebas)")
    parser.add_argument("--workers", type=int, default=None,
                        help="procesos del modo paralelo (por defecto, los núcleos disponibles)")
    parser.add_argument("--mundo", default=None, metavar="ANCHOxALTO",
                        help="tamaño del mundo pedido al motor, p. ej. 960x720 (por defecto, el del motor)")
    argumentos = parser.parse_args(argv)
    if argumentos.hormigas < 1:
        parser.error("--hormigas debe ser >= 1")
    if argumentos.workers is not None and argumentos.workers < 1:
        parser.error("--workers debe ser >= 1")
    if argumentos.mundo is not None:
        try:
            ancho, alto = (int(v) for v in argumentos.mundo.lower().split("x"))
            assert ancho > 0 and alto > 0
        except (ValueError, AssertionError):
            parser.error("--mundo debe tener la forma ANCHOxALTO, p. ej. 960x720")
        argumentos.mundo = (ancho, alto)
    return argumentos


def main(argv: list[str] | None = None) -> ResumenEjecucion:
    """Punto de entrada: lee la línea de comandos y ejecuta la aplicación."""
    a = leer_argumentos(argv)
    return ejecutar(a.hormigas, n_workers=a.workers, mundo=a.mundo)


if __name__ == "__main__":
    # Obligatorio en Windows: con "spawn" cada worker vuelve a importar este archivo y, sin esta
    # protección, abriría una ventana (y otro motor) por proceso.
    main()
