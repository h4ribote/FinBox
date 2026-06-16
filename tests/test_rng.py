"""Deterministic subseed / RNG tests (doc 03 3.6)."""
from finbox.core import rng


def test_subseed_deterministic():
    a = rng.subseed(12345, 7, rng.STREAM_WEATHER, "CELL:ALD.1.2.3")
    b = rng.subseed(12345, 7, rng.STREAM_WEATHER, "CELL:ALD.1.2.3")
    assert a == b
    assert 0 <= a < (1 << 64)


def test_stream_isolation():
    s = 999
    assert rng.subseed(s, 1, rng.STREAM_WEATHER) != rng.subseed(s, 1, rng.STREAM_COMBAT)
    assert rng.subseed(s, 1, rng.STREAM_DEMOGRAPHY) != rng.subseed(s, 2, rng.STREAM_DEMOGRAPHY)


def test_encoding_no_collision():
    # ("AB","C") must not collide with ("A","BC") thanks to length prefixes
    s = 1
    assert rng.subseed(s, 0, "x", "AB", "C") != rng.subseed(s, 0, "x", "A", "BC")


def test_per_entity_independence():
    s = 7
    a = rng.subseed(s, 5, rng.STREAM_DEMOGRAPHY, "AGENT:000001")
    b = rng.subseed(s, 5, rng.STREAM_DEMOGRAPHY, "AGENT:000002")
    assert a != b


def test_generator_reproducible():
    draws1 = rng.rng(42, 3, rng.STREAM_COMBAT, "CELL:ALD.0.0.0").integers(0, 10000, size=8).tolist()
    draws2 = rng.rng(42, 3, rng.STREAM_COMBAT, "CELL:ALD.0.0.0").integers(0, 10000, size=8).tolist()
    assert draws1 == draws2


def test_genesis_tick():
    assert rng.GENESIS_TICK == -1
    a = rng.subseed(1, rng.GENESIS_TICK, rng.STREAM_WORLDGEN_TERRAIN, "CELL:ALD.0.0.0")
    b = rng.subseed(1, rng.GENESIS_TICK, rng.STREAM_WORLDGEN_TERRAIN, "CELL:ALD.0.0.1")
    assert a != b
