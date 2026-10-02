"""The three models the AgentDB skill picks for this problem, written in PyTorch.

AgentDB itself does not train any of them on numbers (see README.md for the evidence), so this
file follows the skill's recipe step by step with real models:

1. Store experiences {state, action, reward, next_state, done}, with the skill's confidence
   (0.9 when the reward is positive, else 0.5) and success flag (`ExperienceStore`).
2. Train with epochs, batch size, learning rate and a 0.2 validation split. The split is BY VISIT,
   never by row, so a held-out visit is wholly unseen (`split_by_visit`).
3. Evaluate by retrieving the most similar successful experiences and reading off their action and
   confidence (`ExperienceStore.retrieve`, `retrieval_policy`).

The models, chosen from the skill's own guidance:
* Decision Transformer: "recommended" for offline learning from logged data. A small causal
  transformer reads (return-to-go, state, action) triplets within one visit and predicts the
  action. The skill's configuration: context 20, width 128, 8 heads, 6 layers.
* SARSA: "more conservative than Q-learning, better for safety". A Q-network over 36 coarse
  setting cells (rate 4 x Left current 3 x Right current 3). The next action in its target is the
  next logged step's setting in the same visit (on-policy). It only recommends cells that the
  training data delivered at least `min_support` times, and a chosen cell becomes the mean of
  the settings actually delivered in it, so it never proposes an untried setting.
* Actor-Critic: "continuous actions". Offline form: the critic Q(s, a) learns the value of the
  logged next step (SARSA-style target); a value baseline V(s) is fitted to Q; the actor is a
  Gaussian policy trained on the logged settings weighted by exp(advantage / beta)
  (advantage-weighted actor-critic). Skill configuration: actor_lr 0.001, critic_lr 0.002,
  gamma 0.99, entropy_coef 0.01.

Rewards are in pain points (positive = better). A visit's last step has no next step; its value
target is the reward alone (the visit ends there).
"""
from __future__ import annotations

import copy
import math
import time
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

STATE_DIM = 22
ACTION_DIM = 5


def pick_device(prefer: str | None = None) -> torch.device:
    if prefer:
        return torch.device(prefer)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def set_seed(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)


# ==================================================================================================
# Recipe step 1: store experiences
# ==================================================================================================
@dataclass
class Episode:
    visit: str
    states: np.ndarray      # [T, 22]
    actions: np.ndarray     # [T, 5], in [-1, 1]
    rewards: np.ndarray     # [T]
    next_states: np.ndarray  # [T, 22]
    dones: np.ndarray       # [T]

    def __len__(self):
        return len(self.rewards)

    def returns_to_go(self, gamma: float = 1.0) -> np.ndarray:
        out = np.zeros(len(self), dtype=np.float32)
        g = 0.0
        for t in range(len(self) - 1, -1, -1):
            g = self.rewards[t] + gamma * g
            out[t] = g
        return out


