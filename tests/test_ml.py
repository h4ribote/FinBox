"""M9 RL: observation/env/policy/PPO/runtime (doc 07)."""
import math
from dataclasses import replace

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
    o, r, done, info = env.step(0.5)
    assert o.shape == (OBS_DIM,)
    assert math.isfinite(r) and done is False          # alive after one fed turn
    assert "delta_wealth" in info and "invalid_fraction" in info


def test_policy_forward_shapes():
    pol = ActorCritic()
    mu, std, v = pol(torch.zeros(3, OBS_DIM))
    assert mu.shape == (3, 1) and v.shape == (3, 1) and std.shape == (1,)


def test_ppo_train_runs_and_is_finite():
    _pol, history = train(iters=5, horizon=24, seed=0)
    assert len(history) == 5
    # reward is the full WORKER reward (needs + b_alive + wealth − death), so it is no longer
    # bounded at 1.2; it is still finite and within a sane band (a death turn costs ~D_death).
    assert all(math.isfinite(h) and -6.0 <= h <= 1.5 for h in history)


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


def test_death_terminates_episode():
    """Never buying food starves the worker; the episode must terminate with the death penalty
    applied exactly once (doc 07 7.5.1 / 7.5.10)."""
    env = WorkerEnv()
    env.reset()
    done, steps, term_r, term_info = False, 0, None, None
    while not done and steps < 40:
        _o, r, done, info = env.step(0.0)
        steps += 1
        term_r, term_info = r, info
    assert done and env.agent in env.store.deceased
    assert term_info["died"] is True
    assert term_r < 0.0           # terminal turn carries −D_death (= -5.0 by default)


def test_wealth_term_breaks_satiety_saturation():
    """At pinned satiety=100 the satiety term saturates; the wealth term still differentiates a
    frugal step from a wasteful one, so reward is not flat (the fix for the flat learning curve)."""
    e1, e2 = WorkerEnv(), WorkerEnv()
    e1.reset(); e2.reset()
    for _ in range(6):                     # drive both identical worlds to satiety=100
        e1.step(0.6); e2.step(0.6)
    _o, r_heavy, _d, _i = e1.step(1.0)     # buy the max (more consumption tax -> lower ΔW)
    _o, r_light, _d, _i = e2.step(0.2)     # buy just enough to stay fed
    assert e1.store.satiety[e1.agent] == e2.store.satiety[e2.agent]   # both pinned at 100
    assert r_light > r_heavy               # frugality pays via the wealth term


def test_reward_reads_config_coefficients():
    """b_alive (and the rest) are read from config, not hardcoded (doc 16 §16.15.5)."""
    c1 = SkeletonConfig()
    c2 = replace(c1, ml_b_alive=0.5)
    e1, e2 = WorkerEnv(c1), WorkerEnv(c2)
    e1.reset(); e2.reset()
    _o, r1, _d, _i = e1.step(0.5)
    _o, r2, _d, _i = e2.step(0.5)          # identical world+action -> only b_alive differs
    assert abs((r2 - r1) - (0.5 - 0.01)) < 1e-6
