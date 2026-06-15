"""
Adapter + routine fidelity tests for the streaming PSD biomarker.

Runs standalone (no Django, no PyCap) on a tiny synthetic fixture. Validates:
  1. The adapter's reshape of a BRAVO TimeDomain recording produces the SAME PSD as feeding
     a `dbs_io.Stream`-shaped epoch directly (the science is unchanged by the glue).
  2. `align_pros` joins correctly for both target modes ("session" and "chronic").

Importable as a pytest module, or runnable directly: `python test_adapter.py`.
"""

import os
import sys
import pathlib

import numpy as np
import pandas as pd

# Put BRAVO/ on the path so `modules.Biomarkers...` resolves (modules is a namespace pkg).
_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

import datetime as _dt

from modules.Biomarkers import adapter
from modules.Biomarkers import pipeline
from modules.Biomarkers.routines import streaming_psd
from modules.Biomarkers.routines import threshold_biomarker


FS = 250.0
CHAN_ORDER = ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"]


def _make_recording(n_seconds=8, seed=0):
    """A synthetic 2-channel BRAVO TimeDomain recording: Data shape (N, n_ch)."""
    rng = np.random.default_rng(seed)
    n = int(n_seconds * FS)
    t = np.arange(n) / FS
    # ch0: 20 Hz tone + noise; ch1: 30 Hz tone + noise.
    ch0 = np.sin(2 * np.pi * 20 * t) + 0.3 * rng.standard_normal(n)
    ch1 = np.sin(2 * np.pi * 30 * t) + 0.3 * rng.standard_normal(n)
    data = np.column_stack([ch0, ch1])  # (N, 2)
    return {
        "SamplingRate": FS,
        "ChannelNames": list(CHAN_ORDER),
        "Data": data,
        "Missing": np.zeros_like(data),
        "StartTime": 1_700_000_000.0,  # fixed unix ts
        "Duration": n / FS,
    }


def test_adapter_reshape_preserves_psd():
    """Adapter reshape (N,ch)->per-channel must reproduce the routine's PSD exactly."""
    rec = _make_recording()

    # Path A: through the adapter.
    epoch = adapter.bravo_timedomain_to_streamdata(rec)
    psd_via_adapter = streaming_psd.welch_psd_for_instance(
        epoch["stream_data"][0], epoch["channel_names"][0], epoch["sample_rate"], CHAN_ORDER
    )

    # Path B: hand-built Stream-shaped input (channels-major), as dbs_io.Stream would expose.
    stream_data = rec["Data"].T  # (2, N)
    psd_direct = streaming_psd.welch_psd_for_instance(
        stream_data, list(CHAN_ORDER), FS, CHAN_ORDER
    )

    assert psd_via_adapter.shape == (1, len(CHAN_ORDER), len(streaming_psd.F_SET))
    np.testing.assert_allclose(psd_via_adapter, psd_direct, rtol=1e-12, atol=1e-12)

    # Sanity: 20 Hz power should land in ch0, 30 Hz in ch1 (tones are separable).
    f = streaming_psd.F_SET
    i20 = int(np.argmin(np.abs(f - 20)))
    i30 = int(np.argmin(np.abs(f - 30)))
    assert psd_direct[0, 0, i20] > psd_direct[0, 0, i30]
    assert psd_direct[0, 1, i30] > psd_direct[0, 1, i20]


def test_compute_psd_pain_correlation_runs():
    """End-to-end routine call over several epochs returns correctly-shaped corr/pval."""
    recs = [_make_recording(seed=k) for k in range(5)]
    streams = adapter.bravo_timedomain_recordings_to_streams(recs)
    labels = np.array([2.0, 4.0, 6.0, 8.0, 9.0])  # increasing pain
    out = streaming_psd.compute_psd_pain_correlation(streams, labels, CHAN_ORDER, transform="log")
    C, F = len(CHAN_ORDER), len(streaming_psd.F_SET)
    assert out["psd"].shape == (5, C, F)
    assert out["corr"].shape == (C, F)
    assert out["pval"].shape == (C, F)


