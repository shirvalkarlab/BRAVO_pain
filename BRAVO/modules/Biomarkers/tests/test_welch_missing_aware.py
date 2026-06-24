"""Tests for Missing-aware TD Welch rejection (fix A: FixBreaking zero-fill must not bias the PSD)."""
import numpy as np
from modules.Biomarkers.routines import streaming_psd as sp


def _sine(n, fs, hz, amp=10.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / fs
    return amp * np.sin(2 * np.pi * hz * t) + 0.5 * rng.standard_normal(n)


def test_first_window_rejected_when_mostly_missing():
    """welch_psd_for_instance returns all-NaN when the first window exceeds the missing-frac floor."""
    fs = 250.0
    n = int(30 * fs)
    sig = np.vstack([_sine(n, fs, 20.0)])  # (1, n)
    names = ["ZERO_TWO_LEFT"]
    # No missing -> finite PSD.
    psd_clean = sp.welch_psd_for_instance(sig, names, fs, names, missing=np.zeros(n))
    assert np.isfinite(psd_clean).any()
    # 50% missing -> rejected (all NaN).
    miss = np.zeros(n); miss[: n // 2] = 1
    psd_bad = sp.welch_psd_for_instance(sig, names, fs, names, missing=miss)
    assert not np.isfinite(psd_bad).any()


def test_first_window_kept_when_missing_below_threshold():
    fs = 250.0
    n = int(30 * fs)
    sig = np.vstack([_sine(n, fs, 20.0)])
    names = ["ZERO_TWO_LEFT"]
    miss = np.zeros(n); miss[: int(0.05 * n)] = 1  # 5% < 10% floor
    psd = sp.welch_psd_for_instance(sig, names, fs, names, missing=miss)
    assert np.isfinite(psd).any()


def test_centered_window_dropped_over_gap():
    """A rating-centered window dominated by a zero-fill gap is dropped from kept_mask."""
    fs = 250.0
    n = int(120 * fs)
    sig = np.vstack([_sine(n, fs, 18.0)])
    names = ["ZERO_TWO_LEFT"]
    # Two PROs: one over clean data (t=20s), one centered on a 25 s zero-fill gap (t=60s).
    gap_lo, gap_hi = int(47.5 * fs), int(72.5 * fs)
    miss = np.zeros(n); miss[gap_lo:gap_hi] = 1
    sig[:, gap_lo:gap_hi] = 0.0
    centers = np.array([20.0, 60.0])
    psd, used, kept = sp.welch_rating_centered(sig, names, fs, names, centers, missing=miss)
    assert kept[0] == True   # clean window kept
    assert kept[1] == False  # gap-dominated window dropped
    assert psd.shape[0] == 1


def test_centered_no_mask_is_legacy():
    """Passing missing=None reproduces the pre-fix behavior (both windows kept)."""
    fs = 250.0
    n = int(120 * fs)
    sig = np.vstack([_sine(n, fs, 18.0)])
    names = ["ZERO_TWO_LEFT"]
    centers = np.array([20.0, 60.0])
    psd, used, kept = sp.welch_rating_centered(sig, names, fs, names, centers, missing=None)
    assert kept.all()
    assert psd.shape[0] == 2


def test_indefinitestream_shape_6ch_centered():
    """IndefiniteStream carries a 2-D (n_samples, n_ch) Missing array and routes through the SAME
    centered Welch path as BrainSenseTimeDomain. A 6-channel recording with a localized gap must drop
    only the gap-overlapping rating window, not a clean one in the same recording."""
    from modules.Biomarkers.bravo_service import _missing_time_vector
    fs = 250.0
    n = int(180 * fs)
    chans = ["ZERO_THREE_LEFT", "ONE_THREE_LEFT", "ZERO_TWO_LEFT",
             "ZERO_THREE_RIGHT", "ONE_THREE_RIGHT", "ZERO_TWO_RIGHT"]
    sig = np.vstack([_sine(n, fs, 18.0, seed=i) for i in range(len(chans))])  # (6, n)
    # 2-D Missing in (n_samples, n_ch) layout, like the decoder stores for IndefiniteStream.
    miss2d = np.zeros((n, len(chans)))
    gap_lo, gap_hi = int(57 * fs), int(63 * fs)   # 6 s gap around t=60 s -> ~20% of a 30 s window
    miss2d[gap_lo:gap_hi, :] = 1
    sig[:, gap_lo:gap_hi] = 0.0
    mvec = _missing_time_vector(miss2d, n)        # collapse to per-sample
    assert mvec is not None and mvec.shape[0] == n
    centers = np.array([20.0, 60.0])              # clean, gap-centered
    psd, used, kept = sp.welch_rating_centered(sig, chans, fs, chans, centers, missing=mvec)
    assert kept[0] == True   # clean window kept
    assert kept[1] == False  # gap window dropped


def test_missing_threshold_boundary():
    """Exactly at the threshold is kept; just above is rejected."""
    fs = 250.0
    n = int(30 * fs)
    sig = np.vstack([_sine(n, fs, 20.0)])
    names = ["ZERO_TWO_LEFT"]
    at = np.zeros(n); at[: int(sp.WELCH_MAX_MISSING_FRAC * n)] = 1  # == floor -> kept (>, not >=)
    assert np.isfinite(sp.welch_psd_for_instance(sig, names, fs, names, missing=at)).any()
    over = np.zeros(n); over[: int(sp.WELCH_MAX_MISSING_FRAC * n) + int(0.02 * n)] = 1
    assert not np.isfinite(sp.welch_psd_for_instance(sig, names, fs, names, missing=over)).any()
