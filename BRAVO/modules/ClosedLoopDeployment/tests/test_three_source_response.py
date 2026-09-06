"""Tests for the three-way comparison of how stimulation current moves band power.

Each test below guards a specific way this comparison could go wrong and still look right, which is
the only kind of failure worth a test here. The three routes really must come from three separate
recordings; neighbouring band columns really must never be added together; a piece of recording the
device flagged really must be dropped; the bands that are carrying a folded landing really must be
marked; no new calibration constant may appear; and a route with no recording must say so rather
than go quietly missing.
"""

import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import three_source_response as TSR
from ClosedLoopDeployment import three_source_plots as TSP
from Biomarkers.routines import analytics


CENTRES = np.arange(2.5, 100.5, 1.0)
RATE_HZ = 55.0


def _steps(currents, *, t0=1_000_000.0, hold_s=60.0, block="run 1"):
    """A ladder of settings, each held for ``hold_s`` seconds, in the shape build_comparison wants."""
    t = t0 + hold_s * np.arange(len(currents), dtype=float)
    return pd.DataFrame({"t0": t, "t_end": np.append(t[1:], t[-1] + hold_s),
                         "current_mA": np.asarray(currents, dtype=float),
                         "block": [block] * len(currents)})


def _tiles(*, td_value=None, psd_value=None, t0=1_000_000.0, hold_s=60.0, n_settings=4,
           ok=True, saturated=False, per_piece_s=3.0):
    """A tile cache entry whose two families carry DIFFERENT, recognisable values.

    Route 1 and route 2 are given deliberately different numbers so a test can tell which one a
    panel read. If the code ever filled one panel from the other's numbers, the values would come out
    equal and the test below would see it.
    """
    n = int(n_settings * hold_s / per_piece_s)
    t = t0 + per_piece_s * np.arange(n, dtype=float)
    out = {"centers_hz": CENTRES.tolist(), "band_half_hz": 2.5, "window_s": per_piece_s}
    if td_value is not None:
        lsb = np.full((n, CENTRES.size), float(td_value))
        out["td"] = {"t": t, "lsb": lsb,
                     "ok": np.full(n, bool(ok)), "saturated": np.full(n, bool(saturated))}
    else:
        out["td"] = {"t": np.empty(0), "lsb": np.empty((0, CENTRES.size)),
                     "ok": np.empty(0, dtype=bool), "saturated": np.empty(0, dtype=bool)}
    if psd_value is not None:
        out["psd"] = {"t": t, "lsb": np.full((n, CENTRES.size), float(psd_value))}
    else:
        out["psd"] = {"t": np.empty(0), "lsb": np.empty((0, CENTRES.size))}
    return out


def _device(centre_hz=23.44, value=999.0, *, t0=1_000_000.0, hold_s=60.0, n_settings=4,
            currents=None, fs=2.0):
    """A device band power entry whose value is different again from both tile families."""
    n = int(n_settings * hold_s * fs)
    t = t0 + np.arange(n, dtype=float) / fs
    amp = np.zeros(n, dtype=float)
    if currents is not None:
        for i, c in enumerate(currents):
            amp[(t >= t0 + i * hold_s) & (t < t0 + (i + 1) * hold_s)] = float(c)
    return {"t": t, "power": np.full(n, float(value)), "mA": amp,
            "centre_hz": np.full(n, float(centre_hz)), "rate_hz": np.full(n, RATE_HZ),
            "averaging_s": np.full(n, 3.0), "hemisphere": "Left", "n_samples": n,
            "n_recordings": 1}


def _build(**kw):
    currents = kw.pop("currents", [0.0, 1.0, 2.0, 3.0])
    steps = _steps(currents)
    tiles = kw.pop("tiles", _tiles(td_value=100.0, psd_value=200.0, n_settings=len(currents)))
    device = kw.pop("device", _device(value=300.0, n_settings=len(currents), currents=currents))
    return TSR.build_comparison(
        label="test run", ramped_side="Left", sensing_contact="ONE_THREE_LEFT", steps=steps,
        visit_date="2026-08-18", window_start_local="2026-08-18 12:00:00",
        window_end_local="2026-08-18 12:04:00", tiles=tiles, device_band_power=device,
        stimulation_rate_hz=RATE_HZ, **kw)


