"""Runnable demo of the FinBox walking skeleton: ``python -m finbox.demo``.

Runs the one-country food economy for a number of turns, prints a per-turn
summary, and verifies determinism (two runs -> identical hashes) and journal
replay. This is the "fully working" vertical slice of impl-plan milestone M2.
"""
from __future__ import annotations

from .engine import SkeletonEngine, verify_determinism, verify_journal_replay
from .init import SkeletonConfig, genesis
from .state import state_hash


def main(n_turns: int = 24) -> None:
    cfg = SkeletonConfig()
    store = genesis(cfg)
    engine = SkeletonEngine(store, cfg)
    cur_total = cfg.n_agents * cfg.agent_start_cash + cfg.firm_start_cash + cfg.gov_start_cash

    print("FinBox walking skeleton: one-country (ALD) food economy")
    print(f"  agents={cfg.n_agents}  food_ref={cfg.food_ref_price}  fee={cfg.fee_rate_bps}bps  "
          f"tax={cfg.consumption_tax_bps}bps  wage={cfg.wage_per_turn}")
    print(f"  genesis CUR total = {cur_total:,} minor (= {cur_total / 1000:,.3f} ALD display)")
    print()
    print(f"  {'tick':>4} {'price':>6} {'gdp':>8} {'a1_cash':>9} {'a1_food':>7} "
          f"{'a1_sat':>6} {'firm_cash':>10} {'gov_cash':>11}  hash[:12]")
    a1 = store.agents[0]
    for _ in range(n_turns):
        engine.run_turn()
        h = state_hash(store)
        print(f"  {store.tick:>4} {store.last_price[store.pair.pair_id]:>6} "
              f"{store.macro['gdp']:>8} {store.cash(a1):>9} {store.food_qty(a1):>7} "
              f"{store.satiety[a1]:>6} {store.cash(store.firm):>10} {store.cash(store.gov):>11}  {h[:12]}")

    print()
    print(f"  currency conserved: {store.ledger.total_supply(store.cur) == cur_total}")
    print(f"  journal replay matches: {verify_journal_replay(store)}")
    print(f"  deterministic (2 runs identical hashes): {verify_determinism(cfg, n_turns)}")
    print(f"  final state hash: {state_hash(store)}")


if __name__ == "__main__":
    main()
