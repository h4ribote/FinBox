"""M4 integration: a multi-firm supply chain runs and stays consistent."""
from finbox.engine import SkeletonEngine, run_skeleton
from finbox.init import SkeletonConfig, genesis


def test_runs_and_advances_tick():
    store, hashes = run_skeleton(SkeletonConfig(), 96)
    assert store.tick == 96
    assert len(hashes) == 96


def test_currency_conserved_every_turn():
    store = genesis(SkeletonConfig())
    eng = SkeletonEngine(store, SkeletonConfig())
    total = store.ledger.total_supply(store.cur)  # genesis mint total
    for _ in range(96):
        eng.run_turn()
        assert store.ledger.total_supply(store.cur) == total  # only genesis mints currency


def test_balances_non_negative_and_satiety_bounded():
    store = genesis(SkeletonConfig())
    eng = SkeletonEngine(store, SkeletonConfig())
    for _ in range(96):
        eng.run_turn()
        for row in store.ledger.balances().values():
            assert all(q >= 0 for q in row.values())
        assert all(0 <= store.satiety[a] <= 100000 for a in store.agents)   # needs held x1000


def test_perishable_labor_fully_expires_each_turn():
    store = genesis(SkeletonConfig())
    eng = SkeletonEngine(store, SkeletonConfig())
    for _ in range(48):
        eng.run_turn()
        assert sum(store.ledger.total_supply(a) for a in store.labor_assets()) == 0


def test_supply_chain_active():
    # food is produced (agriculture), and the intermediate (fertilizer) trades:
    # both require the upstream manufacturing firm, proving the chain connects.
    store = genesis(SkeletonConfig())
    eng = SkeletonEngine(store, SkeletonConfig())
    food = store.food
    produced_food = traded_value = False
    for _ in range(48):
        before = store.ledger.total_supply(food)
        eng.run_turn()
        if store.ledger.total_supply(food) > before:
            produced_food = True
        if store.macro["gdp"] > 0:
            traded_value = True
    assert produced_food and traded_value


def test_capacity_evolves_with_construction_labor():
    c = SkeletonConfig()
    store = genesis(c)
    eng = SkeletonEngine(store, c)
    agri = min(store.firms)  # FIRM:000001
    start_cap = store.firms[agri].capacity
    cap_max = c.capacity_max_for(store.firms[agri].industry)
    for _ in range(48):
        eng.run_turn()
        assert 0 <= store.firms[agri].capacity <= cap_max
    # expanding firm should have grown capacity above its initial value
    assert store.firms[agri].capacity > start_cap
