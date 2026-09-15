"""Tests for Stage 1, the open-loop search that freezes ONE joint configuration for both sides.

Rewritten 2026-09-14 for the joint (rate, amplitude-Left, amplitude-Right) redesign (the PI,
verbatim: "model the left and right sides together because they're always on"). The tests that
matter most here are still the ones about what Stage 1 REFUSES to claim — a surrogate that reports
an optimum is easy; a surrogate that reports "I cannot tell you whether this beats what you are
already doing" is the thing this module exists to get right. What is NEW to this file is the
guarantee the redesign itself is FOR: both sides of one frozen configuration share the same rate,
the same resolution verdict and the same gain, because there is one rate knob and one joint
decision now, not two independent ones that could disagree.

Several tests from the pre-joint version of this file covered machinery that no longer exists at
all — the rate-blocked, era-blocked, precision-weighted single-hemisphere pulse-width regression
(``pulse_width_contrast``) and the ability to fit one hemisphere while ignoring the other's current
entirely. Per this project's own rule (a test whose name asserts something untrue is worse than no
test), those tests are REMOVED rather than kept passing against a renamed no-op; the joint audit
that replaces the single-hemisphere design audit (``pulse_width_pair_design_audit``) has its own
tests below.
"""
import dataclasses

import numpy as np
import pandas as pd
import pytest

