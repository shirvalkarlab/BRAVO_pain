"""One scoring routine for every model: how well it agrees with long-term home outcomes.

Every model, whatever its library, is wrapped as two functions on the 24-number state:
  policy(obs[n, 24]) -> recommended settings, scaled to [-1, 1]   (required)
  q(obs[n, 24], actions[n, 5]) -> the model's value of each setting, in pain points (optional)

and scored on the long-term setting periods (`data_pipeline.chronic_validation_set`), which no
model trained on. All pain numbers are on the 0-10 scale (six REDCap items averaged).

PRIMARY SCORES ARE ABOUT CHANGE. Pain carries over from one period to the next (rank correlation
0.55 between consecutive periods), so a score on pain LEVELS rewards any model whose output tracks
the previous period's pain (audit 2026-10-02: a critic that ignores the setting scored 0.548). The
primary scores therefore use the change in pain from the previous period with reports
(`pain - prev_pain`, negative = better):

* `rho_dist_change`: rank correlation (Spearman) between how far each period's setting was from the
  model's recommendation and that change. Positive is good: periods whose setting sat closer to
  the recommendation got better (or less worse).
* `near_minus_far_change`: mean change in periods at or below the one-third point of distance minus
  those at or above the two-thirds point (thirds by distance value, so ties stay together).
  Negative is good: pain fell more near the recommendation.
* `rho_adv`: rank correlation between the model's predicted gain from switching (value of the
  period's setting minus value of the previous setting, at the same state) and the observed drop in
  pain. Positive is good. Only for models with a value function.
Level scores (`rho_dist`, `near_minus_far`, `rho_q`) are kept as secondary.

Distances: root-mean-square over the five settings scaled to [-1, 1]; for a period with Left
stimulation off the Left current and width are left out (the contact already fixes them, so they
would only measure agreement about the contact).

P-values, one-sided: `p_shuffle` shuffles the outcome across periods; `p_shift` rotates it
against the settings, which keeps neighbouring periods' similarity and is the honest one here.
With 52 periods the smallest `p_shift` possible is 1/52.

Risk of the recommendations: mean risk score (0 below 4.0 mA, 1 at the 4.5 mA ceiling, above 1
past it), the share at or above 4.0 mA on either side, the share past a limit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import config as C
from .data_pipeline import SafetyModel, denormalize_action, normalize_action

ACTION_COLS = list(C.ACTION_NAMES)
OFF = "off (Left 0 mA)"


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


def action_distance(a, b, left_off=None) -> np.ndarray:
    """Root-mean-square difference over the settings, each scaled to [-1, 1], in double precision
    rounded to 6 decimals so equal settings give EXACTLY equal distances (regression 2026-10-02:
    float32 noise split ties and moved rank correlations by up to 0.03). Rows flagged `left_off`
    leave out the Left current and Left width."""
    a, b = np.atleast_2d(np.asarray(a, np.float64)), np.atleast_2d(np.asarray(b, np.float64))
    sq = (a - b) ** 2
    if left_off is not None:
        mask = np.ones_like(sq)
        lo = np.asarray(left_off, bool)
        mask[lo, 1] = 0.0
        mask[lo, 3] = 0.0
        d = np.sqrt((sq * mask).sum(axis=1) / mask.sum(axis=1))
    else:
        d = np.sqrt(sq.mean(axis=1))
    return np.round(d, 6)


def _thirds(d, y):
    lo, hi = np.quantile(d, [1 / 3, 2 / 3])
    near, far = d <= lo, d >= hi
    if not (near.any() and far.any()) or lo >= hi:
        return float("nan")
    return float(np.mean(y[near]) - np.mean(y[far]))


def evaluate_policy(name: str, policy, val: pd.DataFrame, q=None, *, n_perm: int = 2000,
                    seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    obs = np.stack(val["obs"].to_list()).astype(np.float32)
    a_hist = normalize_action(val[ACTION_COLS].to_numpy(float))
    a_prev = obs[:, 10:15].astype(np.float64) * 2.0 - 1.0
    pain = val["pain_composite"].to_numpy(float)
    change = pain - val["prev_pain_composite"].to_numpy(float)
    left_off = (val["left_contact"] == OFF).to_numpy()
    a_rec = np.clip(np.asarray(policy(obs), dtype=np.float64), -1, 1)
    d = action_distance(a_rec, a_hist, left_off)
    out = {"model": name, "n_periods": int(len(val)), "distances": d.tolist(), "pain": pain.tolist(),
           "change": change.tolist()}
    out["rho_dist_change"] = _spearman(d, change)
    out["p_dist_change_shuffle"], out["p_dist_change_shift"] = _p_values(
        d, change, out["rho_dist_change"], n_perm=n_perm, rng=rng)
    out["near_minus_far_change"] = _thirds(d, change)
    out["rho_dist"] = _spearman(d, pain)
    out["p_dist_shuffle"], out["p_dist_shift"] = _p_values(d, pain, out["rho_dist"], n_perm=n_perm, rng=rng)
    out["near_minus_far"] = _thirds(d, pain)
    if q is not None:
        qv = np.round(np.asarray(q(obs, a_hist.astype(np.float32)), float).ravel(), 6)
        qp = np.round(np.asarray(q(obs, a_prev.astype(np.float32)), float).ravel(), 6)
        adv = qv - qp
        out["rho_adv"] = _spearman(adv, -change)
        out["p_adv_shuffle"], out["p_adv_shift"] = _p_values(adv, -change, out["rho_adv"], n_perm=n_perm, rng=rng)
        out["rho_q"] = _spearman(qv, -pain)
        out["p_q_shuffle"], out["p_q_shift"] = _p_values(qv, -pain, out["rho_q"], n_perm=n_perm, rng=rng)
        q_rec = np.asarray(q(obs, a_rec.astype(np.float32)), float).ravel()
        # the model's own estimate of the gain from its recommendation over the period's setting
        # (its critic's opinion, optimistic by construction; reported, never ranked on)
        out["model_gain_vs_history"] = float(np.mean(q_rec - qv))
    else:
        for k in ("rho_adv", "p_adv_shuffle", "p_adv_shift", "rho_q", "p_q_shuffle", "p_q_shift",
                  "model_gain_vs_history"):
            out[k] = float("nan")
    safety = SafetyModel()
    raw = denormalize_action(a_rec)
    risk = np.array([safety.risk(s) for s in raw])
    out["risk_mean"] = float(risk.mean())
    out["share_at_or_above_4mA"] = float(np.mean(np.max(raw[:, 1:3], axis=1) >= C.AMP_WARN_MA - 1e-9))
    out["share_past_limit"] = float(np.mean([safety.violates(s) for s in raw]))
    out["mean_rec_setting"] = dict(zip(ACTION_COLS, np.round(raw.mean(axis=0), 2).tolist()))
    return out


def evaluate_all(name, policy, val_sets: dict, q=None, **kw) -> dict:
    """Primary scores on `val_sets['primary']`, the headline numbers of the others under
    `sensitivity`."""
    res = evaluate_policy(name, policy, val_sets["primary"], q=q, **kw)
    res["sensitivity"] = {}
    for k, v in val_sets.items():
        if k == "primary" or len(v) < 8:
            continue
        r = evaluate_policy(name, policy, v, q=q, **kw)
        res["sensitivity"][k] = {m: r[m] for m in ("n_periods", "rho_dist_change", "p_dist_change_shift",
                                                   "near_minus_far_change", "rho_adv", "p_adv_shift",
                                                   "rho_dist", "near_minus_far")}
    return res


def recommend(policy, obs_by_contact: dict, q=None) -> pd.DataFrame:
    """The recommended setting for each Left contact from today's state, raw units, with risk."""
    safety = SafetyModel()
    rows = []
    for contact, obs in obs_by_contact.items():
        if obs is None:
            continue
        a = np.clip(np.asarray(policy(obs[None, :].astype(np.float32)), float), -1, 1)
        raw = denormalize_action(a)[0]
        if contact == OFF:
            raw[1] = 0.0                       # the contact means Left current 0
        rec = {"left_contact": contact, **dict(zip(ACTION_COLS, np.round(raw, 2))),
               "risk": round(safety.risk(raw), 3)}
        if q is not None:
            rec["q"] = float(np.asarray(q(obs[None, :].astype(np.float32), a.astype(np.float32))).ravel()[0])
        rows.append(rec)
    return pd.DataFrame(rows)


