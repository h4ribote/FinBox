"""PPO training loop against the FinBox WorkerEnv (doc 07 7.6).

Clipped-surrogate PPO with GAE. Deterministic for a fixed seed (the engine has
no RNG; only torch sampling does, which manual_seed fixes). Small by default so
it runs as a fast smoke test; scale up for real training.
"""
from __future__ import annotations
import torch

from .env import WorkerEnv
from .policy import ActorCritic


def train(iters: int = 8, horizon: int = 32, epochs: int = 4, gamma: float = 0.99,
          lam: float = 0.95, clip: float = 0.2, lr: float = 3e-3, seed: int = 0):
    """Train an ActorCritic; return (policy, mean_reward_per_iteration)."""
    torch.manual_seed(seed)
    env = WorkerEnv()
    pol = ActorCritic()
    opt = torch.optim.Adam(pol.parameters(), lr=lr)
    history: list[float] = []

    for _ in range(iters):
        obs = env.reset()
        obs_buf, act_buf, rew, val, logp = [], [], [], [], []
        for _ in range(horizon):
            ot = torch.as_tensor(obs).unsqueeze(0)
            mu, std, v = pol(ot)
            dist = torch.distributions.Normal(mu, std)
            a = dist.sample()
            nobs, r, _done, _ = env.step(float(a.squeeze()))
            obs_buf.append(ot.squeeze(0))
            act_buf.append(a.squeeze(0).detach())
            rew.append(r)
            val.append(float(v.squeeze().detach()))
            logp.append(float(dist.log_prob(a).sum().detach()))
            obs = nobs
        history.append(sum(rew) / len(rew))

        # generalized advantage estimation
        adv = [0.0] * horizon
        ret = [0.0] * horizon
        gae = 0.0
        next_v = 0.0
        for t in reversed(range(horizon)):
            delta = rew[t] + gamma * next_v - val[t]
            gae = delta + gamma * lam * gae
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
            dist = torch.distributions.Normal(mu, std)
            logp_new = dist.log_prob(at_b).sum(-1)
            ratio = torch.exp(logp_new - logp_old)
            surr1 = ratio * adv_t
            surr2 = torch.clamp(ratio, 1 - clip, 1 + clip) * adv_t
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = ((v.squeeze(-1) - ret_t) ** 2).mean()
            loss = policy_loss + 0.5 * value_loss - 0.01 * dist.entropy().mean()
            opt.zero_grad()
            loss.backward()
            opt.step()

    return pol, history