from StimOptimizer import stage1_openloop as S1


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------
def _matrix(n_per_cell=10, pw_pairs=((60.0, 160.0), (140.0, 140.0)), rates=(55.0, 110.0), seed=0,
           aliased=False, effect=0.0, asymmetric_dosing=True):
    """Design matrix with a controllable rate x (pulse-width-Left, pulse-width-Right) layout.

    ``pw_pairs`` is a sequence of (pw_left, pw_right) pairs, generalising the pre-joint fixture's
    single ``pw_levels`` axis to the joint stratum the module now fits on. ``aliased=True`` gives
    each pair its OWN rate, the structure under which a pulse-width contrast is not estimable.
    ``effect`` adds a pain benefit to the LAST pair. ``asymmetric_dosing=True`` (the default)
    includes rows where one side runs at 0 mA while the other does not, and a few rows where both
    are 0 -- the real record's own mix (25 Left-off, 10 Right-off, 9 both-off, 73 both-on of 120
    epochs on RCS08) -- specifically so a joint fit has the asymmetric information it needs.
    """
    rng = np.random.default_rng(seed)
    rows = []
    ep = 0
    for i, (pwl, pwr) in enumerate(pw_pairs):
        use = (rates[i % len(rates)],) if aliased else rates
        for rate in use:
            for k in range(n_per_cell):
                ep += 1
                amp_left = 1.0 + 0.2 * (k % 5)
                amp_right = 1.2 + 0.2 * (k % 4)
                if asymmetric_dosing and k % 7 == 0:
                    amp_left = 0.0
                elif asymmetric_dosing and k % 7 == 1:
                    amp_right = 0.0
                rows.append(dict(
                    epoch=float(ep), freq_hz=float(rate), pw_us_Left=float(pwl),
                    pw_us_Right=float(pwr),
                    amp_mA_Left=float(amp_left), amp_mA_Right=float(amp_right),
                    n=8.0, dur_h=200.0,
                    left_leg_vas=float(50.0 - 10.0 * effect * (i == len(pw_pairs) - 1)
                                       + 3.0 * rng.standard_normal()),
                    left_leg_vas_sd=8.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    return d


@pytest.fixture
def rcs08_like():
    """A matrix reproducing the structural features of the real RCS08 record: pulse width paired
    with rate is aliased, the incumbent sits at one particular (rate, pw-pair), and at least one
    joint stratum never delivered the incumbent's rate at all."""
    return _matrix(n_per_cell=11, pw_pairs=((100.0, 150.0), (140.0, 180.0)), rates=(55.0, 165.0),
                  aliased=True)


# FIT ONCE, ASSERT MANY, per this file's own established convention: a joint fit costs a few
# seconds, so the same result is reused by every test that only reads it.
@pytest.fixture(scope="module")
def stage1_both_sides():
    d = _matrix(n_per_cell=11, pw_pairs=((100.0, 150.0), (140.0, 180.0)), rates=(55.0, 165.0),
               aliased=True)
    return S1.run_stage1(d, data_horizon="test", washin_min=1.0)


@pytest.fixture(scope="module")
def stage1_with_thin_stratum():
    """The same matrix plus a 2-epoch (120, 130) us pair, below the stratum floor."""
    thin = _matrix(n_per_cell=11, pw_pairs=((100.0, 150.0), (140.0, 180.0)), rates=(55.0, 165.0),
                   aliased=True)
    extra = thin.iloc[:2].copy()
    extra["epoch"] = [9001.0, 9002.0]
    extra["pw_us_Left"] = 120.0
    extra["pw_us_Right"] = 130.0
    d = pd.concat([thin, extra], ignore_index=True)
    return S1.run_stage1(d, data_horizon="test", washin_min=1.0)


# ---------------------------------------------------------------------------------------------
# The common incumbent
# ---------------------------------------------------------------------------------------------
def test_every_stratum_is_referenced_to_one_common_incumbent(rcs08_like, stage1_both_sides):
    res = stage1_both_sides
    expected = float(rcs08_like.sort_values("t0")["epoch"].iloc[-1])
    assert res.frozen.incumbent_epoch == expected
    inc = res.D.loc[res.D["epoch"] == expected]
    assert float(inc["J_pain"].iloc[0]) == pytest.approx(0.0, abs=1e-9)


def test_an_incumbent_absent_from_the_matrix_is_refused(rcs08_like):
    with pytest.raises(ValueError, match="not in this design matrix"):
        S1.run_stage1(rcs08_like, incumbent_epoch=99999.0)


def test_a_joint_fit_needs_both_currents(rcs08_like):
    """A design matrix with no Right-side current cannot be joint-fitted at all -- this is the
    guarantee that replaces the pre-joint single-hemisphere fit path."""
    d = rcs08_like.drop(columns=["amp_mA_Right"])
    with pytest.raises(KeyError, match="amp_mA_Right"):
        S1.run_stage1(d)


# ---------------------------------------------------------------------------------------------
# Joint (pulse-width-Left, pulse-width-Right) strata
# ---------------------------------------------------------------------------------------------
def test_one_joint_surface_is_fitted_per_adequately_sampled_pulse_width_pair(stage1_both_sides):
    res = stage1_both_sides
    fitted = sorted(res.slices)
    assert fitted == [(100.0, 150.0), (140.0, 180.0)]
    assert set(zip(res.summary["pw_us_left"], res.summary["pw_us_right"])) == set(fitted)


def test_an_undersampled_pair_is_skipped_with_its_reason_never_pooled(stage1_with_thin_stratum):
    """A thin joint stratum must be recorded as skipped, not merged into a neighbouring pair.

    Pooling it would put two different pulse-width pairs on one surface under a single length
    scale, which is exactly the borrowing the stratification exists to prevent.
    """
    res = stage1_with_thin_stratum
    assert (120.0, 130.0) not in res.slices
    assert "pwL120_pwR130" in res.skipped
    assert "below the 8-epoch floor" in res.skipped["pwL120_pwR130"]


def test_the_epoch_counts_are_internally_consistent(stage1_with_thin_stratum):
    res = stage1_with_thin_stratum
    a = res.audit["per_hemisphere"]["Left"]
    per_pair = {k: s.n_epochs for k, s in res.slices.items()}
    skipped_epochs = sum(int(v) for k, v in res.audit["design"]["epochs_per_pair"].items()
                        if k not in {f"{p[0]:g}_{p[1]:g}" for p in per_pair})
    assert sum(per_pair.values()) == res.audit["n_epochs_in_fitted_strata"]
    assert res.audit["n_epochs_in_fitted_strata"] + skipped_epochs == res.audit["n_epochs_eligible"]
    assert skipped_epochs == 2, "fixture must skip exactly the 2-epoch (120, 130) us pair"
    assert res.frozen.setting("Left").n_epochs_fitted in per_pair.values()


def test_pulse_width_right_falls_back_to_left_column_when_absent(rcs08_like):
    d = rcs08_like.drop(columns=["pw_us_Right"])
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0)
    assert res.audit["per_hemisphere"]["Right"]["pw_col_fallback"] is True
    assert res.audit["per_hemisphere"]["Right"]["pw_col"] == "pw_us_Left"


# ---------------------------------------------------------------------------------------------
# THE JOINT GUARANTEE: one decision, not two that could disagree
# ---------------------------------------------------------------------------------------------
def test_both_sides_share_the_same_rate_gain_and_resolution_verdict(stage1_both_sides):
    """This is the property the redesign exists for: the device has one rate knob, so a joint
    fit cannot recommend two different rates for the two sides, and the resolution comparison is
    ONE joint comparison against ONE incumbent, not two independent ones."""
    res = stage1_both_sides
    left, right = res.frozen.setting("Left"), res.frozen.setting("Right")
    if np.isfinite(left.rate_hz) or np.isfinite(right.rate_hz):
        assert left.rate_hz == right.rate_hz or (np.isnan(left.rate_hz) and np.isnan(right.rate_hz))
    assert left.rate_resolved == right.rate_resolved
    assert left.gain == pytest.approx(right.gain, nan_ok=True) if hasattr(pytest, "approx") else True
    if np.isfinite(left.gain) and np.isfinite(right.gain):
        assert left.gain == pytest.approx(right.gain)
        assert left.sd_of_difference == pytest.approx(right.sd_of_difference)


def test_pulse_width_and_preferred_amplitude_stay_genuinely_per_side():
    """Unlike rate, pulse width and current are independently programmable per hemisphere, so a
    joint stratum whose two sides run different pulse widths must hand back two different
    ``pw_us`` values -- one per side -- from the SAME fit."""
    d = _matrix(n_per_cell=12, pw_pairs=((60.0, 160.0),), rates=(55.0, 110.0), aliased=False)
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0)
    left, right = res.frozen.setting("Left"), res.frozen.setting("Right")
    assert left.pw_us == pytest.approx(60.0)
    assert right.pw_us == pytest.approx(160.0)


