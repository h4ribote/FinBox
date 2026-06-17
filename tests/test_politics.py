"""M6 politics: P3 aggregation drives taxation and welfare (doc 12)."""
from dataclasses import replace

from finbox.core.enums import Cause
from finbox.engine import SkeletonEngine
from finbox.init import SkeletonConfig, genesis


def test_policy_aggregated_from_politician_proposals():
    s = genesis(SkeletonConfig())
    SkeletonEngine(s, SkeletonConfig()).run_turn()
    # 3 politicians propose tax {700,800,900} -> mean 800; welfare {2000,2500,3000} -> 2500
    assert s.policy["tax_bps"] == 800
    assert s.policy["welfare_bps"] == 2500


def test_welfare_paid_when_agents_qualify():
    c = replace(SkeletonConfig(), welfare_threshold=10 ** 9)  # everyone qualifies
    s = genesis(c)
    SkeletonEngine(s, c).run_turn()
    assert any(p.cause is Cause.SUBSIDY for p in s.ledger.journal)


def test_currency_conserved_with_politics():
    c = replace(SkeletonConfig(), welfare_threshold=10 ** 9)
    s = genesis(c)
    e = SkeletonEngine(s, c)
    total = s.ledger.total_supply(s.cur)
    for _ in range(60):
        e.run_turn()
        assert s.ledger.total_supply(s.cur) == total  # tax + welfare are conserving transfers