# ---- reference policies, so every number has something to be compared with ------------------------
def stay_policy(obs):
    """Keep the setting in force (the state carries it, scaled to 0-1)."""
    return np.asarray(obs, np.float64)[:, 10:15] * 2.0 - 1.0


def make_random_policy(seed=0):
    rng = np.random.default_rng(seed)

    def pol(obs):
        return rng.uniform(-1, 1, size=(len(obs), len(ACTION_COLS)))
    return pol


def make_constant_policy(transitions: pd.DataFrame):
    """Always the single most often delivered setting in training (audit 2026-10-02: a constant
    setting already scores on the level measures, so every model must be compared with one)."""
    raw = transitions[[f"act_{k}" for k in C.ACTION_NAMES]].round(4)
    mode = raw.value_counts().index[0]
    a = normalize_action(np.asarray(mode, float))

    def pol(obs):
        return np.repeat(a[None, :], len(obs), axis=0)
    pol.setting = tuple(float(x) for x in mode)
    return pol


def heldout_visit_value_rank(fit, transitions: pd.DataFrame, *, n_folds: int = 5, seed: int = 0,
                             n_perm: int = 2000) -> dict:
    """Clinic-sheet test with more data: in visits left out of training (5 folds by visit), does
    the model's value of the setting that came next rank the relief that actually followed?

    `fit(train_transitions)` returns q(obs, actions). Scores: Spearman between the observed
    `symptom` drop (pain points, before penalties) and (a) q itself, (b) the predicted switch gain
    q(s, next setting) - q(s, setting in force). (a) is inflated by pain that falls by itself
    from a high level (the state carries the current pain), so (b) is the one that says whether
    the model knows anything about SETTINGS. p is one-sided from shuffling the drops within each
    visit."""
    rng = np.random.default_rng(seed)
    visits = np.array(sorted(transitions["visit"].unique()))
    rng.shuffle(visits)
    folds = [set(visits[i::n_folds]) for i in range(n_folds)]
    qs, ys, groups, advs = [], [], [], []
    for test in folds:
        tr = transitions[~transitions["visit"].isin(test)]
        te = transitions[transitions["visit"].isin(test)]
        q = fit(tr)
        obs = np.stack(te["obs"].to_list()).astype(np.float32)
        act = normalize_action(te[[f"act_{k}" for k in C.ACTION_NAMES]].to_numpy(float)).astype(np.float32)
        cur = (obs[:, 10:15].astype(np.float64) * 2.0 - 1.0).astype(np.float32)
        qs.append(np.round(np.asarray(q(obs, act), float).ravel(), 6))
        advs.append(np.round(np.asarray(q(obs, act), float).ravel() - np.asarray(q(obs, cur), float).ravel(), 6))
        ys.append(te["symptom"].to_numpy(float))
        groups.append(te["visit"].to_numpy())
    qv, y, g, adv = np.concatenate(qs), np.concatenate(ys), np.concatenate(groups), np.concatenate(advs)
    out = {"n_heldout": int(len(y))}
    for key, x in (("value", qv), ("switch_gain", adv)):
        rho = _spearman(x, y)
        null = []
        for _ in range(n_perm):
            yp = y.copy()
            for v in np.unique(g):
                m = g == v
                yp[m] = rng.permutation(y[m])
            null.append(_spearman(x, yp))
        p = (1 + np.sum(np.asarray(null) >= rho)) / (1 + n_perm) if np.isfinite(rho) else float("nan")
        out[f"heldout_rho_{key}"] = rho
        out[f"heldout_p_{key}"] = float(p)
    return out


