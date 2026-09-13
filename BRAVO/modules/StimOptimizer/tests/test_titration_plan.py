"""The titration session the Stim Optimizer recommends for the next visit (`titration_plan.py`,
2026-09-12 evening: open item 30 and the 20 s post-ramp margin of decision 144 joined into one
recommendation).

Values, never shapes: the ladder never exceeds the stated ceiling and rounds DOWN; a rate below
55 Hz is lifted to 55 with the reason; the harmonic-avoidance lists for 55, 110 and 145 Hz are
pinned centre by centre; the hold is at least 60 s and leaves at least 10 usable 3 s pieces after
the margin; the points-yield arithmetic; `post_ramp.margin_becomes_available` on a constructed
table with a 6-setting run (False) and an 8-setting run (True); and the service response carries
`titration_plan` for both sides with every `source` non-empty.
"""
import shutil
import sys
import tempfile
import types

import numpy as np
import pandas as pd
import pytest

from ClosedLoopDeployment import amplitude_effect as AE
from ClosedLoopDeployment import post_ramp as PR
from StimOptimizer import titration_plan as TP
from StimOptimizer.routines import percept_adaptive as PA
from StimOptimizer.routines import within_visit as WV


# ---------------------------------------------------------------------------------------------
# the ladder
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("ceiling", [5.0, 4.8, 3.0, 0.5, 2.25, 6.0])
def test_the_ladder_never_exceeds_the_stated_ceiling_and_goes_up_then_down(ceiling):
    lad = TP.ladder(ceiling)
    assert max(lad["steps_mA"]) <= ceiling + 1e-9
    assert lad["top_mA"] == max(lad["steps_mA"])
    assert lad["steps_mA"][0] == 0.0 and lad["steps_mA"][-1] == 0.0
    # up in 0.5 mA steps, the top held once, then down the same steps
    up = lad["steps_mA"][: lad["n_distinct_currents"]]
    assert up == [round(0.5 * i, 3) for i in range(lad["n_distinct_currents"])]
    assert lad["steps_mA"] == up + list(reversed(up[:-1]))
    assert lad["n_steps"] == 2 * lad["n_distinct_currents"] - 1


def test_the_ladder_for_the_stated_5_mA_ceiling_is_11_currents_and_21_steps():
    lad = TP.ladder(5.0)
    assert lad["top_mA"] == 5.0
    assert lad["n_distinct_currents"] == 11 and lad["n_steps"] == 21
    assert lad["steps_mA"] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0,
                               4.5, 4.0, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0, 0.5, 0.0]
    assert lad["compact"] == "0 → 0.5 → … → 5.0 → … → 0 mA"


def test_a_ceiling_that_is_not_a_multiple_of_the_step_rounds_down_and_says_so():
    lad = TP.ladder(4.8)
    assert lad["top_mA"] == 4.5 and lad["n_distinct_currents"] == 10 and lad["n_steps"] == 19
    assert "not a multiple of 0.5 mA" in lad["why"]


def test_no_ceiling_means_no_ladder_and_a_reason():
    for bad in (None, 0.0, -1.0, float("nan")):
        lad = TP.ladder(bad)
        assert lad["steps_mA"] == [] and lad["n_steps"] == 0 and lad["top_mA"] is None
        assert "no ceiling" in lad["why"]


# ---------------------------------------------------------------------------------------------
# the rate
# ---------------------------------------------------------------------------------------------
def test_a_rate_below_55_hz_is_lifted_to_55_with_the_reason():
    r = TP.rate_to_hold(40.0)
    assert r["rate_hz"] == 55.0 and r["rate_in_force_hz"] == 40.0 and r["lifted"] is True
    assert "40 Hz" in r["why"] and "55 Hz" in r["why"] and "decision 138" in r["why"]
    assert PA.MIN_ADAPTIVE_RATE_HZ == 55.0


def test_a_rate_at_or_above_55_hz_is_held_as_is():
    for rate in (55.0, 110.0, 145.0):
        r = TP.rate_to_hold(rate)
        assert r["rate_hz"] == rate and r["lifted"] is False and f"{rate:g} Hz" in r["why"]


def test_no_rate_on_record_means_the_adaptive_minimum_and_says_so():
    r = TP.rate_to_hold(None)
    assert r["rate_hz"] == 55.0 and r["rate_in_force_hz"] is None and r["lifted"] is True
    assert "no stimulation rate is on record" in r["why"]


