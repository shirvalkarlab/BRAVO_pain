"""A BoTorch/GPyTorch implementation of the StimOptimizer surrogates, offered as an
alternative backend behind the same interface as ``surrogate.py`` and ``preference.py``.

Why this file exists
--------------------
The scikit-learn stack in ``surrogate.py`` works, and nothing here is intended to replace it
until the numbers in :func:`equivalence_report` have been read and accepted. It exists because
three specific problems in that stack were patched by hand rather than solved, and the BoTorch
and GPyTorch libraries provide the machinery to solve each one directly.

1.  **The frequency length scale is not identifiable from the historical data.** Profiling the
    log posterior over that length scale on the RCS08 warm start gives two competing solutions,
    one near 0.22 on the standardised log2 frequency axis in which each frequency is nearly
    independent of its neighbours and one near 2.6 in which the surface is smooth across the
    whole range, separated by about 2.8 nats in favour of the first. The current code responds
    by pinning the length scale to 0.823, a value chosen by hand which happens to lie in the
    valley between the two. This file instead places a prior on the length scales and fits the
    posterior mode, which makes the assumption explicit, updatable and reflected in the reported
    uncertainty. Note carefully that the DEFAULT prior does not by itself select the smooth
    solution on this data: it is broad, and it moves the fitted frequency length scale only from
    0.20 to 0.22. The measurement, and the prior scale at which the answer changes, are in
    :func:`prior_scale_sweep` and in the docstring of :class:`TorchObjectiveGP`.

2.  **The safety model's two-anchor seed can produce a safe set that is not contiguous in
    amplitude.** A clinician ramps stimulation amplitude upward through intermediate values, so
    a recommended setting that sits above a band of cells the model calls unsafe cannot be
    reached in practice. The safety model in this file is an amplitude envelope, which is a
    lower interval in amplitude at every frequency, so contiguity holds by construction rather
    than by luck. See :class:`AmplitudeEnvelopeSafety`.

3.  **A monotone polynomial prior mean bends the wrong way outside the range it was fitted on,
    and the severity data does not support it in the first place.** The coded acute record for
    this participant contains 774 steps, and within it amplitude does not predict side-effect
    severity: among non-procedural steps with stimulation switched on (n = 417) the Spearman
    correlation between amplitude and severity rank is -0.013 with p = 0.79, the rate of
    moderate-or-worse events is 4.3 percent below 2 mA against 4.8 percent at or above 2 mA,
    and five moderate events occurred at 0.0 mA. A model that forces severity to increase with
    amplitude is therefore asserting a relationship the data contradicts. This file does not
    impose one.

What is deliberately unchanged
------------------------------
The kernel is still Matern with smoothness parameter nu = 3/2 and separate length scales per
input dimension. That is the choice every clinically deployed system in this literature made
(Sarikhani et al. 2022, doi:10.1088/1741-2552/ac86a2; Cole et al. 2024,
doi:10.1088/1741-2552/ad6cf3; Louie et al. 2021, doi:10.1186/s12984-021-00873-9), and a
response surface that is continuous but not infinitely smooth is the right assumption for a
dose-response curve. The :class:`~StimOptimizer.routines.surrogate.ParameterGrid` from the
existing module is reused unchanged, so both backends see identical transformed inputs, which
is what makes the comparison in :func:`equivalence_report` meaningful.

Optional dependency
-------------------
PyTorch, GPyTorch and BoTorch are imported lazily and the import failure is captured rather
than raised. Importing this module on a machine without PyTorch installed therefore succeeds,
:func:`torch_available` returns ``False``, and any attempt to construct one of the model
classes raises a clear error naming the missing package. This is what allows the production
Django container to ship without PyTorch while a research environment can still use this
backend. The reasoning behind that arrangement is written up in ``BOTORCH_REFACTOR.md``; the
decision about whether to add PyTorch to the container is not made here.
"""
from __future__ import annotations

import math
import warnings

from . import objective as _OBJ
import numpy as np

from .objective import SE_THRESHOLD
from .surrogate import ParameterGrid

# --- optional dependency handling ---------------------------------------------------------
# Everything torch-related is imported inside this block. If the import fails the exception is
# stored and re-reported by require_torch(), so that merely importing this module is always
# safe. Nothing at module scope may touch a torch symbol.
_IMPORT_ERROR: Exception | None = None
try:  # pragma: no cover - the covered path is the one where the import succeeds
    import torch
    from botorch.acquisition.logei import qLogNoisyExpectedImprovement
    from botorch.acquisition.objective import LinearMCObjective
    from botorch.fit import fit_gpytorch_mll
    from botorch.models import ModelListGP, PairwiseGP, SingleTaskGP
    from botorch.models.pairwise_gp import PairwiseLaplaceMarginalLogLikelihood
    from botorch.optim import optimize_acqf_discrete
    from botorch.sampling.normal import SobolQMCNormalSampler
    from gpytorch.constraints import GreaterThan
    from gpytorch.kernels import MaternKernel, ScaleKernel
    from gpytorch.likelihoods import FixedNoiseGaussianLikelihood
    from gpytorch.means import ConstantMean, ZeroMean
    from gpytorch.mlls import ExactMarginalLogLikelihood
    from gpytorch.priors import LogNormalPrior
except Exception as exc:  # ImportError, but a broken install can raise other things
    _IMPORT_ERROR = exc


def torch_available() -> bool:
    """Whether the PyTorch/GPyTorch/BoTorch stack imported successfully.

    Call this to decide at run time whether the BoTorch backend can be offered, rather than
    wrapping constructor calls in a try/except.
    """
    return _IMPORT_ERROR is None


def require_torch() -> None:
    """Raise a informative error if the PyTorch stack is unavailable, otherwise do nothing."""
    if _IMPORT_ERROR is not None:
        raise ImportError(
            "The BoTorch surrogate backend requires the packages torch, gpytorch and botorch, "
            "and importing them failed with: "
            f"{type(_IMPORT_ERROR).__name__}: {_IMPORT_ERROR}. "
            "Install them with `pip install botorch`, which pulls torch, gpytorch and "
            "linear_operator as dependencies. The scikit-learn backend in "
            "StimOptimizer.routines.surrogate has no such requirement and remains available."
        ) from _IMPORT_ERROR


def _t(a):
    """Convert an array-like to a double-precision torch tensor.

    Double precision throughout, not single. Gaussian-process fitting inverts a covariance
    matrix that becomes badly conditioned as length scales grow, and single precision produces
    Cholesky failures on exactly the well-sampled data where the model should be most reliable.
    """
    require_torch()
    return torch.as_tensor(np.asarray(a, float), dtype=torch.double)


# --- the length-scale prior ----------------------------------------------------------------
# Hvarfner, Hellsten and Nardi (2024), "Vanilla Bayesian Optimization Performs Great in High
# Dimensions" (arXiv:2402.02229), propose a log-normal prior on each length scale whose location
# grows with the input dimension, and this is the prior BoTorch now applies by default. The
# location is sqrt(2) + log(d)/2 and the scale is sqrt(3), on the log length-scale.
_PRIOR_SCALE = math.sqrt(3.0)
# Length scales below this value are excluded outright. This is a numerical guard rather than a
# scientific statement: at a length scale far below the spacing of the standardised grid the
# covariance matrix becomes the identity and the Cholesky factorisation stops being informative.
_MIN_LENGTHSCALE = 0.025


def dim_scaled_prior_loc(n_dim: int) -> float:
    """Location parameter of the log-normal length-scale prior for ``n_dim`` inputs."""
    return math.sqrt(2.0) + math.log(float(n_dim)) / 2.0


def _matern_kernel(n_dim, *, nu=1.5, prior_loc=None, prior_scale=_PRIOR_SCALE,
                   min_lengthscale=_MIN_LENGTHSCALE):
    """A Matern kernel with one length scale per dimension and a log-normal prior on each.

    The prior is what replaces the hand-pinned length scale of the scikit-learn backend. See
    :class:`TorchObjectiveGP` for why that substitution is the principled one.
    """
    require_torch()
    loc = dim_scaled_prior_loc(n_dim) if prior_loc is None else float(prior_loc)
    base = MaternKernel(
        nu=float(nu), ard_num_dims=int(n_dim),
        lengthscale_prior=LogNormalPrior(loc, float(prior_scale)),
        lengthscale_constraint=GreaterThan(float(min_lengthscale)),
    )
    # The outputscale of a ScaleKernel is the signal variance. It plays the same role as
    # scikit-learn's ConstantKernel factor, and it is left free with no prior because the data
    # determine it well: it is the overall vertical extent of the response surface, which every
    # observation informs.
    return ScaleKernel(base)


