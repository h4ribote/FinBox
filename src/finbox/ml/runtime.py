"""Agent Runtime: frozen-policy decentralized inference (doc 07 7.6.5).

Holds a trained policy and maps observations to actions greedily (the Gaussian
mean, clipped), so inference is deterministic given frozen weights.
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
        return float(torch.clamp(mu.squeeze(), 0.0, 1.0))
