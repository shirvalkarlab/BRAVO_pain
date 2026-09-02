"""Tests for the BoTorch surrogate backend in ``routines/surrogate_torch.py``.

Two groups of tests live here and they have different requirements.

The first group needs no PyTorch at all. It covers the amplitude-envelope safety model, which
is deliberately written in plain NumPy, and it covers the optional-import machinery itself.
These tests run in the ordinary ``bravo_app`` environment alongside the rest of the suite, and
they are what checks the claim in ``BOTORCH_REFACTOR.md`` that the module can be imported in a
container that does not have PyTorch installed.

The second group needs PyTorch, GPyTorch and BoTorch and is skipped when they are absent. It
covers the objective surrogate, the preference model, the modelled severity outcome and the
constrained batch acquisition.

Every test here pins a behaviour that either a real defect in the scikit-learn backend
violated, or that the equivalence argument depends on. The two most important are
``test_matched_hyperparameters_reproduce_sklearn_posterior``, which is the evidence that the two
backends compute the same posterior, and ``test_safe_set_is_contiguous_in_amplitude``, which is
the defect this safety model exists to prevent.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer.routines import objective as OBJ
from StimOptimizer.routines import surrogate_torch as ST
from StimOptimizer.routines.surrogate import ObjectiveGP, ParameterGrid

FREQS = [10, 20, 30, 40, 55, 70, 85, 110, 125, 130, 145, 165]
AMPS = np.round(np.arange(0.8, 4.01, 0.1), 2)

# The length scales the scikit-learn backend pins by hand, on the standardised transformed
# axes. Kept here so the equivalence tests use the value the production configuration uses.
PINNED_LENGTH_SCALE = [0.823, 0.72]

needs_torch = pytest.mark.skipif(
    not ST.torch_available(),
    reason="requires the torch/gpytorch/botorch stack, which is an optional dependency")


@pytest.fixture
def grid():
    return ParameterGrid(FREQS, AMPS)


@pytest.fixture
def wide_grid():
    """A grid whose amplitudes extend above the clinician-declared 4.9 mA ceiling.

    The production grid stops at 4.0 mA, so it can never produce a cell labelled ``excluded``.
    This fixture exists so the ceiling is actually exercised rather than assumed.
    """
    return ParameterGrid(FREQS, np.round(np.arange(0.8, 5.31, 0.1), 2))


@pytest.fixture
def epochs():
    """The same six synthetic epochs the existing core tests use.

    Reusing the fixture is deliberate: the equivalence claim is only meaningful if both
    backends are given identical inputs, and this is the input the existing backend is already
    tested on.
    """
    return pd.DataFrame({
        "epoch": [1, 2, 3, 4, 5, 6],
        "freq_hz": [55.0, 55.0, 10.0, 110.0, 130.0, 55.0],
        "amp_mA_Left": [1.6, 1.8, 1.6, 4.0, 2.9, 1.4],
        "amp_mA_Right": [1.2, 1.2, 1.2, 3.0, 3.1, 1.2],
        "pw_us_Left": [60.0] * 6,
        "n": [155, 5, 26, 63, 34, 1],
        "t0": pd.to_datetime(["2026-03-04", "2026-06-11", "2026-01-05",
                              "2025-09-14", "2025-07-17", "2026-02-06"], utc=True),
        "dur_h": [2035.0, 160.0, 358.0, 646.0, 308.0, 40.0],
        "nrs": [7.28, 6.60, 7.08, 7.81, 8.59, 8.00],
        "nrs_sd": [1.24, 0.55, 0.84, 0.76, 0.50, np.nan],
        "left_leg_vas": [72.8, 66.0, 70.8, 78.1, 85.9, 80.0],
        "left_leg_vas_sd": [12.4, 5.5, 8.4, 7.6, 5.0, np.nan],
    })


@pytest.fixture
def fitted_data(epochs):
    """``(X, y, y_var)`` in the form both backends' ``fit`` expects."""
    d = OBJ.build_objective(epochs, incumbent_epoch=1)
    return (d[["freq_hz", "amp_mA_Left"]].to_numpy(float),
            d["J"].to_numpy(float), d["obs_var"].to_numpy(float))


@pytest.fixture
def delivered():
    """Settings the participant actually received and sustained, in (freq_hz, amp_mA)."""
    return np.array([[10.0, 1.6], [55.0, 1.6], [55.0, 1.8], [55.0, 1.4],
                     [110.0, 4.0], [130.0, 2.9]])


# =========================================================================================
# Group one: no PyTorch required
# =========================================================================================
def test_module_imports_without_torch_and_says_so():
    """Importing this module must never fail, and it must report its own availability.

    This is the property the container argument rests on. If PyTorch is absent the import
    still succeeds, ``torch_available()`` returns False, and ``require_torch()`` raises an
    error that names the missing packages rather than an obscure ``NameError`` from somewhere
    inside a model constructor.
    """
    assert isinstance(ST.torch_available(), bool)
    if ST.torch_available():
        assert ST.require_torch() is None
    else:
        with pytest.raises(ImportError, match="torch, gpytorch and botorch"):
            ST.require_torch()


def test_safe_set_is_contiguous_in_amplitude(grid, delivered):
    """The safe set must be reachable by ramping amplitude upward.

    This is the defect the envelope model exists to prevent. In the scikit-learn safety model
    the safe set is a confidence-bound region over a fitted severity surface, and it can
    contain a cell at a higher amplitude while excluding one at a lower amplitude at the same
    frequency. A clinician ramps amplitude through intermediate values, so such a
    recommendation cannot be programmed. Here the safe set is a threshold on amplitude at each
    frequency, so at every frequency it is an interval running up from the lowest amplitude on
    the grid, and the property holds for any input rather than for fortunate inputs.
    """
    saf = ST.AmplitudeEnvelopeSafety(grid).fit(delivered)
    assert saf.assert_contiguous() == []
    surface = grid.as_surface(saf.safe_mask().astype(float)) > 0.5
    for i in range(surface.shape[0]):
        row = surface[i]
        if row.any():
            # every cell below the highest safe cell at this frequency is also safe
            assert row[: int(np.flatnonzero(row).max()) + 1].all()
    # the same must hold once the eligible set is widened to allow bounded exploration
    assert saf.assert_contiguous(saf.candidate_mask(unknown_amp_step=0.4)) == []


