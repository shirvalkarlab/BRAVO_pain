"""Regression tests for welch_rating_centered — the rating-centered TD-streaming Welch.

Motivation: the legacy `welch_psd_for_instance` Welch's only the FIRST 30 s of each streaming
session and stamps the PSD at the session START, so a rating in the middle of a long IndefiniteStream
reads "no neural match" despite full time-domain coverage. `welch_rating_centered` cuts a window
CENTERED on each rating inside [t0, t0+dur], clipped to the session boundary, dropping windows below
WELCH_CENTERED_MIN_SECONDS. These tests pin: exact centering vs the single-window reference, the
asymmetric edge-clip (the "15 s before / 5 s after" case), the min-duration floor, empty input, and
that a full-length centered window equals the legacy first-window when the rating sits at the start.
"""
import os, sys
if "DJANGO_SETTINGS_MODULE" not in os.environ:
    os.environ["DJANGO_SETTINGS_MODULE"] = "BRAVO.settings"
if "BRAVO" not in [p.split("/")[-1] for p in sys.path]:
    sys.path.insert(0, "/usr/src/BRAVO")
try:
    import django
    if not django.apps.apps.ready:
        django.setup()
except Exception:
    pass

import numpy as np
from scipy.signal import welch, butter, filtfilt
from modules.Biomarkers.routines import streaming_psd as sp

FS = 250.0


def _make_sig(n, n_ch=2, seed=11):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / FS
    return np.vstack([np.cumsum(rng.standard_normal(n)) * 0.02
                      + 1.5 * np.sin(2 * np.pi * 20 * t)
                      + 0.5 * rng.standard_normal(n) for _ in range(n_ch)])


def _ref_single_window(seg):
    """The reference single-window Welch (same DSP as welch_psd_for_instance), on a clipped span."""
    b, a = butter(4, 1 / (FS / 2), btype="high")
    seg = filtfilt(b, a, np.atleast_2d(seg), axis=-1)
    nper = min(1024, seg.shape[-1])
    f, P = welch(seg, fs=FS, nperseg=max(nper, 8), axis=-1)
    return np.stack([np.interp(sp.F_SET, f, P[c]) for c in range(P.shape[0])])


def test_centered_full_window_matches_reference():
    """A rating mid-session yields a full 30 s window equal to the reference single-window Welch."""
    sig = _make_sig(int(120 * FS))
    names = ["A", "B"]
    psd, used, kept = sp.welch_rating_centered(sig, names, FS, names, [60.0])
    assert kept.tolist() == [True]
    assert abs(used[0] - 30.0) < 1e-6
    half = int(round(sp.WELCH_MAX_SECONDS * FS / 2))
    ci = int(round(60.0 * FS))
    ref = _ref_single_window(sig[:, ci - half:ci + half])
    assert np.max(np.abs(psd[0] - ref)) < 1e-6


def test_asymmetric_edge_clip_uses_all_available():
    """Rating 5 s before session end -> [rating-15, rating+5] = 20 s window, not slid to 30 s."""
    sig = _make_sig(int(120 * FS))
    names = ["A", "B"]
    # rating at 115 s in a 120 s session: 15 s before, 5 s after -> 20 s
    psd, used, kept = sp.welch_rating_centered(sig, names, FS, names, [115.0])
    assert kept.tolist() == [True]
    assert abs(used[0] - 20.0) < 1e-6
    ci = int(round(115.0 * FS))
    half = int(round(sp.WELCH_MAX_SECONDS * FS / 2))
    lo, hi = max(ci - half, 0), min(ci + half, sig.shape[-1])
    ref = _ref_single_window(sig[:, lo:hi])
    assert np.max(np.abs(psd[0] - ref)) < 1e-6


def test_min_duration_floor_drops_short_windows():
    """A session too short to give >= WELCH_CENTERED_MIN_SECONDS of coverage emits no PSD."""
    short = _make_sig(int(8 * FS))   # 8 s < 10 s floor
    names = ["A", "B"]
    psd, used, kept = sp.welch_rating_centered(short, names, FS, names, [4.0])
    assert kept.tolist() == [False]
    assert psd.shape[0] == 0 and used.shape[0] == 0


def test_empty_centers_returns_empty():
    sig = _make_sig(int(60 * FS))
    names = ["A", "B"]
    psd, used, kept = sp.welch_rating_centered(sig, names, FS, names, [])
    assert psd.shape == (0, 2, len(sp.F_SET))
    assert used.shape == (0,) and kept.shape == (0,)


def test_multiple_ratings_one_call():
    """Several ratings in one session each get their own centered PSD, kept-mask aligns to input."""
    sig = _make_sig(int(200 * FS))
    names = ["A", "B"]
    centers = [10.0, 100.0, 195.0]   # start-edge(clipped), full, end-edge(clipped)
    psd, used, kept = sp.welch_rating_centered(sig, names, FS, names, centers)
    assert kept.tolist() == [True, True, True]
    assert psd.shape == (3, 2, len(sp.F_SET))
    # mid rating is full length; the two edges are shorter
    assert abs(used[1] - 30.0) < 1e-6
    assert used[0] < 30.0 and used[2] < 30.0


def test_no_overlapping_rating_keeps_session_matchable_via_caller_fallback():
    """A short session with NO rating inside its coverage must yield an empty kept-mask (so the
    CALLER falls back to a session-start PSD). This is the contract behind the `_welch_rows_into`
    fall-back that restores tolerance-matching for short TD sessions — without it, every short-session
    TD lane greys out and the matched pool is undercounted (the "no neural match" regression)."""
    sig = _make_sig(int(30 * FS))     # 30 s session
    names = ["A", "B"]
    # the only rating is far outside [t0, t0+30 s] coverage (centers measured from t0)
    psd, used, kept = sp.welch_rating_centered(sig, names, FS, names, [5000.0])
    assert kept.tolist() == [False]
    assert psd.shape[0] == 0          # caller sees zero kept -> emits the first-window PSD instead


def test_partial_floor_drop_keeps_only_surviving_ratings():
    """When several ratings overlap and some fall below the floor, only the surviving ones produce a
    PSD; the kept-mask marks exactly those, so the caller emits centered rows for them and does NOT
    additionally fall back (the fall-back fires only when ZERO ratings survive)."""
    sig = _make_sig(int(60 * FS))
    names = ["A", "B"]
    # 30 s (full, kept), and 0.2 s from the start edge -> clipped window ~15.2 s (>=10 s floor, kept)
    psd, used, kept = sp.welch_rating_centered(sig, names, FS, names, [30.0, 0.2])
    assert kept.tolist() == [True, True]
    assert psd.shape[0] == 2


def test_channel_slotting_respects_chan_order():
    """Output rows are placed at chan_order.index(name), zeros for channels not present."""
    sig = _make_sig(int(60 * FS), n_ch=2)
    names = ["B", "A"]                 # raw order
    chan_order = ["A", "B", "C"]       # global order with an extra channel C
    psd, used, kept = sp.welch_rating_centered(sig, names, FS, chan_order, [30.0])
    assert psd.shape == (1, 3, len(sp.F_SET))
    # row for C (index 2) is all zeros (no data); A and B are populated
    assert np.allclose(psd[0, 2, :], 0.0)
    assert psd[0, 0, :].any() and psd[0, 1, :].any()
