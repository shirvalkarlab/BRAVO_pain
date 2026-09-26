"""The research band detector, in two versions, saved as control analyses (the PI's rulings 5a-5c of
2026-09-25, `artifacts/research_2026-09-25_options/11_REVISED_PLAN.md` section 6; the design is
`04_band_detector.md`). Free of the database: the runner feeds it the page's own matched band power,
the device's own 3-second readings, the pain ratings and the current in force.

THE QUESTION. Is a pain signal in the bands being thrown away by the device's simplicity, or does
the flexible model only find patterns a device could never use? So one record is read twice:

  * THE RESEARCH VERSION keeps pain as a number (ruling 5b): every band of one sensing pair read
    together (a ridge regression, the same one `confound_diagnostic` uses), predicting the pain
    score itself on held-out blocks of time; scored by the rank correlation between the held-out
    prediction and the rating, taken within each held-out block (0 is chance; never folded -- a
    negative score means the model got the direction wrong on data it had not seen), with the
    held-out R-squared beside it (against the training rows' own mean, so drift lowers it).
  * THE DEVICE-SHAPED VERSION reads what the Percept RC could read (ruling 5b and 5c): ONE band, and
    pain split into two groups by the page's own split. Its area under the curve comes from a
    LOGISTIC REGRESSION of the two groups on that band's power (the PI's note), fitted on the
    training blocks and scored on the held-out ones, over the pairs of ratings inside one block. The band power is the device's own timing
    from the start: 3-second averaged readings, a reading counts only once it has held for the
    onset time, and the first readings after a recording starts are skipped for the start-up
    delay -- the values placed from this participant's record (decisions 150, 169), checked
    against their one home for the ranges (`DecodeCommon/device_ranges.py`, decision 168).

HOW BOTH ARE HELD HONEST. Held-out blocks of time with the neighbouring rows dropped, the gap from
pain's own persistence (decision 240, `stats_utils.purged_time_blocked_folds`). Every reading is
reported plainly AND with the stimulation current taken out as a 3-knot spline (decision 241),
fitted on the training rows only. Every reading carries a 95% interval that resamples whole
California days of the held-out rows, and a p from rotating the pain ratings in time (which keeps
their day-to-day persistence) and refitting the same pipeline, the adjusted reading against its own
rotations (decision 276). Raw band power only (decision 202). Nothing refuses anything: a
warning, never blocking (the PI, 2026-09-22); nothing here reaches a recommendation.

WHAT THE DEVICE TIMING DOES AND DOES NOT DO HERE. The device decides on averaged readings and acts
on a threshold crossing only once the reading has stayed past the threshold for the onset time.
So the band power at a rating is summarised by the onset window of readings the device would have
decided on, as the SUSTAINED LEVEL: the lowest reading in the window is the highest threshold the
device would have confirmed the power to be above; the highest reading is the lowest threshold it
would have confirmed the power to be below. Which of the two a switch would use (power rising or
falling with pain) is learned on the training blocks, like everything else. The blanking and the
ramp times act only after a switch -- a pause in re-classifying and the time the current takes to
move -- and a detector read at one moment, with no switch simulated, cannot use them; they are
recorded beside the result and not applied.
"""
import numpy as np

try:
    from modules.Biomarkers.routines import stats_utils as SU
    from modules.Biomarkers.routines import confound_diagnostic as CD
except ImportError:                                            # host spelling
    from Biomarkers.routines import stats_utils as SU
    from Biomarkers.routines import confound_diagnostic as CD

from . import stats as ST

MIN_ROWS = CD.MIN_ROWS
DEFAULT_SHAPE = CD.DEFAULT_SHAPE

#: The logistic regression's own penalty, on standardised power. Tiny: it exists only so that a
#: training block the band separates perfectly still returns a finite fit instead of an infinite
#: slope. It never decides a direction.
LOGISTIC_L2 = 1e-2

#: A contiguous run of 3-second pieces breaks where two pieces are further apart than this many
#: piece lengths (the pieces of one recording sit exactly one piece length apart).
RUN_GAP_PIECES = 1.5


