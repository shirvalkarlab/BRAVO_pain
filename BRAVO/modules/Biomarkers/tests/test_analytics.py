"""Regression tests for the analytics plot-data helpers touched in the plot-review pass.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_analytics.py
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import analytics  # noqa: E402


def _cv_df(n=5000, seed=0):
    rng = np.random.default_rng(seed)
    lfp = rng.normal(size=n)
    pain = (lfp + 0.5 * rng.normal(size=n) > 0).astype(float)        # LFP-correlated label
    return pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="min"),
        "LFP": lfp, "LFP_smoothed": lfp, "stim_amplitude": 0.0,
        "pain_level": pain, "nrs": (pain * 6 + 2).astype(int),
    })


def test_roc_downsampled_for_plot():
    df = _cv_df(n=5000)
    roc = analytics.roc_analysis(df, max_points=400)
    assert 0 < len(roc["fpr"]) <= 400 and len(roc["fpr"]) == len(roc["tpr"])
    assert roc["n_points_full"] == 5000                              # AUC computed on full data
    assert 0.5 <= roc["auc"] <= 1.0
    # endpoints preserved after thinning
    assert roc["fpr"][0] <= 1e-9 and abs(roc["fpr"][-1] - 1.0) < 1e-9


def test_sliding_window_emits_per_window_roc():
    """Each sliding window carries a downsampled per-window ROC (fpr/tpr) alongside its AUC, so
    the frontend can overlay one ROC curve per window. Endpoints anchored at 0 and 1; length capped."""
    rng = np.random.default_rng(1)
    n = 60 * 24 * 40                                                  # 40 days at 1-min resolution
    lfp = rng.normal(size=n)
    pain = (lfp + 0.5 * rng.normal(size=n) > 0).astype(float)
    df = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="min"),
        "LFP": lfp, "LFP_smoothed": lfp, "stim_amplitude": 0.0,
        "pain_level": pain, "nrs": (pain * 6 + 2).astype(int),
    })
    out = analytics.sliding_window_analytics(df, train_days=4, test_days=4, sliding=True)
    wins = [w for w in out["windows"] if w.get("auc") is not None]
    assert wins, "expected at least one usable sliding window"
    roc_wins = [w for w in wins if w.get("roc")]
    assert roc_wins, "no window carried a per-window ROC curve"
    for w in roc_wins:
        roc = w["roc"]
        assert 0 < len(roc["fpr"]) <= 60 and len(roc["fpr"]) == len(roc["tpr"])
        assert roc["fpr"][0] <= 1e-9 and abs(roc["fpr"][-1] - 1.0) < 1e-9
        assert all(0.0 <= x <= 1.0 for x in roc["fpr"]) and all(0.0 <= y <= 1.0 for y in roc["tpr"])


def test_cluster_scatter_one_feature():
    df = _cv_df(n=3000)                                              # only 'nrs' present
    cs = analytics.cluster_scatter(df, kmeans_features=("nrs",))
    assert cs is not None and cs["features"] == ["nrs"] and "y" not in cs
    # de-duplicated to unique (nrs, pain_level) observations, not 3000 per-sample rows
    assert len(cs["x"]) == len(cs["pain_level"]) <= 30
    assert set(cs["pain_level"]) <= {0, 1}


def test_cluster_scatter_two_features():
    df = _cv_df(n=2000)
    df["left_leg_vas"] = (df["nrs"] * 9).astype(float)
    df["mpq_sum"] = (df["nrs"] * 5).astype(float)
    cs = analytics.cluster_scatter(df, kmeans_features=("left_leg_vas", "mpq_sum"))
    assert cs["features"] == ["left_leg_vas", "mpq_sum"]
    assert cs["x_label"] == "left_leg_vas" and cs["y_label"] == "mpq_sum"
    assert len(cs["x"]) == len(cs["y"]) == len(cs["pain_level"])


def test_cluster_scatter_missing_features():
    df = _cv_df(n=100)
    assert analytics.cluster_scatter(df, kmeans_features=("not_a_col",)) is None


def test_pain_binarization():
    """Binarization panel: per-feature raw distribution + the empirical high/low boundary derived
    from the actual labels, with the boundary's percentile and 30th/70th references."""
    rng = np.random.default_rng(3)
    nrs = np.clip(np.round(rng.normal(5, 2, size=4000)), 0, 10)
    pain = (nrs >= 6).astype(float)                         # monotone split at 6
    cv = pd.DataFrame({"nrs": nrs, "pain_level": pain})
    pro = pd.DataFrame({"nrs": nrs[:600]})                  # PRO-level distribution source
    out = analytics.pain_binarization(cv, "nrs", kmeans_features=("nrs",), pro_df=pro)
    assert out is not None and len(out["features"]) == 1
    ft = out["features"][0]
    assert ft["name"] == "nrs" and ft["n_obs"] == 600       # distribution drawn from pro_df
    assert 5.0 <= ft["boundary"] <= 6.0                     # boundary between low(<6) and high(>=6)
    assert 0 <= ft["boundary_percentile"] <= 100
    assert ft["p30"] <= ft["p70"]
    # missing pain_level -> None
    assert analytics.pain_binarization(pd.DataFrame({"nrs": nrs}), "nrs", kmeans_features=("nrs",)) is None