class TorchObjectiveGP:
    """Gaussian-process posterior over the composite objective J, which is minimised.

    This matches the interface of :class:`StimOptimizer.routines.surrogate.ObjectiveGP`:
    ``fit(X, y, y_var)``, ``predict(X, return_std=True)``, ``predict_grid()``,
    ``with_fantasy(X_new, var_new)``, ``loo_predict(groups)`` and a ``hyperparameters``
    property. ``X`` is ``(n, 2)`` in the original units of frequency in hertz and amplitude in
    milliamps; the grid's transform puts frequency on a base-2 logarithmic axis and standardises
    both axes before the kernel sees them.

    Why a prior on the length scales is preferable to pinning them
    --------------------------------------------------------------
    The problem being solved is that the frequency length scale is only weakly identified by
    the historical data. The historical settings changed frequency and time together, so a
    contrast between two frequencies also contains the drift in the participant's pain over the
    months separating them, and the likelihood cannot separate the two. Maximum likelihood
    resolves this indeterminacy by pushing the length scale to the smallest value allowed,
    which amounts to the model concluding that neighbouring frequencies tell it nothing about
    each other. That conclusion is an artefact of the historical design, not a finding about
    the nervous system.

    Pinning the length scale by hand does prevent that failure, and the reasoning recorded in
    the existing code for doing so is sound as far as it goes. But pinning has three costs.
    First, it states the assumption as a certainty: the fitted model behaves as though the
    frequency length scale were known exactly, so every posterior standard deviation it reports
    is too small, and those standard deviations are what the acquisition function uses to decide
    where to sample next. Second, it does not update. As prospective data accumulate and begin
    to identify the length scale, a pinned value stays pinned and the model cannot learn from
    them; a prior is progressively overwhelmed by data, which is the behaviour wanted. Third,
    the pinned value has to come from somewhere, and in practice it came from inspecting the
    same likelihood surface whose flatness is the problem.

    A prior expresses the same scientific assumption as a distribution instead of a point. The
    default here is the log-normal prior of Hvarfner et al. (2024) that BoTorch adopted as its
    default, whose location increases with the number of input dimensions. On the standardised
    axes used here its median length scale is 5.817, meaning it expects the response surface to
    vary smoothly across the whole searched range. Fitting then maximises the posterior rather
    than the likelihood, so no dimension is fixed by hand and the reported uncertainty accounts
    for the fact that the smoothness is estimated rather than known.

    An earlier version of this docstring also claimed that the prior "assigns very little mass
    to the near-zero length scales that maximum likelihood would otherwise select" and that
    "where the data are informative they dominate". Both claims were removed because the
    measurement below contradicts them: on the RCS08 design matrix the fit under the default
    prior lands at a frequency length scale of 0.22, which is a near-zero value on these axes,
    and at four of the five prior scales tested the fitted value barely differs across data sets
    whose likelihoods disagree by orders of magnitude. The argument for a prior over a pinned
    point value still stands, but it is an argument about honesty of representation, not about
    the prior extracting a better answer from the data.

    What the prior actually does, measured on two data sets
    ------------------------------------------------------
    The paragraph above is the argument for a prior. It is not a claim that the DEFAULT prior
    solves the identifiability problem, and it does not. The measurements below come from
    :func:`prior_scale_sweep` and :func:`profile_frequency_lengthscale` and can be re-run at any
    time. Two data sets are used deliberately: the 71 feasible epochs of the RCS08 design matrix
    on the 230-cell grid, and the six-epoch synthetic fixture the test suite uses. Reporting only
    one of them is what made the earlier version of this docstring wrong.

    Profiling the log posterior over the frequency length scale, with the amplitude length
    scale, the signal variance and the noise re-optimised at each value, shows that on the RCS08
    design matrix the surface is BIMODAL rather than flat. One solution sits near 0.22 on the
    standardised log2 axis, which is the model treating each frequency as nearly independent of
    its neighbours. The other sits near 2.6, which is the model borrowing across the whole
    frequency range. The likelihood prefers the first by about 2.8 nats, and the hand-pinned
    value of 0.823 sits in the valley between them, preferred by neither.

    **Which value maximum likelihood reports is not stable across data sets.** With the length
    scales free and no prior, the scikit-learn backend gives a frequency length scale of 0.203
    on the RCS08 design matrix but runs to the UPPER bound of 20.0 on the six-epoch fixture --
    opposite ends of the permitted range from the same non-identifiability. Any statement of the
    form "the prior barely moves the estimate" or "the prior rescues the estimate from a
    near-zero value" is therefore a statement about one data set and not about the model. The
    earlier version of this docstring made the first of those statements without that
    qualification, having measured only the RCS08 design matrix.

    **What is stable is that the prior, not the data, largely picks the answer.** Fitting the
    same backend at a fixed prior scale across four data sets whose likelihoods disagree -- the
    RCS08 design matrix and three variants of the six-epoch fixture -- gives these fitted
    frequency length scales:

    ===========  ==========  ==========  =============================
    Prior scale  RCS08 (71)  Fixture (6) Spread across four data sets
    ===========  ==========  ==========  =============================
    1.732 (def)  0.222       0.288       0.066
    1.000        0.541       2.140       1.599
    0.500        4.664       4.530       0.133
    0.350        5.239       5.146       0.093
    0.250        5.465       5.465       0.0001
    ===========  ==========  ==========  =============================

    Read the spread column carefully, because it is NOT monotone in the prior scale and an
    earlier version of this docstring described it as though it were a single threshold. Ranked
    from most to least agreement between data sets the scales run 0.25 (0.0001), then the
    DEFAULT of 1.732 (0.066), then 0.35 (0.093), then 0.5 (0.133), and last 1.0 (1.599). The
    default scale is the second most convergent row here, not a row in which the data drive the
    answer, and a scale of 1.0 is the only setting at which the four data sets separate at all.

    The implication is worse for identifiability than a threshold would be. At the default scale
    all four land between 0.222 and 0.288, a short length scale, even though their unpenalised
    maximum-likelihood estimates are 0.203 and 20.0 -- two orders of magnitude apart. At 0.5 and
    tighter all four land near the prior median of 5.817. So at four of the five scales tested
    the fit returns essentially the same number whichever data set it was shown; what differs
    between those four is WHICH number, and the prior scale sets it. **No tested setting returns
    a frequency length scale that is both stable and data-driven.** Fixing a prior scale is
    therefore choosing the length scale, which is a legitimate modelling decision but has to be
    declared as an assumption in ``OBJECTIVE_SPEC.md`` rather than presented as a fit. It is the
    reason this docstring no longer recommends any particular prior scale as the fix.

    None of this makes a prior worse than pinning. A prior still updates as prospective data
    arrive, still propagates the smoothness uncertainty into the posterior standard deviations
    the acquisition function reads, and still comes from a published default rather than from
    inspecting this data set. But the honest summary is that the identifiability problem is not
    solved by adopting the default prior; it is made explicit and given a single knob, and that
    knob turns out to control the answer almost completely once it is turned even moderately.

    Correspondence with the scikit-learn backend
    --------------------------------------------
    Three details are matched exactly so that :func:`equivalence_report` compares like with
    like. First, ``y`` is standardised here in NumPy using the same population standard
    deviation (divisor ``n``) that the scikit-learn backend uses, rather than being handed to
    BoTorch's ``Standardize`` outcome transform, which uses the sample standard deviation
    (divisor ``n - 1``). Second, the per-observation variances are divided by the squared
    standardisation scale so that they are in the same units as the kernel diagonal, and they
    enter through a fixed-noise likelihood. Third, that likelihood also carries a single learned
    homoscedastic term, which is the counterpart of the ``WhiteKernel`` in the scikit-learn
    kernel; both backends therefore have the same total noise structure of a known
    per-observation part plus one fitted part.

    One deliberate difference: the mean function defaults to a fitted constant rather than to
    zero. On standardised data a zero mean is very nearly right, but a constant mean lets the
    model fall back to the average objective far from any observation instead of to exactly the
    mean of the training set. Pass ``mean="zero"`` to reproduce the scikit-learn behaviour,
    which is what the matched arm of the equivalence check does.

    Parameters
    ----------
    grid
        The shared :class:`~StimOptimizer.routines.surrogate.ParameterGrid`.
    nu
        Matern smoothness parameter. Left at 3/2 to match the existing backend and the cited
        literature. Note that BoTorch's own default helper uses 5/2, so this must be set
        explicitly rather than taken from the library default.
    prior_loc, prior_scale
        Location and scale of the log-normal prior on each length scale, on the log scale.
        ``prior_loc=None`` uses the dimension-scaled default described above.
    fixed_hyperparameters
        For the equivalence check only. A dictionary with keys ``lengthscale`` (one value per
        dimension), ``outputscale`` and ``noise`` that sets those values and skips fitting
        entirely. This is how the two backends are given identical hyperparameters so that the
        remaining difference is attributable to the linear algebra rather than to the fitting.
    mean
        ``"constant"`` (default) or ``"zero"``.
    random_state
        Seed for the fitting routine's initialisation. BoTorch's fitting is deterministic given
        the seed, and unlike the scikit-learn backend it does not need many random restarts,
        because the prior removes the degenerate optimum that the restarts were guarding
        against.
    """

    def __init__(self, grid: ParameterGrid, *, nu=1.5, prior_loc=None,
                 prior_scale=_PRIOR_SCALE, min_lengthscale=_MIN_LENGTHSCALE,
                 fixed_hyperparameters=None, mean="constant", random_state=0):
        require_torch()
        self.grid = grid
        self.nu = float(nu)
        self.prior_loc = prior_loc
        self.prior_scale = float(prior_scale)
        self.min_lengthscale = float(min_lengthscale)
        self.fixed_hyperparameters = fixed_hyperparameters
        if mean not in ("constant", "zero"):
            raise ValueError("mean must be either 'constant' or 'zero'")
        self.mean = mean
        self.random_state = int(random_state)
        self.model_ = None

    def _clone(self):
        return TorchObjectiveGP(
            self.grid, nu=self.nu, prior_loc=self.prior_loc, prior_scale=self.prior_scale,
            min_lengthscale=self.min_lengthscale,
            fixed_hyperparameters=self.fixed_hyperparameters, mean=self.mean,
            random_state=self.random_state)

    # --- fitting -------------------------------------------------------------------------
    def _build(self, Z, yz, alpha, *, fit: bool):
        """Construct the model on already-transformed inputs and standardised outputs."""
        n_dim = Z.shape[1]
        kernel = _matern_kernel(n_dim, nu=self.nu, prior_loc=self.prior_loc,
                                prior_scale=self.prior_scale,
                                min_lengthscale=self.min_lengthscale)
        fixed = self.fixed_hyperparameters
        # `learn_additional_noise` adds one fitted homoscedastic variance on top of the known
        # per-observation variances. That is the direct counterpart of the WhiteKernel term in
        # the scikit-learn kernel. When hyperparameters are supplied it is switched off and the
        # supplied noise is folded into the fixed diagonal instead, so that the diagonal is
        # exactly known and the two backends can be compared to machine precision.
        extra = None if fixed is None else float(fixed["noise"])
        noise = alpha if extra is None else alpha + extra
        likelihood = FixedNoiseGaussianLikelihood(
            noise=_t(noise), learn_additional_noise=(extra is None))
        mean_module = ZeroMean() if self.mean == "zero" else ConstantMean()
        model = SingleTaskGP(
            train_X=_t(Z), train_Y=_t(yz).unsqueeze(-1), likelihood=likelihood,
            covar_module=kernel, mean_module=mean_module, outcome_transform=None)
        if fixed is not None:
            ls = np.atleast_1d(np.asarray(fixed["lengthscale"], float))
            if ls.size == 1:
                ls = np.repeat(ls, n_dim)
            if ls.size != n_dim:
                raise ValueError(f"fixed lengthscale must have {n_dim} entries or be scalar")
            with torch.no_grad():
                model.covar_module.base_kernel.lengthscale = _t(ls)
                model.covar_module.outputscale = _t(float(fixed["outputscale"]))
                if self.mean == "constant":
                    model.mean_module.constant.fill_(float(fixed.get("constant", 0.0)))
            self._extra_noise = extra
        elif fit:
            torch.manual_seed(self.random_state)
            with warnings.catch_warnings():
                # BoTorch warns when the fitted length scale sits against its lower bound. With
                # a prior in place that should not happen, and if it does the caller should see
                # it, so warnings are promoted rather than suppressed.
                warnings.simplefilter("always")
                fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model))
            self._extra_noise = float(
                model.likelihood.second_noise_covar.noise.detach().flatten()[0])
        else:
            self._extra_noise = 0.0
        model.eval()
        return model

    def fit(self, X, y, y_var):
        """Fit to observed objective values with known per-observation variances.

        The validation performed here is deliberately identical to the scikit-learn backend's,
        including the refusal of non-finite objective values. An infinite J marks a cell that
        was hard-rejected for a moderate or severe side effect; such a cell is evidence for the
        safety model and must not be fed to the objective model, where it would dominate every
        other observation.
        """
        X = np.atleast_2d(np.asarray(X, float))
        y = np.asarray(y, float).ravel()
        y_var = np.asarray(y_var, float).ravel()
        if not (len(y) == len(y_var) == X.shape[0]):
            raise ValueError("X, y and y_var must have matching length")
        if np.any(y_var <= 0):
            raise ValueError("observation variances must be strictly positive")
        if not np.all(np.isfinite(y)):
            raise ValueError(
                "non-finite J passed to TorchObjectiveGP: these are hard-infeasible cells "
                "(moderate/severe side effect). Filter on the `feasible` flag from "
                "build_objective before fitting; they inform the safety model, not this one.")
        if len(y) < 3:
            raise ValueError(f"need at least 3 observations to fit hyperparameters, got {len(y)}")

        self._y_loc = float(y.mean())
        self._y_scale = float(max(y.std(ddof=0), 1e-9))
        yz = (y - self._y_loc) / self._y_scale
        alpha = y_var / self._y_scale ** 2
        self.model_ = self._build(self.grid.transform(X), yz, alpha, fit=True)
        self.X_, self.y_, self.y_var_ = X, y, y_var
        return self

    def _check(self):
        if self.model_ is None:
            raise RuntimeError("TorchObjectiveGP is not fitted")

    # --- prediction ----------------------------------------------------------------------
    def predict(self, X, return_std=True, *, latent_only=False):
        """Posterior mean, and optionally standard deviation, in the original units of J.

        By default the returned standard deviation includes the fitted homoscedastic noise
        term, because that is what the scikit-learn backend returns and the acquisition code
        downstream is calibrated against it. Under the scikit-learn construction the
        ``WhiteKernel`` sits inside the kernel, so its variance appears on the diagonal at test
        points as well as training points, and the predictive standard deviation therefore
        describes a single noisy measurement rather than the noise-free response surface.

        Pass ``latent_only=True`` for the standard deviation of the underlying response surface
        with the measurement noise removed. That is the quantity a purist would put into an
        expected-improvement calculation, since the improvement of interest is in the true
        response and not in one noisy reading of it. The difference is a constant added to every
        variance on the grid, so it changes the absolute level of the acquisition function but
        moves the ranking of cells only slightly. Both are offered because the choice should be
        visible rather than implicit.
        """
        self._check()
        Zq = _t(self.grid.transform(X))
        with torch.no_grad():
            post = self.model_.posterior(Zq)
            mu = post.mean.squeeze(-1).detach().numpy()
            var = post.variance.squeeze(-1).detach().numpy()
        mu = mu * self._y_scale + self._y_loc
        if not return_std:
            return mu
        if not latent_only:
            var = var + self._extra_noise
        return mu, np.sqrt(np.maximum(var, 0.0)) * self._y_scale

    def predict_grid(self, **kwargs):
        return self.predict(self.grid.grid_X(), **kwargs)

    @property
    def hyperparameters(self):
        """Fitted hyperparameters, in a form comparable with the scikit-learn backend's.

        ``lengthscale`` is on the standardised transformed axes, so the first entry is in units
        of log2 frequency divided by the grid's frequency spread and is not directly readable as
        hertz. ``log_marginal_likelihood`` is the log marginal likelihood of the standardised
        data, which is the same quantity the scikit-learn backend reports, so the two are
        comparable when the hyperparameters are matched. ``log_posterior`` is that value plus the
        log prior density of the hyperparameters, and it is the quantity fitting actually
        maximises here.

        Two corrections were made to an earlier version of this property, and both changed the
        reported numbers materially, so they are recorded rather than quietly fixed.

        First, the marginal log likelihood must be evaluated with the model in TRAINING mode.
        GPyTorch's ``ExactGP.__call__`` returns the prior latent distribution in training mode
        and the posterior predictive distribution in evaluation mode, and ``_build`` leaves the
        model in evaluation mode so that prediction works. Evaluating the marginal likelihood on
        the posterior at the training inputs is not the marginal likelihood of anything; GPyTorch
        itself emits ``GPInputWarning`` when it happens. On the RCS08 warm start the difference
        was 7.0 nats, from a reported -97.32 to a correct -104.27 for the sum of the log
        likelihood and the log prior.

        Second, ``ExactMarginalLogLikelihood`` already adds the log prior of every registered
        prior into the value it returns, and then divides the total by the number of
        observations. Multiplying back by the number of observations therefore recovers the log
        likelihood PLUS the log prior, which is the log posterior and not the marginal
        likelihood. The earlier version labelled that quantity ``log_marginal_likelihood`` and
        then added the log prior to it a second time to form ``log_posterior``, so the prior was
        counted twice. The decomposition below subtracts instead.

        The corrected marginal likelihood can be checked against the scikit-learn backend: with
        its length scales left free, scikit-learn maximises the marginal likelihood directly and
        reaches -100.30 on this data, while this backend maximises the marginal likelihood plus
        the log prior and reaches -100.36 for the likelihood part. The BoTorch value must be
        slightly lower, and it is, by 0.06 nats.
        """
        self._check()
        k = self.model_.covar_module
        ls = k.base_kernel.lengthscale.detach().numpy().ravel().tolist()
        was_training = self.model_.training
        with torch.no_grad():
            log_prior = 0.0
            for _, module, prior, closure, _ in self.model_.named_priors():
                log_prior += float(prior.log_prob(closure(module)).sum())
            mll = ExactMarginalLogLikelihood(self.model_.likelihood, self.model_)
            self.model_.train()
            try:
                train_x = self.model_.train_inputs[0]
                n = self.model_.train_targets.shape[-1]
                log_posterior = float(mll(self.model_(train_x), self.model_.train_targets)) * n
            finally:
                self.model_.train(was_training)
        return dict(
            backend="botorch",
            kernel=(f"{float(k.outputscale.detach()):.4g} * Matern(nu={self.nu}, "
                    f"lengthscale={np.round(ls, 4).tolist()}) "
                    f"+ White(noise={self._extra_noise:.4g})"),
            lengthscale=ls,
            outputscale=float(k.outputscale.detach()),
            noise=float(self._extra_noise),
            mean_constant=(0.0 if self.mean == "zero"
                           else float(self.model_.mean_module.constant.detach())),
            log_marginal_likelihood=log_posterior - log_prior,
            log_prior=log_prior,
            log_posterior=log_posterior,
        )

    # --- the pieces the acquisition code calls -------------------------------------------
    def with_fantasy(self, X_new, var_new):
        """A copy of this model conditioned on hypothetical observations at ``X_new``.

        Used by sequential-greedy batch selection, which needs the posterior as it would be
        after the earlier members of the batch had been measured. The hypothetical value is the
        current posterior mean at each new location, which is the kriging-believer heuristic.
        Hyperparameters are held at their fitted values rather than re-estimated, so a
        hypothetical observation can move the posterior but not the smoothness.

        Note that :class:`ConstrainedBatchSelector` does not need this: BoTorch's
        ``qLogNoisyExpectedImprovement`` has a genuine joint form over a batch of q points and
        integrates over the unknown outcomes by Monte Carlo instead of substituting a point
        guess for them. This method exists so that the existing
        ``select_batch_within_visit`` and ``select_batch_between_visit`` routines can be driven
        by this backend unchanged, which is necessary for a like-for-like comparison.
        """
        self._check()
        X_new = np.atleast_2d(np.asarray(X_new, float))
        var_new = np.broadcast_to(np.asarray(var_new, float), (X_new.shape[0],)).copy()
        y_new = np.atleast_1d(self.predict(X_new, return_std=False))
        X = np.vstack([self.X_, X_new])
        y = np.concatenate([self.y_, y_new])
        v = np.concatenate([self.y_var_, var_new])

        out = self._clone()
        out._y_loc, out._y_scale = self._y_loc, self._y_scale
        hp = self.hyperparameters
        out.fixed_hyperparameters = dict(
            lengthscale=hp["lengthscale"], outputscale=hp["outputscale"],
            noise=hp["noise"], constant=hp["mean_constant"])
        yz = (y - out._y_loc) / out._y_scale
        out.model_ = out._build(self.grid.transform(X), yz, v / out._y_scale ** 2, fit=False)
        out._extra_noise = self._extra_noise
        out.X_, out.y_, out.y_var_ = X, y, v
        return out

    def loo_predict(self, groups=None):
        """Leave-one-out or leave-one-group-out predictions, refitting on each fold.

        Refitting from scratch is slower than the analytic shortcut but it is the honest
        calculation: the shortcut leaves the held-out observation inside the hyperparameters,
        so the resulting calibration statistics are optimistic.
        """
        self._check()
        n = len(self.y_)
        groups = np.arange(n) if groups is None else np.asarray(groups)
        mu = np.full(n, np.nan)
        sd = np.full(n, np.nan)
        for g in np.unique(groups):
            te = groups == g
            tr = ~te
            if tr.sum() < 3:
                continue
            m = self._clone().fit(self.X_[tr], self.y_[tr], self.y_var_[tr])
            mu[te], sd[te] = m.predict(self.X_[te])
        return mu, sd

    # --- access for the acquisition layer -------------------------------------------------
    def botorch_model(self):
        """The underlying BoTorch model, on standardised outputs.

        Exposed because BoTorch's acquisition functions take a model rather than arrays. The
        caller must remember that this model's outputs are standardised J values, so a
        threshold expressed in objective units has to be standardised with
        :meth:`standardise` before it is handed to an acquisition function.
        """
        self._check()
        return self.model_

    def standardise(self, y):
        """Map values in objective units onto the standardised scale the model works on."""
        self._check()
        return (np.asarray(y, float) - self._y_loc) / self._y_scale