def test_no_monotone_amplitude_ceiling_is_imposed(grid, delivered):
    """The envelope must not be a monotone increasing function of amplitude by construction.

    The coded acute record for this participant does not support a severity-versus-amplitude
    relationship: within the 417 non-procedural steps with stimulation on, the Spearman
    correlation between amplitude and severity rank is -0.013 with p = 0.79. The envelope must
    therefore be driven by where stimulation was actually delivered and nothing else. This test
    checks the consequence: the envelope varies non-monotonically across frequency, taking its
    largest value at 110 Hz where a 4.0 mA setting was delivered and falling again above it,
    which a fitted monotone ceiling could not produce.
    """
    saf = ST.AmplitudeEnvelopeSafety(grid).fit(delivered)
    env = saf.envelope(np.array(FREQS, float))
    assert env[np.array(FREQS) == 110][0] == pytest.approx(4.0)
    assert env[np.array(FREQS) == 165][0] < env[np.array(FREQS) == 110][0]
    diffs = np.diff(env)
    assert (diffs > 0).any() and (diffs < 0).any(), "envelope should not be monotone in frequency"


def test_unknown_region_is_labelled_unknown_not_safe_or_unsafe(wide_grid, delivered):
    """Above 4 mA the record holds 5 steps, which supports no statement in either direction.

    The requirement is that this region is reported as unknown rather than silently folded
    into either the safe set or the unsafe set. A boolean mask cannot express that, which is
    why ``classify`` exists alongside ``safe_mask``.
    """
    saf = ST.AmplitudeEnvelopeSafety(wide_grid).fit(delivered)
    lab = saf.classify()
    amp = wide_grid.grid_X()[:, 1]
    assert set(np.unique(lab)) == {"supported", "unknown", "excluded"}
    # nothing above the data-supported maximum may be called supported
    assert not (lab[amp > ST.DATA_SUPPORTED_AMP_MAX + 1e-9] == "supported").any()
    # the band between the data-supported maximum and the clinician ceiling is unknown
    band = (amp > ST.DATA_SUPPORTED_AMP_MAX + 1e-9) & (amp <= ST.CLINICIAN_AMP_CEILING + 1e-9)
    assert band.any() and (lab[band] == "unknown").all()
    # unknown is excluded from the conservative boolean safe mask
    assert not saf.safe_mask()[saf.unknown_mask()].any()


def test_clinician_ceiling_is_a_hard_bound(wide_grid, delivered):
    """No amount of model optimism may propose an amplitude above 4.9 mA.

    The ceiling is a clinical declaration, not an estimate, so it is enforced by removing cells
    from the candidate set rather than by weighting them. Even asking for an unbounded
    exploration step must not breach it.
    """
    saf = ST.AmplitudeEnvelopeSafety(wide_grid).fit(delivered)
    amp = wide_grid.grid_X()[:, 1]
    assert (amp > ST.CLINICIAN_AMP_CEILING).any(), "fixture must contain cells above the ceiling"
    for step in (0.0, 0.4, 5.0, 1e6):
        m = saf.candidate_mask(include_unknown=True, unknown_amp_step=step)
        assert amp[m].max() <= ST.CLINICIAN_AMP_CEILING + 1e-9
    assert saf.excluded_mask().sum() == int((amp > ST.CLINICIAN_AMP_CEILING + 1e-9).sum())


def test_expansion_cap_keys_off_worst_severity(grid, delivered):
    """A moderate report must stop the safe boundary moving outward at all.

    Same two-brake arrangement as the scikit-learn backend, following Sarikhani et al. 2022:
    the boundary may move 0.4 mA when nothing has been reported, 0.2 mA after a mild report,
    and not at all after a moderate or severe one.
    """
    saf = ST.AmplitudeEnvelopeSafety(grid).fit(delivered)
    n_none = saf.expansion_capped_mask("none").sum()
    n_mild = saf.expansion_capped_mask("mild").sum()
    n_mod = saf.expansion_capped_mask("moderate").sum()
    assert n_none > n_mild > n_mod
    assert n_mod == saf.safe_mask().sum(), "after a moderate report only the supported set remains"
    with pytest.raises(ValueError, match="unknown severity"):
        saf.expansion_capped_mask("a bit")


def test_envelope_refuses_an_empty_or_unusable_history(grid):
    """With no delivered history there is no evidence of tolerability anywhere.

    The scikit-learn backend's failure mode was a seed that silently produced an empty safe
    set. Here the equivalent situation raises, with a message that says what is missing.
    """
    with pytest.raises(ValueError, match="at least one delivered setting"):
        ST.AmplitudeEnvelopeSafety(grid).fit(np.empty((0, 2)))
    # a delivered setting that produced a moderate-or-worse event is not evidence of tolerance
    with pytest.raises(ValueError, match="every delivered setting was dropped"):
        ST.AmplitudeEnvelopeSafety(grid).fit(np.array([[55.0, 2.0]]),
                                             severity=[OBJ.SE_THRESHOLD])


