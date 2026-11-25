"""ADAPTADOR — ÚNICO archivo de la interfaz que conoce los nombres del motor.

Todo lo demás (timestep, runner, interface, controls, snapshot, panel, assets,
renderer, main) trabaja con RenderSnapshot, Orden/Resultado y funciones recibidas
por parámetro.

CONTRATOS QUE USA (código oficial del repositorio, commit 12e22a1 de Jean Pierre, que
integra la implementación definitiva de Mike, commit 4e71fb0):
  * models/  (Mike): GameState, Ant, Food, Nest, Pheromone, SimConfig, AntState.
  * logic/   (Mike): update(state, ejecutor) y crear_estado_inicial(config, n_hormigas).
  * engine/  (Jean): abrir_motor, ejecutor_paralelo, procesar_secuencial, nucleos_totales.
Este archivo NO modifica ni duplica ninguno de ellos: solo lee el estado y lo traduce
a RenderSnapshot. Se usa SimConfig() tal cual; solo se acepta otro tamaño de mundo si
se pide expresamente con `mundo`.

Para ver el estado de cada punto:   python -m ui.adapter
"""
from __future__ import annotations

import importlib.util
import math
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from itertools import groupby
from operator import itemgetter
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping

from ui.snapshot import (
    CapaFeromonaVista,
    EstadoHormigaVista,
    FuenteVista,
    HormigaVista,
    HormigueroVista,
    MetricasVista,
    RenderSnapshot,
)

MODULOS_MOTOR: tuple[str, ...] = ("engine", "logic", "models")
DISPONIBLE: bool = all(importlib.util.find_spec(m) is not None for m in MODULOS_MOTOR)
CELDA_FEROMONA: float = 10.0   # unidades del mundo por celda de la cuadrícula de DIBUJO (decisión de la UI)

# Nombres de AntState (models/entities.py de Mike) -> estado de dibujo. La entrega NO es un
# estado: es el evento `AntResult.delivered`, tras el cual la hormiga vuelve a EXPLORING.
ESTADOS_HORMIGA = MappingProxyType({
    "EXPLORING": EstadoHormigaVista.EXPLORANDO,
    "COLLECTING": EstadoHormigaVista.RECOLECTANDO,
    "RETURNING": EstadoHormigaVista.REGRESANDO,
})

VERIFICADO = "VERIFICADO_CON_CODIGO_OFICIAL"
DERIVADO = "DERIVADO_DEL_CODIGO_OFICIAL"
SIN_DATO_EN_MOTOR = "NO_EXISTE_EN_EL_MOTOR"
INDEPENDIENTE = "INDEPENDIENTE_DEL_MOTOR"


@dataclass(frozen=True)
class Punto:
    nombre: str
    estado: str
    detalle: str


PUNTOS_DE_INTEGRACION: tuple[Punto, ...] = (
    Punto("logic.update(state, ejecutor=procesar_hormigas) -> GameState", VERIFICADO,
          "Firma oficial (logic/update.py). No recibe ni devuelve `events`."),
    Punto("logic.crear_estado_inicial(config, n_hormigas) -> GameState", VERIFICADO,
          "logic/state.py. Hormiguero en el centro, 4 fuentes de 50 unidades, todas las hormigas EXPLORING."),
    Punto("SimConfig.dt = 1/60", VERIFICADO, "Se lee de estado.config.dt; coincide con el paso fijo aprobado."),
    Punto("Ejecutores y `with abrir_motor()`", VERIFICADO,
          "engine/ejecutores.py: un solo Pool para toda la sesión, spawn por defecto, cierre con close()+join() "
          "(o terminate()+join() ante un error). Equivalencia secuencial == paralelo probada por Jean y aquí."),
    Punto("Campos usados de GameState/Ant/Food/Nest/SimConfig", VERIFICADO,
          "ants, foods, nest, pheromones, config; x, y, state; id, amount, radius; food_stored; width, height, "
          "dt, pheromone_deposit."),
    Punto("Estados de hormiga: EXPLORING, COLLECTING, RETURNING", VERIFICADO,
          "models/entities.py. La entrega es un evento, no un estado; un estado desconocido lanza ValueError."),
    Punto("Feromonas: UN solo tipo (lista de puntos x, y, intensity)", VERIFICADO,
          "Las depositan las hormigas en RETURNING. La UI conserva dos capas opcionales; solo se llena la de "
          "'regreso'. La de 'exploración' queda en None porque el motor no distingue tipos."),
    Punto("Entregas = nest.food_stored", VERIFICADO,
          "logic/results.py suma 1 por cada AntResult.delivered."),
    Punto("Comida recolectada = comida inicial - comida restante", DERIVADO,
          "aplicar_resultados resta 1 a la fuente por cada reclamo aceptado, así que equivale a las unidades "
          "reclamadas (entregadas + las que van en camino). Se calcula en la UI con el estado inicial de la "
          "partida; una prueba la contrasta con food_stored + hormigas con has_food."),
    Punto("Tamaño del mundo: SimConfig.width x height (800x600 por defecto)", VERIFICADO,
          "Origen (0,0) arriba a la izquierda; movement.py mantiene a las hormigas dentro. Se dibuja con escala "
          "uniforme, así que cualquier tamaño funciona."),
    Punto("Fuentes agotadas", VERIFICADO,
          "El motor ELIMINA la fuente al llegar a 0; la UI la sigue mostrando (agotada) con el estado inicial."),
    Punto("Métricas: workers, núcleos, ms/paso", VERIFICADO,
          "motor.n_workers, nucleos_totales(); el ms/paso lo mide el simulador asíncrono alrededor de update."),
    Punto("RenderSnapshot, renderer, panel, controles, timestep, runner, main", INDEPENDIENTE,
          "No dependen de los nombres de ningún motor."),
)


