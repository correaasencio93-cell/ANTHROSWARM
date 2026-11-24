from dataclasses import dataclass
from enum import Enum


class AntState(Enum):
    EXPLORING = "exploring"
    COLLECTING = "collecting"
    RETURNING = "returning"


@dataclass(frozen=True)
class Ant:
    id: int
    x: float
    y: float
    angle: float
    state: AntState
    has_food: bool
    target_food_id: int | None


@dataclass(frozen=True)
class Food:
    id: int
    x: float
    y: float
    amount: int
    radius: float


@dataclass(frozen=True)
class Nest:
    x: float
    y: float
    radius: float
    food_stored: int


@dataclass(frozen=True)
class Pheromone:
    x: float
    y: float
    intensity: float


@dataclass(frozen=True)
class SimConfig:
    width: int = 800
    height: int = 600
    speed: float = 120.0
    max_turn: float = 0.5
    sense_radius: float = 100.0
    follow_gain: float = 0.5
    pheromone_deposit: float = 1.0
    deposit_interval: int = 3
    evaporation: float = 0.02
    min_intensity: float = 0.05
    max_pheromones: int = 2000
    dt: float = 1 / 60
    seed: int = 42


@dataclass(frozen=True)
class WorldView:
    foods: tuple[Food, ...]
    nest: Nest
    pheromones: tuple[Pheromone, ...]
    config: SimConfig
    tick: int


@dataclass(frozen=True)
class AntResult:
    ant: Ant
    food_claim_id: int | None
    delivered: bool
    new_pheromone: Pheromone | None


@dataclass(frozen=True)
class GameState:
    ants: tuple[Ant, ...]
    foods: tuple[Food, ...]
    nest: Nest
    pheromones: tuple[Pheromone, ...]
    config: SimConfig
    tick: int

