"""Production recipes and firm capital state (doc 10)."""
from __future__ import annotations
from dataclasses import dataclass

from ..core.enums import FirmLifecycle, Industry
from ..core.ids import AssetId, EntityId


@dataclass(frozen=True, slots=True)
class Recipe:
    """Leontief recipe: fixed inputs -> fixed outputs per batch (doc 10 10.3, doc 15 15.9)."""
    inputs: dict[AssetId, int]                      # per batch (labor + materials)
    outputs: dict[AssetId, int]                     # per batch
    region_capped_output: AssetId | None = None     # output bounded by region_cap (extractive)
    recipe_id: str = ""                             # unique recipe identifier (doc 15.9)
    industry: Industry | None = None                # target industry (doc 15.9)
    capacity_cost: int = 1                          # capacity units consumed per batch (doc 15.9)
    cell_requirement: dict[AssetId, int] | None = None  # optional per-cell siting requirement (doc 15.9)


@dataclass(slots=True)
class FirmState:
    """A firm's industry, recipe and mutable capital stock (doc 10 10.7/10.8)."""
    entity: EntityId
    industry: Industry
    recipe: Recipe
    capacity: int                                   # max production runs per turn
    expands: bool = False                           # buys construction labor to grow capacity
    region_id: str = ""                             # location region (doc 04 4.1.1, region_cap key)
    state: FirmLifecycle = FirmLifecycle.OPERATING  # lifecycle phase (doc 10 10.8)
