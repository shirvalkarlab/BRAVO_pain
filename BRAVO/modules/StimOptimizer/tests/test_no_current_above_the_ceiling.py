"""No current above a side's safe ceiling is proposed, recommended, scheduled or exported (decision 308).

Decision 306 capped every current the Closed-Loop page recommends at the PI-stated ceiling (4.5 mA
per side on RCS08, `safety_ceiling.PI_STATED_CEILING_MA`). Its agent found, read-only, the places in
the Stim Optimizer that could still name a higher one:

1. the titration ladders held the side not being stepped at its current in force, never checked
   against that side's ceiling, and copied it into every ladder row and the Google-sheet export;
2. the "what to test next" queue was built from the whole 0-5.0 mA grid with no ceiling filter;
3. the per-arm fit's queue and batches were bounded only by the 5.0 mA module limit;
4. Stage 2's amplitude windows used the 5.0 mA module limit while the gate checked 4.5 mA;
5. the optimum per rate, the best current inside the allowed range and the batches were bounded
   only by the safety model's SOFT safe set, which on RCS08 carries a tolerated 4.8 mA;
6. the next-visit list fell back to a typed 4.5 mA.

Each test below builds the situation that let the value through -- a current in force, or a
tolerated current, ABOVE the stated ceiling, as on RCS08 -- and reads every value the module offers
as one to deliver. History (currents delivered in the past) is not tested here: it may be shown,
labelled as history.
"""
import inspect

import numpy as np
import pandas as pd

from ClosedLoopDeployment import post_ramp as PR
from StimOptimizer import pipeline as PL
from StimOptimizer import safety_ceiling as SC
from StimOptimizer import stage1_openloop as S1
from StimOptimizer import stage2_closedloop as S2
from StimOptimizer import titration_plan as TP
from StimOptimizer.routines import stage_gate as GATE

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


def _stage1():
    return S1.run_stage1(_design_above_ceiling(), data_horizon="t", washin_min=1.0,
                         safety_ceiling_by_hemisphere=CEIL, pool_pulse_widths=True)


def test_stage1_proposes_and_recommends_nothing_above_either_sides_ceiling():
    s1 = _stage1()
    assert s1.slices, "the fixture fits a joint surface"
    for (pwl, pwr), sl in s1.slices.items():
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


def test_the_control_this_fixture_reaches_above_the_ceiling_without_the_hard_bound():
    """The control: on this fixture the safety models' own (soft) safe set, and the untouched
    queue, reach above 3.0 mA -- so the test above measures the bound, not a fixture that never
    went there. The two models are refitted exactly as `run_stage1` fits them."""
    from StimOptimizer.routines import plots as PLT
    from StimOptimizer.routines import surrogate as SUR
    s1 = _stage1()
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


def test_the_what_to_test_next_queue_is_filtered_to_the_ceiling_even_where_nothing_else_filters_it():
    """The queue was the one table filtered by nothing: not the safe set, not the ceiling."""
    s1 = _stage1()
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
def _frozen(hi_left=4.8, hi_right=3.5, star_left=4.0, star_right=2.5):
    settings = tuple(
        S1.HemisphereSetting(hemisphere=h, rate_hz=55.0, pw_us=100.0, amp_star_mA=star,
                             amp_delivered_min_mA=1.0, amp_delivered_max_mA=hi, n_epochs_fitted=20,
                             rate_resolved=True, pw_resolved=True, reasons=("fixture",))
        for h, hi, star in (("Left", hi_left, star_left), ("Right", hi_right, star_right)))
    return S1.FrozenConfiguration(
        settings=settings, primary_item="left_leg", incumbent_epoch=1.0, incumbent_rate_hz=55.0,
        incumbent_pw_us=100.0, data_horizon="test", washin_min=1.0, n_epochs_total=40)


def test_stage2_windows_read_each_sides_own_ceiling_from_a_per_side_mapping():
    fr = _frozen()
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
                     stage1_kwargs={"safety_ceiling_by_hemisphere": ceil})
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
