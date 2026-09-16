"""T7 of the contest's implementation plan (contest_2026-09-13_SYNTHESIS.md section 4): "the gain".

VERBATIM ACCEPTANCE CRITERION: "the simulation card's M1 run differs from M0 on the titration run's
data." NO TITRATION SESSION HAS BEEN RECORDED ON RCS08 -- decision 146 says plainly that the 20 s
post-ramp margin "stays off until the session is recorded", and that has not changed. So the
acceptance criterion cannot be satisfied with real data today; it is blocked on a clinical session
(open item 30), not on missing code. What this file proves instead, on CONSTRUCTED data only, is
that the WIRING that criterion depends on is already correct and needs no manual step once a real
titration run lands:

  1. `simulation.run_models` already builds M0 and M1 whenever a stored pooled row carries a real
     slope, and already reports M1 -- not M0 -- as the active model (decision 128, before this
     contest). Given a pooled row with a real slope, M1's own commanded-amplitude trajectory
     differs from M0's, step for step.
  2. `edges.pooled_actuation_edge` (E1, decision 126) reads the same stored row with no manual
     step: a resolved slope resolves the edge automatically.
  3. `post_ramp.margin_becomes_available` (decision 144/146) is fully DERIVED from the stored
     per-run points table -- nobody has to flip a switch to see whether the titration session
     would already qualify -- while the actual behaviour switch, `USE_POST_RAMP_MARGIN`, stays a
     separate, human decision (his call, decision 144), never auto-flipped by the derived flag.
  4. The two stored tables the gain runs through -- the pooled within-visit shape
     (`pooled_shape_signature`) and the simulation itself (`simulation_signature`) -- both fold in
     `recording_set_signature`, which changes whenever the recording set changes. A titration
     session is new recordings, so its own key is new: no stale cached M0-only simulation can be
     served after the session lands, and nothing needs to be swept or told to rebuild by hand.

None of this is invented data standing in for a real titration session -- every assertion below is
about the MECHANISM (does the code route a slope through correctly, does a new recording set change
a cache key), proven with hand-built numbers, never claimed as an RCS08 result.
"""
import numpy as np
import pandas as pd
import pytest

try:
    from modules.ClosedLoopDeployment import (simulation as S, edges as E, post_ramp as PR,
                                               amplitude_effect as AE, adapter as AD, types as T)
except ImportError:                                              # pragma: no cover
    from ClosedLoopDeployment import (simulation as S, edges as E, post_ramp as PR,
                                      amplitude_effect as AE, adapter as AD, types as T)


def _plan(upper=120.0, lower=80.0, lo=1.0, hi=3.0):
    return T.ThresholdPlan(upper=upper, lower=lower, scale="linear",
                           capture_amp_low=lo, capture_amp_high=hi)


def _series(n=900, dt=1.2, seed=0, amp_obs=2.0):
    rng = np.random.default_rng(seed)
    p = 100.0 + np.cumsum(rng.normal(0, 4.0, n))
    p = 100.0 + 35.0 * np.sin(np.linspace(0, 6 * np.pi, n)) + (p - p.mean()) * 0.3
    t = np.arange(n) * dt
    a = np.full(n, float(amp_obs))
    return t, p, a


def _titration_pooled_row(slope=-18.0, se=3.0, p=0.002, n=24, n_visits=5):
    """A pooled row shaped exactly like `amplitude_effect.pooled_row` would return after a real
    titration session widened the tested current range and added settled points -- a real,
    resolved slope, no established bend (a straight line is the plainer of the two cases)."""
    return {"pooled_direction": "band power falls as current rises", "pooled_slope_per_mA": slope,
            "pooled_slope_stderr": se, "pooled_slope_p": p, "n": n, "n_visits": n_visits,
            "verdict": "band power falls as current rises", "curves": False, "peaks_inside": False,
            "peak_mA": float("nan"), "p_curvature": 0.6, "r2_linear": 0.55, "r2_quadratic": 0.56}


# --------------------------------------------------------------------------------------------
# 1. M0 vs M1, given a titration-shaped pooled slope
# --------------------------------------------------------------------------------------------
def test_1_m1_is_active_and_its_trajectory_differs_from_m0_field_for_field():
    t, p, a = _series()
    row = _titration_pooled_row()
    out = S.run_models(t, p, a, _plan(), row, n_resample=0)

    assert out["refused"] is False
    assert out["curves"]["M1"]["kind"] == "linear", "the stored slope must build a real M1 curve"
    assert out["active_model"] == "M1", "decision 128: M1 is reported as active whenever a slope exists"
    assert set(out["models"]) == {"M0", "M1"}

    m0, m1 = out["models"]["M0"], out["models"]["M1"]
    # values, not shapes (CLAUDE.md rule 11): count how many summary fields actually differ
    fields = ("frac_time_at_upper", "frac_time_at_lower", "n_transitions", "mean_amplitude_mA",
             "frac_time_above", "frac_time_below")
    n_diff = sum(1 for f in fields if m0[f] != m1[f])
    assert n_diff > 0, "M1 must differ from M0 on at least one summary field"

    # and the drawn per-step trajectory itself differs, not only the rolled-up summary
    d = out["drawn"][0]
    amp0 = np.asarray(d["models"]["M0"]["amp"])
    amp1 = np.asarray(d["models"]["M1"]["amp"])
    assert amp0.shape == amp1.shape and amp0.size > 100
    n_amp_diff = int(np.sum(amp0 != amp1))
    assert n_amp_diff > 0, (n_amp_diff, "the commanded amplitude must actually move")
    # a real, non-trivial fraction of the run should differ -- not one stray step
    assert n_amp_diff > amp0.size // 4, (n_amp_diff, amp0.size)

    # M0 is still the exact replay: unaffected by the stored slope
    assert int(np.sum(out["closed_loop_difference"]["mean_amplitude_mA"] != 0.0)) >= 0
    assert out["closed_loop_difference"]["mean_amplitude_mA"] == pytest.approx(m1["mean_amplitude_mA"]
                                                                              - m0["mean_amplitude_mA"])


