"""Track A step 7: the per-band amplitude-effect table derived from the three-source comparison.

The table must copy the comparison's settled powers value for value, fit the straight line and
the curvature on exactly the currents each band has, say how many currents were tested and over
what range, report "not assessed" rather than "no response" when there are too few, and be
written through the store with the tile entry in its provenance so Stim Optimizer may read it.
"""
import json
import os
import shutil
import tempfile

import numpy as np
import pytest

from ClosedLoopDeployment import adapter as AD
from ClosedLoopDeployment import amplitude_effect as AE
from ClosedLoopDeployment import three_source_response as TSR

CENTRES = [10.5, 20.5, 26.5, 30.5]
CURRENTS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]


def _panel(currents=CURRENTS, *, absent=None):
    p = TSR.SourcePanel(source=TSR.SOURCE_TIME_DOMAIN, covers_whole_spectrum=True,
                        conversion_into_device_units=352.62, n_settings_offered=len(currents) + 1)
    if absent:
        p.absent_reason = absent
        return p
    x = np.asarray(currents, dtype=float)
    rising = 100.0 * np.exp(0.4 * x)                                 # log-linear rise
    flat = np.full(x.size, 150.0) + np.array([1, -1, 2, -2, 1, -1, 2, -2, 1, -1])[: x.size]
    peaked = 300.0 - 60.0 * (x - 2.1) ** 2                           # rise then fall, peak 2.1 mA
    peaked = np.clip(peaked, 5.0, None)
    falling = 400.0 * np.exp(-0.3 * x)
    p.current_mA = [float(v) for v in x]
    p.settled_power = [float(v) for v in rising]
    p.n_pieces = [10] * x.size
    p.spectrum_centres_hz = list(CENTRES)
    p.spectrum_power = [[float(rising[i]), float(flat[i]), float(peaked[i]), float(falling[i])]
                        for i in range(x.size)]
    p.spectrum_band_is_measuring_the_stimulator = [False, False, True, False]
    p.n_settings_used = x.size
    return p


def _comparison(label="2026-08-18 14:00, left stimulator turned up", **kw):
    c = TSR.ThreeSourceComparison(
        label=label, ramped_side="LEFT", sensing_contact=kw.get("sensing_contact", "ONE_THREE_LEFT"),
        programmed_centre_hz=26.5, stimulation_rate_hz=55.0, visit_date=kw.get("visit_date", "2026-08-18"),
        window_start_local="2026-08-18 14:00:00", window_end_local="2026-08-18 14:15:00",
        current_from_mA=0.5, current_to_mA=5.0, n_settings=11, settled_window_s=30.0)
    c.panels.append(kw.get("panel") or _panel())
    return c


def _build(*comps):
    return {"comparisons": list(comps), "gates_nothing": True}


def test_one_row_per_band_with_the_currents_and_the_powers_copied_exactly():
    table = AE.table_from_build(_build(_comparison()), checked_lo_hz=7.8, checked_hi_hz=28.3,
                                band_half_hz=2.5)
    assert len(table) == 4
    assert list(table["band_center_hz"]) == CENTRES
    assert (table["n_currents_tested"] == 10).all()
    assert (table["current_min_mA"] == 0.5).all() and (table["current_max_mA"] == 5.0).all()
    assert (table["n_pieces_total"] == 100).all()
    assert json.loads(table.loc[0, "currents_mA"]) == CURRENTS
    assert AE.count_matches(table, _build(_comparison())) == (8, 0)
    assert list(table["band_is_measuring_the_stimulator"]) == [False, False, True, False]
    assert list(table["band_inside_checked_conversion_range"]) == [True, True, True, False]


def test_the_slope_reads_a_rise_a_fall_and_no_movement_and_the_curvature_finds_the_peak():
    table = AE.table_from_build(_build(_comparison()), checked_lo_hz=7.8, checked_hi_hz=28.3,
                                band_half_hz=2.5).set_index("band_center_hz")
    rise, flat, peak, fall = (table.loc[c] for c in CENTRES)
    assert rise["slope_log_per_mA"] == pytest.approx(0.4, abs=1e-9)
    assert rise["slope_p"] < 1e-6 and rise["direction"].startswith("band power rises")
    assert fall["slope_log_per_mA"] == pytest.approx(-0.3, abs=1e-9)
    assert fall["direction"].startswith("band power falls")
    assert flat["slope_p"] > 0.05 and flat["direction"].startswith("no straight-line movement")
    assert bool(peak["curves"]) and bool(peak["peaks_inside"])
    assert peak["peak_mA"] == pytest.approx(2.1, abs=0.05)
    assert peak["p_curvature"] < 0.01 and peak["r2_quadratic"] > peak["r2_linear"]
    assert peak["quadratic_coefficient"] < 0
    assert rise["fold_max_over_min"] == pytest.approx(np.exp(0.4 * 4.5), rel=1e-9)
    assert np.isfinite(rise["smallest_detectable_slope_log_per_mA"])
    assert rise["smallest_detectable_slope_log_per_mA"] == pytest.approx(2 * rise["slope_stderr"])


