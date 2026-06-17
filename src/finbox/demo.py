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

    print("FinBox economy: one-country (ALD) supply chain + finance (M2-M5)")
    print(f"  agents={cfg.n_agents}  investors={len(store.investors)}  firms={len(store.firms)}  "
          f"pairs={len(store.pairs)}  bonds={len(store.bonds)}  policy_rate={cfg.cb_policy_rate_bps}bps")
    print(f"  genesis CUR total = {cur_total:,} minor (= {cur_total / 1000:,.3f} ALD)")
    print()
    print(f"  {'tick':>4} {'food_px':>7} {'gdp':>8} {'agri_cap':>8} {'cpi':>6} "
          f"{'unemp':>6} {'avgSat':>6} {'tax':>4}  hash[:12]")
    for _ in range(n_turns):
        engine.run_turn()
        m = store.macro
        h = state_hash(store)
        print(f"  {store.tick:>4} {store.last_price[food_pair]:>7} {m['gdp']:>8} "
              f"{store.firms[agri].capacity:>8} {m['cpi']:>6} {m['unemployment_bps']:>6} "
              f"{m['avg_satiety']:>6} {store.policy['tax_bps']:>4}  {h[:12]}")

    print()
    if store.investors:
        inv = store.investors[0]
        print(f"  investor NAV: {store.net_worth(inv):,} (cash {store.cash(inv):,}, "
              f"bonds {sum(store.ledger.get(inv, b.asset) for b in store.bonds)})")
    print(f"  currency conserved: {store.ledger.total_supply(store.cur) == cur_total}")
    print(f"  journal replay matches: {verify_journal_replay(store)}")
    print(f"  deterministic (2 runs identical hashes): {verify_determinism(cfg, n_turns)}")
    print(f"  final state hash: {state_hash(store)}")


if __name__ == "__main__":
    main()
