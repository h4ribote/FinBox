"""Build the initial StateStore for the M4 supply-chain economy (doc 16 16.12)."""
from __future__ import annotations

from ..core.enums import Cause, Industry, MarketKind, TurnPhase
from ..core.ids import AssetId, EntityId
from ..domain.production import FirmState, Recipe
from ..ledger import Ledger, LedgerLine
from ..market.types import TradingPair
from ..state import StateStore
from .config import SkeletonConfig

_LABOR_KINDS = ("farm", "factory", "build")


def genesis(config: SkeletonConfig) -> StateStore:
    cur = AssetId.cur("ALD")
    food = AssetId.comm("good", "food")
    fert = AssetId.comm("mat", "fertilizer")
    build = AssetId.comm("build", "construction_labor")
    labor = {k: AssetId.comm("labor", k) for k in _LABOR_KINDS}

    def goods_pair(base: AssetId) -> TradingPair:
        return TradingPair(base, cur, MarketKind.GOODS)

    def labor_pair(base: AssetId) -> TradingPair:
        return TradingPair(base, cur, MarketKind.LABOR)

    pairs_list = [goods_pair(food), goods_pair(fert), goods_pair(build)]
    pairs_list += [labor_pair(labor[k]) for k in _LABOR_KINDS]
    pairs = {p.pair_id: p for p in pairs_list}

    agents = tuple(EntityId.agent(i) for i in range(1, config.n_agents + 1))
    agent_labor = {a: labor[_LABOR_KINDS[i % len(_LABOR_KINDS)]] for i, a in enumerate(agents)}

    agri = EntityId.firm(1)
    manuf = EntityId.firm(2)
    constr = EntityId.firm(3)
    firms = {
        agri: FirmState(agri, Industry.AGRICULTURE,
                        Recipe({fert: 1, labor["farm"]: 2}, {food: 6}, region_capped_output=food),
                        capacity=config.capacity_init, expands=True),
        manuf: FirmState(manuf, Industry.MANUFACTURING,
                         Recipe({labor["factory"]: 1}, {fert: 4}),
                         capacity=config.capacity_init, expands=True),
        constr: FirmState(constr, Industry.CONSTRUCTION,
                          Recipe({labor["build"]: 1}, {build: 2}),
                          capacity=config.capacity_init, expands=False),
    }

    gov = EntityId.gov("ALD")
    cb = EntityId.cb("ALD")
    exch = EntityId.exch()

    ledger = Ledger()
    lines: list[LedgerLine] = [LedgerLine(a, cur, config.agent_start_cash) for a in agents]
    for f in firms:
        lines.append(LedgerLine(f, cur, config.firm_start_cash))
    lines.append(LedgerLine(gov, cur, config.gov_start_cash))
    # seed inventories so the chain has supply on turn 1
    lines.append(LedgerLine(agri, food, 6))
    lines.append(LedgerLine(manuf, fert, 4))
    lines.append(LedgerLine(constr, build, 4))
    ledger.post(0, TurnPhase.INIT, Cause.GENESIS, lines)

    last_price = {goods_pair(food).pair_id: config.food_ref_price,
                  goods_pair(fert).pair_id: config.fertilizer_ref_price,
                  goods_pair(build).pair_id: config.build_ref_price}
    for k in _LABOR_KINDS:
        last_price[labor_pair(labor[k]).pair_id] = config.wage_ref_price

    return StateStore(
        ledger=ledger, tick=0, master_seed=config.master_seed,
        cur=cur, food=food, build=build, pairs=pairs,
        agents=agents, agent_labor=agent_labor, firms=firms,
        gov=gov, cb=cb, exch=exch,
        region_cap={food: config.region_cap_food},
        last_price=last_price,
        satiety={a: config.init_satiety for a in agents},
        macro={"gdp": 0},
    )