# ------------------------------------------------------------------------------------------------
# small fitted models
# ------------------------------------------------------------------------------------------------

def _ridge_predict(Xtr, ytr, Xte):
    """The ridge regression `confound_diagnostic` reads every band with, returned as a PREDICTION of
    the score (its mean added back), so a held-out R-squared means something."""
    return CD._ridge_fit_predict(Xtr, ytr, Xte) + float(np.mean(ytr))


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35.0, 35.0)))


def logistic_fit(X, y, *, l2=LOGISTIC_L2, max_iter=50, tol=1e-9):
    """Logistic regression of a 0/1 label on the columns of ``X`` by Newton's method, on columns
    standardised with the fitting rows' own mean and spread. Returns ``(beta, mu, sd)``; the
    intercept is ``beta[0]`` and is never penalised."""
    X = np.asarray(X, float)
    X = X[:, None] if X.ndim == 1 else X
    y = np.asarray(y, float)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    A = np.column_stack([np.ones(len(y)), (X - mu) / sd])
    P = np.eye(A.shape[1]) * float(l2)
    P[0, 0] = 0.0
    beta = np.zeros(A.shape[1])
    p0 = float(np.clip(y.mean(), 1e-6, 1 - 1e-6))
    beta[0] = np.log(p0 / (1 - p0))
    for _ in range(int(max_iter)):
        p = _sigmoid(A @ beta)
        w = p * (1 - p)
        g = A.T @ (y - p) - P @ beta
        H = (A * w[:, None]).T @ A + P
        try:
            step = np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            break
        beta = beta + step
        if float(np.max(np.abs(step))) < tol:
            break
    return beta, mu, sd


def logistic_predict(fit, X):
    beta, mu, sd = fit
    X = np.asarray(X, float)
    X = X[:, None] if X.ndim == 1 else X
    return _sigmoid(np.column_stack([np.ones(len(X)), (X - mu) / sd]) @ beta)


def auc_signed(score, labels):
    """Area under the curve, signed and never folded (decision 8): 0.5 is chance, below it the
    held-out score ranked the groups the wrong way round."""
    return CD._auc(score, labels)


def _day_interval(fn, cols, days, *, n_boot=2000, seed=0):
    """95% interval of ``fn(*cols)`` resampling whole California days; NaNs with too few days or
    fewer than 100 usable resamples."""
    days = np.asarray(days)
    ud = np.unique(days)
    if ud.size < 5:
        return float("nan"), float("nan")
    idx = {d: np.flatnonzero(days == d) for d in ud}
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(int(n_boot)):
        ix = np.concatenate([idx[d] for d in rng.choice(ud, ud.size, replace=True)])
        v = fn(*(c[ix] for c in cols))
        if v is not None and np.isfinite(v):
            vals.append(v)
    if len(vals) < 100:
        return float("nan"), float("nan")
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(lo), float(hi)


def _rotation_p(observed, null_vals):
    """One-sided: how often the rotated ratings did at least as well. Returns (p, p50, p95, n)."""
    v = np.asarray([x for x in null_vals if x is not None and np.isfinite(x)], float)
    if observed is None or not np.isfinite(observed) or v.size == 0:
        return None, None, None, int(v.size)
    return (float((int((v >= observed).sum()) + 1) / (v.size + 1)), float(np.percentile(v, 50)),
            float(np.percentile(v, 95)), int(v.size))


def rotations(n, block, n_perm, rng):
    """``n_perm`` rotations of the ratings in time (`stats_utils.circular_block_perm_matrix`, which
    keeps their persistence), leaving out the identity. A rotation by zero IS the observed data;
    counted as a null draw it can only push the p upwards, and on a short record it is not rare --
    60 draws on 120 ratings drew it three times with seed 0 (found writing these tests, where it
    turned p 0.016 into 0.066 for a band the rotations otherwise never approached)."""
    n, n_perm = int(n), int(n_perm)
    if n_perm <= 0 or n < 2:
        return np.zeros((0, max(n, 0)), int)
    ident = np.arange(n)
    got = []
    for _ in range(20):
        m = SU.circular_block_perm_matrix(n, block, n_perm, rng)
        got.extend(r for r in m if not np.array_equal(r, ident))
        if len(got) >= n_perm:
            break
    return np.asarray(got[:n_perm], int).reshape(-1, n)