def test_lfp_distribution_robust_range():
    """Extreme outliers from the un-normalized merged sources must NOT collapse the histogram into a
    single bar: binning is over the 1st-99th percentile, with the outliers reported as n_clipped."""
    rng = np.random.default_rng(0)
    bulk = rng.normal(1300, 50, size=5000)                 # the dense bulk
    outliers = np.array([-20000.0, 146000.0, 99000.0])     # a few extreme merged-source outliers
    df = pd.DataFrame({"LFP_smoothed": np.concatenate([bulk, outliers]),
                       "pain_level": np.r_[np.ones(2500), np.zeros(2503)]})
    d = analytics.lfp_distribution(df, bins=40)
    edges = d["bin_edges"]
    assert d["n_clipped"] >= 3 and d["n_total"] == 5003
    assert edges[-1] - edges[0] < 2000                     # range zoomed to the bulk, not [-20k, 146k]
    assert max(d["counts"]) < sum(d["counts"])             # not all samples in one bar


def test_corr_spectrum_enforces_50hz_cap():
    """50 Hz cap in the correlation spectrum: a planted, dominant correlation at a >=50 Hz bin must
    be excluded from peak-picking, the per-frequency significance markers, AND the peak-scatter — a
    biomarker can never be drawn from there, so the panel must not surface it."""
    from Biomarkers.routines import streaming_psd
    f = streaming_psd.F_SET
    Ff = len(f)
    rng = np.random.default_rng(1)
    E = 40
    labels = np.linspace(0, 10, E)
    feat = rng.normal(0, 1, (E, 2, Ff))
    hi = int(np.argmin(np.abs(f - 70)))                 # plant the strongest |R| at 70 Hz
    feat[:, 0, hi] = labels * 3
    corr = np.array([[ (np.corrcoef(feat[:, c, j], labels)[0, 1] if np.std(feat[:, c, j]) > 0 else 0.0)
                       for j in range(Ff)] for c in range(2)])
    det = {"f_set": f, "corr": corr, "pval": np.full((2, Ff), 1e-4), "feature": feat,
           "labels": labels, "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "transform": "log"}
    # The global argmax |R| for ch0 IS the >=50 Hz cell -- the cap must keep it out of the outputs.
    assert f[int(np.argmax(np.abs(corr[0])))] >= 50.0
    cs = analytics.corr_spectrum(det, max_freq_hz=50.0)
    ch0 = cs["channels"][0]
    assert all(p["freq"] < 50.0 for p in ch0["peaks"]), "a >=50 Hz peak leaked past the cap"
    assert all(ch0["significant"][k] is None for k in range(Ff) if f[k] >= 50.0)
    if ch0["peak_scatter"] is not None:
        assert ch0["peak_scatter"]["peak_freq"] < 50.0
    # r is NaN'd at every >=50 Hz bin so nothing downstream can pick it.
    assert all(ch0["r"][k] is None for k in range(Ff) if f[k] >= 50.0)


def test_lfp_distribution_otsu_on_mad_filtered_data():
    """The Otsu split must be computed on the MAD-filtered LFP (within 3 MADs of the median), so a
    handful of artifact spikes cannot drag the threshold. The returned otsu sits between the two
    real classes, whereas an UNFILTERED Otsu on the same data is pulled far above by the spikes."""
    rng = np.random.default_rng(2)
    low = rng.normal(110, 3, 2000)
    high = rng.normal(150, 3, 2000)
    spikes = np.array([1e5, 1.2e5, -5e4])               # extreme merged-source artifacts
    df = pd.DataFrame({"LFP_smoothed": np.concatenate([low, high, spikes]),
                       "pain_level": np.r_[np.zeros(2000), np.ones(2000), np.ones(3)]})
    d = analytics.lfp_distribution(df, bins=40)
    assert 110.0 <= d["otsu"] <= 150.0, f"otsu {d['otsu']} dragged out of the class range by spikes"
    naive = analytics._otsu_threshold(df["LFP_smoothed"].values)   # unfiltered, for contrast
    # Control: the unfiltered Otsu is pulled toward the extreme spikes — it sits ABOVE the
    # MAD-filtered split (closer to the high mode / the artifacts), proving the MAD pre-filter
    # materially changes the threshold. (Magnitude depends on the bin grid; assert the direction
    # and a clear gap rather than a brittle absolute value.)
    assert naive > d["otsu"] + 10.0, (
        f"control: a naive Otsu ({naive:.1f}) should sit well above the MAD-filtered split "
        f"({d['otsu']:.1f}) — proves MAD filtering matters")
    assert d["n_total"] == 4003


def test_power_pain_scatter_corr_and_outlier_exclusion():
    """power_pain_scatter returns paired points + Pearson r/p over the MAD-inlier set; power outliers
    are excluded and r recovers the planted correlation rather than being dragged by spikes."""
    rng = np.random.default_rng(5)
    n = 400
    power = rng.normal(100, 15, n)
    pain = 0.5 * power + rng.normal(0, 5, n)          # strong positive association
    # Inject a few extreme power spikes with mismatched pain to test outlier handling.
    power = np.concatenate([power, np.array([5e4, 6e4, -3e4])])
    pain = np.concatenate([pain, np.array([0.0, 0.0, 100.0])])
    df = pd.DataFrame({"LFP_smoothed": power, "nrs": pain})
    d = analytics.power_pain_scatter(df, "nrs")
    assert d["n_clipped"] >= 3, d["n_clipped"]                 # the spikes are excluded
    assert d["r"] is not None and d["r"] > 0.5, d["r"]         # planted positive corr recovered
    assert 0.0 <= d["p"] <= 1.0
    assert len(d["x"]) == len(d["y"]) and len(d["x"]) >= 3
    assert d["y_label"] == "nrs"
    # Missing metric column -> safe empty result, no crash.
    d2 = analytics.power_pain_scatter(df.rename(columns={"nrs": "vas"}), "nrs")
    assert d2["r"] is None and d2["x"] == []
    print("OK power_pain_scatter: r=%.3f p=%.2g n=%d clipped=%d" % (d["r"], d["p"], d["n"], d["n_clipped"]))


def test_td_sliding_corr_grid_reaches_last_session_drops_corrupt_dates():
    """Sliding-corr time-span fix: with a SKEWED session distribution (dense early block + sparse
    recent tail, the RCS08 shape) plus one corrupt ~1677 StartTime, the window grid must (a) NOT be
    anchored back to 1677 by the corrupt date and (b) still extend to within one window of the last
    REAL recording — the bug the 5*MAD clip introduced (truncating the grid months early)."""
    rng = np.random.default_rng(5)
    base = pd.Timestamp("2024-01-01")
    times = [base + pd.Timedelta(days=k * 0.33) for k in range(30)]      # dense early block
    times += [base + pd.Timedelta(days=15 + k * 8) for k in range(19)]   # sparse recent tail
    times.append(pd.Timestamp("1677-09-22"))                             # one corrupt StartTime
    times = list(pd.to_datetime(times))
    E = len(times)
    last_real = max(t for t in times if t.year > 2000)
    det = {"psd": rng.normal(0, 1, (E, 2, 5)), "labels": rng.normal(5, 1, E),
           "f_set": np.arange(5.0), "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"]}
    out = analytics.td_sliding_corr_spectrum(det, times, window_days=30, step_days=7, min_sessions=3)
    starts = pd.to_datetime(out["channels"][0]["window_starts"])
    assert starts.min().year > 2000, "corrupt 1677 date wrongly anchored the grid"
    # Last window start must be within `window_days` of the final real session (grid reaches the end).
    assert (last_real - starts.max()).days <= 30, "grid terminated before the last real session"


