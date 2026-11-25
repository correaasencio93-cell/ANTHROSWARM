"""Simulador asíncrono: la simulación corre en un hilo aparte y Pygame sigue dibujando.

PROBLEMA. `update()` es síncrono y, en modo paralelo, `starmap` bloquea hasta que
terminan los workers. Si el Game Loop lo llamara directamente, la ventana quedaría
congelada (sin dibujar ni leer controles) durante todo el paso.

SOLUCIÓN. Un hilo ("simulador") ejecuta los pasos y el hilo principal solo dibuja y
lee eventos. Se hablan por dos buzones de UN solo valor (queue.Queue(maxsize=1)):

    hilo principal  --Orden-->     simulador     (pausa, velocidad, modo, generación)
    hilo principal  <--Resultado-- simulador     (estado nuevo + métricas)

POR QUÉ ES SEGURO SIN CANDADOS PARA LOS DATOS. El GameState es inmutable
(@dataclass(frozen=True)): el simulador lo publica por referencia y nadie puede
modificarlo, así que no hay que copiarlo ni protegerlo. Los únicos objetos mutables
compartidos son los buzones y el Event de cierre, y ya son seguros entre hilos.
Las órdenes y los resultados también son dataclasses congeladas.

CÓMO SE EVITAN RESULTADOS OBSOLETOS
  1. Buzón "el último gana": si el dibujo va más lento que la simulación, los
     resultados viejos se sustituyen; nunca se forma una cola de estados antiguos.
  2. Generación: cada reinicio sube un contador. Todo Resultado lleva la
     generación con la que se calculó y la interfaz descarta (es_vigente) los de una
     generación anterior, que pudieron publicarse justo antes de que el simulador
     viera el reinicio. El simulador, además, abandona el paso pendiente.
  3. Secuencia creciente: la interfaz solo reconvierte/dibuja si llegó una nueva.
  4. Cambio de modo: un paso en curso no se puede interrumpir y termina con el modo
     anterior; su resultado sigue siendo válido porque continúa el MISMO estado (la
     equivalencia secuencial == paralelo la comprueban los tests de Jean). Cada
     Resultado indica con qué modo se calculó (ms_del_modo evita mostrar tiempos de
     otro modo).

LÍMITE HONESTO. Python tiene un GIL: en modo secuencial el cálculo en Python puro
compite con el dibujo por el intérprete, así que la ventana sigue respondiendo pero
no a pleno rendimiento. En modo paralelo el hilo casi solo espera a los procesos
(libera el GIL) y el beneficio es mayor. Está medido en tests/bench_asincrono.py.

Este módulo no importa pygame ni el motor: recibe funciones (crear estado, pasos).
"""
from __future__ import annotations

import queue
import threading
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping

from ui.timestep import MAX_PASOS_POR_CUADRO, EstadoTiempo, avanzar_tiempo, cancelar_pasos, devolver_pasos

VENTANA_RITMO_S: float = 1.0     # cada cuánto se recalcula el ritmo real y el ms/paso
ESPERA_CIERRE_S: float = 10.0    # cuánto espera el cierre a que termine el paso en curso (si vence: SimuladorNoTerminoError)


@dataclass(frozen=True)
class Orden:
    """Lo que la interfaz le pide al simulador."""
    generacion: int
    modo: str
    en_pausa: bool
    multiplicador: float


@dataclass(frozen=True)
class Resultado:
    """Lo que el simulador publica. `estado` es el GameState (inmutable) del motor."""
    generacion: int
    secuencia: int
    estado: Any
    estado_inicial: Any
    pasos: int                       # pasos ejecutados en esta generación
    modo: str                        # modo con el que se calculó el último paso
    ms_por_paso: float | None
    ritmo: float | None              # 1.0 = la simulación sigue el ritmo pedido
    descartado_total: float          # segundos de simulación que no se pudieron ejecutar
    error: str | None = None
    cancelado_total: float = 0.0     # segundos de pasos calculados y abandonados por un reinicio


class SimuladorNoTerminoError(RuntimeError):
    """El hilo del simulador sigue dentro de un paso al vencer la espera de cierre.

    No se puede matar un hilo en Python; por eso el cierre NO continúa en silencio y
    quien abrió el pool (ver `sesion_motor`) no debe cerrarlo mientras el hilo viva.
    """


_POOLS_ABANDONADOS: list[ExitStack] = []   # ver sesion_motor


@dataclass(frozen=True)
class Canales:
    ordenes: queue.Queue
    resultados: queue.Queue
    parar: threading.Event


@dataclass(frozen=True)
class Simulador:
    canales: Canales
    hilo: threading.Thread


# ------------------------------------------------------------ funciones puras
def calcular_ritmo(pasos: int, dt_paso: float, tiempo_real_s: float,
                   multiplicador: float) -> float | None:
    """Tiempo de simulación ejecutado / tiempo de simulación pedido (1.0 = al ritmo)."""
    if tiempo_real_s <= 0 or multiplicador <= 0 or dt_paso <= 0:
        return None
    return pasos * dt_paso / (tiempo_real_s * multiplicador)


