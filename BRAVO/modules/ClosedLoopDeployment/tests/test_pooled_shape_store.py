"""The stored pooled within-visit table, and the rule that a partial pool is never written.

WHY THIS EXISTS. The consistency check (decision 74) combines two links: current -> power, pooled
across every stimulation-current ladder, and power -> pain from the calibrated grid. When the check
was first wired into `report_for_participant` it pooled from `_3build` — and that build is truncated
to the runs the PAGE draws whenever the amplitude-effect and ground-truth entries already exist,
which is the steady state after the first request.

Measured live on RCS08, ONE_THREE_LEFT at 17.5 Hz, the same band on the same day:

    cold cache, every run  -> 13 points across 4 visits, "no straight-line movement detected"
    warm cache, 4 runs     ->  6 points across 1 visit,  "not assessed"

The 13 across 4 is exactly what decision 56 measured for this contact. **An answer that depends on
what happened to be cached is not a finding**, and the wrong half of that pair is the one a reader
would almost always have seen. The fix is a stored table pooled from every run, read on every
request — proven live afterwards to give 13 points across 4 visits cold, warm, and warm again.

These tests hold the two rules that keep it that way.

Merged here 2026-10-05: test_run_points_store.py.
"""
import pandas as pd
import pytest

try:
    from modules.ClosedLoopDeployment import adapter, amplitude_effect, direction_consistency, run_points
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import adapter, amplitude_effect, direction_consistency, run_points


# --------------------------------------------------------------------------------------------
# 1. a partial table is never stored, for either stored table: the pooled within-visit table
#    (`write_pooled_shape`) and the per-run points behind the pooled three-source view
#    (`write_run_points`, from test_run_points_store.py)
# --------------------------------------------------------------------------------------------
# id -> (the adapter's writer, the module, the module's table-from-build function, its kind)
_TABLES = {
    "pooled_shape": ("write_pooled_shape", amplitude_effect, "pooled_table_from_build", "POOLED_KIND"),
    "run_points": ("write_run_points", run_points, "run_points_table_from_build", "KIND"),
}


@pytest.mark.parametrize("table", list(_TABLES))
def test_a_table_from_a_truncated_build_is_refused(monkeypatch, table):
    """THE RULE THAT MATTERS. A stored wrong answer is worse than no stored answer, because
    everything downstream then trusts it."""
    writer, module, derive, _ = _TABLES[table]
    called = []
    monkeypatch.setattr(module, derive, lambda *a, **k: called.append(1) or pd.DataFrame())

    got = getattr(adapter, writer)(object(), {"comparisons": [{"x": 1}]}, is_every_run=False)

    assert got["written"] is False
    assert got["n_rows"] == 0
    assert "fraction of the visits" in got["reason"]
    assert not called, (
        "the table was derived before the refusal — it must not even be computed from a truncated "
        "build, or a later edit could accidentally store it")


@pytest.mark.parametrize("table", list(_TABLES))
def test_a_build_with_no_runs_is_reported_not_stored(table):
    got = getattr(adapter, _TABLES[table][0])(object(), {"comparisons": []}, is_every_run=True)
    assert got["written"] is False
    assert "no run of stepped current" in got["reason"]


@pytest.mark.parametrize("table", list(_TABLES))
def test_an_absent_reason_from_the_build_is_carried_through(table):
    got = getattr(adapter, _TABLES[table][0])(
        object(), {"comparisons": [], "absent_reason": "the recordings could not be decoded"},
        is_every_run=True)
    assert got["written"] is False
    assert got["reason"] == "the recordings could not be decoded"


@pytest.mark.parametrize("table", list(_TABLES))
def test_the_new_kind_is_registered_with_its_writer(table):
    """A derived kind written with no registered writer looks like a raw input to anything that
    later cites it (decision 39)."""
    try:
        from modules.CacheStore import provenance as prov
    except ImportError:                                          # pragma: no cover
        from CacheStore import provenance as prov
    _, module, _, kind_attr = _TABLES[table]
    kind = getattr(module, kind_attr)
    assert prov._WRITER_BY_KIND[kind] == "closed_loop"
    assert kind not in prov.RAW_KINDS, "a stored table is derived from the tile entry, not a raw input"


# --------------------------------------------------------------------------------------------
# 2. the check reads the stored row rather than re-pooling
# --------------------------------------------------------------------------------------------

