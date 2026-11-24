# engine/ — Motor de procesamiento secuencial y paralelo

Responsable: Jean Pierre. Contratos: Anexo A de Mike (firmas definitivas de `models/` y `logic/`).

El motor ejecuta el **paso 2** de `update`. Recibe `(ants, vista)` y devuelve un `AntResult` por hormiga. Lo hace en un solo proceso o repartiendo el trabajo entre varios workers con `multiprocessing`. Los pasos 1 (`crear_vista`) y 3 (`aplicar_resultados`) son de `logic/`.

```python
def update(state, ejecutor=procesar_hormigas):
    vista      = crear_vista(state)              # 1. logic/
    resultados = ejecutor(state.ants, vista)     # 2. engine/  ← aquí
    return aplicar_resultados(state, resultados) # 3. logic/
```

## Estructura

```
engine/
├── __init__.py        API pública y ESTRATEGIA_PARTICION
├── segmentacion.py    segmentar_hormigas, limites_segmentos
├── workers.py         nucleos_totales, detectar_nucleos, configurar_workers,
│                      inicializar_worker, worker_listo, procesar_segmento
├── ejecutores.py      procesar_secuencial, procesar_paralelo, Motor,
│                      abrir_motor, ejecutor_paralelo, validar_resultados
├── metricas.py        MetricasEjecucion, medir_simulacion, aceleracion, eficiencia
├── benchmark.py       python -m engine.benchmark
└── README.md
tests/test_engine_*.py   pruebas del motor (71)
ejemplos/main_consola.py integración de referencia sin Pygame
```

Dependencias: `engine/` importa `logic/` y `models/`. `logic/` no importa `engine/`, y en `engine/` no hay Pygame.

## Cumplimiento de las reglas de la rúbrica

| Regla | Cómo se cumple en engine/ |
|---|---|
| 1. Estado único inmutable | El motor nunca modifica el `GameState` ni las hormigas: recibe tuplas y devuelve tuplas nuevas. Los datos del motor abierto están en `Motor`, una `@dataclass(frozen=True)`. No hay variables globales mutables (solo constantes). |
| 2. Funciones puras | `segmentar_hormigas`, `procesar_segmento`, `procesar_secuencial` y `validar_resultados` dependen solo de sus argumentos. Los workers solo llaman a `procesar_hormigas`. La medición de tiempo está fuera de `update`. |
| 3. Prohibido el `self` mutable | No hay clases con métodos que cambien atributos. El ciclo de vida del Pool se maneja con un administrador de contexto (`abrir_motor`) y el ejecutor paralelo es una aplicación parcial (`functools.partial`). |
| 4. Transformaciones declarativas | Comprensiones (`tuple(... for ...)`), `chain.from_iterable`, `next(...)`, `reduce` y `starmap`. No hay `append` ni bucles destructivos. |
| Segmentación → mapeo paralelo → sincronización y consolidación | Exactamente esos tres pasos en `procesar_paralelo`, explicados abajo. |

Lo único con efectos es inevitable y queda en el borde: crear y cerrar los procesos (`abrir_motor`), medir el tiempo (`metricas.py`) e imprimir resultados (`benchmark.py`). Ninguno ocurre dentro de la lógica de las hormigas.

## Firmas

| Diseño original | Firma final |
|---|---|
| `detectar_nucleos()` | `() -> int`: núcleos que el proceso puede usar (respeta la afinidad de CPU) |
| — | `nucleos_totales() -> int`: núcleos lógicos de la máquina (dato pedido en la rúbrica) |
| `configurar_workers()` | `(n_workers: int \| None = None) -> int` |
| `segmentar_hormigas()` | `(ants, n_segmentos: int) -> tuple[tuple[Ant, ...], ...]` |
| `procesar_segmento()` | `(segmento, vista: WorldView) -> tuple[AntResult, ...]`; solo llama a `procesar_hormigas` |
| `procesar_secuencial()` | `(ants, vista) -> tuple[AntResult, ...]` |
| `procesar_paralelo()` | `(ants, vista, *, pool, n_segmentos) -> tuple[AntResult, ...]` |
| — | `abrir_motor(n_workers=None, n_segmentos=None, metodo_inicio="spawn")`: administrador de contexto que entrega un `Motor` |
| — | `ejecutor_paralelo(motor: Motor) -> Ejecutor` |

`procesar_secuencial` y `ejecutor_paralelo(motor)` cumplen el tipo `Ejecutor` del Anexo A, así que los dos se pasan directamente a `update(state, ejecutor)`.

## Pipeline paralelo