# ---------------------------------------------------------------------------------------------
# the harmonic avoidance, pinned on the VALUES
# ---------------------------------------------------------------------------------------------
def test_the_22_centres_are_8_5_to_29_5_hz():
    assert list(TP.CENTRES_HZ) == [8.5 + i for i in range(22)]


def test_harmonic_avoidance_at_55_hz():
    h = TP.harmonic_avoidance(55.0)
    assert h["harmonics_hz"] == {"folded_about_250_hz": 195.0, "half_rate": 27.5,
                                 "quarter_rate": 13.75, "three_quarters_rate": 41.25}
    # 13.75 +/- 2.5 -> 11.25..16.25 catches 11.5, 12.5, 13.5, 14.5, 15.5; 27.5 +/- 2.5 -> 25..30
    # catches 25.5, 26.5, 27.5, 28.5, 29.5; 195 and 41.25 are outside the grid.
    assert h["avoid_hz"] == [11.5, 12.5, 13.5, 14.5, 15.5, 25.5, 26.5, 27.5, 28.5, 29.5]
    assert h["clear_hz"] == [8.5, 9.5, 10.5, 16.5, 17.5, 18.5, 19.5, 20.5, 21.5, 22.5, 23.5, 24.5]
    assert h["n_clear"] == 12 and h["n_avoid"] == 10
    assert "13.75 Hz" in h["avoid_reasons"]["13.5"] and "quarter" in h["avoid_reasons"]["13.5"]
    assert "27.5 Hz" in h["avoid_reasons"]["29.5"] and "half" in h["avoid_reasons"]["29.5"]


def test_harmonic_avoidance_at_110_hz():
    h = TP.harmonic_avoidance(110.0)
    assert h["harmonics_hz"] == {"folded_about_250_hz": 140.0, "half_rate": 55.0,
                                 "quarter_rate": 27.5, "three_quarters_rate": 82.5}
    assert h["avoid_hz"] == [25.5, 26.5, 27.5, 28.5, 29.5]
    assert h["n_clear"] == 17
    assert h["clear_hz"][0] == 8.5 and h["clear_hz"][-1] == 24.5


def test_harmonic_avoidance_at_145_hz_leaves_every_centre_clear():
    h = TP.harmonic_avoidance(145.0)
    assert h["harmonics_hz"] == {"folded_about_250_hz": 105.0, "half_rate": 72.5,
                                 "quarter_rate": 36.25, "three_quarters_rate": 108.75}
    assert h["avoid_hz"] == [] and h["n_clear"] == 22


def test_a_candidate_centre_is_judged_the_same_way():
    h = TP.harmonic_avoidance(55.0, candidate_center_hz=24.5)
    assert h["candidate_clear"] is True and "clear" in h["candidate_note"]
    h2 = TP.harmonic_avoidance(55.0, candidate_center_hz=27.5)
    assert h2["candidate_clear"] is False and "27.5 Hz" in h2["candidate_note"]


# ---------------------------------------------------------------------------------------------
# the hold
# ---------------------------------------------------------------------------------------------
def test_the_hold_is_at_least_60_s_and_leaves_at_least_10_usable_pieces_after_the_margin():
    h = TP.hold_per_step()
    assert h["seconds"] >= 60.0
    assert h["seconds"] == 30.0 + 20.0 + 10.0
    assert h["settled_window_s"] == WV.PRE_CHANGE_WINDOW_S == 30.0
    assert h["post_ramp_margin_s"] == WV.RAMP_EXCLUDE_S == 20.0
    assert h["piece_s"] == WV.CHUNK_S == 3.0
    assert h["min_pieces_required"] == WV.MIN_CHUNKS_PRE_CHANGE == 10
    assert h["usable_pieces_after_margin"] == 13 >= h["min_pieces_required"]
    assert "30 s settled window" in h["why"] and "20 s" in h["why"] and "10 s of slack" in h["why"]


# ---------------------------------------------------------------------------------------------
# the per-run points table and the margin
# ---------------------------------------------------------------------------------------------
def _run_rows(run, currents, contact="ONE_THREE_LEFT", source="time domain voltage trace",
              centres=(20.5, 24.5), value=100.0):
    rows = []
    for c in currents:
        for f in centres:
            rows.append(dict(run=run, sensing_contact=contact, source=source, current_mA=float(c),
                             band_centre_hz=float(f), settled_band_power_device_units=value))
    return rows