def _panel(comp, source):
    return next(p for p in comp.panels if p.source == source)


# -------------------------------------------------------------------------------------------------
# 1. The three routes are read from their own recordings and never from one another
# -------------------------------------------------------------------------------------------------
def test_each_route_reports_its_own_recording_and_not_a_neighbours():
    """Each panel must carry the value from ITS OWN family, so no panel is filled from another.

    The three sources are given three different constant values. If a panel ever borrowed a
    neighbour's numbers to look complete, two panels would report the same value and this fails.
    """
    comp = _build()
    got = {p.source: sorted(set(v for v in p.settled_power if v is not None))
           for p in comp.panels}
    assert got[TSR.SOURCE_TIME_DOMAIN] == pytest.approx([100.0]), got
    assert got[TSR.SOURCE_DEVICE_SPECTRUM] == pytest.approx([200.0]), got
    assert got[TSR.SOURCE_DEVICE_BAND_POWER] == pytest.approx([300.0]), got
    assert len(set(tuple(v) for v in got.values())) == 3, (
        "two routes reported the same values, which means one was filled from another")


def test_a_route_with_no_recording_does_not_borrow_from_the_others():
    """When the device's own spectrum is absent, its panel stays empty and names the reason."""
    comp = _build(tiles=_tiles(td_value=100.0, psd_value=None))
    psd = _panel(comp, TSR.SOURCE_DEVICE_SPECTRUM)
    assert psd.settled_power == [], "the absent route produced values from somewhere"
    assert psd.absent_reason and "spectra" in psd.absent_reason
    assert _panel(comp, TSR.SOURCE_TIME_DOMAIN).settled_power, "the present route lost its values"


def test_the_device_band_power_is_read_from_the_device_and_carries_no_conversion():
    """Route 3 must be reported unconverted: a scale factor there would be a silent recalibration."""
    comp = _build()
    dev = _panel(comp, TSR.SOURCE_DEVICE_BAND_POWER)
    assert dev.conversion_into_device_units is None
    assert dev.settled_power and all(v == pytest.approx(300.0) for v in dev.settled_power)
    assert dev.band_inside_checked_conversion_range is None, (
        "route 3 converts nothing, so it cannot be inside or outside a checked conversion range")


# -------------------------------------------------------------------------------------------------
# 2. Neighbouring band columns are never combined
# -------------------------------------------------------------------------------------------------
def test_one_band_is_one_column_and_never_a_sum_of_neighbours():
    """A 5 Hz band is ONE column of the cache, never the sum or mean of adjacent columns.

    The columns are 5 Hz wide on 1 Hz spacing, so they overlap heavily; adding two of them counts
    the same signal twice and inflates every value. Here every column holds 100, so a sum of two
    neighbours would show as 200 and a mean of three as 100 -- the sum is what this catches, and the
    band edges below catch the mean by pinning the width.
    """
    comp = _build()
    td = _panel(comp, TSR.SOURCE_TIME_DOMAIN)
    assert all(v == pytest.approx(100.0) for v in td.settled_power), (
        "a band came out larger than one column, so columns were combined")
    assert td.band_hi_hz - td.band_lo_hz == pytest.approx(2 * TSR.BAND_HALF_HZ)
    assert len(td.spectrum_power[0]) == CENTRES.size, (
        "the spectrum row has a different number of bands than the cache has columns")


def test_the_comparison_band_is_the_single_nearest_centre_to_what_the_device_sensed():
    """The band all three are compared at is the ONE closest cache centre, with the gap reported."""
    comp = _build(device=_device(centre_hz=23.44, value=300.0, currents=[0.0, 1.0, 2.0, 3.0]))
    td = _panel(comp, TSR.SOURCE_TIME_DOMAIN)
    assert td.band_centre_hz == pytest.approx(23.5)
    assert td.offset_from_programmed_centre_hz == pytest.approx(0.06, abs=1e-6)