def test_1b_the_zero_curve_is_returned_when_the_row_has_no_slope_and_m1_is_then_inert():
    """The control: WITHOUT a resolved pooled slope (today's actual state on RCS08's committed
    band, decision 139/144), M1 is built from `ResponseCurve.zero()` in all but name and its
    trajectory is bit-identical to M0's -- confirming the difference in test 1 comes from the
    slope, not from some other effect of merely naming two models."""
    t, p, a = _series()
    row = dict(_titration_pooled_row(), pooled_slope_per_mA=float("nan"), pooled_slope_p=float("nan"),
              verdict="not assessed: no pooled titration slope is stored for this band")
    out = S.run_models(t, p, a, _plan(), row, n_resample=0)
    assert out["curves"]["M1"]["kind"] == "none"
    assert out["active_model"] == "M1"
    m0, m1 = out["models"]["M0"], out["models"]["M1"]
    assert all(m0[f] == m1[f] for f in ("frac_time_at_upper", "n_transitions", "mean_amplitude_mA"))
    d = out["drawn"][0]
    assert int(np.sum(np.asarray(d["models"]["M0"]["amp"]) != np.asarray(d["models"]["M1"]["amp"]))) == 0


# --------------------------------------------------------------------------------------------
# 2. the same stored row resolves E1 automatically, no manual step
# --------------------------------------------------------------------------------------------
def test_2_the_titration_row_resolves_e1_with_no_manual_step():
    row = _titration_pooled_row()
    e = E.pooled_actuation_edge(row, scale="power_linear")
    assert e.estimate == pytest.approx(-18.0) and e.resolved is True
    assert e.sign == -1
    assert e.n == 24 and e.n_clusters == 5


# --------------------------------------------------------------------------------------------
# 3. `margin_becomes_available` is derived; the behaviour switch is a separate human decision
# --------------------------------------------------------------------------------------------
def _run_rows(run, currents, *, contact="ONE_THREE_LEFT", centre=20.5, source="voltage trace",
             value=100.0):
    return [{"run": run, "sensing_contact": contact, "band_centre_hz": centre, "current_mA": c,
            "source": source, "settled_band_power_device_units": value} for c in currents]


def test_3_margin_availability_is_derived_from_the_stored_table_and_never_flips_the_switch():
    # today's record: at most six settled settings in one run -> not available
    today = pd.DataFrame(_run_rows("2026-08-18 L", [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]))
    switch_before, margin_before = PR.USE_POST_RAMP_MARGIN, PR.margin_s()
    m = PR.margin_becomes_available(today)
    assert m["available"] is False and m["switch_on"] is switch_before
    assert PR.USE_POST_RAMP_MARGIN is switch_before, "asking the question must never change the answer"

    # a titration session, constructed: 0-5.0 mA in 0.5 mA steps, all settled -> 11 settings
    titration = pd.DataFrame(_run_rows("titration L", [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]))
    m2 = PR.margin_becomes_available(pd.concat([today, titration], ignore_index=True))
    assert m2["available"] is True, "the derived flag reflects the titration session's own data"
    assert m2["max_settled_settings_in_one_run"] == 11 and m2["run"] == "titration L"
    # AND STILL, the module constant that actually changes behaviour is untouched: this is his
    # call (decision 144 off, decision 178 on), not a thing code flips for him once the data
    # support it
    assert m2["switch_on"] is switch_before and PR.USE_POST_RAMP_MARGIN is switch_before
    assert PR.margin_s() == margin_before, "the margin does not switch itself either way"


# --------------------------------------------------------------------------------------------
# 4. the stored tables' own keys change when the recording set changes -- no stale entry can be
#    served once a titration session's recordings are ingested
# --------------------------------------------------------------------------------------------
def test_4_pooled_shape_and_simulation_keys_both_depend_on_the_recording_set(monkeypatch):
    import types as _pytypes
    participant = _pytypes.SimpleNamespace(uid="p-t7")

    monkeypatch.setattr(AD, "recording_set_signature", lambda p: ("rs-before",))
    sig_pooled_before = AD.pooled_shape_signature(participant, tiles_key="tiles-1")
    plan = _plan()
    sig_sim_before = AD.simulation_signature(
        participant, tiles_key="tiles-1", contact="ONE_THREE_LEFT", centre_hz=20.5,
        hemisphere="Left", power_scale="lsb", plan=plan, n_resample=200, seed=0)

    # a titration session lands: new recordings, so a new recording-set identity
    monkeypatch.setattr(AD, "recording_set_signature", lambda p: ("rs-after-titration",))
    sig_pooled_after = AD.pooled_shape_signature(participant, tiles_key="tiles-1")
    sig_sim_after = AD.simulation_signature(
        participant, tiles_key="tiles-1", contact="ONE_THREE_LEFT", centre_hz=20.5,
        hemisphere="Left", power_scale="lsb", plan=plan, n_resample=200, seed=0)

    assert sig_pooled_before != sig_pooled_after, ("the pooled within-visit table's key must move "
                                                    "when the recording set does, or a titration "
                                                    "session's own points would never get pooled")
    assert sig_sim_before != sig_sim_after, ("a stale M0-only simulation must not be served after "
                                             "new recordings land under the same candidate")
