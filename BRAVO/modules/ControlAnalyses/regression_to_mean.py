"""Does regression to the mean explain decision 253's block-to-block swing at one unchanged
setting? (`artifacts/research_2026-09-25_options/01_regression_to_the_mean.md`, 2026-09-25.) Free
of the database; the runner feeds it the same per-setting-period table decision 253's own
calibration diagnosis already builds (`StimOptimizer/stage1_openloop.py`).

WHAT THIS TESTS. Decision 253 found the objective (pain relative to today's setting) falling block
by block at the setting delivered most often in one rate/pulse-width group: this is exactly what
regression to the mean predicts if that setting was kept, or came to be the most-delivered one,
partly because its own early weeks happened to look bad. Step 5 asks whether the swing is special
to that one current pair or is what every other way of splitting the same setting-periods into a
group the same size would show; Step 6 asks whether a swing this size is common anywhere else in
the whole record. Descriptive throughout: it never selects a setting, exactly like every other
calibration check in this module family (`StimOptimizer.stage1_openloop.CALIBRATION_CONSEQUENCE`).

WHAT WAS LEFT OUT OF THE SPECIFICATION, AND WHY. The document's own recommendation is to run this
first on the one group decision 253 flagged and generalise later "if it proves useful" -- so this
module and its runner are built for one group at a time, not swept across every rate/pulse-width
stratum yet. Step 5's random-sample fallback for a record too large to enumerate exactly is not
built (the document says none is needed at this record's size); `internal_split_test` raises rather
than silently sampling if a caller ever asks for more splits than `max_splits` allows.
"""
import itertools
import math

import numpy as np
import pandas as pd
from scipy import stats as st

#: Currents within this many decimal places are the same setting -- the same rounding
#: `StimOptimizer.stage1_openloop._reference_setting` uses.
ROUND_MA = 3

#: Safety cap on Step 5's exact enumeration (`math.comb(n, k)`); decision 253's own group is 19
#: choose 8 = 75,582. Above the cap this module refuses rather than falling back to a random
#: sample the specification does not ask for.
MAX_EXACT_SPLITS = 2_000_000


def time_blocks(t0, n_blocks=3):
    """Setting-periods in time order, cut into `n_blocks` contiguous, roughly equal-sized blocks --
    the same recipe as `StimOptimizer.stage1_openloop._fold_labels_by_time`, reimplemented here so
    this module reads no other module and stays testable on made-up numbers."""
    t0 = np.asarray(t0, dtype=float)
    n = t0.size
    if n < 2:
        return np.zeros(n, dtype=int)
    order = np.argsort(t0)
    lab = np.zeros(n, dtype=int)
    for i, idx in enumerate(np.array_split(order, max(1, int(n_blocks)))):
        lab[idx] = i
    return lab


def target_mask(amp_left, amp_right, *, round_ma=ROUND_MA):
    """Step 1: the current pair delivered in the most setting-periods -- the same recipe as
    `_reference_setting`. Returns `(mask, (left_mA, right_mA))`."""
    aL = np.round(np.asarray(amp_left, dtype=float), round_ma)
    aR = np.round(np.asarray(amp_right, dtype=float), round_ma)
    key = list(zip(aL.tolist(), aR.tolist()))
    counts = pd.Series(key).value_counts()
    top = counts.index[0]
    mask = np.array([k == top for k in key], dtype=bool)
    return mask, (float(top[0]), float(top[1]))


def block_series(J, obs_var, blocks, mask):
    """Steps 3/4's per-block weighted mean and standard error for the setting-periods `mask`
    selects: one row per block that has at least one of them. Mirrors `_reference_setting`."""
    J = np.asarray(J, dtype=float)
    obs_var = np.asarray(obs_var, dtype=float)
    blocks = np.asarray(blocks)
    mask = np.asarray(mask, dtype=bool)
    rows = []
    for b in np.unique(blocks):
        m = mask & (blocks == b)
        if not m.any():
            continue
        w = 1.0 / np.maximum(obs_var[m], 1e-12)
        mean = float(np.sum(w * J[m]) / np.sum(w))
        rows.append(dict(block=int(b), n=int(m.sum()), mean=mean,
                          se=float(1.0 / np.sqrt(np.sum(w))), w=float(np.sum(w))))
    return rows