def test_the_band_width_is_refused_if_the_cache_ever_changes_it():
    """If the cache's band half-width stops being 2.5 Hz, stop rather than compare unlike bands."""
    tiles = _tiles(td_value=100.0, psd_value=200.0)
    tiles["band_half_hz"] = 1.5
    with pytest.raises(ValueError, match="either side of centre"):
        _build(tiles=tiles)


# -------------------------------------------------------------------------------------------------
# 3. A saturated or not-ok piece of recording is excluded
# -------------------------------------------------------------------------------------------------
def test_a_saturated_piece_of_recording_is_excluded():
    comp = _build(tiles=_tiles(td_value=100.0, psd_value=200.0, saturated=True))
    td = _panel(comp, TSR.SOURCE_TIME_DOMAIN)
    assert td.settled_power == [], "a saturated recording produced a settled value"
    assert td.n_pieces_dropped_for_quality > 0
    assert td.absent_reason


def test_a_piece_the_device_did_not_mark_usable_is_excluded():
    comp = _build(tiles=_tiles(td_value=100.0, psd_value=200.0, ok=False))
    td = _panel(comp, TSR.SOURCE_TIME_DOMAIN)
    assert td.settled_power == []
    assert td.n_pieces_dropped_for_quality > 0


def test_pieces_outside_the_run_are_not_counted_as_coverage_for_it():
    """The count a panel prints must describe the run drawn beside it, not the whole record.

    A whole-history count would tell a reader the route is well covered here when it may have
    nothing here at all, which is the exact mistake the honest empty state exists to prevent.
    """
    tiles = _tiles(td_value=100.0, psd_value=200.0, t0=2_000_000.0)   # far from the steps
    comp = _build(tiles=tiles)
    td = _panel(comp, TSR.SOURCE_TIME_DOMAIN)
    assert td.n_pieces_in_run_before_quality_checks == 0
    assert td.n_pieces_available_in_visit == 0
    assert td.settled_power == []
    assert td.absent_reason


# -------------------------------------------------------------------------------------------------
# 4. The bands that are carrying a folded landing are marked
# -------------------------------------------------------------------------------------------------
def test_the_bands_measuring_the_stimulator_are_marked_from_the_existing_helper():
    """The marked bands must be the ones the shared helper names, not a list computed here."""
    comp = _build()
    expected = [float(c) for c in CENTRES
                if not clinic_mask(RATE_HZ, c)]
    assert comp.bands_measuring_the_stimulator_hz == pytest.approx(expected)
    assert comp.bands_measuring_the_stimulator_hz, "no band was marked at all"
    landings = {d["lands_at_hz"] for d in analytics.harmonic_landings_hz(RATE_HZ, 0.0, 102.0)}
    assert set(comp.stimulator_landings_hz) <= landings


def clinic_mask(rate_hz, centre_hz):
    from ClosedLoopDeployment import clinic_steps
    return bool(clinic_steps.amplitude_response_band_mask(rate_hz, np.array([centre_hz]))[0])


def test_the_marking_reaches_every_row_of_the_table_and_the_figure_text():
    comp = _build()
    rows = TSR.comparison_rows(comp)
    assert rows, "the table came out empty"
    assert any(r["band_is_measuring_the_stimulator"] for r in rows), (
        "no row was marked as carrying a folded landing")
    assert all("band_is_measuring_the_stimulator" in r for r in rows)
    ctx = TSP.build_context(comp)
    assert ctx.striped_centres_hz, "the figure marked no band as carrying a folded landing"
    assert all(TSP.SPECTRUM_LO_HZ <= f <= TSP.SPECTRUM_HI_HZ for f in ctx.striped_centres_hz)