class ExperienceStore:
    """The skill's experience store, kept in memory: one record per experience, in file order.

    Each record carries the skill's `confidence` (0.9 if reward > 0 else 0.5) and
    `success_count` (1 if reward > 0). Episodes are visits, split again wherever `done` is set,
    with the order of steps kept."""

    def __init__(self, experiences: list[dict]):
        self.records = []
        for i, e in enumerate(experiences):
            r = float(e["reward"])
            self.records.append({
                "id": i, "visit": e["visit"],
                "state": np.asarray(e["state"], np.float32),
                "action": np.clip(np.asarray(e["action"], np.float32), -1, 1),
                "reward": r,
                "next_state": np.asarray(e["next_state"], np.float32),
                "done": bool(e["done"]),
                "confidence": 0.9 if r > 0 else 0.5,
                "success_count": 1 if r > 0 else 0,
            })

    def __len__(self):
        return len(self.records)

    @property
    def visits(self) -> list[str]:
        seen = []
        for r in self.records:
            if r["visit"] not in seen:
                seen.append(r["visit"])
        return seen

    def subset(self, visits) -> "ExperienceStore":
        keep = set(visits)
        s = ExperienceStore([])
        s.records = [r for r in self.records if r["visit"] in keep]
        return s

    def episodes(self) -> list[Episode]:
        eps, cur = [], []

        def flush():
            if cur:
                eps.append(Episode(cur[0]["visit"],
                                   np.stack([c["state"] for c in cur]),
                                   np.stack([c["action"] for c in cur]),
                                   np.array([c["reward"] for c in cur], np.float32),
                                   np.stack([c["next_state"] for c in cur]),
                                   np.array([c["done"] for c in cur], np.float32)))
        for r in self.records:
            if cur and r["visit"] != cur[-1]["visit"]:
                flush(); cur = []
            cur.append(r)
            if r["done"]:
                flush(); cur = []
        flush()
        return eps

    def transitions(self) -> dict:
        """Flat arrays with the next logged action in the same episode (SARSA's a') and an
        `end` flag (1 where there is no next step: done, or the visit's last step)."""
        S, A, R, S2, A2, END = [], [], [], [], [], []
        for ep in self.episodes():
            T = len(ep)
            for t in range(T):
                S.append(ep.states[t]); A.append(ep.actions[t]); R.append(ep.rewards[t])
                S2.append(ep.next_states[t])
                last = t == T - 1
                A2.append(ep.actions[t + 1] if not last else ep.actions[t])
                END.append(1.0 if (last or ep.dones[t]) else 0.0)
        f = lambda x: np.asarray(x, np.float32)
        return {"s": f(S), "a": f(A), "r": f(R), "s2": f(S2), "a2": f(A2), "end": f(END)}

    # ---- recipe step 3 -----------------------------------------------------------------------
    def retrieve(self, query: np.ndarray, k: int = 10, successful_only: bool = True) -> list[dict]:
        """The k stored experiences whose state is most similar (cosine) to the query.
        AgentDB's default embedding under npx is a hash of the JSON text, which carries no
        numeric similarity; the state vector itself is used here instead."""
        recs = [r for r in self.records if (r["success_count"] if successful_only else True)]
        if not recs:
            return []
        M = np.stack([r["state"] for r in recs])
        q = np.asarray(query, np.float32)
        sim = M @ q / (np.linalg.norm(M, axis=1) * np.linalg.norm(q) + 1e-9)
        order = np.argsort(-sim)[:k]
        return [{**recs[i], "similarity": float(sim[i])} for i in order]


def split_by_visit(store: ExperienceStore, validation_split: float = 0.2, seed: int = 0):
    """The recipe's validationSplit, by visit: (train visits, held-out visits)."""
    visits = list(store.visits)
    rng = np.random.default_rng(seed)
    rng.shuffle(visits)
    n_val = max(1, int(round(validation_split * len(visits))))
    return sorted(visits[n_val:]), sorted(visits[:n_val])


def retrieval_policy(store: ExperienceStore, k: int = 10):
    """Recipe step 3 as a policy: the action of the most similar successful experience.
    Returns (policy, confidence_fn)."""
    def policy(obs):
        out = []
        for o in np.atleast_2d(obs):
            m = store.retrieve(o, k=k)
            out.append(m[0]["action"] if m else np.zeros(ACTION_DIM, np.float32))
        return np.asarray(out, np.float32)

    def confidence(obs):
        return np.array([(store.retrieve(o, k=k) or [{"similarity": np.nan}])[0]["similarity"]
                         for o in np.atleast_2d(obs)])
    return policy, confidence


def mlp(i, o, h=128, n=2):
    layers, d = [], i
    for _ in range(n):
        layers += [nn.Linear(d, h), nn.ReLU()]
        d = h
    layers.append(nn.Linear(d, o))
    return nn.Sequential(*layers)


def _batches(n, batch_size, rng):
    idx = rng.permutation(n)
    for i in range(0, n, batch_size):
        yield idx[i:i + batch_size]