def _rows_and_folds(y, n_folds, embargo):
    n = len(y)
    if embargo is None:
        embargo = SU.block_length_for(y, n)
    embargo = int(embargo)
    return SU.purged_time_blocked_folds(n, y=y, n_folds=n_folds, embargo=embargo), embargo


def _spearman(a, b, block=None):
    """Rank correlation, taken WITHIN each held-out block when ``block`` is given (`stats.
    spearman_within`). Pooling held-out predictions across blocks mixes each block's own training
    mean into the ranking: when pain drifts over the record, an early high-pain block is predicted
    from later, lower-pain rows and a late block from earlier, higher ones, and a band carrying
    nothing ranks pain BACKWARDS (a constructed drift read -0.77; found 2026-09-25 when the first
    live run gave device areas as low as 0.04). Within a block that shift is one constant and cannot
    reorder anything."""
    m = np.isfinite(a) & np.isfinite(b)
    if int(m.sum()) < 5:
        return None
    v = ST.spearman_within(a[m], b[m], None if block is None else np.asarray(block)[m])
    return None if not np.isfinite(v) else float(v)


def auc_within_blocks(score, labels, block):
    """The area under the curve over the (worse, better) pairs that sit in the SAME held-out block,
    signed and never folded: each block's own area weighted by its number of pairs. Why within a
    block: see `_spearman` -- each block's probabilities carry its own training rows' base rate,
    and pooled across blocks that base rate, not the band, decides the ranking."""
    score, labels, block = np.asarray(score, float), np.asarray(labels, float), np.asarray(block)
    m = np.isfinite(score) & np.isfinite(labels)
    num = den = 0.0
    for b in np.unique(block[m]):
        k = m & (block == b)
        npos = int((labels[k] == 1).sum())
        nneg = int((labels[k] == 0).sum())
        if npos == 0 or nneg == 0:
            continue
        num += CD._auc(score[k], labels[k]) * npos * nneg
        den += npos * nneg
    return None if den == 0 else float(num / den)


def _r2(pred, target, base):
    m = np.isfinite(pred) & np.isfinite(target) & np.isfinite(base)
    if int(m.sum()) < 5:
        return None
    den = float(np.sum((target[m] - base[m]) ** 2))
    return None if den <= 0 else float(1.0 - np.sum((target[m] - pred[m]) ** 2) / den)


# ------------------------------------------------------------------------------------------------
# the research version: every band, pain as a number
# ------------------------------------------------------------------------------------------------

def _oof_research(X, y, folds, sh=None, *, columns_only=False):
    """Held-out prediction of the pain score from the columns of ``X``. With ``sh`` (a
    `CovariateShape` of the current) the current is taken out of every column AND out of the pain
    score, fitted on the training rows and applied to the held-out ones, so what is scored is the
    part of pain the current does not explain. Returns (prediction, target, fold-mean baseline,
    held-out block of each row)."""
    n = len(y)
    pred, target, base = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    blk = np.full(n, -1)
    need = max(8, X.shape[1] + 2)
    for k, (tr, te) in enumerate(folds):
        if tr.size < need or te.size == 0:
            continue
        if sh is not None:
            Xtr, Xte = sh.train_test_residuals(X, tr, te)
            ytr, yte = sh.train_test_residuals(y, tr, te)
        else:
            Xtr, Xte, ytr, yte = X[tr], X[te], y[tr], y[te]
        try:
            pred[te] = _ridge_predict(Xtr, ytr, Xte)
        except np.linalg.LinAlgError:
            continue
        target[te] = yte
        base[te] = float(np.mean(ytr))
        blk[te] = k
    return pred, target, base, blk


def _research_score(X, y, folds, sh=None):
    pred, target, base, blk = _oof_research(X, y, folds, sh)
    return _spearman(pred, target, blk), pred, target, base, blk