def test_the_headline_says_so_when_the_sensed_band_is_measuring_the_stimulator():
    """A band the device was sensing that is really the stimulator must be named in the headline.

    This is the failure that actually happened on this record: an artifact band reaching 45506
    device units looked like a spectacular biomarker until it was marked.
    """
    on_stim = _build(device=_device(centre_hz=25.0, value=300.0, currents=[0.0, 1.0, 2.0, 3.0]))
    assert "carrying a folded landing" in TSP.build_context(on_stim).headline
    clean = _build(device=_device(centre_hz=10.0, value=300.0, currents=[0.0, 1.0, 2.0, 3.0]))
    assert "carrying a folded landing" not in TSP.build_context(clean).headline


# -------------------------------------------------------------------------------------------------
# 5. No new calibration constant appears anywhere
# -------------------------------------------------------------------------------------------------
def test_the_two_converted_routes_use_only_the_two_existing_constants():
    comp = _build()
    assert (_panel(comp, TSR.SOURCE_TIME_DOMAIN).conversion_into_device_units
            == pytest.approx(analytics.LSB_PER_UV2_TRANSFORM))
    assert (_panel(comp, TSR.SOURCE_DEVICE_SPECTRUM).conversion_into_device_units
            == pytest.approx(analytics.LSB_PER_DEVICE_PSD))
    assert TSR.SOURCE_CONVERSION[TSR.SOURCE_DEVICE_BAND_POWER] is None


def test_the_checked_frequency_range_is_read_from_analytics_and_not_written_again():
    """The checked range must be the constants' own values, and must not be the firmware's limit.

    28.3 Hz is the highest centre we have paired data to check the conversion at. 30 Hz is the
    highest place the firmware will let a sensing band sit. Using the firmware limit here would
    claim a check that was never run, so the two must not be confused.
    """
    assert TSR.CHECKED_LO_HZ == pytest.approx(analytics.LSB_VALIDATED_HZ_LO)
    assert TSR.CHECKED_HI_HZ == pytest.approx(analytics.LSB_VALIDATED_HZ_HI)
    assert TSR.CHECKED_HI_HZ != pytest.approx(analytics.LSB_DEPLOYABLE_HZ_HI)


def test_no_numeric_calibration_constant_is_written_into_either_new_module():
    """Neither new module may contain a hardcoded conversion number of its own.

    The two real constants live in analytics and are imported. A literal that happens to equal one
    of them, or any new number sitting next to a conversion word, is how a third calibration would
    enter this codebase without anybody deciding to add one.
    """
    import re
    from pathlib import Path
    banned = (analytics.LSB_PER_UV2_TRANSFORM, analytics.LSB_PER_DEVICE_PSD)
    for name in ("three_source_response.py", "three_source_plots.py"):
        src = (Path(TSR.__file__).parent / name).read_text()
        code = "\n".join(line for line in src.splitlines()
                         if not line.lstrip().startswith("#"))
        code = re.sub(r'""".*?"""', "", code, flags=re.S)
        code = re.sub(r"'''.*?'''", "", code, flags=re.S)
        for value in banned:
            assert f"{value:g}" not in code, (
                f"{name} writes the calibration constant {value:g} as a literal instead of "
                f"importing it from analytics")


# -------------------------------------------------------------------------------------------------
# 6. Settled signal only, and never across a break in the ladder
# -------------------------------------------------------------------------------------------------
def test_a_setting_the_current_did_not_rise_into_gets_no_value_and_a_reason():
    comp = _build(currents=[0.0, 1.0, 2.0, 3.0])
    td = _panel(comp, TSR.SOURCE_TIME_DOMAIN)
    first = td.settings[0]
    assert first["current_mA"] == pytest.approx(0.0)
    assert first["settled_power"] is None
    assert first["why_not_used"], "a refused setting gave no reason"