def test_for_band_uses_the_stored_row_and_does_not_pool_again(monkeypatch):
    """If `for_band` ever re-pools while holding a stored row, the truncation defect returns
    silently — the answer would look the same in a cold test and be wrong in production."""
    pooled_calls = []
    monkeypatch.setattr(amplitude_effect, "pooled_shape_for_band",
                        lambda *a, **k: pooled_calls.append(1) or {})

    stored = {"pooled_direction": "band power rises as current rises",
              "pooled_slope_per_mA": 0.4, "pooled_slope_p": 0.01, "n": 13, "n_visits": 4}
    grid = {"available": True, "band_time_sweep": {"L": {"best_correlation_rows": [
        {"band_center_hz": 17.5, "pearson_r": -0.5, "p_selection_aware": 0.01}]}}}

    got = direction_consistency.for_band({"comparisons": []}, grid, "L", 17.5, pooled=stored)

    assert not pooled_calls, "for_band re-pooled from the build despite being handed a stored row"
    assert got["within_visit_n_points"] == 13
    assert got["within_visit_n_visits"] == 4
    # rises with current, and higher power means LESS pain -> raising current should relieve
    assert "relieve" in got["implied_control_direction"]


def test_without_a_stored_row_for_band_still_pools_from_the_build(monkeypatch):
    """The build path is kept, not deleted — a caller that genuinely holds every run may use it,
    and the tests do."""
    monkeypatch.setattr(amplitude_effect, "pooled_shape_for_band",
                        lambda *a, **k: {"pooled_direction": "not assessed"})
    got = direction_consistency.for_band({"comparisons": []}, None, "L", 17.5)
    assert got["implied_control_direction"] == "not assessed"


# --------------------------------------------------------------------------------------------
# 3. reading one row out of the table
# --------------------------------------------------------------------------------------------

def _table():
    return pd.DataFrame([
        {"sensing_contact": "L", "band_center_hz": 17.5, "pooled_direction": "rises",
         "pooled_slope_per_mA": 0.4, "pooled_slope_stderr": 0.1, "pooled_slope_p": 0.01,
         "n": 13, "n_visits": 4, "verdict": "ok", "curves": False, "peaks_inside": False,
         "peak_mA": float("nan"), "p_curvature": float("nan"), "r2_linear": 0.5,
         "r2_quadratic": 0.5},
        {"sensing_contact": "R", "band_center_hz": 17.5, "pooled_direction": "falls",
         "pooled_slope_per_mA": -0.2, "pooled_slope_stderr": 0.1, "pooled_slope_p": 0.04,
         "n": 9, "n_visits": 3, "verdict": "ok", "curves": False, "peaks_inside": False,
         "peak_mA": float("nan"), "p_curvature": float("nan"), "r2_linear": 0.4,
         "r2_quadratic": 0.4},
    ])


def test_pooled_row_matches_on_contact_and_centre_together():
    """Two contacts share a band centre. Matching on the centre alone would hand back another
    electrode's dose-response — the conflation decision 74's own contact fix already had to correct
    once."""
    left = amplitude_effect.pooled_row(_table(), "L", 17.5)
    right = amplitude_effect.pooled_row(_table(), "R", 17.5)
    assert left["pooled_direction"] == "rises" and left["n_visits"] == 4
    assert right["pooled_direction"] == "falls" and right["n_visits"] == 3


def test_pooled_row_is_none_when_the_point_is_not_in_the_table():
    assert amplitude_effect.pooled_row(_table(), "L", 29.5) is None
    assert amplitude_effect.pooled_row(_table(), "MISSING", 17.5) is None
    assert amplitude_effect.pooled_row(None, "L", 17.5) is None
    assert amplitude_effect.pooled_row(pd.DataFrame(), "L", 17.5) is None


def test_the_stored_row_carries_every_field_the_check_reads():
    row = amplitude_effect.pooled_row(_table(), "L", 17.5)
    for k in ("pooled_direction", "pooled_slope_per_mA", "pooled_slope_p", "n", "n_visits"):
        assert k in row, f"{k} is missing, and direction_consistency reads it"

# --------------------------------------------------------------------------------------------
# The stored per-run points (from test_run_points_store.py, merged 2026-10-05)
# --------------------------------------------------------------------------------------------
# The stored per-run points behind the pooled three-source view (redesign decisions 5 and 10).
#
# The rules held here are the ones decision 103 established for the pooled table: a table from a
# truncated build is never stored -- not even derived -- and the reader groups what was stored rather
# than computing anything new.


# --------------------------------------------------------------------------------------------
# 4. the run-points view groups the stored rows and computes nothing new
# --------------------------------------------------------------------------------------------