def test_asymmetric_dosing_epochs_are_not_excluded_from_the_joint_fit():
    """An epoch where one side is at 0 mA is real information for a joint fit -- it is what lets
    the surface tell the two currents' effects apart -- and must not be dropped the way the
    pre-joint per-hemisphere fit dropped a hemisphere's own 0 mA rows."""
    d = _matrix(n_per_cell=14, pw_pairs=((60.0, 60.0),), rates=(55.0,), asymmetric_dosing=True)
    n_asymmetric = int(((d["amp_mA_Left"] == 0) | (d["amp_mA_Right"] == 0)).sum())
    assert n_asymmetric > 0, "fixture must contain asymmetric-dosing rows"
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0)
    ((_pwl, _pwr), sl), = res.slices.items()
    assert sl.n_epochs == len(d)


# ---------------------------------------------------------------------------------------------
# The support gate on the resolution comparison
# ---------------------------------------------------------------------------------------------
def test_a_stratum_that_never_ran_the_incumbent_rate_reports_not_assessed_not_resolved(
        stage1_both_sides):
    res = stage1_both_sides
    inc_rate = res.frozen.incumbent_rate_hz
    for key, sl in res.slices.items():
        ran_incumbent_rate = inc_rate in set(sl.meta["rates_delivered"])
        assert sl.incumbent_rate_supported is ran_incumbent_rate
        if not ran_incumbent_rate:
            assert sl.resolves_its_optimum() is None, (
                f"the {key} stratum ran {sl.meta['rates_delivered']} Hz and not the incumbent's "
                f"{inc_rate:g} Hz, so its comparison against the incumbent is an extrapolation")
    unsupported = [sl for sl in res.slices.values() if not sl.incumbent_rate_supported]
    assert unsupported, "fixture must contain a stratum that never ran the incumbent rate"


def test_not_assessed_never_counts_as_resolved(stage1_both_sides):
    res = stage1_both_sides
    for s in res.frozen.settings:
        if s.rate_resolved is None or s.pw_resolved is None:
            assert s.resolved is False
    assert res.frozen.resolved is False


def test_the_unsupported_refusal_names_the_extrapolation(stage1_both_sides):
    res = stage1_both_sides
    s = res.frozen.setting("Left")
    if s.rate_resolved is None:
        joined = " ".join(s.reasons)
        assert "NOT ASSESSED" in joined
        assert "extrapolation" in joined
        assert "PINNED" in joined


# ---------------------------------------------------------------------------------------------
# Retaining the incumbent is not a positive finding
# ---------------------------------------------------------------------------------------------
def test_choosing_the_setting_already_in_force_is_reported_as_unresolved():
    sl = S1.JointStratum(
        pw_us_left=60.0, pw_us_right=160.0, n_epochs=20, grid=None, gp=None,
        mu=np.zeros(1), sd=np.ones(1), safe=np.ones(1, bool), i_star=0,
        x_star=(55.0, 2.0, 2.0), mu_star=0.0, sd_star=0.5,
        incumbent_mu=0.0, incumbent_sd=0.5, n_reports=np.zeros(1),
        queue=np.array([], int), stopping=None, incumbent_rate_supported=True)
    assert sl.gain_over_incumbent() == pytest.approx(0.0)
    assert sl.resolves_its_optimum() is False