class TorchPreferenceGP:
    """Pairwise-probit preference Gaussian process, using BoTorch's ``PairwiseGP``.

    This replaces a hand-written Laplace approximation with the library implementation of the
    same model. Both are the preference-learning Gaussian process of Chu and Ghahramani, which
    is the model Louie et al. 2021 (doi:10.1186/s12984-021-00873-9) used for deep brain
    stimulation preferences, Zhao et al. 2021 (doi:10.1109/TNSRE.2021.3113636) used for spinal
    cord stimulation, and Dastin-van Rijn et al. 2021 (doi:10.3390/brainsci12010025) used for a
    central post-stroke pain case. For a judgement that setting a is preferred to setting b the
    likelihood is the normal cumulative distribution function of the scaled difference in
    latent value, and the posterior is approximated by a Gaussian centred at the mode.

    Higher latent value means more preferred. This is the opposite sign convention to the
    composite objective J, which is minimised, so any code that moves between the two must
    negate explicitly.

    Interface parity with :class:`StimOptimizer.routines.preference.PreferenceGP`:
    ``fit(X, comparisons)``, ``predict(X)``, ``best(X)``, ``prob_prefer(Xa, Xb)`` and
    ``holdout_accuracy(folds, random_state)``.

    Three substantive differences from the hand-written version
    -----------------------------------------------------------
    First, the comparison noise scale. The hand-written version fixes it at 1 and folds the
    remaining freedom into the kernel amplitude; BoTorch does the same thing by construction,
    setting it to 1 implicitly and letting the ``ScaleKernel`` outputscale carry the scale. The
    two are therefore the same model, and in both the latent values are identified only up to
    that amplitude, which is why preference output should be read as a ranking and not in
    clinical units.

    Second, the kernel hyperparameters are fitted here rather than supplied. The hand-written
    version holds the length scales fixed on the grounds that realistic numbers of comparisons
    cannot identify them, which is a real concern. The compromise taken here is to fit them
    under the same log-normal prior used for the objective model, so that a small number of
    comparisons leaves the estimate near the prior median instead of at whatever value the
    Laplace-approximated likelihood happens to prefer. Passing ``length_scale`` to
    :meth:`fit` restores the fixed-length-scale behaviour exactly, which is what the interface
    parity test uses.

    Third, :meth:`prob_prefer` uses the joint posterior covariance of the two settings rather
    than treating them as independent. Two nearby settings on the grid have strongly correlated
    latent values, and ignoring that correlation overstates the variance of their difference,
    which pushes the reported probability toward one half and makes the model look less able to
    separate the pair than it is. The correction matters most for exactly the close comparisons
    one would want to put to the patient.
    """

    def __init__(self, grid: ParameterGrid, *, nu=1.5, prior_loc=None,
                 prior_scale=_PRIOR_SCALE, min_lengthscale=_MIN_LENGTHSCALE,
                 jitter=1e-6, random_state=0):
        require_torch()
        self.grid = grid
        self.nu = float(nu)
        self.prior_loc = prior_loc
        self.prior_scale = float(prior_scale)
        self.min_lengthscale = float(min_lengthscale)
        self.jitter = float(jitter)
        self.random_state = int(random_state)
        self.model_ = None

    def fit(self, X, comparisons, *, length_scale=None):
        """Fit the latent value function from pairwise judgements.

        Parameters
        ----------
        X
            ``(n, 2)`` array of the distinct settings that were compared, in the original units
            of frequency in hertz and amplitude in milliamps.
        comparisons
            An iterable of ``(i, j)`` index pairs into ``X``, each meaning that setting i was
            preferred to setting j. Ties have no representation in this likelihood and must be
            dropped by the caller rather than encoded in either direction.
        length_scale
            If given, the length scales are set to these values and not fitted. If omitted they
            are fitted under the log-normal prior described in the class docstring.
        """
        X = np.atleast_2d(np.asarray(X, float))
        pairs = np.asarray(list(comparisons), int)
        if pairs.ndim != 2 or pairs.shape[1] != 2:
            raise ValueError("comparisons must be an iterable of (winner, loser) index pairs")
        if pairs.size == 0:
            raise ValueError("no comparisons supplied")
        if np.any(pairs[:, 0] == pairs[:, 1]):
            raise ValueError("a setting cannot be preferred to itself; drop ties before fitting")
        if pairs.max() >= X.shape[0] or pairs.min() < 0:
            raise IndexError("comparison indices out of range for X")

        Z = self.grid.transform(X)
        kernel = _matern_kernel(Z.shape[1], nu=self.nu, prior_loc=self.prior_loc,
                                prior_scale=self.prior_scale,
                                min_lengthscale=self.min_lengthscale)
        model = PairwiseGP(_t(Z), torch.as_tensor(pairs, dtype=torch.long),
                           covar_module=kernel, jitter=self.jitter)
        if length_scale is None:
            torch.manual_seed(self.random_state)
            fit_gpytorch_mll(
                PairwiseLaplaceMarginalLogLikelihood(model.likelihood, model))
        else:
            ls = np.atleast_1d(np.asarray(length_scale, float))
            if ls.size == 1:
                ls = np.repeat(ls, Z.shape[1])
            with torch.no_grad():
                model.covar_module.base_kernel.lengthscale = _t(ls)
                model.covar_module.outputscale = _t(1.0)
        model.eval()
        self.model_ = model
        self.X_, self.Z_, self.pairs_ = X, Z, pairs
        self.length_scale_ = length_scale
        return self

    def _check(self):
        if self.model_ is None:
            raise RuntimeError("TorchPreferenceGP is not fitted")

    def _posterior(self, Xq):
        self._check()
        with torch.no_grad():
            return self.model_.posterior(_t(self.grid.transform(Xq)))

    def predict(self, X=None):
        """Latent preference mean and standard deviation. A higher mean is more preferred."""
        Xq = self.grid.grid_X() if X is None else np.atleast_2d(np.asarray(X, float))
        post = self._posterior(Xq)
        mu = post.mean.squeeze(-1).detach().numpy()
        sd = post.variance.squeeze(-1).clamp_min(0.0).sqrt().detach().numpy()
        return mu, sd

    def best(self, X=None):
        """Index and location of the most-preferred cell, the maximum of the latent mean."""
        Xq = self.grid.grid_X() if X is None else np.atleast_2d(np.asarray(X, float))
        mu, _ = self.predict(Xq)
        i = int(np.argmax(mu))
        return i, Xq[i]

    def prob_prefer(self, Xa, Xb):
        """Posterior probability that each setting in ``Xa`` is preferred to its partner in ``Xb``.

        The probability integrates both the model's uncertainty about the latent values and the
        unit comparison noise of the probit likelihood, so a value near one half means the model
        genuinely cannot separate the two settings and the comparison is worth collecting from
        the patient. The variance of the latent difference is computed from the joint posterior
        covariance, which accounts for the correlation between two nearby settings.
        """
        Xa = np.atleast_2d(np.asarray(Xa, float))
        Xb = np.atleast_2d(np.asarray(Xb, float))
        if Xa.shape != Xb.shape:
            raise ValueError("Xa and Xb must have the same shape")
        k = Xa.shape[0]
        post = self._posterior(np.vstack([Xa, Xb]))
        mu = post.mean.squeeze(-1).detach().numpy()
        cov = post.distribution.covariance_matrix.detach().numpy()
        dm = mu[:k] - mu[k:]
        # Var(f_a - f_b) = Var(f_a) + Var(f_b) - 2 Cov(f_a, f_b), plus the probit comparison
        # noise. The two latent values enter the likelihood divided by sqrt(2), so the
        # comparison noise contributes a variance of 2 on this scale.
        ia, ib = np.arange(k), np.arange(k) + k
        dv = cov[ia, ia] + cov[ib, ib] - 2.0 * cov[ia, ib] + 2.0
        from scipy.stats import norm
        return norm.cdf(dm / np.sqrt(np.maximum(dv, 1e-12)))

    def holdout_accuracy(self, folds=5, random_state=0):
        """The fraction of held-out comparisons whose direction the model predicts correctly.

        Reported for the same reason Zhao et al. 2021 reported it: a preference model that
        cannot predict preferences it has not seen is not a therapeutic target. They obtained
        71.5 percent in internal cross-validation and 65.6 percent prospectively for spinal
        cord stimulation, both above the 50 percent chance level. Folds are taken over
        comparisons, not over settings, so every fold's training set still covers the whole set
        of compared settings; this measures whether the latent value function generalises across
        judgements, not across settings.

        The length scales are held at the full-data values across folds. Refitting them per fold
        would be stricter, but with the small numbers of comparisons this test is designed for
        it makes the fold-to-fold variation in the score larger than the signal being measured.
        This is a known optimism in the reported number and it should be quoted as such.
        """
        self._check()
        rng = np.random.default_rng(random_state)
        m = self.pairs_.shape[0]
        if m < folds * 2:
            raise ValueError(f"need at least {folds * 2} comparisons for {folds}-fold CV, have {m}")
        ls = self.model_.covar_module.base_kernel.lengthscale.detach().numpy().ravel()
        order = rng.permutation(m)
        correct = total = 0
        for k in range(folds):
            te = order[k::folds]
            tr = np.setdiff1d(order, te)
            fold = TorchPreferenceGP(
                self.grid, nu=self.nu, prior_loc=self.prior_loc,
                prior_scale=self.prior_scale, min_lengthscale=self.min_lengthscale,
                jitter=self.jitter, random_state=self.random_state
            ).fit(self.X_, self.pairs_[tr], length_scale=ls)
            mu, _ = fold.predict(self.X_)
            for i, j in self.pairs_[te]:
                correct += int(mu[i] > mu[j])
                total += 1
        return correct / total


