"""
Statistical-rigor helpers for the Biomarkers module.

Added per the 2026-06 multi-expert rigor review of the DBS pain-biomarker analysis. These are
small, pure, unit-testable functions used to make the inferential claims honest:

  * bh_fdr            — Benjamini-Hochberg FDR q-values for the multi-frequency/-channel p-grid.
  * fisher_z_ci       — confidence interval for a Pearson r (Fisher z-transform).
  * effective_n       — autocorrelation-adjusted effective sample size (serial dependence).
  * partial_corr      — correlation of x,y after regressing out a covariate (e.g. stim amplitude).
  * block_perm_pvalue — circular-block permutation p-value (preserves temporal autocorrelation).
  * balanced_metrics  — balanced accuracy + prevalence/chance baseline for an imbalanced test set.

None of these touch the verbatim notebook science; they wrap/annotate its outputs.
"""

import numpy as np


def bh_fdr(pvals):
    """Benjamini-Hochberg FDR q-values for a 1-D array of p-values (NaNs preserved as NaN).

    Returns an array the same shape as `pvals` with monotone BH-adjusted q-values over the finite
    entries. Use to threshold a family of tests (e.g. ~101 freqs x channels) at a target FDR
    instead of an uncorrected per-test alpha.
    """
    p = np.asarray(pvals, dtype=float).ravel()
    q = np.full(p.shape, np.nan)
    finite = np.isfinite(p)
    m = int(finite.sum())
    if m == 0:
        return q.reshape(np.asarray(pvals).shape)
    idx = np.where(finite)[0]
    order = idx[np.argsort(p[idx])]
    ranked = p[order]
    adj = ranked * m / (np.arange(1, m + 1))
    adj = np.minimum.accumulate(adj[::-1])[::-1]   # enforce monotonicity
    np.clip(adj, 0, 1, out=adj)
    q[order] = adj
    return q.reshape(np.asarray(pvals).shape)


def fisher_z_ci(r, n, alpha=0.05):
    """(lo, hi) confidence interval for a Pearson r via the Fisher z-transform. Returns (nan, nan)
    when n < 4 or r is not finite. `n` should be the EFFECTIVE sample size for serially-correlated
    data (see effective_n)."""
    try:
        r = float(r)
        n = float(n)
    except (TypeError, ValueError):
        return (np.nan, np.nan)
    if not np.isfinite(r) or n < 4 or abs(r) >= 1:
        return (np.nan, np.nan)
    from scipy.stats import norm
    z = np.arctanh(r)
    se = 1.0 / np.sqrt(n - 3.0)
    zc = norm.ppf(1 - alpha / 2.0)
    return (float(np.tanh(z - zc * se)), float(np.tanh(z + zc * se)))


def lag1_autocorr(x):
    """Lag-1 autocorrelation of a 1-D series (finite values, in order). 0.0 if undefined."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 3 or np.std(x) == 0:
        return 0.0
    x = x - x.mean()
    denom = np.sum(x * x)
    if denom == 0:
        return 0.0
    return float(np.sum(x[:-1] * x[1:]) / denom)


def effective_n(x, y):
    """Autocorrelation-adjusted effective sample size for correlating two serially-correlated
    series (Bartlett/Bretherton lag-1 approximation): N_eff = N * (1 - r1x*r1y)/(1 + r1x*r1y),
    clipped to [2, N]. Used so p-values / CIs on r are not anti-conservative when daily pain is
    autocorrelated."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m = np.isfinite(x) & np.isfinite(y)
    n = int(m.sum())
    if n < 3:
        return float(n)
    r1x, r1y = lag1_autocorr(x[m]), lag1_autocorr(y[m])
    factor = (1 - r1x * r1y) / (1 + r1x * r1y) if (1 + r1x * r1y) != 0 else 1.0
    return float(np.clip(n * factor, 2, n))


