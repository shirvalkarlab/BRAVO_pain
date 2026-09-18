"""Layer 1 of the shared matching design (`artifacts/design_2026-09-08_biomarker_pipeline_and_
closed_loop_deployment.md` §2, `artifacts/plan_2026-09-08_shared_matching_layer.md` Track A): the
one algorithm that decides which pain report matches which sample, with the independence rule the
richest of the four existing matchers already has (`Biomarkers.routines.streaming_psd.
_match_to_pro` for the direction handling, `build_pooled_detail_from_matrix`'s own per-
(group, rating) refractory-gap cap) -- read from that source and ported here, not re-derived, so
this module's behavior is provably the same algorithm rather than a fresh guess at one.

WHY THIS LIVES IN DecodeCommon AND DUPLICATES RATHER THAN IMPORTS. `DecodeCommon` is this
project's leaf module: small, stable, imported by every consumer, and importing nothing from
Biomarkers, StimOptimizer or ClosedLoopDeployment (its own dependency-direction rule, already
followed by `canon_channel`, `to_epoch`, and the frequency helpers in `representation.py`). The
matching algorithm below is copied from `streaming_psd.py` rather than imported from it for the
same reason those helpers are duplicated rather than imported: a shared leaf module must not
create a dependency edge back into a statistics module.

WHAT CHANGED, AND WHAT DID NOT, VS. THE SOURCE. The three-direction matching logic
("nearest"/"prior"/"pro_first") and the post-hoc refractory-gap cap are unchanged, value for
value. The one generalization: the source groups the refractory cap's "one rating cannot absorb an
unlimited burst" rule by electrode CHANNEL specifically; this module groups by a caller-supplied
``group_keys`` array instead, so the same rule applies whether the caller's independent unit is a
channel, a (channel, band) pair, or something else -- the design doc's own Layer 1 box specifies
"(band-power sample, pain value, timestamp, rating-cluster id) tuples, per (channel, band)".
"""
import numpy as np

#: The independence rule closes decision 73's own finding: two of the four existing matching
#: mechanisms (`per_pro_lsb`, `align_pros`) have no cap at all, letting one report or one
#: recording be claimed by an unbounded number of matches -- the same pseudoreplication shape
#: decision 17's impedance term was rejected for. Callers that want today's uncapped behavior can
#: still ask for it explicitly by passing ``max_per_rating=None``.
DEFAULT_MAX_PER_RATING = None
DEFAULT_REFRACTORY_MIN = 0.0