def research_reading(X, y, current, days, *, n_folds=5, embargo=None, shape=DEFAULT_SHAPE,
                     n_perm=200, n_boot=2000, seed=0, adjust=True):
    """The research version on one sensing pair: pain read as a number from every band at once,
    out of sample, three ways -- the current alone, every band, and every band with the current
    taken out of the bands and the pain -- each with a day-resampled interval and, for the two
    band readings, a p from rotating the ratings in time and refitting the same pipeline.

    ``X`` rows are pain ratings in time order, columns bands (raw band power); ``y`` the pain
    score; ``current`` the current in force on the pair's own side at each rating; ``days`` the
    California day of each rating. With ``adjust=False`` only the plain band reading is made (the
    same-setting stretch, where there is no current to take out)."""
    X = np.asarray(X, float)
    X = X[:, None] if X.ndim == 1 else X
    y = np.asarray(y, float)
    c = np.asarray(current, float) if current is not None else np.zeros(len(y))
    days = np.asarray(days)
    ok = np.isfinite(X).all(axis=1) & np.isfinite(y) & np.isfinite(c)
    out = {"n": int(ok.sum()), "n_days": int(len(set(days[ok].tolist()))), "folded": False,
           "score": "held-out rank correlation between the prediction and the rating (0 is chance)",
           "current_alone": None, "bands": None, "bands_without_current": None, "reason": None}
    if int(ok.sum()) < MIN_ROWS:
        out["reason"] = (f"{int(ok.sum())} ratings carry every band and a current, and {MIN_ROWS} "
                         f"are needed to hold blocks of time out")
        return out
    X, y, c, days = X[ok], y[ok], c[ok], days[ok]
    folds, embargo = _rows_and_folds(y, n_folds, embargo)
    out["embargo_rows"], out["n_folds"] = embargo, int(n_folds)
    rng = np.random.default_rng(int(seed))
    rot = rotations(len(y), SU.block_length_for(y, len(y)), n_perm, rng)

    def block(score, pred, target, base, blk, null_vals):
        m = np.isfinite(pred) & np.isfinite(target)
        lo, hi = _day_interval(_spearman, (pred[m], target[m], blk[m]), days[m], n_boot=n_boot, seed=seed)
        p, p50, p95, nn = _rotation_p(score, null_vals)
        return {"rho": score, "lo": lo, "hi": hi, "r2": _r2(pred, target, base),
                "n_scored": int(m.sum()), "p": p, "null_p50": p50, "null_p95": p95, "n_rotations": nn}

    s, pr, tg, bs, bk = _research_score(X, y, folds)
    out["bands"] = block(s, pr, tg, bs, bk, [_research_score(X, y[r], folds)[0] for r in rot])
    if not adjust:
        return out
    sh = SU.CovariateShape(c, shape=shape)
    out["shape"] = SU._shape_in_words(sh.shape, sh.effective_df if sh.usable else None)
    out["shape_note"] = sh.reason
    if not sh.usable:
        out["bands_without_current"] = {"reason": sh.reason}
        out["current_alone"] = {"reason": sh.reason}
        return out
    s, pr, tg, bs, bk = _research_score(sh.feature_columns(), y, folds)
    alone = block(s, pr, tg, bs, bk, [])
    alone.pop("p"); alone.pop("null_p50"); alone.pop("null_p95"); alone.pop("n_rotations")
    out["current_alone"] = alone
    s, pr, tg, bs, bk = _research_score(X, y, folds, sh)
    out["bands_without_current"] = block(s, pr, tg, bs, bk,
                                         [_research_score(X, y[r], folds, sh)[0] for r in rot])
    return out


# ------------------------------------------------------------------------------------------------
# the device-shaped version: one band, two groups, logistic regression
# ------------------------------------------------------------------------------------------------

