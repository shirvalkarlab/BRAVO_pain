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


# ---- CS-4 review fixes (request_changes -> resolved) ----

def test_overlay_trace_axes_stay_aligned_under_nonfinite_samples():
    """BLOCKING fix: a gappy TD slice (some NaN samples, still <10% so the window passes) must keep
    t_offset_s, lsb, and the saturation flags on ONE window axis. The band power is computed over the
    finite-filtered slice, so the trace x and QC must be derived from that same vector — not the
    NaN-inclusive length (which used to give 59 vs 58)."""
    n = int(30 * _FS); tt = np.arange(n) / _FS
    sig = 2.0 * np.sin(2 * np.pi * 20 * tt) + 0.1 * np.random.default_rng(1).standard_normal(n)
    sig[1000:1010] = np.nan                                # 10 NaN of 7500 (<<10%, passes missing gate)
    ov = av.per_pro_lsb_overlay(sig, _FS, 15.0, 20.0)
    assert ov["ok"]
    assert len(ov["t_offset_s"]) == len(ov["lsb"]) == ov["n_windows"]   # the alignment guarantee
    assert ov["median_lsb"] is not None and ov["median_lsb"] > 0


def test_native_tier_fails_closed_on_misaligned_modeled_mask():
    """IMPORTANT fix: if the native series' `modeled` array is missing or length-misaligned, the native
    tier must NOT promote a modeled estimate to tier='native'. It fails CLOSED (every point treated as
    modeled), so a lower tier serves the PRO instead."""
    ch = "ZERO_THREE_LEFT"; center = 20.0
    td = _td_rec(ch, _T0, secs=40.0)
    # a series whose `modeled` is misaligned (len 1 vs y len 1 is aligned; force mismatch with len 0)
    bad_native = {"t": [_T0 + 20.0], "y": [999.0], "center_hz": [20.0], "modeled": [],
                  "source": ["modeled"]}
    r = av.per_pro_lsb([_T0 + 20.0], bad_native, ch, center, td_recordings=[td])[0]
    assert r["tier"] != av.PRO_LSB_TIER_NATIVE       # never selected the modeled 999 as native
    assert r["tier"] == av.PRO_LSB_TIER_TD           # fell through to the real TD transform
    # absent `modeled` key entirely -> also fail closed
    bad2 = {"t": [_T0 + 20.0], "y": [999.0], "center_hz": [20.0]}
    r2 = av.per_pro_lsb([_T0 + 20.0], bad2, ch, center, td_recordings=[td])[0]
    assert r2["tier"] == av.PRO_LSB_TIER_TD


def test_saturated_flag_does_not_leak_across_recordings():
    """IMPORTANT fix: a PRO cleanly served by recording #2 must NOT report saturated=True because an
    earlier overlapping recording #1 had a railed window. The clean conversion resets the flag."""
    ch = "ZERO_THREE_LEFT"; center = 20.0
    railed = _td_rec(ch, _T0, secs=40.0, rail=(4900, 5100))   # overlaps the PRO, saturated
    clean = _td_rec(ch, _T0, secs=40.0, seed=7)               # overlaps the PRO, clean
    r = av.per_pro_lsb([_T0 + 20.0], None, ch, center, td_recordings=[railed, clean])[0]
    assert r["tier"] == av.PRO_LSB_TIER_TD and r["lsb"] > 0
    assert r["saturated"] is False                            # not leaked from recording #1


