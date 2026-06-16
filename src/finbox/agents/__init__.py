"""Scripted (heuristic) policies that drive the skeleton economy (doc 07 stub).

These are deterministic functions of observable state; they let the economic
engine be validated long before any RL is introduced (impl plan M8).
"""
from .scripted import ProtoOrder, generate_orders

__all__ = ["ProtoOrder", "generate_orders"]