@dataclass(frozen=True)
class Conexion:
    """Lo que la interfaz necesita del motor abierto (inmutable)."""
    pasos: Mapping[str, Callable[[Any], Any]]   # modo -> (estado -> estado nuevo, un paso de dt fijo)
    workers: Mapping[str, int]                  # modo -> procesos que lo ejecutan
    nucleos: int


def _exigir_motor() -> None:
    if not DISPONIBLE:
        faltan = tuple(m for m in MODULOS_MOTOR if importlib.util.find_spec(m) is None)
        raise ModuleNotFoundError(
            f"Faltan módulos del motor: {', '.join(faltan)}. Copia engine/, logic/ y models/ "
            "a la carpeta del proyecto (ver ui/adapter.py).")


@contextmanager
def abrir(n_workers: int | None = None) -> Iterator[Conexion]:
    """Abre el motor paralelo UNA vez para toda la partida y lo cierra al salir (`with abrir_motor()`)."""
    _exigir_motor()
    from engine import abrir_motor, ejecutor_paralelo, nucleos_totales, procesar_secuencial
    from logic import update

    with abrir_motor(n_workers=n_workers) as motor:
        ejecutores = {"secuencial": procesar_secuencial, "paralelo": ejecutor_paralelo(motor)}
        yield Conexion(
            pasos=MappingProxyType({m: partial(update, ejecutor=e) for m, e in ejecutores.items()}),
            workers=MappingProxyType({"secuencial": 1, "paralelo": motor.n_workers}),
            nucleos=nucleos_totales())


def crear_estado_inicial(n_hormigas: int, mundo: tuple[int, int] | None = None) -> Any:
    """GameState inicial. Con mundo=None se usa SimConfig() tal como lo define el motor."""
    _exigir_motor()
    from logic import crear_estado_inicial as crear
    from models import SimConfig

    config = SimConfig() if mundo is None else SimConfig(width=mundo[0], height=mundo[1])
    return crear(config, n_hormigas)


def dt_paso(estado: Any) -> float:
    """Duración del paso lógico: la define el motor (SimConfig.dt), la UI no la duplica."""
    return float(estado.config.dt)


def _estado_vista(estado_hormiga: Any) -> EstadoHormigaVista:
    nombre = getattr(estado_hormiga, "name", str(estado_hormiga))
    try:
        return ESTADOS_HORMIGA[nombre]
    except KeyError:
        raise ValueError(f"Estado de hormiga desconocido: {nombre!r}. "
                         "Actualiza ESTADOS_HORMIGA en ui/adapter.py con el contrato de Mike.") from None


