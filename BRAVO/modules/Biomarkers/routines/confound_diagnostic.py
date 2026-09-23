"""What a decoder built on this record could learn, and how much of it is the stimulation current.

WHY THIS RUNS BEFORE ANY DECODER. On this participant the stimulation current moves the band power
and moves the pain. A model reading every band on both sides can therefore score above chance while
carrying nothing about the brain at all -- it has found the current, which the clinician already
knows. The 2026-09-22 review panel made this check the condition on building any decoder here, so
that whoever proposes one starts from a measured ceiling rather than from hope.

WHAT IT MEASURES. The pain label, read three ways, all out of sample:

  1. from the **stimulation current alone** -- the floor a decoder has to beat to be worth anything;
  2. from **every band**, as they are;
  3. from **every band with the current taken out of each one**, fitted inside the training rows and
     applied to the held-out rows, so the removal itself cannot leak.

against a null that keeps pain's own day-to-day persistence (the rotation test the rest of this
module already uses), because a label that drifts slowly scores above 0.5 by chance alone.

HOW IT HOLDS DATA OUT. Blocks of TIME, with the rows either side of each block dropped from training
(`stats_utils.purged_time_blocked_folds`); the gap is the label's own decorrelation timescale, not a
number anybody chose. Ratings filed minutes apart are nearly the same measurement, and a model
trained on the rows next to its test block has already seen the answer.

THE SCORE IS NOT FOLDED. Elsewhere in this module an undirected single-band screen reports
max(AUC, 1-AUC), because a band that separates downwards separates. That is wrong for a fitted
model: an out-of-sample score of 0.30 means the model got the direction wrong on data it had not
seen, which is a failure, and printing 0.70 for it would invert the finding.

Nothing here refuses anything. It reports (the PI, 2026-09-22: a warning, never blocking).
"""
import numpy as np

from . import stats_utils as _su

#: Below this many usable rows the answer is "too few rows", which is an answer. Five folds of a
#: forty-row record leave eight rows a fold before the embargo takes its share.
MIN_ROWS = 40

#: The shape the covariate is allowed to take when it is removed from each band. A straight line
#: cannot remove an effect that turns over, and on this record the stimulation current may: measured
#: 2026-09-22, a 3-knot spline explains 29.4% of pain's scatter on the left sensing pair against
#: 25.7% for a straight line and puts the lowest pain at 3.21 mA rather than at the top of the range.
#: The spline is the cheapest shape that can turn over at all, which is why it is the default and a
#: kernel is not: the three kernels spend 4 to 6 degrees of freedom on 53 reports and do not agree
#: with each other about where the turn is (decision 241).
DEFAULT_SHAPE = "spline"

#: Ridge strength for the linear model read across every band at once. Small records with dozens of
#: correlated bands overfit instantly without one; this is a plain regularised least squares on
#: standardised features, fitted inside each training fold, chosen because a reader can follow it.
RIDGE_LAMBDA = 10.0


def _auc(score, labels):
    """Signed AUC: the chance that a randomly chosen positive row scores above a negative one.

    Not folded -- see the module docstring. Returns None where it is not defined.
    """
    score = np.asarray(score, dtype=float)
    labels = np.asarray(labels, dtype=float)
    m = np.isfinite(score) & np.isfinite(labels)
    score, labels = score[m], labels[m]
    pos = labels == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    from scipy.stats import rankdata
    ranks = rankdata(score)
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _standardise(train, apply_to):
    mu, sd = train.mean(axis=0), train.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    return (train - mu) / sd, (apply_to - mu) / sd


def _ridge_fit_predict(Xtr, ytr, Xte):
    """Least squares with a ridge penalty on standardised features; the prediction is used as a
    score, which is all an AUC needs (a logistic link would rank the rows identically here)."""
    Xtr, Xte = _standardise(Xtr, Xte)
    A = np.column_stack([np.ones(len(Xtr)), Xtr])
    P = np.eye(A.shape[1]) * RIDGE_LAMBDA
    P[0, 0] = 0.0                                    # never penalise the intercept
    beta = np.linalg.solve(A.T @ A + P, A.T @ (ytr - ytr.mean()))
    return np.column_stack([np.ones(len(Xte)), Xte]) @ beta


