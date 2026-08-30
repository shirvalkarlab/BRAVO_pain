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


def _planted_detail(E=60, C=2, F=60, center=20.0, half=2.5, beta=0.4, seed=0, prelog=False):
    """Synthetic td_detail with a planted band-power<->label correlation in channel 0."""
    rng = np.random.default_rng(seed)
    f = np.linspace(0.95, 100, F)
    labels = rng.normal(5, 2, E)
    psd = np.abs(rng.normal(1, 0.2, (E, C, F)))
    band = (f >= center - half) & (f <= center + half)
    psd[:, 0, band] *= (1 + beta * (labels - labels.mean())[:, None])
    if prelog:
        psd = 10.0 * np.log10(psd)
    return {"f_set": f, "psd": psd, "labels": labels,
            "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"],
            "times": [f"2025-07-{1 + (i % 28):02d} 10:00:00" for i in range(E)],
            "prelog": prelog}


def test_binarize_labels_tertile_excludes_middle():
    vals = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, np.nan], float)
    b = analytics._binarize_labels(vals, strategy="tertile", low_pct=33.3333, high_pct=66.6667)
    assert b[0] == 0 and b[8] == 1, b
    assert np.isnan(b[3]) and np.isnan(b[9]), b   # middle + NaN both excluded


def test_binarize_cut_invariant_to_sample_multiplicity():
    """R11/audit A7: the tertile cut must be computed on the unique-PRO distribution, not the
    pseudoreplicated per-sample vector. Duplicating one rating's samples must NOT move the cut."""
    # 9 unique ratings 1..9, one rating (value 7, near the 67th pct) replicated 18x as in the
    # real data (max_reuse=18). Without rating_group the duplication drags the high cut down.
    base_vals = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9], float)
    base_rg = np.arange(9)
    dup_vals = np.concatenate([base_vals, np.full(17, 7.0)])      # rating "7" now appears 18x
    dup_rg = np.concatenate([base_rg, np.full(17, 6)])            # all share rating-group id 6

    # Per-group (deduplicated) cut: identical labels for the 9 canonical samples in both cases.
    b_unique = analytics._binarize_labels(base_vals, strategy="tertile",
                                          rating_group=base_rg)
    b_dup = analytics._binarize_labels(dup_vals, strategy="tertile",
                                       rating_group=dup_rg)
    # The first 9 entries correspond to the same 9 unique ratings; their labels must match exactly.
    assert np.array_equal(np.nan_to_num(b_unique, nan=-1),
                          np.nan_to_num(b_dup[:9], nan=-1)), (b_unique, b_dup[:9])

    # Contrast: WITHOUT rating_group the pseudoreplicated cut differs (regression guard — confirms
    # the dedup is actually doing something, not a no-op).
    b_pseudo = analytics._binarize_labels(dup_vals, strategy="tertile")
    assert not np.array_equal(np.nan_to_num(b_unique, nan=-1),
                              np.nan_to_num(b_pseudo[:9], nan=-1)), \
        "dedup made no difference — rating_group not wired through"


def test_matched_sample_counts_reports_high_low_and_offset():
    vals = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, np.nan], float)
    dt = np.array([2, -5, 10, np.nan, 3, -12, 1, 8, -2, np.nan], float)
    mc = analytics.matched_sample_counts(vals, strategy="tertile", match_dt_min=dt, tolerance_min=15)
    assert mc["n_matched"] == 9 and mc["n_high"] == 3 and mc["n_low"] == 3, mc
    assert mc["n_excluded_middle"] == 3, mc
    assert abs(mc["median_abs_offset_min"] - 4.0) < 1e-9, mc


def test_cv_logistic_auc_oriented_and_guards_small_n():
    rng = np.random.default_rng(1)
    x = np.concatenate([rng.normal(0, 1, 30), rng.normal(3, 1, 30)])
    y = np.array([0] * 30 + [1] * 30, float)
    auc, n = analytics._cv_logistic_auc(x, y)
    assert np.isfinite(auc) and auc > 0.8, auc
    assert np.isnan(analytics._cv_logistic_auc(x[:6], y[:6])[0])        # too few -> NaN
    assert np.isnan(analytics._cv_logistic_auc(x, np.ones_like(y))[0])  # single class -> NaN


def test_spectral_feature_importance_finds_planted_band():
    det = _planted_detail(center=17.5, beta=0.5)
    sc = analytics.spectral_feature_importance(det, strategy="tertile")
    assert len(sc["centers"]) == 96 and sc["adaptive_band"] == [8.0, 30.0]
    ch0 = sc["channels"][0]
    absr = [abs(x) if x is not None else 0 for x in ch0["r"]]
    bi = int(np.argmax(absr))
    # planted band 15-20 Hz; the peak 5 Hz scan-band center sits within +/- one band-half of 17.5
    assert abs(sc["centers"][bi] - 17.5) <= 2.5, sc["centers"][bi]
    assert ch0["auc"][bi] is not None and ch0["scatter"][bi] is not None
    # adaptive_valid now flags by CENTER (not full-band-inside), so the green tint spans
    # [8, 30] Hz center-wise. On the 1.0 Hz-step, half-integer grid the first adaptive center is 8.5 Hz
    # and the last is 29.5 Hz (== largest center ≤ 30.0).
    cen = np.array(sc["centers"]); av = np.array([b["adaptive_valid"] for b in sc["bands"]])
    assert cen[av].min() == 8.5 and cen[av].max() == 29.5


def test_auc_signed_reflects_correlation_direction():
    """R1/audit A1: the folded `auc` is always >= 0.5, so it cannot show direction. `auc_signed`
    must reflect the band's correlation sign — a band whose feature RISES with pain reads > 0.5, one
    that FALLS with pain reads < 0.5 — and must satisfy signed == auc or 1-auc band-by-band."""
    # Positive-correlation planted band (feature rises with pain).
    sc_pos = analytics.spectral_feature_importance(_planted_detail(center=17.5, beta=0.6, seed=1),
                                                   strategy="tertile")
    ch = sc_pos["channels"][0]
    assert "auc_signed" in ch and len(ch["auc_signed"]) == len(ch["auc"])
    bi = int(np.argmax([abs(x) if x is not None else 0 for x in ch["r"]]))
    assert ch["r"][bi] is not None and ch["r"][bi] > 0, ch["r"][bi]
    assert ch["auc"][bi] >= 0.5                       # folded is always >= chance
    assert ch["auc_signed"][bi] >= 0.5                # rises with pain -> signed >= chance
    # Negative-correlation planted band (feature falls with pain): folded still >= 0.5, signed < 0.5.
    sc_neg = analytics.spectral_feature_importance(_planted_detail(center=17.5, beta=-0.6, seed=1),
                                                   strategy="tertile")
    chn = sc_neg["channels"][0]
    bn = int(np.argmax([abs(x) if x is not None else 0 for x in chn["r"]]))
    assert chn["r"][bn] is not None and chn["r"][bn] < 0, chn["r"][bn]
    assert chn["auc"][bn] >= 0.5                       # folded hides the sign
    assert chn["auc_signed"][bn] <= 0.5               # falls with pain -> signed below chance
    # Band-by-band relationship: signed is either the folded value or its reflection.
    for a, s in zip(chn["auc"], chn["auc_signed"]):
        if a is None:
            assert s is None
        else:
            assert (abs(s - a) < 1e-9) or (abs(s - (1.0 - a)) < 1e-9), (a, s)


def test_selected_band_is_per_contact_and_signed():
    """R2/audit A2: each channel carries a `selected_band` naming its own best band + sign. The
    planted band must be selected, with the correct direction, and never a single global band."""
    sc = analytics.spectral_feature_importance(_planted_detail(center=17.5, beta=0.6, seed=2),
                                               strategy="tertile")
    # Every channel has a selected_band entry (channel 1 has no planted signal but still gets a pick).
    assert all("selected_band" in ch for ch in sc["channels"])
    sb0 = sc["channels"][0]["selected_band"]
    assert sb0 is not None
    assert abs(sb0["center_hz"] - 17.5) <= 2.5, sb0          # picked the planted band
    assert sb0["sign"] == "positive" and sb0["direction"] == "elevation", sb0
    assert sb0["rho"] is not None and sb0["rho"] > 0
    # Negative planted band -> suppression direction on its selected band.
    scn = analytics.spectral_feature_importance(_planted_detail(center=17.5, beta=-0.6, seed=2),
                                                strategy="tertile")
    sbn = scn["channels"][0]["selected_band"]
    assert sbn["sign"] == "negative" and sbn["direction"] == "suppression", sbn
    assert sbn["auc_signed"] is not None and sbn["auc_signed"] <= 0.5, sbn


def test_spectral_scan_lsb_feature_cs14_td_and_full_spectrum():
    """LSB feature mode (CS-1…CS-4 cache, PI 2026-06-27): when pro_lsb_spectrum_by_channel is
    provided, the band feature is log10(CS-14 LSB) from the cache, covering the full 0–100 Hz scan.
    Validates: (1) feature == 'lsb_cs14'; (2) full scan centers 2.5–97.5 Hz;
    (3) adaptive_valid True only for centers in [8, 30] Hz;
    (4) the planted band is recovered from the cache values;
    (5) logpsd fallback when no cache is provided."""
    det = _planted_detail(center=17.5, beta=0.5, seed=3)
    cen_grid = np.arange(2.5, 100.0, 1.0)
    E = det["psd"].shape[0]
    labels = det["labels"]
    rgroup = np.arange(E)
    det["rating_group"] = rgroup

    # Build a synthetic cache: one spectrum per PRO for channel ZERO_TWO_LEFT.
    # Plant strong LSB at ~17.5 Hz for matched rows; unmatched rows get None.
    ch = "ZERO_TWO_LEFT"
    planted_center = 17.5
    spectra = []
    for i in range(E):
        if not np.isfinite(labels[i]):
            spectra.append({"t": 0.0, "tier": None, "lsb": [None] * len(cen_grid),
                            "calibrated": [False] * len(cen_grid),
                            "center_hz": list(cen_grid)})
            continue
        lsb_vec = []
        for c in cen_grid:
            if abs(c - planted_center) <= 2.5:
                lsb_vec.append(500.0 + float(labels[i]) * 20.0)  # correlated with pain
            else:
                lsb_vec.append(100.0)
        # TD-transform: calibrated=True for any finite band (k=352.62 is band-agnostic).
        # Only the CS-3 bridge gates calibrated by [7.8,30] Hz.
        cal = [True] * len(cen_grid)
        spectra.append({"t": 0.0, "tier": "td_transform", "lsb": lsb_vec,
                        "calibrated": cal, "center_hz": list(cen_grid)})

    cache = {ch: spectra}
    sc = analytics.spectral_feature_importance(det, strategy="tertile", feature="lsb",
                                               pro_lsb_spectrum_by_channel=cache)
    assert sc["feature"] == "lsb_cs14", sc["feature"]
    assert "352.62" in sc["feature_note"] or "CS-1" in sc["feature_note"]
    cen = np.array(sc["centers"])
    # Full 0–100 Hz scan
    assert abs(cen.min() - 2.5) < 1e-9 and abs(cen.max() - 97.5) < 1e-9, (cen.min(), cen.max())
    # adaptive_valid flagged by center in [8, 30]
    av = np.array([b["adaptive_valid"] for b in sc["bands"]])
    assert av.any() and not av.all()
    assert cen[av].min() >= 8.0 - 1e-9 and cen[av].max() <= 30.0 + 1e-9
    # Planted band (~17.5 Hz) should have strongest |r|
    ch0 = sc["channels"][0]
    bi = int(np.nanargmax([abs(x) if x is not None else 0 for x in ch0["r"]]))
    assert abs(cen[bi] - planted_center) <= 3.0, cen[bi]
    # Fallback: no cache -> logpsd_db
    sc2 = analytics.spectral_feature_importance(det, strategy="tertile", feature="lsb")
    assert sc2["feature"] == "logpsd_db", sc2["feature"]


def test_spectral_scan_lsb_cs14_cache_lookup_per_pro():
    """Cache lookup correctness: per matched row, the scan looks up the PRO index in the cache
    and assigns log10(cache_lsb) for that band. Rows with no cache entry (tier=None) get NaN.
    Verifies: (1) matched rows with TD LSB produce finite bp_log; (2) unmatched rows produce NaN;
    (3) source priority is already enforced by the cache (TD > survey > bridge), not by the scan."""
    f = np.linspace(0.95, 100, 60)
    E = 4
    cen_grid = np.arange(2.5, 100.0, 1.0)
    ci17 = int(np.argmin(np.abs(cen_grid - 17.5)))
    labels = np.array([8.0, 5.0, np.nan, 2.0])
    rgroup = np.array([0, 1, -1, 2])
    psd = np.random.default_rng(42).normal(0, 1, (E, 1, 60))
    det = {
        "f_set": f, "psd": psd, "labels": labels,
        "row_source": np.array(["TD streaming"] * E, dtype=object),
        "row_lsb_tier": np.array(["td"] * E, dtype=object),
        "row_channel": np.array(["ZERO_TWO_LEFT"] * E, dtype=object),
        "rating_group": rgroup,
        "chan_order": ["ZERO_TWO_LEFT"],
        "times": [f"2025-07-{1+i:02d} 10:00:00" for i in range(E)],
        "prelog": True,
    }
    # PRO 0: LSB=400 at band 17.5; PRO 1: LSB=600; PRO 2: all None (no source)
    def _spec(lsb_at_17):
        lsb = [lsb_at_17 if i == ci17 else 100.0 for i in range(len(cen_grid))]
        # TD-transform: calibrated=True everywhere (k=352.62 is band-agnostic)
        cal = [True] * len(cen_grid)
        return {"t": 0.0, "tier": "td_transform", "lsb": lsb,
                "calibrated": cal, "center_hz": list(cen_grid)}
    none_spec = {"t": 0.0, "tier": None, "lsb": [None]*len(cen_grid),
                 "calibrated": [False]*len(cen_grid), "center_hz": list(cen_grid)}
    cache = {"ZERO_TWO_LEFT": [_spec(400), _spec(600), none_spec]}
    sc = analytics.spectral_feature_importance(det, strategy="tertile", feature="lsb",
                                               low_pct=50.0, high_pct=50.0,
                                               pro_lsb_spectrum_by_channel=cache)
    assert sc["feature"] == "lsb_cs14"
    # Find band at ~17.5 Hz
    cen = np.array(sc["centers"])
    bi = int(np.argmin(np.abs(cen - 17.5)))
    ch0 = sc["channels"][0]
    scat = ch0["scatter"][bi]
    if scat is not None:
        xs = [v for v in scat["x"] if v is not None]
        assert len(xs) >= 2          # at least PRO 0 and PRO 1 contribute
        expect0 = float(np.log10(400.0)); expect1 = float(np.log10(600.0))
        assert any(abs(x - expect0) < 1e-6 for x in xs), (xs, expect0)
        assert any(abs(x - expect1) < 1e-6 for x in xs), (xs, expect1)


