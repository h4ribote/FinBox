"""M8 economic validation: a long scripted run stays consistent and active.

Runs the full economy for 10 years (480 turns) with all roles driven by scripted
policies (workers, firms, politicians, investor), checking that invariants hold
and macro KPIs stay in sane ranges -- the gate before introducing RL (impl M8).
"""
from finbox.engine import SkeletonEngine, verify_journal_replay
from finbox.init import SkeletonConfig, genesis

EPISODE = 480  # 10 years at TURNS_PER_YEAR = 48


def test_ten_year_run_is_stable():
    c = SkeletonConfig()
    s = genesis(c)
    e = SkeletonEngine(s, c)
    cur_total = s.ledger.total_supply(s.cur)
    active = 0
    for _ in range(EPISODE):
        e.run_turn()
        assert s.ledger.total_supply(s.cur) == cur_total                 # money conserved
        assert all(q >= 0 for row in s.ledger.balances().values() for q in row.values())
        assert all(0 <= s.satiety[a] <= 100000 for a in s.agents)        # needs bounded (x1000)
        assert 0 <= s.macro["unemployment_bps"] <= 10000
        assert sum(s.ledger.total_supply(a) for a in s.labor_assets()) == 0  # labor perished
        if s.macro["gdp"] > 0:
            active += 1
    assert active > EPISODE // 2          # market clears in most turns (economy stays alive)
    assert s.macro["cpi"] == 10000        # static-quote scripted slice: no price drift
    assert verify_journal_replay(s)       # entire 10-year journal still reconstructs state


def test_kpis_are_reported():
    c = SkeletonConfig()
    s = genesis(c)
    e = SkeletonEngine(s, c)
    for _ in range(48):
        e.run_turn()
    for key in ("gdp", "cpi", "avg_satiety", "unemployment_bps", "investor_nav", "policy_rate"):
        assert key in s.macro


def test_long_run_is_deterministic():
    def run():
        c = SkeletonConfig()
        s = genesis(c)
        e = SkeletonEngine(s, c)
        return [e._step_hash() for _ in range(120)]
    assert run() == run()


def test_action_log_replay_reconstructs():
    from finbox.engine import record_run, verify_replay
    c = SkeletonConfig()
    action_log, hashes = record_run(c, 60)          # doc 02 2.6.1: per-tick intents captured
    assert len(action_log) == 60
    assert verify_replay(c, action_log, hashes)     # doc 02 2.6.2: re-sim matches per-tick hashes