def _make_pro_df():
    return pd.DataFrame({
        "date_time_s1_daily": ["2023-11-14 09:00", "2023-11-14 21:00", "2023-11-15 09:00"],
        "nrs": [8, 6, 4],
        "vas": [80, 60, 40],
        "mpq_sum": [30, 20, 10],
    })


def test_align_pros_session():
    """Session alignment aggregates PRO metrics by the session's calendar date."""
    rec = _make_recording()  # StartTime 1_700_000_000 -> 2023-11-14 UTC
    df = adapter.align_pros(_make_pro_df(), target="session", recordings=[rec])
    assert len(df) == 1
    row = df.iloc[0]
    # 2023-11-14 has nrs [8,6] -> mean 7, min 6.
    assert row["nrs_mean"] == 7.0
    assert row["nrs_min"] == 6.0


def test_align_pros_chronic():
    """Chronic alignment joins nearest-date PRO and reads stim amplitude from the packet."""
    # Two chronic samples on 2023-11-14 and 2023-11-15 (unix ts), LFP + Amplitude columns.
    t0 = 1_700_000_000.0
    chronic = {
        "Time": np.array([t0, t0 + 86_400.0]),
        "Data": np.array([[1.0, 2.5], [1.5, 3.0]]),  # [LFP, Amp]
        "ChannelNames": ["L LFP", "L Amplitude"],
    }
    df = adapter.align_pros(_make_pro_df(), target="chronic", chronic=chronic)
    assert len(df) == 2
    assert list(df["stim_amplitude"]) == [2.5, 3.0]
    # 2023-11-14 nrs mean = 7; 2023-11-15 nrs mean = 4.
    assert df.iloc[0]["nrs"] == 7.0
    assert df.iloc[1]["nrs"] == 4.0


# ---------------------------------------------------------------------------
# Chronic ("10-min PSD") source: adapter, science, merge, back-compat
# ---------------------------------------------------------------------------
_MIDNIGHT_UTC = 1_699_920_000.0  # 2023-11-14 00:00:00 UTC


def _utc_str(unix):
    return _dt.datetime.utcfromtimestamp(unix).isoformat()


def _make_chronic_trend(days=14, step_hours=2):
    """Synthetic chronic recording + daily PRO. Even days = high pain (high LFP power)."""
    times, lfp, amp = [], [], []
    for d in range(days):
        pain_day = (d % 2 == 0)
        for h in range(0, 24, step_hours):
            times.append(_MIDNIGHT_UTC + d * 86_400 + h * 3_600)
            lfp.append(150.0 if pain_day else 110.0)
            amp.append(2.0)
    chronic = {
        "SamplingRate": -1,
        "Time": np.array(times, dtype=float),
        "Data": np.column_stack([np.array(lfp), np.array(amp)]),
        "ChannelNames": ["L LFP", "L Amplitude"],
    }
    pro = pd.DataFrame({
        "date_time_s1_daily": [_utc_str(_MIDNIGHT_UTC + d * 86_400 + 12 * 3_600) for d in range(days)],
        "nrs": [8 if d % 2 == 0 else 2 for d in range(days)],
    })
    return chronic, pro


def test_bravo_chronic_to_lfp_df_shape():
    chronic, pro = _make_chronic_trend()
    cv = adapter.bravo_chronic_to_lfp_df(chronic, pro, label_metric="nrs")
    assert list(cv.columns) == ["timestamp", "LFP", "LFP_smoothed", "stim_amplitude", "pain_level", "nrs"]
    levels = set(cv["pain_level"].dropna().unique())
    assert levels <= {0.0, 1.0} and len(levels) == 2  # both classes present
    # High-pain (even) days should be labeled 1.
    assert cv.loc[cv["nrs"] == 8, "pain_level"].eq(1.0).all()


