"""Review of 2026-09-12, finding S8: the safety model's limit anchors come from the participant's
own settings stream, per side, with a sensing group's limit excluded while its adaptive therapy
is running (decision 136's rule, imported), behind `plots.USE_STREAM_LIMIT_ANCHORS`.

Values: which (rate, upper) pairs survive, which are excluded and why, which side each fit
reads, and that the switch restores the hard-coded snapshot exactly.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import adapter as AD
from StimOptimizer import pipeline as PL
from StimOptimizer import stage1_openloop as S1
from StimOptimizer.routines import plots as PLT


# ---------------------------------------------------------------------------------------------
# the stream carries whether each limit is a patient limit
# ---------------------------------------------------------------------------------------------
def _sensing_channel(side, upper, status):
    return {"HemisphereLocation": f"HemisphereLocationDef.{side}", "SuspendAmplitudeInMilliAmps": 2.0,
            "PulseWidthInMicroSecond": 100, "RateInHertz": 55, "UpperLimitInMilliAmps": upper,
            "LowerLimitInMilliAmps": 1.0, "AdaptiveTherapyStatus": status,
            "ElectrodeState": [{"Electrode": "ElectrodeDef.SenSight_1", "ElectrodeStateResult": "Negative"}]}


def test_a_sensing_limit_under_running_adaptive_therapy_is_not_a_patient_limit():
    g = {"ProgramSettings": {"SensingChannel": [
        _sensing_channel("Left", 3.0, "AdaptiveTherapyStatusDef.RUNNING"),
        _sensing_channel("Right", 4.0, "AdaptiveTherapyStatusDef.NOT_CONFIGURED")]}}
    out = AD.group_settings(g)
    assert out["Left"]["upper"] == 3.0 and out["Left"]["upper_is_patient_limit"] is False
    assert out["Right"]["upper"] == 4.0 and out["Right"]["upper_is_patient_limit"] is True
    assert out["Left"]["schema"] == "sensing"


def test_a_legacy_program_limit_is_a_patient_limit_and_no_limit_is_none():
    g = {"ProgramSettings": {"RateInHertz": 110, "LeftHemisphere": {"Programs": [
        {"AmplitudeInMilliAmps": 2.0, "PulseWidthInMicroSecond": 60, "UpperLimitInMilliAmps": 3.2,
         "ElectrodeState": []}]}, "RightHemisphere": {"Programs": [
        {"AmplitudeInMilliAmps": 2.0, "PulseWidthInMicroSecond": 60, "ElectrodeState": []}]}}}
    out = AD.group_settings(g)
    assert out["Left"]["upper_is_patient_limit"] is True and out["Left"]["schema"] == "hemisphere"
    assert out["Right"]["upper"] is None and out["Right"]["upper_is_patient_limit"] is None


def test_the_rule_is_the_closed_loop_modules_not_a_copy():
    import inspect
    src = inspect.getsource(AD._sensing_upper_is_patient_limit)
    assert "session_report_facts" in src and "_patient_limits_configured" in src
    # the comparison itself lives in the imported rule; only the docstring names the status here
    assert '== "RUNNING"' not in src and "AdaptiveTherapyStatus" not in src.split('"""')[2]


def test_the_stream_rule_version_was_bumped_for_the_new_column():
    assert AD._THERAPY_SETTINGS_RULE_VERSION == "v2_active_groups_limit_kind"
    import inspect
    assert '"upper_is_patient_limit"' in inspect.getsource(AD._build_settings_stream)


# ---------------------------------------------------------------------------------------------
# the anchor builder
# ---------------------------------------------------------------------------------------------
def _stream():
    t = pd.to_datetime(["2026-01-01"] * 8, utc=True)
    return pd.DataFrame(dict(
        t=t, src="history",
        hemi=["Left", "Left", "Left", "Left", "Right", "Right", "Right", "Right"],
        amp=[2.0] * 8, pw=[100.0] * 8,
        rate=[55.0, 55.0, 110.0, 130.0, 55.0, 55.0, 10.0, 165.0],
        upper=[2.0, 3.0, 4.0, np.nan, 2.5, 3.5, 2.0, 2.5],
        upper_is_patient_limit=[True, False, True, None, False, True, True, None],
        schema=["hemisphere", "sensing", "sensing", "hemisphere", "sensing", "sensing",
                "hemisphere", "sensing"],
        cathode=["1"] * 8))


