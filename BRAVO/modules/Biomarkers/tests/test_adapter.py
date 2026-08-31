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
from modules.Biomarkers.routines import analytics


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
    # `source` is carried (defaults to "chronic") for the two-source batch-confound diagnostic, and
    # `frequency_hz` is carried per-sample for the per-(channel,frequency) decoding path (NaN here
    # because the synthetic trend recordings have no CenterFrequencyHz).
    assert list(cv.columns) == ["timestamp", "LFP", "LFP_smoothed", "stim_amplitude", "pain_level", "nrs", "source", "frequency_hz"]
    assert set(cv["source"].unique()) == {"chronic"}
    assert cv["frequency_hz"].isna().all()
    levels = set(cv["pain_level"].dropna().unique())
    assert levels <= {0.0, 1.0} and len(levels) == 2  # both classes present
    # High-pain (even) days should be labeled 1.
    assert cv.loc[cv["nrs"] == 8, "pain_level"].eq(1.0).all()


def test_bravo_chronic_to_lfp_df_frequency_attribution():
    """Each sample carries the sensing frequency of the recording it came from, snapped to the
    Percept FFT bin — so the decoding path can filter to one (channel, frequency) combo."""
    chronic, pro = _make_chronic_trend()
    # Split the single trend into two recordings programmed at different sensing bands. 7.81 and
    # 22.46 snap to 7.8 and 22.5 (250/256 grid). The samples keep their per-recording frequency.
    t = np.asarray(chronic["Time"], dtype=float)
    d = np.asarray(chronic["Data"], dtype=float)
    mid = len(t) // 2
    rec_a = {"SamplingRate": -1, "Time": t[:mid], "Data": d[:mid],
             "ChannelNames": ["L LFP", "L Amplitude"], "CenterFrequencyHz": 7.81}
    rec_b = {"SamplingRate": -1, "Time": t[mid:], "Data": d[mid:],
             "ChannelNames": ["L LFP", "L Amplitude"], "CenterFrequencyHz": 22.46}
    cv = adapter.bravo_chronic_to_lfp_df([rec_a, rec_b], pro, label_metric="nrs")
    assert "frequency_hz" in cv.columns
    freqs = set(cv["frequency_hz"].dropna().round(1).unique())
    assert freqs == {7.8, 22.5}
    # Filtering to one frequency yields a non-empty, single-band decoding slice.
    sub = cv[cv["frequency_hz"].round(1) == 7.8]
    assert len(sub) > 0 and set(sub["frequency_hz"].round(1).unique()) == {7.8}


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


def _make_cv_df(days=14):
    """Synthetic chronic cv_df: even days high-pain (LFP 150), odd days low (LFP 110)."""
    rows = []
    for d in range(days):
        pain = 1.0 if d % 2 == 0 else 0.0
        for h in range(0, 24, 2):
            ts = pd.Timestamp(_dt.datetime.utcfromtimestamp(_MIDNIGHT_UTC + d * 86_400 + h * 3_600))
            rows.append({"timestamp": ts, "LFP_smoothed": 150.0 if pain else 110.0,
                         "LFP": 150.0 if pain else 110.0, "stim_amplitude": 2.0, "pain_level": pain})
    return pd.DataFrame(rows)


def test_run_chronic_threshold_no_sliding():
    """sliding=False -> ONE all-data fit (no temporal windows): n_windows==1, threshold separates
    the classes, std==0 (single fit). Proves the no-sliding-window toggle path."""
    out = threshold_biomarker.run_chronic_threshold(_make_cv_df(), sliding=False)
    assert out["n_windows"] == 1
    assert np.isfinite(out["mean_thr_sens"]) and 110.0 <= out["mean_thr_sens"] <= 150.0
    assert out["mean_test_acc_sens"] == 1.0
    assert out["std_thr_sens"] == 0.0


def test_sliding_window_analytics_no_sliding():
    """sliding=False -> a single all-data window entry (flagged), vs many entries when sliding on.

    Return shape is now `{windows: [...], summary: {...}}` so the panel can caption coverage.
    """
    cv = _make_cv_df()
    full = analytics.sliding_window_analytics(cv, sliding=True)
    one = analytics.sliding_window_analytics(cv, sliding=False)
    assert set(one.keys()) >= {"windows", "summary"}
    assert len(one["windows"]) == 1 and one["windows"][0].get("all_data") is True
    assert one["windows"][0]["threshold"] is not None
    assert one["summary"]["n_total"] == 1
    assert len(full["windows"]) > 1   # sliding produces many windows on the same data
    assert full["summary"]["n_total"] >= len(full["windows"])


