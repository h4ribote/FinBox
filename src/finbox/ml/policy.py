"""Actor-Critic policy network (doc 07 7.7).

A small MLP trunk with a Gaussian action head (1-D, the food-buy fraction) and a
value head. Actions are clipped to [0,1] by the environment; the Gaussian
log-prob is used for PPO.
"""
from __future__ import annotations
import torch
from torch import nn

from .obs import OBS_DIM


class ActorCritic(nn.Module):
    def __init__(self, obs_dim: int = OBS_DIM, hidden: int = 32) -> None:
        super().__init__()
        self.body = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
        )
        self.mu = nn.Linear(hidden, 1)
        self.log_std = nn.Parameter(torch.zeros(1))
        self.value = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor):
        h = self.body(x)
        return self.mu(h), self.log_std.exp(), self.value(h)