# ==================================================================================================
# Decision Transformer
# ==================================================================================================
class _DTNet(nn.Module):
    def __init__(self, context, embed_dim, n_heads, n_layers, dropout):
        super().__init__()
        self.context = context
        self.emb_r = nn.Linear(1, embed_dim)
        self.emb_s = nn.Linear(STATE_DIM, embed_dim)
        self.emb_a = nn.Linear(ACTION_DIM, embed_dim)
        self.emb_pos = nn.Embedding(context, embed_dim)
        self.emb_type = nn.Embedding(3, embed_dim)
        self.ln = nn.LayerNorm(embed_dim)
        layer = nn.TransformerEncoderLayer(embed_dim, n_heads, 4 * embed_dim, dropout,
                                           batch_first=True, norm_first=True, activation="gelu")
        self.blocks = nn.TransformerEncoder(layer, n_layers, enable_nested_tensor=False)
        self.head = nn.Linear(embed_dim, ACTION_DIM)

    def forward(self, R, S, A):
        """R [B,K,1], S [B,K,22], A [B,K,5] -> predicted actions [B,K,5] (read at state tokens)."""
        B, K, _ = S.shape
        pos = self.emb_pos(torch.arange(K, device=S.device))[None]
        ty = self.emb_type.weight
        toks = torch.stack([self.emb_r(R) + pos + ty[0], self.emb_s(S) + pos + ty[1],
                            self.emb_a(A) + pos + ty[2]], dim=2).reshape(B, 3 * K, -1)
        mask = torch.triu(torch.full((3 * K, 3 * K), float("-inf"), device=S.device), 1)
        h = self.blocks(self.ln(toks), mask=mask)
        h = h.reshape(B, K, 3, -1)[:, :, 1]
        return torch.tanh(self.head(h))


class DecisionTransformerAgent:
    name = "decision_transformer"

    def __init__(self, context=20, embed_dim=128, n_heads=8, n_layers=6, dropout=0.1,
                 target_quantile=0.9, device=None):
        self.cfg = dict(context=context, embed_dim=embed_dim, n_heads=n_heads, n_layers=n_layers,
                        dropout=dropout, target_quantile=target_quantile)
        self.device = pick_device(device)
        self.net = _DTNet(context, embed_dim, n_heads, n_layers, dropout).to(self.device)
        self.rtg_scale = 1.0
        self.target_rtg = 0.0

    def _windows(self, episodes, items):
        """items: list of (episode index, end step, length). Left-aligned, zero-padded."""
        K = self.cfg["context"]
        B = len(items)
        R = np.zeros((B, K, 1), np.float32); S = np.zeros((B, K, STATE_DIM), np.float32)
        A = np.zeros((B, K, ACTION_DIM), np.float32); M = np.zeros((B, K), np.float32)
        for b, (e, t, L) in enumerate(items):
            ep, rtg = episodes[e]
            s0 = t - L + 1
            R[b, :L, 0] = rtg[s0:t + 1] / self.rtg_scale
            S[b, :L] = ep.states[s0:t + 1]; A[b, :L] = ep.actions[s0:t + 1]; M[b, :L] = 1
        d = self.device
        return (torch.tensor(R, device=d), torch.tensor(S, device=d), torch.tensor(A, device=d),
                torch.tensor(M, device=d))

    def _loss(self, episodes, items):
        R, S, A, M = self._windows(episodes, items)
        pred = self.net(R, S, A)
        err = ((pred - A) ** 2).mean(-1)
        return (err * M).sum() / M.sum()

    def _eval_items(self, episodes):
        K = self.cfg["context"]
        return [(e, t, min(K, t + 1)) for e, (ep, _) in enumerate(episodes) for t in range(len(ep))]

    def eval_loss(self, store: ExperienceStore) -> float:
        eps = [(ep, ep.returns_to_go()) for ep in store.episodes()]
        items = self._eval_items(eps)
        if not items:
            return float("nan")
        self.net.eval()
        with torch.no_grad():
            tot = 0.0
            for i in range(0, len(items), 256):
                ch = items[i:i + 256]
                tot += float(self._loss(eps, ch)) * len(ch)
        return tot / len(items)

    def fit(self, train: ExperienceStore, *, epochs=100, batch_size=64, learning_rate=1e-3,
            seed=0, val: ExperienceStore | None = None) -> dict:
        rng = np.random.default_rng(seed)
        eps = [(ep, ep.returns_to_go()) for ep in train.episodes()]
        all_rtg = np.concatenate([r for _, r in eps])
        self.rtg_scale = float(max(1.0, np.abs(all_rtg).max()))
        self.target_rtg = float(np.quantile(all_rtg, self.cfg["target_quantile"]))
        K = self.cfg["context"]
        flat = [(e, t) for e, (ep, _) in enumerate(eps) for t in range(len(ep))]
        opt = torch.optim.AdamW(self.net.parameters(), lr=learning_rate, weight_decay=1e-4)
        hist = []
        t0 = time.time()
        for _ in range(epochs):
            self.net.train()
            tot, n = 0.0, 0
            for b in _batches(len(flat), batch_size, rng):
                items = []
                for j in b:
                    e, t = flat[j]
                    items.append((e, t, int(rng.integers(1, min(K, t + 1) + 1))))
                loss = self._loss(eps, items)
                opt.zero_grad(); loss.backward()
                nn.utils.clip_grad_norm_(self.net.parameters(), 0.25)
                opt.step()
                tot += loss.item() * len(b); n += len(b)
            hist.append(tot / n)
        return {"train_loss_history": hist, "train_loss": self.eval_loss(train),
                "val_loss": self.eval_loss(val) if val is not None and len(val) else float("nan"),
                "loss_name": "mean squared error, predicted vs logged setting ([-1, 1] units)",
                "target_return_to_go": self.target_rtg, "rtg_scale": self.rtg_scale,
                "train_seconds": time.time() - t0}

    def policy(self, obs):
        """A long-term period has no within-visit history: context of one step, conditioned on
        the target return-to-go (the 90th percentile of training returns-to-go)."""
        obs = np.atleast_2d(np.asarray(obs, np.float32))
        n = len(obs)
        d = self.device
        R = torch.full((n, 1, 1), self.target_rtg / self.rtg_scale, device=d)
        S = torch.tensor(obs[:, None, :], device=d)
        A = torch.zeros((n, 1, ACTION_DIM), device=d)
        self.net.eval()
        with torch.no_grad():
            return self.net(R, S, A)[:, 0].cpu().numpy()

    q = None


