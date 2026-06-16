"""Walking-skeleton scenario constants (a minimal slice of doc 16).

A single country (ALD), a single goods market (food / CUR:ALD), N consumer
agents and one producer firm. Values follow the calibrated reference prices
(doc 16 16.15.1) at a small scale so the cash loop is stable for a long run.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkeletonConfig:
    master_seed: int = 0xF1B0C0DE
    n_agents: int = 8

    # market / fiscal
    fee_rate_bps: int = 5            # doc 16 market.fee_rate_bps
    consumption_tax_bps: int = 800   # doc 16 fiscal.consumption_tax_rate_bps (8%)
    food_ref_price: int = 2400       # doc 16 16.15.1 good.food

    # production
    firm_capacity_food: int = 6      # target food inventory the firm refills to each turn

    # P7 cash recycling: firm pays a wage to each agent (closes the agent<->firm loop)
    wage_per_turn: int = 2000

    # genesis endowments (minor units)
    agent_start_cash: int = 50000    # doc 16 16.7.2 labor genesis cash
    firm_start_cash: int = 200000
    gov_start_cash: int = 100_000_000
    initial_firm_food: int = 6

    # needs (satiety only, in this slice) -- doc 05 5.2 / doc 16 16.5
    init_satiety: int = 70
    satiety_decay: int = 6
    satiety_per_food: int = 18
    satiety_buy_threshold: int = 55
