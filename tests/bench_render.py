"""BANCO DE PRUEBAS DE RENDERIZADO — independiente del motor real.

IMPORTANTE: esto mide SOLO cuánto tarda en DIBUJAR la interfaz. NO es un benchmark
de la simulación secuencial ni de la paralela, y sus números no deben presentarse
como tales. Los datos de entrada son SINTÉTICOS (posiciones y estados al azar con
semilla fija, cuadrícula de feromonas de tamaño arbitrario); no provienen de
ningún motor.

Uso (desde la raíz del proyecto):
    python tests/bench_render.py                  # abre una ventana real
    python tests/bench_render.py --sin-ventana    # sin ventana (SDL dummy)
    python tests/bench_render.py --cuadros 120 --hormigas 1000 3000 5000
"""
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

ANCHO_MUNDO_PRUEBA = 960.0   # arbitrario: solo para el banco
ALTO_MUNDO_PRUEBA = 720.0
CELDAS_FEROMONA_PRUEBA = (96, 72)  # columnas, filas: arbitrario, NO es el del motor


def crear_snapshot_sintetico(n_hormigas: int, semilla: int = 7):
    """DATOS DE PRUEBA, no de la simulación."""
    from ui.snapshot import (CapaFeromonaVista, EstadoHormigaVista, FuenteVista,
                             HormigaVista, HormigueroVista, RenderSnapshot)
    rng = random.Random(semilla)
    estados = tuple(EstadoHormigaVista)
    hormigas = tuple(HormigaVista(rng.uniform(0, ANCHO_MUNDO_PRUEBA), rng.uniform(0, ALTO_MUNDO_PRUEBA),
                                  rng.choice(estados)) for _ in range(n_hormigas))
    cols, filas = CELDAS_FEROMONA_PRUEBA
    capa = lambda: CapaFeromonaVista(cols, filas, tuple(rng.random() ** 3 for _ in range(cols * filas)))
    fuentes = tuple(FuenteVista(rng.uniform(80, 880), rng.uniform(80, 640), cant, 100)
                    for cant in (100, 80, 55, 30))
    return RenderSnapshot(ANCHO_MUNDO_PRUEBA, ALTO_MUNDO_PRUEBA, HormigueroVista(480, 360, 18),
                          fuentes, hormigas, capa(), capa(), entregadas=0, recolectada_total=0)


def medir(funcion, repeticiones: int) -> tuple[float, float]:
    """(media, p95) en milisegundos, descartando 5 repeticiones de calentamiento."""
    for _ in range(5):
        funcion()
    muestras = []
    for _ in range(repeticiones):
        t0 = time.perf_counter()
        funcion()
        muestras.append((time.perf_counter() - t0) * 1000.0)
    muestras.sort()
    return statistics.fmean(muestras), muestras[min(len(muestras) - 1, int(len(muestras) * 0.95))]


def ejecutar_banco(conteos: tuple[int, ...], cuadros: int, sin_ventana: bool) -> list[dict]:
    if sin_ventana:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame
    from ui.assets import cargar_fuentes, construir_fondo, crear_sprites_hormigas
    from ui.interface import ALTO_VENTANA, ANCHO_ESCENARIO, ANCHO_VENTANA, EstadoUI
    from ui.panel import construir_lineas_panel
    from ui.renderer import (RECT_ESCENARIO, construir_superficie_panel, dibujar_escenario,
                             dibujar_feromonas, dibujar_fuentes_comida, dibujar_hormigas,
                             dibujar_hormiguero)
    from ui.snapshot import MetricasVista

    pygame.init()
    pantalla = pygame.display.set_mode((ANCHO_VENTANA, ALTO_VENTANA))
    fondo, sprites, fuentes = construir_fondo(ANCHO_ESCENARIO, ALTO_VENTANA), crear_sprites_hormigas(), cargar_fuentes()
    estado_ui = EstadoUI()
    resultados = []
    for n in conteos:
        s = crear_snapshot_sintetico(n)
        lineas = construir_lineas_panel(s, MetricasVista(), estado_ui, 60.0, 0.0)

        def cuadro_completo():
            dibujar_escenario(pantalla, fondo, s, sprites)
            pantalla.blit(construir_superficie_panel(fuentes, lineas, estado_ui), (ANCHO_ESCENARIO, 0))
            pygame.display.flip()

        capas = {
            "fondo": lambda: pantalla.blit(fondo, (0, 0)),
            "feromonas": lambda: dibujar_feromonas(pantalla, s),
            "comida+hormiguero": lambda: (dibujar_fuentes_comida(pantalla, s.fuentes, s.ancho_mundo, s.alto_mundo),
                                          dibujar_hormiguero(pantalla, s.hormiguero, s.ancho_mundo, s.alto_mundo)),
            "hormigas": lambda: dibujar_hormigas(pantalla, s.hormigas, sprites, s.ancho_mundo, s.alto_mundo),
            "panel (reconstruir)": lambda: construir_superficie_panel(fuentes, lineas, estado_ui),
        }
        fila = {"hormigas": n, "capas": {nombre: medir(f, cuadros) for nombre, f in capas.items()},
                "cuadro": medir(cuadro_completo, cuadros)}
        resultados.append(fila)
    pygame.quit()
    return resultados


def imprimir(resultados: list[dict], cuadros: int, sin_ventana: bool) -> None:
    print("=" * 74)
    print("BANCO DE PRUEBAS DE RENDER — datos SINTÉTICOS, sin motor.")
    print("NO es un benchmark de la simulación secuencial ni de la paralela.")
    print(f"Python {sys.version.split()[0]} | {cuadros} repeticiones por medida | "
          f"{'sin ventana (SDL dummy)' if sin_ventana else 'ventana real'}")
    print("=" * 74)
    for fila in resultados:
        media, p95 = fila["cuadro"]
        print(f"\n{fila['hormigas']:>5} hormigas — cuadro completo: media {media:6.2f} ms | "
              f"p95 {p95:6.2f} ms | ≈ {1000.0 / media:6.1f} FPS de solo dibujo")
        for nombre, (m, p) in fila["capas"].items():
            print(f"   {nombre:<22} media {m:6.2f} ms   p95 {p:6.2f} ms")
    print("\nLectura: presupuesto de un cuadro a 60 FPS = 16.67 ms. Esto es solo el dibujo;"
          " el tiempo de update() del motor se suma aparte.")


def principal() -> None:
    p = argparse.ArgumentParser(description="Banco de pruebas de renderizado (datos sintéticos)")
    p.add_argument("--hormigas", type=int, nargs="+", default=[1000, 3000, 5000])
    p.add_argument("--cuadros", type=int, default=120)
    p.add_argument("--sin-ventana", action="store_true")
    a = p.parse_args()
    imprimir(ejecutar_banco(tuple(a.hormigas), a.cuadros, a.sin_ventana), a.cuadros, a.sin_ventana)


if __name__ == "__main__":
    principal()