def test_envelope_does_not_extrapolate_beyond_delivered_frequencies(grid):
    """Outside the delivered frequency range the envelope is held flat, not continued.

    Extrapolating a fitted envelope is how the polynomial prior mean in the scikit-learn
    backend came to bend the wrong way outside its fitted range. Holding the envelope flat at
    the nearest delivered frequency is the conservative alternative and is what is tested here.
    """
    saf = ST.AmplitudeEnvelopeSafety(grid).fit(np.array([[55.0, 2.0], [110.0, 3.0]]))
    assert saf.envelope([10.0])[0] == pytest.approx(2.0)   # below the delivered range
    assert saf.envelope([165.0])[0] == pytest.approx(3.0)  # above it
    assert saf.envelope([30.0])[0] == pytest.approx(2.0)
    mid = saf.envelope([np.sqrt(55.0 * 110.0)])[0]         # midpoint on the log2 axis
    assert 2.0 < mid < 3.0


def test_envelope_report_is_self_describing(grid, delivered):
    """The report must state the basis for the classification, not just the counts.

    A safety output that gives a count of safe cells without saying what made them safe
    invites the reader to assume a severity model was fitted. This one says it was not.
    """
    rep = ST.AmplitudeEnvelopeSafety(grid).fit(delivered).report()
    assert rep["n_supported"] + rep["n_unknown"] + rep["n_excluded"] == len(grid)
    assert rep["contiguity_violations"] == []
    assert "no fitted severity-versus-amplitude relationship" in rep["basis"]
    assert rep["amp_ceiling_mA"] == ST.CLINICIAN_AMP_CEILING


# =========================================================================================
# Group two: PyTorch required
# =========================================================================================
@needs_torch
def test_interface_parity_with_sklearn_objective_gp(grid, fitted_data):
    """The BoTorch objective surrogate must expose the same methods with the same shapes.

    The point of this backend is that it can be swapped in behind the existing interface, so
    the interface is itself the specification and is tested directly.
    """
    X, y, yv = fitted_data
    for cls in (ObjectiveGP, ST.TorchObjectiveGP):
        m = cls(grid).fit(X, y, yv)
        mu, sd = m.predict_grid()
        assert mu.shape == sd.shape == (len(grid),)
        assert np.all(np.isfinite(mu)) and np.all(sd > 0)
        assert m.predict(X, return_std=False).shape == (len(y),)
        assert isinstance(m.hyperparameters, dict)
        fant = m.with_fantasy(np.array([[70.0, 2.0]]), 0.3)
        assert fant.predict_grid()[0].shape == (len(grid),)
        lmu, lsd = m.loo_predict()
        assert lmu.shape == (len(y),) and np.isfinite(lmu).all()


@needs_torch
def test_matched_hyperparameters_reproduce_sklearn_posterior(grid, fitted_data):
    """Given identical hyperparameters the two backends must give the same posterior.

    This is the single most important test in the file. It is what distinguishes a valid
    alternative implementation from a rewrite that merely looks plausible: with the same kernel
    hyperparameters, the same zero mean function and the same total noise on the diagonal, any
    difference between the two posteriors would mean one of them computes the Gaussian-process
    predictive distribution incorrectly.

    Three conventions have to be matched for this to hold, and each was a real source of
    disagreement while this backend was being written. The objective is standardised with the
    population standard deviation rather than the sample standard deviation that BoTorch's
    ``Standardize`` transform uses. The predictive standard deviation includes the homoscedastic
    noise term, because in the scikit-learn construction the ``WhiteKernel`` sits inside the
    kernel and so contributes to the diagonal at test points as well as training points. And
    the mean function is set to zero, because the scikit-learn backend has none while this
    backend defaults to a fitted constant.
    """
    X, y, yv = fitted_data
    rep = ST.equivalence_report(grid, X, y, yv, fixed_length_scale=PINNED_LENGTH_SCALE)
    m = rep["matched"]
    assert m["max_abs_diff_mean"] < 1e-10, m
    assert m["max_abs_diff_sd"] < 1e-10, m
    assert m["best_cell_agrees"]
    assert m["correlation_mean"] == pytest.approx(1.0, abs=1e-9)


@needs_torch
def test_as_used_arms_diverge_and_the_report_says_where(grid, fitted_data):
    """Fitted as each would actually be used, the two backends must differ, and visibly.

    They differ because they answer the identifiability problem differently: the scikit-learn
    arm pins the length scales by hand while this one fits them under a prior. The test asserts
    that the divergence exists and that the report carries the diagnostic information needed to
    interpret it, because a report that hid the divergence would be worse than no report.
    """
    X, y, yv = fitted_data
    rep = ST.equivalence_report(grid, X, y, yv, fixed_length_scale=PINNED_LENGTH_SCALE)
    au = rep["as_used"]
    assert au["max_abs_diff_mean"] > au["rms_diff_mean"] > 0
    assert au["max_abs_diff_mean"] > 10 * rep["matched"]["max_abs_diff_mean"]
    assert "lengthscale" in au["botorch_hyperparameters"]
    assert "kernel" in au["sklearn_hyperparameters"]
    assert set(au["worst_cell"]) >= {"freq_hz", "amp_mA", "sklearn_mean", "botorch_mean"}