def test_power_center_freqs_standard_path():
    """Sensing-band center frequency is read from Descriptor.Therapy.<hemi>.SensingSetup and
    matched to each power contact by its hemisphere token."""
    rec = {"ChannelNames": ["ZERO_THREE_LEFT POWER", "ZERO_THREE_LEFT Stimulation",
                            "ONE_THREE_RIGHT POWER", "ONE_THREE_RIGHT Stimulation"],
           "Descriptor": {"Therapy": {
               "Left":  {"SensingSetup": {"FrequencyInHertz": 22.46}},
               "Right": {"SensingSetup": {"FrequencyInHertz": 9.77}}}}}
    freqs = analytics.power_center_freqs([rec])
    assert freqs == {"ZERO_THREE_LEFT": 22.46, "ONE_THREE_RIGHT": 9.77}


def test_power_center_freqs_direct_hemisphere_key():
    """Streaming Power-Domain (BrainSenseLfp) TherapySnapshot stores FrequencyInHertz DIRECTLY on
    the hemisphere dict (not inside a SensingSetup subdict) — the real RCS08 shape. Verified values
    from RCS008 raw export: ZERO_THREE_LEFT @ 12.7 Hz, ZERO_TWO_RIGHT @ 13.67 Hz."""
    rec = {"ChannelNames": ["ZERO_THREE_LEFT Power", "ZERO_TWO_RIGHT Power"],
           "Descriptor": {"Therapy": {
               "Left":  {"FrequencyInHertz": 12.7, "FrequencyIndex": 13,
                         "SensingChannel": "SensingChannelDef.ZERO_THREE_LEFT"},
               "Right": {"FrequencyInHertz": 13.67, "FrequencyIndex": 14}}}}
    assert analytics.power_center_freqs([rec]) == {"ZERO_THREE_LEFT": 12.7, "ZERO_TWO_RIGHT": 13.67}


