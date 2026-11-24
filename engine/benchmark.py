"""Benchmark secuencial (1 núcleo) vs paralelo (N núcleos): 1.000, 3.000 y 5.000.

Uso (desde la carpeta raíz del proyecto):
    python -m engine.benchmark
    python -m engine.benchmark --precalentar 120 --ticks 20 --salida resultados.csv
    python -m engine.benchmark --workers 4 --markdown tabla.md

Condiciones equivalentes: mismo SimConfig, misma seed, mismo estado inicial y
mismo número de ticks en ambos modos. Al final se comprueba que el estado final
secuencial sea == al paralelo.
"""
from __future__ import annotations

import argparse
import csv
import platform
import sys
import time
from functools import reduce

from logic import crear_estado_inicial, update
from models import SimConfig

from . import ESTRATEGIA_PARTICION
from .ejecutores import abrir_motor, ejecutor_paralelo, procesar_secuencial
from .metricas import MetricasEjecucion, aceleracion, eficiencia, medir_simulacion
from .workers import configurar_workers, detectar_nucleos, nucleos_totales


def preparar_estado(n: int, config: SimConfig, precalentar: int):
    """Estado inicial común. `precalentar` updates secuenciales previos sirven
    para medir en régimen (con feromonas ya presentes)."""
    return reduce(lambda s, _: update(s, procesar_secuencial), range(precalentar),
                  crear_estado_inicial(config, n))


def comparar(n: int, ticks: int, n_workers: int, config: SimConfig, precalentar: int
             ) -> tuple[MetricasEjecucion, MetricasEjecucion, bool]:
    nucleos = detectar_nucleos()
    inicial = preparar_estado(n, config, precalentar)

    final_s, m_s = medir_simulacion(
        inicial, procesar_secuencial, ticks, modo="secuencial",
        n_workers=1, n_segmentos=1, nucleos_detectados=nucleos)

    t0 = time.perf_counter()
    with abrir_motor(n_workers=n_workers) as motor:
        arranque = time.perf_counter() - t0
        final_p, m_p = medir_simulacion(
            inicial, ejecutor_paralelo(motor), ticks, modo="paralelo",
            n_workers=motor.n_workers, n_segmentos=motor.n_segmentos,
            nucleos_detectados=nucleos, arranque_pool_s=arranque)

    return m_s, m_p, final_s == final_p


def fila(m: MetricasEjecucion) -> str:
    return (f"{m.n_hormigas:>7,} {m.modo:<11} {m.n_workers:>3} "
            f"{m.fps:>8.1f} {m.promedio_ms:>9.2f} {m.mediana_ms:>9.2f} "
            f"{m.p95_ms:>9.2f} {m.feromonas_finales:>6}").replace(",", ".")


def tabla_markdown(resultados, n_workers: int) -> str:
    """La tabla comparativa con el formato de la rúbrica."""
    cab = ("| Cantidad de entidades | Rendimiento secuencial (1 núcleo) | "
           f"Rendimiento paralelo ({n_workers} núcleos) | Speedup |\n|---:|---:|---:|---:|\n")
    filas = "".join(
        f"| {m_s.n_hormigas:,} | {m_s.fps:.1f} FPS | {m_p.fps:.1f} FPS | "
        f"{aceleracion(m_s, m_p):.2f}x |\n".replace(",", ".")
        for m_s, m_p, _ in resultados)
    return cab + filas


def datos_tecnicos(n_workers: int, segmentos: int, metodo: str) -> str:
    return (f"Núcleos totales de la máquina: {nucleos_totales()}\n"
            f"Núcleos disponibles para el proceso: {detectar_nucleos()}\n"
            f"Workers configurados: {n_workers} (método de inicio: {metodo})\n"
            f"Segmentos por frame: {segmentos}\n"
            f"Estrategia de partición: {ESTRATEGIA_PARTICION}\n")


def a_csv(m: MetricasEjecucion, speedup: float, iguales: bool) -> dict:
    return {
        "hormigas": m.n_hormigas, "modo": m.modo, "workers": m.n_workers,
        "segmentos": m.n_segmentos, "nucleos": m.nucleos_detectados,
        "ticks": m.ticks, "fps": round(m.fps, 2), "total_s": round(m.total_s, 4),
        "promedio_ms": round(m.promedio_ms, 3), "mediana_ms": round(m.mediana_ms, 3),
        "p95_ms": round(m.p95_ms, 3),
        "arranque_pool_ms": round(m.arranque_pool_s * 1000, 1),
        "speedup": round(speedup, 3), "equivalentes": iguales,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hormigas", type=int, nargs="+", default=[1000, 3000, 5000])
    p.add_argument("--ticks", type=int, default=60)
    p.add_argument("--workers", type=int, default=None,
                   help="por defecto, todos los núcleos disponibles")
    p.add_argument("--precalentar", type=int, default=0,
                   help="updates secuenciales previos que no se miden")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--salida", help="archivo .csv con todos los datos")
    p.add_argument("--markdown", help="archivo .md con la tabla de la rúbrica")
    a = p.parse_args(argv)

    config = SimConfig(seed=a.seed)
    n_workers = configurar_workers(a.workers)
    print(f"Python {platform.python_version()} | {platform.system()} | "
          f"ticks: {a.ticks} | precalentamiento: {a.precalentar} | seed: {a.seed}")
    print(datos_tecnicos(n_workers, n_workers, "spawn"))
    print(f"{'hormigas':>7} {'modo':<11} {'wk':>3} {'FPS':>8} {'prom ms':>9} "
          f"{'med ms':>9} {'p95 ms':>9} {'fer.':>6}")

    def ejecutar(n: int):
        r = comparar(n, a.ticks, n_workers, config, a.precalentar)
        m_s, m_p, iguales = r
        print(fila(m_s))
        print(fila(m_p))
        print(f"{'':>7} speedup {aceleracion(m_s, m_p):.2f}x | eficiencia "
              f"{eficiencia(m_s, m_p):.0%} | arranque del pool "
              f"{m_p.arranque_pool_s * 1000:.0f} ms | equivalentes: "
              f"{'sí' if iguales else 'NO'}\n")
        return r

    resultados = tuple(ejecutar(n) for n in a.hormigas)
    tabla = tabla_markdown(resultados, n_workers)
    print(tabla)

    if a.salida:
        filas = [a_csv(m, aceleracion(m_s, m_p), ok)
                 for m_s, m_p, ok in resultados for m in (m_s, m_p)]
        with open(a.salida, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0]))
            w.writeheader()
            w.writerows(filas)
        print(f"CSV guardado en {a.salida}")
    if a.markdown:
        with open(a.markdown, "w", encoding="utf-8") as f:
            f.write(datos_tecnicos(n_workers, n_workers, "spawn").replace("\n", "  \n")
                    + "\n" + tabla)
        print(f"Tabla guardada en {a.markdown}")

    return 0 if all(ok for _, _, ok in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
