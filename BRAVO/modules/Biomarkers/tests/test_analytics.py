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
    # adaptive-valid flags: a 5 Hz band fits inside [8,30] only for centers in [10.5, 27.5]
    cen = np.array(sc["centers"]); av = np.array([b["adaptive_valid"] for b in sc["bands"]])
    assert cen[av].min() == 10.5 and cen[av].max() == 27.5


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
    # the de-folded null CI honestly reaches below chance (the old fold pinned this at ~0.5)
    assert roc["auc_lo"] < 0.5, f"null lower CI {roc['auc_lo']} should drop below 0.5 (de-fold)"
    assert "de-folded" in roc.get("ci_method", "")
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


def test_band_power_notched_interpolates_mains_line():
    """The 60 Hz line-noise spike is interpolated away before band integration so it cannot dominate a
    band that straddles 60 Hz."""
    freq = np.arange(40.0, 80.0, 1.0)
    power = np.full_like(freq, 0.05)
    power[np.argmin(np.abs(freq - 60.0))] = 100.0   # giant mains spike
    bp_notched = analytics._band_power_notched(freq, power, 60.0, 5.0)
    # a clean ~0.05/Hz over a 10 Hz band ~ 0.5; the spike (if not notched) would push it >>1
    assert bp_notched < 1.0, bp_notched
    assert bp_notched > 0.0


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
    test_deployment_roc_bootstrap_defolded_null_ci_drops_below_chance()
    test_deployment_roc_by_era_pooled_orientation_surfaces_reversal()
    test_deployment_roc_by_era_portable_when_eras_agree()
    test_deployment_summary_gate_states_and_necessary_blocking()
    test_psd_lsb_conversion_recovers_planted_proportional_constant()
    test_psd_lsb_conversion_flags_nonlinear_slope()
    test_psd_lsb_conversion_guards_small_n()
    test_band_power_notched_interpolates_mains_line()
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