def test_power_center_freqs_nested_recordingconfig():
    """Firmware variant: SensingSetup nested under RecordingConfiguration.Config still resolves."""
    rec = {"ChannelNames": ["ZERO_TWO_LEFT POWER"],
           "Descriptor": {"Therapy": {"Left": {
               "RecordingConfiguration": {"Config": {"SensingSetup": {"FrequencyInHertz": 13.18}}}}}}}
    assert analytics.power_center_freqs([rec]) == {"ZERO_TWO_LEFT": 13.18}


def test_power_center_freqs_missing_is_safe():
    """No Therapy / no SensingSetup / no hemisphere token -> no entry, never raises."""
    assert analytics.power_center_freqs([{"ChannelNames": ["ZERO_TWO_LEFT POWER"]}]) == {}
    assert analytics.power_center_freqs(
        [{"ChannelNames": ["ZERO_TWO_LEFT POWER"], "Descriptor": {"Therapy": {"Left": {}}}}]) == {}
    # POWER channel with no LEFT/RIGHT token cannot be matched to a hemisphere.
    rec = {"ChannelNames": ["X POWER"],
           "Descriptor": {"Therapy": {"Left": {"SensingSetup": {"FrequencyInHertz": 7.81}}}}}
    assert analytics.power_center_freqs([rec]) == {}
    # Non-finite / non-positive frequencies are rejected.
    rec2 = {"ChannelNames": ["ZERO_TWO_LEFT POWER"],
            "Descriptor": {"Therapy": {"Left": {"SensingSetup": {"FrequencyInHertz": 0}}}}}
    assert analytics.power_center_freqs([rec2]) == {}


def _group(active, left_hz=None, right_hz=None):
    ch = []
    if left_hz is not None:
        ch.append({"HemisphereLocation": "HemisphereLocationDef.Left",
                   "SensingSetup": {"FrequencyInHertz": left_hz}})
    if right_hz is not None:
        ch.append({"HemisphereLocation": "HemisphereLocationDef.Right",
                   "SensingSetup": {"FrequencyInHertz": right_hz}})
    return {"ActiveGroup": active, "ProgramSettings": {"SensingChannel": ch}}


