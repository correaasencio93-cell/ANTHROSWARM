"""Botones del panel y traducción de clics/teclas a acciones.

Los botones son DATOS (tuplas de dataclasses inmutables), no objetos con métodos.
Este módulo no usa pygame: main.py convierte el evento de Pygame en una posición
(x, y) o en el nombre de una tecla, y estas funciones devuelven una Accion.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from ui.interface import (
    ANCHO_ESCENARIO,
    ANCHO_PANEL,
    MARGEN,
    MODOS,
    MULTIPLICADORES,
    Accion,
    EstadoUI,
    TipoAccion,
)

Rect = tuple[int, int, int, int]  # (x, y, ancho, alto)
Punto = tuple[int, int]

# --- Geometría de la zona de controles (parte baja del panel lateral) ---
ALTO_BOTON: int = 44
SEPARACION: int = 8
X_PANEL: int = ANCHO_ESCENARIO + MARGEN        # 976
ANCHO_UTIL: int = ANCHO_PANEL - 2 * MARGEN     # 288

# Posiciones verticales. El renderer las usa para colocar los títulos.
Y_TITULO_CONTROLES: int = 460
Y_FILA_PAUSA: int = 488
Y_ETIQUETA_VELOCIDAD: int = 540
Y_FILA_VELOCIDAD: int = 564
Y_ETIQUETA_MODO: int = 616
Y_FILA_MODO: int = 640


@dataclass(frozen=True)
class Boton:
    id: str
    etiqueta: str
    rect: Rect
    accion: Accion


def _fila(y: int, cantidad: int) -> tuple[Rect, ...]:
    """Reparte `cantidad` botones del mismo ancho en una fila del panel."""
    ancho = (ANCHO_UTIL - (cantidad - 1) * SEPARACION) // cantidad
    return tuple((X_PANEL + i * (ancho + SEPARACION), y, ancho, ALTO_BOTON)
                 for i in range(cantidad))


def _crear_botones() -> tuple[Boton, ...]:
    r_pausa, r_reiniciar = _fila(Y_FILA_PAUSA, 2)
    r_velocidad = _fila(Y_FILA_VELOCIDAD, len(MULTIPLICADORES))
    r_modo = _fila(Y_FILA_MODO, len(MODOS))
    return (
        Boton("pausa", "Pausa", r_pausa, Accion(TipoAccion.ALTERNAR_PAUSA)),
        Boton("reiniciar", "Reiniciar", r_reiniciar, Accion(TipoAccion.REINICIAR)),
        *(Boton(f"vel_{m:g}", f"{m:g}×", r, Accion(TipoAccion.FIJAR_VELOCIDAD, m))
          for m, r in zip(MULTIPLICADORES, r_velocidad)),
        *(Boton(f"modo_{m}", m.capitalize(), r, Accion(TipoAccion.FIJAR_MODO, m))
          for m, r in zip(MODOS, r_modo)),
    )


BOTONES: tuple[Boton, ...] = _crear_botones()

# Atajos de teclado. Las claves son nombres como los devuelve pygame.key.name().
ACCIONES_TECLADO = MappingProxyType({
    "space": Accion(TipoAccion.ALTERNAR_PAUSA),
    "r": Accion(TipoAccion.REINICIAR),
})


def contiene(rect: Rect, punto: Punto) -> bool:
    x, y, ancho, alto = rect
    px, py = punto
    return x <= px < x + ancho and y <= py < y + alto


def boton_en(punto: Punto, botones: tuple[Boton, ...] = BOTONES) -> Boton | None:
    return next((b for b in botones if contiene(b.rect, punto)), None)


def accion_para_clic(punto: Punto, botones: tuple[Boton, ...] = BOTONES) -> Accion | None:
    boton = boton_en(punto, botones)
    return None if boton is None else boton.accion


def accion_para_tecla(nombre_tecla: str) -> Accion | None:
    return ACCIONES_TECLADO.get(nombre_tecla)


def boton_activo(boton: Boton, estado: EstadoUI) -> bool:
    """True si el botón debe dibujarse resaltado según el estado actual."""
    accion = boton.accion
    if accion.tipo is TipoAccion.ALTERNAR_PAUSA:
        return estado.en_pausa
    if accion.tipo is TipoAccion.FIJAR_VELOCIDAD:
        return accion.valor == estado.multiplicador
    if accion.tipo is TipoAccion.FIJAR_MODO:
        return accion.valor == estado.modo
    return False


def etiqueta_boton(boton: Boton, estado: EstadoUI) -> str:
    """Texto del botón; el de pausa cambia a 'Reanudar' cuando está pausado."""
    if boton.accion.tipo is TipoAccion.ALTERNAR_PAUSA:
        return "Reanudar" if estado.en_pausa else "Pausa"
    return boton.etiqueta
