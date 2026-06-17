"""M4 scenario constants (a minimal slice of doc 16).

One country (ALD), a supply chain: MANUFACTURING (labor.factory -> fertilizer)
feeds AGRICULTURE (fertilizer + labor.farm -> food, region-capped); CONSTRUCTION
(labor.build -> construction_labor) supplies the capital good firms consume to
grow capacity. Agents (split across labor kinds) consume food.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkeletonConfig:
    master_seed: int = 0xF1B0C0DE
    n_agents: int = 6

    # market / fiscal
    fee_rate_bps: int = 5
    consumption_tax_bps: int = 800

    # reference prices (minor units)
    food_ref_price: int = 2400
    fertilizer_ref_price: int = 1500
    build_ref_price: int = 3500
    wage_ref_price: int = 2000          # all labor kinds start here

    # production / capacity (doc 10)
    region_cap_food: int = 60
    capacity_init: int = 4
    capacity_min: int = 1
    capacity_max: int = 50
    depreciation_bps: int = 50          # 0.5%/turn (doc 16 production.depreciation_bps_per_turn)
    expand_g: int = 1                   # capacity gain per construction-labor unit (scaled)
    expand_k: int = 20                  # diminishing-returns scale
    firm_expand_buy: int = 2            # construction labor a firm buys/turn to maintain capacity

    # needs (satiety only) -- doc 05 5.2 / doc 16 16.5
    init_satiety: int = 70
    satiety_decay: int = 6
    satiety_per_food: int = 18
    satiety_buy_threshold: int = 55
    q_labor_per_worker: int = 1

    # genesis endowments (minor units)
    agent_start_cash: int = 50000
    firm_start_cash: int = 300000
    gov_start_cash: int = 100_000_000

    # finance (M5)
    n_investors: int = 1
    investor_start_cash: int = 1_000_000
    bond_face: int = 1000
    bond_coupon_bps: int = 400          # 4%/yr, quarterly coupon
    bond_qty: int = 100
    bond_maturity_tick: int = 47        # ~1 year (year-end)
    equity_shares_per_firm: int = 100
    equity_par: int = 1000
    equity_dividend_bps: int = 200      # 2%/yr, quarterly dividend
    cb_policy_rate_bps: int = 250       # doc 16 fiscal.policy_rate_bps

    # politics / fiscal policy (M6) -- P3 GOVERN aggregation drives these
    n_politicians: int = 3
    politician_start_cash: int = 120000
    tax_lo: int = 0
    tax_hi: int = 3000
    tax_tick: int = 50
    welfare_lo: int = 0
    welfare_hi: int = 10000
    welfare_tick: int = 50
    welfare_base: int = 1000            # minimal-living base; payment = base * welfare_bps/10000
    welfare_threshold: int = 20000      # agents below this cash receive welfare