# --- safety --------------------------------------------------------------------------------
#: Highest amplitude any setting may take, in milliamps. This is a clinician-declared ceiling
#: for this participant and not an estimate from data, so it is a hard bound and no model
#: output can raise it.
# Alias only; single source of truth is objective.AMP_HARD_LIMIT_MA (5.0 mA as of 2026-09-02).
CLINICIAN_AMP_CEILING = _OBJ.AMP_HARD_LIMIT_MA
#: Highest amplitude at which the coded acute record contains enough steps to support any
#: statement about tolerability. Above this the record holds 5 steps in total, which is too few
#: to distinguish tolerated from not tolerated, so the region is reported as unknown.
DATA_SUPPORTED_AMP_MAX = 4.0


class AmplitudeEnvelopeSafety:
    """A three-state safety classification over the grid: supported, unknown, or excluded.

    What this model does and does not claim
    ---------------------------------------
    It does not model side-effect severity as a function of amplitude, because the data for
    this participant do not support such a function. Among the 774 coded acute steps the
    severity distribution is 696 none, 28 mild, 23 moderate, 1 severe and 26 unknown, and
    within the 417 non-procedural steps with stimulation switched on the Spearman correlation
    between amplitude and severity rank is -0.013 with p = 0.79. The rate of moderate-or-worse
    events is 4.3 percent below 2 mA and 4.8 percent at or above 2 mA, and five of the moderate
    events occurred with the amplitude at 0.0 mA. Fitting a monotone increasing severity curve
    in amplitude, as the scikit-learn backend does through its polynomial prior mean, therefore
    asserts a relationship that the record contradicts over the range the record covers.

    What the record does support is much narrower and is what this class encodes. Certain
    settings were actually delivered to this participant and sustained, and a setting she ran
    for an extended period was, by the plain meaning of the word, tolerated. The set of
    delivered settings therefore defines an envelope of amplitude as a function of frequency
    within which stimulation is known to have been tolerable. Outside that envelope the record
    says nothing at all, and there are two quite different reasons why, which this class keeps
    separate:

    ``supported``
        At or below the delivered envelope for that frequency, and at or below
        :data:`DATA_SUPPORTED_AMP_MAX`. Direct evidence of tolerability exists.
    ``unknown``
        Above the envelope, or above :data:`DATA_SUPPORTED_AMP_MAX` where the record thins to
        5 steps, but still at or below :data:`CLINICIAN_AMP_CEILING`. No evidence either way.
        These cells are neither safe nor unsafe and the distinction is preserved in the output
        instead of being collapsed into one of the other two states.
    ``excluded``
        Above :data:`CLINICIAN_AMP_CEILING`. Ruled out by clinical declaration, not by data.

    Why the safe set is contiguous in amplitude by construction
    -----------------------------------------------------------
    The failure this replaces is worth stating plainly. In the scikit-learn backend the safe set
    is the region where an upper confidence bound on modelled severity stays below a threshold.
    Because the severity model is a Gaussian process seeded from a small number of pseudo
    observations, that region can be non-contiguous in amplitude: a cell at 2.6 mA may be inside
    it while a cell at 2.2 mA at the same frequency is outside, if the pseudo observations
    happen to fall that way. A clinician cannot use such a recommendation. Amplitude is ramped
    upward through intermediate values, so reaching 2.6 mA means passing through 2.2 mA, and a
    setting that can only be reached by crossing a band the model calls unsafe is not
    programmable.

    The classification here is a threshold on amplitude at each frequency, so at every frequency
    the supported set is an interval running from the lowest amplitude on the grid up to the
    envelope. Contiguity is a property of the construction and cannot fail for any input.
    :meth:`assert_contiguous` checks it anyway, as a guard against a future change breaking the
    property silently.

    Interface
    ---------
    ``safe_mask``, ``max_safe_amplitude`` and ``expansion_capped_mask`` keep the names and the
    meanings they have in :class:`StimOptimizer.routines.surrogate.SafetyGP`, so this class can
    be passed to the existing acquisition routines. ``classify`` and ``unknown_mask`` are new
    and expose the three-state distinction that the boolean mask necessarily loses. Note that
    ``safe_mask`` here ignores its ``beta`` argument, which is accepted only for signature
    compatibility: there is no fitted posterior to take a confidence bound on, so there is no
    conservatism knob. That is a real reduction in the information the model provides, and a
    caller that was tuning ``beta`` should read :meth:`classify` instead.
    """

    def __init__(self, grid: ParameterGrid, *, amp_ceiling=CLINICIAN_AMP_CEILING,
                 data_supported_amp_max=DATA_SUPPORTED_AMP_MAX,
                 envelope_margin=0.0, threshold=SE_THRESHOLD):
        # This class needs no torch and deliberately does not call require_torch(), so that the
        # safety reasoning remains available in a container without the PyTorch stack.
        self.grid = grid
        self.amp_ceiling = float(amp_ceiling)
        self.data_supported_amp_max = float(data_supported_amp_max)
        self.envelope_margin = float(envelope_margin)
        self.threshold = float(threshold)
        self.envelope_ = None

    def fit(self, delivered, severity=None, severity_var=None):
        """Build the envelope from the settings that were actually delivered.

        Parameters
        ----------
        delivered
            ``(n, 2)`` array of ``(freq_hz, amp_mA)`` pairs the participant actually received
            and sustained.
        severity, severity_var
            Accepted for signature compatibility with ``SafetyGP.fit`` and used only to check
            that no delivered setting carries a moderate-or-worse severity code. If any does,
            that setting is dropped from the envelope, because a setting that produced a
            moderate event is not evidence of tolerability. Passing ``None`` means no severity
            codes are available, and every delivered setting is then taken at face value.

        The envelope is the maximum delivered amplitude at each delivered frequency, extended
        across the grid's frequencies by linear interpolation on the base-2 logarithmic
        frequency axis. Interpolation, not extrapolation: outside the range of delivered
        frequencies the envelope is held flat at the nearest delivered frequency's value rather
        than continued along a trend. Extrapolating an envelope is how the polynomial prior mean
        in the scikit-learn backend came to bend the wrong way, and there is no reason to repeat
        it here.
        """
        D = np.atleast_2d(np.asarray(delivered, float))
        if D.size == 0:
            raise ValueError(
                "the amplitude envelope needs at least one delivered setting; with no delivered "
                "history there is no evidence of tolerability anywhere and every cell should be "
                "reported as unknown rather than as safe")
        if D.shape[1] != 2:
            raise ValueError("delivered must be (n, 2) columns (freq_hz, amp_mA)")
        keep = np.isfinite(D).all(axis=1)
        if severity is not None:
            s = np.asarray(severity, float).ravel()
            if s.size != D.shape[0]:
                raise ValueError("severity must have one entry per delivered setting")
            keep &= s < self.threshold
        D = D[keep]
        if D.shape[0] == 0:
            raise ValueError(
                "every delivered setting was dropped, either as non-finite or as carrying a "
                "moderate-or-worse severity code, so no envelope can be built")

        f_unique = np.unique(D[:, 0])
        amp_at_f = np.array([D[D[:, 0] == f, 1].max() for f in f_unique])
        lf = np.log2(f_unique)
        order = np.argsort(lf)
        self._env_lf, self._env_amp = lf[order], amp_at_f[order]
        self.delivered_ = D
        self.envelope_ = self.envelope(self.grid.freqs)
        return self

    def envelope(self, freq_hz):
        """The delivered-amplitude envelope at the given frequencies, in milliamps."""
        if self.envelope_ is None and not hasattr(self, "_env_lf"):
            raise RuntimeError("AmplitudeEnvelopeSafety is not fitted")
        lf = np.log2(np.asarray(freq_hz, float))
        e = np.interp(lf, self._env_lf, self._env_amp,
                      left=self._env_amp[0], right=self._env_amp[-1])
        return e + self.envelope_margin

    def _cells(self, X):
        X = self.grid.grid_X() if X is None else np.atleast_2d(np.asarray(X, float))
        return X

    def classify(self, X=None):
        """A string label per cell: ``"supported"``, ``"unknown"`` or ``"excluded"``.

        This is the output to report to a clinician, because it distinguishes a cell that is
        untested from a cell that is ruled out. The boolean :meth:`safe_mask` collapses those
        two into one and that collapse is exactly the ambiguity this class exists to remove.
        """
        X = self._cells(X)
        env = self.envelope(X[:, 0])
        amp = X[:, 1]
        out = np.full(X.shape[0], "unknown", dtype="<U9")
        out[(amp <= env + 1e-9) & (amp <= self.data_supported_amp_max + 1e-9)] = "supported"
        out[amp > self.amp_ceiling + 1e-9] = "excluded"
        return out

    def safe_mask(self, X=None, beta=2.0):
        """Cells with direct evidence of tolerability.

        ``beta`` is accepted and ignored; see the class docstring. Cells labelled ``unknown``
        are excluded from this mask, which is the conservative reading. Use
        :meth:`candidate_mask` when the intention is to allow deliberate exploration into the
        unknown region.
        """
        return self.classify(X) == "supported"

    def unknown_mask(self, X=None):
        """Cells with no evidence in either direction, below the clinician ceiling."""
        return self.classify(X) == "unknown"

    def excluded_mask(self, X=None):
        """Cells above the clinician-declared ceiling."""
        return self.classify(X) == "excluded"

    def candidate_mask(self, X=None, *, include_unknown=True, unknown_amp_step=None):
        """Cells eligible to be proposed, optionally including a controlled step into the unknown.

        With ``include_unknown=False`` this is :meth:`safe_mask`, and the optimiser can only
        ever re-propose settings inside the delivered envelope, which means it can never
        improve on what has already been tried. That is safe and useless.

        With ``include_unknown=True`` and ``unknown_amp_step`` set to a number of milliamps,
        unknown cells within that distance above the envelope become eligible. This is the same
        idea as the per-batch expansion cap of Sarikhani et al. 2022: the boundary of the
        explored region is allowed to move outward, but only by a bounded amount in one step,
        so that any error in the model's optimism is discovered at a small increment rather
        than a large one. Cells above the clinician ceiling are never eligible.
        """
        X = self._cells(X)
        lab = self.classify(X)
        m = lab == "supported"
        if include_unknown:
            allowed = lab == "unknown"
            if unknown_amp_step is not None:
                env = self.envelope(X[:, 0])
                ceil = np.minimum(env + float(unknown_amp_step), self.amp_ceiling)
                allowed &= X[:, 1] <= ceil + 1e-9
            m |= allowed
        return m

    def max_safe_amplitude(self, beta=2.0, mask=None):
        """The highest amplitude with direct evidence of tolerability, or NaN if there is none."""
        m = self.safe_mask() if mask is None else np.asarray(mask, bool)
        gx = self.grid.grid_X()
        return float(gx[m, 1].max()) if m.any() else float("nan")

    def expansion_capped_mask(self, worst_severity="none", prev_max_amp=None, beta=2.0,
                              caps=None):
        """The eligible set intersected with a per-batch cap on amplitude expansion.

        Keeps the signature and the caps of ``SafetyGP.expansion_capped_mask`` so that the
        existing pipeline can call either backend. The caps are keyed to the worst severity
        reported so far, following Sarikhani et al. 2022: the boundary may move 0.4 mA when
        nothing has been reported, 0.2 mA after a mild report, and not at all after a moderate
        or severe one.
        """
        caps = caps or {"none": 0.4, "mild": 0.2, "moderate": 0.0, "severe": 0.0}
        key = str(worst_severity).strip().lower()
        if key not in caps:
            raise ValueError(f"unknown severity {worst_severity!r}; expected {sorted(caps)}")
        step = caps[key]
        m = self.candidate_mask(include_unknown=step > 0, unknown_amp_step=step)
        if prev_max_amp is None:
            return m
        ceiling = min(float(prev_max_amp) + step, self.amp_ceiling)
        return m & (self.grid.grid_X()[:, 1] <= ceiling + 1e-9)

    def assert_contiguous(self, mask=None):
        """Check that the mask is a lower interval in amplitude at every frequency.

        Returns the list of frequencies that violate the property, which is empty for any mask
        this class produces. Kept as a live check rather than a comment so that a future change
        to the envelope logic cannot reintroduce the disconnected-island failure unnoticed.
        """
        m = self.safe_mask() if mask is None else np.asarray(mask, bool)
        surface = self.grid.as_surface(m.astype(float)) > 0.5
        bad = []
        for i, f in enumerate(self.grid.freqs):
            row = surface[i]
            if row.any():
                last_true = int(np.flatnonzero(row).max())
                if not row[: last_true + 1].all():
                    bad.append(float(f))
        return bad

    def report(self):
        """A dictionary summarising the classification, suitable for logging or a figure caption."""
        lab = self.classify()
        gx = self.grid.grid_X()
        sup = lab == "supported"
        return dict(
            n_cells=int(len(lab)),
            n_supported=int(sup.sum()),
            n_unknown=int((lab == "unknown").sum()),
            n_excluded=int((lab == "excluded").sum()),
            max_supported_amp_mA=(float(gx[sup, 1].max()) if sup.any() else float("nan")),
            amp_ceiling_mA=self.amp_ceiling,
            data_supported_amp_max_mA=self.data_supported_amp_max,
            envelope_mA_by_freq={float(f): float(e)
                                 for f, e in zip(self.grid.freqs, self.envelope(self.grid.freqs))},
            contiguity_violations=self.assert_contiguous(),
            basis=("delivered-amplitude envelope plus a clinician-declared ceiling; no fitted "
                   "severity-versus-amplitude relationship, because the coded record does not "
                   "support one over 0 to 4 mA"),
        )


