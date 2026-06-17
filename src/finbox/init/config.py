"""Walking-skeleton / M3 scenario constants (a minimal slice of doc 16).

One country (ALD), two markets: labor (COMM:labor.unskilled / CUR:ALD) and food
(COMM:good.food / CUR:ALD). Workers supply labor; the firm buys labor and turns
it into food under a regional output cap (doc 04/10); agents consume food.
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
    food_ref_price: int = 2400        # doc 16 16.15.1 good.food
    labor_ref_price: int = 2000       # wage per labor unit (clearing price)

    # production (Leontief, region-capped extraction-style for the slice)
    food_per_labor: int = 3           # 1 labor unit -> this many food
    region_cap_food: int = 30         # max food the region can yield per turn (doc 04)
    firm_food_target: int = 12        # firm refills food inventory toward this
    q_labor_per_worker: int = 1       # labor units each worker supplies per turn (perishable)

    # genesis endowments (minor units)
    agent_start_cash: int = 50000
    firm_start_cash: int = 200000
    gov_start_cash: int = 100_000_000
    initial_firm_food: int = 6

    # needs (satiety only, in this slice) -- doc 05 5.2 / doc 16 16.5
    init_satiety: int = 70
    satiety_decay: int = 6
    satiety_per_food: int = 18
    satiety_buy_threshold: int = 55
