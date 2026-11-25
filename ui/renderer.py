"""Renderizado: recibe un RenderSnapshot y dibuja. No modifica ni calcula lógica.

Las funciones dibujar_* son efectos externos sobre una Surface de Pygame; la
conversión de coordenadas (mundo -> pantalla) es una función pura.
"""
from __future__ import annotations

import math

import pygame

from ui.assets import Fuentes
from ui.controls import (
    BOTONES,
    Y_ETIQUETA_MODO,
    Y_ETIQUETA_VELOCIDAD,
    Y_TITULO_CONTROLES,
    boton_activo,
    etiqueta_boton,
)
from ui.interface import (
    ALTO_VENTANA,
    ANCHO_ESCENARIO,
    ANCHO_PANEL,
    MARGEN,
    EstadoUI,
    texto_estado,
)
from ui.panel import ALTO_TITULO, LineaPanel, posiciones_panel
from ui.snapshot import CapaFeromonaVista, FuenteVista, HormigueroVista, RenderSnapshot

Rect = tuple[int, int, int, int]
RECT_ESCENARIO: Rect = (0, 0, ANCHO_ESCENARIO, ALTO_VENTANA)

COLOR_PANEL = (28, 32, 30)
COLOR_BORDE = (70, 78, 72)
COLOR_TEXTO = (232, 236, 230)
COLOR_TEXTO_SUAVE = (160, 170, 162)
COLOR_ACENTO = (140, 210, 110)
COLOR_BOTON = (52, 60, 56)
COLOR_BOTON_ACTIVO = (74, 140, 70)
COLOR_PAUSA = (230, 170, 50)
COLOR_AVISO = (200, 60, 40)
COLOR_FER_EXPLORACION = (60, 120, 255)
COLOR_FER_REGRESO = (230, 60, 200)
ALFA_MAX_FEROMONA = 170


# ----------------------------------------------------------------- funciones puras
def mundo_a_pantalla(x: float, y: float, ancho_mundo: float, alto_mundo: float,
                     rect: Rect = RECT_ESCENARIO) -> tuple[int, int]:
    """Convierte coordenadas del mundo a píxeles del escenario (escala por eje)."""
    rx, ry, rw, rh = rect
    return rx + int(x / ancho_mundo * rw), ry + int(y / alto_mundo * rh)


def rect_mundo(ancho_mundo: float, alto_mundo: float, rect: Rect = RECT_ESCENARIO) -> Rect:
    """Zona del escenario que ocupa el mundo, conservando su proporción (escala uniforme).

    Si el mundo no tiene la misma proporción que el escenario (p. ej. 1280x720 en 960x720)
    queda centrado con franjas libres, en vez de deformar las distancias.
    """
    rx, ry, rw, rh = rect
    escala = min(rw / ancho_mundo, rh / alto_mundo)
    w, h = int(ancho_mundo * escala), int(alto_mundo * escala)
    return rx + (rw - w) // 2, ry + (rh - h) // 2, w, h


# ------------------------------------------------------------------ escenario
def superficie_feromona(capa: CapaFeromonaVista, color: tuple[int, int, int],
                        tam: tuple[int, int], alfa_max: int = ALFA_MAX_FEROMONA) -> pygame.Surface:
    """Convierte la cuadrícula en una imagen translúcida escalada al tamaño del escenario.

    El .convert_alpha() final es clave para el rendimiento: una superficie creada desde
    bytes "RGBA" no tiene el formato de píxel de la pantalla y mezclarla con transparencia
    es muy lento (medido: ~8 ms por capa); ya convertida, el mismo blit tarda ~0,2 ms.
    Requiere que la ventana (pygame.display) ya esté creada.
    """
    r, g, b = color
    tabla = tuple(bytes((r, g, b, a)) for a in range(alfa_max + 1))   # un píxel RGBA por nivel
    datos = b"".join(tabla[int(min(1.0, max(0.0, v)) * alfa_max)] for v in capa.intensidades)
    pequena = pygame.image.frombuffer(datos, (capa.columnas, capa.filas), "RGBA")
    return pygame.transform.smoothscale(pequena, tam).convert_alpha()