@needs_torch
def test_length_scale_prior_keeps_the_estimate_off_the_boundary(grid, fitted_data):
    """The prior must prevent the degenerate boundary solution that pure likelihood finds.

    This is the identifiability fix, stated as a testable consequence. Fitted by marginal
    likelihood alone with the length scales free, the scikit-learn backend lands on a boundary
    of its length-scale box in the frequency dimension, which is the signature of a
    hyperparameter the data do not identify. Fitted by posterior mode under the log-normal
    prior, this backend lands strictly inside its allowed range in every dimension, so no
    dimension has to be pinned by hand.
    """
    X, y, yv = fitted_data
    free = ObjectiveGP(grid, n_restarts=12).fit(X, y, yv)
    lo, hi = free.length_scale_bounds
    sk_ls = np.asarray(free.gp_.kernel_.k1.k2.length_scale, float).ravel()
    on_boundary = np.isclose(sk_ls, lo, rtol=1e-3) | np.isclose(sk_ls, hi, rtol=1e-3)
    assert on_boundary.any(), (
        "the unpinned scikit-learn fit is expected to sit on a length-scale boundary on this "
        f"data; got {sk_ls.tolist()} with bounds {(lo, hi)}")

    tg = ST.TorchObjectiveGP(grid).fit(X, y, yv)
    ls = np.asarray(tg.hyperparameters["lengthscale"], float)
    assert (ls > ST._MIN_LENGTHSCALE * 2).all(), ls
    assert np.isfinite(tg.hyperparameters["log_prior"])
    # fitting maximises the sum, so the reported decomposition must add up
    hp = tg.hyperparameters
    assert hp["log_posterior"] == pytest.approx(
        hp["log_marginal_likelihood"] + hp["log_prior"], rel=1e-9)


@needs_torch
def test_latent_only_standard_deviation_is_smaller_by_the_nugget(grid, fitted_data):
    """The two standard deviations offered must differ by exactly the fitted noise variance.

    The default includes the homoscedastic noise so that the backend is a drop-in replacement
    for the scikit-learn one. ``latent_only=True`` removes it, giving the uncertainty about the
    response surface itself. Which of the two belongs in an acquisition function is a real
    question, so the difference is exposed rather than buried, and this test pins the
    relationship between them.
    """
    X, y, yv = fitted_data
    m = ST.TorchObjectiveGP(grid).fit(X, y, yv)
    _, sd_full = m.predict_grid()
    _, sd_latent = m.predict_grid(latent_only=True)
    assert (sd_full >= sd_latent - 1e-12).all()
    nugget = m.hyperparameters["noise"] * m._y_scale ** 2
    assert np.allclose(sd_full ** 2 - sd_latent ** 2, nugget, atol=1e-10)


@needs_torch
def test_objective_gp_refuses_infeasible_and_degenerate_input(grid, epochs):
    """Validation must match the scikit-learn backend's, including the infinite-J refusal.

    An infinite objective marks a cell hard-rejected for a moderate or severe side effect. Such
    a cell is evidence for the safety model, and feeding it to the objective model would let one
    rejected setting dominate every other observation.
    """
    e = epochs.copy()
    e["se_severity"] = ["none", "moderate", "none", "none", "none", "none"]
    d = OBJ.build_objective(e, incumbent_epoch=1)
    X = d[["freq_hz", "amp_mA_Left"]].to_numpy(float)
    with pytest.raises(ValueError, match="hard-infeasible"):
        ST.TorchObjectiveGP(grid).fit(X, d["J"].to_numpy(float), d["obs_var"].to_numpy(float))

    d2 = OBJ.build_objective(epochs, incumbent_epoch=1)
    X2, y2 = d2[["freq_hz", "amp_mA_Left"]].to_numpy(float), d2["J"].to_numpy(float)
    with pytest.raises(ValueError, match="strictly positive"):
        ST.TorchObjectiveGP(grid).fit(X2, y2, np.zeros(len(y2)))
    with pytest.raises(ValueError, match="at least 3 observations"):
        ST.TorchObjectiveGP(grid).fit(X2[:2], y2[:2], d2["obs_var"].to_numpy(float)[:2])
    with pytest.raises(RuntimeError, match="not fitted"):
        ST.TorchObjectiveGP(grid).predict_grid()


@needs_torch
def test_fantasy_freezes_hyperparameters(grid, fitted_data):
    """A hypothetical observation may move the posterior but not the smoothness.

    Sequential-greedy batch selection conditions on hypothetical outcomes. If those
    hypotheticals were allowed to re-estimate the kernel, the batch would be chosen partly on
    the basis of data that do not exist.
    """
    X, y, yv = fitted_data
    m = ST.TorchObjectiveGP(grid).fit(X, y, yv)
    before = np.asarray(m.hyperparameters["lengthscale"], float)
    f = m.with_fantasy(np.array([[70.0, 2.0], [85.0, 2.4]]), 0.3)
    after = np.asarray(f.hyperparameters["lengthscale"], float)
    assert np.allclose(before, after)
    assert len(f.y_) == len(y) + 2
    # the fantasy value at a new cell is that cell's current posterior mean
    assert f.y_[-2] == pytest.approx(m.predict(np.array([[70.0, 2.0]]), return_std=False)[0])
    # and the posterior standard deviation there must fall once it is treated as observed
    assert f.predict(np.array([[70.0, 2.0]]))[1] < m.predict(np.array([[70.0, 2.0]]))[1]


@needs_torch
def test_preference_gp_interface_and_ranking(grid):
    """The preference model must recover a known ranking and expose the existing interface.

    The latent value function is generated with a maximum near 85 Hz, which is the shape Louie
    et al. 2021 reported: the objective optimiser drives frequency to the highest tolerable
    value while the preference model peaks at 70 to 110 Hz. The test asserts that all pairwise
    orderings are recovered from a complete set of noiseless comparisons, which is the weakest
    check that would catch a sign error or an index error.
    """
    X = np.array([[10.0, 1.6], [20.0, 2.0], [55.0, 1.8], [70.0, 2.2],
                  [110.0, 2.6], [130.0, 2.9], [145.0, 3.2], [165.0, 3.6]])
    util = -((np.log2(X[:, 0]) - np.log2(85.0)) ** 2) / 2 - 0.2 * X[:, 1]
    pairs = np.array([(i, j) if util[i] > util[j] else (j, i)
                      for i in range(len(X)) for j in range(i + 1, len(X))])
    pg = ST.TorchPreferenceGP(grid).fit(X, pairs)

    mu, sd = pg.predict(X)
    assert mu.shape == sd.shape == (len(X),)
    agree = np.mean([(mu[i] > mu[j]) == (util[i] > util[j])
                     for i in range(len(X)) for j in range(i + 1, len(X))])
    assert agree == 1.0, f"recovered only {agree:.2%} of the known orderings"
    i, loc = pg.best()
    assert loc.shape == (2,) and 0 <= i < len(grid)
    assert pg.holdout_accuracy(folds=5, random_state=0) > 0.5
    assert pg.predict()[0].shape == (len(grid),)