def _rank(x):
    from scipy.stats import rankdata
    return rankdata(np.asarray(x, float))


def _partial_rank_corr(x, y, Z):
    """Correlation of the ranks of x and y after removing (by least squares) the ranks of Z."""
    R = np.column_stack([np.ones(len(x))] + [_rank(z) for z in Z])
    rx, ry = _rank(x), _rank(y)
    ex = rx - R @ np.linalg.lstsq(R, rx, rcond=None)[0]
    ey = ry - R @ np.linalg.lstsq(R, ry, rcond=None)[0]
    if np.std(ex) == 0 or np.std(ey) == 0:
        return float("nan")
    return float(np.corrcoef(ex, ey)[0, 1])


def switch_gain_decomposition(fit, transitions: pd.DataFrame, *, n_folds=5, seed=0, n_perm=1000) -> dict:
    """The sharper held-out test (scientific review, 2026-10-02), rule fixed before running:
    the model's recommendations are supported only if (a) > 0 with p < 0.05 AND (c) keeps its sign.
      (a) rank correlation of q(s, next) with the relief that followed, after removing q(s, current)
          and the current composite pain;
      (b) rank correlation of -q(s, current) alone with relief ("leaving this setting helps");
      (c) the switch gain on switches between two ACTIVE settings (Left current >= 1 mA before and
          after, neither step with Left off) whose gain is not zero.
    p-values: one-sided, shuffling relief within each visit."""
    rng = np.random.default_rng(seed)
    visits = np.array(sorted(transitions["visit"].unique()))
    rng.shuffle(visits)
    folds = [set(visits[i::n_folds]) for i in range(n_folds)]
    parts = []
    for test in folds:
        q = fit(transitions[~transitions["visit"].isin(test)])
        te = transitions[transitions["visit"].isin(test)]
        obs = np.stack(te["obs"].to_list()).astype(np.float32)
        nxt = normalize_action(te[[f"act_{k}" for k in C.ACTION_NAMES]].to_numpy(float)).astype(np.float32)
        cur = (obs[:, 10:15].astype(np.float64) * 2 - 1).astype(np.float32)
        parts.append(pd.DataFrame({
            "qn": np.round(np.asarray(q(obs, nxt), float).ravel(), 6),
            "qc": np.round(np.asarray(q(obs, cur), float).ravel(), 6),
            "pain": obs[:, 7].astype(float), "base": obs[:, 22].astype(float),
            "y": te["symptom"].to_numpy(float), "visit": te["visit"].to_numpy(),
            "active": ((te["cur_amp_mA_Left"] >= 1.0) & (te["act_amp_mA_Left"] >= 1.0)).to_numpy()}))
    d = pd.concat(parts, ignore_index=True)
    d["gain"] = d["qn"] - d["qc"]
    act = d[d["active"] & (d["gain"] != 0)]
    stats = {
        "a_partial": lambda f, y: _partial_rank_corr(f["qn"], y, [f["qc"], f["pain"]]),
        # the level rewards are measured from the visit's first rating, which the state carries:
        # remove it too, or q can rank "relief from baseline" through the baseline alone
        "a_partial_baseline": lambda f, y: _partial_rank_corr(f["qn"], y, [f["qc"], f["pain"], f["base"]]),
        "b_leave_current": lambda f, y: _spearman(-f["qc"], y),
        "c_active_gain": lambda f, y: _spearman(f["gain"], y),
    }
    out = {"n": int(len(d)), "n_active_nonzero": int(len(act))}
    for k, fn in stats.items():
        f = act if k == "c_active_gain" else d
        y = f["y"].to_numpy()
        obs_stat = fn(f, y)
        null = []
        g = f["visit"].to_numpy()
        for _ in range(n_perm):
            yp = y.copy()
            for v in np.unique(g):
                m = g == v
                yp[m] = rng.permutation(y[m])
            null.append(fn(f, yp))
        null = np.asarray(null, float)
        out[k] = obs_stat
        out[f"p_{k}"] = float((1 + np.sum(null >= obs_stat)) / (1 + n_perm)) if np.isfinite(obs_stat) else float("nan")
    out["supports_recommendations"] = bool(out["a_partial"] > 0 and out["p_a_partial"] < 0.05
                                           and out["c_active_gain"] > 0)
    out["supports_after_baseline"] = bool(out["a_partial_baseline"] > 0 and out["p_a_partial_baseline"] < 0.05
                                          and out["c_active_gain"] > 0)
    return out
