"""Phase 2: the three edges of the amplitude -> power -> pain triangle, estimated honestly.

The triangle is the module's whole argument. Closing the loop on a band requires all three of:

  E1  amplitude -> band power    the device can MOVE the signal (otherwise there is no control)
  E2  band power -> pain         the signal TELLS THE PATIENT'S HIGH PAIN FROM THEIR LOW PAIN
                                 (otherwise control is pointless)
  E3  amplitude -> pain          the therapy WORKS (otherwise there is nothing to automate)

E2 IS NOT A SLOPE. It used to be one. It is now how far this band's power gets above or below coin
flipping at separating high-pain moments from low-pain ones, because the stimulator switches state
when power crosses a value programmed into it and that is a yes-or-no decision. See ``state_edge``.

and requires their signs to be mutually consistent, which is what consistency.py tests.

WHY THE CLUSTERING UNIT IS RECORDED ON EVERY ESTIMATE. The fourteen-finding audit of the biomarker
plate found that the dominant source of overstated significance in this project was treating
correlated observations as independent — spectral samples within one setting epoch, or several
epochs belonging to one pain rating. Cluster-robust standard errors at the right unit are therefore
not a refinement here, they are the difference between a defensible number and an artefact, and an
EdgeEstimate that cannot state its clustering unit is not usable downstream.

WHAT E1 CANNOT BE ON THIS DATA. In the historical record, amplitude was escalated over months, so
amplitude is confounded with time and with everything else that drifts: impedance, disease state,
medication, the patient's expectations. No estimator removes that. E1 computed here is a SCREENING
statistic for deciding what to titrate prospectively, and it is labelled as such on the estimate
itself so that no panel can present it as a causal effect.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .types import EdgeEstimate


# THE CLUSTER-ROBUST TOOLKIT AND THE PAIN-RELATIONSHIP ESTIMATE NOW LIVE ON THE BIOMARKER SIDE.
#
# All of the following used to be written out in this file. It was moved into
# ``Biomarkers/routines/analytics.py`` because the biomarker page is the place where the
# relationship between a frequency band and the patient's pain is worked out, and this module was
# keeping a second copy of that calculation. Two copies of one calculation drift apart, and when
# they do there is no way to tell which of the two numbers on the screen is the right one.
#
# The names are imported back out here, unchanged, for two reasons. Nothing else in this module had
# to be edited -- ``adapter.py`` still calls ``edges.estimator_for`` and the bootstrap tests still
# reach for ``edges.wild_cluster_bootstrap_t`` -- and a reader of this file can still see the whole
# list of statistical machinery the edges depend on without opening another module.
#
# THE IMPORT ONLY WORKS IN THIS DIRECTION. ClosedLoopDeployment may import Biomarkers.
# Biomarkers may NOT import ClosedLoopDeployment: the two would then wait for each other and
# neither would load. That constraint is what decided which module the code moved into, and there
# is a test that runs a fresh interpreter to confirm the leak has not appeared, because checking it
# inside an interpreter that has already imported this module proves nothing.
from Biomarkers.routines.analytics import (      # noqa: F401  (re-exported on purpose)
    MIN_RELIABLE_CLUSTERS,
    MAX_ENUMERABLE_CLUSTERS,
    estimator_for,
    band_pain_auc_from_table,
    read_band_pain_auc_from_export,
    BAND_PAIN_ESTABLISHED,
    BAND_PAIN_NOT_RESOLVED,
    BAND_PAIN_NOT_ASSESSED,
    _cluster_ols,
    _rademacher_weights,
    _cr0_variance,
    _BootstrapPlan,
    wild_cluster_bootstrap_t,
    wild_cluster_bootstrap_ci,
    _small_sample_inference,
)


def actuation_edge(T, *, channel, center_hz, hemisphere="Left", scale="power_linear",
                   n_boot=999, seed=0):
    """E1: does band power move with programmed amplitude?

    Cluster unit is the SETTING EPOCH. Every spectral sample recorded while one set of stimulation
    parameters was in force is one observation of that setting, not many independent ones; treating
    them as independent is the pseudoreplication the audit identified.

    Estimated on the LINEAR power scale by default, because rule D11 records that the device
    computes LFP power as a linear sum of squared magnitude, and an edge intended to predict device
    behaviour should be on the device's own scale.
    """
    from .adapter import resolve_setting_column
    amp_col = resolve_setting_column(T.columns if T is not None else [], "amp", hemisphere)
    if amp_col is None:
        return EdgeEstimate("E1", None, None, None, 0, "setting epoch", 0, scale,
                            note=f"no amplitude column for the {hemisphere} hemisphere under any "
                                 "known spelling; the joined table carried no delivered amplitude, "
                                 "so an actuation slope cannot be formed")
    need = {amp_col, scale, "setting_epoch", "channel", "center_hz"}
    if T is None or T.empty or not need.issubset(T.columns):
        return EdgeEstimate("E1", None, None, None, 0, "setting epoch", 0, scale,
                            note=f"missing columns: {sorted(need - set(T.columns if T is not None else []))}")
    d = T[(T.channel == channel) & (np.isclose(T.center_hz, center_hz))].copy()
    d = d.dropna(subset=[amp_col, scale, "setting_epoch"])
    d = d[d.setting_epoch >= 0]
    if len(d) < 6:
        return EdgeEstimate("E1", None, None, None, len(d), "setting epoch",
                            int(d.setting_epoch.nunique()), scale, note="too few usable samples")
    X = np.column_stack([np.ones(len(d)), pd.to_numeric(d[amp_col], errors="coerce").to_numpy()])
    res, bse, nclu = _cluster_ols(d[scale].to_numpy(), X, d.setting_epoch.to_numpy())
    if res is None:
        return EdgeEstimate("E1", None, None, None, len(d), "setting epoch", nclu, scale,
                            note="fewer than two setting epochs; a within-subject slope is not "
                                 "identifiable from a single setting")
    b = float(res.params[1]); se = float(bse[1])
    p, ci = float(res.pvalues[1]), (b - 1.96 * se, b + 1.96 * se)
    note = ("SCREENING STATISTIC ONLY. Amplitude is confounded with time in the historical record, "
            "so this cannot be read as the causal effect of amplitude on power. Its purpose is to "
            "choose what to titrate.")
    conf = ["time", "impedance drift", "concurrent rate changes"]
    if nclu < MIN_RELIABLE_CLUSTERS:
        note += (f" FEW CLUSTERS: {nclu} setting epochs is below the {MIN_RELIABLE_CLUSTERS} at "
                 "which the cluster-robust variance estimator has an asymptotic argument behind it. "
                 "This is reported as information about which estimator was used, not as a reason "
                 "to withhold the estimate. ")
        conf.append("few clusters")
        p, ci, boot_note, _ = _small_sample_inference(
            d[scale].to_numpy(float), X, d.setting_epoch.to_numpy(), n_boot=n_boot, seed=seed)
        note += boot_note
    else:
        note += (f" Inference is CR0 cluster-robust at the setting epoch on {nclu} clusters, which "
                 f"is at or above the {MIN_RELIABLE_CLUSTERS}-cluster point where the asymptotic "
                 "approximation is usually adequate.")
    return EdgeEstimate("E1", b, ci, p, len(d), "setting epoch", nclu, scale,
                        note=note, confounded_by=conf)


def pooled_actuation_edge(pooled_row, *, scale="power_linear"):
    """E1 from the STORED POOLED SLOPE: band power on current across every run of rising current
    on this sensing contact, one baseline per run and one shared slope (decision 55), read from
    the row `amplitude_effect.pooled_row` returns.

    Chosen by the PI on 2026-09-11 (redesign decision 9, decision 124 in the log) over the
    historical setting-epoch slope `actuation_edge` computes from months of chronic recording:
    the pooled titration slope is the quantity the redesigned three-source panel draws, so the
    triangle and the panel now read one number. The historical estimate is kept beside it in
    the report (`edges_historical`) rather than discarded.

    The curvature answer travels in the note as a CAVEAT: a bend detected across the tested
    currents means a single slope is a poor description, and the note says so; a peak is named
    only when the pooled model placed one inside the tested range. Nothing here fits anything.
    """
    r = pooled_row or {}
    b = r.get("pooled_slope_per_mA")
    se = r.get("pooled_slope_stderr")
    p = r.get("pooled_slope_p")
    n = int(r.get("n") or 0)
    n_visits = int(r.get("n_visits") or 0)
    unit = "run of rising current (one baseline each)"
    if b is None or not np.isfinite(float(b)):
        return EdgeEstimate("E1", None, None, None, n, unit, n_visits, scale,
                            note=("no pooled slope: " + str(r.get("verdict") or
                                  "the pooled within-visit table has no assessed row for this "
                                  "contact and band")))
    b = float(b)
    ci = ((b - 1.96 * float(se), b + 1.96 * float(se))
          if se is not None and np.isfinite(float(se)) else None)
    p = float(p) if p is not None and np.isfinite(float(p)) else None
    note = (f"POOLED ACROSS {n_visits} RUNS OF RISING CURRENT on this contact, {n} settled "
            "points, one baseline per run and one shared slope (decision 55), in the device's "
            "own units per mA. This is the same row the three-source panel draws, chosen for the "
            "triangle on 2026-09-11 in place of the historical setting-epoch slope, which is kept "
            "in the report beside it.")
    curves = bool(r.get("curves"))
    pc = r.get("p_curvature")
    conf = []
    if curves:
        note += (f" CURVATURE: a bend across the tested currents was detected (p = "
                 f"{float(pc):.3f})" if pc is not None and np.isfinite(float(pc))
                 else " CURVATURE: a bend across the tested currents was detected")
        if r.get("peaks_inside") and r.get("peak_mA") is not None \
                and np.isfinite(float(r.get("peak_mA"))):
            note += f", with the peak near {float(r['peak_mA']):.1f} mA"
        note += (", so one straight-line slope is a poor description of this band and the sign "
                 "below is the average across the bend, not the direction past the peak.")
        conf.append("curvature")
    elif pc is not None and np.isfinite(float(pc)):
        note += f" No bend was detected across the tested currents (curvature p = {float(pc):.3f})."
    else:
        note += " Curvature could not be assessed on this many points."
    if n_visits and n_visits < 3:
        conf.append("few runs")
    return EdgeEstimate("E1", b, ci, p, n, unit, n_visits, scale, note=note, confounded_by=conf)


#: What the E2 estimate is a number of, written on every E2 estimate this module produces.
#:
#: E2 no longer carries a slope. It carries how far this band's power gets above or below coin
#: flipping at telling the patient's high-pain moments from the low-pain ones, which is why 0.5 has
#: been subtracted; see ``state_edge`` for why that subtraction is what makes the rest of the
#: module keep working correctly.
E2_QUANTITY = ("how far above or below coin flipping this band's power gets at telling high-pain "
               "moments from low-pain ones, as area under the curve minus 0.5")


def state_edge(T, *, channel, center_hz, outcome="nrs", scale="power_linear",
               cluster="report_id", n_boot=500, seed=0, strategy="tertile"):
    """E2: how well does this band's power tell the patient's high pain from their low pain?

    WHAT CHANGED AND WHY, because this is not the same quantity it used to be. This function used
    to fit a straight line through band power against the pain score and report its slope. The PI
    has rejected that and it has been deleted. The stimulator changes what it is doing when band
    power crosses a value programmed into it, which is a yes-or-no decision about the state of the
    brain signal, so the quantity that decides whether a band is worth driving that decision with
    has to be a quantity about telling two states apart. That quantity is the area under the curve,
    it is computed on the biomarker side, and this function reads it.

    WHAT MAY BE HANDED IN as the first argument, either of two things:

      * the exported table from ``Biomarkers.routines.analytics.band_pain_auc_export`` -- one row
        per sensing contact pair per band centre. This is the table the PI asked the biomarker page
        to produce and the closed-loop page to inherit, and handing it in is the intended route.
      * this module's own table of spectral samples, one row per sample, with columns for the
        channel, the band centre, the band power, the pain score and the pain report. The same
        estimator is then run on those rows directly, through
        ``Biomarkers.routines.analytics.band_pain_auc_from_table``.

    Either way there is ONE estimator, on the biomarker side, so the deployment panel and the
    biomarker page cannot print two different numbers for the same band. Which of the two routes
    was taken is written on the note.

    WHY 0.5 IS SUBTRACTED FROM THE NUMBER BEFORE IT IS STORED. An ``EdgeEstimate`` defines
    ``resolved`` as its interval excluding ZERO, and everything downstream -- the sign coherence
    test in ``consistency.py``, device rule D19 -- reads only ``resolved`` and ``sign``. An area
    under the curve is measured against 0.5, not zero, so storing it raw would make ``resolved``
    trivially true for every band and would silently destroy the one check this module exists to
    perform. Subtracting 0.5 from the value and from both ends of its interval makes "the interval
    excludes zero" mean exactly "the interval excludes 0.5", and makes a positive sign mean exactly
    "more power in this band goes with more pain", which is the sign D19 asks for. The raw value
    and its raw interval are written out in full on the note, so nothing is hidden by the shift.
    ``scale`` names the quantity, so no reader can mistake it for a slope.

    THE THREE-WAY ANSWER SURVIVES THE PACKING, and that is the delicate part. The biomarker side
    says "established", "not resolved" or "not assessed" in words. An ``EdgeEstimate`` carries the
    same distinction in its fields rather than in a word: a band that was never assessed has no
    value at all (``estimate`` is None), while one that was assessed but left the answer open has a
    value and an interval that spans zero once shifted, so ``resolved`` is False. What must never
    happen is a "not assessed" result arriving with a value attached, because it would then read as
    a measurement showing no separation. The mapping below drops the value exactly when the answer
    is "not assessed", and a test checks it.
    """
    from_export = (T is not None and hasattr(T, "columns")
                   and {"channel", "band_center_hz", "auc", "answer"}.issubset(set(T.columns)))
    if from_export:
        out = read_band_pain_auc_from_export(T, channel=channel, center_hz=center_hz)
        route = ("read out of the table the biomarker page exported, which is the intended route: "
                 "the number was computed once, on the biomarker side, and inherited here")
    else:
        out = band_pain_auc_from_table(T, channel=channel, center_hz=center_hz,
                                       pain_column=outcome, power_column=scale,
                                       group_column=cluster, strategy=strategy,
                                       n_boot=n_boot, seed=seed)
        route = ("computed by the biomarker page's own estimator, called here on this module's "
                 "table of spectral samples because no exported table was handed in. The exported "
                 "table is the intended route; this one runs the same estimator on the same rules")
    n = int(out.get("n_spectral_samples") or 0)
    n_reports = int(out.get("n_pain_reports") or 0)
    split = out.get("pain_split_rule") or "the pain split was not recorded"
    if out.get("answer") == BAND_PAIN_NOT_ASSESSED:
        note = (f"NOT ASSESSED, so there is no number here at all and this must not be read as a "
                f"measurement showing that the band does not separate high pain from low pain. "
                f"{out.get('why', '')}. This answer was {route}.")
        return EdgeEstimate("E2", None, None, None, n, cluster, n_reports, E2_QUANTITY, note=note)
    auc = out.get("auc")
    lo, hi = out.get("auc_low"), out.get("auc_high")
    est = (float(auc) - 0.5) if auc is not None else None
    ci = ((float(lo) - 0.5, float(hi) - 0.5) if (lo is not None and hi is not None) else None)
    raw_ci = (f"{float(lo):.3f} to {float(hi):.3f}" if (lo is not None and hi is not None)
              else "no interval could be formed")
    note = (
        f"The number stored on this estimate is {('%.3f' % est) if est is not None else 'absent'}, "
        f"which is the area under the curve minus 0.5. THE RAW AREA UNDER THE CURVE IS "
        f"{('%.3f' % auc) if auc is not None else 'absent'} and its "
        f"{100 * float(out.get('confidence_level') or 0.95):.0f}% interval is {raw_ci}; 0.5 is what "
        f"coin flipping would give, and 0.5 was subtracted so that this module's existing test of "
        f"whether an interval excludes zero becomes a test of whether it excludes coin flipping. "
        f"Clustered on the pain report: {n_reports} pain reports behind {n} spectral samples, and "
        f"the confidence interval comes from resampling whole pain reports rather than individual "
        f"samples, because many samples can share one pain report and therefore share its score "
        f"exactly. How pain was split into high and low: {split}. What the power values are: "
        f"{out.get('power_feature', 'not recorded')}. {out.get('why', '')}. This answer was "
        f"{route}.")
    return EdgeEstimate("E2", est, ci, out.get("p_two_sided"), n, cluster, n_reports,
                        E2_QUANTITY, note=note)


def therapy_edge(design_matrix, *, outcome="nrs", amp_col="amp_mA_Left", cluster="epoch",
                 n_boot=999, seed=0):
    """E3: does pain change with amplitude across settings?

    Read from the exposure-epoch design matrix rather than the spectral table, because this edge
    does not involve the brain signal at all. Era-blocking is the caller's responsibility; the note
    records whether a block variable was supplied, since an unblocked estimate on this record is
    dominated by the same amplitude-time confound that limits E1.
    """
    if design_matrix is None or len(design_matrix) == 0:
        return EdgeEstimate("E3", None, None, None, 0, cluster, 0, "mA", note="no design matrix")
    d = design_matrix.copy()
    if amp_col not in d.columns or outcome not in d.columns:
        return EdgeEstimate("E3", None, None, None, 0, cluster, 0, "mA",
                            note=f"missing {amp_col!r} or {outcome!r}")
    grp = cluster if cluster in d.columns else None
    d = d.dropna(subset=[amp_col, outcome] + ([grp] if grp else []))
    if len(d) < 6 or grp is None:
        return EdgeEstimate("E3", None, None, None, len(d), cluster, 0, "mA",
                            note="too few epochs, or no cluster column")
    X = np.column_stack([np.ones(len(d)), d[amp_col].to_numpy(float)])
    res, bse, nclu = _cluster_ols(d[outcome].to_numpy(float), X, d[grp].to_numpy())
    if res is None:
        return EdgeEstimate("E3", None, None, None, len(d), cluster, nclu, "mA",
                            note="fewer than two epoch clusters")
    b = float(res.params[1]); se = float(bse[1])
    p, ci = float(res.pvalues[1]), (b - 1.96 * se, b + 1.96 * se)
    note = ("unblocked unless the caller supplied an era-restricted matrix; on the historical "
            "record an unblocked estimate carries the amplitude-time confound. ")
    if nclu < MIN_RELIABLE_CLUSTERS:
        note += f"FEW CLUSTERS: {nclu} epochs is below {MIN_RELIABLE_CLUSTERS}. "
        p, ci, boot_note, _ = _small_sample_inference(
            d[outcome].to_numpy(float), X, d[grp].to_numpy(), n_boot=n_boot, seed=seed)
        note += boot_note
    else:
        note += (f"Inference is CR0 cluster-robust on {nclu} clusters, at or above the "
                 f"{MIN_RELIABLE_CLUSTERS}-cluster point where that approximation is usually "
                 "adequate.")
    return EdgeEstimate("E3", b, ci, p, len(d), cluster, nclu, "mA", note=note,
                        confounded_by=["time"])


def max_statistic_permutation(T, *, channels, centers, amp_col="amp_mA_Left",
                              scale="power_linear", n_perm=2000, seed=0):
    """Family-wise corrected p for "does ANY band-cell respond to amplitude?".

    Permutes amplitude BETWEEN SETTING EPOCHS, keeping every sample within an epoch together, and
    records the largest absolute t statistic across all band-cells in each replicate. Comparing the
    observed maximum against that distribution corrects for having scanned many cells without
    assuming they are independent — which they are not, since neighbouring bands share spectral
    bins and channels share a lead.

    Permuting whole epochs rather than samples is the point: shuffling samples would break the
    within-epoch dependence and produce a null that is far too narrow, which is the mechanism that
    made earlier scans look significant.
    """
    if T is None or T.empty or amp_col not in T.columns:
        return {"available": False, "reason": "no usable table"}
    rng = np.random.default_rng(seed)
    cells = [(c, f) for c in channels for f in centers]
    base = T[T.setting_epoch >= 0].dropna(subset=[amp_col, scale, "setting_epoch"])
    if base.empty:
        return {"available": False, "reason": "no rows with an epoch and both variables"}
    ep = base[["setting_epoch", amp_col]].drop_duplicates("setting_epoch").set_index("setting_epoch")[amp_col]
    if ep.size < 3:
        return {"available": False, "reason": f"only {ep.size} setting epochs; a permutation null "
                                              "over epochs needs at least three"}

    def _tmax(amp_map):
        best = 0.0
        for ch, fc in cells:
            d = base[(base.channel == ch) & (np.isclose(base.center_hz, fc))]
            if len(d) < 6 or d.setting_epoch.nunique() < 2:
                continue
            a = d.setting_epoch.map(amp_map).to_numpy(float)
            X = np.column_stack([np.ones(len(d)), a])
            res, bse, _ = _cluster_ols(d[scale].to_numpy(float), X, d.setting_epoch.to_numpy())
            if res is None or not np.isfinite(bse[1]) or bse[1] == 0:
                continue
            best = max(best, abs(float(res.params[1]) / float(bse[1])))
        return best

    obs = _tmax(ep.to_dict())
    vals = ep.to_numpy()
    null = np.empty(n_perm, float)
    for i in range(n_perm):
        null[i] = _tmax(dict(zip(ep.index, rng.permutation(vals))))
    p = float((1 + (null >= obs).sum()) / (1 + n_perm))
    return {"available": True, "observed_max_t": obs, "p_fwer": p, "n_perm": int(n_perm),
            "n_cells": len(cells), "n_epochs_permuted": int(ep.size),
            "resolution": 1.0 / (1 + n_perm),
            "note": ("amplitude permuted between whole setting epochs, preserving within-epoch "
                     "dependence. Permuting individual samples would give a null that is far too "
                     "narrow.")}
