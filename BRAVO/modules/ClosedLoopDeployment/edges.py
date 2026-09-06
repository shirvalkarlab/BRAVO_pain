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
    band_pain_tracking,
    PAIN_TRACKING_TRACKS,
    PAIN_TRACKING_NOT_RESOLVED,
    PAIN_TRACKING_NOT_ASSESSED,
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


def state_edge(T, *, channel, center_hz, outcome="nrs", scale="power_linear",
               cluster="report_id", n_boot=999, seed=0):
    """E2: does the band track the patient's pain at fixed stimulation?

    THIS FUNCTION NO LONGER DOES THE ARITHMETIC. It asks the biomarker page for the answer, through
    ``Biomarkers.routines.analytics.band_pain_tracking``, and then packs that answer into the
    ``EdgeEstimate`` shape the rest of this module reads. The calculation used to be written out
    here as well as there, which meant the deployment panel and the biomarker page could print two
    different slopes for the same band with no way to tell which one to believe.

    Cluster unit is the RATING. One pain report is matched to a window containing many spectral
    samples; those samples share the report's value entirely, so they carry one observation of the
    pain-power relationship between them.

    THE THREE-WAY ANSWER SURVIVES THE PACKING, and that is the only delicate part of this wrapper.
    ``band_pain_tracking`` says "tracks", "not resolved" or "not assessed" in words. An
    ``EdgeEstimate`` carries that same distinction in its fields rather than in a word: an estimate
    that was never worked out has no slope at all (``estimate`` is None), while one that was worked
    out but left the direction open has a slope and an interval that spans zero, so ``resolved`` is
    False. Those are different states and downstream code already tells them apart. What must never
    happen is a "not assessed" result arriving with a slope attached, because it would then read as
    a measured absence of any relationship. The mapping below therefore drops the slope exactly
    when the verdict is "not assessed", and a test checks that.
    """
    out = band_pain_tracking(T, channel=channel, center_hz=center_hz, pain_column=outcome,
                             power_column=scale, group_column=cluster, n_boot=n_boot, seed=seed)
    if out["verdict"] == PAIN_TRACKING_NOT_ASSESSED:
        return EdgeEstimate("E2", None, None, None, out["n"], cluster, out["n_groups"], scale,
                            note=out["note"])
    return EdgeEstimate("E2", out["estimate"], out["ci"], out["p"], out["n"], cluster,
                        out["n_groups"], scale, note=out["note"])


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
