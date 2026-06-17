"""Runnable demo of the FinBox economy: ``python run_demo.py``.

Runs the one-country supply-chain economy (manufacturing -> agriculture, plus
construction supplying capital) and verifies determinism, conservation and
journal replay. Vertical slice of impl-plan milestones M2-M4.
"""
from __future__ import annotations

from .engine import SkeletonEngine, verify_determinism, verify_journal_replay
from .init import SkeletonConfig, genesis
from .state import state_hash


def main(n_turns: int = 24) -> None:
    cfg = SkeletonConfig()
    store = genesis(cfg)
    engine = SkeletonEngine(store, cfg)
    cur_total = store.ledger.total_supply(store.cur)
    food_pair = f"{store.food}/{store.cur}"
    agri = min(store.firms)

    print("FinBox economy: one-country (ALD) supply chain (M2-M4)")
    print(f"  agents={cfg.n_agents}  firms={len(store.firms)}  "
          f"pairs={len(store.pairs)}  food_ref={cfg.food_ref_price}")
    print(f"  genesis CUR total = {cur_total:,} minor (= {cur_total / 1000:,.3f} ALD)")
    print()
    print(f"  {'tick':>4} {'food_px':>7} {'gdp':>8} {'agri_cap':>8} "
          f"{'a1_cash':>9} {'a1_sat':>6} {'gov_cash':>11}  hash[:12]")
    a1 = store.agents[0]
    for _ in range(n_turns):
        engine.run_turn()
        h = state_hash(store)
        print(f"  {store.tick:>4} {store.last_price[food_pair]:>7} {store.macro['gdp']:>8} "
              f"{store.firms[agri].capacity:>8} {store.cash(a1):>9} {store.satiety[a1]:>6} "
              f"{store.cash(store.gov):>11}  {h[:12]}")

    print()
    print(f"  currency conserved: {store.ledger.total_supply(store.cur) == cur_total}")
    print(f"  journal replay matches: {verify_journal_replay(store)}")
    print(f"  deterministic (2 runs identical hashes): {verify_determinism(cfg, n_turns)}")
    print(f"  final state hash: {state_hash(store)}")


if __name__ == "__main__":
    main()
