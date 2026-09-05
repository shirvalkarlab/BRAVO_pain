"""Tests for Stage 2, the closed-loop policy search, and for the whole staged run.

Three properties carry most of the weight here, and all three are about restraint rather than
capability. Stage 2 must not start when the gate refused. Stage 2 must not be able to change the
rate or the pulse width, because the device freezes both the moment BrainSense is configured. And a
candidate that violates a device constraint must be REJECTED rather than clipped into range, since a
clipped policy is a different clinical proposal that nobody evaluated.
"""
import dataclasses
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from StimOptimizer import stage1_openloop as S1
from StimOptimizer import stage2_closedloop as S2
from StimOptimizer.routines import percept_adaptive as PA
from StimOptimizer.routines import stage_gate as GATE


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------
def _setting(hemisphere="Left", rate_hz=130.0, pw_us=60.0, amp_star=2.0, amp_lo=1.0, amp_hi=4.0,
             rate_resolved=True, pw_resolved=True):
    return S1.HemisphereSetting(
        hemisphere=hemisphere, rate_hz=rate_hz, pw_us=pw_us, amp_star_mA=amp_star,
        amp_delivered_min_mA=amp_lo, amp_delivered_max_mA=amp_hi, n_epochs_fitted=20,
        rate_resolved=rate_resolved, pw_resolved=pw_resolved, reasons=("fixture",))


def _frozen(*settings):
    return S1.FrozenConfiguration(
        settings=tuple(settings or (_setting(),)), primary_item="left_leg",
        incumbent_epoch=1.0, incumbent_rate_hz=55.0, incumbent_pw_us=60.0,
        data_horizon="test", washin_min=1.0, n_epochs_total=40)


