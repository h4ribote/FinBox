"""Canonical serialization / state-hash determinism (doc 02 2.6.2)."""
from finbox.init import SkeletonConfig, genesis
from finbox.state import state_hash


def test_hash_is_deterministic():
    assert state_hash(genesis(SkeletonConfig())) == state_hash(genesis(SkeletonConfig()))


def test_hash_changes_on_state_change():
    base = state_hash(genesis(SkeletonConfig()))

    s = genesis(SkeletonConfig())
    s.tick = 1
    assert state_hash(s) != base

    s = genesis(SkeletonConfig())
    s.satiety[s.agents[0]] += 1
    assert state_hash(s) != base

    s = genesis(SkeletonConfig())
    next(iter(s.firms.values())).capacity += 1   # capacity is serialized state
    assert state_hash(s) != base


def test_hash_is_insertion_order_independent():
    s1 = genesis(SkeletonConfig())
    s2 = genesis(SkeletonConfig())
    # rebuild a dict in reverse insertion order with identical content
    s2.satiety = {a: s2.satiety[a] for a in reversed(s2.agents)}
    assert state_hash(s1) == state_hash(s2)
