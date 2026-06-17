"""Agent need states, labor production, consumption and lifecycle (doc 05).

Needs are continuous ``0..100`` values held internally as fixed-point at integer
scale ``x1000`` (doc 05 5.2 / glossary 0.20). Only the engine mutates them. The
P6 update order is: (1) decay -> (2) consumption recovery -> (3) interaction /
threshold effects -> (4) clamp (doc 05 5.2). Labor output uses the skill/stamina
formula (doc 05 5.3) with the stress/happiness/health/rest multiplier (5.5.4).
"""
from __future__ import annotations

from ..core.enums import Cause, TurnPhase
from ..core.ids import AssetId
from ..core.rng import STREAM_DEMOGRAPHY, rng
from ..ledger import LedgerLine

SCALE = 1000                      # fixed-point: stored value = pct * 1000
PCT = 100 * SCALE                 # full need (100.0)
TURNS_PER_YEAR = 48

# per labor-kind stamina / rest cost when supplying labor (doc 05 5.3 table)
STAMINA_COST = {"unskilled": 8, "farm": 10, "mine": 14, "build": 13, "factory": 10,
                "office": 6, "service": 7, "engineer": 8, "health": 9, "research": 7, "soldier": 12}
REST_COST = {"unskilled": 6, "farm": 7, "mine": 9, "build": 9, "factory": 7,
             "office": 4, "service": 5, "engineer": 6, "health": 7, "research": 5, "soldier": 9}

# default decay / recovery / threshold coefficients (0..100 units; doc 05 5.2, configurable per doc 16)
STAMINA_BASE_RECOVERY = 30
REST_RECOVERY = 20
STRESS_ACCUM = 3
SATIETY_LOW = 20                  # satiety < 20 -> health penalty (doc 05 5.2.1)
SATIETY_LOW_HEALTH_PENALTY = 4
STARVE_TURNS = 6                  # consecutive satiety==0 turns -> starvation death (doc 05 5.4.1)
HEALTH_CRIT = 10                  # health < 10 -> probabilistic death
P_BASE_HEALTH = 8                 # in pct (0.08)
HEALTH_CRIT_RANGE = 30
DELTA_WORK = 1200                 # skill learning-by-doing (x1000 of 1.2)
DECAY_SKILL = 100                 # skill idle decay (x1000 of 0.1)
AGE_MAX_YEARS = 110
AGE_SCALE = 85
AGE_SHAPE = 7


def _kind(store, agent) -> str:
    return str(store.agent_labor[agent]).split(".")[-1]


def clampn(x: int) -> int:
    return 0 if x < 0 else PCT if x > PCT else x


def genesis_needs(store, config) -> None:
    """Initialise need states for the genesis (adult) population (doc 05 5.4.3)."""
    for a in store.agents:
        store.satiety[a] = config.init_satiety * SCALE
        store.health[a] = PCT
        store.stamina[a] = PCT
        store.rest[a] = PCT
        store.stress[a] = 0
        store.happiness[a] = config.init_satiety * SCALE
        store.starve_streak[a] = 0
        store.age[a] = config.genesis_age_years * TURNS_PER_YEAR
        store.skill[a] = {_kind(store, a): config.init_skill * SCALE}


def _prod_mult(store, a) -> int:
    """Welfare productivity multiplier in x1000 (doc 05 5.5.4)."""
    m = 1000
    if store.stress[a] > 70 * SCALE:
        m = m * 80 // 100
    if store.happiness[a] < 30 * SCALE:
        m = m * 85 // 100
    if store.health[a] < 25 * SCALE:
        m = m * 85 // 100
    if store.rest[a] < 20 * SCALE:
        m = m * 90 // 100
    return m


