"""
Statistical-rigor helpers for the Biomarkers module.

Added per the 2026-06 multi-expert rigor review of the DBS pain-biomarker analysis. These are
small, pure, unit-testable functions used to make the inferential claims honest:

  * bh_fdr            — Benjamini-Hochberg FDR q-values for the multi-frequency/-channel p-grid.
  * fisher_z_ci       — confidence interval for a Pearson r (Fisher z-transform).
  * effective_n       — autocorrelation-adjusted effective sample size (serial dependence).
  * partial_corr      — correlation of x,y after regressing out a covariate (e.g. stim amplitude).
  * CovariateShape    — the shape that covariate is allowed to have: line, curve or kernel.
  * partial_corr_columns — the same, for every column of a matrix, each on its own usable rows.
  * rotations         — the chance test for a series in time: every other rotation once (decision 315).
  * balanced_metrics  — balanced accuracy + prevalence/chance baseline for an imbalanced test set.
  * purged_time_blocked_folds — held-out blocks of time with the neighbouring rows embargoed.
  * confound_gate     — one association reported plainly and with a third quantity taken out.

None of these touch the verbatim notebook science; they wrap/annotate its outputs.
"""

import numpy as np

#: WHEN TAKING A COVARIATE OUT OF A SERIES LEAVES NOTHING WORTH CORRELATING. If this much of a
#: series' movement is the covariate itself, the residual is noise and any correlation computed on
#: it is a number made of what the fit could not explain. The honest answer is then "this series is
#: almost exactly the covariate here", which is itself a strong finding, not a missing one.
#: Decision 237 set the value at 0.98 for the titration ladder's reading and this is its one home,
#: so the ladder's rule and E2's rule cannot drift apart.
NEARLY_THE_COVARIATE_R2 = 0.98


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


