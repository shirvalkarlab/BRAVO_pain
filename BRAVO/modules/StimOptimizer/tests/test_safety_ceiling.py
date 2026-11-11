"""The safety model's severity-3 seed is a ceiling the PI states, per participant and per side
(`safety_ceiling.py`, 2026-09-12, item 3 of the "Make Closed-Loop Work" session).

Values: which number each side gets and what its provenance says; that the seed is one anchor per
grid rate at that current; that a lower ceiling shrinks the safe set and moves the reachable
ceiling; that the flat fit and Stage 1 seed from the ONE builder and agree; that the gate checks
each side's limits against its own ceiling; and that the fallback for an unknown participant is
the module hard limit and says so.

Merged here 2026-10-05: test_no_current_above_the_ceiling.py (each under its own heading below).
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import pipeline as PL
from StimOptimizer import safety_ceiling as SC
from StimOptimizer import stage1_openloop as S1
from StimOptimizer.routines import objective as OBJ
from StimOptimizer.routines import plots as PLT
from StimOptimizer.routines import stage_gate as GATE
from StimOptimizer.routines import surrogate as SUR
import inspect

from ClosedLoopDeployment import post_ramp as PR
from StimOptimizer import stage2_closedloop as S2
from StimOptimizer import titration_plan as TP

RCS08 = "2e3c75c00d7f4f37b53a048d195f11da"


# ---------------------------------------------------------------------------------------------
# the table and its provenance
# ---------------------------------------------------------------------------------------------
def test_rcs08_reads_the_stated_ceiling_on_both_sides_with_the_pi_provenance():
    """4.5 mA on both sides as of 2026-09-14 (his words: "make max safe amp on each side 4.5 mA,
    PI decided"); the earlier 5.0 mA value is named in the provenance as history, not served."""
    for side in ("Left", "Right"):
        c, why = SC.ceiling_for(RCS08, side)
        assert c == 4.5
        assert why == SC.PI_STATED_PROVENANCE
        assert "stated by PI" in why and "2026-09-14" in why and "5.0 mA" in why


def test_an_unknown_participant_falls_back_to_the_module_hard_limit_and_says_so():
    c, why = SC.ceiling_for("nobody", "Left")
    assert c == OBJ.AMP_HARD_LIMIT_MA
    assert why == SC.FALLBACK_PROVENANCE and "no PI-stated ceiling" in why
    c2, why2 = SC.ceiling_for(None, None)
    assert (c2, why2) == (c, why)


def test_a_side_missing_from_the_table_falls_back_but_the_other_side_does_not(monkeypatch):
    monkeypatch.setitem(SC.PI_STATED_CEILING_MA, "p", {"Left": 3.0})
    assert SC.ceiling_for("p", "Left") == (3.0, SC.PI_STATED_PROVENANCE)
    assert SC.ceiling_for("p", "Right") == (OBJ.AMP_HARD_LIMIT_MA, SC.FALLBACK_PROVENANCE)
    by = SC.ceilings_by_hemisphere("p", ("Left", "Right"))
    assert by["Left"][0] == 3.0 and by["Right"][0] == OBJ.AMP_HARD_LIMIT_MA


def test_a_stated_ceiling_above_the_hard_limit_is_clamped_and_the_provenance_says_so(monkeypatch):
    monkeypatch.setitem(SC.PI_STATED_CEILING_MA, "p", {"Left": 7.5})
    c, why = SC.ceiling_for("p", "Left")
    assert c == OBJ.AMP_HARD_LIMIT_MA
    assert "clamped" in why and "7.5" in why


def test_a_non_positive_or_non_numeric_ceiling_is_refused_not_used(monkeypatch):
    monkeypatch.setitem(SC.PI_STATED_CEILING_MA, "p", {"Left": 0.0})
    with pytest.raises(ValueError, match="positive current"):
        SC.ceiling_for("p", "Left")
    monkeypatch.setitem(SC.PI_STATED_CEILING_MA, "p", {"Left": float("nan")})
    with pytest.raises(ValueError):
        SC.ceiling_for("p", "Left")


def test_the_table_is_the_only_place_a_ceiling_number_lives():
    """The plumbing carries `(ceiling, provenance)` tuples built by `ceiling_for`; no other
    module names a participant's current. Read the sources for the uid."""
    import inspect
    for mod in (PLT, S1, PL, GATE):
        assert RCS08 not in inspect.getsource(mod)
    assert RCS08 in inspect.getsource(SC)


# ---------------------------------------------------------------------------------------------
# the seed
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


def test_the_ceiling_anchors_are_one_per_grid_rate_at_the_ceiling():
    a = SC.ceiling_anchors(4.0, PLT.FREQ_GRID)
    assert a.shape == (len(PLT.FREQ_GRID), 2)
    assert a[:, 0].tolist() == [float(f) for f in PLT.FREQ_GRID]
    assert (a[:, 1] == 4.0).all()


def test_tolerated_anchors_exclude_zero_current_and_short_holds():
    D = pd.DataFrame(dict(freq_hz=[55.0, 55.0, 110.0, 110.0],
                          amp_mA_Left=[0.0, 2.0, 3.0, 3.5],
                          dur_h=[500.0, 500.0, 10.0, 72.0]))
    t = SC.tolerated_anchors(D, "amp_mA_Left", min_tolerated_h=72.0)
    assert t.tolist() == [[55.0, 2.0], [110.0, 3.5]]


def test_tolerated_anchors_exclude_epochs_reported_moderate_or_severe():
    """Audit of 2026-09-15: an epoch the sheet scored moderate or severe is barred from the pain
    fit (`objective.SE_HARD_REJECT`, J = +inf) but was still handed to the safety model as a
    severity-0 "tolerated" anchor -- the opposite of what was reported. Only a REPORTED
    intolerable severity excludes; an unreported epoch (None) and a mild one are still tolerated,
    and a frame with no severity column at all is unchanged."""
    D = pd.DataFrame(dict(freq_hz=[55.0, 55.0, 55.0, 55.0],
                          amp_mA_Left=[1.0, 2.0, 3.0, 4.0],
                          dur_h=[500.0, 500.0, 500.0, 500.0],
                          se_severity=[None, "mild", "moderate", "severe"]))
    t = SC.tolerated_anchors(D, "amp_mA_Left", min_tolerated_h=72.0)
    assert t.tolist() == [[55.0, 1.0], [55.0, 2.0]]
    same_without_column = SC.tolerated_anchors(D.drop(columns=["se_severity"]), "amp_mA_Left",
                                               min_tolerated_h=72.0)
    assert same_without_column.tolist() == [[55.0, 1.0], [55.0, 2.0], [55.0, 3.0], [55.0, 4.0]]


def test_the_seed_names_how_many_intolerable_epochs_it_kept_out_of_the_tolerated_set():
    """The report must be able to say "N settings reported intolerable were not counted as
    tolerated", and 0 when the frame carries no severity column."""
    D = pd.DataFrame(dict(freq_hz=[55.0, 55.0, 55.0],
                          amp_mA_Left=[1.0, 3.0, 4.0],
                          dur_h=[500.0, 500.0, 500.0],
                          se_severity=[None, "moderate", "severe"]))
    _X, sev, _v, meta = SC.safety_seed(D, "amp_mA_Left", freq_grid=PLT.FREQ_GRID,
                                       ceiling=(4.5, "test"), min_tolerated_h=72.0)
    assert meta["n_tolerated_anchors"] == 1
    assert meta["n_intolerable_excluded"] == 2
    assert sev.tolist().count(0.0) == 1
    _X, _s, _v, meta0 = SC.safety_seed(D.drop(columns=["se_severity"]), "amp_mA_Left",
                                       freq_grid=PLT.FREQ_GRID, ceiling=(4.5, "test"),
                                       min_tolerated_h=72.0)
    assert meta0["n_tolerated_anchors"] == 3
    assert meta0["n_intolerable_excluded"] == 0


def test_the_seed_has_the_shape_the_safety_model_expects_and_the_severities_are_0_and_3():
    D = _design()
    X, sev, var, meta = SC.safety_seed(D, "amp_mA_Left", freq_grid=PLT.FREQ_GRID,
                                       ceiling=(5.0, "test"), min_tolerated_h=72.0)
    n_tol = int(((D["amp_mA_Left"] > 0) & (D["dur_h"] >= 72.0)).sum())
    assert X.shape == (n_tol + len(PLT.FREQ_GRID), 2)
    assert sev[:n_tol].tolist() == [0.0] * n_tol
    assert sev[n_tol:].tolist() == [OBJ.SE_THRESHOLD] * len(PLT.FREQ_GRID)
    assert (X[n_tol:, 1] == 5.0).all()
    assert meta["safety_ceiling_mA"] == 5.0 and meta["safety_ceiling_provenance"] == "test"
    assert meta["n_safety_ceiling_anchors"] == len(PLT.FREQ_GRID)
    assert meta["n_tolerated_anchors"] == n_tol
    # and it is exactly what the model's own seeder makes of the same two sets
    X2, s2, v2 = SUR.SafetyGP.seed_from_history(
        SC.tolerated_anchors(D, "amp_mA_Left", min_tolerated_h=72.0),
        SC.ceiling_anchors(5.0, PLT.FREQ_GRID))
    np.testing.assert_array_equal(X, X2)
    np.testing.assert_array_equal(sev, s2)
    np.testing.assert_array_equal(var, v2)


def test_a_seed_with_nothing_tolerated_is_refused_by_the_model_not_silently_empty():
    D = pd.DataFrame(dict(freq_hz=[55.0], amp_mA_Left=[0.0], dur_h=[500.0]))
    with pytest.raises(ValueError, match="tolerated anchor"):
        SC.safety_seed(D, "amp_mA_Left", freq_grid=PLT.FREQ_GRID, ceiling=(5.0, "t"))


# ---------------------------------------------------------------------------------------------
# the ceiling reaches the safe set, in both fitters, from one builder
# ---------------------------------------------------------------------------------------------
#: Measured on `_design()` in the container on 2026-09-12 (`_agent_bridge/_probe_tl/
#: probe_ceiling_test_design.py`): the Left arm's safe cells of 612 and its reachable ceiling
#: under a stated ceiling of 5.0 / 4.0 / 3.0 / 2.0 mA were 612 / 5.0, 468 / 3.8, 324 / 2.6 and
#: 240 / 1.9; under 1.0 mA -- BELOW the 1.0-1.9 mA the design tolerated -- 57 cells and no
#: contiguous ceiling. A lower stated ceiling must shrink the safe set and pull the reachable
#: ceiling down; the exact counts pin the seed's arithmetic against a silent change.
#: DECISION 308 (2026-09-26): the safe set also leaves out every cell above the stated ceiling, as a
#: hard bound. Under 5.0 and 2.0 mA that removes nothing (the model's own set already stopped at
#: 5.0 and 1.9 mA); under 1.0 mA it removes 54 of the 57 cells, because the model seeded with
#: severity 3 at 1.0 mA and severity 0 at the 1.0-1.9 mA the design tolerated still called
#: currents ABOVE the stated ceiling safe -- the failure this bound exists for. 3 cells remain.
N_SAFE_LEFT_AT_5 = 612
N_SAFE_LEFT_AT_2 = 240
REACH_LEFT_AT_5 = 5.0
REACH_LEFT_AT_2 = 1.9
N_SAFE_LEFT_AT_1 = 3


def _run(by_side=None):
    return PL.run(_design(), sites=("left_leg",), outdir=None, render_figures=False,
                  data_horizon="t", washin_min=1.0, safety_ceiling_by_hemisphere=by_side)


def test_each_arm_reads_its_own_sides_ceiling_and_records_it_with_its_provenance():
    by = {"Left": (2.0, "left test"), "Right": (4.5, "right test")}
    rep = _run(by)
    ml, mr = rep.arms["left_leg__Left"].meta, rep.arms["left_leg__Right"].meta
    assert (ml["safety_ceiling_mA"], ml["safety_ceiling_provenance"]) == (2.0, "left test")
    assert (mr["safety_ceiling_mA"], mr["safety_ceiling_provenance"]) == (4.5, "right test")
    assert ml["safety_ceiling_anchors"] == [[float(f), 2.0] for f in PLT.FREQ_GRID]
    assert ml["n_safety_ceiling_anchors"] == len(PLT.FREQ_GRID)


def test_a_lower_ceiling_shrinks_the_safe_set_and_the_reachable_ceiling():
    hi = _run({"Left": (5.0, "t"), "Right": (5.0, "t")}).arms["left_leg__Left"].meta
    lo = _run({"Left": (2.0, "t"), "Right": (5.0, "t")}).arms["left_leg__Left"].meta
    assert (hi["n_safe"], lo["n_safe"]) == (N_SAFE_LEFT_AT_5, N_SAFE_LEFT_AT_2)
    assert (hi["safe_contiguous_ceiling"], lo["safe_contiguous_ceiling"]) == (REACH_LEFT_AT_5,
                                                                              REACH_LEFT_AT_2)
    # no safe cell sits above the stated ceiling
    assert max(lo["safe_amps"]) <= 2.0 + 1e-9


def test_a_ceiling_below_what_was_tolerated_leaves_no_contiguous_ceiling_rather_than_a_made_up_one():
    m = _run({"Left": (1.0, "t"), "Right": (5.0, "t")}).arms["left_leg__Left"].meta
    assert m["n_safe"] == N_SAFE_LEFT_AT_1
    assert m["safe_is_contiguous"] is False
    assert np.isnan(m["safe_contiguous_ceiling"])
    # nothing above the stated ceiling is safe, and the arm is still reported (decision 308): the
    # forward simulation stops and says why instead of losing the arm to "no eligible candidates"
    assert max(m["safe_amps"]) <= 1.0 + 1e-9
    assert m["forward_simulation_note"].startswith("stopped after 1 of 3 batches")


def test_without_a_ceiling_argument_every_arm_reads_the_hard_limit_and_says_no_ceiling_was_stated():
    rep = _run(None)
    for arm in rep.arms.values():
        assert arm.meta["safety_ceiling_mA"] == OBJ.AMP_HARD_LIMIT_MA
        assert arm.meta["safety_ceiling_provenance"] == SC.FALLBACK_PROVENANCE


# Stage 1 runs here without its calibration check (`calibration_check=False`, 2026-10-02): a
# warning that changes no recommendation (decision 233, ruling 6), read by no test in this file,
# and held by `test_stratum_calibration.py`; its leave-one-out refits were most of each fit's time.
def test_the_flat_fit_and_stage_1_seed_from_one_builder_and_agree_on_the_anchors():
    """Until 2026-09-12 the two fitters seeded from different epoch sets (Stage 1 counted a side's
    0 mA epochs as tolerated at zero current; the flat fit did not), so the same side under the
    same anchors had two safe sets. Now both call `safety_ceiling.safety_seed`.

    REWRITTEN 2026-09-14 for the joint redesign: the flat fit's own safe count and Stage 1's can
    no longer be compared directly, because Stage 1 now scores a JOINT (rate, amp-Left,
    amp-Right) grid and the flat fit still scores a 2-D (rate, amp) grid of a different shape and
    a different cell count -- the two were never going to have equal cell counts once the grids
    themselves differ, whatever the anchors say. What both fitters MUST still agree on is what
    they were TOLD: the same ceiling, the same provenance, and the same count of tolerated
    (rate, current) anchors from the same epochs, since both call the one shared seed builder on
    the same design frame.
    """
    D = _design()
    # give the Left side some 0 mA epochs so the old difference would show
    D.loc[D["epoch"] <= 4, "amp_mA_Left"] = 0.0
    by = {"Left": (3.0, "t"), "Right": (5.0, "t")}
    flat = PL.run(D, sites=("left_leg",), hemispheres=("Left",), outdir=None,
                  render_figures=False, data_horizon="t", washin_min=1.0,
                  safety_ceiling_by_hemisphere=by).arms["left_leg__Left"]
    s1 = S1.run_stage1(D, data_horizon="t", washin_min=1.0, safety_ceiling_by_hemisphere=by,
                       calibration_check=False)
    audit = s1.frozen.audit["per_hemisphere"]["Left"]["safety_ceiling"]
    assert audit["safety_ceiling_mA"] == 3.0 and audit["safety_ceiling_provenance"] == "t"
    assert audit["n_tolerated_anchors"] == flat.meta["n_tolerated_anchors"]
    # the 0 mA epochs are not tolerated anchors in either fitter
    assert audit["n_tolerated_anchors"] == int((D["amp_mA_Left"] > 0).sum())


def test_stage_1_reads_each_sides_own_ceiling_and_a_stricter_ceiling_shrinks_the_joint_safe_set():
    """REWRITTEN 2026-09-14: the exact safe-cell count on the joint grid depends on the joint
    grid's own resolution (``JOINT_AMP_GRID``), which is coarser than the flat fit's 2-D
    ``plots.AMP_GRID`` on purpose (a 3-D grid otherwise multiplies the cell count roughly
    50-fold) -- so the historical magic count pinned to the 2-D grid no longer applies. What must
    still hold: each side's own stated ceiling and provenance reach the audit, and a STRICTER
    ceiling on one side shrinks the JOINT safe set (never grows it), because the joint safe mask
    is the AND of both sides' own per-side safety models.
    """
    d = _design()
    by_strict = {"Left": (2.0, "left test"), "Right": (4.5, "right test")}
    by_loose = {"Left": (5.0, "left test"), "Right": (4.5, "right test")}
    res = S1.run_stage1(d, data_horizon="t", washin_min=1.0,
                        safety_ceiling_by_hemisphere=by_strict, calibration_check=False)
    a_l = res.frozen.audit["per_hemisphere"]["Left"]["safety_ceiling"]
    a_r = res.frozen.audit["per_hemisphere"]["Right"]["safety_ceiling"]
    assert (a_l["safety_ceiling_mA"], a_l["safety_ceiling_provenance"]) == (2.0, "left test")
    assert (a_r["safety_ceiling_mA"], a_r["safety_ceiling_provenance"]) == (4.5, "right test")
    n_strict = int(res.summary[res.summary["hemisphere"] == "Left"]["n_safe"].iloc[0])

    loose = S1.run_stage1(d, data_horizon="t", washin_min=1.0,
                          safety_ceiling_by_hemisphere=by_loose, calibration_check=False)
    n_loose = int(loose.summary[loose.summary["hemisphere"] == "Left"]["n_safe"].iloc[0])
    assert n_strict < n_loose, (n_strict, n_loose)


# ---------------------------------------------------------------------------------------------
# the gate checks each side against its own ceiling
# ---------------------------------------------------------------------------------------------
def _frozen(hi_left=4.0, hi_right=4.0, star_left=2.0, star_right=2.0):
    settings = tuple(
        S1.HemisphereSetting(hemisphere=h, rate_hz=55.0, pw_us=100.0, amp_star_mA=star,
                             amp_delivered_min_mA=1.0, amp_delivered_max_mA=hi, n_epochs_fitted=20,
                             rate_resolved=True, pw_resolved=True, reasons=("fixture",))
        for h, hi, star in (("Left", hi_left, star_left), ("Right", hi_right, star_right)))
    return S1.FrozenConfiguration(
        settings=settings, primary_item="left_leg", incumbent_epoch=1.0, incumbent_rate_hz=55.0,
        incumbent_pw_us=100.0, data_horizon="test", washin_min=1.0, n_epochs_total=40)


def test_the_gate_judges_each_side_against_its_own_ceiling_and_reports_both():
    fz = _frozen(hi_left=4.0, hi_right=4.0)
    by = {"Left": (3.5, "left test"), "Right": (5.0, "right test")}
    c = GATE.check_amplitude_limits(fz, amp_limits={"Left": (1.0, 4.0), "Right": (1.0, 4.0)},
                                    ceiling_mA=by)
    assert c.passed is False
    assert "Left: upper limit 4 mA exceeds the declared ceiling of 3.5 mA" in c.detail
    assert "Right: upper limit" not in c.detail
    ev = c.evidence
    assert ev["ceiling_mA"] == 3.5
    assert ev["ceiling_by_side"] == {"Left": dict(ceiling_mA=3.5, provenance="left test"),
                                     "Right": dict(ceiling_mA=5.0, provenance="right test")}


def test_a_plain_number_still_works_and_carries_no_by_side_block():
    fz = _frozen()
    c = GATE.check_amplitude_limits(fz, amp_limits={"Left": (1.0, 4.0), "Right": (1.0, 4.0)},
                                    ceiling_mA=5.0)
    assert c.passed is True and c.evidence["ceiling_mA"] == 5.0
    assert "ceiling_by_side" not in c.evidence


# ================================================================================================
# From test_no_current_above_the_ceiling.py (merged here 2026-10-05).
# No current above a side's safe ceiling is proposed, recommended, scheduled or exported (decision 308).
#
# Decision 306 capped every current the Closed-Loop page recommends at the PI-stated ceiling (4.5 mA
# per side on RCS08, `safety_ceiling.PI_STATED_CEILING_MA`). Its agent found, read-only, the places in
# the Stim Optimizer that could still name a higher one:
#
# 1. the titration ladders held the side not being stepped at its current in force, never checked
#    against that side's ceiling, and copied it into every ladder row and the Google-sheet export;
# 2. the "what to test next" queue was built from the whole 0-5.0 mA grid with no ceiling filter;
# 3. the per-arm fit's queue and batches were bounded only by the 5.0 mA module limit;
# 4. Stage 2's amplitude windows used the 5.0 mA module limit while the gate checked 4.5 mA;
# 5. the optimum per rate, the best current inside the allowed range and the batches were bounded
#    only by the safety model's SOFT safe set, which on RCS08 carries a tolerated 4.8 mA;
# 6. the next-visit list fell back to a typed 4.5 mA.
#
# Each test below builds the situation that let the value through -- a current in force, or a
# tolerated current, ABOVE the stated ceiling, as on RCS08 -- and reads every value the module offers
# as one to deliver. History (currents delivered in the past) is not tested here: it may be shown,
# labelled as history.
# ================================================================================================

TOL = 1e-9


# ---------------------------------------------------------------------------------------------
# 1. the titration ladders' held side
# ---------------------------------------------------------------------------------------------
def _side(ceiling_mA=4.5):
    return dict(rate_in_force_hz=55.0, rate_source="stream", pulse_width_us=100.0,
                pulse_width_source="stream", ceiling_mA=ceiling_mA, ceiling_source="stated by PI",
                contact={"channel": "ONE_THREE_LEFT", "display_short": "L 1-3", "n_responding": 12,
                         "n_bands": 18, "laterality": "ipsilateral", "deployable": True,
                         "rate_hz": 55.0, "sensing_side": "Left"},
                contact_source="the readiness screen", record_today={})


def _in_force(left_mA, right_mA):
    return {"Left": {"amplitude_mA": left_mA, "contacts_short": "L C+2-", "pulse_width_us": 100.0,
                     "source": "the settings stream"},
            "Right": {"amplitude_mA": right_mA, "contacts_short": "R C+1-2-", "pulse_width_us": 150.0,
                      "source": "the settings stream"}}


def _amps(cell):
    """The two currents a clinic-sheet row asks to deliver, from its bilateral 'L x / R y' cell."""
    s = str(cell)
    left = float(s.split("/")[0].replace("L", "").strip())
    right = float(s.split("/")[1].replace("R", "").strip())
    return left, right


def test_a_held_current_in_force_above_the_ceiling_is_held_at_the_ceiling_and_says_so():
    margin = PR.margin_becomes_available(None)
    out = TP.plan_for_sides({"Left": _side(), "Right": _side()}, margin=margin,
                            in_force=_in_force(3.0, 4.8),
                            ceilings={"Left": (4.5, "t"), "Right": (4.5, "t")})
    held = out["sides"]["Left"]["held_other_side"]          # the Left ladder holds the Right
    assert held["current_mA"] == 4.5, held
    assert held["in_force_mA"] == 4.8 and held["ceiling_mA"] == 4.5 and held["above_ceiling"] is True
    assert "4.8 mA" in held["note"] and "4.5 mA" in held["note"] and "above" in held["note"]
    # the conditions list a clinician reads says the same, not "held at its own current in force"
    cond = " ".join(out["sides"]["Left"]["conditions"])
    assert "not at its current in force" in cond and "4.8 mA" in cond
    # the side whose current in force is under its ceiling is held there, as before
    other = out["sides"]["Right"]["held_other_side"]
    assert other["current_mA"] == 3.0 and other["above_ceiling"] is False and other["note"] is None


def test_every_sheet_row_including_the_exploratory_ladder_asks_for_no_current_above_either_ceiling():
    margin = PR.margin_becomes_available(None)
    es = pd.DataFrame([dict(epoch=1.0, t0=pd.Timestamp("2025-08-01", tz="UTC"), dur_h=100.0,
                            freq_hz=55.0, amp_mA_Left=0.0, amp_mA_Right=2.5, pw_us_Left=100.0,
                            pw_us_Right=150.0, cathode_Left="1a-1b-1c-2a-2b-2c",
                            cathode_Right="1a-1b-1c-2a-2b-2c", n=10, left_leg_vas=50.0)])
    contact = {"channel": "ZERO_THREE_LEFT", "display_short": "L 0-3", "rate_hz": 125.0,
               "qualifying_centers_hz": [24.5], "n_qualifying": 1, "n_bands": 18,
               "n_responding": 0, "deployable": False}
    # the caller's own held value (5.0) must not bypass the check either
    proposed = {"Left": dict(rings={1, 2}, contact=contact, rate_source="cell", pulse_width_us=100.0,
                             pulse_width_source="in force", ceiling_mA=4.5, ceiling_source="the PI",
                             exposure=TP.configuration_exposure(es, "Left", {1, 2}),
                             held_other_side_mA=5.0, held_other_side_source="caller",
                             in_force_rings={2})}
    out = TP.plan_for_sides({"Left": _side(), "Right": _side()}, margin=margin,
                            in_force=_in_force(4.9, 4.8), proposed=proposed,
                            ceilings={"Left": (4.5, "t"), "Right": (4.5, "t")})
    rows = [r for r in out["sheet_rows"] if r.get("Amp (mA)") is not None]
    assert rows, "the sheet has rows that name currents"
    over = [(r["block"], r["Amp (mA)"]) for r in rows
            if max(_amps(r["Amp (mA)"])) > 4.5 + TOL]
    assert not over, over
    assert out["proposed"]["Left"]["held_other_side"]["current_mA"] == 4.5
    assert out["proposed"]["Left"]["held_other_side"]["above_ceiling"] is True


def test_a_one_side_plan_still_checks_the_held_side_against_its_own_ceiling():
    """A request for one side still holds the other; its ceiling comes from `ceilings`, not from
    the one side's inputs."""
    margin = PR.margin_becomes_available(None)
    out = TP.plan_for_sides({"Left": _side()}, margin=margin, in_force=_in_force(3.0, 4.8),
                            ceilings={"Right": (4.0, "t")})
    assert out["sides"]["Left"]["held_other_side"]["current_mA"] == 4.0


# ---------------------------------------------------------------------------------------------
# 2, 5. Stage 1: the queue, the batch, the optimum per rate, the best current in range
# ---------------------------------------------------------------------------------------------
def _design_above_ceiling(n=24, seed=0):
    """RCS08's situation: the left side delivered and tolerated currents up to 4.8 mA (before its
    ceiling was lowered), the right up to 3.5 mA; pain falls with the left current, so the fit's
    own optimum sits at the top of what was delivered."""
    rng = np.random.default_rng(seed)
    rows = []
    for ep in range(1, n + 1):
        al = float([1.6, 2.4, 3.2, 4.0, 4.8][ep % 5])
        ar = float([1.5, 2.5, 3.5][ep % 3])
        rows.append(dict(epoch=float(ep), freq_hz=55.0, pw_us_Left=60.0, pw_us_Right=160.0,
                         amp_mA_Left=al, amp_mA_Right=ar, n=8.0, dur_h=200.0,
                         left_leg_vas=float(70.0 - 8.0 * al + 2.0 * rng.standard_normal()),
                         left_leg_vas_sd=6.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-20", periods=len(d), freq="4D", tz="UTC")
    return d


CEIL = {"Left": (3.0, "test"), "Right": (3.0, "test")}


# Stage 1 runs here without its calibration check (`calibration_check=False`, 2026-10-02): a
# warning that changes no recommendation (decision 233, ruling 6), read by no test in this file,
# and held by `test_stratum_calibration.py`; its leave-one-out refits were most of each fit's time.
@pytest.fixture(scope="module")
def stage1_above_ceiling():
    """Fitted once for the three tests below, which only read it (each refitted it until
    2026-10-02)."""
    return S1.run_stage1(_design_above_ceiling(), data_horizon="t", washin_min=1.0,
                         safety_ceiling_by_hemisphere=CEIL, pool_pulse_widths=True,
                         calibration_check=False)


def test_stage1_proposes_and_recommends_nothing_above_either_sides_ceiling(stage1_above_ceiling):
    s1 = stage1_above_ceiling
    assert s1.slices, "the fixture fits a joint surface"
    for (pwl, pwr, _contact), sl in s1.slices.items():
        gx = sl.grid.grid_X()
        q = np.asarray(sl.queue, int)
        assert (gx[q, 1] <= 3.0 + TOL).all() and (gx[q, 2] <= 3.0 + TOL).all(), \
            ("queue", sorted(set(gx[q, 1])), sorted(set(gx[q, 2])))
        for b in sl.batch:
            assert b.amp_mA_left <= 3.0 + TOL and b.amp_mA_right <= 3.0 + TOL, ("batch", b)
        assert sl.x_star[1] <= 3.0 + TOL and sl.x_star[2] <= 3.0 + TOL, ("best in range", sl.x_star)
        assert sl.x_star_unconstrained[1] <= 3.0 + TOL and sl.x_star_unconstrained[2] <= 3.0 + TOL
        # the safe set itself holds nothing above either ceiling
        assert not (sl.safe & ((gx[:, 1] > 3.0 + TOL) | (gx[:, 2] > 3.0 + TOL))).any()
        for rate, rs in (sl.rate_strata or {}).items():
            if rs.fitted:
                assert rs.x_star[0] <= 3.0 + TOL and rs.x_star[1] <= 3.0 + TOL, ("per rate", rate, rs.x_star)
    for rate, rs in (s1.pooled_rate_strata or {}).items():
        if rs.fitted:
            assert rs.x_star[0] <= 3.0 + TOL and rs.x_star[1] <= 3.0 + TOL, ("pooled per rate", rate, rs.x_star)
    for st in s1.frozen.settings:
        if np.isfinite(st.amp_star_mA):
            assert st.amp_star_mA <= 3.0 + TOL, (st.hemisphere, st.amp_star_mA)


def test_the_control_this_fixture_reaches_above_the_ceiling_without_the_hard_bound(stage1_above_ceiling):
    """The control: on this fixture the safety models' own (soft) safe set, and the untouched
    queue, reach above 3.0 mA -- so the test above measures the bound, not a fixture that never
    went there. The two models are refitted exactly as `run_stage1` fits them."""
    from StimOptimizer.routines import plots as PLT
    from StimOptimizer.routines import surrogate as SUR
    s1 = stage1_above_ceiling
    sgp = {}
    for hemi in ("Left", "Right"):
        Xs, sev, sv, _m = SC.safety_seed(s1.D, f"amp_mA_{hemi}", freq_grid=PLT.FREQ_GRID,
                                         ceiling=CEIL[hemi], min_tolerated_h=S1.MIN_TOLERATED_H)
        sgp[hemi] = SUR.SafetyGP(SUR.ParameterGrid(PLT.FREQ_GRID, S1.JOINT_AMP_GRID),
                                 random_state=0).fit(Xs, sev, sv)
    sl = next(iter(s1.slices.values()))
    gx = sl.grid.grid_X()
    soft = (np.asarray(sgp["Left"].safe_mask(X=gx[:, [0, 1]], beta=PLT.BETA), bool)
            & np.asarray(sgp["Right"].safe_mask(X=gx[:, [0, 2]], beta=PLT.BETA), bool))
    assert (gx[soft, 1] > 3.0 + TOL).any(), "the soft safe set alone would allow a left current above 3.0 mA"


def test_the_what_to_test_next_queue_is_filtered_to_the_ceiling_even_where_nothing_else_filters_it(stage1_above_ceiling):
    """The queue was the one table filtered by nothing: not the safe set, not the ceiling."""
    s1 = stage1_above_ceiling
    sl = next(iter(s1.slices.values()))
    gx = sl.grid.grid_X()
    q = np.asarray(sl.queue, int)
    assert len(q), "the queue is not empty on this fixture"
    assert float(gx[q, 1].max()) <= 3.0 + TOL and float(gx[q, 2].max()) <= 3.0 + TOL


# ---------------------------------------------------------------------------------------------
# 3. the per-arm fit (`pipeline.run`, not on the page since 2026-09-14, still a documented entry)
# ---------------------------------------------------------------------------------------------
def test_the_per_arm_queue_batches_and_optimum_stay_under_the_arms_own_ceiling():
    rep = PL.run(_design_above_ceiling(), sites=("left_leg",), hemispheres=("Left",), outdir=None,
                 render_figures=False, data_horizon="t", washin_min=1.0,
                 safety_ceiling_by_hemisphere=CEIL)
    arm = rep.arms["left_leg__Left"]
    ctx = arm.ctx
    gx = ctx.grid.grid_X()
    q = np.asarray(ctx.queue, int)
    assert len(q) == 0 or float(gx[q, 1].max()) <= 3.0 + TOL, sorted(set(gx[q, 1]))
    for bm in ctx.batches:
        for m in bm:
            assert float(gx[m.index, 1]) <= 3.0 + TOL, ("batch", float(gx[m.index, 1]))
    assert float(gx[ctx.i_star, 1]) <= 3.0 + TOL
    if arm.queue is not None and len(arm.queue):
        assert float(pd.to_numeric(arm.queue["amp_mA"]).max()) <= 3.0 + TOL


# ---------------------------------------------------------------------------------------------
# 4. Stage 2's amplitude windows
# ---------------------------------------------------------------------------------------------
def test_stage2_windows_read_each_sides_own_ceiling_from_a_per_side_mapping():
    fr = _frozen(hi_left=4.8, hi_right=3.5, star_left=4.0, star_right=2.5)
    acc, rej = S2.enumerate_candidates(fr, lfp=None, ceiling_mA={"Left": (4.5, "PI"), "Right": (3.0, "PI")})
    pols = list(acc) + [p for p, _ in rej]
    assert pols, "the enumeration produced candidates to read"
    for p in pols:
        cap = 4.5 if p.hemisphere == "Left" else 3.0
        assert p.amp_max_mA <= cap + TOL, (p.hemisphere, p.amp_min_mA, p.amp_max_mA)
    # the left's window reaches its own ceiling, not the delivered 4.8 mA
    assert max(p.amp_max_mA for p in pols if p.hemisphere == "Left") == 4.5


def test_run_two_stage_hands_the_gates_ceiling_to_stage2(monkeypatch):
    seen = {}
    real = S2.run_stage2

    def spy(frozen, gate, **kw):
        seen.update(kw)
        return real(frozen, gate, **kw)

    monkeypatch.setattr(S2, "run_stage2", spy)
    ceil = {"Left": (4.5, "PI"), "Right": (4.5, "PI")}
    d = _design_above_ceiling()
    PL.run_two_stage(d, data_horizon="t", washin_min=1.0, primary_item="left_leg",
                     gate_kwargs={"ceiling_mA": ceil},
                     stage1_kwargs={"safety_ceiling_by_hemisphere": ceil,
                                    "calibration_check": False})
    assert seen.get("ceiling_mA") == ceil


# ---------------------------------------------------------------------------------------------
# 6. the next-visit list's fallback
# ---------------------------------------------------------------------------------------------
def test_the_next_visit_list_reads_a_missing_sides_ceiling_from_the_safety_module_not_a_typed_number():
    assert "4.5" not in inspect.getsource(S1.coverage_gap)
    cov = {"n_pairs": 0, "n_pairs_required": 6, "span_required_mA": 1.0, "span_left_mA": 0.0,
           "span_right_mA": 0.0, "reports_per_pair_required": 5, "days_per_pair_required": 2,
           "pairs": []}
    gap = S1.coverage_gap(cov, ceiling_mA={"Left": 3.0}, held_right_mA=2.0)
    assert gap["ceiling_mA"] == {"Left": 3.0, "Right": SC.ceiling_for(None, "Right")[0]}
    for p in gap["pairs_to_add"]:
        assert p["amp_mA_Left"] <= 3.0 + TOL


def test_the_next_visit_list_holds_a_side_above_its_ceiling_at_the_ceiling_and_says_so():
    cov = {"n_pairs": 0, "n_pairs_required": 6, "span_required_mA": 1.0, "span_left_mA": 0.0,
           "span_right_mA": 0.0, "reports_per_pair_required": 5, "days_per_pair_required": 2,
           "pairs": []}
    gap = S1.coverage_gap(cov, ceiling_mA={"Left": 4.5, "Right": 4.5}, held_right_mA=4.8)
    assert gap["held_side_mA"] == 4.5
    assert "4.8 mA" in gap["held_side_note"]
    assert gap["pairs_to_add"], "holding at the ceiling leaves pairs to propose"
    for p in gap["pairs_to_add"]:
        assert p["amp_mA_Left"] <= 4.5 + TOL and p["amp_mA_Right"] <= 4.5 + TOL


def test_the_service_builds_both_sides_ceilings_whatever_sides_were_requested():
    from StimOptimizer import bravo_service as SOS
    src = inspect.getsource(SOS._run_for_participant)
    assert "_ceilings = SC.ceilings_by_hemisphere(uid)" in src


# ---------------------------------------------------------------------------------------------
# the helpers
# ---------------------------------------------------------------------------------------------
def test_the_hard_mask_reads_both_forms_of_the_ceiling_mapping():
    amps = np.array([0.0, 2.0, 3.0, 3.01, 4.5, 5.0])
    np.testing.assert_array_equal(SC.within_ceiling_mask(amps, None, {"Left": (3.0, "p")}),
                                  [True, True, True, False, False, False])
    np.testing.assert_array_equal(SC.within_ceiling_mask(None, amps, {"Right": 4.5}),
                                  [True, True, True, True, True, False])
    # no ceiling at all is the module limit, the grid's own top: nothing removed
    assert SC.within_ceiling_mask(amps, amps, None).all()
    assert GATE.AMP_CEILING_MA == SC.ceiling_for(None, "Left")[0]


def test_a_held_current_at_or_below_the_ceiling_is_returned_untouched():
    d = SC.held_at_or_below_ceiling(2.5, 4.5, side="Right")
    assert d == {"current_mA": 2.5, "in_force_mA": 2.5, "ceiling_mA": 4.5, "above_ceiling": False,
                 "note": None, "source": None}
    assert SC.held_at_or_below_ceiling(None, 4.5, side="Right")["current_mA"] is None