def test_left_anchors_keep_legacy_and_patient_sensing_limits_and_drop_the_adaptive_one():
    a, m = PLT.limit_anchors_from_stream(_stream(), "Left", use_stream=True)
    assert a.tolist() == [[55.0, 2.0], [110.0, 4.0]]
    assert m["n_rows_with_upper"] == 3 and m["n_kept"] == 2
    assert m["n_excluded_adaptive_limit"] == 1 and m["n_excluded_unknown_kind"] == 0
    assert m["source"].startswith("the participant's settings stream")
    assert m["hemisphere"] == "Left"


def test_right_anchors_are_the_right_sides_own_and_an_unknown_kind_is_excluded():
    a, m = PLT.limit_anchors_from_stream(_stream(), "Right", use_stream=True)
    assert a.tolist() == [[10.0, 2.0], [55.0, 3.5]]
    assert m["n_excluded_adaptive_limit"] == 1 and m["n_excluded_unknown_kind"] == 1


def test_a_legacy_row_is_kept_whatever_the_kind_column_says():
    s = _stream()
    s.loc[s["schema"] == "hemisphere", "upper_is_patient_limit"] = None
    a, _ = PLT.limit_anchors_from_stream(s, "Left", use_stream=True)
    assert [55.0, 2.0] in a.tolist()


def test_the_switch_off_returns_the_hard_coded_snapshot_exactly():
    a, m = PLT.limit_anchors_from_stream(_stream(), "Left", use_stream=False)
    np.testing.assert_array_equal(a, PLT.LIMIT_ANCHORS)
    assert "USE_STREAM_LIMIT_ANCHORS off" in m["source"]
    assert PLT.USE_STREAM_LIMIT_ANCHORS is False   # off until the PI decides (decision 143)


def test_no_usable_anchor_falls_back_and_says_why():
    s = _stream()
    s = s[s["hemi"] == "Left"].copy()
    s["schema"] = "sensing"
    s["upper_is_patient_limit"] = False
    a, m = PLT.limit_anchors_from_stream(s, "Left", use_stream=True)
    np.testing.assert_array_equal(a, PLT.LIMIT_ANCHORS)
    assert "no usable limit anchor" in m["source"] and "3 adaptive limits excluded" in m["source"]
    a2, m2 = PLT.limit_anchors_from_stream(None, "Left", use_stream=True)
    np.testing.assert_array_equal(a2, PLT.LIMIT_ANCHORS)
    assert "no settings stream" in m2["source"]


def test_nulls_read_back_from_parquet_do_not_break_the_kind_test():
    s = _stream()
    s["upper_is_patient_limit"] = pd.array([True, False, True, pd.NA, False, True, True, pd.NA],
                                           dtype="boolean")
    a, m = PLT.limit_anchors_from_stream(s, "Right", use_stream=True)
    assert a.tolist() == [[10.0, 2.0], [55.0, 3.5]] and m["n_excluded_unknown_kind"] == 1