def es_vigente(resultado: Resultado | None, generacion_esperada: int) -> bool:
    """False para un resultado calculado con una generación anterior (obsoleto)."""
    return resultado is not None and resultado.generacion == generacion_esperada


def ms_del_modo(resultado: Resultado | None, modo: str) -> float | None:
    """ms/paso solo si se midieron con el modo que muestra la interfaz."""
    return None if resultado is None or resultado.modo != modo else resultado.ms_por_paso


# --------------------------------------------------------------------- buzones
def publicar_ultimo(cola: queue.Queue, valor: Any) -> None:
    """Deja `valor` en el buzón sustituyendo el anterior (el último gana).

    Hay un único productor por buzón, así que tras vaciarlo put_nowait nunca falla.
    """
    try:
        cola.get_nowait()
    except queue.Empty:
        pass
    cola.put_nowait(valor)


def leer_ultimo(cola: queue.Queue) -> Any | None:
    """Toma lo publicado sin esperar; None si no hay nada nuevo."""
    try:
        return cola.get_nowait()
    except queue.Empty:
        return None


def enviar_orden(sim: Simulador, orden: Orden) -> None:
    publicar_ultimo(sim.canales.ordenes, orden)


def leer_resultado(sim: Simulador) -> Resultado | None:
    """No bloquea nunca: es lo único que el hilo principal hace con el simulador."""
    return leer_ultimo(sim.canales.resultados)


# ------------------------------------------------------------ bucle del hilo
def bucle_simulador(crear_estado: Callable[[], Any],
                    pasos: Mapping[str, Callable[[Any], Any]],
                    dt_de_estado: Callable[[Any], float],
                    canales: Canales,
                    orden_inicial: Orden,
                    reloj: Callable[[], float] = time.perf_counter,
                    dormir: Callable[[float], None] = time.sleep,
                    max_pasos: int = MAX_PASOS_POR_CUADRO,
                    ventana_s: float = VENTANA_RITMO_S) -> None:
    """Función del hilo. Las variables locales de abajo son el estado del BORDE (efectos);
    el simulador en sí (los pasos) sigue siendo estado -> estado nuevo."""
    orden = orden_inicial
    generacion = orden.generacion - 1      # fuerza el arranque de la primera generación
    estado = inicial = None
    dt = 1.0 / 60.0
    tiempo = EstadoTiempo()
    pasos_total = secuencia = 0
    modo_actual = orden.modo
    ms_pub: float | None = None
    ritmo: float | None = None
    v_inicio = v_pasos = v_ms = 0.0
    clave_ventana = (orden.modo, orden.multiplicador)   # condiciones bajo las que se mide
    anterior = reloj()

    def publicar(error: str | None = None) -> None:
        nonlocal secuencia
        secuencia += 1
        publicar_ultimo(canales.resultados, Resultado(
            generacion=generacion, secuencia=secuencia, estado=estado, estado_inicial=inicial,
            pasos=pasos_total, modo=modo_actual, ms_por_paso=ms_pub, ritmo=ritmo,
            descartado_total=tiempo.descartado_total, error=error,
            cancelado_total=tiempo.cancelado_total))

    def reiniciar_ventana() -> None:
        nonlocal v_inicio, v_pasos, v_ms
        v_inicio, v_pasos, v_ms = reloj(), 0, 0.0

    def sincronizar_ventana() -> None:
        """Una ventana de medición solo vale para UN modo y UN multiplicador.

        Si cambian, lo medido hasta ahora no describe las condiciones nuevas: se abre una
        ventana limpia y se olvidan ms/paso y ritmo hasta medirlos de nuevo.
        """
        nonlocal clave_ventana, ms_pub, ritmo
        if (orden.modo, orden.multiplicador) != clave_ventana:
            clave_ventana = (orden.modo, orden.multiplicador)
            ms_pub = ritmo = None
            reiniciar_ventana()

    try:
        while not canales.parar.is_set():
            nueva = leer_ultimo(canales.ordenes)
            if nueva is not None:
                orden = nueva

            if orden.generacion != generacion:                 # arranque o reinicio
                generacion = orden.generacion
                estado = inicial = crear_estado()
                dt = dt_de_estado(estado)
                tiempo = EstadoTiempo(descartado_total=tiempo.descartado_total,
                                      cancelado_total=tiempo.cancelado_total)
                pasos_total, ms_pub, ritmo = 0, None, None
                modo_actual = orden.modo
                clave_ventana = (orden.modo, orden.multiplicador)
                reiniciar_ventana()
                anterior = reloj()
                publicar()

            ahora = reloj()
            dt_real, anterior = ahora - anterior, ahora

            if orden.en_pausa:
                ritmo = None
                reiniciar_ventana()
                dormir(0.005)
                continue

            sincronizar_ventana()
            if ahora - v_inicio >= ventana_s and v_pasos > 0:
                ritmo = calcular_ritmo(v_pasos, dt, ahora - v_inicio, orden.multiplicador)
                ms_pub = v_ms / v_pasos
                reiniciar_ventana()

            r = avanzar_tiempo(tiempo, dt_real, orden.multiplicador, False, dt, max_pasos)
            tiempo = r.estado

            ejecutados = 0
            for _ in range(r.pasos):
                sincronizar_ventana()                            # la orden pudo cambiar entre pasos
                modo_actual = orden.modo
                t0 = reloj()
                estado = pasos[modo_actual](estado)              # UN paso de dt fijo (puede bloquear)
                ms = (reloj() - t0) * 1000.0
                ejecutados += 1
                pasos_total += 1
                v_pasos += 1
                v_ms += ms
                if ms_pub is None:
                    ms_pub = ms                                  # primera muestra de estas condiciones
                publicar()
                nueva = leer_ultimo(canales.ordenes)             # reaccionar entre pasos
                if nueva is not None:
                    orden = nueva
                    if orden.generacion != generacion or orden.en_pausa:
                        break
                if canales.parar.is_set():
                    break

            # Pasos que avanzar_tiempo ya descontó pero no se ejecutaron: nunca se pierden en silencio.
            pendientes = r.pasos - ejecutados
            if pendientes:
                if orden.generacion != generacion or canales.parar.is_set():
                    tiempo = cancelar_pasos(tiempo, pendientes, dt)   # su estado ya no existe: se registran
                else:
                    tiempo = devolver_pasos(tiempo, pendientes, dt)   # pausa: se ejecutarán al reanudar

            if r.pasos == 0:
                dormir(min(0.004, max(0.001, (dt - tiempo.acumulador) / max(orden.multiplicador, 0.01))))
    except BaseException as exc:                                  # el hilo nunca muere en silencio
        publicar(error=f"{type(exc).__name__}: {exc}")