def _oof_device(low, high, mid, y, folds, sh=None):
    """Held-out probability of the worse-pain group from ONE band's sustained level. On each
    training block the direction is learned first (the sign of the logistic slope on the window's
    middle reading): rising with pain means a switch would fire when power STAYS ABOVE a threshold,
    so the lowest reading of the onset window is the level the device confirmed; falling means it
    fires when power STAYS BELOW, and the highest reading is. The logistic regression is then fitted
    on that level. With ``sh`` the current is taken out of the band's readings first (fitted on the
    training rows), the pain groups untouched. Returns (probability, directions, held-out block)."""
    n = len(y)
    prob = np.full(n, np.nan)
    blk = np.full(n, -1)
    dirs = []
    V = np.column_stack([low, high, mid])
    for k, (tr, te) in enumerate(folds):
        if tr.size < 8 or te.size == 0 or len(np.unique(y[tr])) < 2:
            continue
        if sh is not None:
            Vtr, Vte = sh.train_test_residuals(V, tr, te)
        else:
            Vtr, Vte = V[tr], V[te]
        slope = logistic_fit(Vtr[:, 2], y[tr])[0][1]
        col = 0 if slope >= 0 else 1
        dirs.append("above" if col == 0 else "below")
        fit = logistic_fit(Vtr[:, col], y[tr])
        prob[te] = logistic_predict(fit, Vte[:, col])
        blk[te] = k
    return prob, dirs, blk


def _device_score(low, high, mid, y, folds, sh=None):
    prob, dirs, blk = _oof_device(low, high, mid, y, folds, sh)
    m = np.isfinite(prob)
    a = auc_within_blocks(prob, y, blk) if int(m.sum()) >= MIN_ROWS // 2 else None
    return a, prob, dirs, blk