def heterogeneity(rows):
    """Step 3's two-sided number: how far the block averages sit from their own combined average,
    weighted by how much each can be trusted. `None` fields when fewer than two blocks have a
    setting-period -- mirrors `_reference_setting`'s own refusal."""
    if len(rows) < 2:
        return dict(q=None, p=None, grand_mean=None, df=None,
                    reason="fewer than two blocks of time have a setting-period")
    W = np.array([r["w"] for r in rows], dtype=float)
    M = np.array([r["mean"] for r in rows], dtype=float)
    grand = float(np.sum(W * M) / np.sum(W))
    q = float(np.sum(W * (M - grand) ** 2))
    df = len(rows) - 1
    return dict(q=q, p=float(st.chi2.sf(q, df)), grand_mean=grand, df=df, reason=None)


def trend(rows):
    """Step 3's one-sided number: a weighted straight-line fit of the block averages against block
    order (their own block index, not their position in this list), weighted the same way.
    Negative = pain improving block to block, positive = worsening. `None` when fewer than two
    blocks have a setting-period."""
    if len(rows) < 2:
        return dict(slope=None, intercept=None,
                    reason="fewer than two blocks of time have a setting-period")
    x = np.array([r["block"] for r in rows], dtype=float)
    y = np.array([r["mean"] for r in rows], dtype=float)
    w = np.array([r["w"] for r in rows], dtype=float)
    X = np.column_stack([np.ones_like(x), x])
    beta = np.linalg.solve(X.T @ (X * w[:, None]), X.T @ (w * y))
    return dict(slope=float(beta[1]), intercept=float(beta[0]), reason=None)


def group_diagnosis(J, obs_var, blocks, mask):
    """Steps 3/4 for one group of setting-periods: its block averages, heterogeneity and trend."""
    rows = block_series(J, obs_var, blocks, mask)
    return dict(by_block=rows, heterogeneity=heterogeneity(rows), trend=trend(rows))


def _combo_mask_matrix(n, k):
    combos = np.array(list(itertools.combinations(range(n), k)), dtype=np.intp)
    mat = np.zeros((combos.shape[0], n), dtype=float)
    rows = np.repeat(np.arange(combos.shape[0]), k)
    mat[rows, combos.ravel()] = 1.0
    return mat