# ==================================================================================================
# SARSA on coarse setting cells
# ==================================================================================================
class ActionBins:
    """rate 4 x Left current 3 x Right current 3 equal-width cells on [-1, 1]."""

    def __init__(self, n_rate=4, n_left=3, n_right=3):
        self.n = (n_rate, n_left, n_right)
        self.size = n_rate * n_left * n_right

    def index(self, a) -> np.ndarray:
        a = np.clip(np.atleast_2d(np.asarray(a, float)), -1, 1)
        idx = 0
        for dim, nb in zip((0, 1, 2), self.n):
            b = np.minimum(((a[:, dim] + 1) / 2 * nb).astype(int), nb - 1)
            idx = idx * nb + b
        return idx

    def geometric_centre(self, i: int) -> np.ndarray:
        out = np.zeros(ACTION_DIM)
        rem = i
        for dim, nb in reversed(list(zip((0, 1, 2), self.n))):
            b = rem % nb; rem //= nb
            out[dim] = -1 + (b + 0.5) * 2 / nb
        return out


class SarsaAgent:
    name = "sarsa"

    def __init__(self, gamma=0.99, min_support=3, hidden=128, device=None):
        self.cfg = dict(gamma=gamma, min_support=min_support, hidden=hidden,
                        bins="rate 4 x Left current 3 x Right current 3")
        self.device = pick_device(device)
        self.bins = ActionBins()
        self.net = mlp(STATE_DIM, self.bins.size, hidden).to(self.device)
        self.centres = np.stack([self.bins.geometric_centre(i) for i in range(self.bins.size)])
        self.support = np.zeros(self.bins.size, int)

    def _t(self, x):
        return torch.tensor(np.asarray(x), device=self.device)

    def _td(self, net, tgt, s, a, r, s2, a2, end):
        q = net(s).gather(1, a[:, None])[:, 0]
        with torch.no_grad():
            q2 = tgt(s2).gather(1, a2[:, None])[:, 0]
        target = r + self.cfg["gamma"] * (1 - end) * q2
        return ((q - target) ** 2).mean()

    def _tensors(self, tr):
        return (self._t(tr["s"]), self._t(self.bins.index(tr["a"])).long(), self._t(tr["r"]),
                self._t(tr["s2"]), self._t(self.bins.index(tr["a2"])).long(), self._t(tr["end"]))

    def eval_loss(self, store) -> float:
        if not len(store):
            return float("nan")
        T = self._tensors(store.transitions())
        with torch.no_grad():
            return float(self._td(self.net, self.net, *T))

    def fit(self, train: ExperienceStore, *, epochs=100, batch_size=64, learning_rate=1e-3,
            seed=0, val=None) -> dict:
        rng = np.random.default_rng(seed)
        tr = train.transitions()
        ai = self.bins.index(tr["a"])
        self.support = np.bincount(ai, minlength=self.bins.size)
        for i in range(self.bins.size):   # a chosen cell -> mean of the settings delivered in it
            if self.support[i]:
                self.centres[i] = tr["a"][ai == i].mean(0)
        T = self._tensors(tr)
        tgt = copy.deepcopy(self.net)
        opt = torch.optim.Adam(self.net.parameters(), lr=learning_rate)
        hist = []
        t0 = time.time()
        for _ in range(epochs):
            tot, n = 0.0, 0
            for b in _batches(len(tr["r"]), batch_size, rng):
                bi = torch.tensor(b, device=self.device)
                loss = self._td(self.net, tgt, *(x[bi] for x in T))
                opt.zero_grad(); loss.backward(); opt.step()
                tot += loss.item() * len(b); n += len(b)
            tgt.load_state_dict(self.net.state_dict())
            hist.append(tot / n)
        return {"train_loss_history": hist, "train_loss": self.eval_loss(train),
                "val_loss": self.eval_loss(val) if val is not None else float("nan"),
                "loss_name": "squared SARSA error, pain points^2",
                "cells_supported": int((self.support >= self.cfg["min_support"]).sum()),
                "cells_total": self.bins.size, "train_seconds": time.time() - t0}

    def _qall(self, obs):
        with torch.no_grad():
            return self.net(self._t(np.atleast_2d(np.asarray(obs, np.float32)))).cpu().numpy()

    def policy(self, obs):
        q = self._qall(obs)
        ok = self.support >= self.cfg["min_support"]
        if not ok.any():
            ok = self.support > 0
        q[:, ~ok] = -np.inf
        return self.centres[q.argmax(1)].astype(np.float32)

    def q(self, obs, actions):
        qa = self._qall(obs)
        return qa[np.arange(len(qa)), self.bins.index(actions)]


