
import math


def distancia(x1: float, y1: float, x2: float, y2: float) -> float:
    """
    Calcula la distancia entre dos puntos.
    """
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def normalizar_angulo(angulo: float) -> float:
    """
    Mantiene el ángulo entre -pi y pi.
    """
    return (angulo + math.pi) % (2 * math.pi) - math.pi


def diferencia_angular(objetivo: float, actual: float) -> float:
    """
    Calcula la diferencia angular más corta.
    """
    return normalizar_angulo(objetivo - actual)