def test_bravo_chronic_accepts_list_of_recordings():
    chronic, pro = _make_chronic_trend(days=6)
    half = len(chronic["Time"]) // 2
    rec_a = {"Time": chronic["Time"][:half], "Data": chronic["Data"][:half], "ChannelNames": chronic["ChannelNames"]}
    rec_b = {"Time": chronic["Time"][half:], "Data": chronic["Data"][half:], "ChannelNames": chronic["ChannelNames"]}
    cv = adapter.bravo_chronic_to_lfp_df([rec_b, rec_a], pro, label_metric="nrs")  # out of order on purpose
    assert cv["timestamp"].is_monotonic_increasing  # _concat_chronic sorts by time
    assert len(cv) == len(chronic["Time"])


def test_run_chronic_threshold_runs():
    rows = []
    for d in range(14):
        pain = 1.0 if d % 2 == 0 else 0.0
        for h in range(0, 24, 2):
            ts = pd.Timestamp(_dt.datetime.utcfromtimestamp(_MIDNIGHT_UTC + d * 86_400 + h * 3_600))
            rows.append({"timestamp": ts, "LFP_smoothed": 150.0 if pain else 110.0, "pain_level": pain})
    cv_df = pd.DataFrame(rows)
    out = threshold_biomarker.run_chronic_threshold(cv_df, train_days=3, gap_days=1, test_days=2)
    assert out["n_windows"] >= 1
    assert np.isfinite(out["mean_thr_sens"])
    # Threshold should fall between the two class levels and separate them well.
    assert 110.0 <= out["mean_thr_sens"] <= 150.0
    assert out["mean_test_acc_sens"] == 1.0


def test_merge_timelines_both_and_degenerate():
    base = _dt.datetime(2023, 11, 14, 12, 0, 0)
    td = pd.DataFrame({
        "time": pd.to_datetime([base, base + _dt.timedelta(days=1)]),
        "date": [base.date(), (base + _dt.timedelta(days=1)).date()],
        "td_biomarker_value": [1.0, 2.0],
    })
    chronic = pd.DataFrame({
        "time": pd.to_datetime([base + _dt.timedelta(hours=k) for k in range(5)]),
        "date": [base.date()] * 5,
        "chronic_biomarker_value": [10.0, 11.0, 12.0, 13.0, 14.0],
    })
    merged = adapter.merge_timelines(td, chronic)
    assert len(merged) == 5  # chronic spine
    assert "td_biomarker_value" in merged.columns and "chronic_biomarker_value" in merged.columns
    assert merged["td_biomarker_value"].notna().all()  # nearest session within 1 day

    only_td = adapter.merge_timelines(td, None)
    assert len(only_td) == 2 and "chronic_biomarker_value" not in only_td.columns
    only_ch = adapter.merge_timelines(None, chronic)
    assert len(only_ch) == 5 and "td_biomarker_value" not in only_ch.columns


def test_run_streaming_biomarker_backcompat():
    recs = [_make_recording(seed=k) for k in range(4)]
    for k, r in enumerate(recs):
        r["StartTime"] = _MIDNIGHT_UTC + k * 86_400
    pro = pd.DataFrame({
        "date_time_s1_daily": [_utc_str(_MIDNIGHT_UTC + k * 86_400 + 12 * 3_600) for k in range(4)],
        "nrs": [8, 6, 4, 3], "vas": [80, 60, 40, 30], "mpq_sum": [30, 20, 10, 5],
    })
    out = pipeline.run_streaming_biomarker(recs, pro, CHAN_ORDER)
    assert {"result", "band", "combined"} <= set(out)
    assert isinstance(out["combined"], pd.DataFrame)


def test_run_biomarker_both_unified_timeline():
    recs = [_make_recording(seed=k) for k in range(6)]
    for k, r in enumerate(recs):
        r["StartTime"] = _MIDNIGHT_UTC + (2 * k) * 86_400
    chronic, pro_chronic = _make_chronic_trend(days=14)
    # PRO frame must cover both the session dates and the chronic dates.
    pro = pd.DataFrame({
        "date_time_s1_daily": list(pro_chronic["date_time_s1_daily"]),
        "nrs": list(pro_chronic["nrs"]),
    })
    out = pipeline.run_biomarker(recs, pro, CHAN_ORDER, source="both", chronic=chronic,
                                 train_days=3, gap_days=1, test_days=2)
    assert out["source"] == "both"
    assert out["timedomain"] is not None and out["powerdomain"] is not None
    cols = set(out["combined"].columns)
    assert "td_biomarker_value" in cols and "powerdomain_biomarker_value" in cols
    assert out["powerdomain"]["summary"]["n_windows"] >= 1