class SeverityGP:
    """A Gaussian process over side-effect severity with a flat, fitted constant prior mean.

    Prefer :class:`StimOptimizer.routines.safety_ordinal.OrdinalSeverityGP` for any statement
    about safety that will be shown to a clinician
    -----------------------------------------------------------------------------------------
    This class fits a GAUSSIAN likelihood to what is in fact an ordered categorical outcome. It
    therefore asserts that the distance from "none" to "mild" equals the distance from
    "moderate" to "severe", it can predict severity values such as 1.4 or -0.3 which correspond
    to no clinical statement, and the standard deviation it reports describes a continuous
    quantity that does not exist. It is retained because BoTorch's outcome-constraint machinery
    in :class:`ConstrainedBatchSelector` needs a model whose posterior at a candidate point is
    Gaussian on the same scale as the constraint threshold, and because it is the closest
    like-for-like comparison against the scikit-learn ``SafetyGP`` it replaces.

    Its one genuine improvement over ``SafetyGP`` is that the prior mean is a fitted constant
    rather than a monotone increasing function of amplitude, which is described below. For the
    probability of a moderate-or-worse event, for credible intervals on that probability, and
    for the distinction between a region that is safe and a region that is merely unvisited, use
    the ordinal model instead.

    It exists so that the severity constraint can enter the acquisition function as a genuine
    outcome constraint. It
    differs from ``SafetyGP`` in one deliberate and important respect: the prior mean is a
    fitted constant rather than a monotone increasing function of amplitude. The reason is the
    finding recorded in :class:`AmplitudeEnvelopeSafety`: over the range the record covers,
    amplitude does not predict severity, so the constant is the shape the data support. If
    prospective data later show a rise in severity with amplitude, this model will fit it
    through the kernel, because a Gaussian process with a constant mean can represent an
    increasing function perfectly well; what it will not do is assume one in advance.

    A caveat that should be quoted whenever this model's output is used. It is fitted to the
    severity codes that exist, and 26 of the 774 coded acute steps have severity recorded as
    unknown. Those steps carry no information here and are simply absent from the fit, which
    means the model is conditioned on severity having been successfully coded. If coding failure
    is more likely when something went wrong, the model is optimistic by an amount that cannot
    be estimated from this data set.
    """

    def __init__(self, grid: ParameterGrid, *, threshold=SE_THRESHOLD, nu=1.5, prior_loc=None,
                 prior_scale=_PRIOR_SCALE, min_lengthscale=_MIN_LENGTHSCALE, random_state=0):
        require_torch()
        self.grid = grid
        self.threshold = float(threshold)
        self.nu = float(nu)
        self.prior_loc = prior_loc
        self.prior_scale = float(prior_scale)
        self.min_lengthscale = float(min_lengthscale)
        self.random_state = int(random_state)
        self.model_ = None

    def fit(self, X, severity, severity_var=None):
        """Fit to coded severity values on the ladder used by ``objective.SE_LADDER``."""
        X = np.atleast_2d(np.asarray(X, float))
        s = np.asarray(severity, float).ravel()
        if X.shape[0] != s.size:
            raise ValueError("X and severity must have matching length")
        if not np.all(np.isfinite(s)):
            raise ValueError(
                "non-finite severity passed to SeverityGP. The objective ladder maps moderate "
                "and severe to positive infinity for hard rejection; convert them to their "
                "finite rank on the severity scale before fitting this model.")
        v = np.full(s.shape, 0.25) if severity_var is None else np.asarray(severity_var, float).ravel()
        if np.any(v <= 0):
            raise ValueError("severity variances must be strictly positive")
        if s.size < 3:
            raise ValueError(f"need at least 3 observations, got {s.size}")

        Z = self.grid.transform(X)
        kernel = _matern_kernel(Z.shape[1], nu=self.nu, prior_loc=self.prior_loc,
                                prior_scale=self.prior_scale,
                                min_lengthscale=self.min_lengthscale)
        likelihood = FixedNoiseGaussianLikelihood(noise=_t(v), learn_additional_noise=True)
        model = SingleTaskGP(train_X=_t(Z), train_Y=_t(s).unsqueeze(-1),
                             likelihood=likelihood, covar_module=kernel,
                             mean_module=ConstantMean(), outcome_transform=None)
        torch.manual_seed(self.random_state)
        fit_gpytorch_mll(ExactMarginalLogLikelihood(model.likelihood, model))
        model.eval()
        self.model_ = model
        self.X_, self.s_, self.s_var_ = X, s, v
        return self

    def predict(self, X=None):
        """Posterior mean and standard deviation of severity, in severity-scale units."""
        if self.model_ is None:
            raise RuntimeError("SeverityGP is not fitted")
        Xq = self.grid.grid_X() if X is None else np.atleast_2d(np.asarray(X, float))
        with torch.no_grad():
            post = self.model_.posterior(_t(self.grid.transform(Xq)))
            return (post.mean.squeeze(-1).detach().numpy(),
                    post.variance.squeeze(-1).clamp_min(0.0).sqrt().detach().numpy())

    def botorch_model(self):
        if self.model_ is None:
            raise RuntimeError("SeverityGP is not fitted")
        return self.model_