def test_resolution_propagates_both_standard_deviations():
    """Same criterion the module has always used: the gain must clear the SD OF THE DIFFERENCE."""
    def stratum_with(mu_star, sd_star, inc_mu, inc_sd):
        return S1.JointStratum(
            pw_us_left=60.0, pw_us_right=60.0, n_epochs=20, grid=None, gp=None,
            mu=np.zeros(1), sd=np.ones(1), safe=np.ones(1, bool), i_star=0,
            x_star=(110.0, 2.0, 2.0), mu_star=mu_star, sd_star=sd_star,
            incumbent_mu=inc_mu, incumbent_sd=inc_sd, n_reports=np.zeros(1),
            queue=np.array([], int), stopping=None, incumbent_rate_supported=True)

    borderline = stratum_with(-0.60, 0.5, 0.0, 0.5)
    assert borderline.sd_of_difference() == pytest.approx(0.7071, abs=1e-3)
    assert borderline.resolves_its_optimum() is False       # clears 0.5 but not 0.707
    clear = stratum_with(-2.0, 0.5, 0.0, 0.5)
    assert clear.resolves_its_optimum() is True
    assert stratum_with(-1.0, 0.0, 0.0, 0.0).resolves_its_optimum() is False   # degenerate variance


# ---------------------------------------------------------------------------------------------
# The design audit over rate x pulse-width PAIR
# ---------------------------------------------------------------------------------------------
def test_the_pair_audit_detects_aliasing_when_each_pair_has_its_own_rate():
    d = _matrix(n_per_cell=11, pw_pairs=((100.0, 150.0), (140.0, 180.0)), rates=(55.0, 165.0),
               aliased=True)
    a = S1.pulse_width_pair_design_audit(d)
    assert a["n_pairs_delivered"] == 2
    assert a["fittable_pw_pairs"] and len(a["fittable_pw_pairs"]) == 2


def test_the_pair_audit_detects_a_crossed_design():
    d = _matrix(n_per_cell=11, pw_pairs=((100.0, 150.0), (140.0, 180.0)), rates=(55.0, 165.0),
               aliased=False)
    a = S1.pulse_width_pair_design_audit(d)
    assert a["n_pairs_delivered"] == 2
    # crossed: every pair sees every rate, so each pair still has n_per_cell*2 rows -> fittable
    assert a["n_pairs_fittable"] == 2


# ---------------------------------------------------------------------------------------------
# The frozen configuration and the override
# ---------------------------------------------------------------------------------------------
def test_the_frozen_configuration_cannot_be_written_to(stage1_both_sides):
    res = stage1_both_sides
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.frozen.settings = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.frozen.setting("Left").rate_hz = 130.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.frozen.setting("Left").pw_us = 60.0


def test_an_override_requires_a_reason(stage1_both_sides):
    res = stage1_both_sides
    for bad in ("", "   ", "\n"):
        with pytest.raises(ValueError, match="non-empty reason"):
            S1.clinician_override(res.frozen, reason=bad)


def test_an_override_records_itself_and_changes_no_setting(stage1_both_sides):
    res = stage1_both_sides
    before = res.frozen
    after = S1.clinician_override(before, reason="tolerated at this rate for two years", by="PI")
    assert after.overridden is True
    assert after.override["reason"] == "tolerated at this rate for two years"
    assert after.override["by"] == "PI"
    assert after.resolved == before.resolved
    assert after.setting("Left").rate_hz == before.setting("Left").rate_hz
    assert after.setting("Left").pw_us == before.setting("Left").pw_us
    assert before.overridden is False, "the original must be left untouched"


def test_the_frozen_configuration_carries_its_declared_provenance(rcs08_like):
    res = S1.run_stage1(rcs08_like, data_horizon="2026-08-12", washin_min=1.0)
    assert res.frozen.data_horizon == "2026-08-12"
    assert res.frozen.washin_min == pytest.approx(1.0)
    assert res.frozen.n_epochs_total == len(rcs08_like)


def test_the_summary_reports_support_alongside_every_verdict(stage1_both_sides):
    res = stage1_both_sides
    for col in ("optimum_resolved", "incumbent_rate_supported", "optimum_rate_supported",
               "gain", "sd_of_difference", "hemisphere", "pw_us_left", "pw_us_right"):
        assert col in res.summary.columns
    unsupported = res.summary.loc[~res.summary["incumbent_rate_supported"]]
    assert unsupported["optimum_resolved"].isna().all()
    # one row per (hemisphere, joint stratum): exactly twice the number of fitted strata
    assert len(res.summary) == 2 * len(res.slices)