def test_sliding_window_skips_one_class_test_folds():
    """When a tertile-labeled test fold has only one class, the window is expanded; if it still
    has one class after expansion, it's SKIPPED (not a half-NaN row) and counted in summary."""
    # 30 days, label_metric alternates blocks; tertile-style binarization (NaN middle on day 15)
    rng = np.random.default_rng(0)
    days = pd.date_range("2025-01-01", periods=30, freq="D")
    rows = []
    for i, d in enumerate(days):
        label = 0.0 if i < 14 else (np.nan if i == 14 else 1.0)
        for k in range(20):
            rows.append({"timestamp": d + pd.Timedelta(minutes=10 * k),
                         "LFP_smoothed": float(rng.normal(100 + 20 * (label if np.isfinite(label) else 0.5), 5)),
                         "pain_level": label})
    cv = pd.DataFrame(rows)
    out = analytics.sliding_window_analytics(cv, train_days=7, gap_days=1, test_days=2,
                                             step_days=1, sliding=True, max_test_days=4)
    # No half-NaN rows leak out: every returned window has a defined AUC.
    assert all(w["auc"] is not None for w in out["windows"])
    # Summary counts what was skipped.
    assert out["summary"]["n_total"] >= len(out["windows"])
    assert out["summary"]["n_skipped_test_one_class"] >= 0
    assert out["summary"]["max_test_days"] == 4


def test_td_sliding_corr_spectrum_matches_scipy():
    """The fully-vectorized sliding R-vs-frequency heatmap must equal scipy.stats.pearsonr computed
    the naive way for each (window, channel, freq) — proving the W@X matmul math is correct."""
    from scipy.stats import pearsonr
    rng = np.random.default_rng(0)
    E, C, F = 40, 2, 5
    times = [pd.Timestamp(_dt.datetime.utcfromtimestamp(_MIDNIGHT_UTC + d * 86_400)) for d in range(E)]
    psd = rng.standard_normal((E, C, F))
    labels = rng.standard_normal(E)
    detail = {"psd": psd, "labels": labels, "f_set": np.arange(F) * 1.0,
              "chan_order": ["ZERO_TWO_LEFT", "ZERO_TWO_RIGHT"]}
    out = analytics.td_sliding_corr_spectrum(detail, times, window_days=10, step_days=10, min_sessions=3)
    chans = out["channels"]
    assert len(chans) == C
    starts = chans[0]["window_starts"]
    assert len(starts) >= 2
    assert chans[0]["channel"] == "L 0⁻2⁺"   # numeric contact label, not word form

    tv = np.array([t.value for t in times], dtype=float)  # ns since epoch (tz-naive)
    w_ns = 10 * 86_400 * 1e9
    # The function applies session-level MAD outlier rejection on the label (>=3 MADs from the
    # median dropped from every window), so the scipy reference must use the SAME surviving sessions.
    lmed = np.median(labels)
    lmad = np.median(np.abs(labels - lmed))
    label_keep = (np.abs(labels - lmed) <= 3.0 * lmad) if lmad > 0 else np.ones(labels.shape, bool)
    checked = 0
    for (wi, ci, fi) in [(0, 0, 0), (1, 1, F - 1)]:
        if wi >= len(starts):
            continue
        w0 = pd.Timestamp(starts[wi]).value
        idx = np.where((tv >= w0) & (tv < w0 + w_ns) & label_keep)[0]
        if len(idx) < 3:
            continue
        r_ref = pearsonr(psd[idx, ci, fi], labels[idx])[0]
        r_got = chans[ci]["r"][fi][wi]   # r is [freq][window]
        assert abs(r_got - r_ref) < 1e-9, (wi, ci, fi, r_got, r_ref)
        checked += 1
    assert checked >= 1
    print("OK td_sliding_corr_spectrum matches scipy (checked %d cells)" % checked)


