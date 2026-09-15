"""The safety model's severity-3 seed is a ceiling the PI states, per participant and per side
(`safety_ceiling.py`, 2026-09-12, item 3 of the "Make Closed-Loop Work" session).

Values: which number each side gets and what its provenance says; that the seed is one anchor per
grid rate at that current; that a lower ceiling shrinks the safe set and moves the reachable
ceiling; that the flat fit and Stage 1 seed from the ONE builder and agree; that the gate checks
each side's limits against its own ceiling; and that the fallback for an unknown participant is
the module hard limit and says so.
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
N_SAFE_LEFT_AT_5 = 612
N_SAFE_LEFT_AT_2 = 240
REACH_LEFT_AT_5 = 5.0
REACH_LEFT_AT_2 = 1.9
N_SAFE_LEFT_AT_1 = 57


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


def test_without_a_ceiling_argument_every_arm_reads_the_hard_limit_and_says_no_ceiling_was_stated():
    rep = _run(None)
    for arm in rep.arms.values():
        assert arm.meta["safety_ceiling_mA"] == OBJ.AMP_HARD_LIMIT_MA
        assert arm.meta["safety_ceiling_provenance"] == SC.FALLBACK_PROVENANCE


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
    s1 = S1.run_stage1(D, data_horizon="t", washin_min=1.0, safety_ceiling_by_hemisphere=by)
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
                        safety_ceiling_by_hemisphere=by_strict)
    a_l = res.frozen.audit["per_hemisphere"]["Left"]["safety_ceiling"]
    a_r = res.frozen.audit["per_hemisphere"]["Right"]["safety_ceiling"]
    assert (a_l["safety_ceiling_mA"], a_l["safety_ceiling_provenance"]) == (2.0, "left test")
    assert (a_r["safety_ceiling_mA"], a_r["safety_ceiling_provenance"]) == (4.5, "right test")
    n_strict = int(res.summary[res.summary["hemisphere"] == "Left"]["n_safe"].iloc[0])

    loose = S1.run_stage1(d, data_horizon="t", washin_min=1.0,
                          safety_ceiling_by_hemisphere=by_loose)
    n_loose = int(loose.summary[loose.summary["hemisphere"] == "Left"]["n_safe"].iloc[0])
    assert n_strict < n_loose, (n_strict, n_loose)


# ---------------------------------------------------------------------------------------------
# the gate checks each side against its own ceiling
# ---------------------------------------------------------------------------------------------
def _frozen(hi_left=4.0, hi_right=4.0):
    settings = tuple(
        S1.HemisphereSetting(hemisphere=h, rate_hz=55.0, pw_us=100.0, amp_star_mA=2.0,
                             amp_delivered_min_mA=1.0, amp_delivered_max_mA=hi, n_epochs_fitted=20,
                             rate_resolved=True, pw_resolved=True, reasons=("fixture",))
        for h, hi in (("Left", hi_left), ("Right", hi_right)))
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
