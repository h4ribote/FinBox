"""Agent Runtime: frozen-policy decentralized inference (doc 07 7.6.5).

Holds a trained policy and maps observations to actions greedily (the tanh-squashed
Gaussian mean), so inference is deterministic given frozen weights (doc 07 7.6.1).
"""
from __future__ import annotations
import torch

from .policy import ActorCritic


class AgentRuntime:
    def __init__(self, policy: ActorCritic) -> None:
        self.policy = policy
        self.policy.eval()

    @torch.no_grad()
    def act(self, obs) -> float:
        mu, _std, _v = self.policy(torch.as_tensor(obs).unsqueeze(0))
        # greedy action = tanh-squashed mean mapped to the [0,1] food-buy fraction (doc 07 7.6.1)
        return float(0.5 * (1.0 + torch.tanh(mu.squeeze())))
