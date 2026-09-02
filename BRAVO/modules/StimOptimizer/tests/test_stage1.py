"""Tests for Stage 1, the open-loop search that freezes a configuration.

The tests that matter most here are the ones about what Stage 1 REFUSES to claim. A surrogate that
reports an optimum is easy; a surrogate that reports "I cannot tell you whether this beats what you
are already doing" is the thing this module exists to get right, so most of what follows checks that
an unresolved or unassessable comparison comes back as unresolved or unassessed.
"""
import dataclasses

import numpy as np
import pandas as pd
import pytest

from StimOptimizer import stage1_openloop as S1


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------
def _matrix(n_per_cell=10, pw_levels=(60.0, 140.0), rates=(55.0, 110.0), seed=0,
            aliased=False, effect=0.0):
    """Design matrix with a controllable rate x pulse-width layout.

    ``aliased=True`` gives each pulse width its OWN rate, which is the structure the real RCS08
    record has and the structure under which a pulse-width contrast is not estimable. ``effect``
    adds a pain benefit to the LAST pulse-width level so a resolvable case can be constructed.
    """
    rng = np.random.default_rng(seed)
    rows = []
    ep = 0
    for i, pw in enumerate(pw_levels):
        use = (rates[i % len(rates)],) if aliased else rates
        for rate in use:
            for k in range(n_per_cell):
                ep += 1
                rows.append(dict(
                    epoch=float(ep), freq_hz=float(rate), pw_us_Left=float(pw),
                    amp_mA_Left=float(1.0 + 0.2 * (k % 5)),
                    # A different modulus, so the two amplitude columns are not perfectly
                    # collinear. With `1.2 + 0.2 * (k % 5)` they differed by a constant, which made
                    # the contrast's design matrix rank deficient for a reason that had nothing to
                    # do with pulse width and briefly looked like pulse-width aliasing.
                    amp_mA_Right=float(1.2 + 0.2 * (k % 4)),
                    n=8.0, dur_h=200.0,
                    left_leg_vas=float(50.0 - 10.0 * effect * (i == len(pw_levels) - 1)
                                       + 3.0 * rng.standard_normal()),
                    left_leg_vas_sd=8.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2025-07-01", periods=len(d), freq="3D", tz="UTC")
    return d


@pytest.fixture
def rcs08_like():
    """A matrix reproducing the structural features of the real RCS08 record.

    Three of those features drive every honest refusal Stage 1 makes on the real data, so they are
    reproduced deliberately rather than incidentally: pulse width is aliased with rate, so no rate
    was delivered at two adequately-sampled pulse widths; the incumbent is the most recent epoch and
    sits at one particular (rate, pulse width) pair; and at least one pulse-width stratum never
    delivered the incumbent's rate at all.
    """
    return _matrix(n_per_cell=11, pw_levels=(100.0, 140.0), rates=(55.0, 165.0), aliased=True)


# ---------------------------------------------------------------------------------------------
# The common incumbent
# ---------------------------------------------------------------------------------------------
def test_every_stratum_is_referenced_to_one_common_incumbent(rcs08_like):
    """J is only comparable across strata if they share an incumbent.

    build_objective defines J as the pain item minus its value at the incumbent epoch. If each
    stratum derived its own incumbent — which is what build_context would do, since it takes the
    most recent epoch of whatever frame it is handed — the posterior means could not be compared
    between strata at all, and the pulse-width comparison would be meaningless.
    """
    res = S1.run_stage1(rcs08_like, data_horizon="test", washin_min=1.0)
    expected = float(rcs08_like.sort_values("t0")["epoch"].iloc[-1])
    assert res.frozen.incumbent_epoch == expected
    # J is zero at the incumbent by construction, on the single shared objective build.
    inc = res.D.loc[res.D["epoch"] == expected]
    assert float(inc["J_pain"].iloc[0]) == pytest.approx(0.0, abs=1e-9)


def test_an_incumbent_absent_from_the_matrix_is_refused(rcs08_like):
    with pytest.raises(ValueError, match="not in this design matrix"):
        S1.run_stage1(rcs08_like, incumbent_epoch=99999.0)


# ---------------------------------------------------------------------------------------------
# Pulse-width strata
# ---------------------------------------------------------------------------------------------
def test_one_surface_is_fitted_per_adequately_sampled_pulse_width(rcs08_like):
    res = S1.run_stage1(rcs08_like, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    fitted = sorted(pw for (_h, pw) in res.slices)
    assert fitted == [100.0, 140.0]
    assert set(res.summary["pw_us"]) == {100.0, 140.0}


def test_an_undersampled_stratum_is_skipped_with_its_reason_never_pooled():
    """A thin stratum must be recorded as skipped, not merged into a neighbouring pulse width.

    Pooling it would put two different pulse widths on one surface under a single length scale,
    which is exactly the borrowing the stratification exists to prevent.
    """
    thin = _matrix(n_per_cell=11, pw_levels=(100.0, 140.0), rates=(55.0, 165.0), aliased=True)
    extra = thin.iloc[:2].copy()
    extra["epoch"] = [9001.0, 9002.0]
    extra["pw_us_Left"] = 120.0
    d = pd.concat([thin, extra], ignore_index=True)
    res = S1.run_stage1(d, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    assert 120.0 not in [pw for (_h, pw) in res.slices]
    assert "Left__pw120" in res.skipped
    assert "below the 8-epoch floor" in res.skipped["Left__pw120"]


def test_the_epoch_counts_are_internally_consistent():
    """The per-stratum counts must sum to the total they are reported against.

    Regression, 2026-09-02. The audit exposed one count under the name of another: the number of
    epochs surviving the amplitude and feasibility filters was labelled "fitted epochs", so a
    report stated 54 fitted epochs on the left while listing strata of 22 + 8 + 22 = 52, the
    difference being a skipped 2-epoch stratum. Eligible, in-fitted-strata, and per-stratum counts
    are three different numbers and the arithmetic between them has to close.
    """
    thin = _matrix(n_per_cell=11, pw_levels=(100.0, 140.0), rates=(55.0, 165.0), aliased=True)
    extra = thin.iloc[:2].copy()
    extra["epoch"] = [9001.0, 9002.0]
    extra["pw_us_Left"] = 120.0
    d = pd.concat([thin, extra], ignore_index=True)
    res = S1.run_stage1(d, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    a = res.audit["per_hemisphere"]["Left"]
    per_stratum = {pw: s.n_epochs for (_h, pw), s in res.slices.items()}
    skipped_epochs = sum(v for k, v in a["design"]["epochs_per_pw"].items()
                         if float(k) not in per_stratum)
    assert sum(per_stratum.values()) == a["n_epochs_in_fitted_strata"]
    assert a["n_epochs_in_fitted_strata"] + skipped_epochs == a["n_epochs_eligible"]
    assert sum(a["design"]["epochs_per_pw"].values()) == a["n_epochs_eligible"]
    assert skipped_epochs == 2, "fixture must skip exactly the 2-epoch 120 us stratum"
    # and the frozen setting's count is ONE stratum's, never the hemisphere total
    assert res.frozen.setting("Left").n_epochs_fitted in per_stratum.values()


def test_pulse_width_is_reported_as_not_observed_when_the_column_is_absent(rcs08_like):
    """The real matrix carries pw_us_Left only, so the right hemisphere's pulse width is unknown.

    It must be reported as unknown rather than silently assumed equal to the left hemisphere's.
    The matrix is left intact and ``pw_col`` points at the ABSENT right-hemisphere column, because
    ``objective.build_objective`` requires ``pw_us_Left`` unconditionally for its energy term — so
    "no pulse width for this hemisphere" is exactly the situation of a missing ``pw_us_Right``, not
    of a matrix with no pulse width at all.
    """
    res = S1.run_stage1(rcs08_like, hemispheres=("Right",), data_horizon="test", washin_min=1.0,
                        pw_col="pw_us_Right")
    s = res.frozen.setting("Right")
    assert s.pw_us is None
    assert s.pw_resolved is None
    assert s.resolved is False
    assert any("NOT OBSERVED" in r for r in s.reasons)


# ---------------------------------------------------------------------------------------------
# The support gate on the resolution comparison — the module's most consequential correction
# ---------------------------------------------------------------------------------------------
def test_a_stratum_that_never_ran_the_incumbent_rate_reports_not_assessed_not_resolved():
    """Regression, found by running the real RCS08 matrix on 2026-09-02.

    J is zero at the incumbent BY CONSTRUCTION. A pulse-width stratum with no epoch at the
    incumbent's rate has no data near that cell, so its posterior there reverts towards the
    stratum's own mean. On the real matrix the 140 us stratum, which contains no 55 Hz epoch on
    either hemisphere, predicted J = +1.66 at the incumbent cell with SD 1.60 — a definitional zero
    reported as 1.66 points worse than it is — and against that fictitious baseline its own optimum
    showed a 2.28-point gain that passed the resolution criterion. The verdict was entirely an
    artefact of extrapolating into a rate the stratum never ran, so an unsupported comparison must
    return None rather than a boolean.
    """
    d = _matrix(n_per_cell=11, pw_levels=(100.0, 140.0), rates=(55.0, 165.0), aliased=True)
    res = S1.run_stage1(d, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    inc_rate = res.frozen.incumbent_rate_hz
    for (_h, pw), sl in res.slices.items():
        ran_incumbent_rate = inc_rate in set(sl.meta["rates_delivered"])
        assert sl.incumbent_rate_supported is ran_incumbent_rate
        if not ran_incumbent_rate:
            assert sl.resolves_its_optimum() is None, (
                f"the {pw:g} us stratum ran {sl.meta['rates_delivered']} Hz and not the incumbent's "
                f"{inc_rate:g} Hz, so its comparison against the incumbent is an extrapolation")
    unsupported = [sl for sl in res.slices.values() if not sl.incumbent_rate_supported]
    assert unsupported, "fixture must contain a stratum that never ran the incumbent rate"


def test_not_assessed_never_counts_as_resolved(rcs08_like):
    """A three-valued verdict must collapse to "not resolved", never to "resolved"."""
    res = S1.run_stage1(rcs08_like, data_horizon="test", washin_min=1.0)
    for s in res.frozen.settings:
        if s.rate_resolved is None or s.pw_resolved is None:
            assert s.resolved is False
    assert res.frozen.resolved is False


def test_the_unsupported_refusal_names_the_extrapolation(rcs08_like):
    res = S1.run_stage1(rcs08_like, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
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
    """Gain over the incumbent is zero when the optimum IS the incumbent, so it cannot be resolved.

    This looks like a bug and is not. The gate asks whether the frozen values were CHOSEN on
    evidence, and carrying forward what was already running answers that question negatively.
    """
    sl = S1.Stage1Slice(
        hemisphere="Left", pw_us=60.0, n_epochs=20, grid=None, gp=None,
        mu=np.zeros(1), sd=np.ones(1), safe=np.ones(1, bool), i_star=0,
        x_star=(55.0, 2.0), mu_star=0.0, sd_star=0.5,
        incumbent_mu=0.0, incumbent_sd=0.5, n_reports=np.zeros(1),
        queue=np.array([], int), stopping=None, incumbent_rate_supported=True)
    assert sl.gain_over_incumbent() == pytest.approx(0.0)
    assert sl.resolves_its_optimum() is False


def test_resolution_propagates_both_standard_deviations():
    """Same criterion pipeline.ArmResult uses: the gain must clear the SD OF THE DIFFERENCE.

    A gain of 0.60 clears the candidate SD of 0.50 on its own, but sqrt(0.5^2 + 0.5^2) = 0.707 is
    larger than 0.60, so propagating the incumbent's SD as well correctly withholds the verdict.
    """
    def slice_with(mu_star, sd_star, inc_mu, inc_sd):
        return S1.Stage1Slice(
            hemisphere="Left", pw_us=60.0, n_epochs=20, grid=None, gp=None,
            mu=np.zeros(1), sd=np.ones(1), safe=np.ones(1, bool), i_star=0,
            x_star=(110.0, 2.0), mu_star=mu_star, sd_star=sd_star,
            incumbent_mu=inc_mu, incumbent_sd=inc_sd, n_reports=np.zeros(1),
            queue=np.array([], int), stopping=None, incumbent_rate_supported=True)

    borderline = slice_with(-0.60, 0.5, 0.0, 0.5)
    assert borderline.sd_of_difference() == pytest.approx(0.7071, abs=1e-3)
    assert borderline.resolves_its_optimum() is False       # clears 0.5 but not 0.707
    clear = slice_with(-2.0, 0.5, 0.0, 0.5)
    assert clear.resolves_its_optimum() is True
    assert slice_with(-1.0, 0.0, 0.0, 0.0).resolves_its_optimum() is False   # degenerate variance


# ---------------------------------------------------------------------------------------------
# The design audit over rate x pulse width
# ---------------------------------------------------------------------------------------------
def test_the_audit_detects_aliasing_when_each_pulse_width_has_its_own_rate():
    d = _matrix(n_per_cell=11, pw_levels=(100.0, 140.0), rates=(55.0, 165.0), aliased=True)
    fit = d.loc[d["amp_mA_Left"] > 0]
    a = S1.pulse_width_design_audit(fit)
    assert a["n_pw_levels"] == 2
    assert a["n_rates_with_two_pw_levels"] == 0, "aliased fixture must share no rate"
    assert a["rate_pw_coverage"] < 1.0


def test_the_audit_detects_a_crossed_design():
    d = _matrix(n_per_cell=11, pw_levels=(100.0, 140.0), rates=(55.0, 165.0), aliased=False)
    fit = d.loc[d["amp_mA_Left"] > 0]
    a = S1.pulse_width_design_audit(fit)
    assert a["n_rates_with_two_pw_levels"] == 2
    assert a["n_rates_with_two_fittable_pw_levels"] == 2
    assert a["rate_pw_coverage"] == pytest.approx(1.0)


def test_the_pulse_width_contrast_refuses_a_rank_deficient_design():
    """With rate blocked, a pulse width delivered at one rate only is collinear with that rate.

    statsmodels will return a pseudo-inverse solution rather than complain, so the check has to be
    explicit; a coefficient from a rank-deficient fit is an arbitrary point on a flat ridge.
    """
    d = _matrix(n_per_cell=11, pw_levels=(100.0, 140.0), rates=(55.0, 165.0), aliased=True)
    res = S1.run_stage1(d, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    c = res.audit["per_hemisphere"]["Left"]["contrast"]
    assert c["estimable"] is False
    assert "rank deficient" in c["reason"]
    assert c["coefficients"] == {}


def test_the_pulse_width_contrast_is_estimable_on_a_crossed_design():
    d = _matrix(n_per_cell=12, pw_levels=(100.0, 140.0), rates=(55.0, 165.0), aliased=False,
                effect=1.0)
    res = S1.run_stage1(d, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    c = res.audit["per_hemisphere"]["Left"]["contrast"]
    assert c["estimable"] is True, c["reason"]
    assert c["coefficients"], "a crossed design must yield at least one pulse-width coefficient"
    for lvl, v in c["coefficients"].items():
        assert set(v) >= {"estimate", "ci", "p", "resolved"}
        assert np.isfinite(v["estimate"])


def test_undersampled_levels_are_excluded_from_the_contrast_and_the_exclusion_is_reported():
    """A declared data-scope reduction, not a silent one.

    On the real record a single two-epoch level (120 us, delivered at 145 Hz only) is the whole
    cause of the rank deficiency: with it in, nothing is estimable; with it out, the remaining
    coefficients are. The levels dropped are the same ones the stratified surrogate omits, so both
    views are fitted on the same rows — but the reduction must be visible in the output.
    """
    d = _matrix(n_per_cell=12, pw_levels=(100.0, 140.0), rates=(55.0, 165.0), aliased=False)
    extra = d.iloc[:2].copy()
    extra["epoch"] = [9001.0, 9002.0]
    extra["pw_us_Left"] = 120.0
    d = pd.concat([d, extra], ignore_index=True)
    # The contrast reads `obs_var`, which build_objective produces; it is not in the raw matrix.
    from StimOptimizer.routines import objective as OBJ
    D = OBJ.build_objective(d, incumbent_epoch=float(d["epoch"].iloc[-1]),
                            cfg={"primary_item": "left_leg"})
    fit = D.loc[(D["amp_mA_Left"] > 0) & D["feasible"]]
    c = S1.pulse_width_contrast(fit, reference_pw=100.0)
    assert c["excluded_levels"] == {120.0: 2}
    assert c["n"] == len(fit) - 2
    assert any("stratum floor" in n for n in c["notes"])
    assert 120.0 not in {float(k) for k in c["coefficients"]}


def test_a_sign_disagreement_between_the_two_views_is_reported_as_a_reason():
    """Observed on the real record's right hemisphere on 2026-09-02.

    The stratified surrogate preferred 140 us while the rate-blocked, era-blocked,
    precision-weighted regression on the same rows put 140 us +3.09 NRS points WORSE than the 100 us
    reference (95% CI +0.31 to +5.87, p = 0.030). Reporting only the view that favours the proposal
    is the failure mode this note exists to prevent, so the disagreement has to reach the reasons.
    """
    d = _matrix(n_per_cell=12, pw_levels=(100.0, 140.0), rates=(55.0, 165.0), aliased=False,
                effect=-1.0)                          # make the LAST level worse, not better
    res = S1.run_stage1(d, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    c = res.audit["per_hemisphere"]["Left"]["contrast"]
    if not c["estimable"]:
        pytest.skip("fixture did not yield an estimable contrast")
    s = res.frozen.setting("Left")
    coef = c["coefficients"].get(f"{s.pw_us:g}")
    joined = " ".join(s.reasons)
    if coef is not None and coef["estimate"] > 0:
        assert "DISAGREEMENT BETWEEN TWO VIEWS" in joined
        assert "WORSE" in joined
    else:
        assert "DISAGREEMENT BETWEEN TWO VIEWS" not in joined


def test_a_single_pulse_width_level_is_unidentifiable_not_null():
    d = _matrix(n_per_cell=12, pw_levels=(60.0,), rates=(55.0, 165.0))
    fit = d.loc[d["amp_mA_Left"] > 0]
    c = S1.pulse_width_contrast(fit)
    assert c["estimable"] is False
    assert "never varied" in c["reason"]


# ---------------------------------------------------------------------------------------------
# The frozen configuration and the override
# ---------------------------------------------------------------------------------------------
def test_the_frozen_configuration_cannot_be_written_to(rcs08_like):
    """The device freeze is enforced by the type, not merely documented."""
    res = S1.run_stage1(rcs08_like, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.frozen.settings = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.frozen.setting("Left").rate_hz = 130.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.frozen.setting("Left").pw_us = 60.0


def test_an_override_requires_a_reason(rcs08_like):
    res = S1.run_stage1(rcs08_like, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    for bad in ("", "   ", "\n"):
        with pytest.raises(ValueError, match="non-empty reason"):
            S1.clinician_override(res.frozen, reason=bad)


def test_an_override_records_itself_and_changes_no_setting(rcs08_like):
    res = S1.run_stage1(rcs08_like, hemispheres=("Left",), data_horizon="test", washin_min=1.0)
    before = res.frozen
    after = S1.clinician_override(before, reason="tolerated at this rate for two years", by="PI")
    assert after.overridden is True
    assert after.override["reason"] == "tolerated at this rate for two years"
    assert after.override["by"] == "PI"
    # The override licenses proceeding; it does not make anything resolved and moves no value.
    assert after.resolved == before.resolved
    assert after.setting("Left").rate_hz == before.setting("Left").rate_hz
    assert after.setting("Left").pw_us == before.setting("Left").pw_us
    assert before.overridden is False, "the original must be left untouched"


def test_the_frozen_configuration_carries_its_declared_provenance(rcs08_like):
    res = S1.run_stage1(rcs08_like, hemispheres=("Left",), data_horizon="2026-08-12",
                        washin_min=1.0)
    assert res.frozen.data_horizon == "2026-08-12"
    assert res.frozen.washin_min == pytest.approx(1.0)
    assert res.frozen.n_epochs_total == len(rcs08_like)


def test_an_unknown_hemisphere_column_is_refused_not_substituted(rcs08_like):
    with pytest.raises(KeyError, match="amp_mA_Both"):
        S1.run_stage1(rcs08_like, hemispheres=("Both",))


def test_the_summary_reports_support_alongside_every_verdict(rcs08_like):
    """A reader must be able to see WHY a resolution verdict is trustworthy or absent."""
    res = S1.run_stage1(rcs08_like, data_horizon="test", washin_min=1.0)
    for col in ("optimum_resolved", "incumbent_rate_supported", "optimum_rate_supported",
                "gain", "sd_of_difference"):
        assert col in res.summary.columns
    unsupported = res.summary.loc[~res.summary["incumbent_rate_supported"]]
    assert unsupported["optimum_resolved"].isna().all(), (
        "a stratum without support at the incumbent must report a null verdict, not a boolean")