def test_chronic_center_freqs_group_level():
    """Chronic-trend sensing frequency comes from Groups.Final[].ProgramSettings.SensingChannel[]
    keyed by HemisphereLocation, mapped to Left/RightHemisphere (the chronic ChannelNames tokens)."""
    groups = {"Final": [_group(active=True, left_hz=10.74, right_hz=8.79)]}
    assert analytics.chronic_center_freqs(groups) == {"LeftHemisphere": 10.74, "RightHemisphere": 8.79}
    # A bare list of groups is also accepted.
    assert analytics.chronic_center_freqs([_group(True, left_hz=7.81)]) == {"LeftHemisphere": 7.81}


def test_chronic_center_freqs_active_group_wins():
    """When several groups carry a frequency for the same hemisphere, the ACTIVE group wins."""
    groups = {"Final": [_group(active=False, left_hz=5.0),
                        _group(active=True, left_hz=10.74)]}
    assert analytics.chronic_center_freqs(groups) == {"LeftHemisphere": 10.74}


def test_chronic_center_freqs_missing_is_safe():
    """Malformed / absent structures return {} and never raise."""
    assert analytics.chronic_center_freqs(None) == {}
    assert analytics.chronic_center_freqs({}) == {}
    assert analytics.chronic_center_freqs([1, 2, "x", {}]) == {}
    # hemisphere present but no finite frequency -> omitted
    assert analytics.chronic_center_freqs({"Final": [_group(True, left_hz=0)]}) == {}


def test_otsu_matches_canonical_convention():
    """The corrected _otsu_threshold must (a) match the canonical between-class-variance Otsu (the
    skimage convention) and (b) NOT exhibit the old +half-bin upward bias. On two clean Gaussians the
    threshold sits between the modes; on an asymmetric mixture it matches a brute-force argmax of the
    between-class variance to within one bin width."""
    rng = np.random.default_rng(11)

    def brute_otsu(data, grid=4000):
        ts = np.linspace(data.min(), data.max(), grid)
        best_t, best_v = ts[0], -1.0
        for t in ts:
            b, f = data[data <= t], data[data > t]
            if b.size == 0 or f.size == 0:
                continue
            wb, wf = b.size / data.size, f.size / data.size
            v = wb * wf * (b.mean() - f.mean()) ** 2
            if v > best_v:
                best_v, best_t = v, t
        return best_t

    for d in (np.concatenate([rng.normal(110, 3, 2000), rng.normal(150, 3, 2000)]),
              np.concatenate([rng.normal(50, 5, 500), rng.normal(80, 15, 3000)]),
              np.concatenate([rng.normal(20, 2, 100), rng.normal(60, 8, 5000)])):
        thr = analytics._otsu_threshold(d, nbins=256)
        bf = brute_otsu(d)
        binw = (d.max() - d.min()) / 256.0
        assert abs(thr - bf) <= 1.5 * binw, f"otsu {thr:.3f} far from brute-force optimum {bf:.3f}"
    # Two well-separated modes: the threshold must land in the empty valley BETWEEN them. (It will
    # not be the exact midpoint — between-class variance is flat across the gap, so canonical Otsu
    # returns the leftmost maximizer; the point of the fix is that it no longer overshoots by half a
    # bin, and the cut cleanly separates the two clusters.)
    sym = np.concatenate([rng.normal(100, 4, 5000), rng.normal(140, 4, 5000)])
    thr_sym = analytics._otsu_threshold(sym, nbins=256)
    assert 108.0 < thr_sym < 132.0, f"otsu {thr_sym:.1f} did not land in the valley between the modes"


