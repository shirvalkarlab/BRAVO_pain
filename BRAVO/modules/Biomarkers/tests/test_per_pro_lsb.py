"""CS-4: per-PRO LSB selection precedence + sliding-window overlay + saturation QC.

Pins the strict source precedence (native > direct TD transform > PSD bridge), the rating-centered
window contract reuse (transform_centered_window), the 50%-overlap sliding-window overlay, and the
saturation/missing QC. availability imports cleanly without Django, but we keep the Django shim for
parity with the other Biomarker tests (and in case analytics pulls settings transitively).
"""
import os
import sys
import pathlib
import numpy as np

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django
    django.setup()
except Exception:
    pass

from modules.Biomarkers.routines import availability as av
from modules.Biomarkers.routines import analytics


_FS = 250.0
_T0 = 1_700_000_000.0


def _td_rec(channel, start, secs=40.0, freq_hz=20.0, amp=2.0, seed=0, rail=None):
    n = int(secs * _FS)
    tt = np.arange(n) / _FS
    sig = amp * np.sin(2 * np.pi * freq_hz * tt) + 0.1 * np.random.default_rng(seed).standard_normal(n)
    if rail is not None:
        sig[rail[0]:rail[1]] = 5000.0
    return {"ChannelNames": [channel], "Data": sig.reshape(-1, 1),
            "SamplingRate": _FS, "StartTime": start}


def _event_block(channel, t, center=20.0):
    f = np.linspace(0.0, 96.68, 100)
    mag = np.zeros(100); mag[(f >= center - 2.5) & (f <= center + 2.5)] = 2.0
    return {"channel": channel, "t": t, "freq": list(f), "power": list(mag), "center_hz": center}


def test_precedence_native_beats_td_beats_bridge():
    """A PRO that could be served by ALL THREE tiers gets NATIVE; with native removed it gets TD;
    with TD also removed it gets the bridge. Strict precedence, no tier-skipping."""
    ch = "ZERO_THREE_LEFT"; center = 20.0
    td = _td_rec(ch, _T0, secs=40.0)                      # covers _T0.._T0+40
    native = {"t": [_T0 + 20.0], "y": [321.0], "center_hz": [20.0],
              "modeled": [False], "source": ["streaming"]}
    ev = _event_block(ch, _T0 + 20.0)
    pro = [_T0 + 20.0]
    # all three available -> native
    r = av.per_pro_lsb(pro, native, ch, center, td_recordings=[td], event_psd_recordings=[ev])[0]
    assert r["tier"] == av.PRO_LSB_TIER_NATIVE and abs(r["lsb"] - 321.0) < 1e-9
    # no native -> TD
    r = av.per_pro_lsb(pro, None, ch, center, td_recordings=[td], event_psd_recordings=[ev])[0]
    assert r["tier"] == av.PRO_LSB_TIER_TD and r["lsb"] > 0
    # no native, no TD -> bridge
    r = av.per_pro_lsb(pro, None, ch, center, td_recordings=[], event_psd_recordings=[ev])[0]
    assert r["tier"] == av.PRO_LSB_TIER_BRIDGE and r["lsb"] > 0


def test_montage_td_uses_transform_never_bridge():
    """A montage/survey-style TD recording (carries TD) serves the PRO via the DIRECT transform, even
    when a coincident PSD-only event also exists — the bridge is for PSD-only events alone."""
    ch = "ZERO_THREE_LEFT"; center = 20.0
    montage_td = _td_rec(ch, _T0, secs=40.0)
    ev = _event_block(ch, _T0 + 20.0)
    r = av.per_pro_lsb([_T0 + 20.0], None, ch, center,
                       td_recordings=[montage_td], event_psd_recordings=[ev])[0]
    assert r["tier"] == av.PRO_LSB_TIER_TD            # TD present -> transform, NOT bridge
    assert "352.62" in r["reason"]


def test_bridge_only_inside_deployable_band():
    """The PSD bridge tier is honored only for a center in [LSB_VALIDATED_HZ_LO, LSB_DEPLOYABLE_HZ_HI].
    A high-gamma center (55.5 Hz) with only an event source returns unmatched."""
    ch = "ZERO_THREE_LEFT"
    ev = _event_block(ch, _T0 + 5.0, center=55.5)
    r = av.per_pro_lsb([_T0 + 5.0], None, ch, 55.5, td_recordings=[], event_psd_recordings=[ev])[0]
    assert r["tier"] is None and r["lsb"] is None