def test_margin_becomes_available_is_false_on_a_six_setting_run_and_true_on_an_eight_setting_run():
    six = pd.DataFrame(_run_rows("2026-08-18 L", [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]))
    m = PR.margin_becomes_available(six)
    assert m["available"] is False and m["min_settled_settings"] == AE.MIN_POINTS_CURVATURE == 8
    assert m["max_settled_settings_in_one_run"] == 6 and m["run"] == "2026-08-18 L"
    assert m["n_runs"] == 1 and m["runs_at_or_above_floor"] == []
    assert "no run holds 8 settled settings" in m["note"] and "6" in m["note"]
    assert m["switch_on"] is False and PR.USE_POST_RAMP_MARGIN is False   # NOT flipped here

    eight = pd.DataFrame(_run_rows("titration L", [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]))
    m2 = PR.margin_becomes_available(pd.concat([six, eight], ignore_index=True))
    assert m2["available"] is True and m2["n_runs"] == 2
    assert m2["max_settled_settings_in_one_run"] == 8 and m2["run"] == "titration L"
    assert m2["runs_at_or_above_floor"] == [{"run": "titration L", "sensing_contact": "ONE_THREE_LEFT",
                                             "n_settled_settings": 8}]


def test_margin_counts_settled_values_on_the_voltage_trace_route_only_and_distinct_currents():
    # eight currents but two of them carry no settled value -> 6; and a device route with eight
    # settled currents does not count
    rows = _run_rows("r", [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]) + \
        _run_rows("r", [3.0, 3.5], value=float("nan")) + \
        _run_rows("r", [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5], source="device's own band power")
    m = PR.margin_becomes_available(pd.DataFrame(rows))
    assert m["max_settled_settings_in_one_run"] == 6 and m["available"] is False
    # the same current at two band centres is ONE setting
    per = TP.settled_settings_per_run(pd.DataFrame(_run_rows("r", [1.0, 1.0, 2.0], centres=(10.5, 11.5, 12.5))))
    assert per["n_settled_settings"].tolist() == [2]


def test_margin_on_no_table_says_nothing_was_counted():
    m = PR.margin_becomes_available(None)
    assert m["available"] is False and m["table_stored"] is False
    assert "not stored" in m["note"] and m["max_settled_settings_in_one_run"] is None
    m2 = PR.margin_becomes_available(pd.DataFrame())
    assert m2["available"] is False and m2["table_stored"] is True and m2["n_runs"] == 0


# ---------------------------------------------------------------------------------------------
# what the record holds today, and the yield arithmetic
# ---------------------------------------------------------------------------------------------
def _pooled(contact="ONE_THREE_LEFT"):
    return pd.DataFrame([
        dict(sensing_contact=contact, band_center_hz=20.5, n=13, n_visits=4),
        dict(sensing_contact=contact, band_center_hz=24.5, n=11, n_visits=3),
        dict(sensing_contact=contact, band_center_hz=72.5, n=40, n_visits=9),   # outside 8-30 Hz
        dict(sensing_contact="ZERO_THREE_RIGHT", band_center_hz=20.5, n=12, n_visits=6),
    ])


def test_record_today_reads_the_best_covered_centre_inside_the_adaptive_window_for_that_contact():
    runs = pd.DataFrame(_run_rows("a", [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]) + _run_rows("b", [1.0, 2.0, 3.0]))
    rec = TP.record_today_for_contact(_pooled(), runs, "ONE_THREE_LEFT", lo_hz=8.0, hi_hz=30.0)
    assert rec["points"] == 13 and rec["runs"] == 4 and rec["band_center_hz"] == 20.5
    assert rec["n_centres_at_max"] == 1 and rec["n_centres_in_window"] == 2   # 72.5 Hz is outside
    assert rec["max_settled_settings_in_one_run"] == 6 and rec["n_runs_on_contact"] == 2
    assert "13 settled points across 4 runs" in rec["note"] and "at most 6 settled currents" in rec["note"]
    assert "1 of 2 centres" in rec["note"]
    other = TP.record_today_for_contact(_pooled(), runs, "ZERO_THREE_RIGHT", lo_hz=8.0, hi_hz=30.0)
    assert other["points"] == 12 and other["runs"] == 6 and other["max_settled_settings_in_one_run"] is None
    assert "no run on this contact" in other["note"]


def test_record_today_with_no_tables_says_so_rather_than_zero():
    rec = TP.record_today_for_contact(None, None, "ONE_THREE_LEFT")
    assert rec["points"] is None and rec["max_settled_settings_in_one_run"] is None
    assert rec["pooled_table_stored"] is False and rec["run_points_table_stored"] is False
    assert "not stored yet" in rec["note"]
    none = TP.record_today_for_contact(_pooled(), None, None)
    assert "no sensing contact" in none["note"]


