"""Canonical serialization / state-hash determinism (doc 02 2.6.2)."""
from finbox.core.enums import Cause, MarketKind, TurnPhase
from finbox.core.ids import AssetId, EntityId
from finbox.ledger import Ledger, LedgerLine
from finbox.market.types import TradingPair
from finbox.state import StateStore, state_hash

CUR = AssetId.cur("ALD")
FOOD = AssetId.comm("good", "food")
LABOR = AssetId.comm("labor", "unskilled")
PAIR = TradingPair(FOOD, CUR, MarketKind.GOODS)
LABOR_PAIR = TradingPair(LABOR, CUR, MarketKind.LABOR)


def make_store(cash=(1000, 2000), satiety=((1, 70), (2, 65)), tick=0):
    led = Ledger()
    lines = [LedgerLine(EntityId.agent(i + 1), CUR, c) for i, c in enumerate(cash)]
    lines.append(LedgerLine(EntityId.firm(1), FOOD, 10))
    led.post(0, TurnPhase.INIT, Cause.GENESIS, lines)
    return StateStore(
        ledger=led, tick=tick, master_seed=123, cur=CUR, food=FOOD, labor=LABOR,
        pair=PAIR, labor_pair=LABOR_PAIR,
        agents=(EntityId.agent(1), EntityId.agent(2)), firm=EntityId.firm(1),
        gov=EntityId.gov("ALD"), cb=EntityId.cb("ALD"), exch=EntityId.exch(),
        region_cap={FOOD: 30},
        last_price={PAIR.pair_id: 2400, LABOR_PAIR.pair_id: 2000},
        satiety={EntityId.agent(n): v for n, v in satiety},
        macro={"gdp": 0},
    )


def test_hash_is_deterministic():
    assert state_hash(make_store()) == state_hash(make_store())


def test_hash_changes_on_state_change():
    base = state_hash(make_store())
    assert state_hash(make_store(tick=1)) != base
    assert state_hash(make_store(cash=(1001, 2000))) != base
    assert state_hash(make_store(satiety=((1, 71), (2, 65)))) != base


def test_hash_is_insertion_order_independent():
    # satiety dict built in reverse insertion order must hash the same (sorted serialization)
    a = make_store(satiety=((1, 70), (2, 65)))
    b = make_store(satiety=((2, 65), (1, 70)))
    assert state_hash(a) == state_hash(b)