def test_pearson_corr_psd_label_rejects_mad_outliers():
    """MAD outlier rejection: a single artifact session must be excluded from the PSD<->pain
    correlation so it cannot fabricate (or destroy) a correlation. The MAD-filtered R on data with
    one planted spike must match the R on the clean data, and differ from the naive (unfiltered) R.

    Updated 2026-08-30 for the plate-wide consolidation: the threshold is now read from
    stats_utils.MAD_N_DEFAULT instead of being hardcoded at 3, so this test follows the canonical
    rule rather than pinning a value that has since changed. Note the API change it also covers:
    `mad_k=None` now means USE THE CANONICAL THRESHOLD, and disabling is `mad_k=0`."""
    pearson_corr_psd_label = streaming_psd.pearson_corr_psd_label
    rng = np.random.default_rng(7)
    E = 60
    label = np.linspace(0, 10, E)
    feat_clean = (label + rng.normal(0, 1.0, E))           # genuinely correlated feature
    psd_clean = feat_clean.reshape(E, 1, 1)
    r_clean, _ = pearson_corr_psd_label(psd_clean, label)      # canonical threshold

    # Plant one extreme artifact session (huge feature, mid-range label) that would distort a naive R.
    feat_spk = feat_clean.copy(); feat_spk[E // 2] += 500.0
    psd_spk = feat_spk.reshape(E, 1, 1)
    r_filtered, _ = pearson_corr_psd_label(psd_spk, label)                # MAD drops the spike
    r_naive, _ = pearson_corr_psd_label(psd_spk, label, mad_k=0)          # 0 == disabled

    rc, rf, rn = float(r_clean[0, 0]), float(r_filtered[0, 0]), float(r_naive[0, 0])
    # Filtered R recovers the clean correlation; naive R is corrupted by the spike.
    assert abs(rf - rc) < 0.05, (rc, rf)
    assert abs(rn - rc) > 0.1, (rc, rn)
    print("OK pearson_corr_psd_label MAD rejection: clean=%.3f filtered=%.3f naive=%.3f" % (rc, rf, rn))


def test_mad_outlier_mask_behavior():
    """mad_outlier_mask: KEEP-mask True within k MADs of the median. Drops |x-med|>k*MAD spikes,
    excludes non-finite, and (deliberately) returns the plain finite mask when MAD is undefined
    (all-equal) or there are < 3 finite points — those are the documented no-op fallbacks."""
    m = adapter.mad_outlier_mask(np.array([1.0, 2.0, 3.0, 4.0, 100.0]), k=3.0)
    assert m.tolist() == [True, True, True, True, False]          # 100 is the spike
    # all-equal -> MAD==0 -> keep everything (no false positives on a constant series)
    assert adapter.mad_outlier_mask(np.array([5.0, 5.0, 5.0, 5.0])).all()
    # < 3 finite points -> MAD unstable -> return the finite mask unchanged (NaN excluded)
    assert adapter.mad_outlier_mask(np.array([1.0, np.nan])).tolist() == [True, False]
    # NaN excluded from the keep set AND the spike still dropped, simultaneously
    assert adapter.mad_outlier_mask(np.array([1.0, 2.0, 3.0, np.nan, 100.0])).tolist() == \
        [True, True, True, False, False]


def test_concat_chronic_mad_is_per_recording_not_global():
    """_concat_chronic applies MAD outlier rejection PER RECORDING, not globally. A small low-scale
    source (~10) concatenated with a large high-scale source (~100): per-recording MAD keeps BOTH
    sources intact, whereas a GLOBAL MAD (dominated by the high source) would erase the entire
    low-scale source. A within-source spike is still dropped; mad_k=None disables rejection."""
    tA = _MIDNIGHT_UTC + np.arange(8) * 3600.0
    dA = np.column_stack([np.full(8, 10.0), np.full(8, 2.0)])      # tight low-scale source
    tB = _MIDNIGHT_UTC + (50 + np.arange(60)) * 3600.0
    dB = np.column_stack([np.full(60, 100.0), np.full(60, 2.0)])   # tight high-scale source
    rec_a = {"Time": tA, "Data": dA, "ChannelNames": ["L LFP", "L Amplitude"]}
    rec_b = {"Time": tB, "Data": dB, "ChannelNames": ["L LFP", "L Amplitude"]}
    lfp = adapter._concat_chronic([rec_a, rec_b])["Data"][:, 0]   # canonical threshold
    assert (lfp == 10.0).sum() == 8 and (lfp == 100.0).sum() == 60   # both sources fully survive
    # Control: a GLOBAL MAD would flag every low-scale sample as an outlier.
    allv = np.concatenate([dA[:, 0], dB[:, 0]])
    med = np.median(allv); mad = np.median(np.abs(allv - med))
    from modules.Biomarkers.routines.stats_utils import MAD_N_DEFAULT as _K
    assert (np.abs(allv[:8] - med) <= _K * mad).sum() == 0
    # A within-source spike IS dropped (give the source spread so MAD is defined).
    rng = np.random.default_rng(3)
    dS = np.column_stack([rng.normal(10, 1, 40), np.full(40, 2.0)]); dS[5, 0] = 9000.0
    rec_s = {"Time": _MIDNIGHT_UTC + np.arange(40) * 3600.0, "Data": dS,
             "ChannelNames": ["L LFP", "L Amplitude"]}
    assert 9000.0 not in set(adapter._concat_chronic(rec_s)["Data"][:, 0])
    # mad_k=0 disables rejection -> the spike survives. (None now means CANONICAL, not off.)
    assert 9000.0 in set(adapter._concat_chronic(rec_s, mad_k=0)["Data"][:, 0])


def test_sliding_window_test_fold_expansion_fires_and_categorizes_skips():
    """The test-fold expansion must actually FIRE (a window's test_days_used grows beyond the
    requested test_days when the short window is single-class) and skips must be CATEGORIZED into
    one-class vs no-data with the summary counts reconciling to n_total. Every returned window has a
    defined AUC (no half-NaN rows leak out)."""
    days = pd.date_range("2025-01-01", periods=40, freq="D")
    rows = []
    for i, d in enumerate(days):
        if i < 20:
            lab = float(i % 2)            # alternating classes -> usable training
        elif i < 28:
            lab = 0.0                     # homogeneous block -> short test fold is single-class
        else:
            lab = 1.0                     # class flips -> expansion reaches both classes
        for k in range(15):
            rows.append({"timestamp": d + pd.Timedelta(minutes=5 * k),
                         "LFP_smoothed": 100 + 30 * lab + np.random.default_rng(i * 15 + k).normal(0, 2),
                         "pain_level": lab})
    cv = pd.DataFrame(rows)
    out = analytics.sliding_window_analytics(cv, train_days=10, gap_days=1, test_days=2,
                                             step_days=1, sliding=True, max_test_days=8)
    used = [w["test_days_used"] for w in out["windows"]]
    assert any(u > 2 for u in used), "expansion never fired (no test_days_used grew past test_days)"
    assert all(u <= 8 for u in used)                              # never exceeds max_test_days
    assert all(w["auc"] is not None for w in out["windows"])      # no half-NaN rows
    s = out["summary"]
    assert s["n_skipped_test_one_class"] >= 1                     # at least one genuine one-class skip
    assert s["n_total"] == len(out["windows"]) + s["n_skipped_test_one_class"] + s["n_skipped_no_data"]
    assert s["max_test_days"] == 8 and s["test_days"] == 2


def test_decimate_for_plot_thins_only():
    """decimate_for_plot thins rows FOR PLOTTING ONLY: a strict row-subset, columns + values
    unchanged (no interpolation), under-cap frames returned as-is. Locks the plot-only invariant."""
    df = pd.DataFrame({"time": list(range(100)), "v": [x * 1.5 for x in range(100)]})
    out = adapter.decimate_for_plot(df, 10)
    assert len(out) <= 10
    assert list(out.columns) == ["time", "v"]            # columns preserved
    assert out["v"].iloc[0] == 0.0                        # first row kept
    assert set(out["v"]).issubset(set(df["v"]))           # strict subset: no interpolated values
    assert len(adapter.decimate_for_plot(df.head(5), 10)) == 5   # under cap -> unchanged


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


def test_threshold_pain_level_tertile_drops_middle():
    """tertile labeler: low tertile -> 0, high tertile -> 1, ambiguous middle -> NaN."""
    # 90 samples, metric ramps 0..89 -> tertiles at 30th/60th value-ish
    df = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=90, freq="D"),
                       "nrs": np.arange(90, dtype=float)})
    pl = adapter._threshold_pain_level(df, "nrs", strategy="tertile", daily_broadcast=True)
    assert set(np.unique(pl[np.isfinite(pl)])) <= {0.0, 1.0}
    assert np.isnan(pl).sum() > 0, "the middle band must be excluded (NaN)"
    # lowest values labeled low, highest labeled high
    assert pl[0] == 0.0 and pl[-1] == 1.0
    # middle value excluded
    assert np.isnan(pl[45])


