"""engine/ — motor de procesamiento secuencial y paralelo de ANTHROSWARM.

Depende de logic/ y models/; logic/ no importa engine/ y aquí no se usa Pygame.
"""
from .ejecutores import (
    METODO_INICIO_POR_DEFECTO, Ejecutor, ErrorConsolidacion, Motor, abrir_motor,
    ejecutor_paralelo, procesar_paralelo, procesar_secuencial, validar_resultados,
)
from .metricas import MetricasEjecucion, aceleracion, eficiencia, medir_simulacion
from .segmentacion import limites_segmentos, segmentar_hormigas
from .workers import (
    configurar_workers, detectar_nucleos, inicializar_worker, nucleos_totales,
    procesar_segmento,
)

ESTRATEGIA_PARTICION = (
    "Bloques contiguos equilibrados: un segmento por worker, cada uno con "
    "n // k hormigas y los primeros n % k con una más; se conserva el orden."
)

__all__ = [
    "Ejecutor", "Motor", "abrir_motor", "ejecutor_paralelo",
    "procesar_secuencial", "procesar_paralelo", "validar_resultados",
    "ErrorConsolidacion", "METODO_INICIO_POR_DEFECTO", "ESTRATEGIA_PARTICION",
    "segmentar_hormigas", "limites_segmentos",
    "nucleos_totales", "detectar_nucleos", "configurar_workers",
    "inicializar_worker", "procesar_segmento",
    "MetricasEjecucion", "medir_simulacion", "aceleracion", "eficiencia",
]
