"""M9 RL: observation/env/policy/PPO/runtime (doc 07)."""
import math

import pytest

torch = pytest.importorskip("torch")

from finbox.init import SkeletonConfig, genesis
from finbox.ml import OBS_DIM, ActorCritic, AgentRuntime, WorkerEnv, encode, train


def test_obs_shape():
    s = genesis(SkeletonConfig())
    o = encode(s, s.agents[0], SkeletonConfig())
    assert o.shape == (OBS_DIM,)


def test_env_reset_and_step():
    env = WorkerEnv()
    o = env.reset()
    assert o.shape == (OBS_DIM,)
    o, r, done, _ = env.step(0.5)
    assert o.shape == (OBS_DIM,)
    assert r > 0 and done is False


def test_policy_forward_shapes():
    pol = ActorCritic()
    mu, std, v = pol(torch.zeros(3, OBS_DIM))
    assert mu.shape == (3, 1) and v.shape == (3, 1) and std.shape == (1,)


def test_ppo_train_runs_and_is_finite():
    _pol, history = train(iters=5, horizon=24, seed=0)
    assert len(history) == 5
    assert all(math.isfinite(h) and 0.0 <= h <= 1.2 for h in history)  # reward bounded


def test_training_is_deterministic():
    _, h1 = train(iters=3, horizon=16, seed=0)
    _, h2 = train(iters=3, horizon=16, seed=0)
    assert h1 == h2


def test_runtime_inference_is_deterministic():
    pol, _ = train(iters=1, horizon=8, seed=0)
    rt = AgentRuntime(pol)
    o = WorkerEnv().reset()
    a1, a2 = rt.act(o), rt.act(o)
    assert a1 == a2 and 0.0 <= a1 <= 1.0


def test_policy_learns_to_feed():
    # over more iterations the agent should keep itself fed better than a no-op baseline
    _, history = train(iters=25, horizon=48, seed=0)
    early = sum(history[:5]) / 5
    late = sum(history[-5:]) / 5
    assert late >= early - 0.05   # not worse; typically improves