1. **Segmentación.** `segmentar_hormigas` divide `ants` en un bloque contiguo por worker. Con n hormigas y k workers, cada bloque tiene `n // k` hormigas y los primeros `n % k` bloques tienen una más. El inicio del bloque i es `i * base + min(i, resto)`. Ejemplo: 10 hormigas en 3 bloques dan 4, 3 y 3. Se conserva el orden y nunca hay bloques vacíos.
2. **Mapeo paralelo.** `pool.starmap(procesar_segmento, [(segmento, vista), ...], chunksize=1)`. Cada worker aplica la función pura `procesar_hormigas`, que es una comprensión sobre su bloque. La vista viaja una vez por segmento, no una vez por hormiga.
3. **Sincronización y consolidación.** `starmap` bloquea hasta que terminan todos los workers, así que el pipeline no avanza antes de tiempo. Devuelve las partes en el orden de los segmentos aunque los workers terminen en otro orden. Las partes se concatenan con `chain.from_iterable` y `validar_resultados` comprueba que haya exactamente un resultado por hormiga, en el mismo orden. Si no, lanza `ErrorConsolidacion` en lugar de devolver un estado corrupto.
4. `aplicar_resultados` (de `logic/`) construye el nuevo `GameState` congelado en el proceso principal. Ahí se resuelven la comida disputada y las feromonas y se suma `tick + 1`. Por eso el resultado no depende de cuántos workers haya ni de cuál termine primero.

**Por qué no se rompe la inmutabilidad:** cada worker recibe una *copia serializada* (pickle) de su segmento y de la vista, y devuelve objetos nuevos. Ningún proceso puede modificar el estado del proceso principal. El estado anterior sigue intacto (hay una prueba que lo verifica).

## Administración de los workers

```python
with abrir_motor() as motor:          # crea los workers una sola vez
    paralelo = ejecutor_paralelo(motor)
    state = update(state, paralelo)   # se reutilizan en cada frame
                                      # al salir: se cierran
```

| Momento | Qué pasa |
|---|---|
| Inicialización | Al entrar al `with` se crea el `Pool`. Cada worker ejecuta `inicializar_worker` (ignora Ctrl+C) y `abrir_motor` espera a que todos estén listos, así el arranque no cae sobre el primer frame. |
| Reutilización | El mismo Pool y los mismos procesos sirven para todos los frames. Las pruebas lo verifican comparando los PID. |
| Cierre ordenado | Al salir del `with` sin error: `close()` + `join()`. |
| Cierre por error | Si hay una excepción o Ctrl+C dentro del `with`: `terminate()` + `join()`, que detiene los workers de inmediato. |
| Después de cerrar | Usar el ejecutor lanza `ValueError` (Pool cerrado). |

**Método de inicio:** `spawn` por defecto (`METODO_INICIO_POR_DEFECTO`). Es el único que existe en Windows y el de macOS, así todo el equipo ve el mismo comportamiento. En Linux evita los bloqueos de `fork()` cuando el proceso ya tiene hilos (Pygame los crea). Arrancar los intérpretes cuesta unos 70 ms con 2 workers y se paga una sola vez. Para usar el método del sistema: `abrir_motor(metodo_inicio=None)`.

> **Obligatorio:** con `spawn`, `main.py` debe tener `if __name__ == "__main__": main()`. Sin eso, cada worker vuelve a ejecutar el programa completo.

## Conexión con main.py (para Tamara)

```python
import pygame
from engine import abrir_motor, ejecutor_paralelo, procesar_secuencial
from logic import crear_estado_inicial, update
from models import SimConfig


def main():
    pygame.init()
    pantalla = pygame.display.set_mode((1280, 720))
    reloj = pygame.time.Clock()
    state = crear_estado_inicial(SimConfig(), 3000)

    with abrir_motor() as motor:                  # los workers viven todo el juego
        ejecutores = {"secuencial": procesar_secuencial,
                      "paralelo": ejecutor_paralelo(motor)}
        modo, corriendo = "paralelo", True
        while corriendo:
            eventos = pygame.event.get()
            corriendo = not any(e.type == pygame.QUIT for e in eventos)
            modo = alternar_modo(modo, eventos)   # p.ej. tecla P
            state = update(state, ejecutores[modo])
            dibujar(pantalla, state, modo, reloj.get_fps(), motor.n_workers)
            pygame.display.flip()
            reloj.tick(60)                        # no cambia dt (Anexo A, punto 4)
    pygame.quit()


def alternar_modo(modo, eventos):
    pulsada = any(e.type == pygame.KEYDOWN and e.key == pygame.K_p for e in eventos)
    return ("secuencial" if modo == "paralelo" else "paralelo") if pulsada else modo


if __name__ == "__main__":
    main()
```

Notas:

- Cambiar de modo no reinicia nada: el Pool sigue vivo (y ocioso) mientras se usa el modo secuencial. El cambio es instantáneo y la simulación sigue desde el mismo `state`.
- Nunca se abre un motor por frame: crear el Pool es lo más caro del modo paralelo.
- Para mostrar en pantalla los datos técnicos de la rúbrica: `nucleos_totales()`, `motor.n_workers`, `motor.n_segmentos` y `ESTRATEGIA_PARTICION`.
- La rúbrica pide `update(state, events, ...)`. Si Mike agrega `events` a la firma, el motor no cambia: sigue entrando como `ejecutor`.