@needs_torch
def test_preference_prob_prefer_is_a_probability_and_antisymmetric(grid):
    """``prob_prefer(a, b)`` and ``prob_prefer(b, a)`` must sum to one.

    Antisymmetry is the property that fails if the joint posterior covariance is mishandled,
    which is the substantive change this implementation makes over the hand-written version. It
    also has to stay a probability: the hand-written version treats the two settings as
    independent, which inflates the variance of their difference and pulls the answer toward
    one half.
    """
    X = np.array([[10.0, 1.6], [55.0, 1.8], [110.0, 2.6], [165.0, 3.6]])
    util = np.array([0.0, 1.0, 0.5, -1.0])
    pairs = np.array([(i, j) if util[i] > util[j] else (j, i)
                      for i in range(4) for j in range(i + 1, 4)])
    pg = ST.TorchPreferenceGP(grid).fit(X, pairs)
    ab = pg.prob_prefer(X[[1, 0, 2]], X[[3, 3, 1]])
    ba = pg.prob_prefer(X[[3, 3, 1]], X[[1, 0, 2]])
    assert ((ab >= 0) & (ab <= 1)).all()
    assert np.allclose(ab + ba, 1.0, atol=1e-9)
    # a setting compared with itself is a coin flip, and the joint covariance is what makes
    # this come out exactly right: independent variances would not cancel
    assert pg.prob_prefer(X[[0]], X[[0]])[0] == pytest.approx(0.5, abs=1e-9)
    assert ab[0] > 0.5, "the preferred setting must be given the larger probability"
    with pytest.raises(ValueError, match="same shape"):
        pg.prob_prefer(X[[0]], X[[1, 2]])


@needs_torch
def test_preference_gp_rejects_ties_and_bad_indices(grid):
    """Ties have no representation in a probit likelihood and must not be silently encoded."""
    X = np.array([[10.0, 1.6], [55.0, 1.8], [110.0, 2.6]])
    with pytest.raises(ValueError, match="cannot be preferred to itself"):
        ST.TorchPreferenceGP(grid).fit(X, [(0, 0)])
    # Empty input is rejected by the shape check rather than by the emptiness check, because
    # `list(comparisons)` turns any empty input into a one-dimensional array. The dedicated
    # "no comparisons supplied" branch is therefore unreachable through `fit`, in this backend
    # and equally in the scikit-learn one whose validation order it mirrors. That branch is
    # kept for interface parity and is not asserted on here, since asserting on unreachable
    # behaviour would be asserting on nothing.
    for empty in ([], np.empty((0, 2), int)):
        with pytest.raises(ValueError, match="iterable of .winner, loser. index pairs"):
            ST.TorchPreferenceGP(grid).fit(X, empty)
    with pytest.raises(IndexError):
        ST.TorchPreferenceGP(grid).fit(X, [(0, 7)])
    with pytest.raises(RuntimeError, match="not fitted"):
        ST.TorchPreferenceGP(grid).predict()


@needs_torch
def test_severity_gp_prior_mean_is_flat_not_monotone(grid):
    """The severity model must not assume severity rises with amplitude.

    Given severity that is genuinely unrelated to amplitude, which is what the coded record
    shows for this participant, the fitted posterior must be essentially flat in amplitude. The
    scikit-learn safety model would impose a non-decreasing polynomial mean here and report a
    rise that the data do not contain.
    """
    rng = np.random.default_rng(11)
    amps = np.round(rng.uniform(0.8, 4.0, 60), 1)
    freqs = rng.choice(FREQS, 60)
    # severity assigned independently of amplitude: 7% moderate, 10% mild, rest none
    u = rng.random(60)
    sev = np.where(u < 0.07, 2.0, np.where(u < 0.17, 1.0, 0.0))
    sg = ST.SeverityGP(grid, threshold=2.0).fit(np.column_stack([freqs, amps]), sev,
                                                np.full(60, 0.25))
    gx = grid.grid_X()
    mu, _ = sg.predict()
    lo = mu[gx[:, 1] <= 1.5].mean()
    hi = mu[gx[:, 1] >= 3.5].mean()
    spread = mu.max() - mu.min()
    assert abs(hi - lo) < 0.5 * max(spread, 1e-9) + 0.2, (
        f"posterior severity mean moved from {lo:.3f} at low amplitude to {hi:.3f} at high "
        "amplitude on data with no amplitude relationship")
    with pytest.raises(ValueError, match="non-finite severity"):
        sg.fit(np.column_stack([freqs, amps])[:5], [0.0, 1.0, np.inf, 0.0, 1.0])


