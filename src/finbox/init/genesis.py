"""Build the initial StateStore for the M5 economy (doc 16 16.12).

M4 supply chain + M5 finance: an investor holds a government coupon bond and
firm equity issued at genesis (the genesis mint point, doc 00 0.10).
"""
from __future__ import annotations

from ..core.enums import Cause, Industry, MarketKind, TurnPhase
from ..core.ids import AssetId, EntityId
from ..domain.finance import Bond, Equity
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

    def gp(base: AssetId) -> TradingPair:
        return TradingPair(base, cur, MarketKind.GOODS)

    def lp(base: AssetId) -> TradingPair:
        return TradingPair(base, cur, MarketKind.LABOR)

    pairs_list = [gp(food), gp(fert), gp(build)] + [lp(labor[k]) for k in _LABOR_KINDS]
    pairs = {p.pair_id: p for p in pairs_list}

    agents = tuple(EntityId.agent(i) for i in range(1, config.n_agents + 1))
    agent_labor = {a: labor[_LABOR_KINDS[i % len(_LABOR_KINDS)]] for i, a in enumerate(agents)}
    investors = tuple(EntityId.agent(config.n_agents + 1 + j) for j in range(config.n_investors))
    base = config.n_agents + config.n_investors
    politicians = tuple(EntityId.agent(base + 1 + j) for j in range(config.n_politicians))

    agri, manuf, constr = EntityId.firm(1), EntityId.firm(2), EntityId.firm(3)
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

    gov, cb, exch = EntityId.gov("ALD"), EntityId.cb("ALD"), EntityId.exch()

    # financial instruments
    bond = Bond(AssetId.bond_gov("ALD", 1, 1), gov, config.bond_face,
                config.bond_coupon_bps, config.bond_maturity_tick)
    equities = tuple(
        Equity(AssetId.eq_firm(n), EntityId.firm(n), config.equity_par, config.equity_dividend_bps)
        for n in (1, 2, 3))

    ledger = Ledger()
    lines: list[LedgerLine] = [LedgerLine(a, cur, config.agent_start_cash) for a in agents]
    for f in firms:
        lines.append(LedgerLine(f, cur, config.firm_start_cash))
    lines.append(LedgerLine(gov, cur, config.gov_start_cash))
    lines.append(LedgerLine(agri, food, 6))
    lines.append(LedgerLine(manuf, fert, 4))
    lines.append(LedgerLine(constr, build, 4))
    for inv in investors:
        lines.append(LedgerLine(inv, cur, config.investor_start_cash))
        lines.append(LedgerLine(inv, bond.asset, config.bond_qty))           # bond endowment (mint)
        for eq in equities:
            lines.append(LedgerLine(inv, eq.asset, config.equity_shares_per_firm))  # equity (mint)
    for pol in politicians:
        lines.append(LedgerLine(pol, cur, config.politician_start_cash))
    ledger.post(0, TurnPhase.INIT, Cause.GENESIS, lines)

    last_price = {gp(food).pair_id: config.food_ref_price,
                  gp(fert).pair_id: config.fertilizer_ref_price,
                  gp(build).pair_id: config.build_ref_price}
    for k in _LABOR_KINDS:
        last_price[lp(labor[k]).pair_id] = config.wage_ref_price

    return StateStore(
        ledger=ledger, tick=0, master_seed=config.master_seed,
        cur=cur, food=food, build=build, pairs=pairs,
        agents=agents, agent_labor=agent_labor, firms=firms,
        gov=gov, cb=cb, exch=exch,
        region_cap={food: config.region_cap_food},
        last_price=last_price,
        satiety={a: config.init_satiety for a in agents},
        macro={"gdp": 0, "investor_nav": 0},
        investors=investors, bonds=(bond,), equities=equities,
        cb_policy_rate_bps=config.cb_policy_rate_bps,
        politicians=politicians,
        policy={"tax_bps": config.consumption_tax_bps, "welfare_bps": 0},
    )
