"""Estabilidad del simulador asíncrono: cierre seguro, pasos interrumpidos y métricas.

Sin Pygame y sin el motor. Los pasos son DOBLES DE PRUEBA y el reloj es FALSO
(el tiempo solo avanza cuando el propio doble lo avanza), así que los resultados
son deterministas y no dependen de la velocidad del computador.
"""
import queue
import threading
from contextlib import contextmanager

import pytest

from ui.runner import (
    Canales,
    Orden,
    SimuladorNoTerminoError,
    bucle_simulador,
    cerrar_pools_abandonados,
    iniciar_simulador,
    publicar_ultimo,
    sesion_motor,
)

DT = 1.0 / 60.0


# ------------------------------------------------------------ cierre seguro
def paso_bloqueado():
    """Paso que se queda dentro de update() hasta que el test lo libera."""
    en_paso, liberar = threading.Event(), threading.Event()

    def paso(e):
        en_paso.set()
        liberar.wait(10)
        return e + 1
    return paso, en_paso, liberar


def test_un_paso_lento_hace_que_el_cierre_falle_en_voz_alta_y_no_deja_el_hilo_en_silencio():
    paso, en_paso, liberar = paso_bloqueado()
    try:
        with pytest.raises(SimuladorNoTerminoError, match="sigue ejecutando un paso"):
            with iniciar_simulador(lambda: 0, {"secuencial": paso}, lambda e: DT,
                                   Orden(0, "secuencial", False, 4.0), espera_cierre_s=0.2) as sim:
                assert en_paso.wait(5)                      # el hilo ya está dentro del paso lento
        assert sim.hilo.is_alive()                          # y se ha informado: no es un cierre "limpio"
    finally:
        liberar.set()
    sim.hilo.join(5)
    assert not sim.hilo.is_alive()                          # al terminar el paso, el hilo sí se detiene


def test_si_el_paso_termina_a_tiempo_el_cierre_es_normal():
    paso, en_paso, liberar = paso_bloqueado()
    threading.Timer(0.1, liberar.set).start()               # el paso termina durante la espera de cierre
    with iniciar_simulador(lambda: 0, {"secuencial": paso}, lambda e: DT,
                           Orden(0, "secuencial", False, 4.0), espera_cierre_s=5.0) as sim:
        assert en_paso.wait(5)
    assert not sim.hilo.is_alive()


def _pool_falso(eventos):
    @contextmanager
    def abrir():
        eventos.append("pool abierto")
        try:
            yield "conexion"
        finally:
            eventos.append("pool cerrado")
    return abrir


def test_el_pool_se_cierra_solo_despues_de_que_el_hilo_termino():
    eventos, hilos = [], []
    pasos = {"secuencial": lambda e: e + 1}

    def iniciar(conexion):
        assert conexion == "conexion"
        return iniciar_simulador(lambda: 0, pasos, lambda e: DT, Orden(0, "secuencial", False, 1.0))

    @contextmanager
    def abrir():
        with _pool_falso(eventos)() as c:
            try:
                yield c
            finally:
                eventos.append(f"hilo vivo al cerrar el pool: {hilos[0].is_alive()}")

    with sesion_motor(abrir, iniciar) as (conexion, sim):
        hilos.append(sim.hilo)
    assert eventos == ["pool abierto", "hilo vivo al cerrar el pool: False", "pool cerrado"]


def test_si_el_hilo_no_termina_el_pool_no_se_cierra():
    eventos = []
    paso, en_paso, liberar = paso_bloqueado()

    def iniciar(conexion):
        return iniciar_simulador(lambda: 0, {"secuencial": paso}, lambda e: DT,
                                 Orden(0, "secuencial", False, 4.0), espera_cierre_s=0.2)
    hilo = None
    try:
        with pytest.raises(SimuladorNoTerminoError):
            with sesion_motor(_pool_falso(eventos), iniciar) as (_, sim):
                hilo = sim.hilo
                assert en_paso.wait(5)
        assert eventos == ["pool abierto"]                  # NO se cerró mientras el hilo podía usarlo
        assert hilo.is_alive()
    finally:
        liberar.set()
    hilo.join(5)
    assert not hilo.is_alive()
    assert cerrar_pools_abandonados() == 1                   # ya sin hilo, se puede cerrar con seguridad
    assert eventos == ["pool abierto", "pool cerrado"]