# --- constrained batch acquisition ---------------------------------------------------------
class ConstrainedBatchSelector:
    """Batch selection by constrained q-point log noisy expected improvement.

    How this differs from the current masking approach, and what that fixes
    ----------------------------------------------------------------------
    The existing ``select_batch_within_visit`` computes single-point expected improvement over
    the whole grid, then restricts the argmax to a boolean safe mask, then repeats after
    substituting the posterior mean as a stand-in for the outcome at the cell just chosen. Two
    approximations are stacked there, and this class removes both.

    The first is the mask. A boolean mask is a hard partition into allowed and forbidden, so it
    throws away the model's uncertainty about the constraint. A cell whose severity is almost
    certainly acceptable and a cell that only just clears the threshold are treated identically
    if both fall inside the mask, and a cell that just misses it is treated the same as one that
    misses by a wide margin. BoTorch's outcome-constraint support instead weights the
    improvement at each cell by the posterior probability that the constraint holds there, using
    the same Monte Carlo samples that produce the improvement. A cell with a large expected
    improvement and a 70 percent chance of being tolerable is then correctly valued below a
    cell with a slightly smaller improvement and a 99 percent chance, whereas a mask at any
    threshold must either admit both at full value or reject one entirely. The practical
    consequence is that the recommended batch stops clustering on the boundary of the mask,
    which is where the masked acquisition tends to put it, because that is where the unmasked
    acquisition is largest.

    The second is the substitution of a point guess for each not-yet-observed outcome in the
    batch, the kriging-believer heuristic. The q-point form used here has a joint acquisition
    value over all q cells at once and integrates over their unknown outcomes by Monte Carlo,
    so a batch is evaluated as a batch. The logarithmic parameterisation, from Ament et al.
    2023 (arXiv:2310.20708), matters for a practical rather than a conceptual reason: plain
    expected improvement underflows to exactly zero across most of a grid once the model is
    reasonably confident, at which point the optimiser is choosing among ties, and the
    logarithmic form keeps the values distinguishable.

    Two kinds of constraint, kept separate on purpose
    -------------------------------------------------
    Not every restriction belongs in the acquisition function, and putting all of them there
    would be a mistake in the opposite direction. This class distinguishes:

    *Modelled outcomes* go into the acquisition function as constraints. Severity is such an
    outcome: it is measured with noise, the model has a posterior over it, and the probability
    that it clears the threshold is a meaningful quantity to weight by.

    *Declared bounds* go into the choice set instead. The 4.9 mA clinician ceiling is not a
    noisy measurement of anything and has no posterior; it is a bound, and a bound is enforced
    by removing the cells that violate it from the candidates. Softening it into a probabilistic
    weight would allow a sufficiently attractive predicted benefit to buy a small probability of
    exceeding a limit a clinician set, which is not a trade the optimiser is entitled to make.

    The amplitude envelope sits between the two and is treated as a declared bound, through
    ``AmplitudeEnvelopeSafety.candidate_mask`` with a bounded expansion step. That is a
    considered choice rather than an obvious one: the envelope is derived from data, so one
    could argue for modelling it. It is treated as a bound because what it encodes is the limit
    of where evidence exists, and the honest way to handle a region with no evidence is to
    decide deliberately how far outside it to step, not to let an extrapolated posterior decide.
    """

    def __init__(self, objective_gp: TorchObjectiveGP, *, severity_gp: SeverityGP | None = None,
                 safety: AmplitudeEnvelopeSafety | None = None, mc_samples=256,
                 random_state=0, eta=1e-3):
        require_torch()
        self.objective_gp = objective_gp
        self.severity_gp = severity_gp
        self.safety = safety
        self.mc_samples = int(mc_samples)
        self.random_state = int(random_state)
        self.eta = float(eta)

    def _model_and_objective(self):
        """The model handed to the acquisition function, and the sign convention.

        The objective model's outputs are standardised J values and J is minimised, so the
        acquisition function is given a linear objective with weight -1 on that output, turning
        the minimisation into the maximisation BoTorch expects. When a severity model is
        supplied the two are wrapped in a ``ModelListGP`` and the severity output receives
        weight 0, so it influences the acquisition only through the constraint.
        """
        obj = self.objective_gp.botorch_model()
        if self.severity_gp is None:
            return obj, LinearMCObjective(_t([-1.0])), None
        sev = self.severity_gp.botorch_model()
        thr = float(self.severity_gp.threshold)
        return (ModelListGP(obj, sev),
                LinearMCObjective(_t([-1.0, 0.0])),
                [lambda S, _thr=thr: S[..., 1] - _thr])

    def candidate_choices(self, *, include_unknown=True, unknown_amp_step=0.4,
                          exclude_idx=None, n_reports=None, min_reports_to_count=3):
        """The grid cells the optimiser may choose from, and their indices into the grid.

        ``exclude_idx`` and ``n_reports`` implement the same rank-and-select exclusion the
        existing ``candidate_mask`` performs: without it, the argmax of an acquisition function
        on a discrete grid keeps returning the best-sampled cell and the batch collapses onto
        the incumbent.
        """
        gx = self.objective_gp.grid.grid_X()
        m = np.ones(gx.shape[0], bool)
        if self.safety is not None:
            m &= self.safety.candidate_mask(include_unknown=include_unknown,
                                            unknown_amp_step=unknown_amp_step)
        if n_reports is not None:
            m &= np.asarray(n_reports, float) < float(min_reports_to_count)
        elif exclude_idx is not None:
            m[np.asarray(exclude_idx, int)] = False
        return gx[m], np.flatnonzero(m)

    def select_batch(self, *, q, include_unknown=True, unknown_amp_step=0.4,
                     exclude_idx=None, n_reports=None, min_reports_to_count=3):
        """Choose ``q`` grid cells jointly. Returns a list of dictionaries, one per cell.

        Each dictionary carries the frequency and amplitude, the index into the grid, the
        objective posterior mean and standard deviation at that cell, the safety label from
        :meth:`AmplitudeEnvelopeSafety.classify`, and, when a severity model was supplied, the
        posterior probability that severity there clears the threshold. The acquisition value is
        reported once for the batch as a whole, not per cell, because the q-point form has a
        single joint value and splitting it across members would be inventing a number.
        """
        q = int(q)
        if q < 1:
            raise ValueError("q must be at least 1")
        choices, idx = self.candidate_choices(
            include_unknown=include_unknown, unknown_amp_step=unknown_amp_step,
            exclude_idx=exclude_idx, n_reports=n_reports,
            min_reports_to_count=min_reports_to_count)
        if len(idx) == 0:
            raise ValueError(
                "no eligible candidates. The safety classification and the already-tested "
                "exclusion together leave nothing. Either allow a larger unknown_amp_step, "
                "permit re-testing, or accept that the search has exhausted the region the "
                "evidence and the clinician ceiling allow.")
        if len(idx) < q:
            raise ValueError(f"asked for q={q} cells but only {len(idx)} are eligible")

        model, mc_objective, constraints = self._model_and_objective()
        grid = self.objective_gp.grid
        Zc = _t(grid.transform(choices))
        Zb = _t(grid.transform(self.objective_gp.X_))
        acq = qLogNoisyExpectedImprovement(
            model=model, X_baseline=Zb, objective=mc_objective, constraints=constraints,
            eta=self.eta,
            sampler=SobolQMCNormalSampler(torch.Size([self.mc_samples]),
                                          seed=self.random_state),
            prune_baseline=True)
        with torch.no_grad():
            picked, value = optimize_acqf_discrete(acq, q=q, choices=Zc, unique=True)
        Zp = picked.detach().numpy()

        # optimize_acqf_discrete returns the chosen rows of `choices` in transformed
        # coordinates, so map them back to grid rows by nearest match in that same space
        # rather than by inverting the transform.
        pick_rows = [int(np.argmin(np.abs(grid.transform(choices) - z).sum(axis=1))) for z in Zp]
        X_sel = choices[pick_rows]
        mu, sd = self.objective_gp.predict(X_sel)
        labels = (self.safety.classify(X_sel) if self.safety is not None
                  else np.full(len(X_sel), "unclassified"))
        p_ok = None
        if self.severity_gp is not None:
            from scipy.stats import norm
            sm, ss = self.severity_gp.predict(X_sel)
            p_ok = norm.cdf((self.severity_gp.threshold - sm) / np.maximum(ss, 1e-12))
        batch_value = float(np.atleast_1d(value.detach().numpy()).sum())
        out = []
        for k in range(len(X_sel)):
            out.append(dict(
                index=int(idx[pick_rows[k]]),
                freq_hz=float(X_sel[k, 0]), amp_mA=float(X_sel[k, 1]),
                mu=float(mu[k]), sd=float(sd[k]),
                safety_label=str(labels[k]),
                p_severity_below_threshold=(None if p_ok is None else float(p_ok[k])),
                batch_log_acq_value=batch_value,
                constraint_handling=("outcome constraint inside the acquisition function"
                                     if constraints else "no modelled constraint"),
            ))
        return out