def _points():
    """Two runs on the right contact (two visits), one on a left contact; the time-domain route
    covers two bands, the direct route the compared band only, the PSD route nothing."""
    rows = []
    def td(run, visit, side, contact, rate, centre_prog, current, centre, power, pieces, striped=False):
        rows.append(dict(source=run_points.ROUTE_TIME_DOMAIN, run=run, visit_date=visit,
                         ramped_side=side, sensing_contact=contact, stimulation_rate_hz=rate,
                         programmed_centre_hz=centre_prog, window_start_local=f"{visit} 10:00:00",
                         band_centre_hz=centre, current_mA=current,
                         settled_band_power_device_units=power, n_pieces_averaged=pieces,
                         band_is_measuring_the_stimulator=striped, why_not_used="",
                         route_absent_reason=""))
    for cur, p in ((1.0, 700.0), (1.5, 720.0), (2.0, 690.0)):
        td("r1", "2026-08-18", "Right", "ZERO_THREE_RIGHT", 55.0, 17.5, cur, 17.5, p, 10)
        td("r1", "2026-08-18", "Right", "ZERO_THREE_RIGHT", 55.0, 17.5, cur, 18.5, p + 5, 10, True)
    for cur, p in ((2.0, 650.0), (2.5, 640.0)):
        td("r2", "2025-10-21", "Right", "ZERO_THREE_RIGHT", 145.0, 9.5, cur, 17.5, p, 8)
        td("r2", "2025-10-21", "Right", "ZERO_THREE_RIGHT", 145.0, 9.5, cur, 18.5, p + 5, 8)
    td("l1", "2025-08-21", "Left", "ONE_THREE_LEFT", 110.0, 12.5, 1.0, 17.5, 500.0, 6)
    td("l1", "2025-08-21", "Left", "ONE_THREE_LEFT", 110.0, 12.5, 1.5, 17.5, 510.0, 6)
    # direct route, compared band only, run r1
    for cur, p in ((1.0, 710.0), (1.5, 730.0), (2.0, 700.0)):
        rows.append(dict(source=run_points.ROUTE_DEVICE_BAND_POWER, run="r1", visit_date="2026-08-18",
                         ramped_side="Right", sensing_contact="ZERO_THREE_RIGHT",
                         stimulation_rate_hz=55.0, programmed_centre_hz=17.5,
                         window_start_local="2026-08-18 10:00:00", band_centre_hz=17.5,
                         current_mA=cur, settled_band_power_device_units=p, n_pieces_averaged=60,
                         band_is_measuring_the_stimulator=False, why_not_used="",
                         route_absent_reason=""))
    # PSD route, nothing, run r1
    rows.append(dict(source=run_points.ROUTE_DEVICE_SPECTRUM, run="r1", visit_date="2026-08-18",
                     ramped_side="Right", sensing_contact="ZERO_THREE_RIGHT", stimulation_rate_hz=55.0,
                     programmed_centre_hz=17.5, window_start_local="2026-08-18 10:00:00",
                     band_centre_hz=None, current_mA=None, settled_band_power_device_units=None,
                     n_pieces_averaged=0, band_is_measuring_the_stimulator=None, why_not_used="",
                     route_absent_reason="the device computed no spectrum during this run"))
    return pd.DataFrame(rows)


def _pooled():
    return pd.DataFrame([
        {"sensing_contact": "ZERO_THREE_RIGHT", "band_center_hz": 17.5,
         "pooled_direction": "band power falls as current rises", "pooled_slope_per_mA": -0.05,
         "pooled_slope_stderr": 0.01, "pooled_slope_p": 0.02, "n": 5, "n_visits": 2,
         "verdict": "ok", "curves": False, "peaks_inside": False, "peak_mA": float("nan"),
         "p_curvature": 0.4, "r2_linear": 0.6, "r2_quadratic": 0.61},
        {"sensing_contact": "ONE_THREE_LEFT", "band_center_hz": 17.5,
         "pooled_direction": "not assessed", "pooled_slope_per_mA": float("nan"),
         "pooled_slope_stderr": float("nan"), "pooled_slope_p": float("nan"), "n": 2,
         "n_visits": 1, "verdict": "not assessed: 2 usable points", "curves": False,
         "peaks_inside": False, "peak_mA": float("nan"), "p_curvature": float("nan"),
         "r2_linear": float("nan"), "r2_quadratic": float("nan")},
    ])


def test_the_view_groups_by_side_then_contact_then_run_newest_first():
    v = run_points.pooled_view_payload(_points(), _pooled())
    assert v["gates_nothing"] is True
    assert [s["ramped_side"] for s in v["sides"]] == ["Right", "Left"]
    right = v["sides"][0]["contacts"]
    assert [c["sensing_contact"] for c in right] == ["ZERO_THREE_RIGHT"]
    c = right[0]
    assert c["n_runs"] == 2 and c["n_visits"] == 2 and c["stimulation_rates_hz"] == [55.0, 145.0]
    assert [r["run"] for r in c["runs"]] == ["r1", "r2"], "newest visit first"
    assert v["n_runs"] == 3