def test_the_device_route_refuses_a_window_in_which_its_own_record_shows_the_current_moving():
    """Only route 3 can check this, because only it carries the current beside the power."""
    currents = [0.0, 1.0, 2.0, 3.0]
    dev = _device(value=300.0, currents=currents)
    # Make the current move inside the last setting's settled window.
    late = dev["t"] >= dev["t"][0] + 3 * 60.0 + 40.0
    dev["mA"][late] = 3.5
    comp = _build(currents=currents, device=dev)
    panel = _panel(comp, TSR.SOURCE_DEVICE_BAND_POWER)
    refused = [s for s in panel.settings if s["settled_power"] is None and s["why_not_used"]]
    assert refused, "no setting was refused although the current moved during a window"
    assert any("moving" in s["why_not_used"] or "still" in s["why_not_used"] for s in refused), \
        [s["why_not_used"] for s in refused]


def test_a_run_of_rising_current_is_not_joined_across_a_fall_to_zero():
    """When the current drops and rises again, that is two runs, and no window crosses the break."""
    record = {"blocks": [{
        "t": np.arange(0.0, 1200.0, 0.5),
        "mA": {"ONE_THREE_LEFT": _ladder(np.arange(0.0, 1200.0, 0.5),
                                         [(0, 0.0), (60, 1.0), (180, 2.0), (300, 0.0),
                                          (360, 1.0), (480, 2.0), (600, 3.0)]),
               "ONE_THREE_RIGHT": np.zeros(2400)},
    }]}
    runs = TSR.find_single_side_runs_from_device(record, min_settings=2)
    assert len(runs) == 2, [r["current_from_mA"] for r in runs]
    for run in runs:
        amp = run["steps"]["current_mA"].to_numpy(dtype=float)
        rising = amp[amp > 0]
        assert np.all(np.diff(rising) > 0), f"a run contains a fall: {amp}"
    assert len(set(run["steps"]["block"].iloc[0] for run in runs)) == 2, (
        "the two runs share a block label, so a window could be carried across the break")


def _ladder(t, points):
    out = np.zeros(t.size, dtype=float)
    for start, value in points:
        out[t >= start] = value
    return out


def test_both_sides_running_is_not_a_run_because_no_side_can_be_credited():
    record = {"blocks": [{
        "t": np.arange(0.0, 600.0, 0.5),
        "mA": {"ONE_THREE_LEFT": _ladder(np.arange(0.0, 600.0, 0.5),
                                         [(0, 1.0), (120, 2.0), (240, 3.0)]),
               "ONE_THREE_RIGHT": _ladder(np.arange(0.0, 600.0, 0.5),
                                          [(0, 1.0), (120, 2.0), (240, 3.0)])},
    }]}
    assert TSR.find_single_side_runs_from_device(record, min_settings=2) == []


def test_the_fine_increments_the_device_walks_through_are_one_setting_not_many():
    """The device ramps in 0.1 mA steps, and each clinician setting must stay one setting."""
    t = np.arange(0.0, 600.0, 0.5)
    amp = np.zeros(t.size)
    amp[t >= 60] = 1.0
    for i, v in enumerate([1.1, 1.2, 1.3, 1.4, 1.5]):     # the walk to 1.5 mA, a second apart
        amp[t >= 180 + i] = v
    amp[t >= 360] = 2.0
    record = {"blocks": [{"t": t, "mA": {"ONE_THREE_LEFT": amp,
                                         "ONE_THREE_RIGHT": np.zeros(t.size)}}]}
    runs = TSR.find_single_side_runs_from_device(record, min_settings=2)
    assert len(runs) == 1
    got = sorted(set(runs[0]["steps"]["current_mA"].to_numpy(dtype=float)))
    # 1.0, 1.5 and 2.0 are the three settings the device ARRIVED at. The 0.0 it started the
    # recording on is not one: nothing in the record shows the device arriving there, so there is no
    # moment at which it stopped moving and no settled window that can be attributed to it.
    assert got == pytest.approx([1.0, 1.5, 2.0]), got
    assert len(runs[0]["steps"]) == 3, (
        "the 0.1 mA increments the device walks through were read as settings of their own")