# --- equivalence between the two backends ---------------------------------------------------
def equivalence_report(grid: ParameterGrid, X, y, y_var, *, fixed_length_scale=(0.823, 0.72),
                       random_state=0):
    """Compare this backend against the scikit-learn backend on identical data.

    This is the evidence that the BoTorch backend is a valid substitute rather than a
    plausible-looking rewrite, and it is deliberately split into two comparisons that answer
    two different questions.

    ``matched``
        Both backends are given the same kernel hyperparameters, the same zero mean function and
        the same total noise on the diagonal, and neither fits anything. Any disagreement here
        is a disagreement about the linear algebra of the Gaussian-process posterior, which
        would mean one of the two implementations is wrong. The expected result is agreement to
        near machine precision.

        Getting this arm right required matching three conventions that are easy to get wrong.
        The scikit-learn backend standardises the objective with the population standard
        deviation, so this backend does the same rather than using BoTorch's ``Standardize``
        transform, which uses the sample standard deviation. The scikit-learn kernel contains a
        ``WhiteKernel``, whose variance appears on the diagonal at test points as well as
        training points, so its predictive standard deviation describes one noisy measurement;
        this backend adds the same term rather than returning the noise-free latent standard
        deviation. And the mean function is set to zero, because the scikit-learn backend has no
        mean function while this one defaults to a fitted constant.

    ``as_used``
        Each backend is fitted the way it would actually be used: the scikit-learn backend with
        its length scales pinned by hand, this backend with a prior on them. Disagreement here
        is expected and is the entire point of the exercise, because the two are answering the
        identifiability problem differently. The numbers say how much the choice moves the
        posterior, which is what a reader needs in order to decide whether to switch.

    Returns a dictionary with, for each arm, the maximum and root-mean-square differences in
    posterior mean and standard deviation over the whole grid, the correlation between the two
    surfaces, the location of the largest disagreement, and whether the two backends' best cells
    agree. Differences in the mean are in the original units of the objective J.
    """
    require_torch()
    from .surrogate import ObjectiveGP

    X = np.atleast_2d(np.asarray(X, float))
    y = np.asarray(y, float).ravel()
    y_var = np.asarray(y_var, float).ravel()
    gx = grid.grid_X()

    def compare(mu_a, sd_a, mu_b, sd_b):
        dmu, dsd = mu_a - mu_b, sd_a - sd_b
        j = int(np.argmax(np.abs(dmu)))
        return dict(
            max_abs_diff_mean=float(np.max(np.abs(dmu))),
            rms_diff_mean=float(np.sqrt(np.mean(dmu ** 2))),
            max_abs_diff_sd=float(np.max(np.abs(dsd))),
            rms_diff_sd=float(np.sqrt(np.mean(dsd ** 2))),
            correlation_mean=float(np.corrcoef(mu_a, mu_b)[0, 1]),
            correlation_sd=float(np.corrcoef(sd_a, sd_b)[0, 1]),
            worst_cell=dict(freq_hz=float(gx[j, 0]), amp_mA=float(gx[j, 1]),
                            sklearn_mean=float(mu_a[j]), botorch_mean=float(mu_b[j])),
            sklearn_range_mean=[float(mu_a.min()), float(mu_a.max())],
            botorch_range_mean=[float(mu_b.min()), float(mu_b.max())],
            sklearn_best_cell=dict(freq_hz=float(gx[np.argmin(mu_a), 0]),
                                   amp_mA=float(gx[np.argmin(mu_a), 1])),
            botorch_best_cell=dict(freq_hz=float(gx[np.argmin(mu_b), 0]),
                                   amp_mA=float(gx[np.argmin(mu_b), 1])),
            best_cell_agrees=bool(np.argmin(mu_a) == np.argmin(mu_b)),
        )

    # --- arm 1: matched hyperparameters ---------------------------------------------------
    ls = np.atleast_1d(np.asarray(fixed_length_scale, float))
    if ls.size == 1:
        ls = np.repeat(ls, X.shape[1])
    sk = ObjectiveGP(grid, fixed_length_scale=ls.tolist(), n_restarts=8,
                     random_state=random_state).fit(X, y, y_var)
    kern = sk.gp_.kernel_
    outputscale = float(kern.k1.k1.constant_value)
    noise = float(kern.k2.noise_level)
    fitted_ls = np.asarray(kern.k1.k2.length_scale, float).ravel()
    tg = TorchObjectiveGP(
        grid, mean="zero", random_state=random_state,
        fixed_hyperparameters=dict(lengthscale=fitted_ls, outputscale=outputscale,
                                   noise=noise)).fit(X, y, y_var)
    matched = compare(*sk.predict_grid(), *tg.predict_grid())
    matched["hyperparameters_used"] = dict(
        lengthscale=fitted_ls.tolist(), outputscale=outputscale, noise=noise,
        mean="zero", note="identical in both backends; nothing was fitted in this arm")

    # --- arm 2: each backend fitted as it would be used -----------------------------------
    sk2 = ObjectiveGP(grid, fixed_length_scale=ls.tolist(), n_restarts=8,
                      random_state=random_state).fit(X, y, y_var)
    tg2 = TorchObjectiveGP(grid, random_state=random_state).fit(X, y, y_var)
    as_used = compare(*sk2.predict_grid(), *tg2.predict_grid())
    as_used["sklearn_hyperparameters"] = sk2.hyperparameters
    as_used["botorch_hyperparameters"] = tg2.hyperparameters
    as_used["note"] = (
        "The scikit-learn arm has its length scales pinned by hand; the BoTorch arm fits them "
        "under a log-normal prior. Disagreement here reflects that difference in treatment of "
        "an unidentified hyperparameter and not a difference in the posterior calculation, "
        "which the matched arm isolates.")

    return dict(n_observations=int(len(y)), n_grid_cells=int(len(grid)),
                matched=matched, as_used=as_used)