Ejemplo ejecutable sin Pygame:

```bash
python -m ejemplos.main_consola --modo paralelo --hormigas 3000 --ticks 100
python -m ejemplos.main_consola --modo secuencial --hormigas 3000 --ticks 100
```

## Pruebas

```bash
python -m pytest tests -q
```

Qué se comprueba:

- **Segmentación:** sobrantes en los primeros segmentos, concatenación igual al original (42 combinaciones de tamaños), sin segmentos vacíos, casos borde y valores inválidos.
- **Contrato del ejecutor:** un `AntResult` por hormiga y en orden con 1, 2, 3 y 4 workers y con más segmentos que workers; lista vacía; `validar_resultados` detecta faltantes y desorden.
- **Equivalencia secuencial == paralelo** (comparación con `==` de dataclasses frozen):
  - 1.000, 3.000 y 5.000 hormigas, frame a frame;
  - 250 frames con comida escasa (varias hormigas reclaman la última unidad), entregas y feromonas, verificando también la conservación de la comida y el tope de feromonas;
  - el mismo resultado con 1, 3 y 4 workers;
  - con `spawn`, para confirmar que el azar `hash((seed, tick, id))` es estable entre procesos.
- **Inmutabilidad:** el estado original queda idéntico después de `update` en paralelo, y `Motor` no se puede modificar.
- **Ciclo de vida:** reutilización del Pool (mismos PID), cierre ordenado, cierre inmediato ante una excepción, uso después de cerrar y parámetros inválidos.

## Benchmark (tabla de la rúbrica)

```bash
python -m engine.benchmark                                   # 1.000, 3.000 y 5.000; 60 frames
python -m engine.benchmark --precalentar 120 --ticks 20 \
       --salida resultados.csv --markdown tabla.md           # con feromonas al tope
python -m engine.benchmark --workers 4
```

Imprime los datos técnicos (núcleos totales, núcleos disponibles, workers, segmentos y estrategia de partición), una fila por modo y la tabla con el formato de la rúbrica. `--markdown` la guarda lista para pegar en el informe. Condiciones equivalentes: mismo `SimConfig`, misma seed, mismo estado inicial y mismo número de frames en los dos modos. Al final compara los estados finales y devuelve código de salida 1 si no son iguales.

Aquí **FPS** son los updates por segundo de la simulación, sin contar el dibujo. En la defensa en vivo también se puede mostrar el FPS real de Pygame (`reloj.get_fps()`), que incluye el renderizado.

### Resultados de referencia

Máquina de prueba: Linux, Python 3.13, **2 núcleos totales**, 2 workers, `spawn`, partición en bloques contiguos equilibrados. Hay que repetir la medición en el hardware del equipo, que es lo que pide la rúbrica. Con más núcleos el speedup debería subir.

Con carga de feromonas (`--precalentar 120 --ticks 20`):

| Cantidad de entidades | Secuencial (1 núcleo) | Paralelo (2 núcleos) | Speedup | Eficiencia | Equivalentes |
|---:|---:|---:|---:|---:|:---:|
| 1.000 | 6,8 FPS | 12,1 FPS | 1,79x | 90 % | sí |
| 3.000 | 0,8 FPS | 1,6 FPS | 1,92x | 96 % | sí |
| 5.000 | 0,4 FPS | 0,8 FPS | 1,96x | 98 % | sí |

Lectura: el paralelismo rinde cuando cada hormiga tiene trabajo pesado (feromonas). Sin feromonas, con 1.000 hormigas no hay ganancia: enviar los datos a los workers y traerlos de vuelta cuesta casi lo mismo que calcular, y `aplicar_resultados` sigue siendo secuencial (ley de Amdahl). Los FPS absolutos son bajos por el costo de `seguir_feromonas` (ver pendientes); la mejora medible al activar el paralelismo, que es lo que evalúa la rúbrica, sí aparece.

## Pendientes para coordinar

- **Mike — costo de `seguir_feromonas`:** con 2.000 feromonas, el costo hormigas × feromonas domina todo. Con 5.000 hormigas un frame tarda más de 1 s incluso en paralelo. Una cuadrícula espacial en `crear_vista`, como propone el Anexo A, lo resolvería sin cambiar ninguna firma ni tocar `engine/`.
- **Mike — `models/` y `logic/` reales:** las carpetas incluidas aquí son una versión provisional escrita siguiendo el Anexo A, solo para probar el motor. Se reemplazan por las de Mike y se vuelve a correr `pytest`.
- **Mike — firma `update(state, events, ...)`:** la rúbrica menciona `events`; el Anexo A todavía no lo tiene.
- **Tamara:** guarda `if __name__ == "__main__"` en `main.py` y el `with abrir_motor()` alrededor del bucle.