def partial_corr(x, y, covar, shape="line"):
    """Pearson correlation of x and y after regressing each on `covar` (e.g. stim amplitude) — the
    stim-adjusted association. Returns nan if degenerate. Rows with any NaN are dropped pairwise.

    `shape` is how the covariate is allowed to act: `"line"` (the default, and what every existing
    caller gets, so no published number moves) or any other of :data:`COVARIATE_SHAPES` — a squared
    term, a 3-knot spline, one of three kernels, or one level per delivered setting. A straight line
    cannot remove a covariate effect that turns over, and what it leaves behind looks like a
    relationship between x and y (decision 241)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    c = np.asarray(covar, dtype=float)
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(c)
    if m.sum() < 4 or np.std(c[m]) == 0:
        return np.nan
    if shape == "line":
        xr = _residualize(x[m], c[m])
        yr = _residualize(y[m], c[m])
    else:
        sh = CovariateShape(c[m], shape=shape)
        if not sh.usable:
            return np.nan
        xr, yr = sh.residuals(x[m]), sh.residuals(y[m])
    # Relative tolerance so NEAR-collinearity (x or y almost a linear function of covar) returns NaN
    # consistently with exact collinearity, instead of a spurious correlation of tiny residuals.
    if np.std(xr) <= 1e-10 * (np.std(x[m]) + 1e-300) or np.std(yr) <= 1e-10 * (np.std(y[m]) + 1e-300):
        return np.nan
    return float(np.corrcoef(xr, yr)[0, 1])


def partial_corr_columns(X, y, covar, shape="line"):
    """`partial_corr` for EVERY column of a band-power matrix at once, column by column.

    ``X`` is one row per pain report and one column per band; ``y`` is one pain score per report;
    ``covar`` is one covariate value per report (on this page, the stimulation current in force when
    the report was filed). Each column is adjusted and correlated on its OWN usable rows -- the rows
    where that band, the pain score and the covariate are all present -- so a band with more missing
    signal is not cut down to another band's sample, exactly as `pearson_r_columns` does for the
    plain correlation.

    Returns ``{"r": (C,), "n": (C,)}``. A column that cannot be adjusted (fewer than four usable
    rows, no spread left in the covariate, or a band that is itself almost a straight line in the
    covariate) comes back non-finite rather than as a number, the same refusal `partial_corr` makes.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    c = np.asarray(covar, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    C = X.shape[1]
    r = np.full(C, np.nan, dtype=float)
    n = np.zeros(C, dtype=int)
    base = np.isfinite(y) & np.isfinite(c)
    for j in range(C):
        m = base & np.isfinite(X[:, j])
        n[j] = int(m.sum())
        r[j] = partial_corr(X[m, j], y[m], c[m], shape=shape)
    return {"r": r, "n": n}


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
    """The persistence timescale of a series: the lag-1 autocorrelation (decorrelation) timescale,
    -1/ln(r1), clipped to [1, n//4]; 1 when there is no positive autocorrelation.

    USED FOR THE RESAMPLED INTERVALS AND THE EMBARGO, NOT FOR ANY CHANCE TEST (decision 315,
    2026-09-26). It sizes the blocks of the moving-block bootstrap (`block_bootstrap_picks`, the
    heat maps' intervals, decision 183) and the gap left either side of a held-out block of time
    (`purged_time_blocked_folds`). Until decision 315 it also chose the chunk length of the shared
    chance test, which cut the pain series into chunks of this length and reordered them; at 1 that
    test was already a rotation. The chunk shuffle breaks pain's slow rises and falls at every chunk
    edge, and on RCS08 the growing record had moved the heat-map grid from rotations (72 NRS ratings,
    chunk length 1, measured 2026-09-02) to chunks of 2 (777 ratings, lag-1 0.54) without anyone
    deciding it; an unrelated made-up band then read p <= 0.05 in 10.7% of records. Every chance test
    now rotates the whole series (`rotations`), whatever this returns.

    MEASURED ON THE REAL DATA (2026-09-02), kept because the estimator's assumption still matters for
    the intervals. It models the autocorrelation as AR(1), where ACF(k) = r1**k, and reads lag 1 only.
    For the `nrs` rating-level series (72 ratings then) the observed function was
        +0.357 +0.402 +0.426 +0.374 +0.354 +0.226   (lags 1-6; still +0.35 at lag 12)
    where an AR(1) at r1 = 0.357 predicts +0.357 +0.128 +0.046 +0.016 +0.006 +0.002: the series does
    not decay geometrically, so a block of this length under-states how far pain's dependence reaches.
    An integrated autocorrelation time, tau = 1 + 2*sum ACF(k), was implemented and reverted on
    2026-09-02 because it moved the chance test; with the chance test no longer reading this, it is
    a question for the intervals alone, recorded rather than done."""
    labels = np.asarray(labels, dtype=float)
    n = int(labels.size if n is None else n)
    # Use the POSITIVE lag-1 autocorrelation only. The block length is the persistence timescale
    # -1/ln(r1); negative lag-1 autocorrelation is anti-persistence (rapid alternation), which does
    # NOT call for longer blocks -- taking abs() of it would inflate the block length and needlessly
    # widen the intervals it sizes. So r1 <= 0 -> block length 1.
    r1 = lag1_autocorr(labels)
    if r1 <= 0:
        return 1
    return int(np.clip(round(1.0 / max(1e-6, -np.log(max(r1, 1e-6)))), 1, max(1, n // 4)))


def block_bootstrap_picks(n, block, n_boot, rng):
    """``(n_boot, n)`` row indices for a bootstrap of a series of ``n`` observations in TIME ORDER.

    ``block <= 1`` is the plain i.i.d. draw, ``rng.integers(0, n, size=(n_boot, n))`` -- the same
    call, the same place in the generator's order, so a caller that used to make that draw itself
    gets the identical resamples. ``block > 1`` is the circular moving-block bootstrap (Politis and
    Romano): ``ceil(n / block)`` block starts drawn uniformly, each start followed by the next
    ``block - 1`` observations modulo ``n``, truncated to ``n``. Neighbouring observations travel
    together, so an interval built on the draw is as wide as serially dependent observations
    warrant, instead of as narrow as ``n`` independent ones would be. The same draw
    ``analytics._block_bootstrap_aucs`` has made over rating clusters since audit [16]."""
    n, B = int(n), int(n_boot)
    if block is None or int(block) <= 1:
        return rng.integers(0, n, size=(B, n))
    L = int(block)
    n_blocks = int(np.ceil(n / L))
    starts = rng.integers(0, n, size=(B, n_blocks))
    idx = (starts[:, :, None] + np.arange(L)[None, None, :]) % n
    return idx.reshape(B, -1)[:, :n]


#: Above this many values a rotation null draws ``n_perm`` distinct rotations instead of using every
#: one. The heat-map grid (777-819 ratings on RCS08, 2026-09-26), the full-spectrum search (78) and
#: the check before any decoder (86-458) are all below it; the power-over-time area test's series of
#: readings (301,851 on RCS08) is above it, and there 1,000 distinct rotations are drawn,
#: as measured in `artifacts/analysis_2026-09-26_exact_null_on_the_heat_maps.md`.
EXACT_ROTATIONS_MAX = 5000


def rotation_shifts(n, n_perm, rng):
    """The shifts a rotation null moves a series of ``n`` values by: every shift 1 .. n-1 once, in
    order (``rng`` not used), or above ``EXACT_ROTATIONS_MAX`` values ``n_perm`` distinct shifts drawn
    without replacement. ``n_perm`` <= 0 or fewer than 2 values gives none."""
    n, n_perm = int(n), int(n_perm)
    if n_perm <= 0 or n < 2:
        return np.zeros(0, int)
    if n <= EXACT_ROTATIONS_MAX:
        return np.arange(1, n)
    return np.sort(rng.choice(np.arange(1, n), size=min(n_perm, n - 1), replace=False))


def rotations(n, n_perm, rng):
    """THE CHANCE TEST FOR A SERIES IN TIME: every other rotation of the whole series, each once.
    ONE HOME since decision 315 (2026-09-26); the band detector's since decision 314.

    Row k of the ``(k, n)`` answer is ``(arange(n) + shift_k) % n``: the series slid along in time by
    ``shift_k`` values with the end wrapped round to the start. Rotating keeps the series' whole
    persistence -- every slow rise and fall -- and moves only its alignment with what it is compared
    against. n orders exist, the observed one among them; every OTHER rotation is returned once and a
    p of the form (rotations at least as extreme + 1) / (rotations + 1) counts the observed order
    once, so it IS the exact rotation p, smallest value 1/n. Above ``EXACT_ROTATIONS_MAX`` values
    ``n_perm`` distinct rotations are drawn without replacement instead, which keeps the same p valid.

    WHAT IT REPLACED. (1) A shuffle that, once pain resembled its neighbours, cut the series into
    chunks and reordered them (`circular_block_perm_matrix`, deleted): chunk edges break pain's slow
    drift, and with a band that drifts too the shuffled links are narrower than chance really is. On
    RCS08's own layout an unrelated made-up band read p <= 0.05 in 10.7% of records (8.7% under the
    Biomarkers page's settings) where this reads 5.9% (5.8%); with the band as persistent as RCS08's
    at 60 s of signal, 17.1% against 7.4%. (2) At a chunk length of 1 that shuffle already rotated,
    but drew rotations with replacement, so the p was a noisy estimate of this one.

    WHAT IT DOES NOT FIX. The one seam where the series wraps round pairs the end of the record with
    its start, which is never natural; with very persistent series and a pain level that does not
    hold steady this reads p <= 0.05 somewhat more often than 5% (7.4% and 9.1% in the measurement
    above, 7.1% at 60 ratings with lag-1 0.9 in decision 314's)."""
    shifts = rotation_shifts(n, n_perm, rng)
    n = max(int(n), 0)
    if shifts.size == 0:
        return np.zeros((0, n), int)
    return (np.arange(n)[None, :] + shifts[:, None]) % n


def rotation_null_words(n, n_rows):
    """How a rotation null of ``n_rows`` rows over ``n`` values was made, in words, for a saved row."""
    return ("exact: every other rotation once" if int(n_rows) == int(n) - 1 else
            f"{int(n_rows)} of the {int(n) - 1} other rotations, drawn without replacement")


def rotation_null_resolution(n, n_rows=None):
    """How finely a rotation null can resolve a p-value: ``(n_distinct, p_floor, p_step)``.

    With every other rotation once (``n_rows`` None or n - 1) only ``n`` orders exist, so the
    smallest p is 1/n and p moves in steps of 1/n, however many shuffles were asked for. Published
    beside the p so a p near 0.05 at a few dozen ratings is not read to three decimal places. With
    fewer rows drawn (above ``EXACT_ROTATIONS_MAX``) the floor is 1/(rows + 1)."""
    n = int(n)
    if n < 2:
        return None, None, None
    rows = n - 1 if n_rows is None else int(n_rows)
    if rows >= n - 1:
        return n, 1.0 / n, 1.0 / n
    return n, 1.0 / (rows + 1), 1.0 / (rows + 1)


def auc_block_perm_null(score, labels, n_perm=1000, block=None, seed=0):
    """Rotation null for the direction-folded ROC AUC of a continuous biomarker against a binary
    pain label. (The name predates decision 315; the null has rotated since then.)

    The observed statistic is the SAME quantity the card reports: max(AUC, 1-AUC) of `score` vs
    `labels` (undirected separability -- an AUC of 0.21 separates as well as 0.79). Under the null the
    pain labels carry no information about the biomarker; the labels are rotated in time
    (`rotations`), which keeps pain's persistence whole and moves only its alignment with the
    biomarker. ``block`` is accepted and ignored (it chose the old chunk shuffle's length).

    Returns a dict:
      observed   -- max(AUC, 1-AUC) on the real labels (None if degenerate)
      p_value    -- (#{null >= observed} + 1)/(n_used + 1): the exact rotation p up to
                    ``EXACT_ROTATIONS_MAX`` labels, never 0
      null_q     -- {"p50","p95","p99"} percentiles of the null AUC distribution (for a ceiling line)
      null_sample-- up to 200 representative null-AUC values (random subsample of the full null), so the
                   UI can draw the null distribution as a swarm over the chance bar (None if degenerate)
      n_perm     -- rotations that yielded a finite AUC
      block      -- 1, the rotation (kept for the response's shape)
    Pure NumPy; no Django.
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
    # R_pos is the sum of ranks of the positive class. Ranking ONCE lets every rotation reuse the
    # same rank vector (rotating labels just re-selects which ranks count as "positive").
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
    rng = np.random.default_rng(seed)
    shifts = rotation_shifts(n, n_perm, rng)
    # MEMORY-BOUNDED. A single (P, n) materialization is O(P*n): for a long power-domain series
    # (n ~ 3e5) at P=1000 the intermediates are ~2.4 GB EACH, which OOM-kills the worker. The
    # statistic per rotation is just a sum of positive-class ranks, so the rotations are taken in
    # chunks: peak memory is O(chunk*n) instead of O(P*n). The accumulated null is only (P,).
    CHUNK_ELEMS = 8_000_000
    chunk = max(1, min(max(1, shifts.size), CHUNK_ELEMS // max(1, n)))
    fixed_ranks = ranks.astype(float)                         # (n,) rank at each FIXED position
    a_parts = []
    for i in range(0, shifts.size, chunk):
        s = shifts[i:i + chunk]
        perm_idx = (np.arange(n)[None, :] + s[:, None]) % n      # (c, n) rotated label positions
        # Per rotated row i: R_pos = sum_j fixed_ranks[j] * (labels[perm_idx[i,j]] == 1). The RANKS
        # stay at their fixed positions (column j); only the label assignment moves.
        perm_pos = (labels[perm_idx] == 1)                        # (c, n)
        r_pos_perm = (fixed_ranks[None, :] * perm_pos).sum(axis=1)  # (c,)
        a_parts.append((r_pos_perm - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))
        del perm_idx, perm_pos, r_pos_perm
    a_perm = np.concatenate(a_parts) if a_parts else np.empty(0)
    null_auc = np.maximum(a_perm, 1.0 - a_perm)
    null_auc = null_auc[np.isfinite(null_auc)]
    used = int(null_auc.size)
    if used == 0:
        out["observed"] = float(observed); out["block"] = 1
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
        "block": 1,
    })
    return out


# =================================================================================================
# THE outlier rule for the biomarker plate. ONE implementation, one threshold, used everywhere.
# =================================================================================================
# PI decision, 2026-08-30 (superseding an interim 3 MAD decision the same day): every reported
# statistic on the biomarker plate — the correlation spectrum, the full-spectrum exploration scan,
# the chronic LFP-power path, the AUC, the effect sizes — uses ONE filter at 5 MAD, applied
# uniformly to the FEATURE, the LABEL and the chronic power column.
#
# Before this consolidation there were three separate implementations with two different thresholds
# (analytics at 5 MAD dropping, streaming_psd._mad_keep at 3 MAD keeping, adapter.mad_outlier_mask
# at 3 MAD keeping) and inverted polarity between them. They now all delegate here. Raising or
# lowering MAD_N_DEFAULT changes the whole plate at once, which is the point.
#
# NOTE: moving from 3 to 5 MAD LOOSENS the correlation spectrum and the chronic path — they reject
# fewer samples than before this change. That is the intended consequence of the PI's decision.
MAD_N_DEFAULT = 5.0


def mad_outlier_flags(x, n_mad=None, scale="raw"):
    """Boolean mask of OUTLIERS (True == outlier == exclude) under the MAD rule.

    Rule: ``|v - median(v)| > n_mad * MAD``, with ``MAD = median(|v - median(v)|)`` and NO
    consistency rescaling (so ``n_mad`` is in raw MAD units, not sigma; 5 raw MAD is about
    3.37 sigma on Gaussian data). The inequality is STRICT so this is the exact complement of
    :func:`mad_keep_mask` at every threshold, boundary included.

    ``scale`` is accepted for the call sites that spell it out and must be ``"raw"``: the rule is
    evaluated on the values as given. Until 2026-09-19 ``"log"`` evaluated it on ``log10`` of the
    values, for multiplicative quantities such as raw band power, where a symmetric raw-scale
    window is proportionally tighter above the median than below and so trims the upper tail
    almost exclusively (measured on RCS08 then: 3.71% removed one-sidedly against 6.19% two-sidedly
    on the log scale, and the selected band changed). The PI's rule of that day (decision 202: log
    power enters no calculation; this site decision 205) removed the option; the threshold stays
    at 5 MAD. Asking for ``"log"`` raises rather than silently running the raw rule.

    Non-finite entries are never flagged (they are already absent from every statistic), so the
    returned count means genuine exclusions.

    ZERO-MAD GUARD: when a majority of samples share one value the MAD is 0 and a naive rule would
    flag everything that merely differs from the median, deleting all remaining variation. In that
    case nothing is flagged and ``info["skipped"]`` says why.

    Returns ``(mask, info)`` with info = {n_finite, n_mad, scale, median, mad, n_removed, skipped}.
    """
    if str(scale) != "raw":
        raise ValueError(f"the outlier rule runs on raw values only (decision 205); got scale={scale!r}")
    x = np.asarray(x, dtype=float)
    n_mad = float(MAD_N_DEFAULT if n_mad is None else n_mad)
    finite = np.isfinite(x)
    info = {"n_finite": int(finite.sum()), "n_mad": n_mad, "scale": "raw",
            "median": None, "mad": None, "n_removed": 0, "skipped": None}
    if finite.sum() < 4:
        info["skipped"] = "fewer than 4 finite samples"
        return np.zeros_like(x, dtype=bool), info
    v = x
    med = float(np.median(v[finite]))
    mad = float(np.median(np.abs(v[finite] - med)))
    info["median"], info["mad"] = med, mad
    if not np.isfinite(mad) or mad <= 0:
        info["skipped"] = "MAD is zero (majority of samples share one value); no removal applied"
        return np.zeros_like(x, dtype=bool), info
    mask = finite & (np.abs(v - med) > n_mad * mad)
    info["n_removed"] = int(mask.sum())
    return mask, info


def mad_keep_mask(x, n_mad=None, scale="raw"):
    """Boolean KEEP-mask (True == keep) — the exact complement of :func:`mad_outlier_flags`.

    Provided because the historical call sites in ``streaming_psd`` and ``adapter`` are written in
    keep-polarity. Non-finite entries are never kept.
    """
    x = np.asarray(x, dtype=float)
    mask, _ = mad_outlier_flags(x, n_mad=n_mad, scale=scale)
    return np.isfinite(x) & ~mask




# =================================================================================================
# THE SHAPE A COVARIATE IS ALLOWED TO HAVE (decision 241; the PI, 2026-09-22).
#
# Taking the stimulation current out of something meant, until now, fitting a STRAIGHT LINE in the
# current and subtracting it. He asked whether that masks a real effect, because a stimulation
# current can help up to a point and worsen above it. It can, both ways round: a curved current
# effect survives a straight-line removal as a leftover curve, which anything tracking distance from
# the best current then correlates with; and a candidate whose own relationship curves reads near
# zero. So the shape is a choice, it is named on every answer, and the flexibility it spends is
# reported beside it -- because a flexible shape on a short record absorbs the slow drift of the
# record itself along with the dose.
#
# MEASURED ON THE LIVE RECORD BEFORE CHOOSING THE DEFAULT (RCS08, L 1-3+, 53 reports, 11 delivered
# currents, 2026-09-22): a straight line explains 25.7% of pain's scatter and is still falling at the
# highest current tested; two degrees of freedom -- a squared term, or this spline -- explain 29-31%
# and put the lowest pain at 3.1-3.2 mA; the squared-exponential, Matern 3/2 and rational-quadratic
# kernels, given 4-6 degrees of freedom, explain 37-43% and move the lowest pain to 1.8-1.9 mA,
# chasing two ratings at 1.6 mA. The flexible shapes do not agree with each other about where the
# turn is, so the default is the cheapest shape that can turn over at all.
# =================================================================================================

#: Every shape a covariate may take. `line` is what the older helpers still default to, so nothing
#: already published moves; `spline` is what the two guards default to.
COVARIATE_SHAPES = ("line", "quadratic", "spline", "squared_exponential", "matern32",
                    "rational_quadratic", "per_setting")

#: Ridge on the kernel fits. Kernel ridge with no penalty interpolates every point and removes
#: everything, including the candidate.
KERNEL_RIDGE = 0.1

#: Below this many distinct covariate values a shape that needs knots cannot be built. Three knots
#: need three distinct places to put them and something either side.
MIN_DISTINCT_FOR_SPLINE = 4


def _rcs_columns(x, knots):
    """Natural (restricted) cubic spline, 3 knots, in Harrell's form: two columns, straight outside
    the outer knots. The standard dose-response shape in clinical work, and the cheapest one that
    can turn over."""
    k = np.asarray(knots, dtype=float)
    denom = (k[-1] - k[0]) ** 2
    def cube(u, kk):
        return np.maximum(u - kk, 0.0) ** 3
    cols = [x]
    for j in range(len(k) - 2):
        cols.append((cube(x, k[j])
                     - cube(x, k[-2]) * (k[-1] - k[j]) / (k[-1] - k[-2])
                     + cube(x, k[-1]) * (k[-2] - k[j]) / (k[-1] - k[-2])) / denom)
    return np.column_stack(cols)


def _kernel_matrix(a, b, shape, ell):
    d = np.abs(np.asarray(a, float)[:, None] - np.asarray(b, float)[None, :])
    if shape == "squared_exponential":                   # smooth, one length scale
        return np.exp(-0.5 * (d / ell) ** 2)
    if shape == "matern32":                              # rougher: one derivative, follows kinks
        s = d * np.sqrt(3.0) / ell
        return (1.0 + s) * np.exp(-s)
    if shape == "rational_quadratic":                    # a mixture of length scales at once
        return (1.0 + (d ** 2) / (2.0 * ell ** 2)) ** (-1.0)
    raise ValueError(shape)


class CovariateShape:
    """One covariate, and the shape it is allowed to take when it is removed from something else.

    ``shape`` is one of :data:`COVARIATE_SHAPES`. The object reports what it actually built
    (``shape``), why it is not what was asked for where that happens (``reason``), how much
    flexibility it spends (``effective_df`` -- 1 for a straight line, the trace of the smoother for
    a kernel), and, for a kernel, the length scale it chose and why (``length_scale``, ``why``).

    Two ways to use it. :meth:`residuals` takes the shape out using every row, which is what an
    in-sample correlation wants. :meth:`train_test_residuals` fits it on the training rows and
    applies it to the held-out ones, which is the only correct thing to do inside a fold -- fitting
    the removal on all the rows lets a held-out row influence its own adjustment.
    """

    def __init__(self, covar, shape="line", *, length_scale=None, ridge=KERNEL_RIDGE):
        if shape not in COVARIATE_SHAPES:
            raise ValueError(f"unknown covariate shape {shape!r}; the shapes are "
                             f"{', '.join(COVARIATE_SHAPES)} (line, quadratic, spline, three "
                             f"kernels, or one level per delivered setting)")
        self.asked_for = str(shape)
        self.shape = str(shape)
        self.reason = None
        self.why = None
        self.length_scale = None
        self.ridge = float(ridge)
        self.c = np.asarray(covar, dtype=float)
        finite = self.c[np.isfinite(self.c)]
        self.levels = sorted(set(np.round(finite, 6).tolist()))
        self.usable = True
        if finite.size < 4 or len(self.levels) < 2:
            self.usable = False
            self.reason = ("the covariate is constant across these rows, so there is nothing to "
                           "take out" if len(self.levels) < 2 else
                           f"only {finite.size} rows carry the covariate")
            self.effective_df = 0.0
            self._design = None
            return
        # ---- fall back where a shape cannot be built on this many distinct values ----
        if self.shape in ("spline",) and len(self.levels) < MIN_DISTINCT_FOR_SPLINE:
            self.reason = (f"a 3-knot spline needs {MIN_DISTINCT_FOR_SPLINE} distinct covariate "
                           f"values and this record has {len(self.levels)} "
                           f"({'two' if len(self.levels) == 2 else str(len(self.levels))}), so a "
                           f"straight line was used instead")
            self.shape = "line"
        if self.shape == "quadratic" and len(self.levels) < 3:
            self.reason = (f"a squared term needs 3 distinct covariate values and this record has "
                           f"{len(self.levels)}, so a straight line was used instead")
            self.shape = "line"
        if self.shape == "per_setting" and len(self.levels) > max(2, finite.size // 4):
            self.reason = (f"one level per setting would spend {len(self.levels) - 1} degrees of "
                           f"freedom on {finite.size} rows, more than a quarter of them, so a "
                           f"3-knot spline was used instead")
            self.shape = "spline" if len(self.levels) >= MIN_DISTINCT_FOR_SPLINE else "line"
        # ---- build it ----
        if self.shape in ("squared_exponential", "matern32", "rational_quadratic"):
            if length_scale is None:
                lv = np.asarray(self.levels, dtype=float)
                gaps = np.abs(lv[:, None] - lv[None, :])[np.triu_indices(lv.size, 1)]
                length_scale = float(np.median(gaps)) if gaps.size else 1.0
                self.why = (f"length scale {length_scale:.2f}, the median distance between the "
                            f"{len(self.levels)} delivered settings")
            else:
                self.why = f"length scale {float(length_scale):.2f}, given by the caller"
            if not np.isfinite(length_scale) or length_scale <= 0:
                self.reason = "the delivered settings give no usable length scale, so a straight line was used instead"
                self.shape = "line"
            else:
                self.length_scale = float(length_scale)
        self._design = self._build_design(self.c)
        self.effective_df = self._effective_df()

    # -- construction ---------------------------------------------------------------------------
    def _build_design(self, c):
        """The columns a least-squares fit uses, WITHOUT the intercept. None for the kernels, whose
        fit depends on which rows are training rows."""
        if self.shape == "line":
            return c[:, None]
        if self.shape == "quadratic":
            return np.column_stack([c, c ** 2])
        if self.shape == "spline":
            knots = np.quantile(np.asarray(self.levels, float), [0.10, 0.50, 0.90])
            self._knots = knots
            return _rcs_columns(c, knots)
        if self.shape == "per_setting":
            return np.column_stack([(np.round(c, 6) == a).astype(float) for a in self.levels[1:]])
        return None                                       # a kernel

    def _effective_df(self):
        if not self.usable:
            return 0.0
        if self._design is not None:
            return float(self._design.shape[1])
        K = _kernel_matrix(self.c, self.c, self.shape, self.length_scale)
        n = K.shape[0]
        return float(np.trace(np.linalg.solve(K + self.ridge * np.eye(n), K)))

    # -- use ------------------------------------------------------------------------------------
    def residuals(self, values):
        """What is left of ``values`` once this shape of the covariate is taken out, using all rows."""
        V = np.asarray(values, dtype=float)
        flat = V.ndim == 1
        V2 = V[:, None] if flat else V
        if not self.usable:
            return V
        if self._design is not None:
            A = np.column_stack([np.ones(len(self.c)), self._design])
            beta, *_ = np.linalg.lstsq(A, V2, rcond=None)
            out = V2 - A @ beta
        else:
            K = _kernel_matrix(self.c, self.c, self.shape, self.length_scale)
            mu = V2.mean(axis=0)
            W = np.linalg.solve(K + self.ridge * np.eye(K.shape[0]), V2 - mu)
            out = (V2 - mu) - K @ W
        return out[:, 0] if flat else out

    def train_test_residuals(self, values, train_idx, test_idx):
        """The same removal, fitted on the training rows and applied to the held-out ones."""
        V = np.asarray(values, dtype=float)
        flat = V.ndim == 1
        V2 = V[:, None] if flat else V
        tr = np.asarray(train_idx, dtype=int)
        te = np.asarray(test_idx, dtype=int)
        if not self.usable:
            return (V[tr], V[te])
        if self._design is not None:
            Atr = np.column_stack([np.ones(tr.size), self._design[tr]])
            Ate = np.column_stack([np.ones(te.size), self._design[te]])
            beta, *_ = np.linalg.lstsq(Atr, V2[tr], rcond=None)
            rtr, rte = V2[tr] - Atr @ beta, V2[te] - Ate @ beta
        else:
            Ktr = _kernel_matrix(self.c[tr], self.c[tr], self.shape, self.length_scale)
            Kte = _kernel_matrix(self.c[te], self.c[tr], self.shape, self.length_scale)
            mu = V2[tr].mean(axis=0)
            W = np.linalg.solve(Ktr + self.ridge * np.eye(tr.size), V2[tr] - mu)
            rtr, rte = (V2[tr] - mu) - Ktr @ W, (V2[te] - mu) - Kte @ W
        return (rtr[:, 0], rte[:, 0]) if flat else (rtr, rte)

    def feature_columns(self):
        """This shape as COLUMNS, for when the covariate is the thing being read rather than the
        thing being removed. A line, a curve or one level per setting is already a set of columns;
        a kernel becomes one bump per delivered setting, which is the same function written as a
        basis, so the covariate is read exactly as flexibly as it is removed."""
        if not self.usable:
            return self.c[:, None]
        if self._design is not None:
            return self._design
        return _kernel_matrix(self.c, np.asarray(self.levels, dtype=float), self.shape,
                              self.length_scale)

    def describe(self):
        """The shape, its cost and any fallback, as a block a page or a report can print."""
        return {"shape": self.shape, "asked_for": self.asked_for, "usable": bool(self.usable),
                "effective_df": float(self.effective_df), "length_scale": self.length_scale,
                "n_settings": len(self.levels), "reason": self.reason, "why": self.why}

# =================================================================================================
# The two guards every offline model on this record has to pass through (decision 240).
#
# Panel B of the 2026-09-22 review named the two ways a model fitted on this participant can score
# well while carrying no fact about the brain: the pain scores resemble their neighbours in time, and
# the stimulation current moves the band power and the pain together. Both guards live here rather
# than inside any one model, so a new model cannot be written without them.
# =================================================================================================

def purged_time_blocked_folds(n, *, y=None, n_folds=5, embargo=None):
    """Held-out blocks of TIME, with the rows either side of each block removed from training.

    Cross-validation assumes the held-out rows are new. Pain ratings filed minutes apart are very
    nearly the same measurement, so a fold trained on the rows next to its test block has already
    seen most of the answer; the skill that comes back is the series' own persistence, and it looks
    exactly like a working model.

    So: the test rows are a contiguous stretch of time (never a random scatter of rows), and every
    training row within ``embargo`` rows of that stretch is dropped.

    **The gap is measured, not chosen.** With ``embargo=None`` it is the series' own decorrelation
    timescale, ``block_length_for(y)`` -- the same estimator that sizes the resampled intervals' blocks
    (the chance tests stopped reading it in decision 315, when they became rotations). A fixed gap typed into the code
    would be a guess about a quantity the data can state.

    ``y`` is the series whose dependence is being guarded against, usually the label. Returns a list
    of ``(train_index, test_index)`` arrays, one per fold, in time order; every row is in exactly one
    test block, and the training sets are smaller than the complement by the embargoed rows.
    """
    n = int(n)
    if n <= 0:
        return []
    n_folds = max(1, int(n_folds))
    if embargo is None:
        embargo = block_length_for(np.asarray(y, dtype=float), n) if y is not None else 1
    embargo = max(0, int(embargo))
    order = np.arange(n)
    out = []
    for block in np.array_split(order, min(n_folds, n)):
        if block.size == 0:
            continue
        lo, hi = int(block[0]) - embargo, int(block[-1]) + embargo
        train = order[(order < lo) | (order > hi)]
        out.append((train, block))
    return out


def _shape_in_words(shape, effective_df=None):
    """How a shape reads in a sentence, with what it cost, for a reader who is not reading code."""
    words = {"line": "as a straight line", "quadratic": "as a curve with a squared term",
             "spline": "as a curve (a 3-knot spline, which can turn over)",
             "squared_exponential": "as a smooth curve of any shape (squared-exponential kernel)",
             "matern32": "as a curve that can kink (Matern 3/2 kernel)",
             "rational_quadratic": "as a curve mixing scales (rational-quadratic kernel)",
             "per_setting": "as one level per delivered setting, with no shape assumed"}
    base = words.get(str(shape), f"as {shape}")
    if effective_df is None:
        return base
    return f"{base}, spending {float(effective_df):.1f} degrees of freedom"


def confound_gate(x, y, covar, *, label="the covariate", shape="spline", n_boot=1000, seed=0):
    """One candidate association, reported plainly AND with a third quantity taken out of it.

    Both numbers, both intervals, always -- never the adjusted value alone. A reader shown only the
    adjusted number cannot see how much the adjustment did, and a reader shown only the plain one
    cannot see whether there was anything there besides ``covar``. On this record ``covar`` is the
    stimulation current in force, which moves the band power and the pain together (decisions 232,
    234), and the PI's ruling of 2026-09-22 is that the adjusted value is reported descriptively and
    refuses nothing.

    ``shape`` is how the covariate is allowed to act (:data:`COVARIATE_SHAPES`). It defaults to the
    3-knot spline rather than a straight line, because a stimulation current can help up to a point
    and worsen above it, and a straight-line removal leaves that curve behind for the candidate to
    correlate with; the shape and the flexibility it spent are reported on the answer, and
    ``shape="line"`` gives the older behaviour.

    ``survives`` is ``True`` when the adjusted interval lies wholly one side of zero, ``False`` when
    it spans zero, and ``None`` when the adjustment could not be made at all -- a covariate that
    never moves, too few usable rows, or a candidate that is itself almost a straight line in the
    covariate. That third state is not a pass and not a failure, and it is never silently a pass.
    """
    rng = np.random.default_rng(int(seed))
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    c = np.asarray(covar, dtype=float)
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(c)
    out = {"label": str(label), "n": int(m.sum()), "r": None, "r_ci": (None, None),
           "r_adjusted": None, "r_adjusted_ci": (None, None), "drop": None,
           "survives": None, "reason": None, "verdict": None,
           "shape": str(shape), "effective_df": None, "shape_note": None}
    if m.sum() < 4:
        out["reason"] = (f"only {int(m.sum())} rows carry the candidate, the outcome and "
                         f"{label} together, which is too few to correlate")
        out["verdict"] = f"cannot be judged: {out['reason']}"
        return out
    xm, ym, cm = x[m], y[m], c[m]
    if np.std(xm) == 0 or np.std(ym) == 0:
        out["reason"] = "the candidate or the outcome never moves across these rows"
        out["verdict"] = f"cannot be judged: {out['reason']}"
        return out

    out["r"] = float(np.corrcoef(xm, ym)[0, 1])
    n = xm.size

    def _boot(fn):
        vals = []
        for _ in range(int(n_boot)):
            i = rng.integers(0, n, size=n)
            v = fn(i)
            if v is not None and np.isfinite(v):
                vals.append(float(v))
        if len(vals) < max(20, int(n_boot) // 10):
            return (None, None)
        return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))

    out["r_ci"] = _boot(lambda i: (np.corrcoef(xm[i], ym[i])[0, 1]
                                   if np.std(xm[i]) > 0 and np.std(ym[i]) > 0 else np.nan))

    if np.std(cm) == 0:
        out["reason"] = (f"{label} is constant across these rows, so there is nothing to take out; "
                         f"the plain value stands unadjusted")
        out["verdict"] = f"cannot be judged against {label}: {out['reason']}"
        return out

    sh = CovariateShape(cm, shape=shape)
    out["shape"], out["effective_df"], out["shape_note"] = sh.shape, sh.effective_df, sh.reason
    adj = partial_corr(xm, ym, cm, shape=sh.shape)
    if adj is None or not np.isfinite(adj):
        out["reason"] = (f"the candidate is almost a straight line in {label} across these rows, so "
                         f"taking it out leaves too little to correlate -- read that as the finding")
        out["verdict"] = f"cannot be judged against {label}: {out['reason']}"
        return out

    out["r_adjusted"] = float(adj)
    out["r_adjusted_ci"] = _boot(lambda i: partial_corr(xm[i], ym[i], cm[i], shape=sh.shape))
    out["drop"] = float(abs(out["r"]) - abs(out["r_adjusted"]))
    lo, hi = out["r_adjusted_ci"]
    if lo is None or hi is None:
        out["reason"] = f"the adjusted value could not be given an interval on {out['n']} rows"
        out["verdict"] = f"cannot be judged against {label}: {out['reason']}"
        return out
    out["survives"] = bool(lo * hi > 0)
    how = _shape_in_words(out["shape"], out["effective_df"])
    if out["survives"]:
        out["verdict"] = (f"survives {label}: {out['r']:+.3f} plainly, {out['r_adjusted']:+.3f} with "
                          f"{label} taken out {how} ({lo:+.3f} to {hi:+.3f}, {out['n']} rows)")
    else:
        out["verdict"] = (f"does not survive {label}: {out['r']:+.3f} plainly, "
                          f"{out['r_adjusted']:+.3f} with {label} taken out {how}, whose interval "
                          f"({lo:+.3f} to {hi:+.3f}, {out['n']} rows) covers zero")
    return out
