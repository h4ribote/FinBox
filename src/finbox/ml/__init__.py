"""Reinforcement learning: observation/action/reward, PPO, Agent Runtime (doc 07).

A worker's food-purchase decision is controlled by a learned policy on top of the
deterministic engine; the rest of the economy stays scripted. This is the M9
slice: real PPO training and decentralized inference against the FinBox engine.
"""
from .obs import OBS_DIM, encode
from .env import WorkerEnv
from .policy import ActorCritic
from .ppo import train
from .runtime import AgentRuntime

__all__ = ["OBS_DIM", "encode", "WorkerEnv", "ActorCritic", "train", "AgentRuntime"]
