"""Production recipes and firm capital state (doc 10)."""
from __future__ import annotations
from dataclasses import dataclass

from ..core.enums import Industry
from ..core.ids import AssetId, EntityId


@dataclass(frozen=True, slots=True)
class Recipe:
    """Leontief recipe: fixed inputs -> fixed outputs per production run (doc 10 10.3)."""
    inputs: dict[AssetId, int]                      # per run (labor + materials)
    outputs: dict[AssetId, int]                     # per run
    region_capped_output: AssetId | None = None     # output bounded by region_cap (extractive)


@dataclass(slots=True)
class FirmState:
    """A firm's industry, recipe and mutable capital stock (doc 10 10.7)."""
    entity: EntityId
    industry: Industry
    recipe: Recipe
    capacity: int                                   # max production runs per turn
    expands: bool = False                           # buys construction labor to grow capacity
