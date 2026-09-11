"""The stored per-run points behind the pooled three-source view (redesign decisions 5 and 10).

The rules held here are the ones decision 103 established for the pooled table: a table from a
truncated build is never stored -- not even derived -- and the reader groups what was stored rather
than computing anything new.
"""
import pandas as pd

try:
    from modules.ClosedLoopDeployment import adapter, run_points
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import adapter, run_points


# --------------------------------------------------------------------------------------------
# 1. a partial table is never stored
# --------------------------------------------------------------------------------------------

def test_a_points_table_from_a_truncated_build_is_refused(monkeypatch):
    called = []
    monkeypatch.setattr(run_points, "run_points_table_from_build",
                        lambda *a, **k: called.append(1) or pd.DataFrame())
    got = adapter.write_run_points(object(), {"comparisons": [{"x": 1}]}, is_every_run=False)
    assert got["written"] is False and got["n_rows"] == 0
    assert "fraction of the visits" in got["reason"]
    assert not called, "the table was derived before the refusal"


def test_a_build_with_no_runs_is_reported_not_stored():
    got = adapter.write_run_points(object(), {"comparisons": []}, is_every_run=True)
    assert got["written"] is False
    assert "no run of rising current" in got["reason"]


def test_an_absent_reason_from_the_build_is_carried_through():
    got = adapter.write_run_points(
        object(), {"comparisons": [], "absent_reason": "the recordings could not be decoded"},
        is_every_run=True)
    assert got["written"] is False and got["reason"] == "the recordings could not be decoded"


def test_the_new_kind_is_registered_with_its_writer():
    try:
        from modules.CacheStore import provenance as prov
    except ImportError:                                          # pragma: no cover
        from CacheStore import provenance as prov
    assert prov._WRITER_BY_KIND[run_points.KIND] == "closed_loop"
    assert run_points.KIND not in prov.RAW_KINDS


# --------------------------------------------------------------------------------------------
# 2. the view groups the stored rows and computes nothing new
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