def test_saturated_td_window_flagged_and_skipped():
    """A rating-centered TD window touching the ADC rail is flagged saturated and NOT converted (a
    clipped window's band power is unreliable); with no other source the PRO is unmatched."""
    ch = "ZERO_THREE_LEFT"; center = 20.0
    td = _td_rec(ch, _T0, secs=40.0, rail=(4900, 5100))   # rail near the window center
    r = av.per_pro_lsb([_T0 + 20.0], None, ch, center, td_recordings=[td])[0]
    assert r["saturated"] is True and r["lsb"] is None and r["tier"] is None


def test_unmatched_pro_returns_none_honestly():
    """A PRO with no native, no overlapping TD, no coincident event returns lsb=None/tier=None."""
    ch = "ZERO_THREE_LEFT"
    r = av.per_pro_lsb([_T0 + 99999.0], None, ch, 20.0, td_recordings=[], event_psd_recordings=[])[0]
    assert r["lsb"] is None and r["tier"] is None


def test_agg_none_returns_per_window_and_median_matches():
    """td_transform_band_power(agg='none') returns the per-window band power (W,) for a scalar center
    and (W,C) for a vector center; its median equals the agg='median' aggregate (same DSP, just
    un-aggregated)."""
    n = int(30 * _FS); tt = np.arange(n) / _FS
    sig = 2.0 * np.sin(2 * np.pi * 20 * tt) + 0.1 * np.random.default_rng(0).standard_normal(n)
    step = int(round(_FS * analytics.TRANSFORM_STEP_SECONDS))
    pw = analytics.td_transform_band_power(sig, _FS, 20.0, step_samples=step, agg="none")
    assert pw.ndim == 1 and pw.shape[0] in (59, 60)        # ~59 windows over 30 s at 50% overlap
    med_default = analytics.td_transform_band_power(sig, _FS, 20.0, step_samples=step)
    assert abs(float(np.median(pw)) - med_default) < 1e-9
    pwv = analytics.td_transform_band_power(sig, _FS, np.array([10., 20., 30.]),
                                            step_samples=step, agg="none")
    assert pwv.shape == (pw.shape[0], 3)
    # below-one-window trace -> empty per-window series, center axis preserved for vector centers
    assert analytics.td_transform_band_power(sig[:10], _FS, 20.0, agg="none").shape == (0,)
    assert analytics.td_transform_band_power(sig[:10], _FS, np.array([10., 20.]),
                                             agg="none").shape == (0, 2)


def test_overlay_sliding_window_trace_and_saturation_qc():
    """per_pro_lsb_overlay returns the 50%-overlap per-window LSB trace; its median equals the deployed
    single-value path, and per-window saturation QC flags railed windows with a surfaced reason."""
    n = int(30 * _FS); tt = np.arange(n) / _FS
    sig = 2.0 * np.sin(2 * np.pi * 20 * tt) + 0.1 * np.random.default_rng(0).standard_normal(n)
    ov = av.per_pro_lsb_overlay(sig, _FS, 15.0, 20.0)
    assert ov["ok"] and ov["n_windows"] in (59, 60)
    assert ov["median_lsb"] is not None and ov["median_lsb"] > 0
    assert len(ov["t_offset_s"]) == ov["n_windows"] == len(ov["lsb"])
    # the overlay median equals the deployed per-PRO single value (same DSP/window geometry)
    step = int(round(_FS * analytics.TRANSFORM_STEP_SECONDS))
    single = analytics.td_to_lsb(sig, _FS, 20.0, step_samples=step)
    assert abs(ov["median_lsb"] - single) / single < 1e-9
    # saturation QC
    sigsat = sig.copy(); sigsat[3000:3050] = 5000.0
    ovs = av.per_pro_lsb_overlay(sigsat, _FS, 15.0, 20.0)
    assert ovs["n_saturated"] > 0 and ovs["saturated"] and "saturated" in ovs["reason"]


def test_overlay_short_extent_not_ok():
    """An extent below one transform window returns ok=False (no windows), not a spurious LSB."""
    sig = np.random.default_rng(0).standard_normal(50)    # 0.2 s @ 250 Hz < 1 s window
    ov = av.per_pro_lsb_overlay(sig, _FS, 0.1, 20.0)
    assert ov["ok"] is False and ov["n_windows"] == 0 and ov["median_lsb"] is None
