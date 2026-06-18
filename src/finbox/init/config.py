"""M4 scenario constants (a minimal slice of doc 16).

One country (ALD), a supply chain: MANUFACTURING (labor.factory -> fertilizer)
feeds AGRICULTURE (fertilizer + labor.farm -> food, region-capped); CONSTRUCTION
(labor.build -> construction_labor) supplies the capital good firms consume to
grow capacity. Agents (split across labor kinds) consume food.
"""
from __future__ import annotations
from dataclasses import dataclass, field

from ..core.enums import Industry


def _default_capacity_max() -> dict:
    """Per-industry capacity ceilings (doc 10 10.7 capacity_max[industry], doc 16)."""
    return {
        Industry.AGRICULTURE: 50, Industry.MINING: 50, Industry.ENERGY: 80,
        Industry.CONSTRUCTION: 60, Industry.MANUFACTURING: 100, Industry.LOGISTICS: 60,
        Industry.FINANCE: 40, Industry.SERVICES: 60, Industry.RESEARCH: 40,
    }


def _default_wage_ref() -> dict:
    """Per-labor-kind genesis reference wages (doc 16 16.15.1)."""
    return {"unskilled": 12000, "farm": 11000, "mine": 14000, "build": 13000, "factory": 12000,
            "office": 16000, "service": 11000, "engineer": 22000, "health": 20000,
            "research": 22000, "soldier": 13000}


