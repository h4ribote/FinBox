"""Observation encoding for a worker policy (doc 07 7.3).

A fixed-length float vector derived purely from the agent's observable state.
Floats live only in the policy/runtime, never in the engine state (doc 07 7.4.3).
"""
from __future__ import annotations
import numpy as np

OBS_DIM = 5


def encode(store, agent, config) -> np.ndarray:
    food_pid = f"{store.food}/{store.cur}"
    sat = store.satiety.get(agent, 0) / 100.0
    cash = store.cash(agent)
    food = store.food_qty(agent)
    hungry = 1.0 if sat < config.satiety_buy_threshold / 100.0 else 0.0
    return np.array(
        [sat, float(np.log1p(cash)) / 15.0, food / 10.0, hungry, 1.0],
        dtype=np.float32,
    )