def test_the_time_domain_block_is_a_currents_by_centres_matrix_with_values_copied_verbatim():
    v = run_points.pooled_view_payload(_points(), _pooled())
    r1 = v["sides"][0]["contacts"][0]["runs"][0]
    td = r1["routes"]["time_domain"]
    assert td["currents_mA"] == [1.0, 1.5, 2.0]
    assert td["centres_hz"] == [17.5, 18.5]
    assert td["power"] == [[700.0, 705.0], [720.0, 725.0], [690.0, 695.0]]
    assert td["n_pieces"] == [10, 10, 10]
    assert td["striped"] == [False, True]
    assert r1["programmed_centre_hz"] == 17.5 and r1["stimulation_rate_hz"] == 55.0


def test_the_direct_route_carries_its_one_band_and_the_psd_route_its_reason():
    v = run_points.pooled_view_payload(_points(), _pooled())
    r1 = v["sides"][0]["contacts"][0]["runs"][0]
    direct = r1["routes"]["direct"]
    assert direct["centres_hz"] == [17.5] and direct["power"] == [[710.0], [730.0], [700.0]]
    psd = r1["routes"]["psd"]
    assert psd["currents_mA"] == [] and "no spectrum" in psd["absent_reason"]


def test_the_pooled_rows_are_attached_per_contact_and_never_across_contacts():
    v = run_points.pooled_view_payload(_points(), _pooled())
    right = v["sides"][0]["contacts"][0]["pooled_by_centre"]
    left = v["sides"][1]["contacts"][0]["pooled_by_centre"]
    assert len(right) == 1 and right[0]["pooled_slope_per_mA"] == -0.05
    assert right[0]["curvature_note"] == "ok" and "verdict" not in right[0]
    assert left[0]["pooled_direction"] == "not assessed" and left[0]["pooled_slope_per_mA"] is None


def test_the_view_says_so_when_nothing_is_stored():
    v = run_points.pooled_view_payload(None, None, absent_reason="not yet")
    assert v["sides"] == [] and v["absent_reason"] == "not yet"
    v2 = run_points.pooled_view_payload(pd.DataFrame(), None)
    assert "written the next time" in v2["absent_reason"]


def test_the_table_builder_adds_the_programmed_centre_and_start_to_every_row(monkeypatch):
    # Patch the module object run_points itself resolves (`from . import three_source_response`):
    # under the two import spellings this package can carry two module objects, and patching the
    # other one leaves the real comparison_rows in place (seen in the full host run, 2026-09-11).
    import importlib
    TSR = importlib.import_module(run_points.__name__.rsplit(".", 1)[0] + ".three_source_response")

    class Comp:
        programmed_centre_hz = 12.5
        window_start_local = "2025-08-21 10:00:00"
    monkeypatch.setattr(TSR, "comparison_rows",
                        lambda comp: [{"source": "x", "run": "l1", "visit_date": "2025-08-21",
                                       "ramped_side": "Left", "sensing_contact": "L",
                                       "band_centre_hz": 17.5, "current_mA": 1.0,
                                       "settled_band_power_device_units": 1.0}])
    t = run_points.run_points_table_from_build({"comparisons": [Comp(), Comp()]})
    assert len(t) == 2
    assert list(t["programmed_centre_hz"]) == [12.5, 12.5]
    assert list(t["window_start_local"]) == ["2025-08-21 10:00:00"] * 2


# --------------------------------------------------------------------------------------------
# 3. the anchor the pooled line is drawn through (decision 12): each run counts once
# --------------------------------------------------------------------------------------------

def test_the_anchor_is_the_mean_of_per_run_centroids_not_of_all_points():
    x = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5,  1.0, 1.5]
    y = [600.0, 610.0, 620.0, 630.0, 640.0, 650.0,  400.0, 410.0]
    runs = ["six-settings"] * 6 + ["two-settings"] * 2
    a = run_points.pooled_line_anchor(x, y, runs)
    # run centroids: (2.25, 625) and (1.25, 405) -> their mean, not the all-point mean (1.9, 570)
    assert a == {"x": 1.75, "y": 515.0, "n_runs": 2}
    assert run_points.pooled_line_anchor([], [], []) is None


def test_the_anchor_is_attached_per_centre_in_linear_device_units():
    v = run_points.pooled_view_payload(_points(), _pooled())
    row = v["sides"][0]["contacts"][0]["pooled_by_centre"][0]
    # r1 centroid at 17.5 Hz: (1.5, 703.33...); r2: (2.25, 645) -> mean (1.875, 674.1666...)
    assert row["anchor"]["n_runs"] == 2
    assert abs(row["anchor"]["x"] - 1.875) < 1e-9
    assert abs(row["anchor"]["y"] - (703.3333333333334 + 645.0) / 2) < 1e-9
