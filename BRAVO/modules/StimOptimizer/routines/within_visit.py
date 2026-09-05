"""Amplitude-response evidence built from WITHIN-VISIT clinic steps, not chronic exposure epochs.

WHY THIS EXISTS ALONGSIDE ``lfp_evidence.build_all``. That builder reads exposure epochs whose
amplitude is entangled with calendar time, so era blocking is the only defence against the
confound. On RCS08 that defence fails in both directions and for opposite reasons:

  * the FULL-RECORD window fails on capture DIRECTION in all 18 bands, because the two capture arms
    straddle two programming regimes and power therefore RISES across them; and
  * the FIVE-ERA window fails on capture SEPARATION in 14 of 18, because restricting to recent eras
    removes the low amplitudes and the contrast collapses from 2.9 mA to 1.0.

Inside one clinic visit the rate, pulse width and contacts are fixed and the whole amplitude ladder
happens within hours, so there is no time confound to adjust for. The measured within-visit span on
RCS08 reaches 3.5 mA, and the resulting capture separation runs 0.53 to 0.89 per cell rather than
0.41 to 0.93 — which is why separation stops being the binding constraint.

The output is deliberately the SAME shape ``lfp_evidence.build_all`` returns, a
``{(channel, hemisphere, rate): LfpEvidence}`` mapping plus an audit frame, so ``screen_cells`` and
the whole gate downstream of it run unchanged. Only the evidence source is swapped.

DEPENDENCY NOTE. Nothing here imports Biomarkers. The harmonic-landing flag that accompanies the
per-band scores needs ``Biomarkers.routines.analytics.harmonic_landings_hz`` and therefore lives in
``ClosedLoopDeployment.clinic_steps``, which already depends on both. Keeping the flag out of this
file is what lets StimOptimizer stay free of that import.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import stage_gate as GATE
from .lfp_evidence import EvidenceAudit

#: Seconds after a step's onset that are discarded as ramp transient.
#:
#: The clinic sheets themselves warn that the amplitude ramps rather than stepping, and the ramp
#: analysis measured the stimulation-frequency artefact still RISING at 150 s -- far beyond the
#: 30-45 s the sheets suggest. 45 s is therefore the sheets' own figure and not a safe one; it is
#: used because a longer exclusion leaves almost no settled signal (the median step is 60 s), and
#: the residual risk is recorded rather than removed.
RAMP_EXCLUDE_S = 45.0

#: Amplitude bin width for forming capture arms, in mA.
#:
#: A JUDGEMENT. The programmer steps finely while a capture arm needs rows: one RCS08 visit carried
#: 29 distinct amplitude levels across 36 steps, so grouping on the raw level leaves roughly one
#: step per level and no arm reaches ``lfp_response.MIN_ROWS_PER_ARM``. 0.5 mA is the coarsest
#: grouping that still separates clinically distinct settings.
AMP_ARM_BIN_MA = 0.5

#: Minimum settled tiles a step must contribute before its median is used. Two is the arithmetic
#: minimum for a median to mean anything, and it is deliberately low because the median RCS08 step
#: yields only about five settled tiles. The thinness is reported per step, not hidden.
MIN_SETTLED_TILES = 2


def amplitude_arm_bins(amp_mA, bin_mA=AMP_ARM_BIN_MA):
    """Amplitudes rounded to the declared arm bin. See :data:`AMP_ARM_BIN_MA` for why."""
    a = np.asarray(amp_mA, dtype=float)
    if not np.isfinite(bin_mA) or bin_mA <= 0:
        raise ValueError(f"bin_mA must be positive and finite, got {bin_mA}")
    return np.round(a / float(bin_mA)) * float(bin_mA)


def step_settled_medians(step_t0, step_window_s, tile_t, tile_power, *,
                         ramp_s=RAMP_EXCLUDE_S, min_tiles=MIN_SETTLED_TILES):
    """One power vector per step: the median across that step's SETTLED tiles.

    THE UNIT IS THE STEP, NOT THE TILE. A device capture is a short recording summarised to one
    number, so the step median is its analogue, and a median rather than a mean because a capture
    window can contain a transient.

    WHAT THE CHOICE PROTECTS, measured rather than assumed. It does NOT protect the standardised
    separation: on a construction with a large between-step spread and a small within-step one,
    separation came out 2.54 at step level and 2.64 at tile level, a ratio of 1.04, with the slope
    identical to four decimals. A Cohen-style d divides by the pooled within-ARM spread, and an arm
    contains many different steps whichever unit is used, so between-step variation dominates the
    denominator either way. What tiles inflate is the INFERENCE: on that same construction the
    slope p-value went from 4.7e-54 to 1.7e-63 -- ten orders of magnitude -- on an n inflated
    twentyfold from 24 to 480 with the cluster count unchanged. Cluster-robust standard errors do
    not rescue it, because the clusters stay fixed while the rows inside each one multiply.

    ``tile_t`` must be sorted ascending. Returns ``(medians, n_tiles, kept)``.
    """
    t0 = np.asarray(step_t0, dtype=float)
    win = np.asarray(step_window_s, dtype=float)
    tt = np.asarray(tile_t, dtype=float)
    tp = np.asarray(tile_power, dtype=float)
    if t0.shape != win.shape:
        raise ValueError(f"step_t0 {t0.shape} and step_window_s {win.shape} must match")
    if tp.ndim != 2 or tp.shape[0] != tt.size:
        raise ValueError(f"tile_power must be (n_tiles, n_centres) aligned to tile_t "
                         f"({tt.size}); got {tp.shape}")
    if tt.size and np.any(np.diff(tt) < 0):
        raise ValueError("tile_t must be sorted ascending")

    meds, counts, kept = [], [], []
    for i, (a, w) in enumerate(zip(t0, win)):
        if not np.isfinite(a) or not np.isfinite(w) or w <= ramp_s:
            continue
        i0 = int(np.searchsorted(tt, a + ramp_s))
        i1 = int(np.searchsorted(tt, a + w))
        if i1 - i0 < int(min_tiles):
            continue
        meds.append(np.nanmedian(tp[i0:i1, :], axis=0))
        counts.append(i1 - i0)
        kept.append(i)
    if not meds:
        n_cen = tp.shape[1] if tp.ndim == 2 else 0
        return (np.empty((0, n_cen)), np.empty(0, dtype=int), np.empty(0, dtype=int))
    return np.vstack(meds), np.asarray(counts, dtype=int), np.asarray(kept, dtype=int)


def build_within_visit_evidence(steps, *, channel, hemisphere, rate_hz, centers_hz,
                                tile_t, tile_power, band_width_hz=5.0,
                                amp_col=None, visit_col="visit", ramp_s=RAMP_EXCLUDE_S,
                                bin_mA=AMP_ARM_BIN_MA, min_tiles=MIN_SETTLED_TILES,
                                mode_requires=None):
    """One :class:`stage_gate.LfpEvidence` from clinic steps, plus its audit.

    ``steps`` needs ``t0`` (epoch seconds), ``window_s``, a per-hemisphere amplitude column and a
    visit label. The VISIT supplies both the era and the cluster, which is the whole point of the
    design: amplitude varies WITHIN a visit, so blocking on visit removes calendar time without
    absorbing the amplitude contrast. On the chronic epochs the opposite held -- each old era
    carried a single amplitude, so its dummy absorbed the era entirely and contributed nothing.
    """
    aud = EvidenceAudit(channel=str(channel), hemisphere=str(hemisphere), rate_hz=float(rate_hz))
    S = pd.DataFrame(steps)
    aud.n_psd_rows = int(np.asarray(tile_t).size)
    if amp_col is None:
        amp_col = f"amp_mA_{hemisphere}"
    for need in ("t0", "window_s", visit_col, amp_col):
        if need not in S.columns:
            aud.reason_unusable = f"steps frame has no {need!r} column"
            return None, aud
    aud.amp_col, aud.era_col = amp_col, visit_col
    aud.era_source = f"clinic visit ({visit_col!r}); amplitude varies WITHIN each visit"

    rate_num = pd.to_numeric(S.get("rate_hz"), errors="coerce")
    n0 = len(S)
    S = S[np.isclose(rate_num, float(rate_hz))] if rate_num is not None else S
    aud.n_dropped_other_rate = n0 - len(S)
    n0 = len(S)
    S = S[pd.to_numeric(S[amp_col], errors="coerce") > 0]
    aud.n_dropped_stim_off = n0 - len(S)
    S = S.dropna(subset=["t0", "window_s", amp_col])
    if not len(S):
        aud.reason_unusable = (f"no step at {rate_hz:g} Hz with stimulation on and a usable "
                               f"{amp_col}")
        return None, aud

    med, cnt, kept = step_settled_medians(S["t0"].to_numpy(float),
                                          S["window_s"].to_numpy(float),
                                          tile_t, tile_power,
                                          ramp_s=ramp_s, min_tiles=min_tiles)
    aud.n_joined = int(len(kept))
    aud.n_dropped_no_epoch = int(len(S) - len(kept))
    aud.n_final = int(len(kept))
    if not len(kept):
        aud.reason_unusable = (f"no step had at least {min_tiles} tiles in its settled window "
                               f"(ramp exclusion {ramp_s:g} s)")
        return None, aud

    K = S.iloc[kept]
    amp = amplitude_arm_bins(pd.to_numeric(K[amp_col], errors="coerce").to_numpy(float), bin_mA)
    era = K[visit_col].astype(str).to_numpy()
    aud.amplitudes = tuple(sorted(np.unique(np.round(amp, 2)).tolist()))
    aud.n_eras = int(pd.Series(era).nunique())
    if len(aud.amplitudes) < 2:
        aud.reason_unusable = (f"only one binned amplitude ({aud.amplitudes}) — a capture needs "
                               f"two therapeutic amplitudes to contrast")
        return None, aud

    cen = np.asarray(centers_hz, dtype=float)
    if med.shape[1] != cen.size:
        raise ValueError(f"centers_hz has {cen.size} entries but the tile power has "
                         f"{med.shape[1]} columns")
    bp = {(round(float(c), 6), round(float(band_width_hz), 6)): med[:, j]
          for j, c in enumerate(cen)}
    kw = {} if mode_requires is None else {"mode_requires": mode_requires}
    ev = GATE.LfpEvidence(amplitude_mA=amp, band_power=bp, era=era, cluster=era,
                          hemisphere=str(hemisphere), **kw)
    return ev, aud


def build_all_within_visit(steps, *, centers_hz, tiles_by_channel,
                           hemispheres=("Left", "Right"), rates=None, channels=None, **kw):
    """Within-visit evidence for every (channel, hemisphere, rate) cell.

    ``tiles_by_channel`` maps a channel name to ``(tile_t, tile_power)``. Returns
    ``(dict, audit_frame)`` in the same shape as :func:`lfp_evidence.build_all`, so
    ``lfp_evidence.screen_cells`` consumes it without modification -- the majority-of-bands rule,
    the era-significance condition and the amplitude ceiling all apply identically.
    """
    S = pd.DataFrame(steps)
    chans = list(channels) if channels is not None else sorted(tiles_by_channel)
    if rates is None:
        rates = sorted(pd.to_numeric(S.get("rate_hz"), errors="coerce").dropna().unique().tolist())
    out, rows = {}, []
    for ch in chans:
        tt, tp = tiles_by_channel.get(ch, (np.empty(0), np.empty((0, len(centers_hz)))))
        for h in hemispheres:
            for r in rates:
                ev, aud = build_within_visit_evidence(
                    S, channel=ch, hemisphere=h, rate_hz=r, centers_hz=centers_hz,
                    tile_t=tt, tile_power=tp, **kw)
                rows.append({**aud.__dict__, "usable": ev is not None})
                if ev is not None:
                    out[(ch, h, float(r))] = ev
    return out, pd.DataFrame(rows)


# =================================================================================================
# SEARCHING THE BAND AXIS: A CLUSTER-BASED PERMUTATION TEST
# =================================================================================================
# WHY THE MAJORITY RULE CANNOT FIND A LOCALISED SIGNAL. `screen_cells` requires a MAJORITY of the
# scanned bands to respond, and that rule exists for a good reason: the 18 bands are 5 Hz wide on a
# 1 Hz grid, so they overlap heavily and the best of eighteen is the maximum of a correlated family
# rather than a finding. But the rule is a poor instrument for an effect confined to a few adjacent
# centres. A response localised to, say, 24.5-27.5 Hz occupies four of eighteen bands and can never
# reach 50%, however large and however consistent it is. On RCS08 that is not hypothetical: the
# within-visit screen found ONE_THREE_LEFT responding in 5 and 6 of 18 bands with 3 and 4
# significant negative era-blocked slopes, refused on the majority rule alone.
#
# THE STANDARD ANSWER IS A CLUSTER-BASED PERMUTATION TEST (Maris & Oostenveld 2007, J Neurosci
# Methods 164(1):177-190, doi:10.1016/j.jneumeth.2007.03.024). Compute a statistic per band,
# threshold it, group the survivors into runs of ADJACENT same-signed bands, and take each run's
# summed statistic as its cluster mass. Then permute the condition labels, recompute, and keep the
# largest cluster mass per replicate. The observed largest cluster is compared against that
# distribution. Because neighbouring bands are correlated, a real localised effect accumulates mass
# that noise does not, which is exactly the sensitivity the majority rule lacks.
#
# THREE LIMITATIONS, ENCODED BECAUSE THEY DECIDE HOW THE RESULT MAY BE USED.
#
#   1. IT ESTABLISHES EXISTENCE, NOT LOCATION. The test licenses "this cell responds to amplitude
#      somewhere in the adaptive window" and NOT "the response is at 24.5-27.5 Hz". This is not a
#      quibble; it is the documented property of the method (Sassenhagen & Draschkow 2019,
#      Psychophysiology 56(6):e13335, "Cluster-based permutation tests of MEG/EEG data do not
#      establish significance of effect latency or location"; see also Rousselet 2025, Eur J
#      Neurosci, on cluster-sum inference offering only weak family-wise control). THEREFORE THIS
#      FUNCTION MUST NEVER FEED THE DEPLOYABILITY GATE. Programming a device requires naming one
#      band, and this test cannot name one. It is a search instrument that decides whether a cell
#      is worth collecting targeted data on.
#   2. IT IS PRONE TO MISSING NARROW EFFECTS. An effect spanning very few bands accumulates little
#      mass, so its cluster does not stand out from noise clusters (Groppe, Urbach & Kutas 2011).
#      A null result here is therefore weak evidence of absence, and is reported as such.
#   3. IT DEPENDS ON THE CLUSTER-FORMING THRESHOLD, which is a free parameter and not a
#      significance level. Maris & Oostenveld are explicit that the threshold need not come from
#      any null distribution without invalidating the test, but it does change sensitivity, so
#      `t_threshold` is reported on the result and a sweep is cheap. Threshold-free cluster
#      enhancement (Smith & Nichols 2009, NeuroImage 44(1):83-98) removes the dependence and is
#      the natural upgrade if the choice ever turns out to matter here.
#
# WHY THE PERMUTATION NULL ALSO REPAIRS SOMETHING ELSE. The per-band statistic is a cluster-robust
# t, and the wild-bootstrap work earlier in this project established that this variance estimator is
# ANTI-CONSERVATIVE at the cluster counts available here (6 to 12 visits). Under a permutation null
# that ceases to matter for the family-wise p-value, because the SAME statistic, with the same bias,
# is recomputed on every permuted replicate: the bias is common to observation and null and cancels
# in the comparison. The per-band t values reported alongside remain biased and must not be read as
# significances on their own.

#: Cluster-forming threshold on the per-band |t|. Two is close to the conventional two-sided 5%
#: critical value for a comfortable residual degrees of freedom, and is a THRESHOLD rather than a
#: test level (see limitation 3 above).
CLUSTER_T_THRESHOLD = 2.0


def _band_t_cluster_robust(logp, amp, era, cluster):
    """Cluster-robust t on the amplitude coefficient of ``logp ~ amp + C(era)``.

    Hand-rolled for speed, because the permutation loop refits this thousands of times. It is the
    SAME model ``lfp_response.assess_response`` fits with statsmodels, and a test asserts the two
    agree on real data -- a fast reimplementation that silently disagreed with the gate's estimator
    would make the search and the verdict answer different questions.
    """
    y = np.asarray(logp, dtype=float)
    a = np.asarray(amp, dtype=float)
    ok = np.isfinite(y) & np.isfinite(a)
    if ok.sum() < 4:
        return np.nan
    y, a = y[ok], a[ok]
    era_v = np.asarray(era)[ok]
    clus = np.asarray(cluster)[ok]

    cols = [np.ones_like(a), a]
    levels = [u for u in pd.unique(era_v)][1:]          # drop one level as the reference
    for u in levels:
        cols.append((era_v == u).astype(float))
    X = np.column_stack(cols)
    if np.linalg.matrix_rank(X) < X.shape[1]:
        return np.nan
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta

    # CR0 sandwich: sum over clusters of (X_g' u_g)(X_g' u_g)'
    meat = np.zeros((X.shape[1], X.shape[1]))
    for g in pd.unique(clus):
        m = clus == g
        Xu = X[m].T @ resid[m]
        meat += np.outer(Xu, Xu)
    V = XtX_inv @ meat @ XtX_inv

    # STATSMODELS' FINITE-SAMPLE CORRECTION, applied so this matches the gate's estimator exactly.
    # Raw CR0 omits it; measured against `smf.ols(...).fit(cov_type="cluster")` the two differed by
    # a ratio of 1.134349 on a 90-row, 6-cluster construction, against a predicted
    # sqrt(G/(G-1) * (N-1)/(N-K)) of 1.134349 -- agreement to six decimals, which identified the
    # discrepancy as exactly this factor rather than a modelling difference.
    #
    # It does NOT change the family-wise p-value. N, K and G are fixed across permutations, so the
    # factor is a constant that scales every t and therefore every cluster mass identically in the
    # observation and in the null, and cancels in the comparison. It is applied because the
    # cluster-forming THRESHOLD and the reported per-band t values would otherwise mean something
    # different here than in `assess_response`, which a reader comparing the two would not expect.
    G = int(pd.unique(clus).size)
    N, K = X.shape[0], X.shape[1]
    if G > 1 and N > K:
        V = V * (G / (G - 1.0)) * ((N - 1.0) / (N - K))

    se = float(np.sqrt(V[1, 1])) if V[1, 1] > 0 else np.nan
    if not np.isfinite(se) or se == 0:
        return np.nan
    return float(beta[1] / se)


def _clusters_along_axis(t, threshold):
    """Runs of ADJACENT same-signed bands whose |t| clears the threshold, with their masses.

    Adjacency is position on the ordered centre axis, so the caller must pass centres in order.
    Returns ``[(i_start, i_stop_exclusive, mass), ...]``.
    """
    t = np.asarray(t, dtype=float)
    sup = np.isfinite(t) & (np.abs(t) >= float(threshold))
    out, i = [], 0
    while i < t.size:
        if not sup[i]:
            i += 1
            continue
        s = np.sign(t[i])
        j = i
        while j < t.size and sup[j] and np.sign(t[j]) == s:
            j += 1
        out.append((i, j, float(np.sum(t[i:j]))))
        i = j
    return out


def band_cluster_permutation(power_by_center, amp_mA, visits, *, n_perm=2000, seed=0,
                             t_threshold=CLUSTER_T_THRESHOLD, bin_mA=AMP_ARM_BIN_MA):
    """Family-wise corrected answer to "does this cell respond to amplitude ANYWHERE?"

    The null permutes amplitude BETWEEN STEPS WITHIN EACH VISIT. That is the exchangeability the
    design actually supports: visits differ in overall power level and in which amplitudes were
    tried, so shuffling across visits would break the blocking and test a different, weaker null.
    Shuffling within a visit tests exactly "within this visit, amplitude carries no information
    about band power", which is the question.

    Returns the observed clusters, the largest cluster's family-wise p, and the resolution floor of
    that p. Read :data:`band_cluster_permutation` module notes above before using it to justify
    anything: it CANNOT name a band.
    """
    centers = sorted(float(c) for c in power_by_center)
    if len(centers) < 3:
        return {"available": False, "reason": f"a cluster test over the band axis needs at least "
                                              f"three centres, got {len(centers)}"}
    Y = np.column_stack([np.asarray(power_by_center[c], dtype=float) for c in centers])
    amp = amplitude_arm_bins(amp_mA, bin_mA)
    vis = np.asarray(visits)
    if not (Y.shape[0] == amp.size == vis.size):
        raise ValueError(f"power rows {Y.shape[0]}, amplitude {amp.size} and visits {vis.size} "
                         f"must all match")
    uv = pd.unique(vis)
    if uv.size < 2:
        return {"available": False, "reason": f"only {uv.size} visit(s); the null permutes "
                                              f"amplitude WITHIN visits and needs at least two"}
    # a visit with a single amplitude contributes no permutable contrast; say so rather than
    # letting it silently narrow the null
    per_visit = {str(v): int(np.unique(amp[vis == v]).size) for v in uv}
    n_informative = sum(1 for k in per_visit.values() if k >= 2)
    if n_informative == 0:
        return {"available": False, "reason": "no visit contains two amplitudes, so permuting "
                                              "within visits cannot change anything",
                "amplitudes_per_visit": per_visit}

    t_obs = np.array([_band_t_cluster_robust(Y[:, j], amp, vis, vis)
                      for j in range(len(centers))])
    obs = _clusters_along_axis(t_obs, t_threshold)
    if not obs:
        return {"available": True, "n_clusters": 0, "p_fwer": None,
                "t_per_band": {c: (None if not np.isfinite(t) else float(t))
                               for c, t in zip(centers, t_obs)},
                "t_threshold": float(t_threshold), "n_perm": int(n_perm),
                "amplitudes_per_visit": per_visit,
                "note": (f"no band reached |t| >= {t_threshold:g}, so there is no cluster to test. "
                         f"Given limitation 2 (narrow effects accumulate little mass) this is weak "
                         f"evidence of absence, not a demonstration that the cell is flat.")}

    rng = np.random.default_rng(seed)
    idx_by_visit = [np.flatnonzero(vis == v) for v in uv]
    null_max = np.empty(int(n_perm), dtype=float)
    for k in range(int(n_perm)):
        a_perm = amp.copy()
        for ix in idx_by_visit:
            a_perm[ix] = rng.permutation(amp[ix])
        t_p = np.array([_band_t_cluster_robust(Y[:, j], a_perm, vis, vis)
                        for j in range(len(centers))])
        cl = _clusters_along_axis(t_p, t_threshold)
        null_max[k] = max((abs(m) for _, _, m in cl), default=0.0)

    biggest = max(obs, key=lambda c: abs(c[2]))
    mass = abs(biggest[2])
    p = float((1 + np.sum(null_max >= mass)) / (1 + int(n_perm)))
    return {
        "available": True,
        "n_clusters": len(obs),
        "clusters": [{"lo_hz": centers[i], "hi_hz": centers[j - 1], "n_bands": j - i,
                      "mass": m, "sign": ("negative" if m < 0 else "positive")}
                     for i, j, m in obs],
        "largest_cluster": {"lo_hz": centers[biggest[0]], "hi_hz": centers[biggest[1] - 1],
                            "n_bands": biggest[1] - biggest[0], "mass": biggest[2],
                            "sign": ("negative" if biggest[2] < 0 else "positive")},
        "p_fwer": p,
        "p_resolution": 1.0 / (1 + int(n_perm)),
        "t_threshold": float(t_threshold),
        "n_perm": int(n_perm),
        "t_per_band": {c: (None if not np.isfinite(t) else float(t))
                       for c, t in zip(centers, t_obs)},
        "amplitudes_per_visit": per_visit,
        "n_visits_informative": n_informative,
        "note": ("Family-wise corrected across the band axis. Establishes EXISTENCE of an amplitude "
                 "response, NOT its location: the cluster's frequency limits are descriptive and "
                 "must not be used to choose a band to program (Sassenhagen & Draschkow 2019). The "
                 "per-band t values are cluster-robust and anti-conservative at these cluster "
                 "counts; only the family-wise p is calibrated, because the permutation recomputes "
                 "the same biased statistic under the null."),
    }