def prior_scale_sweep(grid: ParameterGrid, X, y, y_var, *,
                      prior_scales=(math.sqrt(3.0), 1.0, 0.5, 0.35, 0.25),
                      fixed_length_scale=(0.823, 0.72), random_state=0):
    """How the fitted length scales and the posterior depend on the strength of the prior.

    This is the diagnostic that explains the ``as_used`` disagreement in
    :func:`equivalence_report`. That comparison shows the two backends' posterior means differing
    by up to about one unit of the objective, and the natural question is whether one of them is
    wrong. Neither is: the disagreement is entirely attributable to the length scales, and this
    function makes that visible by varying the one quantity that controls them.

    For each prior scale the BoTorch backend is refitted from scratch and its posterior over the
    whole grid is compared against the scikit-learn backend with its length scales pinned at
    ``fixed_length_scale``. Reading down the table, the fitted frequency length scale does not
    move smoothly: it stays near the value maximum likelihood would choose while the prior is
    broad, then jumps across to a value an order of magnitude larger once the prior is tight
    enough. That jump is the signature of two competing solutions rather than one poorly
    determined one, and it is why the prior scale cannot be treated as a nuisance setting.

    Returns a list of dictionaries, one per prior scale, each holding the fitted length scales,
    the largest and root-mean-square differences from the scikit-learn posterior, the correlation
    between the two mean surfaces, and whether the two backends still agree on the best cell.
    """
    require_torch()
    from .surrogate import ObjectiveGP

    ls = np.atleast_1d(np.asarray(fixed_length_scale, float))
    sk = ObjectiveGP(grid, fixed_length_scale=ls.tolist(), n_restarts=8,
                     random_state=random_state).fit(X, y, y_var)
    sk_mu, sk_sd = sk.predict_grid()
    out = []
    for ps in prior_scales:
        tg = TorchObjectiveGP(grid, prior_scale=float(ps), random_state=random_state)
        mu, sd = tg.fit(X, y, y_var).predict_grid()
        hp = tg.hyperparameters
        out.append(dict(
            prior_scale=float(ps),
            lengthscale=hp["lengthscale"],
            log_marginal_likelihood=hp["log_marginal_likelihood"],
            log_posterior=hp["log_posterior"],
            max_abs_diff_mean=float(np.max(np.abs(mu - sk_mu))),
            rms_diff_mean=float(np.sqrt(np.mean((mu - sk_mu) ** 2))),
            max_abs_diff_sd=float(np.max(np.abs(sd - sk_sd))),
            correlation_mean=float(np.corrcoef(mu, sk_mu)[0, 1]),
            best_cell_agrees=bool(np.argmin(mu) == np.argmin(sk_mu)),
        ))
    return dict(reference="sklearn ObjectiveGP with length scales pinned at "
                          f"{ls.tolist()}", sweep=out)


def profile_frequency_lengthscale(grid: ParameterGrid, X, y, y_var, *,
                                  values=None, prior_scale=math.sqrt(3.0), prior_loc=None,
                                  random_state=0):
    """Profile log likelihood and log posterior over the frequency length scale.

    At each candidate value the frequency length scale is pinned and every other hyperparameter
    (the amplitude length scale, the signal variance and the noise) is re-optimised by marginal
    likelihood, which is what makes this a profile rather than a slice. The log prior of the
    log-normal length-scale prior is then added to give the profile log posterior.

    This function uses the SCIKIT-LEARN backend to do the fitting, deliberately. The point of the
    diagnostic is to characterise the likelihood surface itself, and using the same optimiser
    that produced the fit under investigation would make it impossible to tell a property of the
    surface from a property of the optimiser. Requires no torch.

    Returns a dictionary with the profile itself and the interior local maxima of both curves. A
    length-scale problem with a single well-determined answer produces one local maximum; more
    than one means the data admit two different explanations and the prior is choosing between
    them rather than refining one.
    """
    from scipy.stats import lognorm

    from .surrogate import ObjectiveGP

    values = np.geomspace(0.05, 30.0, 40) if values is None else np.asarray(values, float)
    loc = dim_scaled_prior_loc(2) if prior_loc is None else float(prior_loc)
    rows = []
    for lf in values:
        g = ObjectiveGP(grid, fixed_length_scale=[float(lf), None], n_restarts=6,
                        random_state=random_state).fit(X, y, y_var)
        la = float(g.gp_.kernel_.k1.k2.length_scale[1])
        lml = float(g.gp_.log_marginal_likelihood_value_)
        lp = float(lognorm.logpdf(lf, s=prior_scale, scale=math.exp(loc))
                   + lognorm.logpdf(la, s=prior_scale, scale=math.exp(loc)))
        rows.append({"frequency_lengthscale": float(lf), "amplitude_lengthscale": la,
                     "log_marginal_likelihood": lml, "log_posterior": lml + lp})

    def _local_maxima(key):
        v = np.array([r[key] for r in rows])
        turn = np.diff(np.sign(np.diff(v))) < 0
        return [float(rows[i + 1]["frequency_lengthscale"]) for i in np.flatnonzero(turn)]

    return {
        "prior_scale": float(prior_scale), "prior_loc": loc, "profile": rows,
        "local_maxima_log_marginal_likelihood": _local_maxima("log_marginal_likelihood"),
        "local_maxima_log_posterior": _local_maxima("log_posterior"),
        "argmax_log_marginal_likelihood": float(
            max(rows, key=lambda r: r["log_marginal_likelihood"])["frequency_lengthscale"]),
        "argmax_log_posterior": float(
            max(rows, key=lambda r: r["log_posterior"])["frequency_lengthscale"]),
    }