# ==================================================================================================
# Actor-Critic (offline, advantage-weighted)
# ==================================================================================================
class ActorCriticAgent:
    name = "actor_critic"

    def __init__(self, gamma=0.99, actor_lr=1e-3, critic_lr=2e-3, entropy_coef=0.01, beta=1.0,
                 max_weight=20.0, hidden=128, device=None):
        self.cfg = dict(gamma=gamma, actor_lr=actor_lr, critic_lr=critic_lr,
                        entropy_coef=entropy_coef, beta=beta, max_weight=max_weight, hidden=hidden)
        self.device = pick_device(device)
        self.qnet = mlp(STATE_DIM + ACTION_DIM, 1, hidden).to(self.device)
        self.vnet = mlp(STATE_DIM, 1, hidden).to(self.device)
        self.actor = mlp(STATE_DIM, ACTION_DIM, hidden).to(self.device)
        self.log_std = nn.Parameter(torch.full((ACTION_DIM,), -0.5, device=self.device))

    def _t(self, x):
        return torch.tensor(np.asarray(x, np.float32), device=self.device)

    def _Q(self, net, s, a):
        return net(torch.cat([s, a], -1))[:, 0]

    def _critic_loss(self, tgt, s, a, r, s2, a2, end):
        with torch.no_grad():
            target = r + self.cfg["gamma"] * (1 - end) * self._Q(tgt, s2, a2)
        return ((self._Q(self.qnet, s, a) - target) ** 2).mean()

    def _dist(self, s):
        mean = torch.tanh(self.actor(s))
        std = self.log_std.clamp(-5, 0.5).exp().expand_as(mean)
        return torch.distributions.Normal(mean, std)

    def _actor_loss(self, s, a):
        with torch.no_grad():
            adv = self._Q(self.qnet, s, a) - self.vnet(s)[:, 0]
            w = torch.exp(adv / self.cfg["beta"]).clamp(max=self.cfg["max_weight"])
        d = self._dist(s)
        logp = d.log_prob(a).sum(-1)
        return -(w * logp).mean() - self.cfg["entropy_coef"] * d.entropy().sum(-1).mean()

    def eval_loss(self, store) -> dict:
        if not len(store):
            return {"critic": float("nan"), "actor_mse": float("nan")}
        tr = store.transitions()
        T = [self._t(tr[k]) for k in ("s", "a", "r", "s2", "a2", "end")]
        with torch.no_grad():
            c = float(self._critic_loss(self.qnet, *T))
            m = float(((torch.tanh(self.actor(T[0])) - T[1]) ** 2).mean())
        return {"critic": c, "actor_mse": m}

    def fit(self, train: ExperienceStore, *, epochs=100, batch_size=64, learning_rate=None,
            seed=0, val=None) -> dict:
        rng = np.random.default_rng(seed)
        tr = train.transitions()
        T = [self._t(tr[k]) for k in ("s", "a", "r", "s2", "a2", "end")]
        tgt = copy.deepcopy(self.qnet)
        opt_c = torch.optim.Adam(list(self.qnet.parameters()) + list(self.vnet.parameters()),
                                 lr=self.cfg["critic_lr"])
        opt_a = torch.optim.Adam(list(self.actor.parameters()) + [self.log_std],
                                 lr=learning_rate or self.cfg["actor_lr"])
        hist_c, hist_a = [], []
        t0 = time.time()
        for _ in range(epochs):
            tc = ta = 0.0; n = 0
            for b in _batches(len(tr["r"]), batch_size, rng):
                bi = torch.tensor(b, device=self.device)
                s, a, r, s2, a2, end = (x[bi] for x in T)
                lc = self._critic_loss(tgt, s, a, r, s2, a2, end)
                lv = ((self.vnet(s)[:, 0] - self._Q(self.qnet, s, a).detach()) ** 2).mean()
                opt_c.zero_grad(); (lc + lv).backward(); opt_c.step()
                la = self._actor_loss(s, a)
                opt_a.zero_grad(); la.backward(); opt_a.step()
                tc += lc.item() * len(b); ta += la.item() * len(b); n += len(b)
            tgt.load_state_dict(self.qnet.state_dict())
            hist_c.append(tc / n); hist_a.append(ta / n)
        tl, vl = self.eval_loss(train), self.eval_loss(val) if val is not None else None
        return {"train_loss_history": hist_c, "actor_loss_history": hist_a,
                "train_loss": tl["critic"], "val_loss": vl["critic"] if vl else float("nan"),
                "train_actor_mse": tl["actor_mse"],
                "val_actor_mse": vl["actor_mse"] if vl else float("nan"),
                "loss_name": "critic: squared value error, pain points^2; actor_mse: policy mean vs logged setting",
                "train_seconds": time.time() - t0}

    def policy(self, obs):
        with torch.no_grad():
            return torch.tanh(self.actor(self._t(np.atleast_2d(obs)))).cpu().numpy()

    def q(self, obs, actions):
        with torch.no_grad():
            return self._Q(self.qnet, self._t(np.atleast_2d(obs)),
                           self._t(np.clip(np.atleast_2d(actions), -1, 1))).cpu().numpy()


AGENTS = {"decision_transformer": DecisionTransformerAgent, "sarsa": SarsaAgent,
          "actor_critic": ActorCriticAgent}