def device_reading(low, high, mid, y01, current, days, *, n_folds=5, embargo=None,
                   shape=DEFAULT_SHAPE, n_perm=200, n_boot=2000, seed=0, adjust=True):
    """The device-shaped version on one band: the two pain groups (1 = the worse group) read by a
    logistic regression on that band's sustained level at the device's own timing, out of sample,
    three ways -- the current alone, the band, and the band with the current taken out of it --
    each an area under the curve with a day-resampled interval, the two band readings with a p
    from rotating the groups in time and refitting."""
    low, high, mid = (np.asarray(a, float) for a in (low, high, mid))
    y = np.asarray(y01, float)
    c = np.asarray(current, float) if current is not None else np.zeros(len(y))
    days = np.asarray(days)
    ok = np.isfinite(low) & np.isfinite(high) & np.isfinite(mid) & np.isfinite(y) & np.isfinite(c)
    out = {"n": int(ok.sum()), "n_worse": int(np.nansum(y[ok])), "folded": False,
           "n_days": int(len(set(days[ok].tolist()))),
           "score": "area under the curve of a held-out logistic regression (0.5 is chance)",
           "current_alone": None, "band": None, "band_without_current": None, "reason": None}
    if int(ok.sum()) < MIN_ROWS:
        out["reason"] = (f"{int(ok.sum())} ratings in the two pain groups carry a device-timed "
                         f"reading and a current, and {MIN_ROWS} are needed to hold blocks of time out")
        return out
    low, high, mid, y, c, days = low[ok], high[ok], mid[ok], y[ok], c[ok], days[ok]
    if len(np.unique(y)) < 2:
        out["reason"] = "the ratings with a reading fall in one pain group only"
        return out
    folds, embargo = _rows_and_folds(y, n_folds, embargo)
    out["embargo_rows"], out["n_folds"] = embargo, int(n_folds)
    rng = np.random.default_rng(int(seed))
    rot = rotations(len(y), SU.block_length_for(y, len(y)), n_perm, rng)

    def block(a, prob, blk, dirs, null_vals):
        m = np.isfinite(prob)
        lo, hi = _day_interval(auc_within_blocks, (prob[m], y[m], blk[m]), days[m], n_boot=n_boot, seed=seed)
        p, p50, p95, nn = _rotation_p(a, null_vals)
        up = sum(1 for d in dirs if d == "above")
        return {"auc": a, "lo": lo, "hi": hi, "n_scored": int(m.sum()), "p": p, "null_p50": p50,
                "null_p95": p95, "n_rotations": nn,
                "direction": ("rises with pain" if up == len(dirs) else "falls with pain" if up == 0
                              else f"rises with pain in {up} of {len(dirs)} training blocks")
                if dirs else None}

    a, prob, dirs, bk = _device_score(low, high, mid, y, folds)
    out["band"] = block(a, prob, bk, dirs, [_device_score(low, high, mid, y[r], folds)[0] for r in rot])
    if not adjust:
        return out
    sh = SU.CovariateShape(c, shape=shape)
    out["shape"] = SU._shape_in_words(sh.shape, sh.effective_df if sh.usable else None)
    out["shape_note"] = sh.reason
    if not sh.usable:
        out["band_without_current"] = {"reason": sh.reason}
        out["current_alone"] = {"reason": sh.reason}
        return out
    F = sh.feature_columns()
    prob = np.full(len(y), np.nan)
    bk = np.full(len(y), -1)
    for k, (tr, te) in enumerate(folds):
        if tr.size < 8 or te.size == 0 or len(np.unique(y[tr])) < 2:
            continue
        prob[te] = logistic_predict(logistic_fit(F[tr], y[tr]), F[te])
        bk[te] = k
    m = np.isfinite(prob)
    alone = block(auc_within_blocks(prob, y, bk) if int(m.sum()) >= MIN_ROWS // 2 else None, prob, bk, [], [])
    for k in ("p", "null_p50", "null_p95", "n_rotations", "direction"):
        alone.pop(k)
    out["current_alone"] = alone
    a, prob, dirs, bk = _device_score(low, high, mid, y, folds, sh)
    out["band_without_current"] = block(a, prob, bk, dirs,
                                        [_device_score(low, high, mid, y[r], folds, sh)[0] for r in rot])
    return out


# ------------------------------------------------------------------------------------------------
# the device's own timing
# ------------------------------------------------------------------------------------------------

def check_timing(placed_ms, ranges_ms):
    """Every placed value inside its device range. ``placed_ms`` and ``ranges_ms`` map a field name
    to milliseconds and to a (low, high) pair. Returns a list of the fields outside their range
    (empty when all are inside) -- a value the device could not be set to is not device timing."""
    bad = []
    for k, v in placed_ms.items():
        r = ranges_ms.get(k)
        if r is None or v is None:
            continue
        if not (float(r[0]) - 1e-9 <= float(v) <= float(r[1]) + 1e-9):
            bad.append(k)
    return bad


def device_windows(piece_t, piece_ok, piece_vals, rating_t, *, piece_s, averaging_s, onset_s,
                   startup_s, tol_s, direction="pro_first"):
    """The device's sustained reading at each rating, per band.

    ``piece_t`` are the centres of the 3-second pieces (epoch s), ``piece_ok`` whether each passed
    the platform's own gates (enough finite signal, no sample at the rail), ``piece_vals`` their
    raw band power (pieces x bands). Pieces sit one piece length apart inside a recording; a longer
    gap, or a piece that failed a gate, ends a run of readings. Inside a run:

      * an averaged reading is the mean of ``averaging_s / piece_s`` consecutive pieces
        (non-overlapping, as the device averages);
      * the first ``startup_s`` of each run are skipped (the start-up delay);
      * the device decides on ``onset_s / averaging_s`` consecutive readings (the onset hold).

    For each rating, the onset window the device would have decided on: with ``pro_first`` the
    first window starting at or after the rating, with ``prior`` the last one ending at or before
    it, with ``nearest`` whichever of the two is closer -- within ``tol_s`` either way.

    Returns ``(low, high, mid, start_t, info)``: per rating and band, the lowest, highest and middle
    (median) reading of that window (NaN where no window qualifies), the window's first-reading
    time per rating, and counts for the report.
    """
    t = np.asarray(piece_t, float)
    okp = np.asarray(piece_ok, bool) & np.isfinite(t)
    V = np.asarray(piece_vals, float)
    V = V[:, None] if V.ndim == 1 else V
    r = np.asarray(rating_t, float)
    nb = V.shape[1]
    k_avg = max(1, int(round(float(averaging_s) / float(piece_s))))
    n_on = max(1, int(round(float(onset_s) / (k_avg * float(piece_s)))))
    n_start = int(np.ceil(float(startup_s) / float(piece_s) - 1e-9))
    low = np.full((r.size, nb), np.nan)
    high, mid = low.copy(), low.copy()
    start_t = np.full(r.size, np.nan)
    info = {"pieces_per_reading": k_avg, "readings_per_decision": n_on, "startup_pieces": n_start,
            "n_runs": 0, "n_decision_windows": 0}
    o = np.argsort(t, kind="stable")
    t, okp, V = t[o], okp[o], V[o]
    t, V = t[okp], V[okp]
    if t.size == 0:
        info["n_matched"] = 0
        return low, high, mid, start_t, info
    brk = np.concatenate([[True], np.diff(t) > RUN_GAP_PIECES * float(piece_s)])
    run_start = np.flatnonzero(brk)
    run_end = np.concatenate([run_start[1:], [t.size]])
    info["n_runs"] = int(run_start.size)
    # averaged readings, run by run, the start-up pieces skipped first
    rd_t, rd_v, rd_run = [], [], []
    for k, (a, b) in enumerate(zip(run_start, run_end)):
        a2 = a + n_start
        m = (b - a2) // k_avg
        if m <= 0:
            continue
        seg = V[a2:a2 + m * k_avg].reshape(m, k_avg, nb)
        rd_v.append(np.nanmean(seg, axis=1) if k_avg > 1 else seg[:, 0, :])
        rd_t.append(t[a2:a2 + m * k_avg].reshape(m, k_avg).mean(axis=1))
        rd_run.append(np.full(m, k))
    if not rd_t:
        info["n_matched"] = 0
        return low, high, mid, start_t, info
    rt, rv, rr = np.concatenate(rd_t), np.concatenate(rd_v), np.concatenate(rd_run)
    # a decision window starts at reading i when readings i .. i+n_on-1 share a run
    nW = rt.size - n_on + 1
    if nW <= 0:
        info["n_matched"] = 0
        return low, high, mid, start_t, info
    valid = rr[:nW] == rr[n_on - 1:]
    ws = np.flatnonzero(valid)
    info["n_decision_windows"] = int(ws.size)
    if ws.size == 0:
        info["n_matched"] = 0
        return low, high, mid, start_t, info
    w_first, w_last = rt[ws], rt[ws + n_on - 1]
    half = 0.5 * k_avg * float(piece_s)
    direction = str(direction or "pro_first").lower()
    for i, x in enumerate(r):
        pick = None
        j = int(np.searchsorted(w_first, x - half, side="left"))
        after = j if j < ws.size and w_first[j] - x <= tol_s else None
        jb = int(np.searchsorted(w_last, x + half, side="right")) - 1
        before = jb if jb >= 0 and x - w_last[jb] <= tol_s else None
        if direction == "prior":
            pick = before
        elif direction == "nearest":
            cands = [c for c in (after, before) if c is not None]
            if cands:
                pick = min(cands, key=lambda c: min(abs(w_first[c] - x), abs(w_last[c] - x)))
        else:
            pick = after
        if pick is None:
            continue
        w = rv[ws[pick]:ws[pick] + n_on]
        low[i], high[i], mid[i] = np.nanmin(w, axis=0), np.nanmax(w, axis=0), np.nanmedian(w, axis=0)
        start_t[i] = w_first[pick]
    info["n_matched"] = int(np.isfinite(start_t).sum())
    return low, high, mid, start_t, info


# ------------------------------------------------------------------------------------------------
# the stretch where the current never moved
# ------------------------------------------------------------------------------------------------

def longest_same_current_run(current, *, decimals=2):
    """Indices of the longest run of consecutive ratings (in time order) at one current on the
    pair's own side. There is nothing to take out there, so it is a cleaner, smaller test of the
    same question; a run is broken by any rating at a different current or with none."""
    c = np.round(np.asarray(current, float), int(decimals))
    best, cur, start = (0, 0), None, 0
    for i, v in enumerate(np.append(c, np.nan)):
        same = cur is not None and np.isfinite(v) and v == cur
        if not same:
            if cur is not None and (i - start) > (best[1] - best[0]):
                best = (start, i)
            cur, start = (v if np.isfinite(v) else None), i
    return np.arange(best[0], best[1])


# ------------------------------------------------------------------------------------------------
# the corrections and the plain-English reading
# ------------------------------------------------------------------------------------------------

def add_q(rows, p_key, q_key):
    """Benjamini-Hochberg over the rows given (one family), written into each row; a missing p
    counts as 1 (`stats.bh_q`)."""
    ps = [((r.get(p_key) if isinstance(r, dict) else None)) for r in rows]
    qs = ST.bh_q([np.nan if p is None else p for p in ps])
    for r, q in zip(rows, qs):
        if isinstance(r, dict) and r.get(p_key) is not None:
            r[q_key] = float(q)
    return rows


def _fmt(v, d=3):
    return "n/a" if v is None or not np.isfinite(v) else f"{v:.{d}f}"


def _ci(b, key):
    if not b or b.get(key) is None:
        return "could not be read" + (f" ({b.get('reason')})" if b and b.get("reason") else "")
    s = f"{b[key]:+.3f}" if key == "rho" else f"{b[key]:.3f}"
    if b.get("lo") is not None and np.isfinite(b.get("lo")):
        s += f" ({b['lo']:+.3f} to {b['hi']:+.3f})" if key == "rho" else f" ({b['lo']:.3f} to {b['hi']:.3f})"
    if b.get("p") is not None:
        s += f", p {b['p']:.3f}"
        if b.get("q") is not None:
            s += f", q {b['q']:.3f}"
    return s


def research_sentences(rows, pair_name):
    out = []
    for r in rows:
        d = r.get("reading") or {}
        head = f"{pair_name(r['pair'])}, {r['seconds']:g} s of signal ({d.get('n', 0)} ratings on {d.get('n_days', 0)} days)"
        if d.get("reason"):
            out.append(f"{head}: {d['reason']}.")
            continue
        out.append(f"{head}: pain predicted out of sample (rank correlation, 0 is chance) from the "
                   f"current alone {_ci(d.get('current_alone'), 'rho')}; every band "
                   f"{_ci(d.get('bands'), 'rho')}; every band with the current taken out "
                   f"{_ci(d.get('bands_without_current'), 'rho')}.")
        s = r.get("same_current") or {}
        if s.get("reading"):
            sd = s["reading"]
            if sd.get("reason"):
                out.append(f"   At one unchanged current ({s.get('current_mA')} mA, {s.get('from')} to "
                           f"{s.get('to')}): {sd['reason']}.")
            else:
                out.append(f"   At one unchanged current ({s.get('current_mA')} mA, {s.get('from')} to "
                           f"{s.get('to')}, {sd.get('n')} ratings): every band {_ci(sd.get('bands'), 'rho')}.")
    return out


def device_sentences(pairs, pair_name):
    out = []
    for p in pairs:
        rows = p.get("bands") or []
        read = [r for r in rows if (r.get("reading") or {}).get("band")]
        if not read:
            why = next(((r.get("reading") or {}).get("reason") for r in rows if (r.get("reading") or {}).get("reason")),
                       p.get("reason") or "no band could be read")
            out.append(f"{pair_name(p['pair'])}: {why}.")
            continue
        d0 = read[0]["reading"]
        best = max(read, key=lambda r: r["reading"]["band"].get("auc") or 0.0)
        b = best["reading"]
        sig = [r for r in read if (r["reading"]["band"].get("q") or 1.0) < 0.05]
        sig_adj = [r for r in read if ((r["reading"].get("band_without_current") or {}).get("q") or 1.0) < 0.05]
        alone = d0.get("current_alone") or {}
        out.append(f"{pair_name(p['pair'])} ({d0.get('n')} ratings in the two pain groups, "
                   f"{d0.get('n_days')} days): the current alone {_ci(alone, 'auc')}; the best single "
                   f"band, {best['centre_hz']:g} Hz ({b['band'].get('direction')}"
                   f"{'; it carries a folded multiple of the rate in force, flagged not dropped' if best.get('carries_folded_multiple') else ''}), "
                   f"{_ci(b['band'], 'auc')}, "
                   f"with the current taken out {_ci(b.get('band_without_current'), 'auc')}. "
                   f"{len(sig)} of {len(read)} bands clear q < 0.05 plainly and {len(sig_adj)} with the "
                   f"current taken out.")
    return out