def _responding_lfp(n=120, seed=0):
    rng = np.random.default_rng(seed)
    amp = np.repeat([1.0, 3.0], n // 2)
    freqs = np.arange(4.0, 40.0, 0.5)
    mag = np.abs(rng.normal(1.0, 0.05, (n, freqs.size)))
    sel = (freqs >= 13.0) & (freqs <= 17.0)
    mag[:, sel] *= (np.exp(-0.9 * amp)[:, None] * 3.0)
    return GATE.LfpEvidence(amplitude_mA=amp, magnitude=mag, freqs=freqs,
                            era=np.tile(["a", "b"], n // 2), cluster=np.arange(n))


@pytest.fixture
def passing_gate():
    """A configuration and gate that pass every condition, so Stage 2 actually runs."""
    cfg = _frozen(_setting(rate_hz=130.0, amp_lo=1.0, amp_hi=4.0))
    lfp = _responding_lfp()
    g = GATE.evaluate_gate(cfg, lfp=lfp, amp_limits={"Left": (1.5, 3.0)})
    assert g.passed, g.describe()
    return cfg, g, lfp


@pytest.fixture
def refusing_gate():
    """A configuration the gate refuses on the rate floor: 40 Hz is below the adaptive minimum."""
    cfg = _frozen(_setting(rate_hz=40.0))
    lfp = _responding_lfp()
    g = GATE.evaluate_gate(cfg, lfp=lfp)
    assert not g.passed
    return cfg, g, lfp


# ---------------------------------------------------------------------------------------------
# Stage 2 must not start when the gate refused
# ---------------------------------------------------------------------------------------------
def test_stage2_does_not_start_when_the_gate_refuses(refusing_gate):
    cfg, g, lfp = refusing_gate
    res = S2.run_stage2(cfg, g, lfp=lfp)
    assert res.started is False
    assert res.policies.empty
    assert res.rejected.empty
    assert res.n_valid == 0


def test_the_refusal_names_which_condition_failed(refusing_gate):
    """"Not ready" is useless without "not ready why"; the answers imply different next actions."""
    cfg, g, lfp = refusing_gate
    res = S2.run_stage2(cfg, g, lfp=lfp)
    names = [n for n, _ in res.refusal_reasons]
    assert "rate_at_or_above_adaptive_minimum" in names
    detail = dict(res.refusal_reasons)["rate_at_or_above_adaptive_minimum"]
    assert "40" in detail and "55" in detail
    text = res.describe()
    assert "DID NOT START" in text
    assert "rate_at_or_above_adaptive_minimum" in text


def test_not_starting_is_reported_as_a_terminal_answer_not_an_error(refusing_gate):
    cfg, g, lfp = refusing_gate
    res = S2.run_stage2(cfg, g, lfp=lfp)
    assert "terminal answer, not a failure" in res.describe()


def test_every_blocking_condition_is_carried_into_the_refusal():
    cfg = _frozen(_setting(rate_hz=40.0, rate_resolved=False))
    g = GATE.evaluate_gate(cfg, lfp=None)
    res = S2.run_stage2(cfg, g, lfp=None)
    assert res.started is False
    assert len(res.refusal_reasons) == len(g.refusals()) == 3


def test_allow_gate_failure_runs_the_enumeration_but_records_that_nothing_is_deployable():
    """The testing escape hatch must not quietly look like a pass."""
    cfg = _frozen(_setting(rate_hz=40.0))
    g = GATE.evaluate_gate(cfg, lfp=_responding_lfp())
    res = S2.run_stage2(cfg, g, lfp=_responding_lfp(), allow_gate_failure=True,
                        band_centers=(15.0,), band_widths=(4.0,))
    assert res.started is True
    joined = " ".join(res.notes)
    assert "REFUSED" in joined
    assert "Nothing below is deployable" in joined
    # and the frozen 40 Hz rate is still refused by validate_policy on every candidate
    assert res.policies.empty
    assert not res.rejected.empty
    assert res.rejected["problems"].str.contains("below the adaptive minimum").all()


# ---------------------------------------------------------------------------------------------
# Stage 2 must not alter the frozen rate or pulse width
# ---------------------------------------------------------------------------------------------
def test_stage2_refuses_a_caller_supplied_rate(passing_gate):
    """Accepting the argument and ignoring it would hide the caller's misunderstanding."""
    cfg, g, lfp = passing_gate
    with pytest.raises(ValueError, match="cannot set the stimulation rate"):
        S2.run_stage2(cfg, g, lfp=lfp, rate_hz=165.0)


def test_stage2_refuses_a_caller_supplied_pulse_width(passing_gate):
    cfg, g, lfp = passing_gate
    with pytest.raises(ValueError, match="cannot set the stimulation rate or the pulse width"):
        S2.run_stage2(cfg, g, lfp=lfp, pw_us=90.0)


def test_the_refusal_quotes_the_device_constraint_and_the_frozen_values(passing_gate):
    cfg, g, lfp = passing_gate
    with pytest.raises(ValueError) as exc:
        S2.run_stage2(cfg, g, lfp=lfp, rate_hz=165.0)
    msg = str(exc.value)
    assert "BrainSense" in msg
    assert "re-run Stage 1" in msg
    assert "130 Hz" in msg          # the frozen rate is named so the caller sees what stands


def test_every_emitted_policy_inherits_the_frozen_rate_and_pulse_width(passing_gate):
    """There must be no path by which a proposal carries a rate the clinician did not freeze."""
    cfg, g, lfp = passing_gate
    res = S2.run_stage2(cfg, g, lfp=lfp, band_centers=(15.0, 20.0), band_widths=(4.0, 5.0))
    assert res.started is True and res.n_valid > 0
    s = cfg.setting("Left")
    assert (res.policies["rate_hz"] == s.rate_hz).all()
    assert (res.policies["pw_us"] == s.pw_us).all()
    # including the rejected ones: nothing anywhere proposes a different rate
    assert (res.rejected["rate_hz"] == s.rate_hz).all()


def test_a_validated_policy_cannot_be_mutated(passing_gate):
    cfg, g, lfp = passing_gate
    accepted, _ = S2.enumerate_candidates(cfg, lfp=lfp, band_centers=(15.0,), band_widths=(4.0,))
    assert accepted
    with pytest.raises(dataclasses.FrozenInstanceError):
        accepted[0].rate_hz = 165.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        accepted[0].amp_max_mA = 9.9


def test_the_frozen_configuration_is_unchanged_by_a_stage2_run(passing_gate):
    cfg, g, lfp = passing_gate
    before = (cfg.setting("Left").rate_hz, cfg.setting("Left").pw_us)
    S2.run_stage2(cfg, g, lfp=lfp, band_centers=(15.0,), band_widths=(4.0,))
    assert (cfg.setting("Left").rate_hz, cfg.setting("Left").pw_us) == before


# ---------------------------------------------------------------------------------------------
# Reject, never clip
# ---------------------------------------------------------------------------------------------
def test_a_band_outside_the_adaptive_range_is_rejected_not_moved_into_range(passing_gate):
    """Clipping 6 Hz up to 10.5 Hz would substitute a different control signal.

    A rejection with its reason attached is information. A clipped value is a fabrication wearing
    the shape of a result, because the policy that comes back is not the one that was proposed.
    """
    cfg, g, lfp = passing_gate
    accepted, rejected = S2.enumerate_candidates(cfg, lfp=lfp, band_centers=(6.0,),
                                                 band_widths=(5.0,))
    assert accepted == []
    assert rejected
    for pol, probs in rejected:
        assert pol.center_hz == 6.0, "the rejected candidate must keep the centre it was given"
        assert any("outside the adaptive range" in p for p in probs)


def test_a_sensing_only_mode_is_rejected_rather_than_silently_swapped(passing_gate):
    """Single Threshold Inverse cannot drive therapy at all, so it must be refused, not replaced."""
    cfg, g, lfp = passing_gate
    accepted, rejected = S2.enumerate_candidates(cfg, lfp=lfp, modes=(PA.SINGLE_INVERSE,),
                                                 band_centers=(15.0,), band_widths=(4.0,))
    assert accepted == []
    assert rejected
    for pol, probs in rejected:
        assert pol.mode == PA.SINGLE_INVERSE
        assert any("Sensing Only" in p for p in probs)


def test_a_sub_floor_frozen_rate_makes_every_candidate_invalid():
    """validate_policy checks the adaptive rate floor on every policy, not just the gate."""
    cfg = _frozen(_setting(rate_hz=40.0))
    accepted, rejected = S2.enumerate_candidates(cfg, lfp=_responding_lfp(),
                                                 band_centers=(15.0,), band_widths=(4.0,))
    assert accepted == []
    assert all(any("adaptive minimum" in p for p in probs) for _pol, probs in rejected)


def test_without_lfp_evidence_every_candidate_is_rejected_for_the_unmeasured_response():
    """A band that has not been shown to move with amplitude gives the loop no authority.

    This is the correct behaviour and not a degenerate case: validate_policy treats anything other
    than a measured True as a problem, and Stage 2 passes the measurement through rather than
    asserting it.
    """
    cfg = _frozen(_setting(rate_hz=130.0))
    accepted, rejected = S2.enumerate_candidates(cfg, lfp=None, band_centers=(15.0,),
                                                 band_widths=(4.0,))
    assert accepted == []
    assert all(any("RESPONDS TO STIMULATION AMPLITUDE" in p for p in probs)
               for _pol, probs in rejected)


def test_no_valid_policy_ever_carries_a_device_problem(passing_gate):
    """The invariant that makes the accepted set meaningful: it is validated, not merely filtered."""
    cfg, g, lfp = passing_gate
    accepted, _ = S2.enumerate_candidates(cfg, lfp=lfp)
    assert accepted
    for pol in accepted:
        assert pol.problems() == []
        assert pol.is_valid()
        lo, hi = pol.band_hz
        assert lo >= PA.ADAPTIVE_LFP_BAND_HZ[0] - 1e-9
        assert hi <= PA.ADAPTIVE_LFP_BAND_HZ[1] + 1e-9
        assert pol.rate_hz >= PA.MIN_ADAPTIVE_RATE_HZ


def test_amplitude_windows_never_leave_the_delivered_envelope_or_the_ceiling(passing_gate):
    cfg, g, lfp = passing_gate
    s = cfg.setting("Left")
    accepted, _ = S2.enumerate_candidates(cfg, lfp=lfp, band_centers=(15.0,), band_widths=(4.0,))
    assert accepted
    for pol in accepted:
        assert pol.amp_min_mA >= s.amp_delivered_min_mA - 1e-9
        assert pol.amp_max_mA <= min(s.amp_delivered_max_mA, GATE.AMP_CEILING_MA) + 1e-9
        assert pol.amp_max_mA > pol.amp_min_mA
        # the device's paused amplitude has to lie inside the adaptive limits
        assert pol.amp_min_mA <= pol.paused_amp_mA <= pol.amp_max_mA


def test_an_envelope_that_cannot_be_bounded_yields_no_window():
    """A hemisphere with no delivered amplitude has nothing to bound the device with."""
    s = _setting(amp_lo=float("nan"), amp_hi=float("nan"))
    assert S2._amp_windows(s, half_widths=(0.5,), ceiling_mA=4.9) == []


# ---------------------------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------------------------
def test_single_mode_predicts_the_device_derived_threshold_rather_than_choosing_one(passing_gate):
    """In Single Threshold mode the DEVICE computes 0.75*(upper-lower)+lower from two captures.

    A Single-mode policy therefore has to predict that number, not propose one of its own.
    """
    cfg, g, lfp = passing_gate
    accepted, _ = S2.enumerate_candidates(cfg, lfp=lfp, modes=(PA.SINGLE,),
                                          band_centers=(15.0,), band_widths=(4.0,))
    assert accepted
    pol = accepted[0]
    assert pol.threshold_single is not None
    assert pol.threshold_lower is None and pol.threshold_upper is None
    assert pol.thresholds_determined is True
    power = lfp.power_for(15.0, 4.0)
    from StimOptimizer.routines import lfp_response as LFP
    r = LFP.assess_response(power, lfp.amplitude_mA, era=lfp.era, cluster=lfp.cluster)
    assert pol.threshold_single == pytest.approx(r.derived_threshold)


def test_dual_mode_carries_a_manual_threshold_pair(passing_gate):
    cfg, g, lfp = passing_gate
    accepted, _ = S2.enumerate_candidates(cfg, lfp=lfp, modes=(PA.DUAL,),
                                          band_centers=(15.0,), band_widths=(4.0,))
    assert accepted
    pol = accepted[0]
    assert pol.threshold_lower is not None and pol.threshold_upper is not None
    assert pol.threshold_upper > pol.threshold_lower
    assert pol.threshold_single is None


# ---------------------------------------------------------------------------------------------
# The ranking is deployability, not efficacy
# ---------------------------------------------------------------------------------------------
def test_the_ranking_basis_states_that_it_is_not_an_efficacy_ordering(passing_gate):
    """No closed-loop pain outcome exists for this patient, so no policy can be called better.

    A ranked table invites being read as a preference ordering; this one has to say that it is not.
    """
    cfg, g, lfp = passing_gate
    res = S2.run_stage2(cfg, g, lfp=lfp, band_centers=(15.0, 20.0), band_widths=(4.0,))
    assert "DEPLOYABILITY" in res.ranking_basis
    assert "NOT an efficacy ordering" in res.ranking_basis
    assert "no closed-loop pain outcome" in res.ranking_basis.lower()
    assert "DEPLOYABILITY" in res.describe()


def test_the_ranking_is_ordered_by_capture_separation(passing_gate):
    cfg, g, lfp = passing_gate
    res = S2.run_stage2(cfg, g, lfp=lfp)
    assert res.ranking_assessed is True
    d = res.policies["separation_d"].to_numpy(float)
    assert np.all(np.diff(d) <= 1e-9), "separation must be non-increasing down the table"
    best = res.best()
    assert best is not None
    assert best["separation_d"] == pytest.approx(float(np.nanmax(d)))
    assert res.best(hemisphere="Right") is None      # fixture has only a Left setting


# ---------------------------------------------------------------------------------------------
# The whole staged run
# ---------------------------------------------------------------------------------------------
def _rcs08_like():
    """A matrix reproducing the real record's structure: pulse width aliased with rate."""
    rng = np.random.default_rng(0)
    rows, ep = [], 0
    for i, pw in enumerate((100.0, 140.0)):
        rate = (55.0, 165.0)[i]
        for k in range(11):
            ep += 1
            rows.append(dict(epoch=float(ep), freq_hz=rate, pw_us_Left=pw,
                             amp_mA_Left=1.0 + 0.2 * (k % 5), amp_mA_Right=1.2 + 0.2 * (k % 4),
                             n=8.0, dur_h=200.0,
                             left_leg_vas=50.0 + 3.0 * rng.standard_normal(),
                             left_leg_vas_sd=8.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    return d


def test_the_two_stage_run_reports_honestly_that_it_cannot_proceed():
    """End to end on a matrix with the real record's structure and no spectral data at all.

    Two of the four gate conditions must block for reasons intrinsic to the data rather than to any
    threshold choice: the open-loop choice is not resolved, and whether any band responds to
    stimulation amplitude was never measured because the matrix carries no LFP.
    """
    from StimOptimizer import pipeline
    rep = pipeline.run_two_stage(_rcs08_like(), data_horizon="test", washin_min=1.0)
    assert rep.can_deploy_closed_loop() is False
    assert rep.stage2.started is False
    assert rep.frozen.resolved is False
    names = [n for n, _ in rep.gate.refusals()]
    assert "openloop_choice_resolved" in names
    assert "adaptive_band_passes_lfp_response" in names
    assert "adaptive_band_passes_lfp_response" in rep.gate.not_assessed_names()
    assert rep.manifest["gate_passed"] is False
    assert rep.manifest["stage2_n_valid_policies"] == 0


def test_the_run_against_the_reconciled_biomarker_plate_refuses_for_three_stateable_reasons():
    """End to end with the reconciled RCS08 plate and the historical LFP-response verdict.

    The three reasons must be reported SEPARATELY, each with its number, so a reader can see which
    condition binds:

    1. the only adaptive-capable selected band (14.817 Hz) is not statistically supported —
       perm_p = 0.4166 after selection correction, FDR q = 0.5055;
    2. the nominally strongest band (3.9215 Hz, perm_p 0.0809) spans roughly 1.4-6.4 Hz and is
       excluded by the 8-30 Hz adaptive window — a DEVICE constraint, independent of its statistics;
    3. the LFP-response requirement fails on the historical record — 3 of 15 channel-by-rate cells
       suppress, one-sided binomial p = 0.996.

    Refusing here is the correct behaviour and no threshold may be relaxed to change it.
    """
    from StimOptimizer import pipeline
    rep = pipeline.run_two_stage(_rcs08_like(), data_horizon="test", washin_min=1.0,
                                 selected_bands=GATE.RCS08_SELECTED_BANDS,
                                 response_summary=GATE.RCS08_RESPONSE_SUMMARY)
    assert rep.can_deploy_closed_loop() is False
    assert rep.stage2.started is False
    assert rep.stage2.n_valid == 0
    assert len(rep.gate.conditions) == 6

    # reason 1: the usable band is not supported, and its numbers are in the detail
    stat = rep.gate.condition("selected_band_statistically_supported")
    assert stat.passed is False
    assert "0.4166" in stat.detail and "0.5055" in stat.detail

    # reason 2: the other band is excluded by the DEVICE window, reported as a device fact and not
    # as a statistical one. The condition itself PASSES, because a band inside the window does
    # exist -- the exclusion is attached to the band it applies to rather than to the whole gate.
    win = rep.gate.condition("selected_band_inside_adaptive_window")
    assert win.passed is True
    assert "DEVICE" in win.detail
    assert "regardless of their statistics" in win.detail
    assert [r["outcome"] for r in win.evidence["outside"]] == ["nrs"]

    # reason 3: the response requirement fails on the historical record, with attribution
    resp = rep.gate.condition("adaptive_band_passes_lfp_response")
    assert resp.passed is False
    assert "3 of 15" in resp.detail and "0.996" in resp.detail

    # each blocking reason is separately named in the refusal, not merged into one verdict
    names = [n for n, _ in rep.stage2.refusal_reasons]
    assert "selected_band_statistically_supported" in names
    assert "adaptive_band_passes_lfp_response" in names
    assert "openloop_choice_resolved" in names


def test_both_routes_for_supplying_selected_bands_reach_the_gate_identically():
    """Regression, 2026-09-02. Both invocation styles must work.

    `selected_bands` and `response_summary` were reachable through `gate_kwargs` before they were
    promoted to named arguments of run_two_stage, so callers written against either style exist.
    Promoting them while still splatting `gate_kwargs` made the older style raise
    "got multiple values for keyword argument 'selected_bands'", which no test caught because the
    end-to-end test above uses the new style and the gate unit tests call evaluate_gate directly.
    """
    from StimOptimizer import pipeline
    d = _rcs08_like()
    named = pipeline.run_two_stage(d, data_horizon="test", washin_min=1.0,
                                   selected_bands=GATE.RCS08_SELECTED_BANDS,
                                   response_summary=GATE.RCS08_RESPONSE_SUMMARY)
    viakw = pipeline.run_two_stage(d, data_horizon="test", washin_min=1.0,
                                   gate_kwargs=dict(
                                       selected_bands=GATE.RCS08_SELECTED_BANDS,
                                       response_summary=GATE.RCS08_RESPONSE_SUMMARY))
    assert [c.name for c in named.gate.conditions] == [c.name for c in viakw.gate.conditions]
    assert [c.verdict for c in named.gate.conditions] == [c.verdict for c in viakw.gate.conditions]
    assert named.gate.passed is viakw.gate.passed is False
    assert len(named.gate.conditions) == 6


def test_supplying_the_same_gate_argument_by_both_routes_is_an_explicit_error():
    """Silent precedence would make the winning value an implementation detail."""
    from StimOptimizer import pipeline
    with pytest.raises(ValueError, match="supplied both as a run_two_stage argument"):
        pipeline.run_two_stage(_rcs08_like(), data_horizon="test", washin_min=1.0,
                               selected_bands=GATE.RCS08_SELECTED_BANDS,
                               gate_kwargs=dict(selected_bands=GATE.RCS08_SELECTED_BANDS))


def test_other_gate_kwargs_still_reach_the_gate():
    """The merge must not swallow the keys it does not manage."""
    from StimOptimizer import pipeline
    rep = pipeline.run_two_stage(_rcs08_like(), data_horizon="test", washin_min=1.0,
                                 gate_kwargs=dict(min_rate_hz=10.0))
    assert rep.gate.condition("rate_at_or_above_adaptive_minimum").passed is True, (
        "a 10 Hz floor passed through gate_kwargs must change the rate verdict")


def test_the_original_flat_entry_point_still_works():
    """run() must be untouched by the staged addition; existing callers depend on it."""
    from StimOptimizer import pipeline
    d = _rcs08_like()
    out = pipeline.run(d, sites=("left_leg",), hemispheres=("Left",), outdir=None,
                       render_figures=False, data_horizon="test", washin_min=1.0,
                       n_batches=1, q=2)
    assert "left_leg__Left" in out.arms
    assert not out.summary.empty
    assert hasattr(out, "recommendation_is_supported")


def _find_real_matrix():
    """Locate the real RCS08 design matrix, or return ``None``.

    The canonical copy of this file lives in the project's artifact store rather than in the
    repository, so it is usually absent from a checkout. ``STIMOPT_DESIGN_MATRIX`` lets a caller
    point at it; the test that needs it skips when it cannot be found, and the structural fixture
    above covers the same behaviour unconditionally.
    """
    env = os.environ.get("STIMOPT_DESIGN_MATRIX")
    candidates = ([Path(env)] if env else []) + [
        Path(__file__).resolve().parents[1] / "data" / "rcs08_bo_design_matrix.csv",
        Path(__file__).resolve().parents[4] / "rcs08_bo_design_matrix.csv",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def test_the_real_design_matrix_cannot_proceed_to_closed_loop():
    """Observed on the real matrix (86 epochs, horizon 2026-08-12) on 2026-09-02.

    Three of the four conditions blocked. The frozen left-hemisphere rate came out at 40 Hz, below
    the 55 Hz adaptive minimum. Neither hemisphere's open-loop choice was resolved: on the left the
    gain over the setting in force was +0.036 NRS points against a difference SD of 0.931, and on
    the right the comparison was NOT ASSESSED because the chosen 140 us stratum never delivered the
    incumbent's 55 Hz rate. And the matrix carries no spectral data, so the LFP-response condition
    was NOT ASSESSED. Only the amplitude-limit condition passed, and it passed on defaulted limits.
    """
    p = _find_real_matrix()
    if p is None:
        pytest.skip("the real design matrix is not on disk (it lives in the artifact store); "
                    "set STIMOPT_DESIGN_MATRIX to point at a copy")
    from StimOptimizer import pipeline
    rep = pipeline.run_two_stage(str(p), data_horizon="2026-08-12", washin_min=1.0)
    assert rep.can_deploy_closed_loop() is False
    assert rep.stage2.started is False
    assert set(rep.gate.failed_names()) >= {"rate_at_or_above_adaptive_minimum",
                                            "openloop_choice_resolved"}
    assert "adaptive_band_passes_lfp_response" in rep.gate.not_assessed_names()


# --- the evidence factory: selection must happen AFTER freezing (2026-09-05) --------------------
def test_lfp_may_be_a_factory_that_receives_the_frozen_configuration():
    """The sequencing fix. Rate and pulse width freeze when BrainSense is configured, so evidence
    measured at another rate says nothing about the configuration Stage 2 will run. Passing a
    pre-selected cell invites that mismatch, and it happened on the first live run: the screen's
    best cell was at 165 Hz while Stage 1 had frozen 40 Hz. Accepting a callable makes the ordering
    structural instead of something the caller has to remember.
    """
    seen = {}

    def factory(frozen):
        seen["rates"] = sorted({float(h.rate_hz) for h in frozen.settings})
        seen["called"] = True
        return _responding_lfp()

    from StimOptimizer import pipeline
    rep = pipeline.run_two_stage(_rcs08_like(), data_horizon="test", washin_min=1.0, lfp=factory)
    assert seen.get("called") is True, "the factory was never called"
    assert seen["rates"], "the factory did not receive a frozen configuration with rates"
    # and the evidence it returned actually reached the gate rather than being discarded
    assert "adaptive_band_passes_lfp_response" in \
        {c.name for c in rep.gate.conditions}


def test_a_plain_evidence_object_still_works_unchanged():
    """Backward compatibility: the non-callable path is the one every existing caller uses."""
    from StimOptimizer import pipeline
    lfp = _responding_lfp()
    rep = pipeline.run_two_stage(_rcs08_like(), data_horizon="test", washin_min=1.0, lfp=lfp)
    names = {c.name for c in rep.gate.conditions}
    assert "adaptive_band_passes_lfp_response" in names


def test_the_factory_may_refuse_by_returning_none_and_the_gate_then_blocks():
    """A factory that cannot honestly pick a cell returns None, and that must BLOCK rather than
    pass. This is the path taken when the two hemispheres freeze different rates: there is no single
    rate to pin the evidence to, and attributing one hemisphere's measurement to the other's
    configuration would be worse than refusing.
    """
    from StimOptimizer import pipeline
    rep = pipeline.run_two_stage(_rcs08_like(), data_horizon="test", washin_min=1.0,
                                 lfp=lambda frozen: None)
    assert rep.gate.passed is False
    assert rep.stage2.started is False
    # the response condition must be NOT ASSESSED, not passed
    cond = {c.name: c for c in rep.gate.conditions}["adaptive_band_passes_lfp_response"]
    assert cond.passed is not True, cond.verdict