@contextmanager
def iniciar_simulador(crear_estado: Callable[[], Any],
                      pasos: Mapping[str, Callable[[Any], Any]],
                      dt_de_estado: Callable[[Any], float],
                      orden_inicial: Orden,
                      *,
                      reloj: Callable[[], float] = time.perf_counter,
                      dormir: Callable[[float], None] = time.sleep,
                      max_pasos: int = MAX_PASOS_POR_CUADRO,
                      ventana_s: float = VENTANA_RITMO_S,
                      espera_cierre_s: float = ESPERA_CIERRE_S) -> Iterator[Simulador]:
    """Arranca el hilo, lo entrega y lo detiene al salir (como `with abrir_motor()`).

    Orden de uso en main: primero `with abrir_motor()` (procesos) y dentro de él
    `with iniciar_simulador(...)`; así el hilo termina ANTES de cerrar los workers.
    """
    canales = Canales(queue.Queue(maxsize=1), queue.Queue(maxsize=1), threading.Event())
    hilo = threading.Thread(
        target=bucle_simulador, name="simulador", daemon=True,
        args=(crear_estado, pasos, dt_de_estado, canales, orden_inicial, reloj, dormir, max_pasos, ventana_s))
    hilo.start()
    try:
        yield Simulador(canales, hilo)
    finally:
        canales.parar.set()
        hilo.join(espera_cierre_s)
        if hilo.is_alive():
            # El hilo sigue dentro de un paso (p. ej. esperando a los workers). No se puede
            # interrumpir; salir en silencio dejaría un hilo usando recursos que el cierre va a liberar.
            raise SimuladorNoTerminoError(
                f"El simulador sigue ejecutando un paso tras {espera_cierre_s:g} s de espera de cierre. "
                "No se cerrará el pool mientras ese hilo pueda estar usándolo.")


@contextmanager
def sesion_motor(abrir: Callable[[], Any], iniciar: Callable[[Any], Any]) -> Iterator[tuple[Any, Simulador]]:
    """`with abrir()` + `with iniciar(conexion)` con el orden de cierre correcto y seguro.

    Cierre normal: el hilo termina primero y después se cierra el pool. Si el hilo NO
    termina (SimuladorNoTerminoError), el pool se deja abierto a propósito: cerrarlo
    con un paso en curso podría bloquear o corromper ese paso; la excepción sube a quien
    llamó y los procesos del pool (daemon) los recoge el intérprete al terminar.
    """
    with ExitStack() as pila:
        conexion = pila.enter_context(abrir())
        try:
            with iniciar(conexion) as sim:
                yield conexion, sim
        except SimuladorNoTerminoError:
            # Se retiran los cierres de esta pila SIN ejecutarlos y se guardan: si no hubiera una
            # referencia, el recolector de basura cerraría el pool igualmente (cierra el generador).
            _POOLS_ABANDONADOS.append(pila.pop_all())
            raise


def cerrar_pools_abandonados() -> int:
    """Cierra los pools que `sesion_motor` dejó abiertos. Llamar SOLO cuando el hilo ya terminó.

    Devuelve cuántos cerró. Si el proceso termina sin llamarla, el intérprete limpia los procesos
    daemon del pool al salir.
    """
    n = 0
    while _POOLS_ABANDONADOS:
        _POOLS_ABANDONADOS.pop().close()
        n += 1
    return n
