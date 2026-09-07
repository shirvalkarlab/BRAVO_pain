"""Track G step 2: the device route's ceiling check and the ground-truth verdict rule."""
import numpy as np
import pandas as pd

from ClosedLoopDeployment import ground_truth as GT
from ClosedLoopDeployment import three_source_response as T3

T0 = 1_750_000_000.0


def _device_stream(n_steps=3, hz=2.0, hold_s=90.0, level=200.0, spikes_at=()):
    """A device band-power stream with the current held at each setting for hold_s seconds."""
    t, p, a = [], [], []
    step_t0, step_end = [], []
    for k in range(n_steps):
        s0 = T0 + k * hold_s
        step_t0.append(s0); step_end.append(s0 + hold_s)
        n = int(hold_s * hz)
        tt = s0 + np.arange(n) / hz
        pp = np.full(n, level * (k + 1))
        t.extend(tt); p.extend(pp); a.extend([1.0 + 0.5 * k] * n)
    t, p, a = np.asarray(t), np.asarray(p, float), np.asarray(a)
    for when in spikes_at:
        j = int(np.argmin(np.abs(t - when)))
        p[j] = 50_000.0
    return np.asarray(step_t0), np.asarray(step_end), np.asarray([1.0 + 0.5 * k for k in range(n_steps)]), t, p, a


def test_a_spike_above_the_ceiling_is_excluded_and_counted_and_the_setting_is_kept():
    st0, se, amps, t, p, a = _device_stream(spikes_at=(T0 + 90 + 70.0,))    # one spike in setting 2's window
    power, table = T3.settled_device_band_power(st0, se, amps, t, p, a, block=None)
    assert table.loc[1, "n_spikes_excluded"] == 1 and table.loc[0, "n_spikes_excluded"] == 0
    assert np.isfinite(power[1]) and abs(power[1] - 400.0) < 1e-9, "the spike did not enter the average"
    assert table.loc[1, "ceiling_device_units"] == 10.0 * 400.0


def test_a_window_left_with_too_few_samples_after_spikes_falls_through_with_the_count_in_its_reason():
    st0, se, amps, t, p, a = _device_stream(hz=2.0)
    # make most of setting 2's last 30 s spikes: the window then has too few clean samples
    win = (t >= se[1] - 30.0) & (t < se[1]) & (a == 1.5)
    idx = np.flatnonzero(win)
    p[idx[: int(0.6 * idx.size)]] = 50_000.0
    power, table = T3.settled_device_band_power(st0, se, amps, t, p, a, block=None)
    # the median of a window that is 60 percent spikes IS a spike, so the ceiling sits above the
    # spikes and nothing is excluded; the rule keeps the setting and its value is the spike level.
    # That is the honest limit of a median ceiling and the reason the constant is provisional.
    assert table.loc[1, "n_spikes_excluded"] == 0
    p2 = p.copy(); p2[idx[: int(0.4 * idx.size)]] = 50_000.0; p2[idx[int(0.4 * idx.size):]] = 400.0
    power2, table2 = T3.settled_device_band_power(st0, se, amps, t, p2, a, block=None,
                                                  min_fraction=0.9)
    assert table2.loc[1, "n_spikes_excluded"] == int(0.4 * idx.size)
    assert not np.isfinite(power2[1]) and "excluded as spikes" in table2.loc[1, "why_not_used"]


