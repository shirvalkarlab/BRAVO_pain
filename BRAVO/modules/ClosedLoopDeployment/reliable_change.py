"""An individual reliable-change threshold for RCS08, reported alongside the Farrar et al. 2001
population minimal-clinically-important-difference (MCID), never in place of it (PI request,
2026-09-08; design doc `artifacts/design_2026-09-08_biomarker_pipeline_and_closed_loop_deployment.md`
§4, check 6).

WHY A SECOND BAR NEXT TO THE POPULATION MCID. Farrar's ~2 points / ~30% on the 0-10 scale is a
group-derived number: the smallest average change a study found patients themselves called
"much improved." It says nothing about how noisy any one person's own ratings are day to day.
RCS08's ratings might be steadier than the group this participant's own noise floor could sit
above OR below 2 points, and only this participant's own data can say which.

THE METHOD, AND WHERE IT DEPARTS FROM THE TEXTBOOK FORMULA. Jacobson & Truax (1991) define a
reliable-change index as (post - pre) / SE_diff, with SE_diff built from a population test-retest
reliability coefficient this project has no way to measure for RCS08 alone. The substitution made
here: instead of a reliability coefficient, use the standard deviation of RCS08's OWN ratings
collected under one UNCHANGED stimulation condition (`StimOptimizer.adapter.exposure_epochs`'s own
definition of an epoch -- every setting a patient could feel held fixed). If nothing about therapy
changed, any spread in those ratings is measurement and moment-to-moment noise, not a treatment
effect, which is exactly the standard-error-of-measurement quantity Jacobson & Truax's own formula
is built from -- estimated directly, with no reliability coefficient required. The pooled
within-epoch standard deviation is the classic ANOVA within-groups estimator, treating each epoch
as one repeated-measures "session" under one fixed condition.

WHAT THIS DOES NOT CLAIM. A change smaller than this threshold is not "no change" -- it is a
change this participant's own noise could plausibly produce even with nothing therapeutic
happening, so it should not, on its own, be read as evidence the therapy worked. The three-state
discipline (decision 9) applies here exactly as it does to every other deployment gate: "not
assessed" is the honest answer when there is not enough same-condition history to estimate the
noise, never a manufactured pass.
"""
import numpy as np
from scipy import stats as _st

#: Farrar CR, Young JP Jr, LaMoreaux L, Werth JL, Poole RM. "Clinical importance of changes in
#: chronic pain intensity measured on an 11-point numerical pain rating scale." Pain. 2001. The
#: smallest average change patients themselves rated "much improved," on the 0-10 NRS -- a
#: population benchmark, reported here only as a secondary, explicitly group-derived cross-check.
FARRAR_MCID_POINTS = 2.0
FARRAR_MCID_FRACTION = 0.30

#: Two-sided 95% confidence, computed rather than hand-rounded to 1.96.
RELIABLE_CHANGE_Z = float(_st.norm.ppf(0.975))

#: Below this many usable ratings, one epoch's own standard deviation is too noisy an estimate of
#: itself to pool -- the same floor `attach_pros`'s own per-epoch SD/mean/count columns imply are
#: needed before an epoch's spread means anything.
MIN_RATINGS_PER_EPOCH = 2

#: Below this many pooled degrees of freedom, the participant's own same-condition noise estimate
#: is not assessed rather than reported on flimsy grounds -- five is a low bar deliberately, since
#: refusing entirely would make this check unusable early in a participant's own record; the pooled
#: degrees of freedom are always reported alongside the estimate so a reader can judge for
#: themselves how much history stands behind it.
MIN_POOLED_DF = 5


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return np.nan
    return x if np.isfinite(x) else np.nan