def test_threshold_pain_level_median_keeps_all():
    """median labeler: every sample labeled (no NaN middle), ~50/50 on a symmetric metric."""
    df = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=100, freq="D"),
                       "nrs": np.arange(100, dtype=float)})
    pl = adapter._threshold_pain_level(df, "nrs", strategy="median", daily_broadcast=True)
    assert np.isnan(pl).sum() == 0
    assert abs(pl.mean() - 0.5) < 0.02


def test_daily_broadcast_fixes_density_confound():
    """The cut is computed on DAILY values, not the density-inflated per-sample array.

    Over-record the low-pain days: per-sample the median sits at the low value (everything would
    label high), but daily-broadcast puts the cut at the true daily median.
    """
    rows = []
    days = pd.date_range("2025-01-01", periods=60, freq="D")
    for i, d in enumerate(days):
        val = 3.0 if i < 20 else (6.0 if i < 40 else 9.0)
        k = 50 if i < 20 else 2   # low days heavily over-recorded
        rows += [(d + pd.Timedelta(minutes=10 * j), val) for j in range(k)]
    df = pd.DataFrame(rows, columns=["timestamp", "nrs"])
    pl_db = adapter._threshold_pain_level(df, "nrs", strategy="median", daily_broadcast=True)
    pl_raw = adapter._threshold_pain_level(df, "nrs", strategy="median", daily_broadcast=False)
    # legacy per-sample median collapses to all-high; daily-broadcast does not
    assert pl_raw.mean() == 1.0
    assert pl_db.mean() < 0.2
    # the value-3 (low) days must be labeled low under daily-broadcast
    assert (pl_db[df["nrs"].to_numpy() == 3.0] == 0.0).all()