@dataclass(frozen=True, slots=True)
class SkeletonConfig:
    master_seed: int = 0xF1B0C0DE
    n_agents: int = 6

    # market / fiscal. There are NO trading fees and NO price-band / circuit-breaker clamps:
    # both are fully removed from all markets (doc 09 "値幅制限の撤廃", doc 00 0.8/0.20).
    consumption_tax_bps: int = 800
    iceberg_enabled: bool = False        # doc 09 9.4.4
    max_orders_per_turn: int = 256       # doc 13 13.6 (AI/human common)

    # margin trading (信用取引, doc 09 §証拠金 / doc 16 margin.*)
    initial_margin_bps: int = 2000       # 20% => max 5x leverage on new/added positions
    maint_margin_fx_bps: int = 1000      # maintenance margin by class (initial > maintenance)
    maint_margin_comm_bps: int = 1200
    maint_margin_equity_bps: int = 1500
    liquidation_penalty_bps: int = 100   # forced-liq penalty on notional -> insurance fund
    close_factor_bps: int = 5000         # max fraction of a position closed per liq round
    liquidation_max_rounds: int = 4      # cascade cap inside one P4 (deterministic stop)

    # lending pool utilization curve (doc 09 §利用率連動金利 / doc 16 lending.*)
    lending_asset_base_rate_bps: int = 200   # asset-pool base rate (CUR pools track policy_rate)
    lending_slope1_bps: int = 400
    lending_slope2_bps: int = 6000
    lending_u_kink_bps: int = 8000           # 80% kink
    lending_reserve_factor_bps: int = 1000   # 10% interest spread -> insurance fund
    lending_genesis_supply_cur: int = 2_000_000   # genesis seed of the home-currency pool

    # insurance fund (doc 09 §不良債権の吸収 / doc 16 insurance.*)
    insurance_genesis_seed: int = 1_000_000  # genesis first-loss buffer (home currency)

    # AMM (doc 09 9.7 / doc 16 amm.*). Off by default; LP supply opt-in like iceberg.
    amm_enabled: bool = False
    amm_spread_fx_bps: int = 10
    amm_spread_equity_bps: int = 50
    amm_spread_comm_bps: int = 30
    amm_ladder_levels: int = 8
    amm_genesis_seed: int = 1_000_000        # per-pair quote reserve when AMM is enabled
    arb_deviation_threshold_bps: int = 50    # ARBITRAGEUR no-arb band (doc 09 §ARBITRAGEUR)

    # YIELD_INVESTOR reward coefficients (doc 07 §7.5.2 / doc 16 16.15.5); w_impair >> w_income
    w_income_bps: int = 10000
    w_impair_bps: int = 30000
    w_stab_bps: int = 2000
    w_dd_bps: int = 5000

    # role permissions (doc 06 6.5/6.6, doc 13 13.5)
    allow_margin: bool = True            # players/agents may open margin positions
    allow_amm: bool = False              # AMM role is AI-only by default (continuous operation)

    # reference prices (minor units) -- doc 16 16.15.1 canonical genesis reference prices
    food_ref_price: int = 2400
    fertilizer_ref_price: int = 2600    # doc 16 16.15.1 mat.fertilizer
    build_ref_price: int = 4800         # doc 16 16.15.1 build.construction_labor
    wage_ref_price: int = 2000          # flat fallback when a kind is absent from wage_ref
    wage_ref: dict = field(default_factory=_default_wage_ref)   # per-labor genesis wages (doc 16 16.15.1)

    # production / capacity (doc 10)
    region_cap_food: int = 60
    recipe_yield_scale: int = 10        # doc 10 10.3 / doc 16 16.6 (output units per labor run)
    capacity_init: int = 12             # genesis seed firm capacity (>= capacity_min)
    capacity_min: int = 10              # doc 10 10.7/10.8.1 founding capacity
    capacity_max: dict = field(default_factory=_default_capacity_max)   # per-industry (doc 10 10.7)
    depreciation_bps: int = 50          # 0.5%/turn (doc 16 production.depreciation_bps_per_turn)
    expand_g: int = 1                   # capacity gain per construction-labor unit (scaled)
    expand_k: int = 100                 # diminishing-returns scale k_scale (doc 10 10.7)
    firm_expand_buy: int = 2            # construction labor a firm buys/turn (maintenance + growth)
    firm_expand_min_cash: int = 200000  # scripted firms only invest in capacity above this cash buffer
    target_output_stock: int = 30       # scripted-firm output inventory buffer (throttles overproduction)

    def capacity_max_for(self, industry: Industry) -> int:
        return self.capacity_max.get(industry, 50)

    # needs model (doc 05 5.2; values in 0..100 units, held internally x1000) -- doc 16 16.5
    base_units: int = 10                # labor units a worker produces at full skill+stamina (doc 05 5.3)
    init_satiety: int = 70              # genesis value for physiological needs
    satiety_decay: int = 6
    satiety_per_food: int = 18          # good.food unit recovery
    satiety_per_agri_food: int = 6      # agri.* unit recovery (doc 05 5.6)
    satiety_buy_threshold: int = 55     # scripted agent buys food below this (0..100)
    init_skill: int = 50                # genesis skill[k] for an agent's primary labor kind
    genesis_age_years: int = 30         # genesis adult age (working population)
    # base health decay/turn (doc 05 5.2.1 default 1.0, recovered via svc.healthcare/good.medicine).
    # This supply-chain slice has no healthcare producer, so health is non-decaying here (= 0).
    health_decay: int = 0

    # genesis endowments (minor units)
    agent_start_cash: int = 50000
    firm_start_cash: int = 800000       # doc 16 16.9 firm.genesis_initial_cash
    gov_start_cash: int = 100_000_000

    # player onboarding / API (doc 13 13.5, doc 14)
    endowment_basis: str = "WUI"        # doc 16 player.endowment_basis (competitive default)
    allow_entrepreneur: bool = False    # room permits player ENTREPRENEUR role (doc 13 13.5)
    allow_market_maker: bool = False
    allow_public_roles: bool = False    # POLITICIAN/CENTRAL_BANKER/... default AI-only (doc 13)
    jwt_secret: str = "finbox-dev-secret"   # HS256 session-token signing key (doc 14 14.2)
    session_ttl_turns: int = 4          # session token lifetime in turns (doc 14 14.2)

    # finance (M5)
    n_investors: int = 1
    investor_start_cash: int = 1_500_000   # doc 16 16.7.2 INVESTOR genesis endowment (= player.starting_capital)
    bond_face: int = 1000
    bond_coupon_bps: int = 400          # 4%/yr, quarterly coupon
    bond_qty: int = 100
    bond_maturity_tick: int = 47        # ~1 year (year-end)
    equity_shares_per_firm: int = 100000   # doc 16.9 firm.initial_shares
    equity_par: int = 1000
    equity_dividend_bps: int = 200      # profit payout ratio in bps (doc 11 11.6.2 payout_ratio)
    cb_policy_rate_bps: int = 250       # doc 16 fiscal.policy_rate_bps
    discount_rate_gamma: float = 0.997  # RL reward discount (doc 07 7.6 / doc 16 16.15.5)

    # politics / fiscal policy (M6) -- P3 GOVERN aggregation drives these
    n_politicians: int = 3
    politician_start_cash: int = 120000
    tax_lo: int = 0
    tax_hi: int = 3000
    tax_tick: int = 25                  # doc 12 12.3 tax_consumption tick (25 bp grid)
    welfare_lo: int = 0
    welfare_hi: int = 10000
    welfare_tick: int = 50
    welfare_base: int = 6000            # minimal-living base; payment = base * welfare_bps/10000
    welfare_threshold: int = 20000      # agents below this cash receive welfare