def test_tier2_recording_order_invariant_after_searchsorted_prep():
    """PERF refactor guard: per_pro_lsb prepares TD recordings once and uses searchsorted over t0-sorted
    recordings. The result must be invariant to the INPUT order of td_recordings (the prep sorts by t0),
    and a PRO must still match the recording that actually covers it."""
    ch = "ZERO_THREE_LEFT"; center = 20.0
    early = _td_rec(ch, _T0, secs=40.0, seed=1)            # covers _T0.._T0+40
    late = _td_rec(ch, _T0 + 1000.0, secs=40.0, seed=2)    # covers _T0+1000.._T0+1040
    pros = [_T0 + 20.0, _T0 + 1020.0]
    r_fwd = av.per_pro_lsb(pros, None, ch, center, td_recordings=[early, late])
    r_rev = av.per_pro_lsb(pros, None, ch, center, td_recordings=[late, early])
    assert [x["tier"] for x in r_fwd] == [x["tier"] for x in r_rev] == ["td_transform", "td_transform"]
    # identical LSB regardless of input order (same recording covers each PRO)
    assert all(abs(a["lsb"] - b["lsb"]) < 1e-9 for a, b in zip(r_fwd, r_rev))
    # a PRO between the two recordings (covered by neither) is honestly None
    r_gap = av.per_pro_lsb([_T0 + 500.0], None, ch, center, td_recordings=[early, late])[0]
    assert r_gap["tier"] is None


def test_wiring_pro_lsb_by_channel_builds_per_channel_series():
    """The bravo_service wiring helper _pro_lsb_by_channel runs per_pro_lsb for every channel that has
    a resolvable sensing center, keyed by raw channel, and resolves the center from
    sensing_hz_by_channel (canonical key) with a fallback to the channel's own series center_hz."""
    from modules.Biomarkers import bravo_service as bs
    ch = "ZERO_THREE_LEFT"
    td = _td_rec(ch, _T0, secs=40.0)
    # an inline lsb_series-shaped dict keyed by raw channel; one NATIVE sensed sample near a PRO
    lsb = {ch: {"t": [_T0 + 5000.0], "y": [321.0], "center_hz": [20.0],
                "source": ["streaming"], "modeled": [False], "method": [None]}}
    pro_times = np.array([_T0 + 20.0, _T0 + 5000.0])      # one TD-overlap, one native
    out = bs._pro_lsb_by_channel(pro_times, lsb, [td], [], {ch: 20.0})
    assert ch in out and len(out[ch]) == 2
    tiers = [r["tier"] for r in out[ch]]
    assert av.PRO_LSB_TIER_TD in tiers and av.PRO_LSB_TIER_NATIVE in tiers
    # center fallback: no sensing map -> use the series' own center_hz
    out2 = bs._pro_lsb_by_channel(pro_times, lsb, [td], [], {})
    assert ch in out2 and out2[ch][1]["center_hz"] == 20.0
    # channel with no resolvable center -> dropped
    lsb_noc = {ch: {"t": [], "y": [], "center_hz": [], "source": [], "modeled": [], "method": []}}
    out3 = bs._pro_lsb_by_channel(pro_times, lsb_noc, [td], [], {})
    assert ch not in out3
    # no PROs -> empty dict (and a numpy-array pro_times must not raise on the truth-value guard)
    assert bs._pro_lsb_by_channel(np.array([]), lsb, [td], [], {ch: 20.0}) == {}


def test_channel_canonicalized_across_all_tiers():
    """IMPORTANT fix: a ring-named `channel` argument is canonicalized at entry, so a ring-named TD
    recording and a ring-named event both match (tier 2 already canonicalized recording names; tiers
    1/3 now compare in canonical form too)."""
    ring = "ZERO_AND_THREE_LEFT_RING"
    canon = av._canon_channel(ring)
    td = _td_rec(ring, _T0, secs=40.0)                        # raw ring-named recording
    r = av.per_pro_lsb([_T0 + 20.0], None, ring, 20.0, td_recordings=[td])[0]
    assert r["tier"] == av.PRO_LSB_TIER_TD and r["center_hz"] == 20.0
    # ring-named event matches a ring-named channel arg via canonicalization on both sides
    ev = _event_block(ring, _T0 + 5.0)
    r2 = av.per_pro_lsb([_T0 + 5.0], None, canon, 20.0, td_recordings=[], event_psd_recordings=[ev])[0]
    assert r2["tier"] == av.PRO_LSB_TIER_BRIDGE


# --- live_lsb_spectrum_match: window-reuse toggle + per-modality independence --------------------