def test_bravo_chronic_tertile_strategy_end_to_end():
    """tertile strategy flows through bravo_chronic_to_lfp_df and yields 0/1/NaN labels."""
    chronic, pro = _make_chronic_trend_with_kmeans_features()
    cv = adapter.bravo_chronic_to_lfp_df(chronic, pro, label_metric="nrs", label_strategy="tertile")
    assert set(cv["pain_level"].dropna().unique()) <= {0.0, 1.0}
    # high-pain days (nrs 8) end up high, low-pain days (nrs 2) end up low
    assert cv.loc[cv["nrs"] == 8, "pain_level"].eq(1.0).all()
    assert cv.loc[cv["nrs"] == 2, "pain_level"].eq(0.0).all()


def test_run_powerdomain_branch_per_channel_split():
    """Two-channel chronic input -> branch returns a per_channel dict keyed by ChannelNames[0]
    with independent summaries; the pooled run continues to work alongside it."""
    chronic_l, pro = _make_chronic_trend(days=14)
    # Build a Right-hemisphere counterpart with the OPPOSITE pain-LFP coupling so the per-channel
    # thresholds (and AUCs) genuinely differ from the pooled result.
    times, lfp_r, amp_r = [], [], []
    for d in range(14):
        pain_day = (d % 2 == 0)
        for h in range(0, 24, 2):
            times.append(_MIDNIGHT_UTC + d * 86_400 + h * 3_600)
            lfp_r.append(80.0 if pain_day else 130.0)   # inverted coupling
            amp_r.append(2.0)
    chronic_r = {
        "SamplingRate": -1,
        "Time": np.array(times, dtype=float),
        "Data": np.column_stack([np.array(lfp_r), np.array(amp_r)]),
        "ChannelNames": ["R LFP", "R Amplitude"],
    }
    run = pipeline.run_powerdomain_branch(pro, chronic=[chronic_l, chronic_r],
                                          label_metric="nrs", label_strategy="cutoff",
                                          train_days=4, gap_days=1, test_days=2)
    assert "per_channel" in run and set(run["per_channel"].keys()) >= {"L LFP", "R LFP"}
    l_thr = run["per_channel"]["L LFP"]["summary"]["best_threshold"]
    r_thr = run["per_channel"]["R LFP"]["summary"]["best_threshold"]
    # Independent thresholds for the two hemispheres (different LFP scales) — must NOT collapse to
    # the pooled threshold.
    assert l_thr != r_thr
    # Each per-channel run carries its own cv_df with no rows from the other channel.
    cv_l = run["per_channel"]["L LFP"]["cv_df"]; cv_r = run["per_channel"]["R LFP"]["cv_df"]
    assert cv_l is not None and cv_r is not None
    # The pooled summary still has its in-sample AUC alongside the per-channel breakdown.
    assert "auc_in_sample" in run["summary"]


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
    # ChannelNames are now real bipolar-contact labels decoded from the power column name
    # (e.g. "ZERO_THREE_LEFT Power" -> "L 0⁻3⁺"), not the generic "Left LFP".
    left = next(o for o in out if o["ChannelNames"][0].startswith("L"))
    right = next(o for o in out if o["ChannelNames"][0].startswith("R"))
    assert "0" in left["ChannelNames"][0] and "3" in left["ChannelNames"][0], \
        f"expected a decoded bipolar contact label, got {left['ChannelNames'][0]!r}"
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
    test_threshold_pain_level_tertile_drops_middle()
    test_threshold_pain_level_median_keeps_all()
    test_daily_broadcast_fixes_density_confound()
    test_bravo_chronic_tertile_strategy_end_to_end()
    test_run_powerdomain_branch_per_channel_split()
    test_bravo_powerdomain_to_chronic_like()
    test_run_chronic_threshold_no_sliding()
    test_sliding_window_analytics_no_sliding()
    test_sliding_window_skips_one_class_test_folds()
    test_td_sliding_corr_spectrum_matches_scipy()
    test_pearson_corr_psd_label_rejects_mad_outliers()
    test_mad_outlier_mask_behavior()
    test_concat_chronic_mad_is_per_recording_not_global()
    test_sliding_window_test_fold_expansion_fires_and_categorizes_skips()
    test_decimate_for_plot_thins_only()
    print("All adapter tests passed.")


