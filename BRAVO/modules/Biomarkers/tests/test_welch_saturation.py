"""The 30 s Welch route drops a window with a sample at the recording rail, as the 3 s route does
(the PI, 2026-10-18, item 6d). The heat maps' 3 s pieces have long refused a piece with any finite
sample at or above 4,000 microvolts (`availability.PRO_LSB_SATURATION_UV`); the all-band scan's
30 s Welch windows (the session's first 30 s, or 30 s centred on a rating) had no such check, so
a saturated stretch entered the scan as a spectrum. Same rule, same number, applied to the window
actually Welch'd. Plain asserts: container suite.
"""
import numpy as np

from modules.Biomarkers.routines import streaming_psd as sp
from modules.Biomarkers.routines import availability as av

FS = 250.0


def _sig(n, n_ch=2, seed=4):
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 20.0, (n_ch, n))


def test_the_limit_is_the_3_s_routes_own():
    assert sp.WELCH_SATURATION_UV == av.PRO_LSB_SATURATION_UV == 4000.0


def test_first_window_with_a_railed_sample_is_dropped_on_that_channel_only():
    """Per channel, as the 3 s route judges each channel's own piece: the other channel's
    spectrum of the same 30 s is unchanged."""
    x = _sig(int(60 * FS))
    clean = sp.welch_psd_for_instance(x, ["A", "B"], FS, ["A", "B"])
    assert np.isfinite(clean).all()
    y = x.copy(); y[1, int(10 * FS)] = -4000.0            # one sample at the rail, inside the first 30 s
    got = sp.welch_psd_for_instance(y, ["A", "B"], FS, ["A", "B"])
    assert np.isnan(got[0, 1]).all() and np.array_equal(got[0, 0], clean[0, 0])
    z = x.copy(); z[0, int(45 * FS)] = 9000.0             # after the first 30 s: not in the window
    assert np.array_equal(sp.welch_psd_for_instance(z, ["A", "B"], FS, ["A", "B"]), clean)
    w = x.copy(); w[0, int(5 * FS)] = 3999.0               # below the limit: kept
    assert np.isfinite(sp.welch_psd_for_instance(w, ["A", "B"], FS, ["A", "B"])).all()


def test_a_nan_sample_is_not_read_as_saturated():
    x = _sig(int(40 * FS)); x[0, 100] = np.nan
    got = sp.welch_psd_for_instance(x, ["A", "B"], FS, ["A", "B"])
    want = sp.welch_psd_for_instance(x, ["A", "B"], FS, ["A", "B"], saturation_uv=np.inf)
    assert np.array_equal(got, want, equal_nan=True)


def test_rating_centred_windows_with_a_railed_sample_are_dropped_one_by_one():
    x = _sig(int(300 * FS))
    x[0, int(100 * FS)] = 4200.0                         # inside the window centred on 100 s only
    psd, used, kept = sp.welch_rating_centered(x, ["A", "B"], FS, ["A", "B"], [50.0, 100.0, 200.0])
    ref, _, _ = sp.welch_rating_centered(x, ["A", "B"], FS, ["A", "B"], [50.0, 100.0, 200.0],
                                         saturation_uv=np.inf)
    assert kept.tolist() == [True, True, True], kept      # channel B of that window is clean
    assert np.isnan(psd[1, 0]).all() and np.array_equal(psd[1, 1], ref[1, 1])
    assert np.array_equal(psd[[0, 2]], ref[[0, 2]])
    x[1, int(100 * FS) + 5] = 5000.0                     # now both channels: the window goes
    psd2, _, kept2 = sp.welch_rating_centered(x, ["A", "B"], FS, ["A", "B"], [50.0, 100.0, 200.0])
    assert kept2.tolist() == [True, False, True], kept2
    assert np.array_equal(psd2, ref[[0, 2]])


def test_with_no_railed_sample_nothing_changes():
    x = _sig(int(120 * FS), seed=9)
    a = sp.welch_rating_centered(x, ["A", "B"], FS, ["A", "B"], [10.0, 60.0, 115.0])
    b = sp.welch_rating_centered(x, ["A", "B"], FS, ["A", "B"], [10.0, 60.0, 115.0], saturation_uv=np.inf)
    assert all(np.array_equal(p, q) for p, q in zip(a, b))


def test_the_rule_is_in_every_spectrum_cache_key():
    """Spectra Welch'd before the rule are not served: the per-recording files' names and the
    assembled matrix's key carry it."""
    from modules.Biomarkers import bravo_service as B
    assert B._TD_SATURATION_VERSION == "sat4000uv"
    assert B._TD_SATURATION_VERSION in B._recording_psd_cache_path("uid", "hash")
    assert B._TD_SATURATION_VERSION in B._recording_psd_cache_path("uid", "hash", pro_sig="abc123abc123")
    assert B._PSD_ROWS_BARE.endswith(B._TD_SATURATION_VERSION)