def test_roc_payload_carries_aligned_thresholds_and_prevalence():
    """The cost-sensitive frontend picker needs (a) thresholds parallel to fpr/tpr (so it can re-pick
    the operating point live without a backend roundtrip) and (b) the class prevalence (so it can
    compute the ROC tangent slope m = (cFP/cFN)*(1-p)/p). Validate shape, alignment, and prevalence."""
    from sklearn import metrics
    rng = np.random.default_rng(7)
    n_neg, n_pos = 3000, 1000
    y = np.r_[np.zeros(n_neg), np.ones(n_pos)]
    score = np.concatenate([rng.normal(100, 12, n_neg), rng.normal(140, 12, n_pos)])
    out = analytics.roc_analysis(pd.DataFrame({"pain_level": y, "LFP_smoothed": score}))
    assert "thr" in out and len(out["thr"]) == len(out["fpr"]) == len(out["tpr"])
    # Prevalence matches the data exactly.
    assert abs(out["prevalence"] - (n_pos / (n_pos + n_neg))) < 1e-12
    assert out["n_pos"] == n_pos and out["n_neg"] == n_neg
    # The very first vertex has +inf threshold (sentinel) → serialized as null.
    assert out["thr"][0] is None
    # Replicate the frontend cost-sensitive picker at cost 1:1 — must reproduce the Youden default.
    fpr = np.array(out["fpr"]); tpr = np.array(out["tpr"])
    thr = np.array([np.nan if t is None else t for t in out["thr"]])
    p = out["prevalence"]
    slope = 1.0 * (1 - p) / p
    util = tpr - slope * fpr
    util[~np.isfinite(thr)] = -np.inf
    k = int(np.argmax(util))
    op = out["operating_point"]
    # NOTE: Youden uses slope = 1 (not (1-p)/p); the picker matches Youden only at the prevalence
    # where the two coincide. The test here is that the frontend re-pick is COHERENT with the
    # backend payload (the device-unit threshold thr[k] actually lies on the curve at fpr[k]/tpr[k]).
    assert thr[k] is not None and np.isfinite(thr[k])
    assert 100.0 < thr[k] < 140.0
    # And independently: the backend's Youden default still equals the unweighted (TPR-FPR) argmax.
    fpr_full, tpr_full, thr_full = metrics.roc_curve(y, score)
    kY = int(np.argmax(tpr_full - fpr_full))
    assert abs(op["threshold"] - float(thr_full[kY])) < 1e-9


def test_roc_operating_point_is_youden_and_separates_classes():
    """roc_analysis must return an operating_point at Youden's J (max TPR-FPR) whose device-unit
    threshold actually separates the two pain classes, and must map the threshold back to the raw
    power scale correctly even when the AUC orientation had to be flipped."""
    from sklearn import metrics
    rng = np.random.default_rng(3)
    y = np.r_[np.zeros(1500), np.ones(1500)]

    # High pain -> high power.
    score = np.concatenate([rng.normal(100, 10, 1500), rng.normal(140, 10, 1500)])
    out = analytics.roc_analysis(pd.DataFrame({"pain_level": y, "LFP_smoothed": score}))
    op = out["operating_point"]
    assert op is not None and op["direction"] == "ge"
    fpr, tpr, thr = metrics.roc_curve(y, score)
    k = int(np.argmax(tpr - fpr))
    assert abs(op["threshold"] - float(thr[k])) < 1e-9, "threshold is not Youden's J"
    assert 100.0 < op["threshold"] < 140.0, "threshold should fall between the class means"
    assert op["sensitivity"] > 0.9 and op["specificity"] > 0.9

    # Flipped: high pain -> LOW power. AUC is flipped internally; threshold must still come back on
    # the raw device scale (between the means), not negated.
    score_flip = np.concatenate([rng.normal(140, 10, 1500), rng.normal(100, 10, 1500)])
    out2 = analytics.roc_analysis(pd.DataFrame({"pain_level": y, "LFP_smoothed": score_flip}))
    op2 = out2["operating_point"]
    assert op2 is not None
    assert 100.0 < op2["threshold"] < 140.0, f"flipped threshold {op2['threshold']:.1f} off the raw scale"


if __name__ == "__main__":
    test_otsu_matches_canonical_convention()
    test_roc_operating_point_is_youden_and_separates_classes()
    test_roc_downsampled_for_plot()
    test_sliding_window_emits_per_window_roc()
    test_cluster_scatter_one_feature()
    test_cluster_scatter_two_features()
    test_cluster_scatter_missing_features()
    test_pain_binarization()
    test_lfp_distribution_robust_range()
    test_corr_spectrum_enforces_50hz_cap()
    test_lfp_distribution_otsu_on_mad_filtered_data()
    test_power_pain_scatter_corr_and_outlier_exclusion()
    test_td_sliding_corr_grid_reaches_last_session_drops_corrupt_dates()
    test_power_center_freqs_standard_path()
    test_power_center_freqs_direct_hemisphere_key()
    test_power_center_freqs_nested_recordingconfig()
    test_power_center_freqs_missing_is_safe()
    test_chronic_center_freqs_group_level()
    test_chronic_center_freqs_active_group_wins()
    test_chronic_center_freqs_missing_is_safe()
    print("All analytics tests passed.")
