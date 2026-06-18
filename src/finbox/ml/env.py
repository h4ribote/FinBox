"""Single-agent RL environment wrapping the FinBox engine (doc 07 7.2).

One designated worker is RL-controlled: its food-purchase quantity comes from
the action; the rest of the economy is scripted. step() advances one full P0..P9
turn with the agent's order injected, and returns (obs, reward, done, info).

The reward is the canonical WORKER reward (doc 07 7.5.1): the consumption-need
term + a per-turn survival bonus + a wealth-growth term + a one-shot death
penalty, with the episode terminating on death (7.5.10). In this supply-chain
slice the sole consumption-recovered need (N_consume, 7.5.1) is `satiety` (food);
the other needs are unmodeled and so are correctly absent from the sum. The
non-satiety learning signal comes from the wealth term, which keeps the reward
from saturating once satiety pins at 100 (doc 07 7.5.9). Coefficients are the
canonical doc 16 §16.15.5 values, read from config (never hardcoded).
"""
from __future__ import annotations
import math

from ..agents.scripted import ProtoOrder
from ..core.enums import OrderType, Side
from ..core.errors import ConservationError
from ..engine.skeleton import SkeletonEngine
from ..init.config import SkeletonConfig
from ..init.genesis import genesis
from .obs import encode


class WorkerEnv:
    QMAX = 5   # max food units an action can buy in a turn

    def __init__(self, config: SkeletonConfig | None = None) -> None:
        self.config = config or SkeletonConfig()
        self.store = None
        self.engine = None
        self.agent = None
        self._prev_nw = 0
        self._cur_total = 0
        self._dead = False

    def reset(self):
        self.store = genesis(self.config)
        self.engine = SkeletonEngine(self.store, self.config)
        self.agent = self.store.agents[0]
        self.store.rl_agents = {self.agent}
        self._prev_nw = self.store.net_worth(self.agent)
        self._cur_total = self.store.ledger.total_supply(self.store.cur)   # conservation anchor (7.8.2)
        self._dead = False
        return encode(self.store, self.agent, self.config)

    def step(self, action: float):
        s, c = self.store, self.config
        # action arrives in [0,1] from the policy's tanh squashing (doc 07 7.6.1); clamp defensively
        qty = int(round(max(0.0, min(1.0, float(action))) * self.QMAX))
        pair = s.pairs[f"{s.food}/{s.cur}"]
        price = max(1, s.last_price[pair.pair_id])
        # P2 VALIDATE clamps the order to what cash can afford; the clamped-away fraction feeds the
        # invalid-action shaping term (doc 07 7.5.10).
        affordable = s.cash(self.agent) // price
        fillable = min(qty, affordable)
        invalid_fraction = (qty - fillable) / qty if qty > 0 else 0.0
        ext = []
        if fillable > 0:
            ext = [ProtoOrder(self.agent, pair, Side.BUY, OrderType.LIMIT, price, fillable)]

        self.engine.run_turn(ext)

        # Conservation is a fatal invariant during training (doc 07 7.8.2): the home currency must be
        # conserved every turn. The ledger enforces double-entry/non-negativity atomically per post;
        # this is the explicit per-step guard the doc mandates.
        if s.ledger.total_supply(s.cur) != self._cur_total:
            raise ConservationError(
                f"currency not conserved at tick {s.tick}: "
                f"{s.ledger.total_supply(s.cur)} != {self._cur_total}")

        died_now = (self.agent in s.deceased) and not self._dead
        self._dead = self.agent in s.deceased

        sat = s.satiety.get(self.agent, 0) / 1000.0          # needs held x1000 (doc 05 5.2), -> 0..100
        nw = s.net_worth(self.agent)
        dW = nw - self._prev_nw
        self._prev_nw = nw

        reward = (c.ml_w_satiety * (sat / 100.0)                       # Σ w_n·need_n/100 (N_consume={satiety})
                  + c.ml_b_alive                                        # survival bonus (7.5.1)
                  + c.ml_w_wealth * math.tanh(dW / c.ml_scale_w)        # wealth growth (7.5.1)
                  - c.ml_w_invalid * invalid_fraction)                  # invalid-action shaping (7.5.10)
        if died_now:
            reward -= c.ml_d_death                                      # one-shot terminal penalty (7.5.1)

        done = self._dead
        info = {"invalid_fraction": invalid_fraction, "delta_wealth": dW, "died": died_now}
        return encode(s, self.agent, c), reward, done, info