def partial_corr(x, y, covar):
    """Pearson correlation of x and y after linearly regressing each on `covar` (e.g. stim
    amplitude) — the stim-adjusted association. Returns nan if degenerate. Rows with any NaN are
    dropped pairwise."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    c = np.asarray(covar, dtype=float)
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(c)
    if m.sum() < 4 or np.std(c[m]) == 0:
        return np.nan
    xr = _residualize(x[m], c[m])
    yr = _residualize(y[m], c[m])
    # Relative tolerance so NEAR-collinearity (x or y almost a linear function of covar) returns NaN
    # consistently with exact collinearity, instead of a spurious correlation of tiny residuals.
    if np.std(xr) <= 1e-10 * (np.std(x[m]) + 1e-300) or np.std(yr) <= 1e-10 * (np.std(y[m]) + 1e-300):
        return np.nan
    return float(np.corrcoef(xr, yr)[0, 1])


def _residualize(v, covar):
    """Residuals of v after OLS on [1, covar]."""
    A = np.column_stack([np.ones_like(covar), covar])
    beta, *_ = np.linalg.lstsq(A, v, rcond=None)
    return v - A @ beta


def balanced_metrics(sens, spec, n_pos, n_neg):
    """Honest summary for an imbalanced binary test set.

    Two DIFFERENT chance baselines, because the headline metric is BALANCED accuracy:
      * `balanced_accuracy` = (sens + spec) / 2. Its chance level is ALWAYS 0.5, independent of
        class imbalance — a majority-class, random-at-prevalence, or coin-flip classifier all
        score balanced accuracy ≈ 0.5 (verified empirically with sklearn.balanced_accuracy_score).
        So `chance_accuracy` (the value to compare balanced_accuracy against) is 0.5.
      * `majority_accuracy` = max(n_pos, n_neg) / total is the chance level for RAW (unbalanced)
        accuracy only — it is NOT the comparator for balanced accuracy. Kept for reference and
        labeled as such so it is never again compared head-to-head with balanced accuracy.

    Previously `chance_accuracy` was set to the majority fraction (e.g. 0.88 at 88% prevalence)
    and compared against balanced accuracy (~0.52), which made the model look far below chance.
    """
    out = {"balanced_accuracy": None, "prevalence": None,
           "chance_accuracy": 0.5,          # chance level FOR BALANCED ACCURACY (always 0.5)
           "majority_accuracy": None,       # chance level for RAW accuracy (reference only)
           "n_pos": int(n_pos), "n_neg": int(n_neg)}
    if np.isfinite(sens) and np.isfinite(spec):
        out["balanced_accuracy"] = float((sens + spec) / 2.0)
    total = n_pos + n_neg
    if total > 0:
        out["prevalence"] = float(n_pos / total)
        out["majority_accuracy"] = float(max(n_pos, n_neg) / total)
    return out


def block_length_for(labels, n=None):
    """Default circular-block length = the lag-1 autocorrelation (decorrelation) timescale of the
    labels, -1/ln(r1), clipped to [1, n//4]. 1 when there is no positive autocorrelation. Shared by
    both the scalar and the vectorized permutation paths so they always agree."""
    labels = np.asarray(labels, dtype=float)
    n = int(labels.size if n is None else n)
    # Use the POSITIVE lag-1 autocorrelation only. Circular-block permutation exists to preserve
    # PERSISTENCE (positive autocorrelation) by keeping nearby samples together; the block length is
    # the persistence timescale -1/ln(r1). Negative lag-1 autocorrelation is anti-persistence (rapid
    # alternation), which does NOT call for longer blocks -- taking abs() of it would inflate the
    # block length, needlessly shrink the effective sample size, and make the permutation test
    # over-conservative. So r1 <= 0 -> block length 1 (i.i.d. shuffle).
    r1 = lag1_autocorr(labels)
    if r1 <= 0:
        return 1
    return int(np.clip(round(1.0 / max(1e-6, -np.log(max(r1, 1e-6)))), 1, max(1, n // 4)))


def circular_block_indices(n, block, rng):
    """One circular-block-permuted index vector of length n (block length `block`). Preserves
    within-block temporal structure, breaking only the cross-block label-feature alignment."""
    block = max(1, int(block))
    shift = int(rng.integers(0, n))
    base = (np.arange(n) + shift) % n
    if block <= 1:
        return base
    # rotate by whole blocks
    nb = int(np.ceil(n / block))
    blocks = [base[i * block:(i + 1) * block] for i in range(nb)]
    rng.shuffle(blocks)
    return np.concatenate(blocks)[:n]


def circular_block_perm_matrix(n, block, n_perm, rng):
    """VECTORIZED generation of `n_perm` circular-block permutations at once -> (n_perm, n) int array,
    each row a valid permutation of range(n) with the same distribution as circular_block_indices.

    Per row: a random circular shift, then the shifted index vector is cut into ceil(n/block)
    contiguous blocks whose ORDER is randomly permuted (within-block order preserved). Built with
    array ops only (no Python per-permutation loop), so the whole null is a couple of NumPy calls."""
    block = max(1, int(block))
    n = int(n); n_perm = int(n_perm)
    shifts = rng.integers(0, n, size=n_perm)
    base = (np.arange(n)[None, :] + shifts[:, None]) % n          # (P, n) circularly shifted
    if block <= 1:
        return base
    nb = int(np.ceil(n / block))
    pad = nb * block - n
    if pad:                                                       # pad with sentinel == n (out of range)
        base = np.concatenate([base, np.full((n_perm, pad), n, dtype=base.dtype)], axis=1)
    blk = base.reshape(n_perm, nb, block)                         # (P, nb, block) contiguous blocks
    order = np.argsort(rng.random((n_perm, nb)), axis=1)          # independent block-order permutation per row
    blk = np.take_along_axis(blk, order[:, :, None], axis=1)
    flat = blk.reshape(n_perm, nb * block)
    if not pad:
        return flat
    # Drop the sentinels; each row has exactly `pad` of them, so row-major masking reshapes cleanly.
    return flat[flat < n].reshape(n_perm, n)


def auc_block_perm_null(score, labels, n_perm=1000, block=None, seed=0):
    """Circular-block permutation null for the direction-folded ROC AUC of a continuous biomarker
    against a binary pain label.

    The observed statistic is the SAME quantity the card reports: max(AUC, 1-AUC) of `score` vs
    `labels` (undirected separability — an AUC of 0.21 separates as well as 0.79). Under the null,
    the pain labels carry no information about the biomarker; we break that association by
    circular-block-permuting the labels (block length = the lag-1 decorrelation timescale of the
    labels, via block_length_for) so the null PRESERVES the temporal autocorrelation of pain. A
    plain i.i.d. shuffle would make p anti-conservative for serially-correlated daily pain.

    Returns a dict:
      observed   — max(AUC, 1-AUC) on the real labels (None if degenerate)
      p_value    — (#{null >= observed} + 1)/(n_used + 1)  [add-one, never 0]
      null_q     — {"p50","p95","p99"} percentiles of the null AUC distribution (for a ceiling line)
      null_sample— up to 200 representative null-AUC values (random subsample of the full null), so the
                   UI can draw the null distribution as a swarm over the chance bar (None if degenerate)
      n_perm     — permutations that yielded a finite AUC
      block      — block length used
    Pure NumPy + a single sklearn AUC call per permutation via the rank identity; no Django.
    """
    out = {"observed": None, "p_value": None, "null_q": None, "null_sample": None, "n_perm": 0, "block": None}
    score = np.asarray(score, dtype=float)
    labels = np.asarray(labels, dtype=float)
    m = np.isfinite(score) & np.isfinite(labels)
    score, labels = score[m], labels[m]
    n = labels.size
    if n < 8 or len(set(labels.tolist())) != 2:
        return out
    # Mann-Whitney/AUC via average ranks: AUC = (R_pos - n_pos*(n_pos+1)/2) / (n_pos*n_neg), where
    # R_pos is the sum of ranks of the positive class. Ranking ONCE lets every permutation reuse the
    # same rank vector (permuting labels just re-selects which ranks count as "positive").
    from scipy.stats import rankdata
    ranks = rankdata(score)                       # average ranks, ties handled
    pos = (labels == 1)
    n_pos = int(pos.sum()); n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return out
    def _auc_from_mask(mask):
        r_pos = ranks[mask].sum()
        a = (r_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
        return max(a, 1.0 - a)
    observed = _auc_from_mask(pos)
    if block is None:
        block = block_length_for(labels, n)
    rng = np.random.default_rng(seed)
    P = int(n_perm)
    perm_idx = circular_block_perm_matrix(n, block, P, rng)   # (P, n)
    perm_labels = labels[perm_idx]                            # (P, n) permuted label rows
    perm_pos = (perm_labels == 1)
    r_pos_perm = (ranks[None, :] * perm_pos).sum(axis=1)      # (P,)
    a_perm = (r_pos_perm - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    null_auc = np.maximum(a_perm, 1.0 - a_perm)
    null_auc = null_auc[np.isfinite(null_auc)]
    used = int(null_auc.size)
    if used == 0:
        out["observed"] = float(observed); out["block"] = int(block)
        return out
    ge = int(np.sum(null_auc >= observed))
    # Representative subsample of the null AUCs for a UI swarm over the chance bar. Cap at 200 so the
    # payload stays small; a uniform random draw (fixed seed for reproducibility) preserves the shape.
    n_keep = min(200, used)
    sample_rng = np.random.default_rng(seed + 1)
    sample_idx = sample_rng.choice(used, size=n_keep, replace=False) if n_keep < used else np.arange(used)
    null_sample = [float(v) for v in null_auc[sample_idx]]
    out.update({
        "observed": float(observed),
        "p_value": float((ge + 1) / (used + 1)),
        "null_q": {"p50": float(np.percentile(null_auc, 50)),
                   "p95": float(np.percentile(null_auc, 95)),
                   "p99": float(np.percentile(null_auc, 99))},
        "null_sample": null_sample,
        "n_perm": used,
        "block": int(block),
    })
    return out


def block_perm_pvalue(observed_stat, feature_matrix, labels, stat_fn, n_perm=1000,
                      block=None, seed=0):
    """Empirical p-value for a max-type statistic via circular-block label permutation.

    `feature_matrix` (N x M), `labels` (N,), `stat_fn(feature_matrix, permuted_labels) -> scalar`
    (e.g. max |R| over all channels x freqs). The block length defaults to the lag-1
    autocorrelation timescale of the labels so the null preserves temporal dependence (otherwise
    p is anti-conservative). Returns (empirical_p, n_perm_used).

    NOTE: generic (arbitrary stat_fn), so it loops over permutations. When the statistic is the
    NaN-aware family max|R|, prefer the fully vectorized pipeline._block_perm_maxcorr_pvalue."""
    labels = np.asarray(labels, dtype=float)
    n = labels.size
    if n < 4 or not np.isfinite(observed_stat):
        return (np.nan, 0)
    if block is None:
        block = block_length_for(labels, n)
    rng = np.random.default_rng(seed)
    ge = 0
    used = 0
    for _ in range(int(n_perm)):
        perm = circular_block_indices(n, block, rng)
        s = stat_fn(feature_matrix, labels[perm])
        if np.isfinite(s):
            used += 1
            if s >= observed_stat:
                ge += 1
    if used == 0:
        return (np.nan, 0)
    return ((ge + 1) / (used + 1), used)   # +1: never report p=0
