"""Build the initial StateStore (genesis, doc 16 16.12).

Currency and initial inventories are minted via a single GENESIS posting (the
genesis mint point, doc 00 0.10). In the full engine the central bank performs
the mint; this slice mints directly to keep it small.
"""
from __future__ import annotations

from ..core.enums import Cause, MarketKind, TurnPhase
from ..core.ids import AssetId, EntityId
from ..ledger import Ledger, LedgerLine
from ..market.types import TradingPair
from ..state import StateStore
from .config import SkeletonConfig


def genesis(config: SkeletonConfig) -> StateStore:
    cur = AssetId.cur("ALD")
    food = AssetId.comm("good", "food")
    labor = AssetId.comm("labor", "unskilled")
    food_pair = TradingPair(food, cur, MarketKind.GOODS)
    labor_pair = TradingPair(labor, cur, MarketKind.LABOR)

    agents = tuple(EntityId.agent(i) for i in range(1, config.n_agents + 1))
    firm = EntityId.firm(1)
    gov = EntityId.gov("ALD")
    cb = EntityId.cb("ALD")
    exch = EntityId.exch()

    ledger = Ledger()
    lines: list[LedgerLine] = [LedgerLine(a, cur, config.agent_start_cash) for a in agents]
    lines.append(LedgerLine(firm, cur, config.firm_start_cash))
    lines.append(LedgerLine(gov, cur, config.gov_start_cash))
    if config.initial_firm_food > 0:
        lines.append(LedgerLine(firm, food, config.initial_firm_food))
    ledger.post(0, TurnPhase.INIT, Cause.GENESIS, lines)

    return StateStore(
        ledger=ledger,
        tick=0,
        master_seed=config.master_seed,
        cur=cur,
        food=food,
        labor=labor,
        pair=food_pair,
        labor_pair=labor_pair,
        agents=agents,
        firm=firm,
        gov=gov,
        cb=cb,
        exch=exch,
        region_cap={food: config.region_cap_food},
        last_price={food_pair.pair_id: config.food_ref_price,
                    labor_pair.pair_id: config.labor_ref_price},
        satiety={a: config.init_satiety for a in agents},
        macro={"gdp": 0, "food_price": config.food_ref_price, "wage": config.labor_ref_price},
    )
