"""World & geography: 4-tier hierarchy, deterministic worldgen, region caps (doc 04)."""
from finbox.core.ids import CellId, RegionId
from finbox.init import SkeletonConfig, genesis
from finbox.state import world


def test_worldgen_produces_full_grid():
    cells = world.generate_world(0xF1B0C0DE)
    assert len(cells) == 6 * 16 * 96 == 9216           # doc 04 4.1
    sample = cells[CellId.of("ALD", 5, 7, 3)]
    assert sample.region_index == 5 and sample.x == 7 and sample.y == 3
    assert 0 <= sample.elevation <= 8000
    assert -30 <= sample.temperature <= 45
    assert all(0 <= sample.fertility[c] <= 1000 for c in sample.fertility)


def test_worldgen_is_deterministic():
    a = world.generate_world(123)
    b = world.generate_world(123)
    assert [(str(k), a[k].terrain, a[k].base_population) for k in sorted(a)] == \
           [(str(k), b[k].terrain, b[k].base_population) for k in sorted(b)]


def test_genesis_wires_world_and_region_caps():
    s = genesis(SkeletonConfig())
    assert len(s.cells) == 9216
    assert len(s.home_cell) == len(s.agents)
    # region_cap[agri.grain][region] is the sum of the region's cell potentials (doc 04 4.3.1)
    from finbox.core.ids import AssetId
    grain = AssetId.comm("agri", "grain")
    region0 = RegionId.of("ALD", 0)
    assert s.region_cap_for(grain, region0) > 0
    # cell-sum equals the stored cap
    expect = sum(world.cell_potential(c, "grain") for c in s.cells.values() if c.region_id == region0)
    assert s.region_cap_for(grain, region0) == expect


def test_population_conserved_under_migration():
    c = SkeletonConfig()
    s = genesis(c)
    from finbox.engine import SkeletonEngine
    e = SkeletonEngine(s, c)
    total0 = sum(cell.base_population for cell in s.cells.values())
    for _ in range(30):
        e.run_turn()
    total1 = sum(cell.base_population for cell in s.cells.values())
    assert total1 == total0          # migration moves population without creating/destroying it