def matched_samples(sample_times, sample_values, pro_times, pro_values, *, tolerance_min,
                    direction="nearest", group_keys=None,
                    max_per_rating=DEFAULT_MAX_PER_RATING,
                    refractory_min=DEFAULT_REFRACTORY_MIN):
    """Match each sample to a pain report within a time window.

    ``sample_times``/``sample_values`` (N,): the candidate samples (a band-power reading, a
    recording, anything with a timestamp and a value). ``pro_times``/``pro_values``: the pain
    report timestamps and their chosen metric value, in the caller's own original order.
    ``group_keys`` (N,), optional: the independent unit the refractory cap and ``pro_first``
    matching are scoped to (e.g. sensing contact, or a (contact, band) tuple) -- when omitted every
    sample is treated as one single group, matching the source algorithm's degenerate case.

    ``direction``:
      * ``"nearest"``   -- each sample matched to its closest report in either time direction.
      * ``"prior"``     -- each sample matched to the nearest report AT OR AFTER it (the sample
                            precedes the rating it explains; the causal direction for closed-loop
                            deployment).
      * ``"pro_first"`` -- walk reports in time order and let each one claim up to
                            ``max_per_rating`` closest UNCLAIMED samples per group within
                            tolerance; requires ``group_keys`` and ``max_per_rating``.

    ``max_per_rating``/``refractory_min``: the independence cap. For ``pro_first`` the cap is
    enforced during matching itself (a sample can only ever be claimed once, so no further
    post-hoc cap is needed). For ``"nearest"``/``"prior"``, a post-hoc pass keeps, per (group,
    matched report), the ``max_per_rating`` samples closest to the report, dropping any candidate
    within ``refractory_min`` minutes of one already kept -- the same greedy, closeness-first,
    temporally-spread selection `build_pooled_detail_from_matrix` already performs. Pass
    ``max_per_rating=None`` for today's uncapped behavior (never recommended for a new call site,
    kept only so an existing caller's current behavior can be reproduced exactly during migration).

    Returns a dict: ``matched_value`` (N,) -- the report's value, NaN where unmatched;
    ``dt_min`` (N,) -- signed minutes report-minus-sample, NaN where unmatched; ``rating_cluster_id``
    (N,) int -- the index of the matched report in the caller's own original ``pro_times``
    ordering, ``-1`` where unmatched; ``n_dropped_by_cap`` int -- how many samples the post-hoc
    cap un-matched (always 0 for ``pro_first``, where the cap is enforced during matching).
    """
    n = len(sample_times)
    labels = np.full(n, np.nan)
    dt_min = np.full(n, np.nan)
    rating_cluster_id = np.full(n, -1, dtype=int)
    n_dropped_by_cap = 0

    pt = np.asarray(pro_times, dtype=float)
    pv = np.asarray(pro_values, dtype=float)
    order = np.argsort(pt)              # order[k] = original index of the k-th sorted report
    pt, pv = pt[order], pv[order]
    if pt.size == 0 or tolerance_min is None or tolerance_min <= 0:
        return dict(matched_value=labels, dt_min=dt_min, rating_cluster_id=rating_cluster_id,
                    n_dropped_by_cap=n_dropped_by_cap)
    tol_s = float(tolerance_min) * 60.0
    ts_arr = np.asarray(sample_times, dtype=float)
    groups = (np.asarray(group_keys, dtype=object) if group_keys is not None
             else np.zeros(n, dtype=object))

    if direction == "pro_first":
        if max_per_rating is None or int(max_per_rating) < 1:
            direction = "nearest"       # misuse: fall through rather than silently match nothing
        else:
            claimed = np.zeros(n, dtype=bool)
            kpr = int(max_per_rating)
            for k in range(pt.size):
                t_pro, pv_k = pt[k], pv[k]
                if not np.isfinite(t_pro) or not np.isfinite(pv_k):
                    continue
                near = np.isfinite(ts_arr) & ~claimed & (np.abs(ts_arr - t_pro) <= tol_s)
                if not near.any():
                    continue
                for grp in np.unique(groups[near]):
                    cand = np.where(near & (groups == grp))[0]
                    if cand.size == 0:
                        continue
                    d_cand = np.abs(ts_arr[cand] - t_pro)
                    take = cand[np.argsort(d_cand)[:kpr]]
                    labels[take] = pv_k
                    dt_min[take] = (t_pro - ts_arr[take]) / 60.0
                    rating_cluster_id[take] = int(order[k])
                    claimed[take] = True
            return dict(matched_value=labels, dt_min=dt_min, rating_cluster_id=rating_cluster_id,
                    n_dropped_by_cap=n_dropped_by_cap)

    if direction != "pro_first":
        for i, t in enumerate(sample_times):
            if not np.isfinite(t):
                continue
            pos = int(np.searchsorted(pt, t))
            best, best_d = -1, None
            if direction == "prior":
                k = pos
                if 0 <= k < pt.size:
                    d = pt[k] - t
                    if 0 <= d <= tol_s:
                        best, best_d = k, d
            else:
                for k in (pos - 1, pos):
                    if 0 <= k < pt.size:
                        d = abs(pt[k] - t)
                        if d <= tol_s and (best_d is None or d < best_d):
                            best, best_d = k, d
            if best >= 0:
                labels[i] = pv[best]
                dt_min[i] = (pt[best] - t) / 60.0
                rating_cluster_id[i] = int(order[best])

    if max_per_rating is not None and int(max_per_rating) >= 1:
        ref_s = float(refractory_min or 0.0) * 60.0
        matched_i = np.where(np.isfinite(labels) & (rating_cluster_id >= 0))[0]
        per_group = {}
        for i in matched_i:
            per_group.setdefault((groups[i], int(rating_cluster_id[i])), []).append(i)
        for _, idxs in per_group.items():
            if len(idxs) <= 1:
                continue
            idxs = np.asarray(idxs)
            order_close = idxs[np.argsort(np.abs(dt_min[idxs]))]
            kept_t = []
            for i in order_close:
                if len(kept_t) >= int(max_per_rating):
                    labels[i], dt_min[i], rating_cluster_id[i] = np.nan, np.nan, -1
                    n_dropped_by_cap += 1
                    continue
                ti = float(ts_arr[i])
                if ref_s > 0 and any(abs(ti - tk) < ref_s for tk in kept_t):
                    labels[i], dt_min[i], rating_cluster_id[i] = np.nan, np.nan, -1
                    n_dropped_by_cap += 1
                    continue
                kept_t.append(ti)

    return dict(matched_value=labels, dt_min=dt_min, rating_cluster_id=rating_cluster_id,
                    n_dropped_by_cap=n_dropped_by_cap)
