"""Build the initial StateStore for the M5 economy (doc 16 16.12).

M4 supply chain + M5 finance: an investor holds a government coupon bond and
firm equity issued at genesis (the genesis mint point, doc 00 0.10).
"""
from __future__ import annotations

from ..core.enums import AMMInvariant, Cause, Industry, MarketKind, Role, TurnPhase
from ..core.ids import AssetId, EntityId, RegionId
from ..domain import naming, needs
from ..domain.finance import Bond, Equity
from ..domain.margin import AMMPool, LendingPool
from ..domain.production import FirmState, Recipe
from ..ledger import Ledger, LedgerLine
from ..market.types import TradingPair
from ..state import StateStore
from ..state import world
from .config import SkeletonConfig

_LABOR_KINDS = ("farm", "factory", "build")
# labor-kind -> worker Role (doc 00 0.14 / doc 06 6.10.1); roles are authoritative engine state
_LABOR_ROLE = {"farm": Role.FARMER, "factory": Role.FACTORY_WORKER, "build": Role.BUILDER}


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

    # authoritative per-entity roles (doc 00 0.14, doc 06 6.1/6.10.1): workers by labor kind,
    # investors INVESTOR, politicians POLITICIAN. The engine owns this, not the gateway.
    roles: dict = {a: (_LABOR_ROLE[_LABOR_KINDS[i % len(_LABOR_KINDS)]],) for i, a in enumerate(agents)}
    roles.update({inv: (Role.INVESTOR,) for inv in investors})
    roles.update({pol: (Role.POLITICIAN,) for pol in politicians})

    agri, manuf, constr = EntityId.firm(1), EntityId.firm(2), EntityId.firm(3)
    region0 = RegionId.of("ALD", 0)
    firms = {
        agri: FirmState(agri, Industry.AGRICULTURE,
                        Recipe({fert: 1, labor["farm"]: 1}, {food: 1}, region_capped_output=food,
                               recipe_id="agri.food", industry=Industry.AGRICULTURE),
                        capacity=config.capacity_init, expands=True, region_id=region0),
        manuf: FirmState(manuf, Industry.MANUFACTURING,
                         Recipe({labor["factory"]: 1}, {fert: 1},
                                recipe_id="manuf.fertilizer", industry=Industry.MANUFACTURING),
                         capacity=config.capacity_init, expands=True, region_id=region0),
        constr: FirmState(constr, Industry.CONSTRUCTION,
                          Recipe({labor["build"]: 1}, {build: 1},
                                 recipe_id="constr.build", industry=Industry.CONSTRUCTION),
                          capacity=config.capacity_init, expands=True, region_id=region0),
    }

    gov, cb, exch = EntityId.gov("ALD"), EntityId.cb("ALD"), EntityId.exch()

    # financial instruments (doc 15 15.8)
    bond = Bond(asset_id=AssetId.bond_gov("ALD", 1, 1), issuer=gov, currency=cur,
                face=config.bond_face, coupon_bps=config.bond_coupon_bps,
                issue_tick=0, maturity_tick=config.bond_maturity_tick, outstanding=config.bond_qty)
    equities = tuple(
        Equity(asset_id=AssetId.eq_firm(n), firm_id=EntityId.firm(n), par=config.equity_par,
               dividend_policy_bps=config.equity_dividend_bps,
               shares_outstanding=config.equity_shares_per_firm, listed=True)
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
        lines.append(LedgerLine(inv, bond.asset_id, config.bond_qty))           # bond endowment (mint)
        for eq in equities:
            lines.append(LedgerLine(inv, eq.asset_id, config.equity_shares_per_firm))  # equity (mint)
    for pol in politicians:
        lines.append(LedgerLine(pol, cur, config.politician_start_cash))

    # margin facilities (doc 09 信用取引): a lending pool per margin-eligible asset, plus a
    # per-currency insurance fund. The home-currency pool and the insurance buffer are seeded at
    # genesis (mint point, doc 00 0.10); other pools start empty and are funded by suppliers.
    margin_assets = [cur] + [eq.asset_id for eq in equities] + [food, fert, build]
    lending_pools = {str(a): LendingPool(asset=a) for a in margin_assets}
    insf = EntityId.insurance_fund("ALD")
    seed = config.lending_genesis_supply_cur
    if seed > 0 and investors:
        cur_pool = lending_pools[str(cur)]
        lines.append(LedgerLine(EntityId.lending_pool(cur), cur, seed))   # mint pool liquidity
        cur_pool.supplied = seed
        cur_pool.total_shares = seed
        cur_pool.shares[investors[0]] = seed       # the seed lender holds the pool shares
    if config.insurance_genesis_seed > 0:
        lines.append(LedgerLine(insf, cur, config.insurance_genesis_seed))   # first-loss buffer
    ledger.post(0, TurnPhase.INIT, Cause.GENESIS, lines)

    last_price = {gp(food).pair_id: config.food_ref_price,
                  gp(fert).pair_id: config.fertilizer_ref_price,
                  gp(build).pair_id: config.build_ref_price}
    for k in _LABOR_KINDS:
        last_price[lp(labor[k]).pair_id] = config.wage_ref.get(k, config.wage_ref_price)

    # secondary markets for bonds/equities (doc 09 9.2.2, doc 11 11.4.2/11.6.1); marked at
    # issue/par at genesis, then repriced by P4 clearing (NAV mark-to-market, doc 11 11.9.2)
    bond_pair = TradingPair(bond.asset_id, cur, MarketKind.BOND)
    pairs[bond_pair.pair_id] = bond_pair
    last_price[bond_pair.pair_id] = bond.face
    for eq in equities:
        eq_pair = TradingPair(eq.asset_id, cur, MarketKind.EQUITY)
        pairs[eq_pair.pair_id] = eq_pair
        last_price[eq_pair.pair_id] = eq.par

    # AMM pools (doc 09 9.7): passive liquidity for non-labor/non-bond pairs. Opt-in (amm_enabled);
    # reserves are seeded by a genesis mint and quoted as a ladder during P4.
    amm_pools: dict = {}
    if config.amm_enabled:
        def _inv_and_spread(pair: TradingPair):
            if pair.kind is MarketKind.FX:
                return AMMInvariant.CONCENTRATED, config.amm_spread_fx_bps
            if pair.kind is MarketKind.EQUITY:
                return AMMInvariant.CONST_PRODUCT, config.amm_spread_equity_bps
            return AMMInvariant.CONST_PRODUCT, config.amm_spread_comm_bps
        for pid, pair in pairs.items():
            if pair.kind in (MarketKind.LABOR, MarketKind.BOND):
                continue
            inv_kind, spread = _inv_and_spread(pair)
            r_quote = config.amm_genesis_seed
            px = max(1, last_price.get(pid, 1))
            r_base = max(1, r_quote // px)
            amm = AMMPool(pair_id=pid, base=pair.base, quote=pair.quote, invariant=inv_kind,
                          spread_bps=spread, r_base=r_base, r_quote=r_quote,
                          total_shares=r_quote, shares={})
            if investors:
                amm.shares[investors[0]] = r_quote
            amm_pools[pid] = amm
            lines_amm = [LedgerLine(amm.entity_id, pair.base, r_base),
                         LedgerLine(amm.entity_id, cur, r_quote)]
            ledger.post(0, TurnPhase.INIT, Cause.GENESIS, lines_amm)

    store = StateStore(
        ledger=ledger, tick=0, master_seed=config.master_seed,
        cur=cur, food=food, build=build, pairs=pairs,
        agents=agents, agent_labor=agent_labor, roles=roles, firms=firms,
        gov=gov, cb=cb, exch=exch,
        region_cap={food: {region0: config.region_cap_food}},
        last_price=last_price,
        macro={"gdp": 0, "investor_nav": 0},
        investors=investors, bonds=(bond,), equities=equities,
        cb_policy_rate_bps=config.cb_policy_rate_bps,
        paid_in_capital={f: config.firm_start_cash for f in firms},
        lending_pools=lending_pools, amm_pools=amm_pools, insurance={str(cur): insf},
        politicians=politicians,
        policy={"tax_bps": config.consumption_tax_bps, "welfare_bps": 0, "min_wage": 0},
    )
    needs.genesis_needs(store, config)   # initialise agent need states (doc 05 5.2)

    # physical world: 6 x 16 x 96 = 9216 cells, deterministic worldgen (doc 04 4.1/4.7)
    store.cells = world.generate_world(config.master_seed)
    # region_cap[asset_id][region_id] = sum of cell potentials (doc 04 4.3.1); keep the calibrated
    # abstract food cap for the active economy region and add the cell-derived agri.* caps alongside
    for asset, by_region in world.region_caps(store.cells).items():
        store.region_cap.setdefault(asset, {}).update(by_region)
    # residency: agents live in the most-populated cells of the active region (doc 05 5.1)
    home = sorted((c for c in store.cells.values() if c.region_id == region0),
                  key=lambda c: (-c.base_population, str(c.cell_id)))
    for i, a in enumerate(store.agents):
        store.home_cell[a] = home[i % len(home)].cell_id
    naming.assign_names(store, config)   # deterministic display names (doc 16 16.14)
    return store