@needs_torch
def test_constrained_acquisition_returns_eligible_cells_with_provenance(grid, fitted_data,
                                                                       delivered):
    """A proposed batch must be inside the eligible set and must say why each cell qualifies.

    A recommendation table that gives frequency and amplitude without saying whether the cell
    has direct evidence of tolerability or is a deliberate step into an untested region is not
    usable by a clinician, so the label travels with the proposal.
    """
    X, y, yv = fitted_data
    tg = ST.TorchObjectiveGP(grid).fit(X, y, yv)
    saf = ST.AmplitudeEnvelopeSafety(grid).fit(delivered)
    sel = ST.ConstrainedBatchSelector(tg, safety=saf, mc_samples=128, random_state=0)
    batch = sel.select_batch(q=4, include_unknown=True, unknown_amp_step=0.4)

    assert len(batch) == 4
    eligible = set(np.flatnonzero(saf.candidate_mask(unknown_amp_step=0.4)).tolist())
    seen = set()
    for b in batch:
        assert b["index"] in eligible
        assert b["safety_label"] in {"supported", "unknown"}
        assert b["freq_hz"] in FREQS
        assert np.isfinite(b["mu"]) and b["sd"] > 0
        seen.add((b["freq_hz"], b["amp_mA"]))
    assert len(seen) == 4, "a batch must not repeat the same cell"
    # the reported grid index must agree with the reported coordinates
    gx = grid.grid_X()
    for b in batch:
        assert gx[b["index"], 0] == pytest.approx(b["freq_hz"])
        assert gx[b["index"], 1] == pytest.approx(b["amp_mA"])


@needs_torch
def test_outcome_constraint_moves_the_batch_away_from_predicted_risk(grid, delivered):
    """The severity constraint must change the chosen batch when it disagrees with the objective.

    This is the test of the mechanism rather than of the plumbing, and it needs a case the
    plumbing alone cannot pass: an objective that is best at high frequency together with a
    severity model that disfavours high frequency. A post-hoc boolean mask has only two
    responses available, admitting the region at full value or forbidding it entirely. The
    outcome constraint weights each cell's improvement by the posterior probability that
    severity clears the threshold there, so the batch shifts away from the risky region in
    proportion to the risk rather than all at once.
    """
    Xo = np.array([[10.0, 1.6], [40.0, 1.8], [70.0, 2.0], [110.0, 2.2],
                   [145.0, 2.4], [165.0, 2.6]])
    yo = np.array([0.6, 0.3, 0.0, -0.4, -0.9, -1.1])   # J is minimised: best at high frequency
    tg = ST.TorchObjectiveGP(grid).fit(Xo, yo, np.full(6, 0.09))
    assert grid.grid_X()[np.argmin(tg.predict_grid()[0]), 0] >= 145.0

    Xs = np.column_stack([np.repeat(FREQS, 3), np.tile([1.2, 2.2, 3.2], len(FREQS))])
    sev = np.where(Xs[:, 0] >= 125, 1.3, 0.2)
    sg = ST.SeverityGP(grid, threshold=1.0).fit(Xs, sev, np.full(len(sev), 0.6))

    saf = ST.AmplitudeEnvelopeSafety(grid).fit(np.array([[10.0, 2.0], [70.0, 2.5], [165.0, 3.0]]))
    kw = dict(q=3, include_unknown=True, unknown_amp_step=0.4)
    with_c = ST.ConstrainedBatchSelector(tg, severity_gp=sg, safety=saf, mc_samples=512,
                                         random_state=0).select_batch(**kw)
    without = ST.ConstrainedBatchSelector(tg, severity_gp=None, safety=saf, mc_samples=512,
                                          random_state=0).select_batch(**kw)
    f_with = np.mean([b["freq_hz"] for b in with_c])
    f_without = np.mean([b["freq_hz"] for b in without])
    assert f_with < f_without, (
        f"the constraint did not move the batch: mean frequency {f_with:.1f} Hz with the "
        f"constraint against {f_without:.1f} Hz without it")
    assert all(b["p_severity_below_threshold"] is not None for b in with_c)
    assert all(b["p_severity_below_threshold"] is None for b in without)
    assert "outcome constraint inside the acquisition function" in with_c[0]["constraint_handling"]


@needs_torch
def test_constraint_probability_is_graded_where_a_mask_would_be_binary(grid):
    """There must exist cells whose constraint probability a boolean mask cannot represent.

    This is the concrete statement of what the masking approach discards. If every cell's
    probability were near zero or near one then a mask would lose nothing and the extra
    machinery would not be worth its cost; the assertion is that this is not the case.
    """
    from scipy.stats import norm
    Xs = np.column_stack([np.repeat(FREQS, 3), np.tile([1.2, 2.2, 3.2], len(FREQS))])
    sev = np.where(Xs[:, 0] >= 125, 1.3, 0.2)
    sg = ST.SeverityGP(grid, threshold=1.0).fit(Xs, sev, np.full(len(sev), 0.6))
    mu, sd = sg.predict()
    p = norm.cdf((sg.threshold - mu) / np.maximum(sd, 1e-12))
    graded = int(((p > 0.05) & (p < 0.95)).sum())
    assert graded > 0, "no cell carries a genuinely uncertain constraint on this data"


@needs_torch
def test_selector_refuses_an_empty_or_undersized_candidate_set(grid, fitted_data, delivered):
    """Asking for more cells than are eligible must raise rather than return a short batch.

    A silently shortened batch would be programmed as though it were complete.
    """
    X, y, yv = fitted_data
    tg = ST.TorchObjectiveGP(grid).fit(X, y, yv)
    saf = ST.AmplitudeEnvelopeSafety(grid).fit(delivered)
    sel = ST.ConstrainedBatchSelector(tg, safety=saf, mc_samples=64, random_state=0)
    n_eligible = int(saf.candidate_mask(include_unknown=False).sum())
    with pytest.raises(ValueError, match="only .* are eligible"):
        sel.select_batch(q=n_eligible + 1, include_unknown=False)
    with pytest.raises(ValueError, match="no eligible candidates"):
        sel.select_batch(q=1, include_unknown=False,
                         exclude_idx=np.arange(len(grid)))
    with pytest.raises(ValueError, match="q must be at least 1"):
        sel.select_batch(q=0)