def test_si_el_cuerpo_falla_con_el_hilo_sano_el_pool_igualmente_se_cierra():
    eventos = []
    with pytest.raises(ValueError, match="boom"):
        with sesion_motor(_pool_falso(eventos),
                          lambda c: iniciar_simulador(lambda: 0, {"secuencial": lambda e: e + 1},
                                                      lambda e: DT, Orden(0, "secuencial", False, 1.0))):
            raise ValueError("boom")
    assert eventos == ["pool abierto", "pool cerrado"]


# ------------------------------------------------- bucle determinista (reloj falso)
class Grabadora(queue.Queue):
    """Buzón que además guarda TODO lo que se publica (el normal solo conserva lo último)."""
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.todo = []

    def put_nowait(self, item):
        self.todo.append(item)
        super().put_nowait(item)


def ejecutar_bucle(crear_pasos, orden, *, salto_inicial=0.0, avance_dormir=0.004, al_dormir=None,
                   ventana_s=1.0, max_pasos=8, limite_dormidas=400, crear=lambda: 0):
    """Corre bucle_simulador en ESTE hilo con un reloj falso.

    crear_pasos(t, canales) -> dict de pasos; t[0] es el reloj. `salto_inicial` simula una espera
    larga en la primera dormida (para que llegue un lote de pasos de una vez).
    """
    t = [0.0]
    canales = Canales(queue.Queue(maxsize=1), Grabadora(maxsize=1), threading.Event())
    n = [0]

    def dormir(s):
        n[0] += 1
        t[0] += salto_inicial if n[0] == 1 else avance_dormir
        if al_dormir:
            al_dormir(n[0], canales)
        if n[0] >= limite_dormidas:
            canales.parar.set()

    bucle_simulador(crear, crear_pasos(t, canales), lambda e: DT, canales, orden,
                    reloj=lambda: t[0], dormir=dormir, max_pasos=max_pasos, ventana_s=ventana_s)
    return canales.resultados.todo


def test_la_pausa_a_mitad_de_un_lote_conserva_los_pasos_pendientes():
    """Llegan 6 pasos de una vez; la pausa aparece tras el 2.º. Los 4 restantes se hacen al reanudar."""
    cuenta = [0]

    def crear_pasos(t, canales):
        def paso(e):
            cuenta[0] += 1
            if cuenta[0] == 2:
                publicar_ultimo(canales.ordenes, Orden(0, "a", True, 1.0))
            if cuenta[0] == 6:
                canales.parar.set()
            return e + 1
        return {"a": paso}

    def al_dormir(n, canales):
        if n >= 2:                                           # ya está en pausa: reanudar
            publicar_ultimo(canales.ordenes, Orden(0, "a", False, 1.0))

    r = ejecutar_bucle(crear_pasos, Orden(0, "a", False, 1.0), salto_inicial=0.1, al_dormir=al_dormir)
    ultimo = r[-1]
    assert (ultimo.pasos, ultimo.estado) == (6, 6)           # ninguno de los 6 se perdió
    assert ultimo.descartado_total == 0 and ultimo.cancelado_total == 0


def test_el_reinicio_a_mitad_de_un_lote_registra_los_pasos_cancelados():
    cuenta = [0]

    def crear_pasos(t, canales):
        def paso(e):
            cuenta[0] += 1
            if cuenta[0] == 2:
                publicar_ultimo(canales.ordenes, Orden(1, "a", False, 1.0))   # reinicio
            return e + 1
        return {"a": paso}

    def al_dormir(n, canales):
        if n >= 3:
            canales.parar.set()

    r = ejecutar_bucle(crear_pasos, Orden(0, "a", False, 1.0), salto_inicial=0.1, al_dormir=al_dormir)
    assert cuenta[0] == 2                                    # el lote se abandonó tras el 2.º paso
    nuevo = next(x for x in r if x.generacion == 1)
    assert (nuevo.estado, nuevo.pasos) == (0, 0)            # estado nuevo y contadores a cero
    assert nuevo.cancelado_total == pytest.approx(4 * DT)    # los 4 pasos abandonados quedaron registrados
    assert nuevo.descartado_total == 0                       # y no se confunden con retraso


