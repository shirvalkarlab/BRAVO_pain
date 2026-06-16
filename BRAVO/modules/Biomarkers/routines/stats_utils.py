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
    """Honest summary for an imbalanced binary test set: balanced accuracy = (sens+spec)/2, the
    prevalence, and the majority-class (chance) accuracy to compare raw accuracy against."""
    out = {"balanced_accuracy": None, "prevalence": None, "chance_accuracy": None,
           "n_pos": int(n_pos), "n_neg": int(n_neg)}
    if np.isfinite(sens) and np.isfinite(spec):
        out["balanced_accuracy"] = float((sens + spec) / 2.0)
    total = n_pos + n_neg
    if total > 0:
        out["prevalence"] = float(n_pos / total)
        out["chance_accuracy"] = float(max(n_pos, n_neg) / total)
    return out


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


def block_perm_pvalue(observed_stat, feature_matrix, labels, stat_fn, n_perm=1000,
                      block=None, seed=0):
    """Empirical p-value for a max-type statistic via circular-block label permutation.

    `feature_matrix` (N x M), `labels` (N,), `stat_fn(feature_matrix, permuted_labels) -> scalar`
    (e.g. max |R| over all channels x freqs). The block length defaults to the lag-1
    autocorrelation timescale of the labels so the null preserves temporal dependence (otherwise
    p is anti-conservative). Returns (empirical_p, n_perm_used)."""
    labels = np.asarray(labels, dtype=float)
    n = labels.size
    if n < 4 or not np.isfinite(observed_stat):
        return (np.nan, 0)
    if block is None:
        r1 = abs(lag1_autocorr(labels))
        block = int(np.clip(round(1.0 / max(1e-6, -np.log(max(r1, 1e-6)))), 1, max(1, n // 4))) if r1 > 0 else 1
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