# ---------------------------------------------------------------------------------------------
# the plumbing: each side's fit reads its own anchors, and the meta says so
# ---------------------------------------------------------------------------------------------
def _design(n=16, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for ep in range(1, n + 1):
        rows.append(dict(epoch=float(ep), freq_hz=float([55.0, 110.0][ep % 2]),
                         pw_us_Left=60.0, pw_us_Right=150.0,
                         amp_mA_Left=float(1.0 + 0.3 * (ep % 4)),
                         amp_mA_Right=float(1.2 + 0.3 * (ep % 3)),
                         n=8.0, dur_h=200.0,
                         left_leg_vas=float(50.0 + 3.0 * rng.standard_normal()),
                         left_leg_vas_sd=8.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    return d


#: An anchor at every grid rate, at 1.0 mA: measured on `_design()` 2026-09-12, the Left arm's
#: safe set is 57 of 612 cells under these against 247 under the hard-coded twelve, and 612 (the
#: whole grid) under one or two anchors -- the safety model constrains little between rates that
#: carry no anchor, which is why a count under a one-anchor set is not a useful pin.
TIGHT = np.array([[float(f), 1.0] for f in PLT.FREQ_GRID])


def test_each_arm_reads_its_own_sides_anchors_and_records_them():
    by_side = {"Left": (TIGHT, {"source": "left test"}),
               "Right": (np.array([[55.0, 4.5], [110.0, 4.0]]), {"source": "right test"})}
    rep = PL.run(_design(), sites=("left_leg",), outdir=None, render_figures=False,
                 data_horizon="t", washin_min=1.0, limit_anchors_by_hemisphere=by_side)
    ml, mr = rep.arms["left_leg__Left"].meta, rep.arms["left_leg__Right"].meta
    assert ml["limit_anchors"] == TIGHT.tolist() and ml["limit_anchors_source"] == "left test"
    assert mr["limit_anchors"] == [[55.0, 4.5], [110.0, 4.0]] and mr["n_limit_anchors"] == 2
    # the anchors reach the safety model: the Left arm under the tight set against the default
    assert ml["n_safe"] == 57
    dflt = PL.run(_design(), sites=("left_leg",), outdir=None, render_figures=False,
                  data_horizon="t", washin_min=1.0)
    assert dflt.arms["left_leg__Left"].meta["n_safe"] == 247


def test_per_side_anchors_equal_to_the_default_change_nothing():
    """The control for the switch: handing every side the hard-coded snapshot through the new
    argument gives the same fit, field for field, as not handing anything."""
    by_side = {h: (PLT.LIMIT_ANCHORS, {"source": "hard-coded"}) for h in ("Left", "Right")}
    a = PL.run(_design(), sites=("left_leg",), outdir=None, render_figures=False,
               data_horizon="t", washin_min=1.0, limit_anchors_by_hemisphere=by_side)
    b = PL.run(_design(), sites=("left_leg",), outdir=None, render_figures=False,
               data_horizon="t", washin_min=1.0)
    cols = [c for c in a.summary.columns]
    pd.testing.assert_frame_equal(a.summary[cols], b.summary[cols])
    for arm in a.arms:
        np.testing.assert_array_equal(a.arms[arm].ctx.safe, b.arms[arm].ctx.safe)
        np.testing.assert_array_equal(a.arms[arm].ctx.mu, b.arms[arm].ctx.mu)


def test_without_per_side_anchors_every_arm_reads_the_default_and_says_caller_supplied():
    rep = PL.run(_design(), sites=("left_leg",), outdir=None, render_figures=False,
                 data_horizon="t", washin_min=1.0)
    for arm in rep.arms.values():
        assert arm.meta["limit_anchors"] == PLT.LIMIT_ANCHORS.tolist()
        assert arm.meta["limit_anchors_source"] == "caller-supplied"


def test_stage_1_reads_per_side_anchors_and_writes_them_into_the_audit():
    by_side = {"Left": (np.array([[55.0, 2.0]]), {"source": "left test"}),
               "Right": (np.array([[55.0, 4.5]]), {"source": "right test"})}
    res = S1.run_stage1(_design(), data_horizon="t", washin_min=1.0,
                        limit_anchors_by_hemisphere=by_side)
    la_l = res.frozen.audit["per_hemisphere"]["Left"]["limit_anchors"]
    la_r = res.frozen.audit["per_hemisphere"]["Right"]["limit_anchors"]
    assert la_l["anchors"] == [[55.0, 2.0]] and la_l["source"] == "left test" and la_l["n"] == 1
    assert la_r["anchors"] == [[55.0, 4.5]] and la_r["source"] == "right test"
    # the anchors reach Stage 1's safety model: the Left side under a different anchor set has
    # a different safe count, and under the default set the same count as with no argument
    tight = {"Left": (TIGHT, {"source": "tight"})}
    res2 = S1.run_stage1(_design(), hemispheres=("Left",), data_horizon="t", washin_min=1.0,
                         limit_anchors_by_hemisphere=tight)
    n1 = int(res.summary[res.summary["hemisphere"] == "Left"]["n_safe"].iloc[0])
    n2 = int(res2.summary["n_safe"].iloc[0])
    assert (n1, n2) == (612, 57), (n1, n2)
    dflt = {"Left": (PLT.LIMIT_ANCHORS, {"source": "hard-coded"})}
    res3 = S1.run_stage1(_design(), hemispheres=("Left",), data_horizon="t", washin_min=1.0,
                         limit_anchors_by_hemisphere=dflt)
    res4 = S1.run_stage1(_design(), hemispheres=("Left",), data_horizon="t", washin_min=1.0)
    pd.testing.assert_frame_equal(res3.summary, res4.summary)