def all_bands_auc(X, y, *, folds, covar=None, shape=DEFAULT_SHAPE, label="every band"):
    """One out-of-fold score for a model reading every column of ``X`` at once.

    With ``covar``, the covariate is taken out of every column first, with the removal FITTED INSIDE
    EACH TRAINING FOLD and applied to the held-out rows -- fitting it on all the rows would let a
    held-out row influence its own adjustment, which is the leak this whole module exists to avoid.
    ``shape`` is how the covariate is allowed to act (`stats_utils.COVARIATE_SHAPES`): a straight
    line cannot remove an effect that turns over, and a stimulation current can.

    Returns ``{"auc", "n_scored", "n_features", "folded": False, "label", "shape",
    "covariate_effective_df", "reason"}``.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    c = None if covar is None else np.asarray(covar, dtype=float)
    out = {"auc": None, "n_scored": 0, "n_features": int(X.shape[1]), "folded": False,
           "label": str(label), "reason": None, "shape": None, "covariate_effective_df": None,
           "shape_note": None}
    usable = np.isfinite(X).all(axis=1) & np.isfinite(y)
    if c is not None:
        usable &= np.isfinite(c)
    if int(usable.sum()) < MIN_ROWS:
        out["reason"] = (f"too few rows carry a pain score and every band together "
                         f"({int(usable.sum())}, and {MIN_ROWS} are needed to hold blocks out)")
        return out
    sh = None
    if c is not None:
        sh = _su.CovariateShape(c[usable], shape=shape)
        out["shape"], out["shape_note"] = sh.shape, sh.reason
        out["covariate_effective_df"] = float(sh.effective_df)
        if not sh.usable:
            out["reason"] = sh.reason
            return out
        # The shape is built on the usable rows, so the fold indices have to speak in those terms.
        position = np.full(len(y), -1, dtype=int)
        position[np.where(usable)[0]] = np.arange(int(usable.sum()))
        Xu = X[usable]
    score = np.full(len(y), np.nan)
    need = max(8, X.shape[1] + 2)
    for tr, te in folds:
        tr = tr[usable[tr]]
        te = te[usable[te]]
        if tr.size < need or te.size == 0:
            continue
        Xtr, Xte = X[tr], X[te]
        if sh is not None:
            Xtr, Xte = sh.train_test_residuals(Xu, position[tr], position[te])
        try:
            score[te] = _ridge_fit_predict(Xtr, y[tr], Xte)
        except np.linalg.LinAlgError:
            continue
    scored = np.isfinite(score) & usable
    out["n_scored"] = int(scored.sum())
    if out["n_scored"] < MIN_ROWS // 2:
        if out["n_scored"] == 0 and int(usable.sum()) < need + MIN_ROWS // 5:
            # The commonest way this record refuses: more bands than the training rows that are left
            # once a block of time is held out. Say that, rather than "0 rows were scored" -- a
            # reader has to know whether the answer is missing or whether the record is too small to
            # ask the question, and a model with more bands than rows would not be an answer either.
            out["reason"] = (f"{int(usable.sum())} rows carry every one of these {X.shape[1]} bands, "
                             f"and holding a block of time out of that leaves fewer training rows "
                             f"than there are bands, so this many bands cannot be read together on "
                             f"this record")
        else:
            out["reason"] = f"only {out['n_scored']} rows could be scored out of sample"
        return out
    out["auc"] = _auc(score[scored], y[scored])
    if out["auc"] is None:
        out["reason"] = "the held-out rows carry only one class of the label"
    return out


def pre_build_diagnostic(X, y_binary, current, *, band_labels=None, n_folds=5, embargo=None,
                         shape=DEFAULT_SHAPE, n_perm=200, seed=0):
    """The whole check, as one answer a reader can follow top to bottom.

    ``X`` is one row per pain report and one column per band (both sides together); ``y_binary`` is
    the pain label, 1 for the worse half; ``current`` is the stimulation current in force when each
    report was filed (`routines/stim_current.py`).
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y_binary, dtype=float)
    c = np.asarray(current, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    n = len(y)
    if embargo is None:
        embargo = _su.block_length_for(y, n)
    embargo = int(embargo)
    folds = _su.purged_time_blocked_folds(n, y=y, n_folds=n_folds, embargo=embargo)

    # The current alone is read under the SAME shape the removal uses, so the floor a decoder has
    # to beat is not an easier floor than the adjustment assumes. `feature_columns` turns the shape
    # into columns: the basis itself for a line, a curve or one level per setting, and one bump per
    # delivered setting for a kernel.
    shape_of_current = _su.CovariateShape(c, shape=shape)
    alone = all_bands_auc(shape_of_current.feature_columns() if shape_of_current.usable
                          else c[:, None], y, folds=folds,
                          label="the stimulation current alone")
    plain = all_bands_auc(X, y, folds=folds, label="every band")
    adjusted = all_bands_auc(X, y, folds=folds, covar=c, shape=shape,
                             label="every band with the stimulation current taken out")

    # The null: rotate the label, keeping its own persistence, and refit everything each time. A
    # model's out-of-sample score is not centred on 0.5 when the label drifts, so the null is the
    # only honest reference -- this is the same rotation the single-band screens already use.
    null = {"p50": None, "p95": None, "n_perm": 0, "block": embargo}
    p_value = None
    if plain["auc"] is not None and int(n_perm) > 0:
        rng = np.random.default_rng(int(seed))
        block = _su.block_length_for(y, n)
        idx = _su.circular_block_perm_matrix(n, block, int(n_perm), rng)
        vals = []
        for row in idx:
            got = all_bands_auc(X, y[row], folds=folds)
            if got["auc"] is not None:
                vals.append(float(got["auc"]))
        if vals:
            vals = np.asarray(vals, float)
            null = {"p50": float(np.percentile(vals, 50)), "p95": float(np.percentile(vals, 95)),
                    "n_perm": int(vals.size), "block": int(block)}
            p_value = float((int((vals >= plain["auc"]).sum()) + 1) / (vals.size + 1))
    plain["p_value"] = p_value

    out = {"current_alone": alone, "bands_plain": plain, "bands_adjusted": adjusted, "null": null,
           "n_rows": int(n), "n_bands": int(X.shape[1]), "n_folds": int(n_folds),
           "embargo_rows": embargo, "held_out_in_blocks_of_time": True,
           "covariate_shape": adjusted.get("shape") or shape_of_current.shape,
           "covariate_effective_df": (adjusted.get("covariate_effective_df")
                                      if adjusted.get("covariate_effective_df") is not None
                                      else float(shape_of_current.effective_df)),
           "covariate_shape_note": adjusted.get("shape_note") or shape_of_current.reason,
           "covariate_shape_in_words": _su._shape_in_words(
               adjusted.get("shape") or shape_of_current.shape,
               adjusted.get("covariate_effective_df")),
           "covariate_length_scale": shape_of_current.length_scale,
           "band_labels": list(band_labels) if band_labels is not None else None,
           "why": ("how much of what a decoder could learn here is the stimulation current: the "
                   "label read from the current alone, from every band, and from every band with "
                   "the current taken out, all on held-out blocks of time"),
           "blocking": False,
           "consequence": ("a warning, never blocking (the PI, 2026-09-22): this refuses nothing "
                           "and changes no recommendation")}
    out["verdict"] = _verdict(out)
    return out


def _verdict(d):
    plain, adj, alone, null = d["bands_plain"], d["bands_adjusted"], d["current_alone"], d["null"]
    if plain["auc"] is None:
        return (f"cannot be measured on this record: {plain['reason']}")
    bits = [f"reading every band out of sample scores {plain['auc']:.3f}"]
    if null["p95"] is not None:
        bits.append(f"against a null of {null['p50']:.3f} (95th {null['p95']:.3f}) that keeps pain's "
                    f"own persistence")
    if alone["auc"] is not None:
        bits.append(f"the stimulation current alone scores {alone['auc']:.3f}")
    if adj["auc"] is None:
        bits.append(f"and the adjusted reading could not be made ({adj['reason']})")
        return "; ".join(bits)
    bits.append(f"with the current taken out of every band {d.get('covariate_shape_in_words')} it "
                f"scores {adj['auc']:.3f}")
    inside_null = null["p95"] is not None and adj["auc"] <= null["p95"]
    if inside_null:
        bits.append("which the null covers, so what a decoder would find here does not survive the "
                    "stimulation current")
    else:
        bits.append("which the null does not cover, so something in the bands survives the "
                    "stimulation current")
    return "; ".join(bits)
