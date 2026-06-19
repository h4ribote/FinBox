"""Physical world: the 4-tier spatial hierarchy and deterministic worldgen (doc 04).

World (1) -> Country (6, 2x3 meta) -> Region (16 per country, 4x4) -> Cell (96 per
region, 12x8) = 9216 cells (doc 04 4.1). Each Cell holds the doc 04 4.2 attributes.
``generate_world`` builds the grid deterministically from the master seed using the
fixed pipeline (terrain -> climate -> resource spots -> population -> ownership ->
infrastructure), each step drawing from its dedicated worldgen subseed (doc 04 4.7).
"""
from __future__ import annotations
from dataclasses import dataclass, field

from ..core.enums import Climate, CountryCode, Terrain
from ..core.ids import CellId, RegionId
from ..core import rng

REGIONS_PER_COUNTRY = 16          # 4x4
CELLS_PER_REGION = 96             # 12x8
REGION_COLS, REGION_ROWS = 4, 4
CELL_COLS, CELL_ROWS = 12, 8
CROPS = ("grain", "vegetable", "livestock", "cotton", "timber", "fish")
MINERALS = ("iron_ore", "copper_ore", "bauxite", "coal", "crude_oil", "rare_earth", "limestone")
# country meta layout (2 cols x 3 rows); row index sets the latitude band (0 hottest..2 coldest)
META = {"ALD": (0, 0), "BOR": (1, 0), "CYR": (0, 1), "DOR": (1, 1), "ESM": (0, 2), "FAR": (1, 2)}
# mineral terrain affinity (doc 04 4.5)
MINERAL_TERRAIN = {
    "iron_ore": {Terrain.MOUNTAIN, Terrain.TUNDRA}, "copper_ore": {Terrain.MOUNTAIN, Terrain.DESERT},
    "bauxite": {Terrain.FOREST}, "coal": {Terrain.MOUNTAIN}, "crude_oil": {Terrain.DESERT, Terrain.COAST},
    "rare_earth": {Terrain.MOUNTAIN, Terrain.DESERT}, "limestone": {Terrain.PLAIN, Terrain.MOUNTAIN},
}


@dataclass(slots=True)
class Cell:
    """The minimal unit of world state (doc 04 4.2, canonical schema doc 15 15.3)."""
    country_code: str
    region_index: int
    x: int
    y: int
    terrain: Terrain
    climate: Climate
    temperature: int            # -30..45
    precipitation: int          # 0..400
    elevation: int              # 0..8000
    fertility: dict             # crop -> 0..1000
    mineral_deposits: dict      # mineral -> {"stock": int, "grade": 0..1000}
    forest_stock: int           # 0..1_000_000
    water: int                  # 0..1000
    base_population: int        # >= 0
    population_capacity: int    # >= 0
    infrastructure: int         # 0..1000
    development_level: int      # 0..1000
    fortification: int          # 0..1000
    pollution: int              # 0..1000
    owner: str | None           # country_code or None (unowned)
    terrain_locked: bool = False

    @property
    def cell_id(self) -> CellId:
        return CellId.of(self.country_code, self.region_index, self.x, self.y)

    @property
    def region_id(self) -> RegionId:
        return RegionId.of(self.country_code, self.region_index)


def _q(generator, lo, hi):
    """Deterministic integer draw in [lo, hi]."""
    return int(generator.integers(lo, hi + 1))


def generate_world(master_seed: int) -> dict:
    """Procedurally generate all 9216 cells deterministically (doc 04 4.7). Returns {CellId: Cell}.

    Each worldgen step uses one dedicated subseed generator (doc 04 4.7); cells are visited in
    the fixed canonical order (country, region_index, x, y) so the result is seed-deterministic.
    """
    T = rng.GENESIS_TICK
    gens = (rng.rng(master_seed, T, rng.STREAM_WORLDGEN_TERRAIN),
            rng.rng(master_seed, T, rng.STREAM_WORLDGEN_CLIMATE),
            rng.rng(master_seed, T, rng.STREAM_WORLDGEN_RESOURCE),
            rng.rng(master_seed, T, rng.STREAM_WORLDGEN_POPDENSITY),
            rng.rng(master_seed, T, rng.STREAM_WORLDGEN_ROLES))
    cells: dict = {}
    for cc in CountryCode:
        lat_row = META[cc.value][1]                        # 0 hottest .. 2 coldest
        for idx in range(REGIONS_PER_COUNTRY):
            for x in range(CELL_COLS):
                for y in range(CELL_ROWS):
                    cells[CellId.of(cc.value, idx, x, y)] = _gen_cell(gens, cc.value, lat_row, idx, x, y)
    return cells


