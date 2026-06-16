"""Walking-skeleton integration: a full P0..P9 economy runs and stays consistent."""
from finbox.engine import SkeletonEngine, run_skeleton
from finbox.init import SkeletonConfig, genesis


def _cur_total(c: SkeletonConfig) -> int:
    return c.n_agents * c.agent_start_cash + c.firm_start_cash + c.gov_start_cash


def test_runs_and_advances_tick():
    store, hashes = run_skeleton(SkeletonConfig(), 96)
    assert store.tick == 96
    assert len(hashes) == 96


def test_currency_conserved_every_turn():
    c = SkeletonConfig()
    store = genesis(c)
    eng = SkeletonEngine(store, c)
    total = _cur_total(c)
    assert store.ledger.total_supply(store.cur) == total
    for _ in range(96):
        eng.run_turn()
        assert store.ledger.total_supply(store.cur) == total  # only genesis mints currency


def test_balances_non_negative_and_satiety_bounded():
    c = SkeletonConfig()
    store = genesis(c)
    eng = SkeletonEngine(store, c)
    for _ in range(96):
        eng.run_turn()
        for row in store.ledger.balances().values():
            assert all(q >= 0 for q in row.values())
        assert all(0 <= store.satiety[a] <= 100 for a in store.agents)
        assert store.ledger.total_supply(store.food) >= 0


def test_economy_is_active():
    c = SkeletonConfig()
    store = genesis(c)
    eng = SkeletonEngine(store, c)
    traded = False
    for _ in range(48):
        eng.run_turn()
        if store.macro["gdp"] > 0:
            traded = True
    assert traded, "expected some food trades to clear"