def test_align_pros_records_the_matched_report_identity_not_just_its_value():
    """`matched_pro_time` is the IDENTITY of the matched report, which is what callers need in order
    to cluster correctly.

    Regression for a defect fixed 2026-08-30: pipeline.run_timedomain_branch used to reconstruct the
    grouping by searching pro_df for a report whose VALUE equalled the session's label and taking the
    first hit. On an integer pain scale that collapses every session sharing a score into one
    "rating". Measured on live RCS08 with Metric=nrs: 72 genuinely distinct matched reports were
    represented as 7 groups, because there were only 7 distinct NRS values. Two sessions matched to
    DIFFERENT reports that happen to share a score must land in different groups.
    """
    import datetime as _dt
    base = _dt.datetime(2026, 3, 1, 12, 0, 0)
    # three reports, two of which share the SAME pain value but are different reports
    pro = pd.DataFrame({
        "date_time_s1_daily": [base, base + _dt.timedelta(days=1), base + _dt.timedelta(days=2)],
        "nrs": [7.0, 7.0, 4.0],
    })
    recs = [{"StartTime": base + _dt.timedelta(minutes=1)},
            {"StartTime": base + _dt.timedelta(days=1, minutes=1)},
            {"StartTime": base + _dt.timedelta(days=2, minutes=1)}]
    sdf = adapter.align_pros(pro, target="session", recordings=recs, metrics=("nrs",),
                             match_tolerance_min=60.0)
    assert "matched_pro_time" in sdf.columns
    assert sdf["matched"].all(), sdf[["matched", "match_dt_min"]]
    ids = pd.to_datetime(sdf["matched_pro_time"])
    # the two 7.0 sessions matched DIFFERENT reports -> distinct identities
    assert ids.nunique() == 3, list(ids)
    assert sdf["nrs_min"].tolist() == [7.0, 7.0, 4.0]
    # the old value-matching would have produced only 2 groups (one per distinct value)
    assert sdf["nrs_min"].nunique() == 2


def test_align_pros_unmatched_session_has_no_identity():
    """An unmatched session must carry NaT, so factorize maps it to -1 (no group) rather than
    silently joining whichever group sorts first."""
    import datetime as _dt
    base = _dt.datetime(2026, 3, 1, 12, 0, 0)
    pro = pd.DataFrame({"date_time_s1_daily": [base], "nrs": [5.0]})
    recs = [{"StartTime": base + _dt.timedelta(minutes=1)},
            {"StartTime": base + _dt.timedelta(days=30)}]          # far outside tolerance
    sdf = adapter.align_pros(pro, target="session", recordings=recs, metrics=("nrs",),
                             match_tolerance_min=60.0)
    assert sdf["matched"].tolist() == [True, False]
    ids = pd.to_datetime(sdf["matched_pro_time"])
    assert pd.notna(ids.iloc[0]) and pd.isna(ids.iloc[1])
    codes, _ = pd.factorize(ids, use_na_sentinel=True)
    assert list(codes) == [0, -1], list(codes)


def test_align_pros_same_day_branch_groups_by_date():
    """On the legacy same-day path the 'rating' is the day's aggregate, so two sessions on one day
    genuinely share a rating and must share a group."""
    import datetime as _dt
    d = _dt.datetime(2026, 3, 1, 8, 0, 0)
    pro = pd.DataFrame({"date_time_s1_daily": [d, d + _dt.timedelta(hours=6)], "nrs": [6.0, 8.0]})
    recs = [{"StartTime": d + _dt.timedelta(hours=1)},
            {"StartTime": d + _dt.timedelta(hours=9)},
            {"StartTime": d + _dt.timedelta(days=5)}]
    sdf = adapter.align_pros(pro, target="session", recordings=recs, metrics=("nrs",))
    ids = pd.to_datetime(sdf["matched_pro_time"])
    codes, _ = pd.factorize(ids, use_na_sentinel=True)
    assert list(codes[:2]) == [0, 0], list(codes)     # same day -> one shared rating
    assert codes[2] == -1                              # no report that day -> ungrouped