# =========================================================================================
# Group three: the reported marginal likelihood, and the length-scale prior as measured
#
# Every test below was added after two defects were found in the reported hyperparameters. The
# earlier version evaluated the marginal log likelihood with the model left in evaluation mode,
# where GPyTorch returns the posterior predictive distribution rather than the prior, and it
# then added the log prior to a quantity that already contained it. Both defects were invisible
# to the internal-consistency check in
# ``test_length_scale_prior_keeps_the_estimate_off_the_boundary``, because the wrong numbers
# were self-consistent. These tests anchor against an external reference instead.
# =========================================================================================
@needs_torch
def test_reported_marginal_likelihood_matches_sklearn_when_the_models_are_identical(
        grid, fitted_data):
    """The decisive external anchor for the reported log marginal likelihood.

    With matched kernel hyperparameters, a zero mean and the same total noise on the diagonal,
    both backends describe exactly the same Gaussian density over the same standardised data, so
    their log marginal likelihoods are the same number and not merely similar. Any difference is
    a defect in one of them. This is what the earlier implementation failed: evaluated in
    evaluation mode and with the prior added twice, it was out by several nats.
    """
    X, y, yv = fitted_data
    sk = ObjectiveGP(grid, fixed_length_scale=PINNED_LENGTH_SCALE, n_restarts=8,
                     random_state=0).fit(X, y, yv)
    k = sk.gp_.kernel_
    tg = ST.TorchObjectiveGP(
        grid, mean="zero", random_state=0,
        fixed_hyperparameters=dict(
            lengthscale=np.asarray(k.k1.k2.length_scale, float).ravel(),
            outputscale=float(k.k1.k1.constant_value),
            noise=float(k.k2.noise_level))).fit(X, y, yv)
    hp = tg.hyperparameters
    assert hp["log_marginal_likelihood"] == pytest.approx(
        float(sk.gp_.log_marginal_likelihood_value_), abs=1e-6)


@needs_torch
def test_the_log_prior_is_counted_exactly_once(grid, fitted_data):
    """The log posterior must exceed the log marginal likelihood by the log prior, no more.

    Stated against an independently recomputed log prior rather than against the model's own
    reported one, so that a decomposition which happens to be internally consistent but wrong
    cannot pass.
    """
    X, y, yv = fitted_data
    tg = ST.TorchObjectiveGP(grid, random_state=0).fit(X, y, yv)
    hp = tg.hyperparameters
    import torch
    with torch.no_grad():
        recomputed = sum(float(prior.log_prob(closure(module)).sum())
                         for _, module, prior, closure, _ in tg.model_.named_priors())
    assert hp["log_prior"] == pytest.approx(recomputed, rel=1e-9)
    assert hp["log_posterior"] - hp["log_marginal_likelihood"] == pytest.approx(
        recomputed, rel=1e-9)


@needs_torch
def test_reading_the_hyperparameters_leaves_the_model_ready_to_predict(grid, fitted_data):
    """Computing the marginal likelihood requires training mode; prediction requires eval mode.

    The property must restore whichever mode it found, or a caller who logs the hyperparameters
    between two predictions silently gets different answers from the second one.
    """
    X, y, yv = fitted_data
    tg = ST.TorchObjectiveGP(grid, random_state=0).fit(X, y, yv)
    before_mu, before_sd = tg.predict_grid()
    assert not tg.model_.training
    _ = tg.hyperparameters
    assert not tg.model_.training
    after_mu, after_sd = tg.predict_grid()
    assert np.allclose(before_mu, after_mu)
    assert np.allclose(before_sd, after_sd)


@needs_torch
def test_fitting_under_the_prior_cannot_beat_pure_likelihood_on_likelihood(grid, fitted_data):
    """A sanity ordering that the corrected number must satisfy and the wrong one did not.

    The scikit-learn backend with free length scales maximises the marginal likelihood directly.
    This backend maximises the marginal likelihood plus a log prior. Whatever the prior does to
    the estimate, the likelihood it lands on cannot be higher than the maximum, so the corrected
    value must sit at or below the scikit-learn one. The earlier implementation reported a value
    ABOVE it, which is impossible and is what first exposed the defect.
    """
    X, y, yv = fitted_data
    free = ObjectiveGP(grid, n_restarts=12, random_state=0).fit(X, y, yv)
    tg = ST.TorchObjectiveGP(grid, random_state=0).fit(X, y, yv)
    assert (tg.hyperparameters["log_marginal_likelihood"]
            <= float(free.gp_.log_marginal_likelihood_value_) + 1e-6)


@needs_torch
def test_prior_scale_sweep_reports_the_transition_rather_than_a_single_number(grid,
                                                                             fitted_data):
    """The prior scale controls the answer non-monotonically, so the sweep must show the curve.

    The claim being pinned is not where along the curve anything happens -- the cross-data-set
    agreement is not monotone in the prior scale and the fitted values depend on the data set --
    but that the sweep returns a comparable row for every scale and that tightening the prior
    does change the fitted length scales. A sweep that returned the same length scales throughout
    would mean the prior was not entering the fit at all.
    """
    X, y, yv = fitted_data
    out = ST.prior_scale_sweep(grid, X, y, yv, prior_scales=(np.sqrt(3.0), 0.5, 0.25),
                               fixed_length_scale=PINNED_LENGTH_SCALE)
    rows = out["sweep"]
    assert len(rows) == 3
    for r in rows:
        assert set(r) >= {"prior_scale", "lengthscale", "max_abs_diff_mean",
                          "correlation_mean", "best_cell_agrees"}
        assert len(r["lengthscale"]) == 2
        assert np.isfinite(r["max_abs_diff_mean"])
    broad = np.asarray(rows[0]["lengthscale"], float)
    tight = np.asarray(rows[-1]["lengthscale"], float)
    assert not np.allclose(broad, tight, rtol=1e-3), (broad, tight)
    # a tighter prior pulls the length scales toward the prior's own large median
    assert tight.min() > broad.min()


