"""The live tile-cache matcher (`live_lsb_spectrum_match`) and the raw tile cache builder: window
reuse off by default, the reuse toggle, the time-domain quantity cap, montage spectra folded into
the cache. The per-report reader (`per_pro_lsb`) that shared this file was deleted on 2026-09-21
at the PI's direction (decision 224): nothing on any page read its answer.
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


_T0 = 1_700_000_000.0


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