def test_chronic_summary_is_self_consistent():
    """Chronic headline summary must report metrics at ONE threshold (the sens-objective):
    spec must be the spec achieved at best_threshold, never the spec-objective's spec."""
    chronic, pro = _make_chronic_trend(days=14)
    out = pipeline.run_chronic_branch(pro, chronic=chronic, train_days=3, gap_days=1, test_days=2)
    s, d = out["summary"], out["detail"]
    assert s["best_threshold"] == d["mean_thr_sens"]
    assert s["sens"] == d["mean_test_sens_sens"]
    assert s["spec"] == d["mean_test_spec_sens"]   # NOT mean_test_spec_spec
    assert s["acc"] == d["mean_test_acc_sens"]
    assert s["spec_objective_threshold"] == d["mean_thr_spec"]


def test_merge_timelines_handles_nat_time():
    """merge_timelines must not crash when a timeline has a NaT time (missing StartTime)."""
    base = _dt.datetime(2023, 11, 14, 12, 0, 0)
    td = pd.DataFrame({
        "time": pd.to_datetime([base, pd.NaT]),
        "date": [base.date(), None],
        "td_biomarker_value": [1.0, 2.0],
    })
    chronic = pd.DataFrame({
        "time": pd.to_datetime([base + _dt.timedelta(hours=k) for k in range(5)]),
        "date": [base.date()] * 5,
        "chronic_biomarker_value": [10.0, 11.0, 12.0, 13.0, 14.0],
    })
    merged = adapter.merge_timelines(td, chronic)  # must not raise
    assert len(merged) == 5
    assert "td_biomarker_value" in merged.columns


# ---------------------------------------------------------------------------
# KMeans pain_level labeler (matches threshold_biomarker.ipynb cell 10)
# ---------------------------------------------------------------------------
def _make_chronic_trend_with_kmeans_features(days=14, step_hours=2):
    """Chronic trend + PRO that ALSO carries the [left_leg_vas, mpq_sum] cluster features."""
    chronic, pro = _make_chronic_trend(days, step_hours)
    pro["left_leg_vas"] = [70 if d % 2 == 0 else 10 for d in range(days)]
    pro["mpq_sum"] = [40 if d % 2 == 0 else 5 for d in range(days)]
    return chronic, pro


def test_kmeans_pain_level_labels_high_pain_as_one():
    """KMeans labeler: higher [vas, mpq] cluster -> 1; NaN-feature rows get a finite label."""
    low = np.column_stack([np.full(10, 5.0), np.full(10, 3.0)])
    high = np.column_stack([np.full(10, 80.0), np.full(10, 40.0)])
    feats = np.vstack([low, high])
    pl = threshold_biomarker.kmeans_pain_level(feats)
    assert set(np.unique(pl)) == {0.0, 1.0}
    assert pl[:10].mean() == 0.0 and pl[10:].mean() == 1.0   # high cluster relabeled to 1

    feats2 = np.vstack([feats, [[np.nan, np.nan]]])           # NaN row -> nearest label, no NaN
    pl2 = threshold_biomarker.kmeans_pain_level(feats2)
    assert not np.isnan(pl2).any()
    assert set(np.unique(pl2)) <= {0.0, 1.0}


def test_bravo_chronic_kmeans_strategy():
    """label_strategy='kmeans' clusters [left_leg_vas, mpq_sum]; high-pain days -> 1."""
    chronic, pro = _make_chronic_trend_with_kmeans_features()
    cv = adapter.bravo_chronic_to_lfp_df(chronic, pro, label_metric="nrs", label_strategy="kmeans")
    assert set(cv["pain_level"].dropna().unique()) <= {0.0, 1.0}
    assert cv.loc[cv["nrs"] == 8, "pain_level"].eq(1.0).all()  # high days
    assert cv.loc[cv["nrs"] == 2, "pain_level"].eq(0.0).all()  # low days