def _raw_cache_fixture(centers):
    """Minimal raw_lsb_spectrum_cache-shaped dict: one TD window at t=1000, three PSD windows.
    PRO geometry (set by the test): PRO0=1000 (TD-tier), PRO1=1100, PRO2=5000."""
    nC = len(centers)
    rowv = lambda v: [float(v)] * nC
    return {
        "td":  {"t": [1000.0], "ok": [True], "lsb": [rowv(300.0)],
                "saturated": [False], "source": ["BrainSense streaming"]},
        "psd": {"t": [1005.0, 1100.0, 5000.0],
                "lsb": [rowv(280.0), rowv(290.0), rowv(310.0)],
                "calibrated": [[True] * nC] * 3,
                "source": ["Montage PSD", "Montage PSD", "PSD event"]},
        "window_s": 3.0, "n_td_windows": 1, "n_psd_windows": 3,
        "centers_hz": list(centers), "band_half_hz": 2.5, "channel": "ZERO_THREE_LEFT",
    }


def test_live_match_strict_no_reuse_default():
    """STRICT (default): each window -> nearest PRO only. PRO0 owns the TD window (TD-tier); the
    co-timestamped 1005 montage-PSD therefore stays unused (TD preferred). PRO1/PRO2 each take one
    PSD. No window+modality serves >1 PRO."""
    centers = np.arange(8.0, 31.0, 1.0)
    raw = _raw_cache_fixture(centers)
    pro = np.array([1000.0, 1100.0, 5000.0])
    recs, st = av.live_lsb_spectrum_match(pro, raw, extent_s=30.0)
    assert st["allow_window_reuse"] is False
    assert recs[0]["tier"] == av.PRO_LSB_TIER_TD and recs[0]["n_td_used"] == 1
    assert recs[1]["tier"] == av.PRO_LSB_TIER_BRIDGE and recs[1]["n_psd_used"] == 1
    assert recs[2]["tier"] == av.PRO_LSB_TIER_BRIDGE and recs[2]["n_psd_used"] == 1
    # 1005 montage-PSD is within PRO0's extent but PRO0 is TD-tier -> only 2 PSD windows used, no reuse
    assert st["n_td_used"] == 1 and st["n_psd_used"] == 2


def test_live_match_reuse_toggle_increases_usage():
    """REUSE (two-window API): a PSD event matches EVERY PSD-tier PRO whose ELIGIBILITY window (tol_s,
    the main slider) covers it. Fixture: one PSD event at t=0 sits 100 s from PRO_a(-100) and 100 s
    from PRO_b(+100); with tol_s=200 BOTH claim it under reuse (n_psd_used 1->2), under strict it goes
    to its single nearest PRO only."""
    centers = np.arange(8.0, 31.0, 1.0)
    nC = len(centers); rowv = lambda v: [float(v)] * nC
    raw = {
        "td":  {"t": [], "ok": [], "lsb": [], "saturated": [], "source": []},
        "psd": {"t": [0.0], "lsb": [rowv(280.0)], "calibrated": [[True] * nC], "source": ["PSD event"]},
        "window_s": 3.0, "n_td_windows": 0, "n_psd_windows": 1,
        "centers_hz": list(centers), "band_half_hz": 2.5, "channel": "ZERO_THREE_LEFT",
    }
    pro = np.array([-100.0, 100.0])
    _, st_strict = av.live_lsb_spectrum_match(pro, raw, tol_s=200.0, td_quantity_s=30.0,
                                              allow_window_reuse=False)
    _, st_reuse = av.live_lsb_spectrum_match(pro, raw, tol_s=200.0, td_quantity_s=30.0,
                                             allow_window_reuse=True)
    assert st_reuse["allow_window_reuse"] is True
    assert st_strict["n_psd_used"] == 1                 # one PRO claims the single event
    assert st_reuse["n_psd_used"] == 2                  # both eligible PROs reuse it