@needs_torch
def test_a_tighter_prior_moves_the_estimate_toward_the_prior_median(grid, fitted_data):
    """The prior scale must actually control how far the estimate is pulled toward the prior.

    This is the mechanism behind the written recommendation that the default prior is a knob
    rather than a fix. Only the direction is pinned here, not the size of the effect: how far
    the default prior moves the estimate depends on how informative the data are, and this
    fixture holds six synthetic epochs while the recommendation in ``BOTORCH_REFACTOR.md`` is
    measured on the 71 epochs of the real design matrix. A future change that made the default
    prior strongly informative would flip the inequality below.
    """
    X, y, yv = fitted_data
    default = ST.TorchObjectiveGP(grid, random_state=0).fit(X, y, yv)
    tight = ST.TorchObjectiveGP(grid, prior_scale=0.25, random_state=0).fit(X, y, yv)
    d_ls = float(default.hyperparameters["lengthscale"][0])
    t_ls = float(tight.hyperparameters["lengthscale"][0])
    prior_median = float(np.exp(ST.dim_scaled_prior_loc(2)))
    assert abs(t_ls - prior_median) < abs(d_ls - prior_median), (d_ls, t_ls, prior_median)


@needs_torch
def test_which_way_the_free_fit_degenerates_is_a_property_of_the_data_not_the_model(
        grid, fitted_data):
    """The direction of the length-scale degeneracy differs between data sets, so no test or
    docstring may assert one direction as though it were a property of the model.

    This test exists because an earlier version of the test above asserted that the
    default-prior fit stays closer to the unpenalised maximum-likelihood estimate than a
    tight-prior fit does. That assertion failed, and the reason is recorded here rather than
    deleted. On this six-epoch fixture the unpenalised fit runs to the UPPER bound of the
    length-scale box in the frequency dimension, so the default prior moves the estimate by
    almost the whole range. On the 71-epoch RCS08 design matrix the same unpenalised fit gives
    0.203 and the default prior moves it only to 0.222. Same model, same prior, opposite
    behaviour, because the likelihood is weakly determined in both and its weak preference
    points different ways.
    """
    X, y, yv = fitted_data
    free = ObjectiveGP(grid, n_restarts=12, random_state=0).fit(X, y, yv)
    lo, hi = free.length_scale_bounds
    mle_freq = float(np.asarray(free.gp_.kernel_.k1.k2.length_scale, float).ravel()[0])
    default = float(ST.TorchObjectiveGP(grid, random_state=0)
                    .fit(X, y, yv).hyperparameters["lengthscale"][0])

    # on THIS data the unpenalised fit is degenerate at the upper bound
    assert np.isclose(mle_freq, hi, rtol=1e-3), (
        f"expected the unpenalised frequency length scale to sit at the upper bound {hi} on "
        f"this fixture; got {mle_freq}. If this has changed, the docstring of "
        "TorchObjectiveGP quoting this measurement needs re-deriving.")
    # and the prior moves it by more than an order of magnitude, in the downward direction
    assert default < mle_freq / 10.0, (default, mle_freq)
    # while remaining strictly inside the box, which is the property that does generalise
    assert lo < default < hi, (lo, default, hi)


@needs_torch
def test_a_tight_prior_picks_the_length_scale_rather_than_estimating_it(grid, fitted_data):
    """The measurement behind the recommendation NOT to fix the problem by tightening the prior.

    Three data sets with genuinely different likelihoods are fitted at the same tight prior
    scale. If the prior were merely regularising, the fitted length scales would still differ
    between them. They do not: they agree to several significant figures and sit near the
    prior's own median, which means the prior has replaced the data's answer rather than
    stabilising it. A tight prior scale is a declared assumption, not an estimate.
    """
    X, y, yv = fitted_data
    variants = {"as measured": y, "reversed": y[::-1].copy(), "scaled by three": y * 3.0}
    fitted = {}
    for name, yy in variants.items():
        fitted[name] = float(ST.TorchObjectiveGP(grid, prior_scale=0.25, random_state=0)
                             .fit(X, yy, yv).hyperparameters["lengthscale"][0])
    values = np.array(list(fitted.values()))
    assert values.max() - values.min() < 0.01, fitted
    prior_median = float(np.exp(ST.dim_scaled_prior_loc(2)))
    assert abs(values.mean() - prior_median) < 0.5 * prior_median, (fitted, prior_median)

    # the same three data sets under the DEFAULT prior do not collapse this way, so the
    # collapse is attributable to the prior scale and not to the data being uninformative
    loose = np.array([float(ST.TorchObjectiveGP(grid, prior_scale=np.sqrt(3.0), random_state=0)
                            .fit(X, yy, yv).hyperparameters["lengthscale"][0])
                      for yy in variants.values()])
    assert abs(loose.mean() - prior_median) > abs(values.mean() - prior_median)


def test_frequency_lengthscale_profile_needs_no_torch_and_finds_its_maxima(grid, fitted_data):
    """The profile diagnostic is deliberately scikit-learn only.

    Characterising the likelihood surface with the same optimiser whose behaviour is under
    investigation would confound a property of the surface with a property of the optimiser, so
    this function uses the other backend and runs without PyTorch installed.
    """
    X, y, yv = fitted_data
    out = ST.profile_frequency_lengthscale(grid, X, y, yv,
                                           values=np.geomspace(0.05, 30.0, 12))
    assert len(out["profile"]) == 12
    for row in out["profile"]:
        assert np.isfinite(row["log_marginal_likelihood"])
        assert row["log_posterior"] <= row["log_marginal_likelihood"]
    assert out["argmax_log_marginal_likelihood"] > 0
    assert isinstance(out["local_maxima_log_posterior"], list)
