"""One scoring routine for every model: how well it agrees with long-term home outcomes.

Every model, whatever its library, is wrapped as two functions on the 22-number state:
  policy(obs[n, 22]) -> recommended settings, scaled to [-1, 1]   (required)
  q(obs[n, 22], actions[n, 5]) -> the model's value of each setting, in pain points (optional)

and scored on the long-term setting periods (`data_pipeline.chronic_validation_set`), none of
which the models saw. Numbers reported, all on the 0-10 pain-point scale:

* `rho_dist`: rank correlation (Spearman) between how far each period's setting was from the
  model's recommendation and the mean home pain during it. Positive is good: periods whose setting
  sat closer to the recommendation hurt less.
* `rho_q`: rank correlation between the model's value of each period's setting and minus its pain.
  Positive is good. Only for models with a value function.
* `near_minus_far`: mean pain in the third of periods closest to the recommendation minus the
  third farthest. Negative is good.
* Two p-values for each correlation, one-sided: `p_shuffle` shuffles pain across periods; `p_shift`
  rotates the pain series against the settings, which keeps neighbouring periods' similarity and
  is the honest one here (consecutive periods are not independent). With 52 periods the smallest
  `p_shift` possible is 1/52.
* Risk of the recommendations: mean risk score (0 below 4.0 mA, 1 at the 4.5 mA ceiling, above 1
  past it), the share at or above 4.0 mA on either side, the share past a limit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import config as C
from .data_pipeline import SafetyModel, denormalize_action, normalize_action

ACTION_COLS = list(C.ACTION_NAMES)


def _spearman(x, y) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 4 or np.nanstd(x[ok]) == 0 or np.nanstd(y[ok]) == 0:
        return float("nan")
    return float(spearmanr(x[ok], y[ok]).statistic)


def _p_values(x, y, rho, *, n_perm, rng) -> tuple[float, float]:
    """One-sided p for rho > 0 by shuffling y and by rotating y (all n-1 rotations)."""
    if not np.isfinite(rho):
        return float("nan"), float("nan")
    y = np.asarray(y, float)
    null = np.array([_spearman(x, rng.permutation(y)) for _ in range(n_perm)])
    p_shuffle = (1 + np.sum(null >= rho)) / (1 + n_perm)
    rot = np.array([_spearman(x, np.roll(y, k)) for k in range(1, len(y))])
    p_shift = (1 + np.sum(rot >= rho)) / (1 + len(rot))
    return float(p_shuffle), float(p_shift)


def action_distance(a, b) -> np.ndarray:
    """Root-mean-square difference over the five settings, each scaled to [-1, 1]."""
    a, b = np.atleast_2d(a), np.atleast_2d(b)
    return np.sqrt(np.mean((a - b) ** 2, axis=1))


def evaluate_policy(name: str, policy, val: pd.DataFrame, q=None, *, n_perm: int = 2000,
                    seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    obs = np.stack(val["obs"].to_list()).astype(np.float32)
    a_hist = normalize_action(val[ACTION_COLS].to_numpy(float)).astype(np.float32)
    pain = val["pain_composite"].to_numpy(float)
    a_rec = np.clip(np.asarray(policy(obs), dtype=np.float32), -1, 1)
    d = action_distance(a_rec, a_hist)
    out = {"model": name, "n_periods": int(len(val))}
    out["rho_dist"] = _spearman(d, pain)
    out["p_dist_shuffle"], out["p_dist_shift"] = _p_values(d, pain, out["rho_dist"], n_perm=n_perm, rng=rng)
    k = max(1, len(d) // 3)
    order = np.argsort(d)
    out["near_minus_far"] = float(np.mean(pain[order[:k]]) - np.mean(pain[order[-k:]]))
    if q is not None:
        qv = np.asarray(q(obs, a_hist), float).ravel()
        out["rho_q"] = _spearman(qv, -pain)
        out["p_q_shuffle"], out["p_q_shift"] = _p_values(qv, -pain, out["rho_q"], n_perm=n_perm, rng=rng)
        q_rec = np.asarray(q(obs, a_rec), float).ravel()
        # the model's own estimate of the gain from switching to its recommendation (its critic's
        # opinion, optimistic by construction; reported, never ranked on alone)
        out["model_gain_vs_history"] = float(np.mean(q_rec - qv))
    else:
        out["rho_q"] = out["p_q_shuffle"] = out["p_q_shift"] = out["model_gain_vs_history"] = float("nan")
    safety = SafetyModel()
    raw = denormalize_action(a_rec)
    risk = np.array([safety.risk(s) for s in raw])
    out["risk_mean"] = float(risk.mean())
    out["share_at_or_above_4mA"] = float(np.mean(np.max(raw[:, 1:3], axis=1) >= C.AMP_WARN_MA - 1e-9))
    out["share_past_limit"] = float(np.mean([safety.violates(s) for s in raw]))
    out["mean_rec_setting"] = dict(zip(ACTION_COLS, np.round(raw.mean(axis=0), 2).tolist()))
    return out


def recommend(policy, obs_by_contact: dict, q=None) -> pd.DataFrame:
    """The recommended setting for each Left contact from today's state, raw units, with risk."""
    safety = SafetyModel()
    rows = []
    for contact, obs in obs_by_contact.items():
        if obs is None:
            continue
        a = np.clip(np.asarray(policy(obs[None, :].astype(np.float32)), float), -1, 1)
        raw = denormalize_action(a)[0]
        rec = {"left_contact": contact, **dict(zip(ACTION_COLS, np.round(raw, 2))),
               "risk": round(safety.risk(raw), 3)}
        if q is not None:
            rec["q"] = float(np.asarray(q(obs[None, :].astype(np.float32), a.astype(np.float32))).ravel()[0])
        rows.append(rec)
    return pd.DataFrame(rows)


# ---- reference policies, so every number has something to be compared with ------------------------
def stay_policy(obs):
    """Keep the setting in force (the state carries it, scaled to 0-1)."""
    return np.asarray(obs)[:, 10:15] * 2.0 - 1.0


def make_random_policy(seed=0):
    rng = np.random.default_rng(seed)

    def pol(obs):
        return rng.uniform(-1, 1, size=(len(obs), len(ACTION_COLS)))
    return pol
