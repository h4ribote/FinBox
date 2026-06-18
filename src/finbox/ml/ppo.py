"""PPO training loop against the FinBox WorkerEnv (doc 07 7.6).

Clipped-surrogate PPO with GAE. Episodes terminate on agent death (doc 07
7.5.10): the rollout resets the env on `done` and the GAE bootstrap is masked at
the terminal boundary so value does not leak across episodes. The WORKER uses
the short-horizon discount preset (γ=0.99, doc 07 7.5.9). Deterministic for a
fixed seed (the engine has no RNG; only torch sampling does, which manual_seed
fixes). Small by default so it runs as a fast smoke test; scale up for real
training. Coefficients (γ, λ) default to the canonical doc 16 §16.15.5 values.
"""
from __future__ import annotations
import torch

from ..init.config import SkeletonConfig
from .env import WorkerEnv
from .policy import ActorCritic


def _squash_logp(base, raw):
    """log-prob of the tanh-squashed-then-affine action a = 0.5*(1+tanh(raw)) (doc 07 7.6.1).

    Includes the change-of-variables Jacobian for tanh and the 0.5 affine scale to [0,1].
    """
    jac = torch.log(0.5 * (1.0 - torch.tanh(raw) ** 2) + 1e-6)
    return base.log_prob(raw).sum(-1) - jac.sum(-1)


def _to_action(raw):
    """Map an unbounded raw sample to the [0,1] food-buy fraction via tanh squashing (doc 07 7.6.1)."""
    return 0.5 * (1.0 + torch.tanh(raw))


class _RewardNorm:
    """Running reward standardization r' = (r − μ)/σ (doc 07 7.5.9).

    Welford running mean/variance over every reward seen during training; deterministic, so a
    fixed seed reproduces the curve. Centering removes the constant (saturated) satiety offset so
    the wealth term's variation becomes a visible gradient, and it tames the large one-shot death
    penalty into a few standard deviations, stabilizing PPO (doc 07 7.5.9 / 7.8.2).
    """
    __slots__ = ("count", "mean", "m2")

    def __init__(self) -> None:
        self.count = 0.0
        self.mean = 0.0
        self.m2 = 0.0

    def update(self, xs) -> None:
        for x in xs:
            self.count += 1.0
            d = x - self.mean
            self.mean += d / self.count
            self.m2 += d * (x - self.mean)

    @property
    def std(self) -> float:
        return (self.m2 / self.count) ** 0.5 if self.count > 1 else 1.0

    def normalize(self, xs) -> list[float]:
        s = self.std
        return [(x - self.mean) / (s + 1e-8) for x in xs]


def train(iters: int = 8, horizon: int = 32, epochs: int = 4, gamma: float | None = None,
          lam: float | None = None, clip: float = 0.2, lr: float = 3e-3, seed: int = 0,
          config: SkeletonConfig | None = None):
    """Train an ActorCritic; return (policy, mean_reward_per_iteration).

    γ defaults to the WORKER short-horizon preset and λ to the GAE default, both from doc 16 §16.15.5.
    """
    config = config or SkeletonConfig()
    gamma = config.ml_gamma_short if gamma is None else gamma   # WORKER preset γ=0.99 (doc 07 7.5.9)
    lam = config.ml_gae_lambda if lam is None else lam
    torch.manual_seed(seed)
    env = WorkerEnv(config)
    pol = ActorCritic()
    opt = torch.optim.Adam(pol.parameters(), lr=lr)
    rnorm = _RewardNorm()                          # running reward standardization (doc 07 7.5.9)
    history: list[float] = []

    for _ in range(iters):
        obs = env.reset()
        obs_buf, act_buf, rew, val, logp, dones = [], [], [], [], [], []
        for _ in range(horizon):
            ot = torch.as_tensor(obs).unsqueeze(0)
            mu, std, v = pol(ot)
            base = torch.distributions.Normal(mu, std)
            raw = base.sample()                            # unbounded; squashed to [0,1] for the env
            a = _to_action(raw)
            nobs, r, done, _ = env.step(float(a.squeeze()))
            obs_buf.append(ot.squeeze(0))
            act_buf.append(raw.squeeze(0).detach())        # store the pre-squash sample for the update
            rew.append(r)
            val.append(float(v.squeeze().detach()))
            logp.append(float(_squash_logp(base, raw).squeeze().detach()))
            dones.append(done)
            obs = env.reset() if done else nobs            # episode terminates on death (doc 07 7.5.10)
        history.append(sum(rew) / len(rew))        # report the raw mean reward (interpretable curve)
        rnorm.update(rew)
        rew_n = rnorm.normalize(rew)               # standardized rewards drive GAE (doc 07 7.5.9)

        # generalized advantage estimation with terminal masking: on a `done` step the bootstrap
        # value V(s') and the GAE accumulation are both zeroed so value does not leak across the
        # episode boundary (doc 07 7.5.10 / 7.6).
        adv = [0.0] * horizon
        ret = [0.0] * horizon
        gae = 0.0
        next_v = 0.0
        for t in reversed(range(horizon)):
            mask = 0.0 if dones[t] else 1.0
            delta = rew_n[t] + gamma * next_v * mask - val[t]
            gae = delta + gamma * lam * mask * gae
            adv[t] = gae
            ret[t] = gae + val[t]
            next_v = val[t]

        ot_b = torch.stack(obs_buf)
        at_b = torch.stack(act_buf)
        adv_t = torch.tensor(adv, dtype=torch.float32)
        ret_t = torch.tensor(ret, dtype=torch.float32)
        logp_old = torch.tensor(logp, dtype=torch.float32)
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

        for _ in range(epochs):
            mu, std, v = pol(ot_b)
            base = torch.distributions.Normal(mu, std)
            logp_new = _squash_logp(base, at_b)            # at_b are the stored pre-squash samples
            ratio = torch.exp(logp_new - logp_old)
            surr1 = ratio * adv_t
            surr2 = torch.clamp(ratio, 1 - clip, 1 + clip) * adv_t
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = ((v.squeeze(-1) - ret_t) ** 2).mean()
            loss = policy_loss + 0.5 * value_loss - 0.01 * base.entropy().mean()
            opt.zero_grad()
            loss.backward()
            opt.step()

    return pol, history