def test_la_pausa_sigue_deteniendo_los_pasos_y_reanudar_los_continua():
    cuenta = [0]

    def crear_pasos(t, canales):
        def paso(e):
            t[0] += 0.001
            cuenta[0] += 1
            return e + 1
        return {"a": paso}

    def al_dormir(n, canales):
        if n == 50:
            publicar_ultimo(canales.ordenes, Orden(0, "a", True, 1.0))
        if n == 80:
            publicar_ultimo(canales.ordenes, Orden(0, "a", False, 1.0))
        if n == 81:
            congelados.append(cuenta[0])
        if n >= 130:
            canales.parar.set()

    congelados = []
    ejecutar_bucle(crear_pasos, Orden(0, "a", False, 1.0), al_dormir=al_dormir)
    assert 0 < congelados[0] < cuenta[0]                     # tras reanudar siguió avanzando


# ------------------------------------------------- métricas coherentes con las condiciones
def pasos_que_cambian_la_orden(cuando, nueva_orden, duraciones, total):
    """Pasos con duración propia (avanzan el reloj falso); en el paso `cuando` llega `nueva_orden`."""
    cuenta = [0]

    def crear_pasos(t, canales):
        def hacer(nombre):
            def paso(e):
                t[0] += duraciones[nombre]
                cuenta[0] += 1
                if cuenta[0] == cuando:
                    publicar_ultimo(canales.ordenes, nueva_orden)
                if cuenta[0] >= total:
                    canales.parar.set()
                return e + 1
            return paso
        return {nombre: hacer(nombre) for nombre in duraciones}
    return crear_pasos


def test_al_cambiar_de_modo_no_se_mezclan_los_ms_por_paso_de_modos_distintos():
    crear_pasos = pasos_que_cambian_la_orden(
        cuando=20, nueva_orden=Orden(0, "rapido", False, 1.0),
        duraciones={"lento": 0.010, "rapido": 0.001}, total=150)
    r = ejecutar_bucle(crear_pasos, Orden(0, "lento", False, 1.0), ventana_s=0.15)
    lentos = [x for x in r if x.modo == "lento" and x.ms_por_paso is not None]
    rapidos = [x for x in r if x.modo == "rapido"]
    assert lentos and rapidos
    assert all(x.ms_por_paso == pytest.approx(10.0) for x in lentos)
    # Con un promedio mezclado saldría entre 1 y 10 ms; con ventanas separadas, 1 ms (o None).
    assert all(x.ms_por_paso is None or x.ms_por_paso == pytest.approx(1.0) for x in rapidos)
    assert rapidos[0].ms_por_paso == pytest.approx(1.0)      # la primera muestra ya es del modo nuevo


def test_al_cambiar_el_multiplicador_el_ritmo_solo_describe_las_condiciones_medidas():
    crear_pasos = pasos_que_cambian_la_orden(
        cuando=30, nueva_orden=Orden(0, "a", False, 2.0), duraciones={"a": 0.001}, total=260)
    r = ejecutar_bucle(crear_pasos, Orden(0, "a", False, 1.0), ventana_s=0.2)
    ritmos = [x.ritmo for x in r if x.ritmo is not None]
    assert len(ritmos) >= 3
    # Con ventanas mezcladas (mitad a 1x, mitad a 2x, comparadas contra 2x) saldría ~0.75.
    assert all(0.85 < v < 1.15 for v in ritmos), ritmos


def test_tras_un_cambio_de_condiciones_el_ritmo_se_olvida_hasta_medirlo_de_nuevo():
    crear_pasos = pasos_que_cambian_la_orden(
        cuando=40, nueva_orden=Orden(0, "a", False, 2.0), duraciones={"a": 0.001}, total=200)
    r = ejecutar_bucle(crear_pasos, Orden(0, "a", False, 1.0), ventana_s=0.2)
    assert any(x.ritmo is not None for x in r if x.pasos <= 40)   # antes del cambio sí había ritmo medido
    primero_nuevo = next(x for x in r if x.pasos == 41)           # primer paso con las condiciones nuevas
    assert primero_nuevo.ritmo is None                            # nada del 1x se muestra como si fuera 2x