def mint_labor(store, config) -> int:
    """P1: working agents supply labor; exhausted agents rest and recover (doc 05 5.3/5.5.4).

    Q_labor(k) = floor(base_units * (0.5 + 0.5*skill/100) * stamina_factor * prod_mult), one floor.
    Records which agents laboured (transient, for P6 skill growth). Returns total labor minted.
    """
    base = config.base_units
    labored: set = set()
    lines: list[LedgerLine] = []
    total = 0
    for a in store.agents:
        if a in store.deceased:
            continue
        k = _kind(store, a)
        scost, rcost = STAMINA_COST.get(k, 8), REST_COST.get(k, 6)
        stamina_pct = store.stamina[a] // SCALE
        if stamina_pct >= scost:                          # labor this turn (doc 05 5.3)
            skill_pct = store.skill[a].get(k, 0) // SCALE
            skill_factor = 500 + 500 * skill_pct // 100                    # (0.5 + 0.5*skill/100) x1000
            stamina_factor = min(1000, stamina_pct * 1000 // scost)        # min(1, stamina/cost) x1000
            q = base * skill_factor * stamina_factor * _prod_mult(store, a) // 1_000_000_000  # one floor
            if q > 0:
                lines.append(LedgerLine(a, store.agent_labor[a], q))
                total += q
            labored.add(a)
            store.stamina[a] = clampn(store.stamina[a] - scost * SCALE)
            store.rest[a] = clampn(store.rest[a] - rcost * SCALE)
        else:                                             # rest turn: recover stamina + rest (doc 05 5.2.4)
            store.rest[a] = clampn(store.rest[a] + REST_RECOVERY * SCALE)
            hf = 600 + 400 * (store.health[a] // SCALE) // 100             # 0.6 + 0.4*health/100 (x1000)
            rec = STAMINA_BASE_RECOVERY * (store.rest[a] // SCALE) // 100 * hf // 1000
            store.stamina[a] = clampn(store.stamina[a] + rec * SCALE)
    store.labored = labored
    if lines:
        store.ledger.post(store.tick, TurnPhase.P1, Cause.PRODUCTION, lines)
    return total


def consume(store, config) -> None:
    """P6: update needs (decay -> recovery -> interactions -> clamp), grow skill, evaluate death."""
    agri_foods = [AssetId.comm("agri", n) for n in ("grain", "vegetable", "livestock", "fish")]
    # per-asset satiety recovery, ordered by unit recovery desc then asset_id asc (doc 05 5.6)
    recovery = [(store.food, config.satiety_per_food)] + [(a, config.satiety_per_agri_food) for a in agri_foods]
    recovery.sort(key=lambda t: (-t[1], str(t[0])))
    labored = getattr(store, "labored", set())
    burn: list[LedgerLine] = []
    for a in store.agents:
        if a in store.deceased:
            continue
        store.satiety[a] = store.satiety[a] - config.satiety_decay * SCALE       # (1) decay
        for asset, per in recovery:                                              # (2) multi-food recovery
            deficit = PCT - store.satiety[a]
            if deficit <= 0:
                break
            have = store.ledger.get(a, asset)
            if have <= 0:
                continue
            eat = min(have, (deficit + per * SCALE - 1) // (per * SCALE))
            if eat > 0:
                burn.append(LedgerLine(a, asset, -eat))
                store.satiety[a] += eat * per * SCALE
        store.health[a] = store.health[a] - config.health_decay * SCALE
        if store.satiety[a] < SATIETY_LOW * SCALE:                               # (3) interactions
            store.health[a] -= SATIETY_LOW_HEALTH_PENALTY * SCALE
        store.stress[a] = (store.stress[a] + STRESS_ACCUM * SCALE
                           - (store.health[a] - 50 * SCALE) // 10
                           - (store.rest[a] - 50 * SCALE) // 10)
        hstar = (store.satiety[a] + store.health[a] + store.stamina[a] + store.rest[a]) // 4
        store.happiness[a] = 2 * store.happiness[a] // 5 + 3 * hstar // 5
        store.satiety[a] = clampn(store.satiety[a])                              # (4) clamp
        store.health[a] = clampn(store.health[a])
        store.stress[a] = clampn(store.stress[a])
        store.happiness[a] = clampn(store.happiness[a])
        store.starve_streak[a] = store.starve_streak[a] + 1 if store.satiety[a] == 0 else 0
        k = _kind(store, a)                                                      # skill growth (doc 05 5.3)
        sk = store.skill[a].get(k, 0)
        sk = sk + DELTA_WORK * (PCT - sk) // PCT if a in labored else max(0, sk - DECAY_SKILL)
        store.skill[a][k] = clampn(sk)
        store.age[a] = store.age.get(a, 0) + 1
    if burn:
        store.ledger.post(store.tick, TurnPhase.P6, Cause.CONSUMPTION, burn)
    _evaluate_deaths(store, config)


def _evaluate_deaths(store, config) -> None:
    """Death evaluation in fixed order: starvation -> health -> old age (doc 05 5.4.1)."""
    for a in list(store.agents):
        if a in store.deceased:
            continue
        died = False
        if store.starve_streak[a] >= STARVE_TURNS:                  # starvation (deterministic)
            died = True
        elif store.health[a] < HEALTH_CRIT * SCALE:                 # health (probabilistic)
            r = rng(store.master_seed, store.tick, STREAM_DEMOGRAPHY, str(a), "health")
            p = P_BASE_HEALTH * (HEALTH_CRIT_RANGE * SCALE - store.health[a]) // (HEALTH_CRIT_RANGE * SCALE)
            died = int(r.integers(0, 100)) < p
        else:                                                       # old age (Gompertz, doc 05 5.4.1)
            age_years = store.age.get(a, 0) // TURNS_PER_YEAR
            if age_years >= AGE_MAX_YEARS:
                died = True
            elif age_years > 0:
                r = rng(store.master_seed, store.tick, STREAM_DEMOGRAPHY, str(a), "age")
                haz = (age_years ** AGE_SHAPE) * 1_000_000 // (AGE_SCALE ** AGE_SHAPE) // TURNS_PER_YEAR
                died = int(r.integers(0, 1_000_000)) < haz
        if died:
            _kill(store, a)


def _kill(store, a) -> None:
    """Move the deceased's balances to the government (no-survivor rule) and mark DECEASED (doc 05 5.4.2)."""
    row = store.ledger.balances().get(a, {})
    lines: list[LedgerLine] = []
    for asset, q in row.items():
        if q > 0:
            lines.append(LedgerLine(a, asset, -q))
            lines.append(LedgerLine(store.gov, asset, q))
    if lines:
        store.ledger.post(store.tick, TurnPhase.P6, Cause.FISCAL, lines)
    store.deceased.add(a)