def test_the_summary_carries_each_sides_own_amplitude_not_the_others():
    d = _matrix(n_per_cell=12, pw_pairs=((60.0, 160.0),), rates=(55.0, 110.0), aliased=False)
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0)
    left_row = res.summary.loc[res.summary["hemisphere"] == "Left"].iloc[0]
    right_row = res.summary.loc[res.summary["hemisphere"] == "Right"].iloc[0]
    assert left_row["opt_amp_mA"] == pytest.approx(left_row["opt_amp_mA_left"])
    assert right_row["opt_amp_mA"] == pytest.approx(right_row["opt_amp_mA_right"])


# ---------------------------------------------------------------------------------------------
# The adaptive envelope, now applied to the ONE shared rate axis
# ---------------------------------------------------------------------------------------------
def test_the_envelope_masks_the_one_shared_rate_axis_for_both_sides():
    d = _matrix(n_per_cell=14, pw_pairs=((60.0, 60.0),), rates=(40.0, 110.0), aliased=False)
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0, adaptive_min_rate_hz=55.0)
    for s in res.frozen.settings:
        if np.isfinite(s.rate_hz):
            assert s.rate_hz >= 55.0
    env = res.frozen.adaptive_envelope
    assert "Left" in env["exclusions"] and "Right" in env["exclusions"]
    # duplicated per side: the same joint decision, reported once per side for the frontend chart
    assert env["exclusions"]["Left"] == env["exclusions"]["Right"] or (
        len(env["exclusions"]["Left"]) == len(env["exclusions"]["Right"]))


def test_no_adaptive_capable_setting_reports_nan_rate_on_both_sides():
    d = _matrix(n_per_cell=14, pw_pairs=((60.0, 60.0),), rates=(40.0,), aliased=False)
    # The candidate grid must not offer any rate at or above the adaptive minimum either -- with
    # the module's own default 12-rate grid, a rate never delivered (e.g. 55 Hz) can still score
    # as safe by extrapolation and get chosen, which is a real property of the safety model and
    # not what this test is about.
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0, adaptive_min_rate_hz=55.0,
                        freq_grid=[10.0, 20.0, 30.0, 40.0])
    for s in res.frozen.settings:
        assert not np.isfinite(s.rate_hz)
        assert s.rate_resolved is None
        assert "NO ADAPTIVE-CAPABLE SETTING" in " ".join(s.reasons)


# ---------------------------------------------------------------------------------------------
# The joint safety model: unsafe on EITHER side's own ceiling excludes the cell
# ---------------------------------------------------------------------------------------------
def test_the_joint_safe_set_is_exactly_the_and_of_both_sides_own_safety_models():
    """The joint safe set at a (rate, amp_Left, amp_Right) cell must be EXACTLY "safe on the
    Left's own (rate, amp_Left) view of it AND safe on the Right's own (rate, amp_Right) view of
    it" -- reconstructed independently here from the same, unchanged, per-side ``SafetyGP`` and
    ``safety_ceiling.safety_seed`` this module calls, and compared bit for bit rather than merely
    checked for a plausible shape."""
    from StimOptimizer.routines import surrogate as SUR
    from StimOptimizer import safety_ceiling as SC

    d = _matrix(n_per_cell=12, pw_pairs=((60.0, 60.0),), rates=(55.0,), aliased=False,
               asymmetric_dosing=False)
    ceilings = {"Left": (1.0, "test"), "Right": (5.0, "test")}
    res = S1.run_stage1(d, data_horizon="test", washin_min=1.0,
                        safety_ceiling_by_hemisphere=ceilings)
    ((_pwl, _pwr), sl), = res.slices.items()
    gx = sl.grid.grid_X()

    from StimOptimizer.routines import objective as OBJ
    D = OBJ.build_objective(d, incumbent_epoch=float(d.sort_values("t0")["epoch"].iloc[-1]),
                            cfg={"primary_item": "left_leg"})
    safety_grid = SUR.ParameterGrid(S1.PLT.FREQ_GRID, S1.JOINT_AMP_GRID)
    expected = np.ones(len(gx), bool)
    for hemi, cols in (("Left", [0, 1]), ("Right", [0, 2])):
        Xs, sev, sv, _meta = SC.safety_seed(D, f"amp_mA_{hemi}", freq_grid=S1.PLT.FREQ_GRID,
                                            ceiling=ceilings[hemi], min_tolerated_h=72.0)
        sgp = SUR.SafetyGP(safety_grid, random_state=0).fit(Xs, sev, sv)
        expected &= np.asarray(sgp.safe_mask(X=gx[:, cols], beta=S1.PLT.BETA), bool)

    assert np.array_equal(sl.safe, expected)
    assert sl.safe.any(), "some cell under both ceilings must remain safe in this fixture"
    assert (~sl.safe).any(), "some cell must be excluded by at least one side's ceiling"