# -------------------------------------------------------------------------------------------------
# 7. The payload is absent-with-a-reason, never silently empty; and it gates nothing
# -------------------------------------------------------------------------------------------------
def test_the_table_carries_a_row_for_a_route_that_produced_nothing():
    """A route with no recording must still appear in the table, with its reason."""
    comp = _build(tiles=_tiles(td_value=100.0, psd_value=None))
    rows = TSR.comparison_rows(comp)
    absent = [r for r in rows if r["source"] == TSR.SOURCE_DEVICE_SPECTRUM]
    assert absent, "the absent route was left out of the table entirely"
    assert all(r["settled_band_power_device_units"] is None for r in absent)
    assert all(r["route_absent_reason"] for r in absent)


def test_the_table_carries_a_row_for_every_setting_including_the_refused_ones():
    comp = _build(currents=[0.0, 1.0, 2.0, 3.0])
    rows = TSR.comparison_rows(comp)
    td_one_band = [r for r in rows if r["source"] == TSR.SOURCE_TIME_DOMAIN
                   and r["band_centre_hz"] == pytest.approx(23.5)]
    assert len(td_one_band) == 4, len(td_one_band)
    assert sum(1 for r in td_one_band if r["settled_band_power_device_units"] is None) == 1
    assert all(r["why_not_used"] for r in td_one_band
               if r["settled_band_power_device_units"] is None)


def test_the_payload_says_which_piece_was_missing_when_there_is_no_streaming_at_all():
    payload = TSP.report_payload({"comparisons": [], "gates_nothing": True,
                                  "absent_reason": "no streaming recordings are stored"})
    assert payload["comparisons"] == []
    assert payload["absent_reason"]
    assert payload["gates_nothing"] is True


def test_the_payload_gates_nothing_and_carries_no_verdict():
    """Nothing in this payload may look like a pass, a fail or a blocking status."""
    comp = _build()
    payload = TSP.report_payload({"comparisons": [comp], "gates_nothing": True})
    assert payload["gates_nothing"] is True
    flat = repr(payload).lower()
    for word in ("blocking_status", "verdict", '"pass"', '"fail"', "gate_passed", "deployable"):
        assert word not in flat, f"the payload carries {word}, which would let it gate something"
    assert payload["comparisons"][0]["notes"], "the payload lost the sentence about independence"
    assert any("not independent" in n or "checks the conversion" in n or "conversion is behaving" in n
               for n in payload["comparisons"][0]["notes"] + [payload["comparisons"][0]["footer"]])


def test_the_figure_text_is_derived_and_moves_when_the_numbers_move():
    """No sentence on the figure may be a fixed claim: change the data, the sentence must change."""
    a = TSP.build_context(_build(device=_device(value=300.0, currents=[0.0, 1.0, 2.0, 3.0])))
    b = TSP.build_context(_build(device=_device(value=3000.0, currents=[0.0, 1.0, 2.0, 3.0])))
    assert a.headline != b.headline, "the headline did not move when the numbers moved"
    dev_a = next(c for c in a.columns if c["source"] == TSR.SOURCE_DEVICE_BAND_POWER)
    dev_b = next(c for c in b.columns if c["source"] == TSR.SOURCE_DEVICE_BAND_POWER)
    assert dev_a["caption"] != dev_b["caption"]
    assert "300" in dev_a["caption"] and "3000" in dev_b["caption"]


def test_the_device_route_refuses_a_window_where_its_sensing_band_changed():
    """Two different bands averaged into one number would be reported as one band's power."""
    dev = _device(value=300.0, currents=[0.0, 1.0, 2.0, 3.0])
    dev["centre_hz"][dev["t"] > dev["t"][0] + 120.0] = 10.74
    with pytest.raises(ValueError, match="more than one band"):
        TSR.device_band_power_in_window(dev, dev["t"][0], dev["t"][-1] + 1.0)