def _rows(run="r1"):
    common = {"run": run, "visit_date": "2026-08-18", "ramped_side": "Left",
              "sensing_contact": "ONE_THREE_LEFT", "stimulation_rate_hz": 55.0,
              "route_absent_reason": "", "band_is_measuring_the_stimulator": False}
    def row(source, centre, cur, power, n, why="", checked=True, spikes=0):
        return {**common, "source": source, "band_centre_hz": centre, "current_mA": cur,
                "settled_band_power_device_units": power, "n_pieces_averaged": n,
                "n_spikes_excluded": spikes, "band_inside_checked_conversion_range": checked,
                "why_not_used": why}
    return [
        # 26.5 Hz at 1.0 mA: device and voltage trace both present -> device wins, fold written
        row(T3.SOURCE_DEVICE_BAND_POWER, 26.5, 1.0, 500.0, 60, spikes=1),
        row(T3.SOURCE_TIME_DOMAIN, 26.5, 1.0, 400.0, 10),
        row(T3.SOURCE_DEVICE_SPECTRUM, 26.5, 1.0, None, 0, why="no spectrum in the window"),
        # 26.5 Hz at 2.0 mA: device refused -> voltage trace
        row(T3.SOURCE_DEVICE_BAND_POWER, 26.5, 2.0, None, 5, why="too few samples (3 excluded as spikes)", spikes=3),
        row(T3.SOURCE_TIME_DOMAIN, 26.5, 2.0, 420.0, 10),
        # 12.5 Hz at 2.0 mA: only the composed spectrum route
        row(T3.SOURCE_TIME_DOMAIN, 12.5, 2.0, None, 0, why="railed", checked=True),
        row(T3.SOURCE_DEVICE_SPECTRUM, 12.5, 2.0, 77.0, 1),
        # 40.5 Hz at 2.0 mA: nothing
        row(T3.SOURCE_TIME_DOMAIN, 40.5, 2.0, None, 0, why="railed", checked=False),
        # a whole-run absence row for the device route (no setting)
        {**common, "source": T3.SOURCE_DEVICE_BAND_POWER, "band_centre_hz": None, "current_mA": None,
         "settled_band_power_device_units": None, "n_pieces_averaged": 0,
         "band_inside_checked_conversion_range": None, "route_absent_reason": "the device did not stream",
         "why_not_used": "the device did not stream"},
    ]


def test_the_precedence_and_the_fold_ratio():
    t = pd.DataFrame(GT.verdict_rows(_rows()), columns=list(GT.COLUMNS))
    by = {(r.band_center_hz, r.current_mA): r for r in t.itertuples()}
    a = by[(26.5, 1.0)]
    assert a.ground_truth_route == GT.ROUTE_DEVICE and a.ground_truth_power == 500.0
    assert a.fold_device_over_voltage_trace == 1.25 and a.device_spikes_excluded == 1
    assert a.ground_truth_is_measured_not_composed == True and a.voltage_trace_power == 400.0
    b = by[(26.5, 2.0)]
    assert b.ground_truth_route == GT.ROUTE_VOLTAGE_TRACE and b.ground_truth_power == 420.0
    assert b.device_spikes_excluded == 3 and "spikes" in b.device_refused_reason
    assert b.fold_device_over_voltage_trace is None or np.isnan(b.fold_device_over_voltage_trace)
    c = by[(12.5, 2.0)]
    assert c.ground_truth_route == GT.ROUTE_DEVICE_SPECTRUM and c.ground_truth_is_measured_not_composed == False
    assert c.device_refused_reason == "the device did not stream", "a whole-run absence is the reason"
    d = by[(40.5, 2.0)]
    assert d.ground_truth_route == GT.ROUTE_NONE and pd.isna(d.ground_truth_power)
    assert "voltage trace: railed" in d.why_no_ground_truth and d.band_inside_checked_conversion_range == False


def test_the_devices_band_is_paired_with_the_nearest_stored_centre_the_comparison_used():
    rows = _rows()
    for r in rows:
        if r["source"] == T3.SOURCE_DEVICE_BAND_POWER and r["band_centre_hz"] == 26.5:
            r["band_centre_hz"] = 26.4                       # the programmed centre, as the device reports it
    alias = {("r1", 26.4): 26.5}
    t = pd.DataFrame(GT.verdict_rows(rows, device_band_alias=alias), columns=list(GT.COLUMNS))
    a = t[(t.band_center_hz == 26.5) & (t.current_mA == 1.0)].iloc[0]
    assert a.ground_truth_route == GT.ROUTE_DEVICE and a.device_band_center_hz == 26.4
    assert a.fold_device_over_voltage_trace == 1.25, "the fold is written where the comparison paired them"
    assert not (t.band_center_hz == 26.4).any(), "no orphan row at the programmed centre"
    assert GT.count_matches(t, rows) == (3, 0)
    # without the alias the two never meet, which is the defect the live record showed
    u = pd.DataFrame(GT.verdict_rows(rows), columns=list(GT.COLUMNS))
    assert u["fold_device_over_voltage_trace"].notna().sum() == 0


def test_the_alias_is_read_from_the_comparisons_own_panels():
    c = _comparison_with_settings()
    c.programmed_centre_hz = 26.4
    assert GT.device_band_alias(c) == {(c.label, 26.4): 26.5}


