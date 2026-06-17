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
    test_power_center_freqs_standard_path()
    test_power_center_freqs_nested_recordingconfig()
    test_power_center_freqs_missing_is_safe()
    print("All analytics tests passed.")