def dibujar_feromonas(sup: pygame.Surface, snapshot: RenderSnapshot, rect: Rect = RECT_ESCENARIO) -> None:
    rx, ry, rw, rh = rect
    for capa, color in ((snapshot.feromona_exploracion, COLOR_FER_EXPLORACION),
                        (snapshot.feromona_regreso, COLOR_FER_REGRESO)):
        if capa is not None:
            sup.blit(superficie_feromona(capa, color, (rw, rh)), (rx, ry))


def dibujar_fuentes_comida(sup: pygame.Surface, fuentes: tuple[FuenteVista, ...],
                           ancho_mundo: float, alto_mundo: float, rect: Rect = RECT_ESCENARIO) -> None:
    """Zona de recolección con su radio real (anillo) y un disco cuyo tamaño refleja lo que queda."""
    escala = rect[2] / ancho_mundo
    for f in fuentes:
        centro = mundo_a_pantalla(f.x, f.y, ancho_mundo, alto_mundo, rect)
        radio_zona = max(6, int(f.radio * escala))
        pygame.draw.circle(sup, (150, 220, 120), centro, radio_zona, 1)
        if f.cantidad <= 0 or f.cantidad_inicial <= 0:
            pygame.draw.circle(sup, (150, 150, 140), centro, max(3, radio_zona // 2), 2)   # agotada
            continue
        fraccion = min(1.0, f.cantidad / f.cantidad_inicial)
        radio = max(3, int(radio_zona * (0.45 + 0.55 * math.sqrt(fraccion))))
        pygame.draw.circle(sup, (36, 90, 40), centro, radio + 2)
        pygame.draw.circle(sup, (88, 196, 72), centro, radio)
        pygame.draw.circle(sup, (170, 235, 140), (centro[0] - radio // 3, centro[1] - radio // 3), max(2, radio // 3))


def dibujar_hormiguero(sup: pygame.Surface, h: HormigueroVista,
                       ancho_mundo: float, alto_mundo: float, rect: Rect = RECT_ESCENARIO) -> None:
    centro = mundo_a_pantalla(h.x, h.y, ancho_mundo, alto_mundo, rect)
    radio = max(12, int(h.radio / ancho_mundo * rect[2]))
    pygame.draw.circle(sup, (60, 38, 20), centro, radio + 8)
    pygame.draw.circle(sup, (96, 64, 34), centro, radio + 3)
    pygame.draw.circle(sup, (36, 22, 12), centro, max(4, radio // 2))
    pygame.draw.circle(sup, (150, 108, 66), centro, radio + 8, 2)


def dibujar_hormigas(sup: pygame.Surface, hormigas, sprites, ancho_mundo: float,
                     alto_mundo: float, rect: Rect = RECT_ESCENARIO) -> None:
    """Dibuja todas las hormigas con una sola llamada a blits (mucho más rápido que una a una)."""
    rx, ry, rw, rh = rect
    sx, sy = rw / ancho_mundo, rh / alto_mundo
    mitad = sprites[next(iter(sprites))].get_width() // 2
    sup.blits([(sprites[h.estado], (rx + int(h.x * sx) - mitad, ry + int(h.y * sy) - mitad))
               for h in hormigas], doreturn=False)


def dibujar_banner(sup: pygame.Surface, fuente: pygame.font.Font, texto: str,
                   color_fondo: tuple[int, int, int], y: int, rect: Rect = RECT_ESCENARIO) -> None:
    """Cartel centrado en el escenario (avisos: retraso, motor no conectado, datos de prueba)."""
    imagen = fuente.render(texto, True, (255, 255, 255))
    caja = pygame.Rect(0, 0, imagen.get_width() + 28, imagen.get_height() + 14)
    caja.midtop = (rect[0] + rect[2] // 2, y)
    pygame.draw.rect(sup, color_fondo, caja, border_radius=8)
    sup.blit(imagen, (caja.x + 14, caja.y + 7))


def dibujar_escenario(sup: pygame.Surface, fondo: pygame.Surface, snapshot: RenderSnapshot | None,
                      sprites, rect: Rect = RECT_ESCENARIO) -> None:
    """Orden de capas: fondo, límites del mundo, feromonas, comida, hormiguero, hormigas.

    Todo lo del mundo se dibuja dentro de rect_mundo(...), con escala uniforme, así que
    funciona con cualquier tamaño de mundo que entregue el motor.
    """
    sup.blit(fondo, (rect[0], rect[1]))
    if snapshot is None:
        return
    rm = rect_mundo(snapshot.ancho_mundo, snapshot.alto_mundo, rect)
    if rm != rect:
        pygame.draw.rect(sup, (235, 235, 215), rm, 2)      # límites del mundo (las hormigas rebotan aquí)
    dibujar_feromonas(sup, snapshot, rm)
    dibujar_fuentes_comida(sup, snapshot.fuentes, snapshot.ancho_mundo, snapshot.alto_mundo, rm)
    dibujar_hormiguero(sup, snapshot.hormiguero, snapshot.ancho_mundo, snapshot.alto_mundo, rm)
    dibujar_hormigas(sup, snapshot.hormigas, sprites, snapshot.ancho_mundo, snapshot.alto_mundo, rm)


# ---------------------------------------------------------------------- panel
def _dibujar_boton(panel: pygame.Surface, fuentes: Fuentes, boton, estado_ui: EstadoUI) -> None:
    x, y, w, h = boton.rect
    caja = pygame.Rect(x - ANCHO_ESCENARIO, y, w, h)      # coordenadas locales del panel
    activo = boton_activo(boton, estado_ui)
    pygame.draw.rect(panel, COLOR_BOTON_ACTIVO if activo else COLOR_BOTON, caja, border_radius=8)
    pygame.draw.rect(panel, COLOR_ACENTO if activo else COLOR_BORDE, caja, 2, border_radius=8)
    texto = fuentes.normal.render(etiqueta_boton(boton, estado_ui), True, COLOR_TEXTO)
    panel.blit(texto, texto.get_rect(center=caja.center))


def construir_superficie_panel(fuentes: Fuentes, lineas: tuple[LineaPanel, ...],
                               estado_ui: EstadoUI) -> pygame.Surface:
    """Panel lateral completo (cabecera, estadísticas y controles).

    Es costoso de redibujar en cada cuadro, por eso main.py lo reutiliza mientras
    sus líneas y el estado de la interfaz no cambien.
    """
    panel = pygame.Surface((ANCHO_PANEL, ALTO_VENTANA))
    panel.fill(COLOR_PANEL)
    pygame.draw.line(panel, COLOR_BORDE, (0, 0), (0, ALTO_VENTANA), 2)

    panel.blit(fuentes.titulo.render("ANTHROSWARM", True, COLOR_TEXTO), (MARGEN, 12))
    estado = fuentes.pequena.render(texto_estado(estado_ui), True,
                                    COLOR_PAUSA if estado_ui.en_pausa else COLOR_ACENTO)
    panel.blit(estado, (ANCHO_PANEL - MARGEN - estado.get_width(), 42))

    for linea, y in zip(lineas, posiciones_panel(lineas)):
        if linea.tipo == "titulo":
            panel.blit(fuentes.seccion.render(linea.etiqueta, True, COLOR_ACENTO), (MARGEN, y))
            pygame.draw.line(panel, COLOR_BORDE, (MARGEN, y + ALTO_TITULO - 4),
                             (ANCHO_PANEL - MARGEN, y + ALTO_TITULO - 4), 1)
        else:
            panel.blit(fuentes.normal.render(linea.etiqueta, True, COLOR_TEXTO_SUAVE), (MARGEN, y))
            valor = fuentes.normal.render(linea.valor, True, COLOR_TEXTO)
            panel.blit(valor, (ANCHO_PANEL - MARGEN - valor.get_width(), y))

    panel.blit(fuentes.seccion.render("Controles", True, COLOR_ACENTO), (MARGEN, Y_TITULO_CONTROLES))
    panel.blit(fuentes.pequena.render("Velocidad", True, COLOR_TEXTO_SUAVE), (MARGEN, Y_ETIQUETA_VELOCIDAD))
    panel.blit(fuentes.pequena.render("Modo", True, COLOR_TEXTO_SUAVE), (MARGEN, Y_ETIQUETA_MODO))
    for boton in BOTONES:
        _dibujar_boton(panel, fuentes, boton, estado_ui)
    return panel
