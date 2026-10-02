"""Two small-data models that need no neural network.

1. `TabularActorCritic`, the actor-critic with a Q-table look-up.
   * States are a handful of cells: the patient's composite pain (lower, middle or upper third
     of the training ratings) by the Left contact the next setting uses (6), so 18 cells.
   * Actions are cells too: rate (4 bands) x Left current (3) x Right current (3) x mean pulse
     width (2), so 72 cells. A recommended cell is turned back into a setting by taking the median
     of the settings actually delivered in it, so the table never invents an untried setting.
   * The critic is the Q-table: Q(s, a) = mean reward + gamma x the value of the next state
     under the actor, solved by repeated sweeps over the observed transitions.
   * The actor is a table of probabilities: pi(a | s) is proportional to how often clinicians
     chose a in s, times exp(Q_pessimistic(s, a) / temperature). Q_pessimistic subtracts
     `beta` x the reward scatter / sqrt(visits), so a cell tried once cannot win on luck
     (the table form of conservative offline RL). Critic and actor are updated in turn.
   * Two ways to read a recommendation: `exploit` (the actor's most likely cell: best setting to
     keep) and `explore` (the cell with the highest optimistic value, Q + beta x scatter /
     sqrt(visits + 1), among cells whose currents stay under the ceiling: what to test next).
2. `GPBandit`: a Gaussian process (the model family the current Stim Optimizer uses) predicting a
   step's reward from the state and setting, recommending the delivered setting with the best
   predicted reward. One step ahead only (no gamma): it shows whether looking further ahead adds
   anything.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .data_pipeline import SafetyModel, denormalize_action, normalize_action

RATE_EDGES = (40.0, 80.0, 120.0)        # bands: <=40, 41-80, 81-120, >120 Hz
AMP_EDGES = (1.0, 2.5)                  # bands: <1, 1-2.5, >2.5 mA
PW_EDGES = (120.0,)                     # bands: <=120, >120 us (mean of the two sides)
N_CONTACT = len(C.CONTACT_LEVELS) + 1


def _band(x, edges):
    return int(np.searchsorted(np.asarray(edges), x, side="left"))


def action_cell(raw) -> int:
    f, aL, aR, pL, pR = raw
    r = _band(f, RATE_EDGES)
    l = _band(aL, AMP_EDGES)
    rr = _band(aR, AMP_EDGES)
    p = _band(0.5 * (pL + pR), PW_EDGES)
    return ((r * 3 + l) * 3 + rr) * 2 + p


N_ACTIONS = 4 * 3 * 3 * 2


class TabularActorCritic:
    def __init__(self, gamma=0.5, beta=1.0, temperature=0.5, n_sweeps=50, n_iter=10, seed=0):
        self.gamma, self.beta, self.tau = gamma, beta, temperature
        self.n_sweeps, self.n_iter = n_sweeps, n_iter
        self.rng = np.random.default_rng(seed)

    # ---- encoding ----
    def state_cell(self, obs) -> np.ndarray:
        obs = np.atleast_2d(obs)
        comp = obs[:, 7] * 10.0
        tert = np.searchsorted(self.cuts, comp, side="right")
        contact = np.argmax(obs[:, 15:15 + N_CONTACT], axis=1)
        return tert * N_CONTACT + contact

    # ---- fitting ----
    def fit(self, transitions: pd.DataFrame):
        obs = np.stack(transitions["obs"].to_list())
        nxt = np.stack(transitions["next_obs"].to_list())
        raw = transitions[[f"act_{k}" for k in C.ACTION_NAMES]].to_numpy(float)
        self.cuts = np.quantile(obs[:, 7] * 10.0, [1 / 3, 2 / 3])
        s = self.state_cell(obs)
        s2 = self.state_cell(nxt)
        a = np.array([action_cell(x) for x in raw])
        r = transitions["reward"].to_numpy(float)
        done = transitions["terminal"].to_numpy(bool)
        nS = 3 * N_CONTACT
        self.nS = nS
        n = np.zeros((nS, N_ACTIONS))
        np.add.at(n, (s, a), 1)
        self.n = n
        self.sigma = float(np.std(r)) if len(r) > 1 else 1.0
        # the setting each action cell stands for: median of what was delivered there
        self.cell_setting = {c: np.median(raw[a == c], axis=0) for c in np.unique(a)}
        behav = (n + 1e-3) / (n + 1e-3).sum(axis=1, keepdims=True)
        visited = n > 0
        pi = np.where(visited, behav, 0.0)
        pi = np.where(pi.sum(1, keepdims=True) > 0, pi / np.maximum(pi.sum(1, keepdims=True), 1e-12),
                      1.0 / N_ACTIONS)
        Q = np.zeros((nS, N_ACTIONS))
        for _ in range(self.n_iter):
            for _ in range(self.n_sweeps):                       # critic: evaluate the actor
                V = np.sum(pi * Q, axis=1)
                target = r + self.gamma * np.where(done, 0.0, V[s2])
                tot = np.zeros_like(Q)
                np.add.at(tot, (s, a), target)
                Q = np.where(visited, tot / np.maximum(n, 1), 0.0)
            q_lcb = Q - self.beta * self.sigma / np.sqrt(np.maximum(n, 1))
            logits = np.log(behav) + q_lcb / self.tau            # actor: behaviour-weighted softmax
            logits = np.where(visited, logits, -np.inf)
            has = visited.any(axis=1)
            m = np.where(has, np.max(np.where(visited, logits, -1e300), axis=1), 0.0)
            ex = np.where(visited, np.exp(logits - m[:, None]), 0.0)
            pi = np.where(has[:, None], ex / np.maximum(ex.sum(1, keepdims=True), 1e-300), 1.0 / N_ACTIONS)
        self.Q, self.pi, self.visited = Q, pi, visited
        V = np.sum(pi * Q, axis=1)
        # shrink each cell toward its state's value by its visit count (2 pseudo-visits)
        self.Q_shrunk = np.where(visited, (n * Q + 2.0 * V[:, None]) / (n + 2.0), V[:, None])
        self.fallback_cell = int(np.argmax(n.sum(axis=0)))
        return self

    # ---- reading ----
    def _cell_to_norm(self, cells, obs):
        out = []
        for c, o in zip(cells, obs):
            raw = self.cell_setting.get(int(c))
            if raw is None:                       # never delivered: keep the setting in force
                out.append(o[10:15] * 2.0 - 1.0)
            else:
                out.append(normalize_action(raw))
        return np.asarray(out, dtype=np.float32)

    def policy(self, obs, mode="exploit"):
        obs = np.atleast_2d(obs)
        s = self.state_cell(obs)
        cells = []
        safety = SafetyModel()
        for si in s:
            if mode == "exploit":
                cells.append(int(np.argmax(self.pi[si])) if self.visited[si].any() else self.fallback_cell)
            else:
                ucb = self.Q_shrunk[si] + self.beta * self.sigma / np.sqrt(self.n[si] + 1.0)
                ok = np.array([c in self.cell_setting and not safety.violates(self.cell_setting[c])
                               for c in range(N_ACTIONS)])
                cells.append(int(np.argmax(np.where(ok, ucb, -np.inf))))
        return self._cell_to_norm(cells, obs)

    def q(self, obs, actions_norm):
        s = self.state_cell(obs)
        raw = denormalize_action(actions_norm)
        a = np.array([action_cell(x) for x in raw])
        return self.Q_shrunk[s, a]


class GPBandit:
    """Gaussian process on (composite pain, contact, setting) -> one-step reward."""

    def __init__(self, seed=0):
        self.seed = seed

    @staticmethod
    def _x(obs, act_norm):
        obs = np.atleast_2d(obs)
        return np.hstack([obs[:, [7]], obs[:, 15:15 + N_CONTACT], np.atleast_2d(act_norm)])

    def fit(self, transitions: pd.DataFrame):
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ConstantKernel
        obs = np.stack(transitions["obs"].to_list())
        raw = transitions[[f"act_{k}" for k in C.ACTION_NAMES]].to_numpy(float)
        act = normalize_action(raw)
        y = transitions["reward"].to_numpy(float)
        k = ConstantKernel(1.0) * RBF(length_scale=np.ones(1 + N_CONTACT + 5)) + WhiteKernel(1.0)
        self.gp = GaussianProcessRegressor(k, normalize_y=True, random_state=self.seed,
                                           n_restarts_optimizer=2).fit(self._x(obs, act), y)
        safety = SafetyModel()
        cand = np.unique(raw, axis=0)
        self.candidates = normalize_action(cand[[not safety.violates(c) for c in cand]])
        return self

    def q(self, obs, actions_norm):
        return self.gp.predict(self._x(obs, actions_norm))

    def policy(self, obs, mode="exploit"):
        obs = np.atleast_2d(obs)
        out = []
        for o in obs:
            X = self._x(np.repeat(o[None], len(self.candidates), 0), self.candidates)
            mu, sd = self.gp.predict(X, return_std=True)
            score = mu if mode == "exploit" else mu + 1.0 * sd
            out.append(self.candidates[int(np.argmax(score))])
        return np.asarray(out, dtype=np.float32)