def _gen_cell(gens, cc, lat_row, idx, x, y) -> Cell:
    g, gc, gr, gp, gi = gens
    # (1) terrain + elevation (stream worldgen.terrain)
    elevation = _q(g, 0, 8000)
    region_x, region_y = idx % REGION_COLS, idx // REGION_COLS
    gx, gy = region_x * CELL_COLS + x, region_y * CELL_ROWS + y
    edge = gx == 0 or gy == 0 or gx == REGION_COLS * CELL_COLS - 1 or gy == REGION_ROWS * CELL_ROWS - 1
    roll = _q(g, 0, 99)
    if edge and roll < 22:
        # pure ocean: deep water beyond the coast -- not buildable and unowned (doc 04 4.2/4.7 step 5).
        # Represented as COAST terrain with terrain_locked=True (no OCEAN terrain token, doc 04 4.2.1).
        terrain, terrain_locked = Terrain.COAST, True
    elif edge and roll < 55:
        terrain, terrain_locked = Terrain.COAST, False
    elif elevation > 6000:
        terrain, terrain_locked = Terrain.MOUNTAIN, False
    elif roll < 38:
        terrain, terrain_locked = Terrain.PLAIN, False
    elif roll < 60:
        terrain, terrain_locked = Terrain.FOREST, False
    elif roll < 74:
        terrain, terrain_locked = Terrain.DESERT, False
    elif roll < 86:
        terrain, terrain_locked = Terrain.TUNDRA, False
    else:
        terrain, terrain_locked = Terrain.SWAMP, False

    # (2) climate (stream worldgen.climate): latitude band + elevation
    if elevation > 5000:
        climate = Climate.HIGHLAND
    elif lat_row == 0:
        climate = Climate.TROPICAL if _q(gc, 0, 99) < 70 else Climate.ARID
    elif lat_row == 1:
        climate = Climate.TEMPERATE if _q(gc, 0, 99) < 70 else Climate.CONTINENTAL
    else:
        climate = Climate.POLAR if _q(gc, 0, 99) < 60 else Climate.CONTINENTAL
    base_temp = {Climate.TROPICAL: 28, Climate.ARID: 30, Climate.TEMPERATE: 15,
                 Climate.CONTINENTAL: 8, Climate.POLAR: -10, Climate.HIGHLAND: 5}[climate]
    temperature = max(-30, min(45, base_temp - elevation // 400))
    base_precip = {Climate.TROPICAL: 300, Climate.ARID: 30, Climate.TEMPERATE: 150,
                   Climate.CONTINENTAL: 120, Climate.POLAR: 40, Climate.HIGHLAND: 110}[climate]
    precipitation = max(0, min(400, base_precip + _q(gc, -30, 30)))

    # (3) resource spots (stream worldgen.resource)
    fert_base = {Terrain.PLAIN: 700, Terrain.COAST: 400, Terrain.FOREST: 450, Terrain.SWAMP: 300,
                 Terrain.DESERT: 80, Terrain.TUNDRA: 100, Terrain.MOUNTAIN: 60}[terrain]
    fertility = {}
    for crop in CROPS:
        if crop == "fish":
            fertility[crop] = _q(gr, 300, 1000) if terrain is Terrain.COAST else 0
        elif crop == "timber":
            fertility[crop] = _q(gr, 400, 1000) if terrain is Terrain.FOREST else fert_base // 4
        else:
            fertility[crop] = max(0, min(1000, fert_base + _q(gr, -100, 100)))
    mineral_deposits = {}
    for m in MINERALS:
        if terrain in MINERAL_TERRAIN.get(m, set()) and _q(gr, 0, 99) < 12:   # sparse rich spots
            mineral_deposits[m] = {"stock": _q(gr, 50_000, 500_000), "grade": _q(gr, 300, 1000)}
        else:
            mineral_deposits[m] = {"stock": 0, "grade": 0}
    forest_stock = _q(gr, 400_000, 1_000_000) if terrain is Terrain.FOREST else _q(gr, 0, 50_000)
    water = max(0, min(1000, precipitation * 2 + _q(gr, 0, 200)))

    # (4) population (stream worldgen.popdensity): habitability-weighted
    hab = (1000 - elevation // 8) // 4 + (300 if terrain in (Terrain.PLAIN, Terrain.COAST) else 0) \
        + fertility["grain"] // 4
    population_capacity = max(0, hab * 2)
    base_population = _q(gp, 0, population_capacity) if not terrain_locked else 0

    # (5) ownership: land cells owned by their geographic country; pure ocean is unowned
    owner = None if terrain_locked else cc

    # (6) infrastructure / development / fortification (denser cells more developed)
    dev = min(1000, base_population // 4 + _q(gi, 0, 200))
    infrastructure = min(1000, dev + _q(gi, 0, 150))
    fortification = min(1000, (300 if edge else 0) + _q(gi, 0, 100))

    return Cell(
        country_code=cc, region_index=idx, x=x, y=y, terrain=terrain, climate=climate,
        temperature=temperature, precipitation=precipitation, elevation=elevation,
        fertility=fertility, mineral_deposits=mineral_deposits, forest_stock=forest_stock,
        water=water, base_population=base_population, population_capacity=population_capacity,
        infrastructure=infrastructure, development_level=dev, fortification=fortification,
        pollution=0, owner=owner, terrain_locked=terrain_locked,
    )


def cell_potential(cell: Cell, crop: str) -> int:
    """Per-cell agricultural potential for a crop (doc 04 4.3.1), season/weather factor 1."""
    if cell.terrain_locked:
        return 0                                          # pure ocean produces nothing (doc 04 4.2)
    fert = cell.fertility.get(crop, 0)
    infra_mult = 1000 + cell.infrastructure // 2          # 1.0 .. 1.5 (x1000)
    return fert * (2000 - cell.pollution) // 2000 * infra_mult // 1000


def region_caps(cells: dict) -> dict:
    """Aggregate region_cap[asset_id][region_id] = sum of cell potentials (doc 04 4.3.1).

    Keyed by COMM:agri.<crop> asset-id string and RegionId. Only agricultural crops here;
    mineral caps follow the same sum-of-cell-potential pattern.
    """
    from ..core.ids import AssetId
    caps: dict = {}
    for cell in cells.values():
        rid = cell.region_id
        for crop in ("grain", "vegetable", "livestock", "cotton", "fish"):
            asset = AssetId.comm("agri", crop)
            caps.setdefault(asset, {}).setdefault(rid, 0)
            caps[asset][rid] += cell_potential(cell, crop)
    return caps