def capa_de_puntos(puntos, ancho: float, alto: float, deposito: float,
                   celda: float = CELDA_FEROMONA) -> CapaFeromonaVista:
    """Convierte puntos (x, y, intensity) en una cuadrícula 0-1 SOLO para dibujar.

    La intensidad de varios puntos en una misma celda se suma y se recorta a `deposito`
    (la intensidad de un depósito es SimConfig.pheromone_deposit). No cambia ningún dato del motor.
    """
    columnas, filas = max(1, math.ceil(ancho / celda)), max(1, math.ceil(alto / celda))
    referencia = deposito if deposito > 0 else 1.0

    def indice(p) -> int:
        c = min(columnas - 1, max(0, int(p.x / celda)))
        f = min(filas - 1, max(0, int(p.y / celda)))
        return f * columnas + c

    pares = sorted((indice(p), p.intensity) for p in puntos)
    suma = {i: sum(v for _, v in grupo) for i, grupo in groupby(pares, key=itemgetter(0))}
    return CapaFeromonaVista(columnas, filas,
                             tuple(min(1.0, suma.get(i, 0.0) / referencia) for i in range(columnas * filas)))


def _fuentes_vista(estado: Any, referencia: Any | None) -> tuple[FuenteVista, ...]:
    """Una FuenteVista por cada fuente ORIGINAL (las del estado de referencia).

    El motor elimina las fuentes agotadas del estado, pero la interfaz debe seguir
    mostrándolas (con cantidad 0, en su posición original). Las fuentes que estén en el
    estado actual y no en la referencia se agregan al final (no se pierde ninguna).
    """
    actuales = {f.id: f for f in estado.foods}
    originales = tuple((estado if referencia is None else referencia).foods)

    def de_original(f0: Any) -> FuenteVista:
        f = actuales.get(f0.id)
        if f is None:                                    # agotada y eliminada por el motor
            return FuenteVista(f0.x, f0.y, 0, f0.amount, f0.radius)
        return FuenteVista(f.x, f.y, f.amount, max(f0.amount, f.amount), f.radius)

    ids_originales = {f0.id for f0 in originales}
    nuevas = tuple(FuenteVista(f.x, f.y, f.amount, f.amount, f.radius)
                   for f in estado.foods if f.id not in ids_originales)
    return tuple(de_original(f0) for f0 in originales) + nuevas


def _recolectada(fuentes: tuple[FuenteVista, ...], referencia: Any | None) -> int | None:
    """Unidades de comida que salieron de las fuentes = inicial - restante.

    Es una lectura del GameState, no una regla nueva: en logic/results.py cada reclamo aceptado
    resta exactamente 1 a la fuente. Sin estado inicial de referencia no se puede saber -> None.
    """
    if referencia is None:
        return None
    return sum(f.cantidad_inicial - f.cantidad for f in fuentes)


def a_snapshot(estado: Any, referencia: Any | None = None) -> RenderSnapshot:
    """GameState -> RenderSnapshot (solo lectura).

    `referencia` es el estado inicial de la generación: sirve para saber cuánta comida
    tenía cada fuente al empezar (el motor no la guarda y las agotadas desaparecen).
    """
    cfg = estado.config
    fuentes = _fuentes_vista(estado, referencia)
    return RenderSnapshot(
        ancho_mundo=float(cfg.width),
        alto_mundo=float(cfg.height),
        hormiguero=HormigueroVista(estado.nest.x, estado.nest.y, estado.nest.radius),
        fuentes=fuentes,
        hormigas=tuple(HormigaVista(a.x, a.y, _estado_vista(a.state)) for a in estado.ants),
        feromona_exploracion=None,   # el motor oficial tiene un solo tipo de feromona (ver PUNTOS_DE_INTEGRACION)
        feromona_regreso=capa_de_puntos(estado.pheromones, cfg.width, cfg.height, cfg.pheromone_deposit),
        entregadas=estado.nest.food_stored,
        recolectada_total=_recolectada(fuentes, referencia),
    )


def metricas(conexion: Conexion, modo: str, ms_por_paso: float | None) -> MetricasVista:
    return MetricasVista(workers=conexion.workers.get(modo), nucleos=conexion.nucleos,
                         ms_por_paso=ms_por_paso)


def imprimir_puntos() -> None:
    print(f"Motor disponible en esta carpeta: {'sí' if DISPONIBLE else 'NO (faltan ' + ', '.join(m for m in MODULOS_MOTOR if importlib.util.find_spec(m) is None) + ')'}\n")
    for p in PUNTOS_DE_INTEGRACION:
        print(f"[{p.estado}] {p.nombre}\n    {p.detalle}")


if __name__ == "__main__":
    imprimir_puntos()