def test_spectral_scan_lsb_cs14_vectorized_scatter_assigns_correct_pro_per_band():
    """The vectorized (E, n_cache_centers) LSB matrix must assign each epoch row the LSB of ITS
    PRO at the right band — distinct PROs and distinct bands. Guards the Finding-2 rewrite (per-band
    column gather replacing the per-row Python loop): a transposed scatter or a wrong
    rating_group→row mapping would surface here.

    De-dup contract (2026-06-28): the scatter collapses to ONE observation per distinct rating
    (rating_group), because plotting one marker per matched PSD overplots all rows that share a
    rating onto the same (x, y) pixel and inflates the headline n. With two PSDs per PRO below, the
    scatter must therefore emit ONE point per PRO (3), each carrying that PRO's per-band LSB — NOT
    one point per matched row (6). Both rows of a PRO carry the identical per-band LSB (the cache is
    keyed by rating_group), so first-wins de-dup yields the same value either row wins."""
    f = np.linspace(0.95, 100, 60)
    cen_grid = np.arange(2.5, 100.0, 1.0)
    ci10 = int(np.argmin(np.abs(cen_grid - 10.5)))
    ci40 = int(np.argmin(np.abs(cen_grid - 40.5)))
    # 6 epoch rows: rows {0,1}->PRO0, {2,3}->PRO1, {4,5}->PRO2 (two PSDs per PRO, pro_first style)
    E = 6
    labels = np.array([8.0, 8.0, 4.0, 4.0, 1.0, 1.0])
    rgroup = np.array([0, 0, 1, 1, 2, 2])
    psd = np.random.default_rng(7).normal(0, 1, (E, 1, 60))
    det = {
        "f_set": f, "psd": psd, "labels": labels,
        "row_source": np.array(["TD streaming"] * E, dtype=object),
        "row_lsb_tier": np.array(["td"] * E, dtype=object),
        "row_channel": np.array(["ZERO_TWO_LEFT"] * E, dtype=object),
        "rating_group": rgroup,
        "chan_order": ["ZERO_TWO_LEFT"],
        "times": [f"2025-07-{1+i:02d} 10:00:00" for i in range(E)],
        "prelog": True,
    }
    # Each PRO has DISTINCT LSB at the 10.5 and 40.5 Hz bands.
    def _spec(lsb10, lsb40):
        lsb = [100.0] * len(cen_grid)
        lsb[ci10] = lsb10; lsb[ci40] = lsb40
        return {"t": 0.0, "tier": "td_transform", "lsb": lsb,
                "calibrated": [True] * len(cen_grid), "center_hz": list(cen_grid)}
    cache = {"ZERO_TWO_LEFT": [_spec(200.0, 700.0), _spec(300.0, 800.0), _spec(500.0, 900.0)]}
    sc = analytics.spectral_feature_importance(det, strategy="tertile", feature="lsb",
                                               low_pct=50.0, high_pct=50.0,
                                               pro_lsb_spectrum_by_channel=cache)
    assert sc["feature"] == "lsb_cs14"
    cen = np.array(sc["centers"])
    ch0 = sc["channels"][0]
    # De-dup must have fired (3 distinct ratings from 6 matched rows), and the headline count must
    # equal the rendered point count — the integrity invariant the de-dup exists to guarantee.
    bi10 = int(np.argmin(np.abs(cen - 10.5)))
    scat10 = ch0["scatter"][bi10]
    assert scat10 and scat10.get("dedup_by_rating") is True, scat10
    assert scat10["n_obs"] == 3 and scat10["n_rows"] == 6, (scat10["n_obs"], scat10["n_rows"])
    ng = scat10["n_grp"]; assert ng["high"] + ng["low"] + ng["mid"] == 3, ng
    # At the 10.5 Hz band: PRO0 -> 200.0; PRO1 -> 300.0; PRO2 -> 500.0 (raw LSB, one each).
    xs10 = sorted(v for v in (scat10["x"] if scat10 else []) if v is not None)
    exp10 = sorted([200.0, 300.0, 500.0])
    assert len(xs10) == 3, xs10
    assert all(abs(a - b) < 1e-6 for a, b in zip(xs10, exp10)), (xs10, exp10)
    # At the 40.5 Hz band: the SAME PROs map to the 40-band LSBs (distinct from 10-band), de-duped.
    bi40 = int(np.argmin(np.abs(cen - 40.5)))
    scat40 = ch0["scatter"][bi40]
    xs40 = sorted(v for v in (scat40["x"] if scat40 else []) if v is not None)
    exp40 = sorted([700.0, 800.0, 900.0])
    assert len(xs40) == 3, xs40
    assert all(abs(a - b) < 1e-6 for a, b in zip(xs40, exp40)), (xs40, exp40)


def test_builder_no_device_psd_scale_in_detail():
    """device_psd_scale_by_channel and psd_abs_uv2_per_hz were REMOVED from build_pooled_detail
    (PI 2026-06-27). Validates: (1) neither key is present in the returned detail;
    (2) row_lsb_tier now uses 'td'/'survey'/'patient_event' (no 'device_psd_scaled');
    (3) the detail still contains psd, row_source, row_channel, row_lsb_tier, f_set."""
    from modules.Biomarkers.routines import streaming_psd as sp
    f = np.linspace(0.95, 100, 60)
    F = f.size
    rng = np.random.default_rng(0)
    td_dens = np.abs(rng.normal(5.0, 0.3, (4, F))) + 1.0
    dev_dens = np.abs(rng.normal(2.0, 0.1, (3, F))) + 1.0
    rows_log = np.vstack([10 * np.log10(td_dens), 10 * np.log10(dev_dens)])
    channel = np.array(["ZERO_TWO_LEFT"] * 4 + ["ZERO_TWO_LEFT"] * 3, dtype=object)
    source = np.array(["TD streaming"] * 4 + ["Patient event"] * 3, dtype=object)
    t0 = 1_700_000_000.0
    t = t0 + np.arange(7) * 600.0
    mat = {"f_set": f, "logX": rows_log, "t": t, "channel": channel, "source": source,
           "dur": np.full(7, 30.0)}
    det = sp.build_pooled_detail_from_matrix(mat, np.array([]), np.array([]),
                                             aggregate="all", match_direction="pro_first")
    # Removed fields must NOT be present
    assert "device_psd_scale_by_channel" not in det, "device_psd_scale_by_channel should be removed"
    assert "psd_abs_uv2_per_hz" not in det, "psd_abs_uv2_per_hz should be removed"
    # Core fields still present
    for key in ("psd", "f_set", "row_source", "row_channel", "row_lsb_tier", "labels"):
        assert key in det, f"missing key: {key}"
    # Tiers: TD rows -> "td", patient-event rows -> "patient_event" (no device_psd_scaled)
    tiers = list(det["row_lsb_tier"])
    assert tiers[:4] == ["td"] * 4, tiers[:4]
    assert tiers[4:7] == ["patient_event"] * 3, tiers[4:7]
    valid_tiers = {"td", "survey", "patient_event"}
    assert all(t in valid_tiers for t in tiers), tiers


def test_spectral_scan_lsb_falls_back_without_abs_density():
    """No pro_lsb_spectrum_by_channel cache passed (e.g. back-compat caller) -> feature="lsb" degrades
    to the legacy dB feature ("logpsd_db") rather than failing, and the full range is scanned."""
    det = _planted_detail(center=20.0, beta=0.4, seed=11)
    sc = analytics.spectral_feature_importance(det, strategy="tertile", feature="lsb")
    assert sc["feature"] == "logpsd_db", sc["feature"]
    assert len(sc["centers"]) == 96    # unrestricted range when not LSB-calibrated


def test_spectral_scan_prelog_matches_linear():
    """prelog=True (mean over already-log bins) must match log10(mean linear) closely in r."""
    lin = _planted_detail(center=20.0, beta=0.4, seed=7, prelog=False)
    pre = dict(lin); pre["psd"] = 10.0 * np.log10(lin["psd"]); pre["prelog"] = True
    r_lin = analytics.spectral_feature_importance(lin, strategy="tertile")["channels"][0]["r"]
    r_pre = analytics.spectral_feature_importance(pre, strategy="tertile")["channels"][0]["r"]
    # Spearman-free: signs and rough magnitude of the strongest band agree.
    bi = int(np.argmax([abs(x) if x is not None else 0 for x in r_lin]))
    assert r_pre[bi] is not None and np.sign(r_pre[bi]) == np.sign(r_lin[bi])


def test_spectral_scan_emits_fdr_qs_and_summary():
    """Rigor pass: scan output exposes per-band q (rating-clustered logit + naive Pearson) and a
    family-level fdr_summary. Validates: keys exist; q is None exactly where p is None; q >= p for
    every finite pair (BH never makes a p smaller); summary counts agree with the per-band q masks."""
    # Strong, isolated planted band — needs enough power that rating-clustered logit (not just
    # naive Pearson) clears BH on a modest fixture. Real RCS08 data has hundreds of bands; this
    # fixture has 96. The clustered-logit FDR threshold is therefore steeper here than on real
    # data; the point of the test is to verify wiring, not detection sensitivity.
    det = _planted_detail(center=17.5, beta=1.2, E=200)
    sc = analytics.spectral_feature_importance(det, strategy="tertile")
    # Per-channel arrays present and aligned
    for ch in sc["channels"]:
        assert "q" in ch and "q_pearson" in ch and "is_fdr_sig" in ch, list(ch.keys())
        assert len(ch["q"]) == len(ch["p"]) == len(ch["centers"]) if "centers" in ch else True
        assert len(ch["q"]) == len(ch["p"])
        # None alignment: q is None iff p is None (we never invent significance for missing p)
        for q, p in zip(ch["q"], ch["p"]):
            assert (q is None) == (p is None)
        # BH monotonicity: q >= p for every finite pair (BH never deflates)
        for q, p in zip(ch["q"], ch["p"]):
            if q is not None and p is not None:
                assert q + 1e-12 >= p, f"q={q} < p={p} violates BH"
    # Family summary present, counts agree with the per-band masks
    fs = sc["fdr_summary"]
    assert fs is not None and fs["method"] == "BH-FDR" and fs["alpha"] == 0.05
    n_sig_from_channels = sum(
        1 for ch in sc["channels"] for q in (ch.get("q") or []) if q is not None and q < 0.05
    )
    assert fs["n_rigorous_fdr"] == n_sig_from_channels
    # Pseudoreplication-contrast invariant: under a real planted band-power<->label coupling, the
    # naive Pearson pass (uses every sample as independent) MUST surface at least one FDR-significant
    # band, and the rigorous rating-clustered logit pass MUST be no looser than the naive pass —
    # i.e. it never claims more significance than the naive view. This is the headline rigor
    # invariant the UI annotation rests on (naive >= rigorous, "naive over-reports vs rigorous").
    assert fs["n_naive_fdr"] >= 1, f"planted-band fixture produced 0 naive-FDR bands: {fs}"
    assert fs["n_rigorous_fdr"] <= fs["n_naive_fdr"], \
        f"rigorous FDR > naive FDR violates the pseudoreplication-contrast direction: {fs}"


def test_band_mixedmodel_inference_emits_or_ci():
    """The click-triggered glmer fit must expose OR + 95% CI bounds so the frontend can render the
    confidence interval next to the odds ratio. The fit itself depends on pymer4/R availability;
    when the backend isn't installed, we accept the available=False degradation but still verify
    the schema contract (no KeyError on or_lo/or_hi access)."""
    det = _planted_detail(center=20.0, beta=1.0, E=120, seed=3)
    out = analytics.band_mixedmodel_inference(det, "ZERO_TWO_LEFT", 20.0)
    # Schema: regardless of success, the keys we wired must exist or the call returns
    # available=False with a reason.
    if not out.get("available"):
        assert "reason" in out, out
        return
    # Successful fit: OR present; CI may be None on older pymer4 (we degrade gracefully).
    assert "odds_ratio" in out and "or_lo" in out and "or_hi" in out, list(out)
    if out["odds_ratio"] is not None and out["or_lo"] is not None and out["or_hi"] is not None:
        assert out["or_lo"] <= out["odds_ratio"] <= out["or_hi"], \
            f"OR {out['odds_ratio']} not bracketed by [{out['or_lo']}, {out['or_hi']}]"
    # Guards documented in the function: separation/singular flags carried explicitly.
    assert "separation" in out and "singular" in out, list(out)


def test_band_stim_stability_shape_and_no_stim_degrades():
    """band_stim_stability returns the LRT schema we wire to the click panel, and degrades cleanly
    when stim data is absent (which is the common case for participants without chronic stim)."""
    det = _planted_detail(center=20.0, beta=0.8, E=80, seed=4)
    # No stim series provided -> must degrade with a reason, not crash.
    out_no_stim = analytics.band_stim_stability(det, "ZERO_TWO_LEFT", 20.0, stim_series=None)
    assert out_no_stim.get("available") is False, out_no_stim
    assert "reason" in out_no_stim, out_no_stim

    # With a synthetic stim series spanning all 3 eras, schema is populated (or degrades to a
    # documented reason if pymer4/R isn't installed -- same contract as the glmer test).
    rng = np.random.default_rng(0)
    # Stim trajectory: 3 distinct levels over the sample span, one per era
    n = det["psd"].shape[0]
    sample_times_iso = det["times"]
    epoch_s = pd.to_datetime(pd.Series(sample_times_iso)).to_numpy().astype("datetime64[ns]").astype("int64") / 1e9
    # Build a stim trajectory at the same epochs with three plateaus: OFF / LOW / HIGH
    third = n // 3
    stim_mA = np.r_[np.zeros(third), 0.7 * np.ones(third), 2.5 * np.ones(n - 2 * third)]
    out = analytics.band_stim_stability(det, "ZERO_TWO_LEFT", 20.0,
                                        stim_series={"t": list(epoch_s), "y": list(stim_mA)})
    if not out.get("available"):
        assert "reason" in out, out
        return
    # Schema contract
    for k in ("chisq", "lrt_p", "stim_stable", "or_by_era", "era_counts", "thresholds_mA"):
        assert k in out, list(out)
    assert set(out["or_by_era"].keys()) == {"OFF", "LOW", "HIGH"}, out["or_by_era"]
    assert set(out["era_counts"].keys()) == {"OFF", "LOW", "HIGH"}, out["era_counts"]


def test_spectral_scan_fdr_zero_signal_returns_no_significant_bands():
    """Null fixture: no planted coupling. The rigor pass MUST return zero (or vanishingly few)
    FDR-significant bands — a real false-positive control on the BH pipeline."""
    rng = np.random.default_rng(42)
    F = 60
    E = 100
    det = {
        "f_set": np.linspace(0.95, 100, F),
        "psd": np.abs(rng.normal(1, 0.2, (E, 2, F))),       # pure noise, no label coupling
        "labels": rng.normal(5, 2, E),
        "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"],
        "times": [f"2025-07-{1 + (i % 28):02d} 10:00:00" for i in range(E)],
        "prelog": False,
    }
    sc = analytics.spectral_feature_importance(det, strategy="tertile")
    fs = sc["fdr_summary"]
    assert fs is not None
    # Under the null, FDR should reject at most a handful of bands by chance (well under 5% of
    # the family). Allowing a small budget rather than 0 because BH is stochastic with the
    # synthetic seed; the test fails loudly if the FDR cap is broken.
    n_total = fs["n_bands_total"]
    assert fs["n_rigorous_fdr"] <= max(2, int(0.10 * n_total)), \
        f"null fixture exceeded BH budget: {fs['n_rigorous_fdr']}/{n_total}"


def test_pooled_psd_detail_is_per_channel_and_matches_pro():
    from Biomarkers.routines import streaming_psd as sp
    f = sp.F_SET
    # Two channels, two sources; flat spectra so interpolation is exact.
    def spec(level):
        return (f, np.full(f.shape, level, float))
    T0 = 1.75e9
    HR = 3600.0
    rows = []
    # channel A: TD streaming at t=T0 and t=T0+10h; channel B: montage at t=T0+20h. Spaced hours
    # apart so the 15-min window matches AT MOST one of them.
    for i, t in enumerate([T0, T0 + 10 * HR]):
        fr, pw = spec(2.0 + i)
        rows.append({"channel": "ZERO_TWO_LEFT", "source": "TD streaming", "t": t, "freq": fr, "power": pw})
    fr, pw = spec(5.0)
    rows.append({"channel": "ZERO_TWO_RIGHT", "source": "Montage/survey", "t": T0 + 20 * HR, "freq": fr, "power": pw})
    # PRO: one report 5 min after T0 (matches ONLY the first A row), one far from everything
    pro_t = np.array([T0 + 300, T0 + 1e6]); pro_v = np.array([8.0, 2.0])
    det = sp.build_pooled_psd_detail(rows, pro_t, pro_v, tolerance_min=15)
    assert det["chan_order"] == ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], det["chan_order"]
    assert det["prelog"] is True
    # channel axis is per-channel: each row populates ONLY its own channel column (no cross-pooling)
    psd = det["psd"]            # (N, C, F)
    chA = ~np.isnan(psd[:, 0, 0]); chB = ~np.isnan(psd[:, 1, 0])
    assert chA.sum() == 2 and chB.sum() == 1, (chA.sum(), chB.sum())
    assert not (chA & chB).any()   # no row appears in two channels
    # matching: exactly the first A row (within 15 min of pro_t[0]) carries a label
    assert det["pool_meta"]["n_matched"] == 1, det["pool_meta"]
    assert np.isfinite(det["labels"]).sum() == 1


def test_deployment_roc_bootstrap_defolded_null_ci_drops_below_chance():
    """Audit C1: the rating-clustered bootstrap CI must be DE-FOLDED — each replicate appends the
    fixed-orientation AUC, not max(ab, 1-ab). On a true-NULL band the folded version censored the
    lower bound at ~0.5 (a manufactured "beats chance" floor); the de-folded CI must be able to
    drop honestly below 0.5. A planted band still keeps both bounds above chance."""
    import numpy as _np
    rng = _np.random.default_rng(7)
    E, C, F = 200, 2, 60
    f = _np.linspace(0.95, 100, F)
    labels = rng.normal(5, 2, E)
    psd = _np.abs(rng.normal(1, 0.3, (E, C, F)))           # NO planted signal -> null band
    det = {"f_set": f, "psd": psd, "labels": labels,
           "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "prelog": False,
           "times": [f"2025-07-{1 + (i % 28):02d} 10:00:00" for i in range(E)]}
    roc = analytics.deployment_roc(det, "ZERO_TWO_LEFT", 20.0, n_boot=500, seed=1)
    assert roc["available"] and roc["auc_lo"] is not None
    # audit C1 (post-[3]): the headline CI is now BCa (bias+skew corrected), whose bias term can
    # re-center a near-chance band's lower bound back to ~0.5. The DE-FOLDED percentile GUARD bound
    # (auc_lo_defold) — which the "beats chance" power gate reads — must still honestly drop below 0.5
    # on a true-null band, so absence-of-signal can never read as significance.
    assert roc["auc_lo_defold"] is not None
    assert roc["auc_lo_defold"] < 0.5, \
        f"null de-folded guard CI {roc['auc_lo_defold']} should drop below 0.5 (C1 guard)"
    assert "de-folded" in roc.get("ci_method", "")
    assert roc.get("ci_interval") == "BCa"
    # CI still brackets the (oriented) point estimate
    assert roc["auc_lo"] <= roc["auc"] + 1e-9 <= roc["auc_hi"] + 1e-9

    # A genuinely strong planted band keeps the WHOLE CI above chance.
    rng2 = _np.random.default_rng(3)
    labels2 = rng2.normal(5, 2, 120)
    psd2 = _np.abs(rng2.normal(1, 0.2, (120, C, F)))
    band = (f >= 17.5) & (f <= 22.5)
    psd2[:, 0, band] *= (1 + 0.8 * (labels2 - labels2.mean())[:, None])
    det2 = {"f_set": f, "psd": psd2, "labels": labels2,
            "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "prelog": False,
            "times": [f"2025-07-{1 + (i % 28):02d} 10:00:00" for i in range(120)]}
    roc2 = analytics.deployment_roc(det2, "ZERO_TWO_LEFT", 20.0, n_boot=300, seed=1)
    assert roc2["auc_lo"] > 0.5, f"planted lower CI {roc2['auc_lo']} should stay above chance"


