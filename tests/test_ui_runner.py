"""Pruebas del simulador asíncrono (ui/runner.py). Sin Pygame y sin el motor.

Los "estados" y "pasos" de aquí son DOBLES DE PRUEBA (enteros y funciones triviales):
solo comprueban la sincronización entre hilos, no la simulación de hormigas.
"""
import queue
import time

import pytest

from ui.runner import (
    Orden,
    calcular_ritmo,
    enviar_orden,
    es_vigente,
    iniciar_simulador,
    leer_resultado,
    leer_ultimo,
    ms_del_modo,
    publicar_ultimo,
    Resultado,
)

DT = 1.0 / 60.0


def esperar(condicion, tiempo_max=5.0, intervalo=0.005):
    """Espera activa hasta que condicion() devuelva algo verdadero; devuelve ese valor."""
    limite = time.perf_counter() + tiempo_max
    while time.perf_counter() < limite:
        valor = condicion()
        if valor:
            return valor
        time.sleep(intervalo)
    raise AssertionError("tiempo agotado esperando la condición")


def ultimo_visto():
    """Lector que recuerda el último Resultado publicado (la interfaz hace lo mismo)."""
    memoria = {"r": None}

    def leer(sim):
        nuevo = leer_resultado(sim)
        if nuevo is not None:
            memoria["r"] = nuevo
        return memoria["r"]
    return leer


def arrancar(pasos=None, crear=lambda: 0, orden=None, dt=lambda e: DT, **kw):
    pasos = pasos or {"secuencial": lambda e: e + 1}
    orden = orden or Orden(0, "secuencial", False, 4.0)
    return iniciar_simulador(crear, pasos, dt, orden, **kw)


# ------------------------------------------------------------ funciones puras
def test_calcular_ritmo():
    assert calcular_ritmo(60, DT, 1.0, 1.0) == pytest.approx(1.0)
    assert calcular_ritmo(20, DT, 1.0, 1.0) == pytest.approx(1 / 3)
    assert calcular_ritmo(120, DT, 1.0, 2.0) == pytest.approx(1.0)       # a 2x se piden 120 pasos/s
    assert calcular_ritmo(5, DT, 0.0, 1.0) is None


def test_es_vigente_descarta_otra_generacion():
    r = Resultado(2, 1, 0, 0, 0, "secuencial", None, None, 0.0)
    assert es_vigente(r, 2) is True
    assert es_vigente(r, 3) is False
    assert es_vigente(None, 0) is False


def test_ms_del_modo_solo_si_coincide_el_modo():
    r = Resultado(0, 1, 0, 0, 3, "paralelo", 12.5, None, 0.0)
    assert ms_del_modo(r, "paralelo") == 12.5
    assert ms_del_modo(r, "secuencial") is None
    assert ms_del_modo(None, "paralelo") is None


def test_buzon_el_ultimo_gana():
    q = queue.Queue(maxsize=1)
    for valor in (1, 2, 3):
        publicar_ultimo(q, valor)
    assert leer_ultimo(q) == 3
    assert leer_ultimo(q) is None


# --------------------------------------------------------------- el hilo
def test_publica_el_estado_inicial_de_la_generacion_aunque_este_en_pausa():
    with arrancar(crear=lambda: 100, orden=Orden(0, "secuencial", True, 1.0)) as sim:
        r = esperar(lambda: leer_resultado(sim))
    assert (r.generacion, r.estado, r.estado_inicial, r.pasos, r.error) == (0, 100, 100, 0, None)


def test_cada_paso_aplica_la_funcion_una_vez_y_las_secuencias_crecen():
    leer = ultimo_visto()
    with arrancar() as sim:
        r1 = esperar(lambda: (r := leer(sim)) and r.pasos >= 5 and r)
        r2 = esperar(lambda: (r := leer(sim)) and r.secuencia > r1.secuencia and r)
    assert r1.estado == r1.pasos                      # 0 + un +1 por paso
    assert r2.estado == r2.pasos and r2.pasos > r1.pasos


def test_el_multiplicador_cambia_los_pasos_por_segundo_no_la_duracion_del_paso():
    def pasos_en(multiplicador, segundos=0.8):
        leer = ultimo_visto()
        with arrancar(orden=Orden(0, "secuencial", False, multiplicador)) as sim:
            time.sleep(segundos)
            return leer(sim) and esperar(lambda: leer(sim)).pasos
    lento, rapido = pasos_en(1.0), pasos_en(4.0)
    assert 0.8 * 60 * 0.5 < lento < 0.8 * 60 * 1.6            # ~48 pasos a 1x (con tolerancia)
    assert 2.0 < rapido / lento < 6.0                          # ~4 veces más a 4x


def test_el_paso_usa_el_dt_que_da_el_estado():
    leer = ultimo_visto()
    with arrancar(dt=lambda e: 0.1, orden=Orden(0, "secuencial", False, 1.0)) as sim:
        time.sleep(0.55)
        r = esperar(lambda: leer(sim))
    assert 3 <= r.pasos <= 7                                   # ~5 pasos de 0.1 s


