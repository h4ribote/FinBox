"""Deterministic RNG subseed tree (doc 03 3.6).

subseed = SHA-256( length-prefixed encode(master_seed, tick, stream_id, *extra) ),
taking the first 8 bytes as a little-endian uint64. The PRNG is numpy's PCG64
seeded by that subseed. There is no mutable global RNG: every draw is derived
on the spot from (master_seed, tick, stream_id, extra) so iteration order never
affects results (per-entity events pass the entity_id in *extra).
"""
from __future__ import annotations
import hashlib
import struct
from typing import Final

import numpy as np

# Canonical stream ids (doc 03 3.6.2). Worldgen uses tick = GENESIS_TICK.
GENESIS_TICK: Final = -1

STREAM_WEATHER: Final = "weather"
STREAM_DISASTER: Final = "disaster"
STREAM_DEMOGRAPHY: Final = "demography"
STREAM_COMBAT: Final = "combat"
STREAM_NEWS: Final = "news"
STREAM_TIEBREAK: Final = "tiebreak"
STREAM_WORLDGEN_TERRAIN: Final = "worldgen.terrain"
STREAM_WORLDGEN_CLIMATE: Final = "worldgen.climate"
STREAM_WORLDGEN_RESOURCE: Final = "worldgen.resource"
STREAM_WORLDGEN_POPDENSITY: Final = "worldgen.popdensity"
STREAM_WORLDGEN_ROLES: Final = "worldgen.roles"

_U64_MASK = (1 << 64) - 1


def _encode(master_seed: int, tick: int, stream_id: str, extra: tuple[object, ...]) -> bytes:
    """Length-prefixed, self-describing byte encoding (doc 03 3.6.1).

    Type tags prevent ambiguity such as ("AB","C") vs ("A","BC").
    """
    out = bytearray()
    out += struct.pack("<Q", master_seed & _U64_MASK)  # 8B LE uint64
    out += struct.pack("<q", tick)                      # 8B LE int64
    sid = stream_id.encode("ascii")
    out += struct.pack("<H", len(sid)) + sid            # uint16 len + ascii
    for e in extra:
        if isinstance(e, bool):
            tag, b = 2, struct.pack("<q", int(e))
        elif isinstance(e, int):
            tag, b = 1, struct.pack("<q", e)
        else:  # ids / strings
            tag, b = 0, str(e).encode("utf-8")
        out += struct.pack("<B", tag) + struct.pack("<H", len(b)) + b
    return bytes(out)


def subseed(master_seed: int, tick: int, stream_id: str, *extra: object) -> int:
    """Derive a 64-bit subseed (doc 03 3.6.1)."""
    digest = hashlib.sha256(_encode(master_seed, tick, stream_id, extra)).digest()
    return int.from_bytes(digest[:8], "little", signed=False)


def rng(master_seed: int, tick: int, stream_id: str, *extra: object) -> np.random.Generator:
    """A fresh PCG64 generator for one (tick, stream, extra) draw context.

    Use ``.integers(...)`` only; floats must be quantized before touching state.
    """
    return np.random.Generator(np.random.PCG64(subseed(master_seed, tick, stream_id, *extra)))