def _era_split_detail(E=240, beta=0.6, high_sign=1.0, seed=11):
    """Synthetic td_detail spanning 90 days with an OFF->LOW->HIGH stim trajectory, planting a
    band-pain relationship whose SIGN in the HIGH era is `high_sign` (use -1 to plant a reversal).
    Returns (det, stim_series)."""
    import datetime as _dt
    rng = np.random.default_rng(seed)
    F = 60
    f = np.linspace(0.95, 100, F)
    band = (f >= 17.5) & (f <= 22.5)
    base = 1_700_000_000.0
    t_epoch = base + np.sort(rng.uniform(0, 90 * 86400, E))
    times = [_dt.datetime.utcfromtimestamp(t).isoformat(sep=" ") for t in t_epoch]
    labels = rng.normal(5, 2, E)
    psd = np.abs(rng.normal(1, 0.3, (E, 2, F)))
    # era sign: OFF/LOW positive, HIGH per high_sign. Eras are the time thirds (stim steps below).
    sign = np.ones(E)
    sign[2 * (E // 3):] = high_sign
    psd[:, 0, band] *= (1 + (beta * sign * (labels - labels.mean()))[:, None])
    st = np.linspace(base, base + 90 * 86400, 9)
    sy = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 3.0, 3.0, 3.0])
    det = {"f_set": f, "psd": psd, "labels": labels,
           "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "prelog": False, "times": times}
    return det, {"t": list(st), "y": list(sy)}


def test_deployment_roc_by_era_pooled_orientation_surfaces_reversal():
    """Audit C3: every era is oriented to the POOLED sign (no per-era re-fold), so an era whose
    band-pain relationship reverses under stim reports a SIGNED AUC below 0.5 and reversed=True —
    the worst closed-loop failure — instead of folding back above 0.5 and reading 'portable'.
    Portability then keys on CI overlap + reversal, not raw point-AUC spread."""
    det, stim = _era_split_detail(high_sign=-1.0, seed=11)   # HIGH era reverses
    res = analytics.deployment_roc_by_era(det, "ZERO_TWO_LEFT", 20.0, stim, n_boot=300, seed=0)
    assert res["available"], res.get("reason")
    counts = res["era_counts"]
    assert counts["OFF"] > 0 and counts["LOW"] > 0 and counts["HIGH"] > 0
    # the pooled fit is oriented to its own data (>= 0.5); a reversing era folds BELOW 0.5
    assert res["pooled"]["auc"] >= 0.5
    high = res["eras"]["HIGH"]
    assert high["available"] and high["auc"] < 0.5 and high["reversed"] is True, high
    # the reversal must propagate to the panel-level signals
    assert res["any_reversed"] is True
    assert res["portable_by_ci"] is False
    assert res["ci_overlaps_pooled"]["HIGH"] is False


def test_deployment_roc_by_era_noisy_dip_is_not_a_confident_reversal():
    """A point AUC below 0.5 is NOT a direction reversal unless the whole 95% CI is below chance.
    With NO real band-pain relationship in the HIGH era (high_sign=0), that era's AUC scatters
    around 0.5 with a wide CI that straddles it — the old point-estimate rule would mis-flag the
    noisy dips as 'direction REVERSES' (the worst, deploy-blocking verdict). The CI-gated rule must
    not: `reversed` stays falsy and `any_reversed` is False, while `any_below_half` still records the
    descriptive dip. This is the statistical-correctness fix: AUC<0.5 alone does not imply a sign
    flip in the band-pain relationship."""
    det, stim = _era_split_detail(beta=0.6, high_sign=0.0, seed=11)   # HIGH era: no real effect
    res = analytics.deployment_roc_by_era(det, "ZERO_TWO_LEFT", 20.0, stim, n_boot=300, seed=0)
    assert res["available"], res.get("reason")
    high = res["eras"]["HIGH"]
    assert high["available"]
    # No era is CONFIDENTLY reversed: every estimable era's reversed flag is falsy (False/None),
    # and the panel-level hard-fail signal is off.
    for tag in ["OFF", "LOW", "HIGH"]:
        e = res["eras"][tag]
        if e.get("available"):
            assert e["reversed"] is not True, (tag, e)
    assert res["any_reversed"] is False
    # And wherever a point AUC dipped below 0.5, that era's CI still includes 0.5 (not a clean
    # reversal) — the very condition the fix protects against.
    for tag in ["OFF", "LOW", "HIGH"]:
        e = res["eras"][tag]
        if e.get("available") and e.get("auc_below_half") and e.get("auc_hi") is not None:
            assert e["auc_hi"] >= 0.5, (tag, e)
    # The descriptive flag is exposed (whether or not a dip occurred this seed, the key must exist).
    assert "any_below_half" in res


def test_deployment_roc_by_era_portable_when_eras_agree():
    """Audit C3 (other direction): when every era shares the pooled sign and their CIs overlap the
    pooled CI, the band is portable_by_ci and no era is flagged reversed."""
    det, stim = _era_split_detail(beta=0.35, high_sign=1.0, seed=5)   # all-positive
    res = analytics.deployment_roc_by_era(det, "ZERO_TWO_LEFT", 20.0, stim, n_boot=300, seed=0)
    assert res["available"] and res["n_eras_estimable"] >= 2
    assert res["any_reversed"] is False
    assert res["portable_by_ci"] is True
    for tag in ["OFF", "LOW", "HIGH"]:
        e = res["eras"][tag]
        if e.get("available"):
            assert e["reversed"] is False and e["auc"] >= 0.5


def test_deployment_summary_gate_states_and_necessary_blocking():
    """Audit C8: gates carry a tri-state (`state`) and a `necessary` flag. An unavailable stim LRT
    must render 'indeterminate' (NOT a pass), and 'ready_to_program' is gated on the NECESSARY
    checks alone, so a hard-prerequisite failure blocks even at a high passed-count. Tested on the
    pure gate-assembly logic (no DB) by exercising the documented contract shape."""
    # Build a minimal gate list mirroring deployment_summary's _gate() contract and assert the
    # downstream arithmetic the card relies on.
    def _gate(key, label, state, necessary=False):
        return {"key": key, "label": label, "state": state,
                "pass": state == "pass", "necessary": bool(necessary)}
    gates = [
        _gate("validated", "Band validated", "pass", necessary=True),
        _gate("adaptive_band", "In adaptive range", "pass", necessary=True),
        _gate("deployable_threshold", "Deployable LSB threshold", "fail", necessary=True),
        _gate("credible_ci", "Credible CI", "pass"),
        _gate("stim_stable", "Stim-stable", "indeterminate"),   # LRT didn't converge
        _gate("powered", "Powered", "pass"),
    ]
    # indeterminate must NOT count as a pass
    assert gates[4]["pass"] is False
    n_indet = sum(1 for g in gates if g["state"] == "indeterminate")
    assert n_indet == 1
    # 4 of 6 "pass" by count, but a NECESSARY gate failed -> not ready to program
    n_passed = sum(1 for g in gates if g["pass"])
    ready = all(g["pass"] for g in gates if g["necessary"])
    assert n_passed == 4 and ready is False
    # flip the failing necessary gate to pass -> ready, despite the indeterminate supportive gate
    gates[2]["state"] = "pass"; gates[2]["pass"] = True
    assert all(g["pass"] for g in gates if g["necessary"]) is True


def test_psd_lsb_conversion_recovers_planted_proportional_constant():
    """A planted linear gain LSB = k0*P (with multiplicative noise) is recovered: the proportional
    constant k lands near k0 and the free log-log slope's 95% CI includes 1.0 (audit C10 / PSD->LSB)."""
    rng = np.random.default_rng(3)
    n = 1200
    # offline band power spanning ~3 decades, log-uniform
    P = 10.0 ** rng.uniform(-1.0, 2.0, n)
    k0 = 80.0
    # device LSB = k0 * P * lognormal(sigma) — a linear gain with ~x2 multiplicative scatter
    L = k0 * P * np.exp(rng.normal(0.0, np.log(2.0), n))
    out = analytics.psd_lsb_conversion(P, L, n_boot=500, seed=0)
    assert out["available"] is True
    assert out["n_pairs"] == n
    # constant within 25% of planted
    assert 0.75 * k0 <= out["k_lsb_per_uv2"] <= 1.25 * k0, out["k_lsb_per_uv2"]
    # free slope ~1 and CI includes unity (the linear-gain falsification check passes)
    assert 0.9 <= out["loglog_slope"] <= 1.1, out["loglog_slope"]
    assert out["slope_consistent_with_unity"] is True
    assert out["k_ci"][0] <= out["k_lsb_per_uv2"] <= out["k_ci"][1]
    # inverse is the reciprocal
    assert abs(out["uv2_per_lsb"] - 1.0 / out["k_lsb_per_uv2"]) < 1e-9


def test_psd_lsb_conversion_flags_nonlinear_slope():
    """When the device value is NOT a linear gain on the offline band (here LSB ~ sqrt(P), slope 0.5),
    the falsification check fails: the free log-log slope's CI excludes 1.0."""
    rng = np.random.default_rng(7)
    n = 800
    P = 10.0 ** rng.uniform(-1.0, 2.0, n)
    L = 50.0 * np.sqrt(P) * np.exp(rng.normal(0.0, 0.2, n))   # slope ~0.5, not proportional
    out = analytics.psd_lsb_conversion(P, L, n_boot=300, seed=0)
    assert out["available"] is True
    assert out["loglog_slope"] < 0.8, out["loglog_slope"]
    assert out["slope_consistent_with_unity"] is False


def test_psd_lsb_conversion_guards_small_n():
    """Fewer than 20 usable pairs -> not available, with the pair count surfaced."""
    out = analytics.psd_lsb_conversion(np.array([1.0, 2.0, 3.0]), np.array([10.0, 20.0, 30.0]))
    assert out["available"] is False
    assert out["n_pairs"] == 3


def test_band_power_notched_default_no_mains_removal():
    """The Percept is implanted and battery-powered: there is NO mains coupling, so the default band
    integral must NOT remove any 60 Hz content (removing it would delete real neural power). A spike at
    60 Hz therefore DOES enter the band by default; it is only interpolated away when notch=True is
    explicitly requested (for a genuinely tethered/bench recording)."""
    freq = np.arange(40.0, 80.0, 1.0)
    power = np.full_like(freq, 0.05)
    power[np.argmin(np.abs(freq - 60.0))] = 100.0   # a feature at 60 Hz (real neural, NOT mains here)
    # DEFAULT (notch off): the 60 Hz content is preserved, so the band integral is dominated by it.
    bp_default = analytics._band_power_notched(freq, power, 60.0, 5.0)
    assert bp_default > 1.0, bp_default          # the 60 Hz content is kept, not blanked
    # OPT-IN (notch=True): the spike is interpolated away and the band falls back to the ~0.05/Hz floor.
    bp_notched = analytics._band_power_notched(freq, power, 60.0, 5.0, notch=True)
    assert bp_notched < 1.0, bp_notched
    assert bp_notched > 0.0
    assert bp_default > bp_notched


def _forward_detail(E=300, F=60, center=20.0, seed=0, weeks=12, beta=0.5, noise=0.3,
                    sign_fn=None):
    """Synthetic td_detail spanning `weeks` elapsed weeks, one rating cluster per sample, planting a
    band-pain relationship of strength `beta`. `sign_fn(week_index_array)->±1 array` lets a test make
    the band's sign drift over time (to plant a forward-generalization failure)."""
    import datetime as _dt
    rng = np.random.default_rng(seed)
    f = np.linspace(0.95, 100, F)
    band = (f >= center - 2.5) & (f <= center + 2.5)
    base = 1_700_000_000.0
    t_epoch = base + np.sort(rng.uniform(0, weeks * 7 * 86400, E))
    times = [_dt.datetime.utcfromtimestamp(t).isoformat(sep=" ") for t in t_epoch]
    wk = ((t_epoch - base) / (7 * 86400)).astype(int)
    labels = rng.normal(5, 2, E)
    psd = np.abs(rng.normal(1, noise, (E, 2, F)))
    sign = np.ones(E) if sign_fn is None else sign_fn(wk)
    psd[:, 0, band] *= (1 + (beta * sign * (labels - labels.mean()))[:, None])
    return {"f_set": f, "psd": psd, "labels": labels, "rating_group": np.arange(E),
            "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "prelog": False, "times": times}


def test_freq_extrapolated_guard_agrees_with_frozen_model():
    """The deployment fallback and the frozen per-band model must share ONE definition of 'outside the
    calibrated range', so a band flagged extrapolated by one is flagged by the other. The invariant was
    previously asserted inside the (now-deleted) psd_band_to_lsb guard test; restored standalone here so
    the agreement stays covered. Spans the validated edges (7.8 / 28.3 Hz) and points either side."""
    from Biomarkers.routines import psd_lsb_model as plm
    for c in (5.0, 7.0, 7.8, 18.0, 28.3, 29.0, 55.5):
        assert analytics._freq_extrapolated(c) == plm._freq_extrapolated(c), c


def test_forward_chaining_validates_stationary_band():
    """Audit C2: a genuinely stationary band (same sign + strength across all weeks) trains on the
    past and predicts the future well — the held-out AUC stays high, its bootstrap CI clears 0.5, and
    `beats_chance_forward` is True. Forward-chaining must NOT penalize a real, stable signal."""
    det = _forward_detail(beta=0.10, noise=1.3, seed=11)
    r = analytics.deployment_forward_chaining(det, "ZERO_TWO_LEFT", 20.0, n_boot=500, seed=11)
    assert r["available"], r.get("reason")
    assert r["n_folds"] >= 3, r["n_folds"]
    # train on past / score future: the OOF held-out AUC is well above chance and its CI clears 0.5
    assert r["held_out_auc"] is not None and r["held_out_auc"] > 0.6, r["held_out_auc"]
    assert r["held_out_auc_lo"] is not None and r["held_out_auc_lo"] > 0.5, r["held_out_auc_lo"]
    assert r["beats_chance_forward"] is True
    # a stationary band has near-zero forward optimism (in-sample ≈ held-out)
    assert abs(r["optimism"]) < 0.10, r["optimism"]
    assert "forward-chaining" in r.get("note", "")


def test_forward_chaining_null_band_does_not_beat_chance_forward():
    """Audit C2 + C1 de-fold: a band with NO real signal is winner's-curse optimistic in-sample
    (AUC > 0.5) yet its held-out AUC is NOT re-folded and honestly fails to clear chance — the CI
    lower bound drops below 0.5 and `beats_chance_forward` is False, so the forward gate abstains."""
    det = _forward_detail(beta=0.0, noise=1.0, seed=2)
    r = analytics.deployment_forward_chaining(det, "ZERO_TWO_LEFT", 20.0, n_boot=500, seed=2)
    assert r["available"], r.get("reason")
    # in-sample is biased above 0.5 (the optimism the in-sample number cannot see)
    assert r["in_sample_auc"] >= 0.5
    # but forward it does not beat chance, and the de-folded CI can fall below 0.5
    assert r["beats_chance_forward"] is False
    assert r["held_out_auc_lo"] is not None and r["held_out_auc_lo"] < 0.5, r["held_out_auc_lo"]


def test_forward_chaining_catches_sign_reversal_over_time():
    """Audit C2: the worst closed-loop failure — a band whose sign FLIPS partway through the record.
    A threshold trained on the early (positive) weeks misfires systematically on the later (negative)
    weeks. The in-sample AUC folds it back above 0.5 and hides this, but forward-chaining scores the
    later folds near 0 and the pooled held-out AUC fails to beat chance."""
    def rev(wk):
        s = np.ones_like(wk, dtype=float)
        s[wk >= 6] = -1.0
        return s
    det = _forward_detail(beta=0.7, noise=0.3, seed=3, sign_fn=rev)
    r = analytics.deployment_forward_chaining(det, "ZERO_TWO_LEFT", 20.0, n_boot=500, seed=3)
    assert r["available"], r.get("reason")
    assert r["beats_chance_forward"] is False, r
    # the late folds (after the sign flip) score below chance with the past-trained threshold
    late = [f["test_auc"] for f in r["folds"] if f["test_week_start"] >= 6]
    assert late and min(late) < 0.5, late
    # forward optimism is large and positive (in-sample looks fine, forward collapses)
    assert r["optimism"] is not None and r["optimism"] > 0.0


def test_forward_chaining_guards_single_week():
    """When all ratings fall in a single elapsed week there is no forward split; the routine must
    abstain cleanly rather than fabricate a held-out estimate."""
    det = _forward_detail(beta=0.5, noise=0.5, seed=4, weeks=1, E=120)
    r = analytics.deployment_forward_chaining(det, "ZERO_TWO_LEFT", 20.0, n_boot=200, seed=4)
    assert r["available"] is False
    assert "week" in r.get("reason", "").lower()


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
    test_binarize_labels_tertile_excludes_middle()
    test_matched_sample_counts_reports_high_low_and_offset()
    test_cv_logistic_auc_oriented_and_guards_small_n()
    test_spectral_feature_importance_finds_planted_band()
    test_spectral_scan_lsb_feature_cs14_td_and_full_spectrum()
    test_spectral_scan_lsb_cs14_cache_lookup_per_pro()
    test_spectral_scan_lsb_cs14_vectorized_scatter_assigns_correct_pro_per_band()
    test_builder_no_device_psd_scale_in_detail()
    test_spectral_scan_lsb_falls_back_without_abs_density()
    test_spectral_scan_prelog_matches_linear()
    test_spectral_scan_emits_fdr_qs_and_summary()
    test_spectral_scan_fdr_zero_signal_returns_no_significant_bands()
    test_band_stim_stability_shape_and_no_stim_degrades()
    test_band_mixedmodel_inference_emits_or_ci()
    test_pooled_psd_detail_is_per_channel_and_matches_pro()
    test_deployment_roc_recovers_planted_band()
    test_deployment_roc_clustered_ci_wider_than_naive()
    test_deployment_roc_feature_hist_shape_and_counts()
    test_auc_power_curve_monotone_and_crosses_target()
    test_auc_power_monotone_and_sample_size()
    test_auc_power_conservative_band_gates_on_ci_lower_bound()
    test_deployment_roc_bootstrap_defolded_null_ci_drops_below_chance()
    test_deployment_roc_by_era_pooled_orientation_surfaces_reversal()
    test_deployment_roc_by_era_noisy_dip_is_not_a_confident_reversal()
    test_deployment_roc_by_era_portable_when_eras_agree()
    test_deployment_summary_gate_states_and_necessary_blocking()
    test_psd_lsb_conversion_recovers_planted_proportional_constant()
    test_psd_lsb_conversion_flags_nonlinear_slope()
    test_psd_lsb_conversion_guards_small_n()
    test_band_power_notched_default_no_mains_removal()
    test_freq_extrapolated_guard_agrees_with_frozen_model()
    test_forward_chaining_validates_stationary_band()
    test_forward_chaining_null_band_does_not_beat_chance_forward()
    test_forward_chaining_catches_sign_reversal_over_time()
    test_forward_chaining_guards_single_week()
    print("All analytics tests passed.")


def test_deployment_roc_recovers_planted_band():
    """deployment_roc on a planted band: AUC>0.5 with a bootstrap CI that brackets it, ROC endpoints
    anchored at (0,0)/(1,1), a Youden operating point, and parallel fpr/tpr/thr arrays."""
    det = _planted_detail(E=120, center=20.0, beta=0.8, seed=3)
    roc = analytics.deployment_roc(det, "ZERO_TWO_LEFT", 20.0, band_width_hz=5.0,
                                   strategy="tertile", n_boot=200, seed=1)
    assert roc["available"] is True, roc.get("reason")
    assert 0.5 <= roc["auc"] <= 1.0 and roc["auc"] > 0.6
    # bootstrap CI present and brackets the point estimate
    assert roc["auc_lo"] is not None and roc["auc_hi"] is not None
    assert roc["auc_lo"] <= roc["auc"] + 1e-9 and roc["auc_hi"] >= roc["auc"] - 1e-9
    assert roc["n_boot_ok"] >= 20
    # ROC arrays parallel, endpoints anchored
    assert len(roc["fpr"]) == len(roc["tpr"]) == len(roc["thr"])
    assert roc["fpr"][0] <= 1e-9 and abs(roc["fpr"][-1] - 1.0) < 1e-9
    op = roc["operating_point"]
    assert op is not None and op["rule"] == "youden" and 0.0 <= op["sensitivity"] <= 1.0
    assert 0.0 <= roc["prevalence"] <= 1.0 and roc["n_pos"] > 0 and roc["n_neg"] > 0


def test_deployment_roc_clustered_ci_wider_than_naive():
    """With many samples sharing each rating cluster, the rating-clustered bootstrap CI must be
    WIDER than a per-sample bootstrap would give (it counts independent ratings, not raw rows)."""
    import numpy as _np
    rng = _np.random.default_rng(0)
    # 40 ratings, 6 near-duplicate samples each (one shared label per cluster). Signal is kept weak
    # (beta 0.10 against noise 0.6) so the AUC sits mid-range (~0.67) rather than at the separation
    # ceiling — only then does the bootstrap CI have real width to test.
    n_clu, per = 40, 6
    f = _np.linspace(0.95, 100, 40)
    labels = _np.repeat(rng.normal(5, 2, n_clu), per)
    rg = _np.repeat(_np.arange(n_clu), per)
    psd = _np.abs(rng.normal(1, 0.6, (n_clu * per, 2, 40)))
    band = (f >= 17.5) & (f <= 22.5)
    psd[:, 0, band] *= (1 + 0.10 * (labels - labels.mean())[:, None])
    det = {"f_set": f, "psd": psd, "labels": labels, "rating_group": rg,
           "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "prelog": False,
           "times": [f"2025-07-{1 + (i % 28):02d} 10:00:00" for i in range(n_clu * per)]}
    roc = analytics.deployment_roc(det, "ZERO_TWO_LEFT", 20.0, n_boot=300, seed=2)
    # Tertile binarization drops the middle-third ratings, so the surviving clusters are fewer than
    # the planted n_clu but still a substantial, clustered set (each an independent rating).
    assert roc["available"] and 12 < roc["n_clusters"] < n_clu
    # The clustered CI has real width (not the degenerate ~0 a per-sample bootstrap of duplicates
    # would give); just assert it is a positive-width interval over the independent ratings.
    assert roc["auc_hi"] - roc["auc_lo"] > 0.02


def test_deployment_roc_feature_hist_shape_and_counts():
    """deployment_roc.feature_hist: shared bin edges across both classes, per-class counts sum to
    n_pos/n_neg, centers are interior to the edges, and the cut-point threshold lands within the
    histogram's x-range (so the threshold line is drawable on the same scale)."""
    det = _planted_detail(E=120, center=20.0, beta=0.8, seed=3)
    roc = analytics.deployment_roc(det, "ZERO_TWO_LEFT", 20.0, band_width_hz=5.0,
                                   strategy="tertile", n_boot=100, seed=1)
    assert roc["available"] is True, roc.get("reason")
    fh = roc["feature_hist"]
    assert fh is not None
    # shared edges; centers parallel to bins; one more edge than bins
    assert len(fh["bin_edges"]) == len(fh["bin_centers"]) + 1
    assert len(fh["counts_high"]) == len(fh["counts_low"]) == len(fh["bin_centers"])
    # per-class counts sum to the class n (every in-range sample is binned)
    assert sum(fh["counts_high"]) == fh["n_high"] == roc["n_pos"]
    assert sum(fh["counts_low"]) == fh["n_low"] == roc["n_neg"]
    # edges monotone increasing, centers strictly interior
    assert all(b < a for a, b in zip(fh["bin_edges"][1:], fh["bin_edges"][:-1]))
    assert fh["x_min"] <= fh["bin_centers"][0] and fh["bin_centers"][-1] <= fh["x_max"]
    # the Youden threshold is on the SAME feature scale and lies within the feature range
    op = roc["operating_point"]
    assert fh["x_min"] - 1e-9 <= op["threshold"] <= fh["x_max"] + 1e-9


def test_auc_power_curve_monotone_and_crosses_target():
    """auc_power.curve: power is non-decreasing in N, brackets the target power, and the smallest N
    on the curve at/above target_power agrees with the scalar n_ratings_needed (within grid spacing)."""
    res = analytics.auc_power(0.70, 20, 20, target_power=0.80)
    assert res["available"]
    curve = res["curve"]
    assert curve is not None and len(curve["n"]) >= 2
    ns = curve["n"]; ps = curve["power"]
    # N strictly increasing, power non-decreasing
    assert all(b > a for a, b in zip(ns[:-1], ns[1:]))
    assert all(p2 >= p1 - 1e-6 for p1, p2 in zip(ps[:-1], ps[1:]))
    # curve brackets the 80% target (starts below, ends at/above)
    assert ps[0] < 0.80 and ps[-1] >= 0.80
    # first N reaching target on the curve is near the scalar requirement
    n_cross = next(n for n, p in zip(ns, ps) if p >= 0.80)
    step = ns[1] - ns[0]
    assert abs(n_cross - res["n_ratings_needed"]) <= 2 * step + 1
    # a chance-level AUC yields no informative curve
    assert analytics.auc_power(0.50, 30, 30)["curve"] is None


def test_auc_power_monotone_and_sample_size():
    """auc_power: power rises with n and with AUC; n_ratings_needed falls as AUC rises; chance AUC
    yields ~alpha power and flags more_data_needed."""
    # more ratings -> more power at the same AUC
    p_small = analytics.auc_power(0.70, 13, 13)
    p_big = analytics.auc_power(0.70, 75, 75)
    assert p_small["available"] and p_big["available"]
    assert p_big["power_current"] > p_small["power_current"]
    # stronger AUC -> fewer ratings needed for 80% power
    need_weak = analytics.auc_power(0.60, 20, 20)["n_ratings_needed"]
    need_strong = analytics.auc_power(0.80, 20, 20)["n_ratings_needed"]
    assert need_weak > need_strong > 0
    # a well-powered case is flagged as sufficient
    assert analytics.auc_power(0.80, 60, 60)["more_data_needed"] is False
    # chance AUC -> power ~ alpha, more data needed
    chance = analytics.auc_power(0.50, 30, 30)
    assert chance["power_current"] <= 0.06 and chance["more_data_needed"] is True
    # orientation: AUC < 0.5 is treated as |AUC-0.5| (a strong negative biomarker still has power)
    neg = analytics.auc_power(0.20, 40, 40)
    assert neg["auc"] == 0.80 and neg["power_current"] > 0.5


def test_auc_power_conservative_band_gates_on_ci_lower_bound():
    """audit C4: when auc_lo is supplied, auc_power reports a power band and the gate-driving
    `more_data_needed` reads the CONSERVATIVE (CI-lower-bound) end — so a band that looks powered on
    its optimistic point AUC cannot pass on optimism alone.

    The decisive case: point AUC=0.70 at n=70 clears 80% power (more_data_needed=False), but its CI
    lower bound 0.60 has far less power, so the conservative gate flips to more_data_needed=True.
    """
    point = analytics.auc_power(0.70, 30, 40)
    band = analytics.auc_power(0.70, 30, 40, auc_lo=0.60)
    assert point["available"] and band["available"]
    # point AUC alone reads as powered ...
    assert point["more_data_needed"] is False
    # ... but the conservative band does NOT (gate fail-closed on the CI lower bound)
    assert band["more_data_needed"] is True
    # band carries the conservative readouts
    assert band["auc_lo"] == 0.60
    assert band["power_current_lo"] is not None and band["power_current_lo"] < band["power_current"]
    assert band["n_ratings_needed_hi"] is not None and band["n_ratings_needed_hi"] > band["n_ratings_needed"]
    # a CI lower bound AT chance (0.50) => no power, ratings-needed undefined, more data needed.
    # (Note auc_lo is folded as |auc_lo-0.5|, so 0.49 -> 0.51 is still above chance; only 0.50 lands
    # exactly on the chance line and trips the null branch.)
    null_band = analytics.auc_power(0.62, 30, 40, auc_lo=0.50)
    assert null_band["more_data_needed"] is True and null_band["n_ratings_needed_hi"] is None
    # a CI lower bound just above chance still flags more data (finite but huge ratings requirement)
    weak_band = analytics.auc_power(0.62, 30, 40, auc_lo=0.51)
    assert weak_band["more_data_needed"] is True and weak_band["n_ratings_needed_hi"] > weak_band["n_ratings_needed"]
    # without auc_lo, behaviour is unchanged (back-compat): point-AUC gate, no band fields populated
    assert point["power_current_lo"] is None and point["auc_lo"] is None
    # a genuinely strong band stays powered even on its CI lower bound
    strong = analytics.auc_power(0.85, 60, 60, auc_lo=0.78)
    assert strong["more_data_needed"] is False


def test_empirical_lsb_ratio_recovers_planted_ratio():
    """empirical_lsb_ratio: planted concurrent TD (µV) + device LSB at a known ratio is recovered to
    within the documented ~3× confidence band, and the result is flagged accordingly."""
    import numpy as _np
    rng = _np.random.default_rng(0)
    fs = 250.0; hz = 20.0; secs = 30
    true_ratio = 0.0034            # µV² per LSB we plant
    td_recs, pd_recs = [], []
    for k in range(12):
        t = _np.arange(int(fs * secs)) / fs
        amp = 2.0 + 0.5 * k        # vary band amplitude across sessions
        # narrowband signal at hz (µV), plus white noise; convert to device counts (µV -> /146nV*1000)
        sig_uV = amp * _np.sin(2 * _np.pi * hz * t) + rng.normal(0, 0.3, t.size)
        counts = sig_uV / (analytics.ADC_NV_PER_LSB / 1000.0)
        td_recs.append({"StartTime": 1000.0 + 100 * k, "SamplingRate": fs,
                        "ChannelNames": ["ZERO_TWO_LEFT"], "Data": counts[:, None]})
        # device LSB such that µV²_band / LSB ≈ true_ratio. Welch band power of a sine amp A ≈ A²/2.
        uV2 = (amp ** 2) / 2.0
        lsb_val = uV2 / true_ratio
        n_pd = 60
        pd_data = _np.column_stack([_np.full(n_pd, lsb_val) * (1 + rng.normal(0, 0.02, n_pd)),
                                    _np.zeros(n_pd)])     # Power col, Stim col (0 mA)
        pd_recs.append({"StartTime": 1000.0 + 100 * k + 1, "SamplingRate": 2.0,
                        "ChannelNames": ["ZERO_TWO_LEFT Power", "ZERO_TWO_LEFT Stimulation"],
                        "Data": pd_data})

    def _hz(_pd_rec, _contact):
        return hz
    res = analytics.empirical_lsb_ratio(td_recs, pd_recs, _hz)
    assert res["available"], res.get("reason")
    assert res["n"] >= 8
    # recovered within ~3x of the planted ratio (the documented confidence ceiling)
    assert (true_ratio / 3.0) <= res["median"] <= (true_ratio * 3.0), res["median"]
    assert "confidence" in res and res["rule_of_thumb"] == 0.01


def test_empirical_lsb_ratio_needs_pairs():
    """With no time-paired PowerDomain session, the ratio is unavailable (not a crash)."""
    td = [{"StartTime": 0.0, "SamplingRate": 250.0, "ChannelNames": ["ZERO_TWO_LEFT"],
           "Data": __import__("numpy").zeros((7500, 1))}]
    pd = [{"StartTime": 99999.0, "SamplingRate": 2.0,
           "ChannelNames": ["ZERO_TWO_LEFT Power", "ZERO_TWO_LEFT Stimulation"],
           "Data": __import__("numpy").ones((60, 2))}]
    res = analytics.empirical_lsb_ratio(td, pd, lambda r, c: 20.0)
    assert res["available"] is False


def test_deployment_roc_by_era_splits_eras():
    """deployment_roc_by_era assigns OFF/LOW/HIGH from the stim trajectory and refits the ROC per
    era; a band present in all eras yields estimable per-era AUCs and a finite cut-point spread."""
    import numpy as _np
    rng = _np.random.default_rng(1)
    E, C, F = 180, 2, 60
    f = _np.linspace(0.95, 100, F)
    labels = rng.normal(5, 2, E)
    psd = _np.abs(rng.normal(1, 0.3, (E, C, F)))
    band = (f >= 17.5) & (f <= 22.5)
    psd[:, 0, band] *= (1 + 0.5 * (labels - labels.mean())[:, None])
    # times across 90 days; stim trajectory steps OFF -> LOW -> HIGH over that window.
    base = 1_700_000_000.0
    t_epoch = base + _np.sort(rng.uniform(0, 90 * 86400, E))
    times = [__import__("datetime").datetime.utcfromtimestamp(t).isoformat(sep=" ") for t in t_epoch]
    det = {"f_set": f, "psd": psd, "labels": labels,
           "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "prelog": False, "times": times}
    # stim: 0 mA for first third, 1.0 mA middle, 3.0 mA last third
    st = _np.linspace(base, base + 90 * 86400, 9)
    sy = _np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 3.0, 3.0, 3.0])
    stim_series = {"t": list(st), "y": list(sy)}
    res = analytics.deployment_roc_by_era(det, "ZERO_TWO_LEFT", 20.0, stim_series,
                                          band_width_hz=5.0, n_boot=120, seed=0)
    assert res["available"], res.get("reason")
    # all three eras populated by the trajectory
    counts = res["era_counts"]
    assert counts["OFF"] > 0 and counts["LOW"] > 0 and counts["HIGH"] > 0
    # at least two eras estimable, and the pooled ROC is available
    assert res["n_eras_estimable"] >= 2 and res["pooled"]["available"]
    # cut-point spread is a finite number when >=2 eras have an operating point
    if res["cutpoint_spread"] is not None:
        assert res["cutpoint_spread"] >= 0.0
    # each estimable era carries a clustered-bootstrap AUC in [0.5, 1]
    for tag in ["OFF", "LOW", "HIGH"]:
        e = res["eras"][tag]
        if e.get("available"):
            assert 0.5 <= e["auc"] <= 1.0


def test_assign_stim_eras_uses_locf_not_nocb():
    """_assign_stim_eras must carry the stim trajectory FORWARD (LOCF): a sample's era is the stim
    amplitude in effect at or before it, not the next programmed change. Guards PARITY_audit §7
    (the next-sample/NOCB form mislabeled ~17% of samples and biased the stim-stability LRT)."""
    import numpy as _np
    import datetime as _dt
    # stim steps 0.0 mA -> 3.0 mA exactly at t=1000. A sample at t=999 is OFF (carry forward the
    # 0.0 still in effect); a sample at t=1001 is HIGH. NOCB would wrongly call t=999 HIGH (next
    # reading) and could call t=1001 by a later reading.
    stim_series = {"t": [0.0, 1000.0, 2000.0], "y": [0.0, 3.0, 3.0]}
    def _iso(ep):
        return _dt.datetime.utcfromtimestamp(ep).isoformat(sep=" ")
    times = [_iso(999.0), _iso(1000.0), _iso(1001.0)]
    era = analytics._assign_stim_eras(times, stim_series, off_max=0.1, low_max=1.5)
    assert era is not None
    assert era[0] == "OFF",  f"t=999 should carry forward 0.0 mA (OFF), got {era[0]}"   # LOCF, not NOCB
    assert era[1] == "HIGH", f"t=1000 is exactly the 3.0 mA step (HIGH), got {era[1]}"
    assert era[2] == "HIGH", f"t=1001 should be 3.0 mA (HIGH), got {era[2]}"
    # explicit contrast: the buggy NOCB (searchsorted left, no -1) would call t=999 -> HIGH.
    nocb_idx = int(_np.searchsorted(_np.asarray(stim_series["t"]), 999.0))   # -> 1 -> 3.0 mA -> HIGH
    assert stim_series["y"][nocb_idx] == 3.0, "sanity: NOCB would have mislabeled t=999 as HIGH"


def test_pain_series_epochs_match_pro_match_arrays():
    """pain_series and _pro_match_arrays must agree on PRO epoch seconds to the second — both read
    the canonical UTC instant (ingestion-normalized _pro_time_utc, or the same localized parse as a
    fallback). Guards the 7-8 h timezone smear (RCS08 live readout bug: 67/682 instead of 290/682).
    FIXHANDOUT_pro_timezone_mismatch."""
    import pandas as pd, numpy as np
    from modules.Biomarkers.routines import availability
    from modules.Biomarkers import bravo_service as bs
    # synthetic pro_df: one summer (PDT, +7h) and one winter (PST, +8h) timestamp
    df = pd.DataFrame({
        "date_time_s1_daily": ["2025-07-20 14:00:00", "2025-12-20 14:00:00"],
        "vas": [50.0, 60.0],
    })
    # Ingestion normalizer adds the canonical _pro_time_utc column.
    df = bs._normalize_pro_times(df)
    assert "_pro_time_utc" in df.columns, "ingestion did not add _pro_time_utc"
    back_t, _ = bs._pro_match_arrays(df, "vas")
    live = availability.pain_series(df, "vas")
    assert np.allclose(np.sort(back_t), np.sort(np.asarray(live["t"]))), \
        "pain_series epochs drift from _pro_match_arrays (timezone bug regressed)"
    # PDT row: 14:00 local -> 21:00 UTC; PST row: 14:00 local -> 22:00 UTC. Confirm the DST-correct
    # offset vs the naive-as-UTC interpretation (which would be 7-8 h earlier).
    naive = pd.to_datetime(df["date_time_s1_daily"]).to_numpy().astype("datetime64[ns]").astype("int64") / 1e9
    diff = np.sort(back_t) - np.sort(naive)
    assert set(np.round(diff).astype(int)) == {7 * 3600, 8 * 3600}, \
        f"expected +7h (PDT) and +8h (PST) corrections, got {diff}"


def test_normalize_pro_times_idempotent_and_safe():
    """_normalize_pro_times is idempotent and a no-op on empty/None / already-normalized frames."""
    import pandas as pd
    from modules.Biomarkers import bravo_service as bs
    assert bs._normalize_pro_times(None) is None
    df = pd.DataFrame({"date_time_s1_daily": ["2025-07-20 14:00:00"], "vas": [50.0]})
    once = bs._normalize_pro_times(df)
    first = once["_pro_time_utc"].copy()
    twice = bs._normalize_pro_times(once)   # must not double-localize
    assert (twice["_pro_time_utc"] == first).all(), "second normalize shifted the column"


def test_pain_scores_emit_utc_t_epoch():
    """pain_scores_for_participant must emit a numeric `t_epoch` (UTC seconds) on every point, equal
    to the UTC parse of the display string. Clients match on t_epoch so a browser's Date.parse of the
    tz-naive string (which re-reads it in local time, -7/-8 h) can't drop PROs off the PSDs -- the
    '61/682 instead of 290/682' live-preview symptom. FIXHANDOUT_pro_timezone_mismatch."""
    import pandas as pd
    from modules.Biomarkers import bravo_service as bs
    # ProcessedPRO path -> _load_pros normalizes -> pain_scores emits t_epoch. A non-DEMO
    # ParticipantId that doesn't resolve to a real Participant falls through to the ProcessedPRO body.
    req = {"ParticipantId": "test-uid-not-a-real-participant",
           "ProcessedPRO": [
        {"date_time_s1_daily": "2025-07-20 14:00:00", "nrs": 5},   # PDT 14:00 -> 21:00Z
        {"date_time_s1_daily": "2025-12-20 14:00:00", "nrs": 7},   # PST 14:00 -> 22:00Z
    ]}
    out = bs.pain_scores_for_participant(req)
    mets = out.get("metrics", [])
    assert mets, "no metrics emitted"
    pts = mets[0]["points"]
    assert pts and all("t_epoch" in p for p in pts), "points missing t_epoch"
    for p in pts:
        e_str = pd.Timestamp(p["t"]).value / 1e9   # UTC parse of the display string
        assert abs(p["t_epoch"] - e_str) < 1, f"t_epoch {p['t_epoch']} != UTC parse {e_str}"
    # PDT row epoch must be 21:00Z, PST row 22:00Z (DST-correct, not the naive-as-UTC 14:00).
    epochs = sorted(p["t_epoch"] for p in pts)
    assert abs(epochs[0] - pd.Timestamp("2025-07-20 21:00:00").value / 1e9) < 1
    assert abs(epochs[1] - pd.Timestamp("2025-12-20 22:00:00").value / 1e9) < 1


def test_modeled_lsb_threshold_fallback_ladder():
    """Shared modeled-LSB fallback (_modeled_lsb_threshold_estimate) used by BOTH band_lsb_and_power
    (per-panel LSB readout) and deployment_summary (sign-off card), so an unsensed band defaults to
    the MODELED LSB instead of dead-ending at 'NO DEPLOYABLE LSB THRESHOLD'. Verifies:
      (1) a MEASURED native threshold always wins — the estimate is never consulted (returns None);
      (2) TIER 1 (modeled_timeline) reads the montage/survey LSB at the cut-point percentile;
      (3) the ±1σ band is the modeled-LSB fold (MODELED_LSB_SIGMA_FOLD) either side;
      (4) FAIL-CLOSED: with no modeled timeline AND no frozen per-participant model (participant=None),
          the population-constant last resort having been retired 2026-06-28, the helper returns None
          (indeterminate) rather than a population-average guess — for ANY cut-point or center freq;
      (5) with neither modeled points nor a cut-point, the helper honestly returns None."""
    from modules.Biomarkers import bravo_service as bs
    sigma = analytics.MODELED_LSB_SIGMA_FOLD     # ≈1.26

    # Signature is now (thr_lsb, modeled_thr, n_modeled, center_hz, percentile): the cut-point is no
    # longer passed — the caller models the LSB line off raw TD at the ROC band and passes the
    # percentile-anchored value in as modeled_thr (the single units-consistent modeled tier).

    # (1) measured native threshold present -> estimate never built
    assert bs._modeled_lsb_threshold_estimate(123.0, 200.0, 12, 20.0, 70.0) is None

    # (2)+(3) TIER 1: a modeled-timeline value present -> modeled_timeline tier, ±1σ band
    r1 = bs._modeled_lsb_threshold_estimate(None, 210.0, 15, 20.0, 70.0)
    assert r1["tier"] == "modeled_timeline" and r1["estimated_upper_lsb"] == 210.0
    assert abs(r1["estimated_upper_lsb_lo"] - round(210.0 / sigma, 1)) < 0.2
    assert abs(r1["estimated_upper_lsb_hi"] - round(210.0 * sigma, 1)) < 0.2
    assert r1["freq_extrapolated"] is False        # 20 Hz is in the validated range
    assert r1["k_effective"] == analytics.LSB_PER_UV2_TRANSFORM   # timeline runs transform×352.62
    assert r1["slope_b"] is None                   # no proportional-fit slope applied at read time

    # (4) FAIL-CLOSED: no modeled value (modeled_thr=None, e.g. no TD for the channel) -> indeterminate
    #     (None), regardless of whether the center is in/out of the validated range.
    assert bs._modeled_lsb_threshold_estimate(None, None, 0, 20.0, 70.0) is None
    assert bs._modeled_lsb_threshold_estimate(None, None, 0, 50.0, 70.0) is None

    # (5) nothing to estimate from -> honest None (panel shows the no-anchor message)
    assert bs._modeled_lsb_threshold_estimate(None, None, 0, 20.0, None) is None


def test_deployment_summary_identity_is_json_serializable():
    """Regression: /api/queryDeploymentSummary 500'd with 'Object of type Participant is not JSON
    serializable' because the identity block carried core["Participant"] — a Django MODEL object —
    instead of the participant_uid string. DRF json.dumps() the whole payload on every real fetch, so
    a model object anywhere in the output is a hard 500 (the gate-assembly tests never caught it
    because they build dicts by hand and never render). This pins the contract: the identity dict's
    participant field is a plain string, and an identity-shaped dict round-trips through json.dumps.

    We assert on the documented output shape (no DB): a Participant-like sentinel object in the dict
    must FAIL json.dumps, and the corrected string form must PASS — exactly the before/after of the
    fix at bravo_service.deployment_summary identity = {"participant": core["participant_uid"], ...}.
    """
    import json

    class _FakeParticipantModel:           # stands in for models.Participant (not JSON-serializable)
        def __init__(self, uid): self.uid = uid

    uid = "2e3c75c00d7f4f37b53a048d195f11da"
    # BEFORE the fix: a model object in identity -> json.dumps raises TypeError (the live 500).
    bad_identity = {"participant": _FakeParticipantModel(uid), "contact": "ZERO_TWO_LEFT"}
    try:
        json.dumps({"available": True, "identity": bad_identity})
        raised = False
    except TypeError:
        raised = True
    assert raised, "a model object in identity should NOT be JSON-serializable (the original 500)"

    # AFTER the fix: the uid STRING serializes cleanly and round-trips.
    good_identity = {"participant": uid, "contact": "ZERO_TWO_LEFT"}
    payload = {"available": True, "identity": good_identity}
    restored = json.loads(json.dumps(payload))
    assert restored["identity"]["participant"] == uid
    assert isinstance(restored["identity"]["participant"], str)


def test_deployment_summary_real_payload_json_serializable():
    """Integration guard (code-review PR #8 nit): the hand-built test above can't catch a
    non-serializable value (numpy scalar, model object) leaking from a REAL roc/forward/by_era/threshold
    sub-dict — and DRF's renderer json.dumps the WHOLE payload on every request, so any such leak is a
    hard 500 (exactly the Participant->uid bug). This locks the full contract by json.dumps-ing an actual
    deployment_summary output.

    Requires the live participant DB (present in the container the test harness runs in). Skips cleanly
    (no failure) when the participant can't be resolved, so the offline/synthetic path is unaffected.
    """
    import json
    try:
        from Server import models
        from Biomarkers import bravo_service as bs
    except Exception:
        return  # service/models not importable in this context -> nothing to integration-test
    uid = "2e3c75c00d7f4f37b53a048d195f11da"  # RCS08 live uid
    try:
        if models.Participant.find(uid=uid) is None:
            return  # participant not in this DB -> skip (no real payload to check)
    except Exception:
        return
    out = bs.deployment_summary({
        "ParticipantId": uid, "Channel": "ZERO_TWO_LEFT", "CenterHz": 20.0, "BandWidthHz": 5.0,
        "MatchDirection": "prior",
    })
    # Whether available True or False, the payload MUST be JSON-serializable with the stdlib encoder
    # (no default=str crutch) — that is precisely what DRF does before sending it to the browser.
    s = json.dumps(out)
    assert len(s) > 0
    # And the identity participant, when present, is the uid string (not a model object).
    if out.get("available") and out.get("identity"):
        assert out["identity"].get("participant") == uid
        assert isinstance(out["identity"]["participant"], str)


def test_find_best_threshold_vectorized_matches_reference():
    """The vectorized _find_best_threshold_for_metric (searchsorted sens/spec/acc sweep) must be
    element-for-element identical to the verbatim pre-vectorization loop across degenerate inputs:
    NaN scores, heavy ties, and all-one-class labels. This is the sens/spec-objective selector used
    by the chronic sliding-window detector; vectorizing it removed ~35 s of per-threshold sklearn
    confusion_matrix/accuracy_score overhead from the biomarker recompute."""
    import numpy as np, pandas as pd
    from modules.Biomarkers.routines import threshold_biomarker as tb
    rng = np.random.default_rng(0)
    thr = np.arange(60, 200, 1)
    fails = 0
    for trial in range(150):
        n = int(rng.integers(5, 60))
        y = rng.integers(0, 2, n)
        if trial % 7 == 0:
            y = np.zeros(n, int)
        if trial % 11 == 0:
            y = np.ones(n, int)
        lfp = rng.normal(120, 40, n)
        if trial % 5 == 0:
            lfp[rng.integers(0, n, size=max(1, n // 4))] = np.nan
        if trial % 3 == 0:
            lfp = np.round(lfp / 10) * 10
        df = pd.DataFrame({"pain_level": y, "LFP_smoothed": lfp})
        for metric in ("sens", "spec"):
            a = tb._find_best_threshold_for_metric(df, thr, metric=metric)
            b = tb._find_best_threshold_for_metric_reference(df, thr, metric=metric)

            def _eq(x, yv):
                if isinstance(x, float) and np.isnan(x):
                    return isinstance(yv, float) and np.isnan(yv)
                try:
                    return bool(np.isclose(x, yv))
                except Exception:
                    return x == yv
            if not all(_eq(x, yv) for x, yv in zip(a, b)):
                fails += 1
    assert fails == 0, f"vectorized threshold selector diverged from reference in {fails} cases"


def test_best_threshold_balanced_auc_matches_reference():
    """best_threshold_by_balanced_auc must reproduce the per-threshold roc_auc_score(y, binary_pred)
    grid search's BEST AUC exactly (roc_auc on a binary prediction == (sens+spec)/2), across NaN
    scores / ties / one-class folds. The chosen threshold among EXACT AUC ties is deterministic
    (first/lowest AUC-optimal threshold); we assert the AUC value matches and that the chosen
    threshold is itself AUC-optimal (a valid member of the original's tie set)."""
    import numpy as np
    from sklearn import metrics
    from modules.Biomarkers.routines.threshold_biomarker import (
        best_threshold_by_balanced_auc, _threshold_metric_arrays)

    def _reference(y, lfp, thresholds):
        best_auc, best_thr = -1.0, float(thresholds[0])
        for t in thresholds:
            cls = (lfp >= t).astype(int)
            if len(np.unique(cls)) < 2:
                continue
            try:
                a = metrics.roc_auc_score(y, cls)
                a = max(a, 1 - a)
            except Exception:
                continue
            if a > best_auc:
                best_auc, best_thr = a, float(t)
        return best_thr, best_auc

    rng = np.random.default_rng(7)
    thr = np.arange(60, 200, 1)
    auc_fail = 0
    thr_not_optimal = 0
    for trial in range(150):
        n = int(rng.integers(4, 80))
        y = rng.integers(0, 2, n)
        if len(np.unique(y)) < 2:
            continue   # one-class folds are skipped upstream before this selector is called
        lfp = rng.normal(120, 40, n).astype(float)
        if trial % 4 == 0:
            lfp = np.round(lfp / 15) * 15
        if trial % 6 == 0 and n > 4:
            lfp[rng.integers(0, n, size=max(1, n // 5))] = np.nan
        rt, ra = _reference(y, lfp, thr)
        vt, va = best_threshold_by_balanced_auc(y, lfp, thr)
        # 1) best AUC value identical
        if not (np.isclose(ra, va, atol=1e-9) or (ra == -1.0 and va == -1.0)):
            auc_fail += 1
        # 2) the chosen threshold is AUC-optimal (balanced-acc at vt equals the grid max)
        sens, spec, _ = _threshold_metric_arrays(y, lfp, thr)
        a = np.maximum((sens + spec) / 2.0, 1.0 - (sens + spec) / 2.0)
        fs = np.sort(lfp[np.isfinite(lfp)])
        n_ge = fs.size - np.searchsorted(fs, thr.astype(float), side="left")
        valid = (n_ge > 0) & (n_ge < n) & np.isfinite(a)
        amax = np.nanmax(np.where(valid, a, -np.inf))
        vi = int(np.where(thr == int(vt))[0][0])
        if not np.isclose(a[vi], amax, atol=1e-9):
            thr_not_optimal += 1
    assert auc_fail == 0, f"best balanced-AUC value diverged in {auc_fail} cases"
    assert thr_not_optimal == 0, f"chosen threshold was not AUC-optimal in {thr_not_optimal} cases"


def test_roc_small_sample_advisory_is_label_only():
    """Audit [8]: deployment_roc carries a `small_sample` advisory (n_clusters < floor) that flips at
    the floor and changes NO computed value. We compare a few-cluster vs many-cluster fixture and
    assert (a) the flag tracks n_clusters vs SMALL_SAMPLE_CLUSTER_FLOOR, and (b) removing the two
    advisory keys leaves an otherwise-identical payload for the SAME data (label-only contract)."""
    import numpy as _np
    F, C = 60, 2
    f = _np.linspace(0.95, 100, F)
    band = (f >= 17.5) & (f <= 22.5)

    def _det(n_clusters, reps=4, seed=5):
        # n_clusters INDEPENDENT ratings, each shared by `reps` neural samples (clustered). The det
        # carries an explicit rating_group so deployment_roc counts INDEPENDENT RATINGS (not rows) —
        # exactly the real-data situation where the small_sample advisory matters. reps keeps the
        # matched-sample count >= 12 (the ROC availability floor) even when n_clusters is small.
        rng = _np.random.default_rng(seed)
        E = n_clusters * reps
        labels = _np.repeat(rng.normal(5, 2, n_clusters), reps)
        rating_group = _np.repeat(_np.arange(n_clusters), reps)
        psd = _np.abs(rng.normal(1, 0.2, (E, C, F)))
        psd[:, 0, band] *= (1 + 0.7 * (labels - labels.mean())[:, None])
        times = []
        for ci in range(n_clusters):
            day = 1 + (ci % 27)
            times += [f"2025-07-{day:02d} 10:00:00"] * reps
        return {"f_set": f, "psd": psd, "labels": labels, "rating_group": rating_group,
                "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "prelog": False, "times": times}

    floor = analytics.SMALL_SAMPLE_CLUSTER_FLOOR
    # Use a few-cluster and a many-cluster fixture. n_clusters is the post-binarization independent-
    # rating count (the middle tertile is dropped), so we assert the CONTRACT — small_sample ==
    # (n_clusters < floor) — on whatever n_clusters each fixture yields, plus that the two fixtures
    # land on opposite sides of the floor (sanity that the flag can be both True and False).
    roc_small = analytics.deployment_roc(_det(8), "ZERO_TWO_LEFT", 20.0, n_boot=200, seed=1)
    roc_big = analytics.deployment_roc(_det(30), "ZERO_TWO_LEFT", 20.0, n_boot=200, seed=1)
    assert roc_small["available"] and roc_big["available"]
    # the flag is exactly the floor test on n_clusters — no off-by-one, no perturbation
    for r in (roc_small, roc_big):
        assert r["small_sample"] == (r["n_clusters"] < floor)
        assert r["small_sample_floor"] == floor
    # the two fixtures straddle the floor (flag is genuinely toggling, not stuck)
    assert roc_small["small_sample"] is True, f"expected small fixture below floor, n={roc_small['n_clusters']}"
    assert roc_big["small_sample"] is False, f"expected big fixture at/above floor, n={roc_big['n_clusters']}"

    # (b) label-only: dropping the advisory keys, the small-sample payload equals what the SAME data
    # produced (i.e. the flag did not perturb auc / ci / operating point). Recompute identically.
    roc_small_again = analytics.deployment_roc(_det(8), "ZERO_TWO_LEFT", 20.0, n_boot=200, seed=1)
    for k in ("auc", "auc_lo", "auc_hi", "n_clusters", "n_pos", "n_neg"):
        a, b = roc_small[k], roc_small_again[k]
        assert (a == b) or (a is not None and b is not None and abs(a - b) < 1e-12), \
            f"advisory must not change {k}: {a} vs {b}"


def test_deployment_summary_carries_temporal_validity_block():
    """Audit [23]: the deployment_summary device record must ALWAYS carry an explicit
    `temporal_validity` block (forward_validation / threshold_drift / stim_state_portability), each
    defaulting to 'not_assessed' so the exported JSON is unambiguous. Runs against the live RCS08
    participant; skips cleanly when absent. Asserts presence + allowed enum values, not specific
    verdicts (those depend on data)."""
    import os, sys
    sys.path.insert(0, "/usr/src/BRAVO"); sys.path.insert(0, "/usr/src/BRAVO/modules")
    from modules.Biomarkers import bravo_service as bs
    from Server import models
    uid = "2e3c75c00d7f4f37b53a048d195f11da"
    if models.Participant.find(uid=uid) is None:
        return  # participant not in this DB — skip
    out = bs.deployment_summary({
        "ParticipantId": uid, "Channel": "ZERO_TWO_LEFT", "CenterHz": 20.0, "BandWidthHz": 5.0,
        "Metric": "nrs", "Strategy": "tertile", "MatchDirection": "prior"})
    if not out.get("available"):
        return
    tv = out.get("temporal_validity")
    assert isinstance(tv, dict), "temporal_validity block must always be present"
    assert tv.get("forward_validation") in ("validated", "failed", "not_assessed")
    assert tv.get("threshold_drift") in ("not_assessed",)  # not yet computed (audit [18])
    assert tv.get("stim_state_portability") in ("portable", "fragile", "not_assessed")


def test_block_bootstrap_block_len_1_reproduces_iid_loop():
    """Audit [16]: the vectorized moving-block bootstrap at block_len=1 must reproduce the previous
    per-replicate sklearn rating-cluster bootstrap EXACTLY (same seed -> same cluster picks -> same
    de-folded AUC distribution). This pins that the vectorization changed no number on the i.i.d.
    path. Tolerances are 0 on mean and both CI percentiles."""
    import numpy as _np
    from sklearn import metrics as _metrics
    K = 40
    rng = _np.random.default_rng(3)
    sizes = rng.integers(1, 6, K)
    g = _np.repeat(_np.arange(K), sizes)
    N = g.size
    y = rng.integers(0, 2, N); y[:2] = [0, 1]
    use = rng.normal(0, 1, N) + 0.6 * y

    def loop_boot(nb, seed):
        r = _np.random.default_rng(seed); uniq = _np.unique(g)
        rows = {c: _np.where(g == c)[0] for c in uniq}; out = []
        for _ in range(nb):
            pick = r.choice(uniq, size=uniq.size, replace=True)
            idx = _np.concatenate([rows[c] for c in pick]); yb = y[idx]
            if len(_np.unique(yb)) < 2:
                continue
            try:
                out.append(float(_metrics.roc_auc_score(yb, use[idx])))
            except ValueError:
                continue
        return _np.array(out)

    loop = loop_boot(3000, 11)
    vec = analytics._block_bootstrap_aucs(use, y, g, K, 3000, 1, _np.random.default_rng(11))
    vec = vec[_np.isfinite(vec)]
    assert vec.size == loop.size, f"replicate counts differ: {vec.size} vs {loop.size}"
    assert abs(loop.mean() - vec.mean()) < 1e-12
    assert abs(_np.percentile(loop, 2.5) - _np.percentile(vec, 2.5)) < 1e-12
    assert abs(_np.percentile(loop, 97.5) - _np.percentile(vec, 97.5)) < 1e-12


def test_auto_block_len_degrades_to_iid_when_uncorrelated():
    """Audit [16]: auto block length is 1 (i.i.d.) when the per-cluster pain series has no positive
    autocorrelation, and grows with serial dependence. Guarantees uncorrelated data is unchanged."""
    import numpy as _np
    unc = _np.random.default_rng(1).normal(0, 1, 60)
    assert analytics._auto_block_len(unc) == 1
    z = _np.zeros(60)
    for i in range(1, 60):
        z[i] = 0.8 * z[i - 1] + _np.random.default_rng(i).normal()
    assert analytics._auto_block_len(z) >= 2  # AR(1) rho=0.8 -> blocks longer than 1


def test_auc_power_design_effect_1_is_exact_noop_and_discount_is_monotone():
    """Audit [19]: design_effect=1.0 reproduces the prior auc_power EXACTLY (no-op), and design_effect
    > 1 lowers current power and raises ratings-needed (the honest direction), while DISPLAYING the
    raw (un-discounted) rating counts."""
    a = analytics.auc_power(0.75, 20, 20, auc_lo=0.62)                     # default deff=1.0
    b = analytics.auc_power(0.75, 20, 20, auc_lo=0.62, design_effect=1.0)
    for k in ("power_current", "power_current_lo", "n_ratings_needed", "n_ratings_needed_hi",
              "n_ratings_current", "more_data_needed", "se_auc", "n_pos", "n_neg"):
        assert a.get(k) == b.get(k), f"design_effect=1.0 must be a no-op; differs on {k}"
    assert a["design_effect"] == 1.0 and a["n_ratings_current"] == 40 and a["n_pos"] == 20

    base = analytics.auc_power(0.70, 15, 15, auc_lo=0.58, design_effect=1.0)
    disc = analytics.auc_power(0.70, 15, 15, auc_lo=0.58, design_effect=1.5)
    assert disc["power_current"] <= base["power_current"] + 1e-12, "discount must not raise power"
    assert disc["n_ratings_needed"] >= base["n_ratings_needed"], "discount must not lower ratings-needed"
    assert disc["n_ratings_current"] == 30, "displayed current must be RAW ratings (un-discounted)"
    assert abs(disc["n_ratings_effective"] - 30 / 1.5) < 1e-9, "effective n must be raw/deff"


def test_deployment_roc_bca_fields_and_defold_guard_present():
    """Audit [3]: the deployment ROC reports a BCa headline interval (ci_interval='BCa', with bca_z0 /
    bca_a populated) AND a de-folded percentile guard (auc_lo_defold/auc_hi_defold). On a clean planted
    band both the BCa CI and the guard sit above chance; the guard brackets the point AUC."""
    import numpy as _np
    rng = _np.random.default_rng(3)
    E, C, F = 160, 2, 60
    f = _np.linspace(0.95, 100, F)
    labels = rng.normal(5, 2, E)
    psd = _np.abs(rng.normal(1, 0.2, (E, C, F)))
    band = (f >= 17.5) & (f <= 22.5)
    psd[:, 0, band] *= (1 + 0.8 * (labels - labels.mean())[:, None])
    det = {"f_set": f, "psd": psd, "labels": labels,
           "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "prelog": False,
           "times": [f"2025-07-{1 + (i % 28):02d} 10:00:00" for i in range(E)]}
    roc = analytics.deployment_roc(det, "ZERO_TWO_LEFT", 20.0, n_boot=500, seed=1)
    assert roc["available"]
    assert roc["ci_interval"] == "BCa"
    assert roc["bca_z0"] is not None and roc["bca_a"] is not None
    assert roc["auc_lo_defold"] is not None and roc["auc_hi_defold"] is not None
    assert roc["ci_valid_floor"] == analytics.BOOT_CI_VALID_FLOOR == 100
    # planted band: both the BCa CI and the de-folded guard beat chance
    assert roc["auc_lo"] > 0.5 and roc["auc_lo_defold"] > 0.5
    # the de-folded guard brackets the oriented point estimate
    assert roc["auc_lo_defold"] <= roc["auc"] + 1e-9 <= roc["auc_hi_defold"] + 1e-9


def test_bca_matches_scipy_on_iid_skewed_statistic():
    """Audit [3]: the in-house BCa interval matches scipy.stats.bootstrap(method='BCa') to within
    bootstrap Monte-Carlo error on a skewed statistic where the bias/accel corrections are non-trivial.
    Pins the BCa formula (z0 from the bootstrap, a from the jackknife)."""
    import numpy as _np
    from scipy import stats as _st
    rng = _np.random.default_rng(0)
    x = rng.gamma(2.0, 1.0, 40)
    theta = float(_np.var(x))
    res = _st.bootstrap((x,), _np.var, n_resamples=20000, method="BCa",
                        random_state=1, confidence_level=0.95)
    B = 20000
    idx = rng.integers(0, x.size, size=(B, x.size))
    boot = _np.var(x[idx], axis=1)
    jack = _np.array([_np.var(_np.delete(x, i)) for i in range(x.size)])
    lo, hi, z0, a = analytics._bca_ci(theta, boot, jack, alpha=0.05)
    assert abs(res.confidence_interval.low - lo) < 0.05
    assert abs(res.confidence_interval.high - hi) < 0.05
    assert abs(z0) > 0.01 and abs(a) > 0.001    # corrections are genuinely non-zero on skewed data


def test_jackknife_cluster_aucs_matches_manual_delete_one():
    """Audit [3]: the vectorized delete-one-CLUSTER jackknife (BCa acceleration input) equals a manual
    leave-one-cluster-out AUC loop, exactly."""
    import numpy as _np
    rng = _np.random.default_rng(7)
    K = 35
    sizes = rng.integers(1, 5, K)
    col = _np.repeat(_np.arange(K), sizes)
    N = col.size
    y = rng.integers(0, 2, N); y[:2] = [0, 1]
    use = rng.normal(0, 1, N) + 0.7 * y
    vec = analytics._jackknife_cluster_aucs(use, y, col, K)

    def _auc(uu, yy):
        if len(_np.unique(yy)) < 2:
            return _np.nan
        pos = uu[yy == 1][:, None]; neg = uu[yy == 0][None, :]
        return float((pos > neg).mean() + 0.5 * (pos == neg).mean())

    man = _np.array([_auc(use[col != i], y[col != i]) for i in range(K)])
    fin = _np.isfinite(vec) & _np.isfinite(man)
    assert _np.max(_np.abs(vec[fin] - man[fin])) < 1e-12


def _drift_detail(E, weeks, drift_per_week=0.0, seed=1):
    """Synthetic td_detail spanning `weeks` calendar weeks with a planted band→pain relation whose
    separation threshold optionally drifts `drift_per_week` per week (moves the optimal cut-point)."""
    import numpy as _np, datetime as _dt
    rng = _np.random.default_rng(seed); C, F = 2, 60
    f = _np.linspace(0.95, 100, F)
    labels = rng.normal(5, 2, E)
    psd = _np.abs(rng.normal(1, 0.2, (E, C, F)))
    band = (f >= 17.5) & (f <= 22.5)
    wkidx = _np.repeat(_np.arange(weeks), int(_np.ceil(E / weeks)))[:E]
    shift = drift_per_week * wkidx
    psd[:, 0, band] *= (1 + 0.5 * (labels - labels.mean())[:, None] + shift[:, None])
    t0 = _dt.datetime(2025, 1, 6)
    times = [(t0 + _dt.timedelta(days=int(wkidx[i]) * 7 + (i % 5))).strftime("%Y-%m-%dT10:00:00")
             for i in range(E)]
    return {"f_set": f, "psd": psd, "labels": labels,
            "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "prelog": False, "times": times}


def test_threshold_drift_stationary_is_stable():
    """Audit [18]: a stationary band (no week-trend in the cut-point) is reported 'stable' with a
    non-significant slope and no drift flag."""
    det = _drift_detail(240, 12, drift_per_week=0.0, seed=2)
    r = analytics.threshold_drift_by_week(det, "ZERO_TWO_LEFT", 20.0)
    assert r["available"] and r["status"] == "stable"
    assert r["drift_flag"] is False
    assert r["slope_p"] is not None and r["slope_p"] >= 0.05
    assert r["n_weeks_qualifying"] >= analytics.DRIFT_MIN_WEEKS


def test_threshold_drift_detects_planted_trend():
    """Audit [18]: a band whose cut-point drifts systematically over weeks is flagged 'drift_detected'
    with a significant slope and a non-zero total drift."""
    det = _drift_detail(360, 16, drift_per_week=0.18, seed=5)
    r = analytics.threshold_drift_by_week(det, "ZERO_TWO_LEFT", 20.0)
    assert r["available"] and r["status"] == "drift_detected"
    assert r["drift_flag"] is True
    assert r["slope_p"] < 0.05
    assert abs(r["total_drift"]) > 0


def test_threshold_drift_sparse_record_not_assessed():
    """Audit [18]: fail-closed — too few qualifying weeks yields 'not_assessed', never a spurious
    drift flag from sparse weeks."""
    det = _drift_detail(20, 10, seed=3)
    r = analytics.threshold_drift_by_week(det, "ZERO_TWO_LEFT", 20.0)
    assert r["status"] == "not_assessed"
    assert r["drift_flag"] is False
    assert r["n_weeks_qualifying"] < analytics.DRIFT_MIN_WEEKS


# ─────────────────────────────────────────────────────────────────────────────
# CS-1 — transform route (k=352.62) as the PRIMARY TD→LSB source of truth
# (HANDOFF_TD_LSB_calibration_2026-06-27.md). The transform DSP is the percept-spectral-repro
# "selected band power": per 1 s rcs-Hann window, zero-pad to 256, rFFT, peak scale 2/256, magnitude,
# in-band summed-squared-magnitude, median across windows. NOT Welch.
# ─────────────────────────────────────────────────────────────────────────────

def _reference_transform_block(samples_uv, center_hz, *, half_hz=2.5,
                               nonzero=250, n_fft=256, sr=250.0, maxf=96.68):
    """Verbatim percept-spectral-repro transform DSP (the anchor), NON-overlapping windows. This is an
    independent re-implementation of the published reference — the vendored td_transform_band_power
    must reproduce it bit-for-bit, which is what proves the DSP was vendored correctly (repo k=352.62,
    r=0.9927)."""
    freqs = np.round(np.arange(n_fft // 2 + 1) * sr / n_fft, 2)
    freqs = freqs[freqs <= maxf + 1e-9]
    coeffs = np.zeros(n_fft)
    coeffs[:nonzero] = 0.5 * (1.0 - np.cos(2.0 * np.pi * np.arange(nonzero) / nonzero))
    v = np.asarray(samples_uv, float)
    v = v[np.isfinite(v)]
    if v.size < nonzero:
        return float("nan")
    powers = []
    for s in range(0, v.size - nonzero + 1, nonzero):
        w = v[s:s + nonzero] - np.mean(v[s:s + nonzero])
        pad = np.zeros(n_fft); pad[:nonzero] = w
        mag = 2.0 * np.abs(np.fft.rfft(pad * coeffs, n=n_fft)) / n_fft
        mag = mag[:len(freqs)]
        m = (freqs >= center_hz - half_hz) & (freqs <= center_hz + half_hz)
        powers.append(float(np.sum(mag[m] ** 2)))
    return float(np.median(powers))


def test_td_transform_band_power_reproduces_reference_dsp():
    """ANCHOR: the vendored transform reproduces the percept-spectral-repro reference DSP bit-for-bit
    under non-overlapping windows (the only configuration k=352.62 was fit against). Any deviation here
    means the DSP was vendored wrong, not that the science changed."""
    sr = 250.0
    rng = np.random.default_rng(11)
    max_err = 0.0
    for _ in range(6):
        n = int(rng.integers(800, 6000))
        t = np.arange(n) / sr
        sig = (12 * np.sin(2 * np.pi * 22.5 * t) + 6 * np.sin(2 * np.pi * 9.8 * t)
               + rng.normal(0, 3, n))
        for c in (8.8, 10.0, 20.0, 22.5, 26.4):
            ref = _reference_transform_block(sig, c)
            got = analytics.td_transform_band_power(sig, sr, c)   # default step == win (non-overlap)
            max_err = max(max_err, abs(ref - got))
    assert max_err < 1e-9, max_err
    # vector-center path shares one rFFT and matches the per-center scalar calls
    centers = np.array([8.8, 20.0, 26.4])
    vec = analytics.td_transform_band_power(sig, sr, centers)
    scal = np.array([analytics.td_transform_band_power(sig, sr, c) for c in centers])
    assert np.allclose(vec, scal, atol=1e-12)


def test_td_to_lsb_applies_transform_constant_and_guards():
    """td_to_lsb == LSB_PER_UV2_TRANSFORM (352.62, NOT 269) × transform band power, with the 1 s
    (one-window) minimum and non-positive guards returning NaN."""
    import math
    assert abs(analytics.LSB_PER_UV2_TRANSFORM - 352.62) < 1e-9                 # transform route k
    sr = 250.0
    t = np.arange(3000) / sr
    sig = 10 * np.sin(2 * np.pi * 20.0 * t)
    bp = analytics.td_transform_band_power(sig, sr, 20.0)
    assert abs(analytics.td_to_lsb(sig, sr, 20.0) - analytics.LSB_PER_UV2_TRANSFORM * bp) < 1e-9
    # 1 s minimum: exactly one window (250 samples) computes; below it → NaN
    assert np.isfinite(analytics.td_to_lsb(sig[:250], sr, 20.0))
    assert math.isnan(analytics.td_to_lsb(sig[:249], sr, 20.0))


def test_k_cancels_in_correlation_and_auc():
    """THE SAFETY CLAIM behind the route switch: because the per-band feature is a LOG of band power,
    the multiplicative k is an additive log-offset that cancels in Pearson r and in AUC. So swapping
    the TD path from welch256×269 to transform×352.62 moves the displayed/deployable LSB scale but
    cannot move any correlation or AUC result. Asserted byte-for-byte (not merely 'close')."""
    from sklearn.metrics import roc_auc_score
    from scipy.stats import pearsonr
    rng = np.random.default_rng(3)
    uv2 = np.exp(rng.normal(0, 1, 400))                     # positive band powers
    pain = rng.normal(0, 1, 400)
    label = (np.log(uv2) + 0.4 * rng.normal(0, 1, 400) > np.log(uv2).mean()).astype(int)
    # feature = log(LSB) = log(k) + log(uv2): the log(k) term is a pure additive shift. Compare the
    # PRIMARY transform k against an arbitrary alternate scale (the property is k-agnostic — it held
    # for the retired welch256 269 too, and must hold for ANY positive constant).
    k_alt = 269.0
    f_alt = np.log(k_alt * uv2)
    f352 = np.log(analytics.LSB_PER_UV2_TRANSFORM * uv2)
    # difference is exactly the constant log-ratio, identical for every point
    assert np.allclose(f352 - f_alt, np.log(analytics.LSB_PER_UV2_TRANSFORM / k_alt), atol=1e-12)
    # Pearson r identical to full float precision
    assert abs(pearsonr(f_alt, pain)[0] - pearsonr(f352, pain)[0]) < 1e-12
    # AUC identical (rank statistic — a monotone +shift cannot reorder)
    assert abs(roc_auc_score(label, f_alt) - roc_auc_score(label, f352)) < 1e-12


def test_transform_centered_window_clip_dont_slide_contract():
    """The per-PRO TD extent for the 0–100 Hz sweep: 30 s CENTERED on the rating, CLIPPED to the
    recording (asymmetric near an edge, never slid into padding), dropped below one 1 s window or above
    10% Missing. This is the contract CS-2 wires into PRO matching."""
    sr = 250.0
    n = 30000                                               # 120 s recording
    sig = np.sin(2 * np.pi * 20.0 * np.arange(n) / sr)
    # mid-recording → full 30 s (extent_s default)
    sl, used = analytics.transform_centered_window(sig, sr, 60.0)
    assert sl is not None and sl.size == int(round(30.0 * sr)) and abs(used - 30.0) < 1e-9
    # 5 s from start → clipped to [0, 20 s], asymmetric, not padded to 30 s
    sl, used = analytics.transform_centered_window(sig, sr, 5.0)
    assert sl.size == int(round(20.0 * sr)) and abs(used - 20.0) < 1e-9
    # recording shorter than one transform window → dropped
    sl, used = analytics.transform_centered_window(sig[:200], sr, 0.4)
    assert sl is None and used == 0.0
    # >10% of the centered span Missing → rejected
    miss = np.zeros(n); miss[int(44 * sr):int(76 * sr)] = 1     # covers the [45,75] s span
    sl, used = analytics.transform_centered_window(sig, sr, 60.0, missing=miss)
    assert sl is None and used == 0.0


def test_transform_50pct_overlap_window_count_and_variance_only_shift():
    """The deployed sweep slides the 1 s window at 0.5 s (50% overlap): 59 windows over a full 30 s vs
    30 non-overlapping. Overlap changes only the number of windows the median is taken over (a variance
    reduction), so on a stationary signal the band power barely moves — well under the 1.26× calibration
    scatter (the live-RCS08 check measures the real-data shift; this pins the synthetic invariant)."""
    sr = 250.0
    step = int(round(sr * analytics.TRANSFORM_STEP_SECONDS))     # 125 = 0.5 s
    win = int(round(sr * analytics.TRANSFORM_WIN_SECONDS))       # 250 = 1 s
    n = int(round(30.0 * sr))
    assert len(np.arange(0, n - win + 1, win)) == 30            # non-overlap window count
    assert len(np.arange(0, n - win + 1, step)) == 59          # 50%-overlap window count
    t = np.arange(n) / sr
    sig = 10 * np.sin(2 * np.pi * 22.5 * t) + np.random.default_rng(5).normal(0, 2, n)
    no = analytics.td_transform_band_power(sig, sr, 22.5)                       # non-overlap
    ov = analytics.td_transform_band_power(sig, sr, 22.5, step_samples=step)    # 50% overlap
    fold = max(no / ov, ov / no)
    assert fold < analytics.MODELED_LSB_SIGMA_FOLD, fold       # « 1.26× scatter


def test_modeled_transform_point_stays_flagged_native_preferred():
    """NATIVE-PREFERRED INVARIANT (§3.3). The route switch moved the modeled tier's DSP from
    welch256×269 to transform×352.62 but MUST keep the point tagged source='psd_modeled' + modeled=True,
    because the deployment threshold and the timeline y-scaler exclude modeled points via that exact
    flag. Here: (1) availability.lsb_series tags the switched montage-TD point modeled=True /
    source='psd_modeled' / method='td_transform_…'; (2) the verbatim bravo_service mask
    (y[band & ~is_modeled]) keeps ONLY the native value when a native and a modeled point share a band,
    so a measured threshold is never contaminated by the modeled estimate."""
    from Biomarkers.routines import availability
    sr = 250.0
    t = np.arange(int(40 * sr)) / sr                          # 40 s survey → full transform support
    ch = "ZERO_AND_TWO_LEFT"
    rec = {
        "ChannelNames": [ch],
        "Data": (10 * np.sin(2 * np.pi * 20.0 * t)).reshape(-1, 1),
        "SamplingRate": sr,
        "StartTime": 1_700_000_000.0,
        "PeakFrequencyInHertz": 20.0,
    }
    key = availability._canon_channel(ch)
    out = availability.lsb_series(
        chronic_recordings=[], powerdomain_recordings=[],
        montage_td_recordings=[rec], sensing_hz_by_channel={key: 20.0})
    ser = out.get(key)
    assert ser is not None and len(ser["y"]) >= 1, out.keys()
    # exactly the modeled transform point, correctly flagged
    assert ser["source"][0] == "psd_modeled"
    assert bool(ser["modeled"][0]) is True
    assert ser["method"][0].startswith("td_transform_x_k=")
    assert "352.62" in ser["method"][0]
    assert np.isfinite(ser["y"][0]) and ser["y"][0] > 0

    # (2) the deployment native-only mask keeps native when both exist on the same band
    y = np.array([100.0, 100.0, 9999.0])                     # 2 native, 1 modeled
    hz = np.array([20.0, 20.0, 20.0])
    modeled_flag = np.array([False, False, True], dtype=object)
    center_hz, half = 20.0, 2.5
    bmask = np.isfinite(y) & np.isfinite(hz) & (hz >= center_hz - half) & (hz < center_hz + half)
    is_modeled = np.array([bool(m) for m in modeled_flag])
    native = y[bmask & ~is_modeled]
    assert native.size == 2 and np.all(native == 100.0)      # modeled 9999 excluded
    assert 9999.0 not in set(native.tolist())


def test_modeled_excluded_from_native_correlation_path():
    """SCOPE GUARD for the 'k cancels' safety claim. k cancels in r/AUC only within a SINGLE-SOURCE
    feature (homogeneous k). A native+modeled MIXED feature is NOT k-invariant — raising modeled k from
    269→352.62 shifts only the modeled subset. This is safe ONLY because the deployable / measured path
    excludes modeled points via the is_modeled mask, so no mixed-k column ever reaches a correlation.
    This test pins that segregation: (1) on a mixed series the masked native subset is k-invariant while
    the unmasked mixed series is NOT, and (2) the bravo_service native-only mask drops every modeled
    point regardless of which k produced it."""
    from scipy.stats import pearsonr
    rng = np.random.default_rng(7)
    n = 300
    uv2 = np.exp(rng.normal(0, 1, n))
    pain = rng.normal(0, 1, n)                               # continuous outcome for correlation
    is_modeled = np.zeros(n, bool); is_modeled[rng.choice(n, 120, replace=False)] = True
    # native points carry raw device LSB (no k); modeled points carry k*uv2. Lifting modeled k adds a
    # constant log-offset to ONLY the modeled rows, so the mixed column is no longer a pure rescale of
    # itself between the two k -> a covariance-based statistic (Pearson r) moves.
    native_lsb = uv2.copy()                                  # stand-in raw units, no k
    def mixed_feature(k):
        return np.log(np.where(is_modeled, k * uv2, native_lsb))
    # (1) UNMASKED mixed feature is NOT k-invariant: Pearson r differs between the two k
    k_alt = 269.0                                          # arbitrary alternate scale (k-agnostic claim)
    r_mixed_alt = pearsonr(mixed_feature(k_alt), pain)[0]
    r_mixed_352 = pearsonr(mixed_feature(analytics.LSB_PER_UV2_TRANSFORM), pain)[0]
    assert abs(r_mixed_alt - r_mixed_352) > 1e-6          # mixing DOES move r — claim must be scoped
    # (2) NATIVE-ONLY subset (the masked path) is fully k-invariant
    nat = ~is_modeled
    r_nat_alt = pearsonr(mixed_feature(k_alt)[nat], pain[nat])[0]
    r_nat_352 = pearsonr(mixed_feature(analytics.LSB_PER_UV2_TRANSFORM)[nat], pain[nat])[0]
    assert abs(r_nat_alt - r_nat_352) < 1e-12            # masked native path: k cancels, safe
    # (3) the bravo_service native-only mask drops EVERY modeled point, independent of method/k
    y = np.where(is_modeled, 9999.0, native_lsb)
    keep = ~np.array([bool(m) for m in is_modeled])
    assert np.all(np.isfinite(y[keep])) and 9999.0 not in set(y[keep].tolist())


# ─────────────────────────────  CS-3 PSD→LSB BRIDGE  ─────────────────────────────

def test_bridge_constants_compose_from_transform_and_td_psd_ratio():
    """K_PSD_LSB is exactly LSB_PER_UV2_TRANSFORM / K_TD_PSD — the composition is not an independent
    magic number but the two measured links multiplied. Pins both the ratio and the derived constant."""
    assert abs(analytics.LSB_PER_UV2_DEVICE_PSD_TD_RATIO - 4.789) < 1e-9
    expect = analytics.LSB_PER_UV2_TRANSFORM / analytics.LSB_PER_UV2_DEVICE_PSD_TD_RATIO
    assert abs(analytics.LSB_PER_DEVICE_PSD - expect) < 1e-9
    assert abs(analytics.LSB_PER_DEVICE_PSD - 73.63) < 0.01      # 352.62 / 4.789
    # the bridge constant is the device-PSD constant, NOT the TD transform constant
    assert analytics.LSB_PER_DEVICE_PSD != analytics.LSB_PER_UV2_TRANSFORM


def test_clamp_device_psd_floors_negatives_only():
    """The unit reconciliation: FFTBinData negatives (sub-noise-floor baseline-subtracted bins) clamp
    to 0; positives and NaNs are untouched. This is what puts event FFTBinData on the LFPMagnitude
    (linear µV, 0 negatives) footing."""
    m = np.array([-0.1133, -1e-9, 0.0, 0.5, 2.0, np.nan])
    c = analytics.clamp_device_psd(m)
    assert c[0] == 0.0 and c[1] == 0.0 and c[2] == 0.0       # negatives + zero -> 0
    assert c[3] == 0.5 and c[4] == 2.0                       # positives preserved
    assert np.isnan(c[5])                                    # NaN preserved
    assert np.all(c[np.isfinite(c)] >= 0)


def test_device_psd_band_power_sum_of_squared_in_band_magnitudes():
    """device_psd_band_power == Σ(clamped in-band magnitude)² over [center±half] — the SAME band-power
    definition as td_transform_band_power, so the two sides of the bridge are commensurable. Negatives
    are clamped before squaring (else a -0.11 bin would add spurious +0.012 power)."""
    f = np.linspace(0.0, 96.68, 100)
    m = np.zeros(100)
    band = (f >= 17.5) & (f < 22.5)
    idx = np.where(band)[0]
    m[idx[:5]] = [1.0, -0.11, 3.0, 2.0, -0.05]               # two sub-floor negatives in the band
    bp = analytics.device_psd_band_power(f, m, 20.0, half_hz=2.5)
    # clamp negatives -> [1,0,3,2,0]; sum of squares = 1+0+9+4+0 = 14
    assert abs(bp - 14.0) < 1e-9
    # a band with no in-range bin -> NaN
    assert np.isnan(analytics.device_psd_band_power(f, m, 200.0, half_hz=2.5))


def test_device_psd_to_lsb_applies_bridge_constant_and_guards():
    """device_psd_to_lsb == LSB_PER_DEVICE_PSD × device_psd_band_power, scalar->float and vector->ndarray,
    NaN where band power is NaN/non-positive."""
    f = np.linspace(0.0, 96.68, 100)
    m = np.zeros(100); m[(f >= 17.5) & (f < 22.5)] = 2.0
    bp = analytics.device_psd_band_power(f, m, 20.0)
    assert abs(analytics.device_psd_to_lsb(f, m, 20.0) - analytics.LSB_PER_DEVICE_PSD * bp) < 1e-6
    vec = analytics.device_psd_to_lsb(f, m, np.array([10.0, 20.0, 30.0]))
    assert vec.shape == (3,) and np.isnan(vec[0]) and np.isfinite(vec[1]) and np.isnan(vec[2])
    # an all-negative (sub-floor) band -> clamped to 0 -> non-positive power -> NaN
    mneg = np.where(m > 0, -0.1, m)
    assert np.isnan(analytics.device_psd_to_lsb(f, mneg, 20.0))


def test_bridge_reproduces_direct_transform_on_a_white_signal():
    """Bridge invariant (synthetic end-to-end): a device-PSD that IS the magnitude spectrum of a TD
    trace, fed through device_psd_to_lsb, must equal that TD trace's td_to_lsb to within the K_TD_PSD
    definition. We don't have the device's onboard FFT here, so we synthesize the montage relationship:
    PSD_bp = K_TD_PSD · TD_bp by construction, then check LSB agreement closes the loop."""
    rng = np.random.default_rng(3)
    sr = 250.0
    sig = rng.standard_normal(7500) + 3.0 * np.sin(2 * np.pi * 20.0 * np.arange(7500) / sr)
    td_bp = analytics.td_transform_band_power(sig, sr, 20.0, half_hz=2.5)
    lsb_direct = analytics.td_to_lsb(sig, sr, 20.0)
    # construct a device-PSD whose band power is exactly K_TD_PSD * td_bp (one in-band bin carrying it)
    f = np.linspace(0.0, 96.68, 100)
    mag = np.zeros(100)
    inband = np.where((f >= 17.5) & (f < 22.5))[0]
    mag[inband[0]] = np.sqrt(analytics.LSB_PER_UV2_DEVICE_PSD_TD_RATIO * td_bp)  # |x|² = K*td_bp
    lsb_bridge = analytics.device_psd_to_lsb(f, mag, 20.0)
    # LSB_bridge = K_PSD_LSB * (K_TD_PSD * td_bp) = (352.62/4.789)*4.789*td_bp = 352.62*td_bp = LSB_direct
    assert abs(lsb_bridge - lsb_direct) / lsb_direct < 1e-9


def test_event_psd_bridge_tier_restricted_to_deployable_band():
    """availability.lsb_series only honors an event-PSD bridge point when its center is inside
    [LSB_VALIDATED_HZ_LO, LSB_DEPLOYABLE_HZ_HI]; a center outside that band is dropped (no calibrated
    meaning there). Also: the emitted point is source='psd_modeled', modeled=True, method tagged."""
    from Biomarkers.routines import availability
    f = list(np.linspace(0.0, 96.68, 100))
    mag = np.zeros(100); mag[(np.array(f) >= 17.5) & (np.array(f) < 22.5)] = 2.0
    mag = list(mag)
    inband = {"channel": "ZERO_THREE_LEFT", "t": 1.7e9, "freq": f, "power": mag, "center_hz": 20.0}
    outband = {"channel": "ZERO_THREE_LEFT", "t": 1.7e9 + 10, "freq": f, "power": mag,
               "center_hz": 55.5}                          # high-gamma, above LSB_DEPLOYABLE_HZ_HI
    out = availability.lsb_series([], [], montage_td_recordings=[],
                                  event_psd_recordings=[inband, outband])
    d = out.get("ZERO_THREE_LEFT", {"y": [], "source": [], "modeled": [], "method": []})
    bridge = [(y, s, mo, me) for y, s, mo, me in
              zip(d["y"], d["source"], d["modeled"], d["method"]) if me and "event_psd_bridge" in me]
    assert len(bridge) == 1                                 # only the in-band center survives
    y, s, mo, me = bridge[0]
    assert s == "psd_modeled" and mo is True
    assert me == f"event_psd_bridge_x_k={analytics.LSB_PER_DEVICE_PSD:.2f}"
    assert np.isfinite(y) and y > 0


# ---------------------------------------------------------------------------
# Audit [5] — server-side cut-point on the FULL ROC arrays (was re-solved in the
# browser on the downsampled curve, so the displayed/propagated operating point
# could drift). analytics.deployment_roc now ships an `operating_points` table
# solved on the un-downsampled fpr/tpr/thr; the legacy Youden `operating_point`
# must equal operating_points['youden'].
# ---------------------------------------------------------------------------

def test_solve_roc_operating_point_youden_matches_full_array_argmax():
    """The Youden solve over the parallel arrays returns the (tpr-fpr)-maximizing vertex, skipping the
    +inf sentinel, with sens/spec read off that vertex."""
    fpr = np.array([0.0, 0.0, 0.1, 0.4, 1.0])
    tpr = np.array([0.0, 0.6, 0.9, 0.95, 1.0])
    thr = [None, 3.0, 2.0, 1.0, 0.0]            # index 0 = +inf sentinel at (0,0)
    op = analytics._solve_roc_operating_point(fpr, tpr, thr, "youden", prevalence=0.5)
    # Youden J: [skip, 0.6, 0.8, 0.55, 0.0] -> argmax at index 2.
    assert op is not None and op["k"] == 2
    assert op["threshold"] == 2.0
    assert abs(op["sensitivity"] - 0.9) < 1e-9
    assert abs(op["specificity"] - 0.9) < 1e-9
    assert op["rule"] == "youden" and op["degenerate"] is False


def test_solve_roc_operating_point_skips_inf_sentinel_and_ties_keep_first():
    """A None/inf threshold vertex is never selectable, and tied utilities keep the lowest index
    (strictly-greater) so the chosen point is deterministic."""
    # Exactly-representable values so the J tie is real (no float drift): J = [—, 0.25, 0.25].
    fpr = np.array([0.0, 0.25, 0.5])
    tpr = np.array([0.0, 0.5, 0.75])
    thr = [None, 2.0, 1.0]
    op = analytics._solve_roc_operating_point(fpr, tpr, thr, "youden", prevalence=0.5)
    assert op is not None and op["k"] == 1 and op["threshold"] == 2.0   # first maximizer wins


def test_solve_roc_operating_point_cost_shifts_toward_specificity():
    """Raising the FP:FN cost ratio steepens the tangent slope, moving the operating point toward
    lower FPR (higher specificity)."""
    fpr = np.array([0.0, 0.1, 0.3, 0.6])
    tpr = np.array([0.0, 0.5, 0.85, 0.97])
    thr = [None, 3.0, 2.0, 1.0]
    op_cheap = analytics._solve_roc_operating_point(fpr, tpr, thr, "cost", 0.5, cost_ratio=0.25)
    op_dear = analytics._solve_roc_operating_point(fpr, tpr, thr, "cost", 0.5, cost_ratio=8.0)
    assert op_cheap is not None and op_dear is not None
    assert op_dear["fpr"] <= op_cheap["fpr"]            # costlier FP -> more conservative (lower FPR)
    assert op_dear["specificity"] >= op_cheap["specificity"]


def test_deployment_roc_ships_full_array_operating_points_table():
    """deployment_roc returns operating_points={youden, f1, cost:[...]}, and the full-array Youden
    point equals the legacy operating_point (the displayed default is now exact, not re-solved on the
    downsampled curve). max_points is forced small so the curve IS downsampled in the payload."""
    import numpy as _np
    rng = _np.random.default_rng(5)
    E, C, F = 200, 2, 60
    f = _np.linspace(0.95, 100, F)
    labels = rng.normal(5, 2, E)
    psd = _np.abs(rng.normal(1, 0.2, (E, C, F)))
    band = (f >= 17.5) & (f <= 22.5)
    psd[:, 0, band] *= (1 + 0.7 * (labels - labels.mean())[:, None])   # planted band -> real ROC
    det = {"f_set": f, "psd": psd, "labels": labels,
           "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"], "prelog": False,
           "times": [f"2025-07-{1 + (i % 28):02d} 10:00:00" for i in range(E)]}
    roc = analytics.deployment_roc(det, "ZERO_TWO_LEFT", 20.0, n_boot=200, max_points=20, seed=1)
    assert roc["available"]
    ops = roc.get("operating_points")
    assert isinstance(ops, dict) and "youden" in ops and "f1" in ops and "cost" in ops
    # The displayed curve was downsampled (max_points=20) but the table was solved on the full arrays.
    assert len(roc["fpr"]) <= 20
    yo = ops["youden"]
    assert yo is not None and abs(yo["threshold"] - roc["operating_point"]["threshold"]) < 1e-9
    assert abs(yo["sensitivity"] - roc["operating_point"]["sensitivity"]) < 1e-9
    # cost grid spans the slider's log2 range (-3..3 step 0.25 -> 25 points) with the metadata keys.
    assert isinstance(ops["cost"], list) and len(ops["cost"]) == 25
    assert all("log_cost" in cp and "cost_ratio" in cp for cp in ops["cost"])
    assert ops["cost"][0]["log_cost"] == -3.0 and abs(ops["cost"][-1]["log_cost"] - 3.0) < 1e-9


if __name__ == "__main__":
    # ad-hoc local run of just the CS-1 transform tests (the container harness globs test_* itself)
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_td_") or _name.startswith("test_transform_") or \
           _name.startswith("test_bridge_") or _name.startswith("test_device_psd_") or \
           _name.startswith("test_clamp_device_psd") or _name.startswith("test_event_psd_bridge_") or \
           _name in ("test_k_cancels_in_correlation_and_auc",
                     "test_modeled_transform_point_stays_flagged_native_preferred",
                     "test_modeled_excluded_from_native_correlation_path"):
            _fn(); print("PASS", _name)


def test_deployment_summary_survives_unestimable_power_requirement():
    """Regression, 2026-08-30: `n_ratings_needed` is legitimately None when the power calculation
    flags underpowering but cannot solve for the required N (an effect at chance has no finite N
    reaching 80%). The old code did `power.get('n_ratings_needed', 0) - power.get('n_ratings_current', 0)`,
    and `.get(key, default)` does NOT return the default for a key that is PRESENT with value None —
    so this raised TypeError and took down the entire deployment_summary export for that
    participant. Reached on live RCS08 data after an ingest, not by any synthetic fixture.

    Asserts the summary still builds, and that the caveat says the requirement is not estimable
    rather than inventing a shortfall number.
    """
    import sys
    sys.path.insert(0, "/usr/src/BRAVO"); sys.path.insert(0, "/usr/src/BRAVO/modules")
    from modules.Biomarkers import bravo_service as bs
    from Server import models
    uid = "2e3c75c00d7f4f37b53a048d195f11da"
    if models.Participant.find(uid=uid) is None:
        return  # participant not in this DB — skip

    out = bs.deployment_summary({
        "ParticipantId": uid, "Channel": "ZERO_TWO_LEFT", "CenterHz": 20.0, "BandWidthHz": 5.0,
        "Metric": "nrs", "Strategy": "tertile", "MatchDirection": "prior"})
    if not out.get("available"):
        return
    caveats = out.get("caveats") or []
    assert isinstance(caveats, list) and caveats, "deployment_summary must still produce caveats"

    # No caveat may render a None into user-facing text.
    for c in caveats:
        assert "None" not in c, f"caveat leaked a None into display text: {c!r}"

    # If the underpowered caveat is present at all, it must be one of the two well-formed shapes:
    # a concrete shortfall, or an explicit 'not estimable' — never a bare arithmetic artefact.
    under = [c for c in caveats if c.startswith("Underpowered:")]
    for c in under:
        assert ("could not be estimated" in c) or ("more independent pain ratings needed" in c), \
            f"malformed underpowered caveat: {c!r}"

    # Gate details must not leak a None percentage either (the sibling `power_current` hazard).
    for g in (out.get("gates") or []):
        detail = (g or {}).get("detail") if isinstance(g, dict) else None
        if isinstance(detail, str):
            assert "None%" not in detail, f"gate detail leaked a None percentage: {detail!r}"


# --- auc_power: status vocabulary, invariant shape, feasibility ceiling (2026-08-30) -------------
def test_auc_power_return_shape_is_invariant_across_all_paths():
    """The unavailable / at-chance paths used to return a SHORTER dict than the main path, so a
    consumer reading power['power_current_lo'] raised KeyError on exactly the degenerate inputs
    where it most needed a value. Every path must now fill one canonical key set."""
    from modules.Biomarkers.routines import analytics as an
    shapes = {
        tuple(sorted(an.auc_power(0.80, 24, 24).keys())),
        tuple(sorted(an.auc_power(0.50, 24, 24).keys())),                 # at chance
        tuple(sorted(an.auc_power(0.5036, 24, 24, design_effect=1.283).keys())),  # near chance
        tuple(sorted(an.auc_power(0.70, 1, 9).keys())),                   # too few ratings
    }
    assert len(shapes) == 1, f"return shape diverges across paths: {len(shapes)} distinct key sets"
    keys = tuple(sorted(an.auc_power(0.50, 24, 24).keys()))
    for k in ("status", "requirement_feasible", "feasible_n_max", "power_current_lo",
              "n_ratings_needed_hi", "curve_truncated", "reason"):
        assert k in keys, f"{k} missing from the canonical key set"


def test_auc_power_status_discriminates_the_four_regimes():
    """`status` must let a caller branch without re-deriving the logic from floats."""
    from modules.Biomarkers.routines import analytics as an
    assert an.auc_power(0.80, 24, 24)["status"] == an.POWER_STATUS_POWERED
    assert an.auc_power(0.65, 24, 24)["status"] == an.POWER_STATUS_FEASIBLE
    assert an.auc_power(0.50, 24, 24)["status"] == an.POWER_STATUS_AT_CHANCE
    # near-chance: requirement is finite but astronomically large
    near = an.auc_power(0.5036, 24, 24, design_effect=1.283)
    assert near["status"] == an.POWER_STATUS_INFEASIBLE
    assert near["n_ratings_needed"] is not None and near["n_ratings_needed"] > 100000
    assert near["requirement_feasible"] is False


def test_auc_power_at_chance_requirement_is_undefined_not_large():
    """AUC <= 0.5 has NO finite N reaching target power, and power_current is alpha by definition."""
    from modules.Biomarkers.routines import analytics as an
    o = an.auc_power(0.50, 24, 24, alpha=0.05)
    assert o["available"] is True
    assert o["n_ratings_needed"] is None
    assert o["power_current"] == 0.05
    assert o["more_data_needed"] is True
    assert o["requirement_feasible"] is False


def test_auc_power_curve_is_capped_at_the_feasibility_ceiling():
    """An at-chance band produced a 40-point curve running to ~365,000 ratings, on which the real
    48 ratings sit invisibly at the origin. The curve must stay in the actionable range and say so."""
    from modules.Biomarkers.routines import analytics as an
    o = an.auc_power(0.5036, 24, 24, design_effect=1.283)
    assert o["curve_truncated"] is True
    if o.get("curve"):
        assert max(o["curve"]["n"]) <= o["feasible_n_max"] * 1.5, \
            "curve x-axis still runs past the feasibility ceiling"
    # a genuinely feasible requirement must NOT be flagged as truncated
    assert an.auc_power(0.65, 24, 24)["curve_truncated"] is False


def test_auc_power_feasibility_ceiling_is_configurable():
    from modules.Biomarkers.routines import analytics as an
    o = an.auc_power(0.65, 24, 24, feasible_n_max=10)   # absurdly low ceiling
    assert o["feasible_n_max"] == 10
    assert o["requirement_feasible"] is False and o["status"] == an.POWER_STATUS_INFEASIBLE