def pooled_same_condition_sd(epochs, item, *, min_n_per_epoch=MIN_RATINGS_PER_EPOCH,
                             min_total_df=MIN_POOLED_DF):
    """RCS08's own pooled standard deviation of one pain-report item, estimated from repeated
    ratings collected under an unchanged stimulation condition.

    ``epochs`` is `StimOptimizer.adapter.attach_pros`'s own return shape: one row per contiguous,
    unchanged-settings epoch, columns ``{item}``, ``{item}_sd``, ``{item}_n`` among them. ``item``
    is one of `StimOptimizer.adapter.PRO_ITEMS` (e.g. ``"nrs"``).

    Returns a dict, never raising: ``pooled_sd``, ``df`` (pooled degrees of freedom), ``n_epochs``
    (how many epochs contributed), and ``reason`` (only set when ``pooled_sd`` is NaN, naming why).
    """
    out = dict(pooled_sd=np.nan, df=0, n_epochs=0, reason=None)
    if epochs is None or len(epochs) == 0:
        out["reason"] = "no epochs of unchanged stimulation settings are available"
        return out

    sd_col, n_col = f"{item}_sd", f"{item}_n"
    if sd_col not in epochs.columns or n_col not in epochs.columns:
        out["reason"] = f"no {item!r} ratings were matched to any epoch"
        return out

    ns = epochs[n_col].to_numpy(dtype=float)
    sds = epochs[sd_col].to_numpy(dtype=float)
    ok = np.isfinite(ns) & np.isfinite(sds) & (ns >= min_n_per_epoch)
    if not ok.any():
        out["reason"] = (f"no epoch has at least {min_n_per_epoch} {item!r} ratings to estimate "
                         "its own spread")
        return out

    ns, sds = ns[ok], sds[ok]
    dfs = ns - 1.0
    df = float(np.sum(dfs))
    if df < min_total_df:
        out["df"] = int(round(df))
        out["n_epochs"] = int(ok.sum())
        out["reason"] = (f"only {df:.0f} pooled degrees of freedom of same-condition {item!r} "
                         f"history are available, below the {min_total_df} required")
        return out

    pooled_variance = float(np.sum(dfs * sds ** 2) / df)
    out["pooled_sd"] = float(np.sqrt(pooled_variance)) if pooled_variance >= 0 else np.nan
    out["df"] = int(round(df))
    out["n_epochs"] = int(ok.sum())
    return out


def reliable_change_verdict(pre_mean, post_mean, pooled_sd_result, *, n_pre=1, n_post=1,
                            item_label="pain rating", scale_max=10.0):
    """Combine two means (e.g. a baseline condition's average rating and a candidate condition's)
    with `pooled_same_condition_sd`'s own result into a plain-language verdict, reporting the
    individual reliable-change index alongside the Farrar population MCID as a secondary,
    explicitly group-derived cross-check -- never the other way around.

    ``n_pre``/``n_post`` are how many ratings each mean itself averages; a single rating on each
    side (the default) is the most conservative case, since ``SE_diff`` shrinks as either count
    grows.
    """
    pre_mean, post_mean = _f(pre_mean), _f(post_mean)
    out = dict(
        change=np.nan, individual_reliable_change_threshold=np.nan,
        individual_rci=np.nan, individual_verdict="not assessed",
        pooled_same_condition_sd=_f((pooled_sd_result or {}).get("pooled_sd")),
        pooled_same_condition_df=int((pooled_sd_result or {}).get("df", 0) or 0),
        population_mcid_points=FARRAR_MCID_POINTS,
        population_mcid_fraction=FARRAR_MCID_FRACTION,
        population_verdict="not assessed",
        reason=None,
    )
    if not (np.isfinite(pre_mean) and np.isfinite(post_mean)):
        out["reason"] = "the two mean ratings being compared are not both available"
        return out

    change = post_mean - pre_mean
    out["change"] = change

    # The population cross-check needs only the two means, so it is reported even when the
    # individual index below cannot be (decision 9's own discipline: report what can be assessed).
    fraction_reliable = (abs(change) / pre_mean >= FARRAR_MCID_FRACTION) if pre_mean > 0 else False
    points_reliable = abs(change) >= FARRAR_MCID_POINTS
    out["population_verdict"] = (
        "the change meets the Farrar et al. 2001 population benchmark for a clinically important "
        "change" if (points_reliable or fraction_reliable) else
        "the change does not meet the Farrar et al. 2001 population benchmark for a clinically "
        "important change")

    pooled_sd = out["pooled_same_condition_sd"]
    if not np.isfinite(pooled_sd):
        out["reason"] = ((pooled_sd_result or {}).get("reason")
                         or "RCS08's own same-condition rating variance is not assessed")
        return out
    if pooled_sd == 0:
        out["reason"] = "RCS08's own same-condition ratings show no variation at all to compare against"
        return out

    se_diff = pooled_sd * float(np.sqrt(1.0 / max(n_pre, 1) + 1.0 / max(n_post, 1)))
    rci = change / se_diff
    out["individual_reliable_change_threshold"] = RELIABLE_CHANGE_Z * se_diff
    out["individual_rci"] = rci
    out["individual_verdict"] = (
        f"a change in {item_label} of this size is reliably outside RCS08's own same-condition "
        "rating noise" if abs(rci) >= RELIABLE_CHANGE_Z else
        f"a change in {item_label} of this size cannot be distinguished from RCS08's own ordinary "
        "same-condition rating fluctuation")
    return out
