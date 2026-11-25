"""Recursos gráficos generados por código (sin imágenes externas): fondo del
terreno, decoraciones, sprites de hormigas y fuentes.

Se construyen UNA sola vez al iniciar; el fondo ya trae las decoraciones
"pegadas", así que dibujarlas cada cuadro no cuesta nada. Las decoraciones no
forman parte del estado del simulador y no bloquean el movimiento.

Aleatoriedad: se usa un generador LOCAL con semilla fija (random.Random), no las
funciones globales del módulo random, para que el resultado sea reproducible y no
haya estado global mutable.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from types import MappingProxyType

import pygame

from ui.snapshot import EstadoHormigaVista

Color = tuple[int, int, int]

COLOR_SUELO: Color = (118, 94, 62)
COLORES_PARCHES: tuple[Color, ...] = ((104, 84, 54), (128, 104, 70), (96, 118, 64), (110, 130, 70))
COLORES_PIEDRA: tuple[Color, ...] = ((118, 116, 112), (96, 95, 92), (136, 132, 124))
COLORES_HOJA: tuple[Color, ...] = ((72, 132, 52), (104, 152, 62), (176, 120, 40), (140, 92, 36))
COLOR_RAMA: Color = (84, 58, 34)

COLORES_HORMIGA = MappingProxyType({
    EstadoHormigaVista.EXPLORANDO: (25, 25, 25),
    EstadoHormigaVista.RECOLECTANDO: (255, 225, 50),
    EstadoHormigaVista.REGRESANDO: (255, 110, 20),
    EstadoHormigaVista.ENTREGANDO: (90, 200, 255),
})
TAM_SPRITE: int = 7


@dataclass(frozen=True)
class Decoracion:
    tipo: str        # "piedra", "hoja" o "rama"
    x: float
    y: float
    tamano: float
    angulo: float    # radianes
    variante: int    # índice de color


@dataclass(frozen=True)
class Fuentes:
    titulo: pygame.font.Font
    seccion: pygame.font.Font
    normal: pygame.font.Font
    pequena: pygame.font.Font


def generar_decoraciones(ancho: int, alto: int, semilla: int = 2026,
                         n_piedras: int = 14, n_hojas: int = 26,
                         n_ramas: int = 10) -> tuple[Decoracion, ...]:
    """Decide dónde van las decoraciones. Es determinista: misma semilla, mismo resultado."""
    rng = random.Random(semilla)
    margen = 30

    def una(tipo: str, tam_min: float, tam_max: float, n_variantes: int) -> Decoracion:
        return Decoracion(tipo,
                          rng.uniform(margen, ancho - margen),
                          rng.uniform(margen, alto - margen),
                          rng.uniform(tam_min, tam_max),
                          rng.uniform(0, math.pi),
                          rng.randrange(n_variantes))

    return (tuple(una("piedra", 8, 20, len(COLORES_PIEDRA)) for _ in range(n_piedras))
            + tuple(una("hoja", 8, 14, len(COLORES_HOJA)) for _ in range(n_hojas))
            + tuple(una("rama", 30, 70, 1) for _ in range(n_ramas)))


def _variar(color: Color, rng: random.Random, d: int) -> Color:
    return tuple(max(0, min(255, c + rng.randint(-d, d))) for c in color)  # type: ignore[return-value]


def _dibujar_decoracion(sup: pygame.Surface, d: Decoracion) -> None:
    x, y = d.x, d.y
    if d.tipo == "piedra":
        base = COLORES_PIEDRA[d.variante]
        caja = pygame.Rect(0, 0, int(d.tamano * 1.6), int(d.tamano))
        caja.center = (int(x), int(y))
        sombra = caja.move(2, 2)
        pygame.draw.ellipse(sup, (60, 48, 34), sombra)
        pygame.draw.ellipse(sup, base, caja)
        brillo = pygame.Rect(0, 0, int(caja.w * 0.45), int(caja.h * 0.4))
        brillo.center = (caja.centerx - caja.w // 6, caja.centery - caja.h // 6)
        pygame.draw.ellipse(sup, tuple(min(255, c + 28) for c in base), brillo)
        pygame.draw.ellipse(sup, tuple(max(0, c - 40) for c in base), caja, 1)
    elif d.tipo == "hoja":
        largo, ancho = d.tamano, d.tamano * 0.45
        ca, sa = math.cos(d.angulo), math.sin(d.angulo)
        punta1 = (x + ca * largo, y + sa * largo)
        punta2 = (x - ca * largo, y - sa * largo)
        lado1 = (x - sa * ancho, y + ca * ancho)
        lado2 = (x + sa * ancho, y - ca * ancho)
        color = COLORES_HOJA[d.variante]
        pygame.draw.polygon(sup, color, (punta1, lado1, punta2, lado2))
        pygame.draw.line(sup, tuple(max(0, c - 35) for c in color), punta1, punta2, 1)
    else:  # rama
        fin = (x + math.cos(d.angulo) * d.tamano, y + math.sin(d.angulo) * d.tamano)
        pygame.draw.line(sup, COLOR_RAMA, (x, y), fin, 4)
        medio = ((x + fin[0]) / 2, (y + fin[1]) / 2)
        ramita = (medio[0] + math.cos(d.angulo + 0.9) * d.tamano * 0.3,
                  medio[1] + math.sin(d.angulo + 0.9) * d.tamano * 0.3)
        pygame.draw.line(sup, COLOR_RAMA, medio, ramita, 2)


def construir_fondo(ancho: int, alto: int, semilla: int = 2026) -> pygame.Surface:
    """Terreno abierto de aspecto natural: tierra con parches, motas, hierba y decoraciones."""
    rng = random.Random(semilla + 1)
    fondo = pygame.Surface((ancho, alto))
    fondo.fill(COLOR_SUELO)

    for _ in range(150):  # parches grandes de tierra y pasto
        caja = pygame.Rect(rng.randint(-40, ancho), rng.randint(-40, alto),
                           rng.randint(50, 150), rng.randint(40, 110))
        pygame.draw.ellipse(fondo, _variar(rng.choice(COLORES_PARCHES), rng, 6), caja)
    for _ in range(2600):  # motas de textura
        px, py = rng.randrange(ancho), rng.randrange(alto)
        pygame.draw.circle(fondo, _variar(COLOR_SUELO, rng, 22), (px, py), rng.randint(1, 2))
    for _ in range(700):  # briznas de hierba
        px, py = rng.randrange(ancho), rng.randrange(alto)
        verde = _variar((84, 130, 60), rng, 18)
        for dx in (-2, 0, 2):
            pygame.draw.line(fondo, verde, (px + dx, py), (px + dx + rng.randint(-2, 2), py - rng.randint(3, 6)), 1)

    for decoracion in generar_decoraciones(ancho, alto, semilla):
        _dibujar_decoracion(fondo, decoracion)
    return fondo


def _crear_sprite(color: Color) -> pygame.Surface:
    sprite = pygame.Surface((TAM_SPRITE, TAM_SPRITE), pygame.SRCALPHA)
    centro = (TAM_SPRITE // 2, TAM_SPRITE // 2)
    borde = (235, 235, 235) if sum(color) < 200 else (20, 20, 20)
    pygame.draw.circle(sprite, color, centro, TAM_SPRITE // 2)
    pygame.draw.circle(sprite, borde, centro, TAM_SPRITE // 2, 1)
    return sprite


def crear_sprites_hormigas():
    """Un sprite pre-dibujado por estado (se reutiliza para todas las hormigas)."""
    return MappingProxyType({estado: _crear_sprite(c) for estado, c in COLORES_HORMIGA.items()})


def cargar_fuentes() -> Fuentes:
    """Fuentes monoespaciadas del sistema (Consolas en Windows); si no hay, usa la de Pygame."""
    if not pygame.font.get_init():
        pygame.font.init()
    nombres = "consolas,couriernew,dejavusansmono,monospace"
    return Fuentes(
        titulo=pygame.font.SysFont(nombres, 26, bold=True),
        seccion=pygame.font.SysFont(nombres, 18, bold=True),
        normal=pygame.font.SysFont(nombres, 16),
        pequena=pygame.font.SysFont(nombres, 14),
    )