def internal_split_test(J, obs_var, blocks, mask, *, max_splits=MAX_EXACT_SPLITS):
    """Step 5: every way of splitting this stratum's own setting-periods into a group the size of
    the target and the rest, recomputing the heterogeneity `Q` and the trend for each candidate
    "target" group with the SAME time blocks; exact enumeration only (`n choose k`), which this
    project's record sizes always allow (19 choose 8 = 75,582 for decision 253's own group).

    Returns `p_two_sided` (share of splits whose `Q` is at least as large as the real target's),
    `p_same_direction` (share whose trend falls at least as far in the same direction as the real
    target's), `n_valid` (splits usable after the same refusal `_reference_setting` applies: fewer
    than two blocks of time have a setting-period), `n_total` (`n choose k`, so a caller sees how
    many were skipped) and `floor` (the smallest two-sided value this many usable splits can ever
    report). Raises rather than silently sampling if `n choose k` exceeds `max_splits`: the
    specification calls for exact enumeration only.
    """
    J = np.asarray(J, dtype=float)
    obs_var = np.asarray(obs_var, dtype=float)
    blocks = np.asarray(blocks, dtype=int)
    mask = np.asarray(mask, dtype=bool)
    n = J.size
    k = int(mask.sum())
    n_total = math.comb(n, k) if 0 < k < n else 0
    out = dict(p_two_sided=None, p_same_direction=None, n_valid=0, n_total=n_total,
               q_real=None, trend_real=None, floor=None, reason=None)
    if n_total == 0:
        out["reason"] = "the target group is empty or is the whole stratum"
        return out
    if n_total > max_splits:
        raise ValueError(f"{n_total} splits of {n} choose {k} is too many to enumerate exactly "
                         f"(cap {max_splits}); this check is built for exact enumeration only")
    real = group_diagnosis(J, obs_var, blocks, mask)
    q_real, tr_real = real["heterogeneity"]["q"], real["trend"]["slope"]
    out.update(q_real=q_real, trend_real=tr_real)
    if q_real is None or tr_real is None:
        out["reason"] = "the real target group itself has fewer than two blocks of time"
        return out
    w = 1.0 / np.maximum(obs_var, 1e-12)
    B = int(blocks.max()) + 1 if blocks.size else 0
    M = _combo_mask_matrix(n, k)                                          # (n_total, n)
    counts = np.zeros((M.shape[0], B))
    W = np.zeros((M.shape[0], B))
    WJ = np.zeros((M.shape[0], B))
    for b in range(B):
        ind = (blocks == b).astype(float)
        counts[:, b] = M @ ind
        W[:, b] = M @ (ind * w)
        WJ[:, b] = M @ (ind * w * J)
    present = counts > 0
    n_present = present.sum(axis=1)
    valid = n_present >= 2
    n_valid = int(valid.sum())
    if n_valid == 0:
        out["reason"] = "no split leaves at least two blocks of time populated"
        return out
    Wsafe = np.where(present, W, 0.0)
    Mmean = np.divide(WJ, W, out=np.zeros_like(WJ), where=W > 0)
    Wsum = Wsafe.sum(axis=1)
    grand = Wsum.copy()
    grand[Wsum > 0] = (Wsafe[Wsum > 0] * Mmean[Wsum > 0]).sum(axis=1) / Wsum[Wsum > 0]
    q_split = (Wsafe * (Mmean - grand[:, None]) ** 2).sum(axis=1)
    x = np.arange(B, dtype=float)
    xbar = np.zeros(M.shape[0])
    xbar[Wsum > 0] = (Wsafe[Wsum > 0] * x[None, :]).sum(axis=1) / Wsum[Wsum > 0]
    sxy = (Wsafe * (x[None, :] - xbar[:, None]) * (Mmean - grand[:, None])).sum(axis=1)
    sxx = (Wsafe * (x[None, :] - xbar[:, None]) ** 2).sum(axis=1)
    slope = np.divide(sxy, sxx, out=np.full_like(sxy, np.nan), where=sxx > 0)
    q_v, slope_v = q_split[valid], slope[valid]
    ge_q = int(np.sum(q_v >= q_real - 1e-9))
    if tr_real < 0:
        same_dir = int(np.sum(slope_v <= tr_real + 1e-9))
    else:
        same_dir = int(np.sum(slope_v >= tr_real - 1e-9))
    out.update(n_valid=n_valid, p_two_sided=ge_q / n_valid, p_same_direction=same_dir / n_valid,
               floor=f"< {1.0 / n_valid:.6g}")
    return out


def outside_window_test(J_full, obs_var_full, t0_full, *, window_size, q_real, n_blocks=3):
    """Step 6: every run of `window_size` setting-periods adjacent in time across the WHOLE record
    (every rate and pulse width), its own three time blocks, and the fraction whose heterogeneity
    `Q` is at least as large as `q_real`. These overlapping runs (each shares `window_size - 1`
    setting-periods with the next) are not independent looks; `n_windows` is reported beside the
    fraction for that reason."""
    J = np.asarray(J_full, dtype=float)
    obs_var = np.asarray(obs_var_full, dtype=float)
    t0 = np.asarray(t0_full, dtype=float)
    out = dict(n_windows=0, fraction_ge=None, window_size=int(window_size), q_real=q_real)
    if q_real is None or J.size < window_size or window_size < 2:
        return out
    order = np.argsort(t0)
    J, obs_var = J[order], obs_var[order]
    n = J.size
    n_windows = n - window_size + 1
    ge = 0
    for start in range(n_windows):
        sl = slice(start, start + window_size)
        wblocks = time_blocks(np.arange(window_size, dtype=float), n_blocks=n_blocks)
        rows = block_series(J[sl], obs_var[sl], wblocks, np.ones(window_size, dtype=bool))
        h = heterogeneity(rows)
        if h["q"] is not None and h["q"] >= q_real - 1e-9:
            ge += 1
    out.update(n_windows=int(n_windows), fraction_ge=ge / n_windows)
    return out