def test_kmeans_falls_back_to_cutoff_and_warns():
    """If the cluster features are absent, 'kmeans' warns and degrades to the cutoff labeler."""
    import warnings
    chronic, pro = _make_chronic_trend(days=14)  # nrs only, no left_leg_vas/mpq_sum
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cv = adapter.bravo_chronic_to_lfp_df(chronic, pro, label_metric="nrs", label_strategy="kmeans")
    assert any("Falling back" in str(x.message) for x in w)
    assert cv.loc[cv["nrs"] == 8, "pain_level"].eq(1.0).all()


def test_bravo_powerdomain_to_chronic_like():
    """Power-Domain packets (StartTime+fs, per-contact Power/Stim, sentinel + Missing) convert to
    chronic-shaped power dicts: one series per Power channel, sentinel/missing samples dropped,
    timestamps = StartTime + index/fs of the surviving samples, paired with same-hemi stim."""
    fs, start, n = 2.0, _MIDNIGHT_UTC, 5
    data = np.array([
        [10.0, 100.0, 1.0, 2.0],
        [4.3e9, 110.0, 1.0, 2.0],   # L power sentinel -> dropped from L series
        [12.0, 120.0, 1.0, 2.0],
        [13.0, 130.0, 1.0, 2.0],
        [14.0, 140.0, 1.0, 2.0],
    ])
    missing = np.zeros_like(data); missing[3, 0] = 1.0   # L power idx3 flagged missing
    rec = {"SamplingRate": fs, "StartTime": start, "Duration": n / fs,
           "ChannelNames": ["ZERO_THREE_LEFT Power", "ZERO_THREE_RIGHT Power",
                            "ZERO_THREE_LEFT Stimulation", "ZERO_THREE_RIGHT Stimulation"],
           "Data": data, "Missing": missing}
    out = adapter.bravo_powerdomain_to_chronic_like([rec])
    assert len(out) == 2, "one chronic-shaped series per Power channel"
    left = next(o for o in out if o["ChannelNames"][0].startswith("Left"))
    right = next(o for o in out if o["ChannelNames"][0].startswith("Right"))
    # L: sentinel (idx1) + missing (idx3) dropped -> 10,12,14 at idx 0,2,4
    assert list(left["Data"][:, 0]) == [10.0, 12.0, 14.0]
    assert (left["Data"][:, 1] == 1.0).all()                 # paired with LEFT stim col
    assert np.allclose(left["Time"], [start + 0 / fs, start + 2 / fs, start + 4 / fs])
    assert list(right["Data"][:, 0]) == [100.0, 110.0, 120.0, 130.0, 140.0]
    assert all(o["SamplingRate"] == -1 for o in out)         # chronic-shaped marker
    # Feeds the chronic tidy-frame builder unchanged (cutoff strategy avoids kmeans feature needs).
    cv = adapter.bravo_chronic_to_lfp_df(out, _make_pro_df(), label_metric="nrs",
                                         label_strategy="cutoff")
    assert "LFP" in cv.columns and "LFP_smoothed" in cv.columns and len(cv) == 8


if __name__ == "__main__":
    test_adapter_reshape_preserves_psd()
    test_compute_psd_pain_correlation_runs()
    test_align_pros_session()
    test_align_pros_chronic()
    test_bravo_chronic_to_lfp_df_shape()
    test_bravo_chronic_accepts_list_of_recordings()
    test_run_chronic_threshold_runs()
    test_merge_timelines_both_and_degenerate()
    test_run_streaming_biomarker_backcompat()
    test_run_biomarker_both_unified_timeline()
    test_chronic_summary_is_self_consistent()
    test_merge_timelines_handles_nat_time()
    test_kmeans_pain_level_labels_high_pain_as_one()
    test_bravo_chronic_kmeans_strategy()
    test_kmeans_falls_back_to_cutoff_and_warns()
    test_bravo_powerdomain_to_chronic_like()
    print("All adapter tests passed.")