def test_la_pausa_detiene_los_pasos_y_reanudar_los_continua():
    leer = ultimo_visto()
    with arrancar() as sim:
        esperar(lambda: (r := leer(sim)) and r.pasos >= 3)
        enviar_orden(sim, Orden(0, "secuencial", True, 4.0))
        time.sleep(0.15)                                       # deja terminar el paso en curso
        leer(sim)
        congelado = leer(sim).pasos
        time.sleep(0.3)
        assert leer(sim).pasos == congelado
        enviar_orden(sim, Orden(0, "secuencial", False, 4.0))
        esperar(lambda: leer(sim).pasos > congelado)


def test_reiniciar_crea_un_estado_nuevo_y_los_resultados_viejos_quedan_obsoletos():
    leer = ultimo_visto()
    with arrancar() as sim:
        viejo = esperar(lambda: (r := leer(sim)) and r.pasos >= 10 and r)
        enviar_orden(sim, Orden(1, "secuencial", False, 4.0))
        nuevo = esperar(lambda: (r := leer(sim)) and r.generacion == 1 and r)
    assert nuevo.estado_inicial == 0 and nuevo.pasos < viejo.pasos
    assert es_vigente(viejo, 1) is False and es_vigente(nuevo, 1) is True


def test_cambiar_de_modo_continua_el_mismo_estado_sin_reiniciar():
    leer = ultimo_visto()
    pasos = {"a": lambda e: e + 1, "b": lambda e: e + 100}
    with arrancar(pasos=pasos, orden=Orden(0, "a", False, 4.0)) as sim:
        antes = esperar(lambda: (r := leer(sim)) and r.pasos >= 5 and r)
        enviar_orden(sim, Orden(0, "b", False, 4.0))
        despues = esperar(lambda: (r := leer(sim)) and r.modo == "b" and r.pasos > antes.pasos and r)
    assert despues.generacion == 0
    assert despues.estado >= antes.estado + 100                # siguió desde el mismo estado
    assert despues.estado > despues.pasos                      # mezcla de pasos "a" (+1) y "b" (+100)


def test_ms_por_paso_se_mide_con_el_modo_activo():
    leer = ultimo_visto()
    pasos = {"lento": lambda e: (time.sleep(0.02), e + 1)[1], "rapido": lambda e: e + 1}
    with arrancar(pasos=pasos, orden=Orden(0, "lento", False, 4.0)) as sim:
        r = esperar(lambda: (r := leer(sim)) and r.pasos >= 3 and r)
    assert r.modo == "lento" and r.ms_por_paso >= 15.0
    assert ms_del_modo(r, "lento") == r.ms_por_paso and ms_del_modo(r, "rapido") is None


def test_un_paso_lento_no_bloquea_al_hilo_principal():
    """El corazón de la mejora: mientras el motor tarda 0.3 s por paso, leer no espera."""
    leer = ultimo_visto()
    pasos = {"secuencial": lambda e: (time.sleep(0.3), e + 1)[1]}
    with arrancar(pasos=pasos, orden=Orden(0, "secuencial", False, 1.0)) as sim:
        esperar(lambda: leer(sim))                              # llega el estado inicial
        time.sleep(0.1)                                         # el hilo ya está dentro de un paso largo
        t0 = time.perf_counter()
        for _ in range(200):
            leer(sim)
            enviar_orden(sim, Orden(0, "secuencial", False, 1.0))
        gastado = time.perf_counter() - t0
    assert gastado < 0.05, f"el hilo principal esperó {gastado:.3f} s"


def test_la_simulacion_lenta_se_avisa_con_ritmo_y_tiempo_descartado():
    leer = ultimo_visto()
    pasos = {"secuencial": lambda e: (time.sleep(0.05), e + 1)[1]}    # ~20 pasos/s frente a 60 pedidos
    with arrancar(pasos=pasos, orden=Orden(0, "secuencial", False, 1.0), ventana_s=0.3) as sim:
        r = esperar(lambda: (r := leer(sim)) and r.ritmo is not None and r.descartado_total > 0 and r,
                    tiempo_max=8.0)
    assert 0.1 < r.ritmo < 0.7
    assert r.descartado_total > 0


def test_un_error_del_motor_se_publica_y_el_hilo_termina():
    def roto(e):
        raise ValueError("boom")
    with arrancar(pasos={"secuencial": roto}) as sim:
        r = esperar(lambda: (r := leer_resultado(sim)) and r.error and r)
        esperar(lambda: not sim.hilo.is_alive())
    assert r.error == "ValueError: boom"


def test_un_error_al_crear_el_estado_inicial_tambien_se_publica():
    def crear():
        raise RuntimeError("sin estado")
    with arrancar(crear=crear) as sim:
        r = esperar(lambda: (r := leer_resultado(sim)) and r.error and r)
    assert r.error == "RuntimeError: sin estado" and r.estado is None


def test_al_salir_del_with_el_hilo_se_detiene():
    with arrancar() as sim:
        esperar(lambda: leer_resultado(sim))
        assert sim.hilo.is_alive()
    assert not sim.hilo.is_alive()
