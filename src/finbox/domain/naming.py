"""Deterministic display-name assignment (doc 16 16.14).

Country/currency/firm/person display names are assigned from curated pools using the
dedicated naming RNG streams (doc 16 16.14.2). Names are flavor only: they are written to
state (and the state hash, doc 16 16.14.3) but never affect logic, which uses canonical IDs.
"""
from __future__ import annotations

from ..core import rng
from ..core.enums import CountryCode

COUNTRY_NAMES = ["Aldoria", "Borealis", "Cyrene", "Doria", "Esmark", "Faros",
                 "Galnia", "Halcyra", "Ionis", "Jorvik", "Kestria", "Lumera"]
CURRENCY_NAMES = ["Aldor", "Boreal", "Cyren", "Doriak", "Esmar", "Faron",
                  "Galn", "Halcy", "Ion", "Jorv", "Kestr", "Lum"]
FIRM_NAMES = ["Helios", "Vertex", "Apex", "Nimbus", "Orion", "Atlas", "Meridian", "Cobalt",
              "Pinnacle", "Solace", "Quanta", "Zenith", "Aurora", "Forge", "Harbor", "Lattice"]
PERSON_GIVEN = ["Hina", "Ren", "Mira", "Kai", "Sora", "Leo", "Yuki", "Noa", "Aria", "Taro"]
PERSON_FAMILY = ["Tanaka", "Vance", "Okafor", "Lindqvist", "Moreau", "Reyes", "Castel", "Novak"]


def assign_names(store, config) -> None:
    """Populate ``store.names`` deterministically from seed-derived naming streams (doc 16 16.14.2)."""
    seed, T = config.master_seed, rng.GENESIS_TICK
    names: dict = {}
    countries = sorted(c.value for c in CountryCode)            # assign by country_code ascending

    gc = rng.rng(seed, T, rng.STREAM_NAMING_COUNTRY)
    order = [int(i) for i in gc.permutation(len(COUNTRY_NAMES))]
    for i, cc in enumerate(countries):
        names[f"COUNTRY:{cc}"] = COUNTRY_NAMES[order[i]]

    gcur = rng.rng(seed, T, rng.STREAM_NAMING_CURRENCY)
    order = [int(i) for i in gcur.permutation(len(CURRENCY_NAMES))]
    for i, cc in enumerate(countries):
        names[f"CUR:{cc}"] = CURRENCY_NAMES[order[i]]

    used: set = set()
    for fid in sorted(store.firms, key=str):                   # genesis firms: rng(seed,-1,naming.firm,firm_id)
        g = rng.rng(seed, T, rng.STREAM_NAMING_FIRM, str(fid))
        base = FIRM_NAMES[int(g.integers(0, len(FIRM_NAMES)))]
        name, k = base, 2
        while name in used:                                    # deterministic numeric-suffix collision fallback
            name, k = f"{base} {k}", k + 1
        used.add(name)
        names[str(fid)] = name

    for a in store.agents:                                     # person names: rng(seed,-1,naming.person,agent_id)
        g = rng.rng(seed, T, rng.STREAM_NAMING_PERSON, str(a))
        given = PERSON_GIVEN[int(g.integers(0, len(PERSON_GIVEN)))]
        family = PERSON_FAMILY[int(g.integers(0, len(PERSON_FAMILY)))]
        names[str(a)] = f"{given} {family}"

    store.names = names
