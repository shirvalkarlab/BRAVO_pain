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

#: THE SHORT-GAP ESTIMATOR, replacing the pooled within-epoch one (PI, 2026-09-10, decision 111).
#:
#: Jacobson & Truax's noise is meant to be the same state measured twice over a SHORT gap. The
#: first version of this file pooled the spread of every rating inside a stretch of unchanged
#: stimulation settings -- and on this record those stretches run for days (median 49 h, longest
#: 43 days for RCS08), so the number carried weeks of real pain moving with sleep, weather and
#: activity while the device sat still. Measured: within-stretch spread did not even grow with
#: stretch length (Spearman rho = -0.01), because the patient rates several times a day and the
#: ratings being compared were mostly hours apart whatever the stretch's length. The right unit
#: is therefore the gap between two consecutive ratings, not the length of the stretch.
#:
#: WHAT COUNTS AS A PAIR: two consecutive ratings of the same item, filed inside the same stretch
#: of unchanged settings (so the therapy is the same for both), no more than `MAX_PAIR_GAP_HOURS`
#: apart. The PI chose ONE HOUR: on RCS08 this patient re-rates within the hour often enough for
#: it to be a real measurement (23 pairs from 10 stretches), and when they do the answer is almost
#: always identical and never off by more than one point. That is the tightest honest reading of
#: "how much does this patient's rating move when nothing has changed".
#:
#: DUPLICATES ARE REMOVED FIRST. Eight of those 23 pairs were two entries at the same minute with
#: the same value -- a second entry within a minute of the first is not a second reading, it is the
#: same reading recorded twice, and leaving it in pulls the noise toward zero for free. The later
#: entry of any same-minute pair is dropped and counted (`n_dropped_same_minute`) so the removal
#: is visible.
#:
#: THE ESTIMATE. For n consecutive differences d, the pooled SD of a single rating is
#: sqrt(mean(d^2) / 2), because a difference of two equally noisy readings has twice the variance
#: of one. Each pair contributes one degree of freedom.
MAX_PAIR_GAP_HOURS = 1.0
SAME_MINUTE_SECONDS = 60.0

#: Below this many pairs the floor is reported as not assessed rather than on flimsy grounds. Five
#: is a low bar deliberately, for the same reason the old pooled floor used five degrees of
#: freedom: refusing entirely would make this check unusable early in a participant's own record,
#: and the pair count is always reported beside the estimate so a reader can judge for themselves.
MIN_PAIRS = 5


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return np.nan
    return x if np.isfinite(x) else np.nan


def short_gap_pairwise_sd(rating_times_s, rating_values, epoch_starts_s, epoch_ends_s, *,
                          max_gap_hours=MAX_PAIR_GAP_HOURS, washin_s=60.0,
                          same_minute_s=SAME_MINUTE_SECONDS, min_pairs=MIN_PAIRS):
    """The participant's own short-gap rating noise for ONE pain item, from consecutive ratings
    filed within `max_gap_hours` of each other under unchanged stimulation settings.

    ``rating_times_s`` and ``rating_values`` are one entry per filed rating (seconds since the
    epoch, and the score; non-finite entries are ignored). ``epoch_starts_s`` / ``epoch_ends_s``
    are `StimOptimizer.adapter.exposure_epochs`'s own stretches of unchanged settings, in the
    same units. A rating inside the first ``washin_s`` of a stretch is left out, as `attach_pros`
    leaves it out, because the patient may still be feeling the change.

    Returns a dict, never raising, in the shape `reliable_change_verdict` reads: ``pooled_sd``,
    ``df`` (one per pair), ``n_pairs``, ``n_epochs`` (stretches that contributed a pair),
    ``n_dropped_same_minute``, ``max_gap_hours``, and ``reason`` (set only when ``pooled_sd`` is
    NaN, naming why).
    """
    out = dict(pooled_sd=np.nan, df=0, n_pairs=0, n_epochs=0, n_dropped_same_minute=0,
               max_gap_hours=float(max_gap_hours), reason=None)
    t = np.asarray(rating_times_s, dtype=float)
    v = np.asarray(rating_values, dtype=float)
    if t.size == 0 or t.size != v.size:
        out["reason"] = "no ratings were handed in for this item"
        return out
    ok = np.isfinite(t) & np.isfinite(v)
    t, v = t[ok], v[ok]
    if t.size < 2:
        out["reason"] = "fewer than two ratings of this item exist"
        return out
    order = np.argsort(t, kind="stable")
    t, v = t[order], v[order]

    starts = np.asarray(epoch_starts_s, dtype=float)
    ends = np.asarray(epoch_ends_s, dtype=float)
    if starts.size == 0 or starts.size != ends.size:
        out["reason"] = "no stretches of unchanged stimulation settings are available"
        return out

    diffs, epochs_hit = [], set()
    for i in range(starts.size):
        if not (np.isfinite(starts[i]) and np.isfinite(ends[i])):
            continue
        m = (t >= starts[i] + float(washin_s)) & (t < ends[i])
        if m.sum() < 2:
            continue
        ti, vi = t[m], v[m]
        # Drop the later entry of any two filed within the same minute: one reading recorded twice.
        keep = np.ones(ti.size, dtype=bool)
        for k in range(1, ti.size):
            if ti[k] - ti[k - 1] < float(same_minute_s):
                keep[k] = False
        out["n_dropped_same_minute"] += int((~keep).sum())
        ti, vi = ti[keep], vi[keep]
        if ti.size < 2:
            continue
        gaps_h = (ti[1:] - ti[:-1]) / 3600.0
        close = gaps_h <= float(max_gap_hours)
        if close.any():
            diffs.extend((vi[1:] - vi[:-1])[close].tolist())
            epochs_hit.add(i)

    n = len(diffs)
    out["n_pairs"] = n
    out["df"] = n
    out["n_epochs"] = len(epochs_hit)
    if n < int(min_pairs):
        out["reason"] = (f"only {n} pair(s) of ratings filed within {max_gap_hours:g} h of each "
                         f"other under unchanged settings, below the {min_pairs} required")
        return out
    d = np.asarray(diffs, dtype=float)
    out["pooled_sd"] = float(np.sqrt(np.mean(d ** 2) / 2.0))
    return out


def reliable_change_verdict(pre_mean, post_mean, pooled_sd_result, *, n_pre=1, n_post=1,
                            item_label="pain rating", scale_max=10.0):
    """Combine two means (e.g. a baseline condition's average rating and a candidate condition's)
    with `short_gap_pairwise_sd`'s own result into a plain-language verdict, reporting the
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