# --- the pipeline half of the rating_group fix (was untested; gap recorded 2026-08-31) ----------
def test_rating_group_from_identity_gives_one_group_per_matched_report():
    """Distinct matched report -> distinct group, even when the pain SCORES are identical.

    This is the assertion the original fix was missing: its three tests all exercised align_pros,
    leaving pipeline's factorize step backed only by a live measurement.
    """
    sdf = pd.DataFrame({"matched_pro_time": pd.to_datetime(
        ["2026-03-01 12:00", "2026-03-02 12:00", "2026-03-02 12:00", "2026-03-03 12:00"])})
    labels = np.array([7.0, 7.0, 7.0, 7.0])          # every score identical on purpose
    g = pipeline.rating_group_from_identity(sdf, labels)
    assert len(set(g.tolist())) == 3, g              # three distinct reports
    assert g[1] == g[2] and g[0] != g[1] and g[3] not in (g[0], g[1])
    # the old value-matching would have produced ONE group here, since all four scores are equal
    assert len(set(g.tolist())) > 1


def test_rating_group_from_identity_excludes_unmatched_and_unusable():
    """NaT identity -> -1, and a non-finite label -> -1 even when a report was matched."""
    sdf = pd.DataFrame({"matched_pro_time": pd.to_datetime(
        ["2026-03-01 12:00", None, "2026-03-03 12:00", "2026-03-04 12:00"])})
    labels = np.array([5.0, 5.0, np.nan, 6.0])
    g = pipeline.rating_group_from_identity(sdf, labels)
    assert g[1] == -1, "no matched report must not get a group"
    assert g[2] == -1, "an unusable label must not occupy a group"
    assert g[0] >= 0 and g[3] >= 0 and g[0] != g[3]


def test_rating_group_from_identity_refuses_to_guess_on_a_shape_mismatch():
    """If the session/epoch alignment does not hold, leave the grouping UNSET. Falling back to
    value-matching would silently restore a grouping that clusters on the outcome."""
    sdf = pd.DataFrame({"matched_pro_time": pd.to_datetime(["2026-03-01 12:00"])})
    g = pipeline.rating_group_from_identity(sdf, np.array([5.0, 6.0, 7.0]))
    assert list(g) == [-1, -1, -1], g
    # and the same when the column is absent entirely
    g2 = pipeline.rating_group_from_identity(pd.DataFrame({"other": [1, 2]}), np.array([5.0, 6.0]))
    assert list(g2) == [-1, -1], g2


def test_rating_group_end_to_end_from_align_pros():
    """align_pros -> rating_group_from_identity: the two halves must compose, which is what the
    live 7 -> 72 measurement was standing in for."""
    import datetime as _dt
    base = _dt.datetime(2026, 3, 1, 12, 0, 0)
    pro = pd.DataFrame({
        "date_time_s1_daily": [base, base + _dt.timedelta(days=1), base + _dt.timedelta(days=2)],
        "nrs": [7.0, 7.0, 7.0],                       # all identical scores, three distinct reports
    })
    recs = [{"StartTime": base + _dt.timedelta(minutes=1)},
            {"StartTime": base + _dt.timedelta(days=1, minutes=1)},
            {"StartTime": base + _dt.timedelta(days=2, minutes=1)}]
    sdf = adapter.align_pros(pro, target="session", recordings=recs, metrics=("nrs",),
                             match_tolerance_min=60.0)
    g = pipeline.rating_group_from_identity(sdf, sdf["nrs_min"].to_numpy(dtype=float))
    assert len(set(g.tolist())) == 3, (list(g), sdf["nrs_min"].tolist())


