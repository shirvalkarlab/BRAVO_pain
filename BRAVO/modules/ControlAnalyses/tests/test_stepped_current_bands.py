"""Does settled band power change with current as much in bands with no plausible pain relationship
as in the pain-linked family? (finding M1, item A5, 2026-09-25.) On constructed ladder points whose
answer is known. Plain asserts; both suites."""
import numpy as np
import pandas as pd

try:
    from modules.ControlAnalyses import stepped_current_bands as EA
except ImportError:                                            # host spelling
    from ControlAnalyses import stepped_current_bands as EA


def _rows(n_runs=4, n_steps=5, *, family_slope=0.0, far_slope=0.0, baseline=100.0,
         source="time domain voltage trace", pair="ONE_THREE_LEFT", seed=0, refuse_some=False,
         stimulator_flag_on_far=False):
    rng = np.random.default_rng(seed)
    rows = []
    centres = [5.5, 10.5, 24.5, 26.5, 45.5]                    # 2 far-below, 2 family, 1 far-above
    for run in range(n_runs):
        currents = np.linspace(0.5, 0.5 + 0.5 * (n_steps - 1), n_steps)
        for c in centres:
            slope = family_slope if 21.5 - 1e-9 <= c <= 27.5 + 1e-9 else far_slope
            for k, cur in enumerate(currents):
                power = baseline * (1.0 + slope * cur) + rng.normal(0, 0.5)
                why = ""
                if refuse_some and run == 0 and k == 0:
                    why = "the current did not change to reach this setting"
                rows.append(dict(source=source, sensing_contact=pair, band_centre_hz=c,
                                 current_mA=float(cur), run=f"run{run}", leg=("rising" if k else "unchanged"),
                                 settled_band_power_device_units=(np.nan if why else power),
                                 why_not_used=why,
                                 band_is_measuring_the_stimulator=(stimulator_flag_on_far and c == 45.5)))
    return pd.DataFrame(rows)


def test_usable_rows_drops_refused_unchanged_and_stimulator_flagged_rows():
    d = _rows(refuse_some=True, stimulator_flag_on_far=True)
    u = EA.usable_rows(d)
    assert (u["why_not_used"] == "").all()
    assert "unchanged" not in set(u["leg"])
    assert not (u["band_centre_hz"] == 45.5).any()
    assert u["settled_band_power_device_units"].notna().all()


def test_usable_rows_is_empty_frame_for_none_or_empty_input():
    assert EA.usable_rows(None).empty
    assert EA.usable_rows(pd.DataFrame()).empty


def test_family_of_classifies_by_the_named_ranges():
    assert EA.family_of(21.5) == "family" and EA.family_of(27.5) == "family" and EA.family_of(24.5) == "family"
    assert EA.family_of(11.5) == "far" and EA.family_of(32.5) == "far" and EA.family_of(2.5) == "far"
    assert EA.family_of(15.0) is None and EA.family_of(20.0) is None


def test_fit_slope_recovers_a_planted_per_ma_change_with_run_intercepts():
    rng = np.random.default_rng(0)
    runs = np.repeat(["a", "b", "c"], 8)
    current = np.tile(np.linspace(0, 3.5, 8), 3)
    intercepts = {"a": 50.0, "b": 80.0, "c": 30.0}
    power = np.array([intercepts[r] for r in runs]) + 4.0 * current + rng.normal(0, 0.05, current.size)
    slope = EA._fit_slope(current, power, runs)
    assert abs(slope - 4.0) < 0.1


def test_fit_slope_refuses_when_there_is_no_spare_row():
    assert EA._fit_slope(np.array([1.0]), np.array([10.0]), np.array(["a"])) is None


def test_band_slope_reports_no_interval_below_the_run_floor_and_one_above_it():
    rng = np.random.default_rng(1)
    current = np.tile(np.linspace(0, 3, 5), 2)
    run = np.repeat(["a", "b"], 5)
    power = 100.0 + 2.0 * current + rng.normal(0, 0.2, current.size)
    two_runs = EA.band_slope(current, power, run, n_boot=200)
    assert two_runs["relative_slope_per_mA"] is not None and two_runs["lo"] is None

    current4 = np.tile(np.linspace(0, 3, 5), 4)
    run4 = np.repeat(["a", "b", "c", "d"], 5)
    power4 = 100.0 + 2.0 * current4 + rng.normal(0, 0.2, current4.size)
    four_runs = EA.band_slope(current4, power4, run4, n_boot=500, seed=2)
    assert four_runs["lo"] is not None and four_runs["lo"] < four_runs["relative_slope_per_mA"] < four_runs["hi"]


def test_per_route_pair_reads_a_ratio_near_one_when_far_bands_move_as_much_as_the_family():
    d = EA.usable_rows(_rows(n_runs=5, family_slope=0.10, far_slope=0.10, seed=7))
    bands, ratios = EA.per_route_pair(d, n_boot=300, seed=1)
    assert len(ratios) == 1
    r = ratios[0]
    assert r["n_family_bands"] == 2 and r["n_far_bands"] == 3
    assert 0.7 < r["far_over_family_ratio"] < 1.3


def test_per_route_pair_reads_a_ratio_well_under_one_when_only_the_family_moves():
    d = EA.usable_rows(_rows(n_runs=5, family_slope=0.10, far_slope=0.0, seed=8))
    bands, ratios = EA.per_route_pair(d, n_boot=300, seed=1)
    r = ratios[0]
    assert r["far_over_family_ratio"] < 0.3


def test_reading_states_the_prediction_and_handles_no_ratio():
    lines = EA.reading([dict(route="time domain voltage trace", pair="ONE_THREE_LEFT", n_family_bands=0,
                             n_far_bands=0, family_median_abs_relative_slope=None,
                             far_median_abs_relative_slope=None, far_over_family_ratio=None)])
    assert any("not enough family or far bands" in l for l in lines)
    assert any("never selects a band" in l for l in lines)

    lines2 = EA.reading([dict(route="time domain voltage trace", pair="ONE_THREE_LEFT", n_family_bands=2,
                              n_far_bands=3, family_median_abs_relative_slope=0.10,
                              far_median_abs_relative_slope=0.09, far_over_family_ratio=0.9)])
    assert any("predicts a ratio near 1" in l for l in lines2)
    assert any("at or above 1" in l for l in lines2)