def extremity(target_rows, J_full, obs_var_full):
    """Step 7: how far the target group's first block sits from the whole record's own long-run
    weighted average, in units of that block's own standard error. Descriptive, not a test: the
    more extreme this is, the more reversion regression to the mean predicts on its own."""
    if not target_rows:
        return dict(value=None, block1_mean=None, block1_se=None, record_mean=None,
                    reason="the target group has no block to compare")
    first = min(target_rows, key=lambda r: r["block"])
    J_full = np.asarray(J_full, dtype=float)
    obs_var_full = np.asarray(obs_var_full, dtype=float)
    ok = np.isfinite(J_full) & np.isfinite(obs_var_full)
    if not ok.any():
        return dict(value=None, block1_mean=first["mean"], block1_se=first["se"], record_mean=None,
                    reason="no whole-record values to compare against")
    w = 1.0 / np.maximum(obs_var_full[ok], 1e-12)
    record_mean = float(np.sum(w * J_full[ok]) / np.sum(w))
    if not first["se"]:
        return dict(value=None, block1_mean=first["mean"], block1_se=first["se"],
                    record_mean=record_mean, reason="block 1's own noise number is zero or missing")
    value = (first["mean"] - record_mean) / first["se"]
    return dict(value=float(value), block1_mean=first["mean"], block1_se=first["se"],
                record_mean=record_mean, reason=None)


def block_date_ranges(t0, blocks):
    """Feasibility risk 1: each block's own time span, so a reader can see whether the three
    blocks cover similar stretches of calendar time (dates are formatted by the caller)."""
    t0 = np.asarray(t0, dtype=float)
    blocks = np.asarray(blocks)
    out = []
    for b in np.unique(blocks):
        m = blocks == b
        out.append(dict(block=int(b), n=int(m.sum()),
                        t0_min=float(t0[m].min()) if m.any() else None,
                        t0_max=float(t0[m].max()) if m.any() else None))
    return out


def diagnosis(sub, full, *, n_blocks=3, max_splits=MAX_EXACT_SPLITS):
    """Steps 1-7 for one rate/pulse-width group.

    `sub` is that group's own per-setting-period table (`t0` in seconds, `amp_mA_Left`,
    `amp_mA_Right`, `J`, `obs_var`); `full` is the whole record's same columns (`t0`, `J`,
    `obs_var`, every rate and pulse width), used for Step 6's outside comparison and Step 7's
    long-run average. Never selects a setting: a warning, like every other calibration check in
    this module family.
    """
    sub = pd.DataFrame(sub).reset_index(drop=True)
    full = pd.DataFrame(full).reset_index(drop=True) if full is not None else pd.DataFrame()
    need = {"t0", "amp_mA_Left", "amp_mA_Right", "J", "obs_var"}
    if sub.empty or not need.issubset(sub.columns):
        return {"setting": None, "reason": "no per-setting-period pain values to compare"}
    t0 = sub["t0"].to_numpy(dtype=float)
    J = sub["J"].to_numpy(dtype=float)
    v = sub["obs_var"].to_numpy(dtype=float)
    blocks = time_blocks(t0, n_blocks=n_blocks)
    mask, setting = target_mask(sub["amp_mA_Left"], sub["amp_mA_Right"])
    target = group_diagnosis(J, v, blocks, mask)
    other = group_diagnosis(J, v, blocks, ~mask)
    step5 = internal_split_test(J, v, blocks, mask, max_splits=max_splits)
    have_full = not full.empty and {"t0", "J", "obs_var"}.issubset(full.columns)
    full_J = full["J"].to_numpy(dtype=float) if have_full else J
    full_v = full["obs_var"].to_numpy(dtype=float) if have_full else v
    full_t0 = full["t0"].to_numpy(dtype=float) if have_full else t0
    q_real = target["heterogeneity"]["q"]
    step6 = outside_window_test(full_J, full_v, full_t0, window_size=int(mask.sum()),
                                q_real=q_real, n_blocks=n_blocks)
    step7 = extremity(target["by_block"], full_J, full_v)
    return dict(
        setting=dict(amp_mA_Left=setting[0], amp_mA_Right=setting[1]),
        n_target=int(mask.sum()), n_other=int((~mask).sum()),
        block_ranges=block_date_ranges(t0, blocks),
        target=target, other=other,
        internal_comparison=step5, outside_comparison=step6, extremity=step7,
        n_blocks=int(n_blocks), full_record_is_the_stratum_itself=not have_full,
    )
