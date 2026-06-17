"""Agent need-state model: x1000 scale, labor minting, multi-food, starvation (doc 05)."""
from finbox.domain import needs
from finbox.engine import SkeletonEngine
from finbox.init import SkeletonConfig, genesis


def test_needs_stored_as_fixed_point_x1000():
    c = SkeletonConfig()
    s = genesis(c)
    assert s.satiety[s.agents[0]] == c.init_satiety * needs.SCALE     # 70 -> 70000
    assert all(0 <= s.satiety[a] <= needs.PCT for a in s.agents)
    assert s.skill[s.agents[0]]                                       # skill initialised


def test_labor_minted_via_skill_stamina_formula():
    c = SkeletonConfig()
    s = genesis(c)
    e = SkeletonEngine(s, c)
    total = needs.mint_labor(s, c)
    # 6 agents, base_units 10, skill 50 -> 10*(0.5+0.5*0.5)=7.5 -> 7 each; >> the old flat 1/worker
    assert total == sum(s.ledger.get(a, s.agent_labor[a]) for a in s.agents)
    assert total >= 6 * 7
    assert s.labored == set(s.agents)


def test_starvation_kills_after_streak_and_conserves_assets():
    c = SkeletonConfig()
    s = genesis(c)
    e = SkeletonEngine(s, c)
    a = s.agents[0]
    cur_total = s.ledger.total_supply(s.cur)
    # starve the agent: no food, satiety pinned to 0 for STARVE_TURNS
    s.satiety[a] = 0
    for _ in range(needs.STARVE_TURNS + 1):
        s.satiety[a] = 0
        s.starve_streak[a] = needs.STARVE_TURNS
        needs._evaluate_deaths(s, c)
        if a in s.deceased:
            break
    assert a in s.deceased
    assert s.ledger.total_supply(s.cur) == cur_total      # inheritance conserves currency


def test_population_survives_full_run_with_welfare():
    c = SkeletonConfig()
    s = genesis(c)
    e = SkeletonEngine(s, c)
    for _ in range(480):
        e.run_turn()
    assert s.macro["population"] == len(s.agents)          # welfare sustains the population
    assert len(s.deceased) == 0
