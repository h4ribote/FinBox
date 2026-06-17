"""Single-agent RL environment wrapping the FinBox engine (doc 07 7.2).

One designated worker is RL-controlled: its food-purchase quantity comes from
the action; the rest of the economy is scripted. step() advances one full P0..P9
turn with the agent's order injected, and returns (obs, reward, done, info).
"""
from __future__ import annotations

from ..agents.scripted import ProtoOrder
from ..core.enums import OrderType, Side
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

    def reset(self):
        self.store = genesis(self.config)
        self.engine = SkeletonEngine(self.store, self.config)
        self.agent = self.store.agents[0]
        self.store.rl_agents = {self.agent}
        return encode(self.store, self.agent, self.config)

    def step(self, action: float):
        # action arrives in [0,1] from the policy's tanh squashing (doc 07 7.6.1); clamp defensively
        qty = int(round(max(0.0, min(1.0, float(action))) * self.QMAX))
        ext = []
        if qty > 0 and self.store.cash(self.agent) > 0:
            pair = self.store.pairs[f"{self.store.food}/{self.store.cur}"]
            ext = [ProtoOrder(self.agent, pair, Side.BUY, OrderType.LIMIT,
                              self.store.last_price[pair.pair_id], qty)]
        self.engine.run_turn(ext)
        sat = self.store.satiety[self.agent] / 1000.0   # needs held x1000 (doc 05 5.2)
        reward = sat / 100.0 + 0.01            # needs satisfaction + b_alive (doc 07 7.5.1)
        return encode(self.store, self.agent, self.config), reward, False, {}