# --- cluster-robust p for the correlation spectrum (audit C2, 2026-08-31) -----------------------
def test_cluster_robust_p_matches_statsmodels_cluster_covariance():
    """The sandwich is implemented in closed form (this runs per channel x frequency, hundreds of
    cells per request, so a statsmodels fit per cell is not affordable). That makes an equivalence
    test mandatory rather than optional: assert it reproduces statsmodels' cov_type='cluster'
    exactly, so the closed form can never silently drift from the reference implementation.
    """
    from modules.Biomarkers.routines import streaming_psd as sp
    import statsmodels.api as smapi
    from scipy.stats import t as _t

    rng = np.random.default_rng(11)
    G, per = 40, 4
    g = np.repeat(np.arange(G), per)
    u_g = rng.normal(0, 1.0, G)                       # cluster effect -> real within-cluster dependence
    x = rng.normal(0, 1, G * per) + np.repeat(u_g, per)
    y = 0.5 * x + np.repeat(u_g, per) + rng.normal(0, 1, G * per)

    corr, pval, extra = sp.pearson_corr_psd_label(x.reshape(-1, 1, 1), y, mad_k=0,
                                                  rating_group=g, return_extra=True)
    xz = (x - x.mean()) / x.std()
    yz = (y - y.mean()) / y.std()
    m = smapi.OLS(yz, smapi.add_constant(xz)).fit(cov_type="cluster",
                                                  cov_kwds={"groups": g}, use_t=True)
    assert abs(float(corr[0, 0]) - float(m.params[1])) < 1e-9
    assert abs(float(extra["se_cluster"][0, 0]) - float(m.bse[1])) < 1e-9, \
        (float(extra["se_cluster"][0, 0]), float(m.bse[1]))
    p_ref = float(2 * _t.sf(abs(float(m.params[1]) / float(m.bse[1])), df=G - 1))
    assert abs(float(pval[0, 0]) - p_ref) < 1e-12
    # and the whole point: clustering must WIDEN the interval relative to the naive fit
    se_naive = float(smapi.OLS(yz, smapi.add_constant(xz)).fit().bse[1])
    assert float(extra["se_cluster"][0, 0]) > se_naive


def test_cluster_robust_p_is_not_more_significant_than_naive_under_dependence():
    """With genuine within-cluster dependence the corrected p must be LARGER. If a refactor ever
    inverts this, the panel would be reporting pseudoreplication as extra confidence."""
    from modules.Biomarkers.routines import streaming_psd as sp
    rng = np.random.default_rng(3)
    g = np.repeat(np.arange(30), 5)
    u = rng.normal(0, 1.2, 30)
    x = rng.normal(0, 1, 150) + np.repeat(u, 5)
    y = 0.4 * x + np.repeat(u, 5) + rng.normal(0, 1, 150)
    _, pval, extra = sp.pearson_corr_psd_label(x.reshape(-1, 1, 1), y, mad_k=0,
                                               rating_group=g, return_extra=True)
    assert float(pval[0, 0]) >= float(extra["pval_naive"][0, 0])
    assert int(extra["n_clusters"][0, 0]) == 30


def test_omitting_rating_group_leaves_the_naive_behaviour_untouched():
    """Back-compat: existing callers that pass no grouping must get exactly the old p-value."""
    from modules.Biomarkers.routines import streaming_psd as sp
    rng = np.random.default_rng(7)
    x = rng.normal(0, 1, 60)
    y = 0.5 * x + rng.normal(0, 1, 60)
    _, p_no_g = sp.pearson_corr_psd_label(x.reshape(-1, 1, 1), y, mad_k=0)
    _, p2, extra = sp.pearson_corr_psd_label(x.reshape(-1, 1, 1), y, mad_k=0, return_extra=True)
    assert abs(float(p_no_g[0, 0]) - float(extra["pval_naive"][0, 0])) < 1e-15
    assert abs(float(p_no_g[0, 0]) - float(p2[0, 0])) < 1e-15
    assert "naive" in extra["method"]


def test_too_few_clusters_reports_nothing_rather_than_a_number():
    """Under 3 clusters a sandwich is meaningless; it must yield NaN, not a p-value someone reads."""
    from modules.Biomarkers.routines import streaming_psd as sp
    rng = np.random.default_rng(5)
    g = np.repeat(np.arange(2), 20)                    # only 2 clusters
    x = rng.normal(0, 1, 40)
    y = 0.6 * x + rng.normal(0, 1, 40)
    _, pval, extra = sp.pearson_corr_psd_label(x.reshape(-1, 1, 1), y, mad_k=0,
                                               rating_group=g, return_extra=True)
    assert not np.isfinite(float(pval[0, 0]))
    assert int(extra["n_clusters"][0, 0]) == 2
    assert np.isfinite(float(extra["pval_naive"][0, 0]))   # the naive contrast still computes


def test_ungrouped_epochs_are_excluded_from_the_cluster_p():
    """rating_group == -1 marks an epoch with no matched report; it must not form its own cluster."""
    from modules.Biomarkers.routines import streaming_psd as sp
    rng = np.random.default_rng(13)
    g = np.concatenate([np.repeat(np.arange(10), 4), np.full(8, -1)])
    x = rng.normal(0, 1, g.size)
    y = 0.5 * x + rng.normal(0, 1, g.size)
    _, _, extra = sp.pearson_corr_psd_label(x.reshape(-1, 1, 1), y, mad_k=0,
                                            rating_group=g, return_extra=True)
    assert int(extra["n_clusters"][0, 0]) == 10, extra["n_clusters"][0, 0]