def test_too_few_currents_is_not_assessed_and_still_says_how_many_were_tested():
    table = AE.table_from_build(_build(_comparison(panel=_panel([1.0, 2.0]))),
                                checked_lo_hz=7.8, checked_hi_hz=28.3, band_half_hz=2.5)
    assert len(table) == 4
    assert (table["n_currents_tested"] == 2).all()
    assert table["slope_log_per_mA"].isna().all()
    assert (table["direction"] == "not assessed").all()
    assert table["curvature_verdict"].str.startswith("not assessed").all()
    # eight points are needed for a curve; five currents give a slope but no curvature verdict
    table5 = AE.table_from_build(_build(_comparison(panel=_panel(CURRENTS[:5]))),
                                 checked_lo_hz=7.8, checked_hi_hz=28.3, band_half_hz=2.5)
    assert table5["slope_log_per_mA"].notna().all()
    assert table5["curvature_verdict"].str.startswith("not assessed").all()
    assert table5["p_curvature"].isna().all()


def test_a_run_whose_voltage_trace_panel_is_absent_contributes_no_rows():
    absent = _comparison(label="other", panel=_panel(absent="no voltage trace"))
    table = AE.table_from_build(_build(_comparison(), absent), checked_lo_hz=7.8,
                                checked_hi_hz=28.3, band_half_hz=2.5)
    assert set(table["run_label"]) == {_comparison().label}
    assert len(AE.table_from_build({}, checked_lo_hz=7.8, checked_hi_hz=28.3,
                                   band_half_hz=2.5)) == 0


@pytest.fixture
def sandbox(monkeypatch):
    from CacheStore import ledger
    st = AD._cache_store
    root = tempfile.mkdtemp(prefix="bravo_amp_effect_")
    monkeypatch.setattr(AD, "_SHARED_CACHE_DIR_OVERRIDE", root)
    monkeypatch.setattr(ledger, "ENABLED", False)
    monkeypatch.setattr(st, "ENABLED", True)
    monkeypatch.setattr(AD, "recording_set_signature", lambda p: ("PARTICIPANT", 1, 2, "rs1"))
    monkeypatch.setattr(AD, "_tiles_key_for", lambda p: "raw_lsb_tiles/PARTICIPANT/tiles1")
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _entries(root):
    d = os.path.join(root, AE.KIND)
    return sorted(f for f in os.listdir(d) if f.endswith(".parquet")) if os.path.isdir(d) else []


def test_the_table_is_written_once_with_the_tile_entry_in_its_provenance_and_stim_optimizer_may_read_it(
        sandbox):
    st = AD._cache_store
    first = AD.write_amplitude_effect("PARTICIPANT", _build(_comparison()))
    assert first["written"] is True and first["n_rows"] == 4 and first["n_runs"] == 1
    assert first["store_key"].startswith("amplitude_effect_by_band/PARTICIPANT/")
    files = _entries(sandbox)
    assert len(files) == 1
    with open(os.path.join(sandbox, AE.KIND, files[0].replace(".parquet", ".meta.json"))) as fh:
        meta = json.load(fh)
    assert meta["writer"] == "closed_loop"
    assert [(c["kind"], c["key"]) for c in meta["provenance"]] == \
        [("raw_lsb_tiles", "raw_lsb_tiles/PARTICIPANT/tiles1")]
    # the same inputs write nothing more
    second = AD.write_amplitude_effect("PARTICIPANT", _build(_comparison()))
    assert second["store_key"] == first["store_key"] and _entries(sandbox) == files
    # Stim Optimizer may read it: its chain is raw, so the refusal does not fire
    kind, uid, _h = first["store_key"].split("/")
    sig = AD.amplitude_effect_signature("PARTICIPANT",
                                        tiles_key="raw_lsb_tiles/PARTICIPANT/tiles1")
    # the summary a later request gets without building every run again
    later = AD.amplitude_effect_if_stored("PARTICIPANT")
    assert later["served_from_store"] is True and later["n_rows"] == 4 and later["n_runs"] == 1
    assert later["store_key"] == first["store_key"] and later["stored_utc"]
    got = st.load(kind, uid, sig, consumer="stim_optimizer", root=sandbox)
    assert got is not None and len(got) == 4
    assert list(got.columns) == list(AE.table_from_build(
        _build(_comparison()), checked_lo_hz=7.8, checked_hi_hz=28.3, band_half_hz=2.5).columns)


def test_a_new_recording_set_is_a_new_entry(sandbox, monkeypatch):
    AD.write_amplitude_effect("PARTICIPANT", _build(_comparison()))
    monkeypatch.setattr(AD, "recording_set_signature", lambda p: ("PARTICIPANT", 1, 3, "rs2"))
    out = AD.write_amplitude_effect("PARTICIPANT", _build(_comparison()))
    assert out["written"] is True
    assert len(_entries(sandbox)) == 1, "the superseded entry is swept, as for every derived kind"