def _side(**kw):
    base = dict(rate_in_force_hz=55.0, rate_source="stream", pulse_width_us=100.0,
                pulse_width_source="stream", ceiling_mA=5.0, ceiling_source="stated by PI",
                contact={"channel": "ONE_THREE_LEFT", "display_short": "L 1⁻3⁺", "n_responding": 12,
                         "n_bands": 18, "laterality": "ipsilateral", "deployable": True,
                         "rate_hz": 55.0, "sensing_side": "Left"},
                contact_source="the readiness screen",
                record_today=TP.record_today_for_contact(
                    _pooled(), pd.DataFrame(_run_rows("a", [1.0, 1.5, 2.0, 2.5, 3.0, 3.5])),
                    "ONE_THREE_LEFT", lo_hz=8.0, hi_hz=30.0))
    base.update(kw)
    return base


def test_the_points_yield_arithmetic_and_the_margin_sentence():
    runs = pd.DataFrame(_run_rows("a", [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]))
    margin = PR.margin_becomes_available(runs)
    p = TP.side_plan("Left", margin=margin, **_side())
    y = p["yield"]
    assert y["settled_points_from_session"] == 21 == p["ladder"]["n_steps"]
    assert y["distinct_currents_up_leg"] == 11
    assert y["min_settled_settings_for_margin"] == 8
    assert y["session_clears_margin_floor"] is True          # 11 >= 8
    assert y["run_with_enough_settings_exists_today"] is False
    assert y["margin_switched_on_today"] is False
    s = y["sentence"]
    assert "13 settled points across 4 runs" in s and "at most 6 currents in any one run" in s
    assert "21 settled points" in s and "11 distinct currents" in s
    assert "no run in the record has the 8 settled settings" in s and "stays off" in s


def test_a_lifted_rate_changes_the_band_list_and_the_source_names_the_minimum():
    p = TP.side_plan("Right", margin=PR.margin_becomes_available(None), **_side(rate_in_force_hz=40.0))
    assert p["rate_hz"] == 55.0 and p["rate_lifted"] is True
    assert p["bands"]["rate_hz"] == 55.0 and p["bands"]["avoid_hz"][:2] == [11.5, 12.5]
    assert "MIN_ADAPTIVE_RATE_HZ" in p["sources"]["rate_hz"] and "decision 138" in p["sources"]["rate_hz"]


def test_a_contralateral_contact_is_named_as_on_the_other_side():
    c = {"channel": "ZERO_THREE_RIGHT", "display_short": "R 0⁻3⁺", "n_responding": 9, "n_bands": 18,
         "laterality": "contralateral", "deployable": True, "rate_hz": 55.0, "sensing_side": "Right"}
    p = TP.side_plan("Left", margin=PR.margin_becomes_available(None), **_side(contact=c))
    assert p["sensing_contact"]["on_other_side"] is True
    assert "OTHER side" in p["sensing_contact"]["note"] and "Right" in p["sensing_contact"]["note"]
    p2 = TP.side_plan("Left", margin=PR.margin_becomes_available(None), **_side(contact=None))
    assert p2["sensing_contact"] is None and "no sensing contact is named" in p2["sensing_contact_note"]


def test_every_source_is_non_empty_and_every_number_has_one():
    p = TP.side_plan("Left", margin=PR.margin_becomes_available(None), **_side())
    src = p["sources"]
    for k in ("rate_hz", "pulse_width_us", "ceiling_mA", "sensing_contact", "ladder", "hold", "bands",
              "yield.settled_points_from_session", "yield.record_today", "yield.margin", "conditions"):
        assert isinstance(src.get(k), str) and src[k].strip(), k
    for k in ("rate_hz", "pulse_width_us", "ceiling_mA"):
        assert p[k] is not None
    assert "decision 133" in p["conditions"][2] and "FIXED measurement current" in p["conditions"][2]
    assert "streaming on" in p["conditions"][0] and "baseline before" in p["conditions"][1]


