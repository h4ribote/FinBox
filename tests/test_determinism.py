"""Determinism / replay: the walking-skeleton acceptance criterion (doc 02 2.6.2)."""
from finbox.engine import run_hashes, run_skeleton, verify_determinism, verify_journal_replay
from finbox.init import SkeletonConfig


def test_same_config_identical_hashes():
    assert verify_determinism(SkeletonConfig(), 96)


def test_hashes_are_per_tick_and_stable():
    h1 = run_hashes(SkeletonConfig(), 50)
    h2 = run_hashes(SkeletonConfig(), 50)
    assert h1 == h2
    assert len(h1) == 50
    assert len(set(h1)) > 1  # state actually evolves


def test_journal_replay_reconstructs_state():
    store, _ = run_skeleton(SkeletonConfig(), 96)
    assert verify_journal_replay(store)


def test_final_state_matches_across_runs():
    s1, _ = run_skeleton(SkeletonConfig(), 96)
    s2, _ = run_skeleton(SkeletonConfig(), 96)
    assert s1.ledger.balances() == s2.ledger.balances()
    assert s1.satiety == s2.satiety
    assert s1.macro == s2.macro