def test_without_a_tile_key_the_table_is_derived_but_not_stored(sandbox, monkeypatch):
    monkeypatch.setattr(AD, "_tiles_key_for", lambda p: None)
    out = AD.write_amplitude_effect("PARTICIPANT", _build(_comparison()))
    assert out["written"] is False and out["n_rows"] == 4 and "not stored" in out["reason"]
    assert _entries(sandbox) == []


def test_nothing_stored_means_no_summary(sandbox):
    assert AD.amplitude_effect_if_stored("PARTICIPANT") is None


def test_no_run_is_reported_not_written():
    out = AD.write_amplitude_effect("PARTICIPANT", {"comparisons": [], "absent_reason": "none"})
    assert out == {"written": False, "n_rows": 0, "n_runs": 0, "reason": "none"}


def test_pooled_shape_for_band_pools_raw_pairs_across_runs():
    """Two runs of the same log-linear rising 10.5 Hz band, same contact: the pooled function
    must see both runs' points together (more than either run alone) and read the same rising
    direction."""
    band = CENTRES[0]
    out = AE.pooled_shape_for_band(
        _build(_comparison(label="run A"), _comparison(label="run B")), band, "ONE_THREE_LEFT")
    assert out["n"] == 2 * len(CURRENTS)
    assert out["n_visits"] == 2
    assert out["pooled_direction"] == "band power rises as current rises"
    assert out["pooled_slope_per_mA"] > 0
    assert out["pooled_slope_p"] < 0.05


def test_pooled_shape_for_band_groups_by_run_label_even_when_visit_date_is_shared():
    """Two runs sharing one calendar visit_date, with different labels, must still be treated as
    two separate ladders for the per-run-intercept design -- confirms the grouping key passed to
    `within_visit.amplitude_response_shape_pooled` is the run's own label, not the visit date, per
    `pooled_shape_for_band`'s own contract (a different side, contact or rate is a different
    ladder even on the same calendar day)."""
    band = CENTRES[0]
    comp_a = _comparison(label="run A", visit_date="2026-08-18")
    comp_b = _comparison(label="run B", visit_date="2026-08-18")
    out = AE.pooled_shape_for_band(_build(comp_a, comp_b), band, "ONE_THREE_LEFT")
    assert out["n_visits"] == 2


def test_pooled_shape_for_band_never_pools_a_different_sensing_contact():
    """A run on a different electrode must be excluded entirely, even though it shares the same
    band centre and an overlapping current range -- pooling across contacts would average two
    physically different channels' dose-response curves together, which decision 55/56's own
    per-visit design was never meant to paper over."""
    band = CENTRES[0]
    same_contact = _comparison(label="run A", sensing_contact="ONE_THREE_LEFT")
    other_contact = _comparison(label="run B", sensing_contact="ZERO_TWO_LEFT")
    build = _build(same_contact, other_contact)

    out = AE.pooled_shape_for_band(build, band, "ONE_THREE_LEFT")
    assert out["n"] == len(CURRENTS), "only the matching contact's points should be pooled"
    assert out["n_visits"] == 1

    out_other = AE.pooled_shape_for_band(build, band, "ZERO_TWO_LEFT")
    assert out_other["n"] == len(CURRENTS)
    assert out_other["n_visits"] == 1

    out_absent = AE.pooled_shape_for_band(build, band, "ONE_THREE_RIGHT")
    assert out_absent["pooled_direction"] == "not assessed"
    assert out_absent["n"] == 0


def test_pooled_shape_for_band_with_nothing_usable_is_not_assessed():
    empty_build = AE.pooled_shape_for_band(_build(), CENTRES[0], "ONE_THREE_LEFT")
    assert empty_build["pooled_direction"] == "not assessed"
    assert empty_build["verdict"].startswith("not assessed")

    absent = _comparison(label="other", panel=_panel(absent="no voltage trace"))
    out = AE.pooled_shape_for_band(_build(absent), CENTRES[0], "ONE_THREE_LEFT")
    assert out["pooled_direction"] == "not assessed"

    off_grid = AE.pooled_shape_for_band(_build(_comparison()), 999.0, "ONE_THREE_LEFT")
    assert off_grid["pooled_direction"] == "not assessed"


def test_raw_pairs_for_band_matches_the_table_rows_powers_exactly():
    """`_raw_pairs_for_band`, the helper `pooled_shape_for_band` is built on, must read exactly
    the same (current, power) pairs `rows_for_comparison` puts in the table for that band --
    proof that extracting the shared `_raw_pairs`/`_panel_grid` helpers changed nothing about
    what one run's own row already reported (the pure-refactor half of this change)."""
    comp = _comparison()
    table = AE.table_from_build(_build(comp), checked_lo_hz=7.8, checked_hi_hz=28.3,
                                band_half_hz=2.5).set_index("band_center_hz")
    for centre in CENTRES:
        x, yy = AE._raw_pairs_for_band(comp, centre)
        assert x.tolist() == CURRENTS
        assert float(yy[np.argmin(x)]) == pytest.approx(table.loc[centre, "power_at_min_current"])
        assert float(yy[np.argmax(x)]) == pytest.approx(table.loc[centre, "power_at_max_current"])
