"""Decision 202 (the PI, 2026-09-19): log power is used in no calculation. Two Closed-Loop places
still took it: the per-run amplitude-effect table's slope (decision 40, `slope_log_per_mA`, which
Stim Optimizer reads for "did any run show movement"), and the joined table's two log columns
(`power_log_of_linear`, `power_mean_of_log`, decision 45) with the mean-of-log ranking diagnostic
-- computed on every request and read by nothing, since rule D11 fixes the scale to linear.
"""
import inspect
import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import adapter as AD
from ClosedLoopDeployment import amplitude_effect as AE
from ClosedLoopDeployment import pipeline as PL
from ClosedLoopDeployment import three_source_response as TSR

CENTRES = [10.5, 20.5]
CURRENTS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]


def _panel():
    p = TSR.SourcePanel(source=TSR.SOURCE_TIME_DOMAIN, covers_whole_spectrum=True,
                        conversion_into_device_units=352.62, n_settings_offered=11)
    x = np.asarray(CURRENTS, float)
    rising = 100.0 + 40.0 * x                      # +40 device units per mA, exactly
    falling = 400.0 - 30.0 * x                     # -30 device units per mA, exactly
    p.current_mA = [float(v) for v in x]
    p.settled_power = [float(v) for v in rising]
    p.n_pieces = [10] * x.size
    p.spectrum_centres_hz = list(CENTRES)
    p.spectrum_power = [[float(rising[i]), float(falling[i])] for i in range(x.size)]
    p.spectrum_band_is_measuring_the_stimulator = [False, False]
    p.n_settings_used = x.size
    return p


def _build():
    c = TSR.ThreeSourceComparison(
        label="2026-08-18 14:00, left stimulator turned up", ramped_side="LEFT",
        sensing_contact="ONE_THREE_LEFT", programmed_centre_hz=20.5, stimulation_rate_hz=55.0,
        visit_date="2026-08-18", window_start_local="2026-08-18 14:00:00",
        window_end_local="2026-08-18 14:15:00", current_from_mA=0.5, current_to_mA=5.0,
        n_settings=11, settled_window_s=30.0)
    c.panels.append(_panel())
    return {"comparisons": [c], "gates_nothing": True}


def test_the_amplitude_effect_table_slope_is_in_device_units_per_mA():
    t = AE.table_from_build(_build(), checked_lo_hz=7.8, checked_hi_hz=28.3, band_half_hz=2.5)
    t = t.set_index("band_center_hz")
    assert t.loc[10.5, "slope_per_mA"] == pytest.approx(40.0, abs=1e-9)
    assert t.loc[20.5, "slope_per_mA"] == pytest.approx(-30.0, abs=1e-9)
    assert t.loc[10.5, "direction"].startswith("band power rises")
    assert t.loc[20.5, "direction"].startswith("band power falls")
    assert "power_residual_sd" in t.columns and "smallest_detectable_slope_per_mA" in t.columns
    for gone in ("slope_log_per_mA", "log_power_residual_sd", "smallest_detectable_slope_log_per_mA"):
        assert gone not in t.columns, gone


def test_the_amplitude_effect_rule_version_moved_so_no_log_built_row_is_served():
    assert AE.RULE_VERSION.startswith("v4_slope_on_raw_device_power_post_ramp_margin_"), AE.RULE_VERSION


def test_the_amplitude_effect_source_takes_no_logarithm_of_power():
    src = inspect.getsource(AE)
    for token in ("np.log(", "np.log10(", "np.log1p(", "math.log("):
        assert token not in src, token


def _cal_frame(n=6):
    """The calibrated frame's own columns, as `test_calibrated_join._cal_frame` lays them out."""
    t = np.arange(n, dtype=float) * 3.0
    return pd.DataFrame({"t": t, "channel": ["ZERO_TWO_LEFT"] * n, "source": ["td"] * n,
                         "family": ["td"] * n, "tile_ok": np.ones(n, bool),
                         "tile_saturated": np.zeros(n, bool), "band_half_hz": np.full(n, 2.5),
                         "tile_window_s": np.full(n, 3.0),
                         "band_lsb_26.5": 100.0 + 10.0 * t, "band_lsb_8.5": 50.0 + t,
                         "band_native_26.5": np.zeros(n, bool), "band_native_8.5": np.zeros(n, bool)})


def test_the_joined_table_carries_the_linear_power_only():
    T = AD.joined_table(_cal_frame(), None, centers=(26.5, 8.5))
    assert "power_linear" in T.columns
    for gone in ("power_log_of_linear", "power_mean_of_log"):
        assert gone not in T.columns, gone


def test_band_powers_returns_the_linear_band_power_alone():
    f = np.arange(8.0, 31.0, 1.0)
    bins = np.full(f.size, 7.0)
    lin = AD.band_powers(bins, f, centers=(20.5,), width=5.0)
    assert isinstance(lin, dict) and lin[20.5] == 7.0


def test_the_scale_disagreement_diagnostic_is_gone_and_the_only_scale_is_linear():
    assert not hasattr(AD, "scale_disagreement")
    with pytest.raises(ValueError):
        PL.run("u", power_scale="power_mean_of_log")


# --- decision 204: the older spectrum frame holds raw power ---------------------------------------

def test_band_powers_is_the_mean_of_the_raw_bins_with_nothing_undone():
    """The older frame's spectrum (`frame_from_matrix`) is raw power since decision 204, so the
    band mean is the plain mean of the bins: 1, 2, 3, 2, 1 over the band gives 1.8, not the mean of
    10 ** (x / 10)."""
    f = np.arange(8.0, 31.0, 1.0)
    bins = np.zeros(f.size)
    bins[(f >= 18) & (f < 23)] = [1.0, 2.0, 3.0, 2.0, 1.0]
    lin = AD.band_powers(bins, f, centers=(20.5,), width=5.0)
    assert lin[20.5] == 1.8, lin


def test_the_older_frame_is_joined_on_its_psd_column_and_nothing_in_the_adapter_undoes_a_log():
    src = inspect.getsource(AD)
    assert "log_psd" not in src, "the adapter still names the retired decibel column"
    for token in ("np.power(10.0", "10.0 **", "10 **", "np.log10("):
        assert token not in src, token
    t0 = pd.Timestamp("2026-01-01T00:00:00Z")
    f_set = np.arange(8.0, 31.0, 1.0)
    rows = [{"t": float((t0 + pd.Timedelta(minutes=5 * k)).timestamp()), "channel": "CH",
             "source": "td", "psd": np.full(f_set.size, 2.0 + k), "freqs": f_set} for k in range(3)]
    T = AD.joined_table(pd.DataFrame(rows), None, centers=(20.5,))
    assert list(T["power_linear"]) == [2.0, 3.0, 4.0], list(T["power_linear"])