def test_every_verdict_value_is_a_copy_of_the_comparison_row_it_names():
    rows = _rows()
    t = pd.DataFrame(GT.verdict_rows(rows), columns=list(GT.COLUMNS))
    assert GT.count_matches(t, rows) == (3, 0)
    t.loc[0, "ground_truth_power"] = 1.0
    assert GT.count_matches(t, rows) == (3, 1)


def test_table_from_build_has_every_column_and_tolerates_an_empty_build():
    assert list(GT.table_from_build({}).columns) == list(GT.COLUMNS)
    assert list(GT.table_from_build(None).columns) == list(GT.COLUMNS)


# ---- the write-back, on the amplitude test's sandbox and constructed comparison ----------------
from ClosedLoopDeployment import adapter as AD                                          # noqa: E402
from ClosedLoopDeployment.tests.test_amplitude_effect import _build, _comparison, sandbox   # noqa: E402,F401
from CacheStore import store as st                                                      # noqa: E402


def _comparison_with_settings():
    """The amplitude test's comparison, with per-setting rows on two routes so the rule has
    something to choose between: the voltage trace at every setting, the device at two of them."""
    c = _comparison()
    td = c.panels[0]
    for k, cur in enumerate((0.5, 1.0, 1.5, 2.0)):
        td.settings.append({"current_mA": cur, "settled_power": 100.0 + 10 * k, "n_pieces": 10,
                            "accepted": True, "why_not_used": ""})
        td.current_mA.append(cur); td.settled_power.append(100.0 + 10 * k); td.n_pieces.append(10)
    td.band_centre_hz = 26.5; td.band_lo_hz = 24.0; td.band_hi_hz = 29.0
    td.band_inside_checked_conversion_range = True
    dev = T3.SourcePanel(source=T3.SOURCE_DEVICE_BAND_POWER, covers_whole_spectrum=False,
                         conversion_into_device_units=None, band_centre_hz=26.5,
                         band_lo_hz=24.0, band_hi_hz=29.0)
    for cur, pw, why, spikes in ((0.5, 130.0, "", 1), (1.0, None, "too few samples", 4),
                                 (1.5, 150.0, "", 0), (2.0, None, "current moving", 0)):
        dev.settings.append({"current_mA": cur, "settled_power": pw, "n_pieces": 60 if pw else 5,
                             "n_spikes_excluded": spikes, "accepted": pw is not None,
                             "why_not_used": why})
    c.panels.append(dev)
    return c


def test_the_verdict_is_written_once_with_the_tile_entry_in_its_provenance_and_read_by_stim_optimizer(sandbox):
    first = AD.write_ground_truth("PARTICIPANT", _build(_comparison_with_settings()))
    assert first["routes"]["device"] == 2 and first["routes"]["voltage_trace_calibrated"] >= 2
    assert first["device_spikes_excluded"] == 5
    assert first["written"] is True and first["n_rows"] > 0 and first["routes"]
    assert first["device_spike_fold"] == T3.DEVICE_SPIKE_FOLD
    stamp = st.read_stamp(GT.KIND, "PARTICIPANT",
                          AD.ground_truth_signature("PARTICIPANT", tiles_key="raw_lsb_tiles/PARTICIPANT/tiles1"),
                          root=sandbox)
    assert stamp["writer"] == "closed_loop" and stamp["provenance"][0]["kind"] == "raw_lsb_tiles"
    assert stamp["extra"]["routes"] == first["routes"]
    second = AD.write_ground_truth("PARTICIPANT", _build(_comparison_with_settings()))
    assert second["store_key"] == first["store_key"]
    table, got = st.load_newest(GT.KIND, "PARTICIPANT", consumer="stim_optimizer", root=sandbox)
    assert len(table) == first["n_rows"] and got["signature_key"] == stamp["signature_key"]
    assert AD.ground_truth_if_stored("PARTICIPANT")["served_from_store"] is True


def test_the_report_page_status_names_the_inputs_entry_or_its_absence(sandbox):
    none = AD.cache_status_for_page("PARTICIPANT")
    assert none["exists"] is False and none["kind"] == "inputs" and "no stored entry" in none["note"]
    st.store("inputs", None, ("PARTICIPANT", 1, 2, "rs1"), {"x": 1}, writer="closed_loop",
             provenance=[], trigger="inputs_build", root=sandbox)
    got = AD.cache_status_for_page("PARTICIPANT")
    assert got["exists"] is True and got["trigger"] == "inputs_build" and got["last_built_utc"]