def test_live_match_td_quantity_caps_nearest_n_tiles():
    """PI 2026-06-28 two-window split: td_quantity_s dictates HOW MANY of the nearest 3 s TD tiles to
    median (not a +/- tolerance), while tol_s is the eligibility radius. A smaller quantity slider uses
    FEWER tiles, and they must be the ones CLOSEST to the rating."""
    centers = np.array([10.0, 20.0, 30.0])
    td_t = list(np.arange(-300.0, 301.0, 3.0))           # 201 tiles, 3 s spacing, symmetric about 0
    td_lsb = [[100.0 + abs(t) / 10.0, 200.0, 300.0] for t in td_t]   # band-0 grows with |t|
    raw = {
        "td": {"t": td_t, "ok": [True] * len(td_t), "lsb": td_lsb,
               "saturated": [False] * len(td_t), "source": ["streaming"] * len(td_t)},
        "psd": {"t": [], "lsb": [], "calibrated": [], "source": []},
        "window_s": 3.0, "n_td_windows": len(td_t), "n_psd_windows": 0,
        "centers_hz": list(centers), "band_half_hz": 2.5, "channel": "ZERO_THREE_LEFT",
    }
    pro = np.array([0.0])
    r30, s30 = av.live_lsb_spectrum_match(pro, raw, tol_s=7200.0, td_quantity_s=30.0)
    r60, s60 = av.live_lsb_spectrum_match(pro, raw, tol_s=7200.0, td_quantity_s=60.0)
    assert s30["td_n_epochs_cap"] == 10 and r30[0]["n_td_used"] == 10   # 30 s / 3 s = nearest 10
    assert s60["td_n_epochs_cap"] == 20 and r60[0]["n_td_used"] == 20   # 60 s / 3 s = nearest 20
    assert r30[0]["lsb"][0] < r60[0]["lsb"][0]            # nearest-10 closer to 0 -> lower band-0
    rT, _ = av.live_lsb_spectrum_match(pro, raw, tol_s=60.0, td_quantity_s=30.0)
    assert rT[0]["n_td_used"] == 10                       # tol does NOT cap quantity


def test_live_match_per_modality_independence():
    """The per-modality non-reuse rule (independent of the reuse toggle): a montage snapshot's TD tile
    and its co-timestamped device-PSD window may serve TWO DIFFERENT PROs, because TD and PSD are
    matched in separate passes. Here PRO0 takes the TD modality (td_transform) and PRO1 takes a PSD
    modality (psd_bridge) — different PROs, different tiers."""
    centers = np.arange(8.0, 31.0, 1.0)
    raw = _raw_cache_fixture(centers)
    pro = np.array([1000.0, 1100.0, 5000.0])
    recs, _ = av.live_lsb_spectrum_match(pro, raw, extent_s=30.0)
    assert recs[0]["tier"] == av.PRO_LSB_TIER_TD
    assert recs[1]["tier"] == av.PRO_LSB_TIER_BRIDGE
    assert recs[0]["tier"] != recs[1]["tier"]


def test_raw_cache_folds_montage_psd_windows():
    """Montage device-PSD recordings fold into the cache PSD family (source-tagged), ON TOP of any
    patient-event PSDs — the coverage fix. A montage block {channel,t,freq,power,source} adds one PSD
    window with a finite LSB in the calibrated band."""
    centers = np.arange(8.0, 31.0, 1.0)
    ch = "ZERO_THREE_LEFT"
    f = np.linspace(0.0, 96.68, 100)
    mag = np.zeros(100); mag[(f >= 17.5) & (f <= 22.5)] = 2.0
    montage = [{"channel": ch, "t": _T0, "freq": list(f), "power": list(mag), "source": "Montage PSD"}]
    c_no = av.raw_lsb_spectrum_cache(ch, centers, td_recordings=[], event_psd_recordings=[])
    c_yes = av.raw_lsb_spectrum_cache(ch, centers, td_recordings=[], event_psd_recordings=[],
                                      montage_psd_recordings=montage)
    assert c_yes["n_psd_windows"] == c_no["n_psd_windows"] + 1
    assert "Montage PSD" in c_yes["psd"]["source"]
    # the added window carries a finite LSB somewhere in the calibrated band
    added = c_yes["psd"]["lsb"][-1]
    assert any(v is not None for v in added)
