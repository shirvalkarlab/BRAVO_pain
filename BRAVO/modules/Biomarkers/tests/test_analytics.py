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
    assert naive > 150.0, "control: a naive Otsu IS distorted by the spikes (proves MAD matters)"
    assert d["n_total"] == 4003


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


if __name__ == "__main__":
    test_roc_downsampled_for_plot()
    test_cluster_scatter_one_feature()
    test_cluster_scatter_two_features()
    test_cluster_scatter_missing_features()
    test_pain_binarization()
    test_lfp_distribution_robust_range()
    test_corr_spectrum_enforces_50hz_cap()
    test_lfp_distribution_otsu_on_mad_filtered_data()
    test_td_sliding_corr_grid_reaches_last_session_drops_corrupt_dates()
    test_power_center_freqs_standard_path()
    test_power_center_freqs_direct_hemisphere_key()
    test_power_center_freqs_nested_recordingconfig()
    test_power_center_freqs_missing_is_safe()
    print("All analytics tests passed.")