# ---------------------------------------------------------------------------------------------
# the service response carries the block for both sides
# ---------------------------------------------------------------------------------------------
def _matrix(n=8):
    rows = []
    for k in range(n):
        rows.append(dict(epoch=float(k + 1), freq_hz=55.0, pw_us_Left=100.0, pw_us_Right=150.0,
                         amp_mA_Left=1.0 + 0.5 * (k % 4), amp_mA_Right=1.5 + 0.5 * (k % 3),
                         cathode_Left="2a-2b-2c", cathode_Right="1a-1b-1c",
                         n=8.0, dur_h=200.0, state="bilateral_active",
                         left_leg_vas=50.0 + k, left_leg_vas_sd=8.0, back_vas=40.0 + k, back_vas_sd=8.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    d["t_end"] = d["t0"] + pd.Timedelta(days=2)
    return d


def _screen():
    return pd.DataFrame([
        dict(channel="ONE_THREE_LEFT", hemisphere="Left", rate_hz=55.0, n_bands=18, n_responding=12,
             responding_fraction=0.667, median_separation_d=0.9, laterality="ipsilateral",
             sensing_side="Left", deployable=True),
        dict(channel="ZERO_THREE_RIGHT", hemisphere="Right", rate_hz=55.0, n_bands=18, n_responding=4,
             responding_fraction=0.222, median_separation_d=0.3, laterality="ipsilateral",
             sensing_side="Right", deployable=False),
    ])


class _Arm:
    def __init__(self, hemi):
        self.site, self.hemisphere = "left_leg", hemi
        self.queue = pd.DataFrame({"rank": [1], "freq_hz": [55.0], "amp_mA": [2.0], "score": [0.3]})
        self.batch = self.queue.copy()
        self.meta = {"incumbent_mu": 0.4, "mu_star": -0.6, "sd_star": 0.9, "incumbent_sd": 0.9,
                     "x_star": [55.0, 2.0], "data_horizon": "h", "washin_min": 1.0,
                     "amp_col": f"amp_mA_{hemi}", "n_epochs_fitted": 8, "kernel": "rbf",
                     "safe_is_contiguous": True, "safe_contiguous_ceiling": float("nan")}
        self.ctx = types.SimpleNamespace(meta=self.meta)

    def surface_can_resolve_its_optimum(self, k=1.0):
        return False


class _Report:
    def __init__(self):
        self.arms = {"left_leg__Left": _Arm("Left"), "left_leg__Right": _Arm("Right")}
        self.summary = pd.DataFrame({"arm": list(self.arms), "n_epochs": [8, 8]})
        self.manifest = {"declared": "stub"}

    def recommendation_is_supported(self):
        return False


@pytest.fixture
def bench(monkeypatch):
    import importlib
    from StimOptimizer import adapter as AD
    from StimOptimizer import bravo_service as BS
    st = BS._cache_store
    _ledger = importlib.import_module(st.__name__.rsplit(".", 1)[0] + ".ledger")
    root = tempfile.mkdtemp(prefix="bravo_so_titration_")
    monkeypatch.setattr(BS, "_SHARED_CACHE_DIR_OVERRIDE", root)
    monkeypatch.setattr(AD, "_SHARED_CACHE_DIR_OVERRIDE", root)
    monkeypatch.setattr(_ledger, "ENABLED", False)
    monkeypatch.setattr(st, "ENABLED", True)
    models = types.ModuleType("Server.models")
    models.Participant = types.SimpleNamespace(find=lambda uid: types.SimpleNamespace(uid=uid))
    server = types.ModuleType("Server"); server.models = models
    monkeypatch.setitem(sys.modules, "Server", server)
    monkeypatch.setitem(sys.modules, "Server.models", models)
    stream = pd.DataFrame({"t": pd.to_datetime(["2026-01-01"], utc=True)})
    monkeypatch.setattr(AD, "settings_stream", lambda p, **kw: stream)
    es = _matrix()
    monkeypatch.setattr(AD, "build_design_matrix", lambda p, rd=None, **kw: es.copy())
    monkeypatch.setattr(AD, "evidence_inputs", lambda p, **kw: (None, None))
    monkeypatch.setattr(BS, "_tiles_key_for", lambda p: (None, "no tiles in this test"))
    monkeypatch.setattr(BS, "_blockers", lambda rep, arms, observed=None: [])
    monkeypatch.setattr(BS.pipeline, "run", lambda es, **kw: _Report())

    def readiness(p, es, include=True, inputs=None, screen_out=None, **kw):
        if screen_out is not None:
            screen_out["screen"] = _screen()
        return {"available": True, "ready": True, "verdict": "stubbed"}
    monkeypatch.setattr(BS, "closed_loop_readiness", readiness)
    yield types.SimpleNamespace(root=root, es=es, BS=BS)
    shutil.rmtree(root, ignore_errors=True)


def test_the_response_carries_a_titration_plan_for_both_sides_with_every_source_non_empty(bench):
    out = bench.BS.run_for_participant({"ParticipantId": "P", "Backend": "none",
                                        "Hemispheres": ["Left", "Right"]})
    assert out.get("available") is True, out.get("reason")
    tp = out["titration_plan"]
    assert tp["available"] is True
    assert set(tp["sides"]) == {"Left", "Right"}
    for side, p in tp["sides"].items():
        assert p["side"] == side
        assert p["rate_hz"] == 55.0 and p["rate_lifted"] is False
        assert p["pulse_width_us"] == (100.0 if side == "Left" else 150.0)   # each side's OWN column
        assert p["ceiling_mA"] == 5.0                                        # the module hard limit fallback
        assert "no PI-stated ceiling" in p["sources"]["ceiling_mA"]
        assert p["ladder"]["n_steps"] == 21 and p["hold"]["seconds"] == 60.0
        assert p["bands"]["avoid_hz"] == [11.5, 12.5, 13.5, 14.5, 15.5, 25.5, 26.5, 27.5, 28.5, 29.5]
        for k, v in p["sources"].items():
            assert isinstance(v, str) and v.strip(), (side, k)
        assert "setting in force on the" in p["sources"]["rate_hz"]
    # the Left side's best deployable cell; the Right side's cell did not pass and is named as such
    assert tp["sides"]["Left"]["sensing_contact"]["channel"] == "ONE_THREE_LEFT"
    assert tp["sides"]["Left"]["sensing_contact"]["n_responding"] == 12
    assert "best deployable cell" in tp["sides"]["Left"]["sources"]["sensing_contact"]
    assert "at the session's rate, 55 Hz" in tp["sides"]["Left"]["sources"]["sensing_contact"]
    assert tp["sides"]["Right"]["sensing_contact"]["channel"] == "ZERO_THREE_RIGHT"
    assert "did not pass" in tp["sides"]["Right"]["sensing_contact"]["note"] or \
        "no contact on this side passed" in tp["sides"]["Right"]["sensing_contact"]["note"]
    # no stored tables in the scratch root: said, not counted as zero
    assert tp["margin"]["table_stored"] is False and tp["margin"]["available"] is False
    assert "no entry is stored" in tp["stored_tables"]["pooled"] and "no entry is stored" in tp["stored_tables"]["run_points"]
    assert tp["sides"]["Left"]["yield"]["record_today"]["points"] is None
    # JSON-safe: no numpy scalars anywhere
    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        else:
            assert not isinstance(o, (np.generic,)), type(o)
    walk(tp)


def test_a_contact_that_passed_only_at_another_rate_is_named_with_that_rate(bench, monkeypatch):
    BS = bench.BS

    def readiness(p, es, include=True, inputs=None, screen_out=None, **kw):
        sc = _screen()
        sc.loc[sc["hemisphere"] == "Left", "rate_hz"] = 165.0
        if screen_out is not None:
            screen_out["screen"] = sc
        return {"available": True}
    monkeypatch.setattr(BS, "closed_loop_readiness", readiness)
    out = BS.run_for_participant({"ParticipantId": "P", "Backend": "none", "Hemispheres": ["Left"]})
    p = out["titration_plan"]["sides"]["Left"]
    assert p["rate_hz"] == 55.0
    assert p["sensing_contact"]["channel"] == "ONE_THREE_LEFT" and p["sensing_contact"]["rate_hz"] == 165.0
    assert "no cell on this side passed at the session's rate of 55 Hz" in p["sources"]["sensing_contact"]
    assert "from 165 Hz" in p["sources"]["sensing_contact"]


def test_the_plan_is_in_the_stored_response_and_a_readiness_failure_does_not_remove_it(bench, monkeypatch):
    BS = bench.BS
    monkeypatch.setattr(BS, "closed_loop_readiness",
                        lambda p, es, include=True, **kw: {"available": False, "reason": "stubbed off"})
    out = BS.run_for_participant({"ParticipantId": "P", "Backend": "none", "Hemispheres": ["Left"]})
    tp = out["titration_plan"]
    assert tp["available"] is True and set(tp["sides"]) == {"Left"}
    assert tp["sides"]["Left"]["sensing_contact"] is None
    assert "no sensing contact is named" in tp["sides"]["Left"]["sensing_contact_note"]
    assert tp["sides"]["Left"]["ladder"]["n_steps"] == 21
