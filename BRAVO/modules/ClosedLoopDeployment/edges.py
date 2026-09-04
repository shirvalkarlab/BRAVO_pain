"""Phase 2: the three edges of the amplitude -> power -> pain triangle, estimated honestly.

The triangle is the module's whole argument. Closing the loop on a band requires all three of:

  E1  amplitude -> band power    the device can MOVE the signal (otherwise there is no control)
  E2  band power -> pain         the signal TRACKS the patient (otherwise control is pointless)
  E3  amplitude -> pain          the therapy WORKS (otherwise there is nothing to automate)

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


#: Below this many clusters the cluster-robust variance estimator is itself unreliable and is
#: anti-conservative — its intervals are too NARROW, so it manufactures resolution rather than
#: losing it. This is not a hypothetical: on the RCS08 record, cells with three setting epochs
#: reported all eighteen bands as resolved, while the whole-epoch permutation on the same cells
#: returned a family-wise p of 1.00. Estimates below the floor are still returned, because refusing
#: them would hide data, but they carry the warning and `few_clusters` is set on the note.
MIN_RELIABLE_CLUSTERS = 40


def _cluster_ols(y, X, groups, *, names=None):
    """OLS with cluster-robust (CR0) standard errors. Returns (params, bse, n_clusters).

    statsmodels is used rather than a hand-rolled sandwich because the conventional implementation
    handles the small-sample correction and the singular cases consistently, and because a
    re-implementation would be one more thing to audit.
    """
    import statsmodels.api as sm
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    g = np.asarray(groups)
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1) & pd.notna(g)
    y, X, g = y[ok], X[ok], g[ok]
    if y.size < 3 or np.unique(g).size < 2:
        return None, None, int(np.unique(g).size if g.size else 0)
    res = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": g})
    return res, np.asarray(res.bse, float), int(np.unique(g).size)


def actuation_edge(T, *, channel, center_hz, hemisphere="Left", scale="power_linear"):
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
    ci = (b - 1.96 * se, b + 1.96 * se)
    note = ("SCREENING STATISTIC ONLY. Amplitude is confounded with time in the historical record, "
            "so this cannot be read as the causal effect of amplitude on power. Its purpose is to "
            "choose what to titrate.")
    conf = ["time", "impedance drift", "concurrent rate changes"]
    if nclu < MIN_RELIABLE_CLUSTERS:
        note += (f" FEW CLUSTERS: {nclu} setting epochs is below the {MIN_RELIABLE_CLUSTERS} at which "
                 "the cluster-robust variance estimator becomes reliable. Below it the estimator is "
                 "anti-conservative, meaning this interval is too NARROW and any apparent resolution "
                 "may be manufactured. Prefer the whole-epoch permutation for inference here.")
        conf.append("few clusters")
    return EdgeEstimate("E1", b, ci, float(res.pvalues[1]), len(d), "setting epoch", nclu, scale,
                        note=note, confounded_by=conf)


def state_edge(T, *, channel, center_hz, outcome="nrs", scale="power_linear",
               cluster="report_id"):
    """E2: does the band track the patient's pain at fixed stimulation?

    Cluster unit is the RATING. One pain report is matched to a window containing many spectral
    samples; those samples share the report's value entirely, so they carry one observation of the
    pain-power relationship between them.
    """
    need = {scale, outcome, "channel", "center_hz"}
    if T is None or T.empty or not need.issubset(T.columns):
        return EdgeEstimate("E2", None, None, None, 0, cluster, 0, scale,
                            note=f"missing columns: {sorted(need - set(T.columns if T is not None else []))}")
    d = T[(T.channel == channel) & (np.isclose(T.center_hz, center_hz))].copy()
    grp = cluster if cluster in d.columns else None
    if grp is None:
        return EdgeEstimate("E2", None, None, None, len(d), cluster, 0, scale,
                            note=f"no {cluster} column: the rating-level cluster is unavailable, and "
                                 "estimating this edge without it would reproduce the "
                                 "pseudoreplication the audit flagged")
    d = d.dropna(subset=[scale, outcome, grp])
    if len(d) < 6:
        return EdgeEstimate("E2", None, None, None, len(d), cluster,
                            int(d[grp].nunique()), scale, note="too few usable samples")
    X = np.column_stack([np.ones(len(d)), d[scale].to_numpy(float)])
    res, bse, nclu = _cluster_ols(d[outcome].to_numpy(float), X, d[grp].to_numpy())
    if res is None:
        return EdgeEstimate("E2", None, None, None, len(d), cluster, nclu, scale,
                            note="fewer than two rating clusters")
    b = float(res.params[1]); se = float(bse[1])
    n2 = ("cluster-robust at the rating, which is the unit that carries one independent "
          "observation of pain")
    if nclu < MIN_RELIABLE_CLUSTERS:
        n2 += (f" FEW CLUSTERS: {nclu} ratings is below {MIN_RELIABLE_CLUSTERS}; the interval is "
               "likely too narrow.")
    return EdgeEstimate("E2", b, (b - 1.96 * se, b + 1.96 * se), float(res.pvalues[1]),
                        len(d), cluster, nclu, scale, note=n2)


def therapy_edge(design_matrix, *, outcome="nrs", amp_col="amp_mA_Left", cluster="epoch"):
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
    return EdgeEstimate("E3", b, (b - 1.96 * se, b + 1.96 * se), float(res.pvalues[1]),
                        len(d), cluster, nclu, "mA",
                        note="unblocked unless the caller supplied an era-restricted matrix; on the "
                             "historical record an unblocked estimate carries the amplitude-time "
                             "confound",
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
