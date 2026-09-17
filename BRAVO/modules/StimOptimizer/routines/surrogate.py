"""Gaussian-process surrogates over the (frequency, amplitude) stimulation grid.

Two models, deliberately separate rather than one model with a penalty term:

``ObjectiveGP``
    posterior over the composite objective J (minimised).
``SafetyGP``
    posterior over side-effect severity, with a monotone-in-amplitude prior mean.

Both use a Matern-3/2 kernel with ARD length scales, fitted by marginal-likelihood
maximization. That is the kernel every clinically deployed implementation in this literature
chose (Sarikhani 2022 doi:10.1088/1741-2552/ac86a2; Cole 2024 doi:10.1088/1741-2552/ad6cf3;
Louie 2021 doi:10.1186/s12984-021-00873-9), and Matern-3/2 is the right smoothness assumption
for a response surface that is continuous but not analytic.

Implementation note. scikit-learn's ``GaussianProcessRegressor`` is used rather than a
torch-based stack (the optional PyTorch/BoTorch twin, ``surrogate_torch.py``, and its ordinal
safety model were deleted on 2026-09-12 as reached by nothing). The grid is 228 cells, so the acquisition function is evaluated
exhaustively and no gradient-based acquisition optimizer is needed — this is what Sarikhani
et al. did, and it makes the extra dependency pure cost inside a Django container.
Per-observation noise variance enters through ``alpha``, which is how the heteroscedastic
warm-start weighting of OBJECTIVE_SPEC section 3 is honoured.

y is standardised here rather than via ``normalize_y``, so that ``alpha`` is unambiguously in
the same (standardised) units as the values on the kernel diagonal.
"""
from __future__ import annotations

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, Matern, WhiteKernel

from .objective import SE_THRESHOLD


class ParameterGrid:
    """The discrete search space, plus the transform the GP sees.

    Frequency is modelled on a log2 axis (OBJECTIVE_SPEC section 1): DBS frequency effects are
    conventionally multiplicative, and one ARD length scale cannot serve 10 Hz and 165 Hz on a
    linear axis. Both axes are then standardised to unit scale so the ARD length-scale bounds
    mean the same thing on each.
    """

    def __init__(self, freqs, amps):
        self.freqs = np.asarray(sorted(set(np.asarray(freqs, float))), float)
        self.amps = np.asarray(sorted(set(np.asarray(amps, float))), float)
        if self.freqs.min() <= 0:
            raise ValueError("frequencies must be positive for a log2 axis")
        FF, AA = np.meshgrid(self.freqs, self.amps, indexing="ij")
        self.raw = np.column_stack([FF.ravel(), AA.ravel()])
        lf = np.log2(self.freqs)
        self._loc = np.array([lf.mean(), self.amps.mean()])
        self._scale = np.array([max(lf.std(), 1e-9), max(self.amps.std(), 1e-9)])

    def __len__(self):
        return self.raw.shape[0]

    @property
    def shape(self):
        return (len(self.freqs), len(self.amps))

    def transform(self, X):
        X = np.atleast_2d(np.asarray(X, float))
        if X.shape[1] != 2:
            raise ValueError("expected columns (freq_hz, amp_mA)")
        if np.any(X[:, 0] <= 0):
            raise ValueError("non-positive frequency cannot be placed on a log2 axis")
        Z = np.column_stack([np.log2(X[:, 0]), X[:, 1]])
        return (Z - self._loc) / self._scale

    def grid_X(self):
        return self.raw.copy()

    def as_surface(self, values):
        """Reshape a per-cell vector into (n_freq, n_amp) for plotting."""
        v = np.asarray(values, float)
        if v.size != len(self):
            raise ValueError(f"expected {len(self)} values, got {v.size}")
        return v.reshape(self.shape)

    def snap(self, X):
        """Snap arbitrary (freq, amp) pairs to their nearest grid cell."""
        X = np.atleast_2d(np.asarray(X, float))
        f = self.freqs[np.abs(X[:, [0]] - self.freqs).argmin(axis=1)]
        a = self.amps[np.abs(X[:, [1]] - self.amps).argmin(axis=1)]
        return np.column_stack([f, a])

    def index_of(self, X):
        """Row indices into ``grid_X()`` for the nearest grid cell of each input."""
        S = self.snap(X)
        fi = np.abs(S[:, [0]] - self.freqs).argmin(axis=1)
        ai = np.abs(S[:, [1]] - self.amps).argmin(axis=1)
        return fi * len(self.amps) + ai


class JointParameterGrid:
    """The discrete (rate, amplitude-Left, amplitude-Right) search space, plus the transform the
    GP sees, for a fit that models both stimulators AT ONCE (decision, 2026-09-14: "model the
    left and right sides together because they're always on").

    Both stimulation devices are reprogrammed concurrently on RCS08 -- there is one shared rate
    column in the settings history (``freq_hz``, never a per-side rate), and every exposure epoch
    carries both currents, so a fit that changes only one side's current while pretending the
    other side's current is not also acting on the same pain report is confounded by construction.
    This grid is the 3-D generalisation of :class:`ParameterGrid`: rate stays on the log2 axis for
    the same reason (OBJECTIVE_SPEC section 1), and both amplitude axes are left linear, since a
    joint dose-response has no reason to treat the two currents differently from each other. All
    three axes are standardised to unit scale so one set of ARD length-scale bounds means the same
    thing on every one of them.
    """

    def __init__(self, freqs, amps_left, amps_right):
        self.freqs = np.asarray(sorted(set(np.asarray(freqs, float))), float)
        self.amps_left = np.asarray(sorted(set(np.asarray(amps_left, float))), float)
        self.amps_right = np.asarray(sorted(set(np.asarray(amps_right, float))), float)
        if self.freqs.min() <= 0:
            raise ValueError("frequencies must be positive for a log2 axis")
        FF, AL, AR = np.meshgrid(self.freqs, self.amps_left, self.amps_right, indexing="ij")
        self.raw = np.column_stack([FF.ravel(), AL.ravel(), AR.ravel()])
        lf = np.log2(self.freqs)
        self._loc = np.array([lf.mean(), self.amps_left.mean(), self.amps_right.mean()])
        self._scale = np.array([max(lf.std(), 1e-9), max(self.amps_left.std(), 1e-9),
                                max(self.amps_right.std(), 1e-9)])

    def __len__(self):
        return self.raw.shape[0]

    @property
    def shape(self):
        return (len(self.freqs), len(self.amps_left), len(self.amps_right))

    def transform(self, X):
        X = np.atleast_2d(np.asarray(X, float))
        if X.shape[1] != 3:
            raise ValueError("expected columns (freq_hz, amp_mA_Left, amp_mA_Right)")
        if np.any(X[:, 0] <= 0):
            raise ValueError("non-positive frequency cannot be placed on a log2 axis")
        Z = np.column_stack([np.log2(X[:, 0]), X[:, 1], X[:, 2]])
        return (Z - self._loc) / self._scale

    def grid_X(self):
        return self.raw.copy()

    def as_surface(self, values):
        """Reshape a per-cell vector into (n_freq, n_amp_left, n_amp_right)."""
        v = np.asarray(values, float)
        if v.size != len(self):
            raise ValueError(f"expected {len(self)} values, got {v.size}")
        return v.reshape(self.shape)

    def snap(self, X):
        """Snap arbitrary (freq, amp_left, amp_right) triples to their nearest grid cell."""
        X = np.atleast_2d(np.asarray(X, float))
        f = self.freqs[np.abs(X[:, [0]] - self.freqs).argmin(axis=1)]
        al = self.amps_left[np.abs(X[:, [1]] - self.amps_left).argmin(axis=1)]
        ar = self.amps_right[np.abs(X[:, [2]] - self.amps_right).argmin(axis=1)]
        return np.column_stack([f, al, ar])

    def index_of(self, X):
        """Row indices into ``grid_X()`` for the nearest grid cell of each input."""
        S = self.snap(X)
        fi = np.abs(S[:, [0]] - self.freqs).argmin(axis=1)
        ali = np.abs(S[:, [1]] - self.amps_left).argmin(axis=1)
        ari = np.abs(S[:, [2]] - self.amps_right).argmin(axis=1)
        return (fi * len(self.amps_left) + ali) * len(self.amps_right) + ari


#: The shortest time length scale the model may fit, in months (decision 194). "Drift" means the
#: rating changing over a month or more; variation faster than that between epochs is noise, and
#: must stay with the settings axes and the nugget. Without this floor the marginal likelihood
#: can drive the time scale down to the spacing between epochs, at which point time explains
#: every observation on its own, the settings surface goes flat and the best cell is arbitrary
#: (measured on the adaptive-envelope test fixture: a time scale of 0.35 months, the "best" cell
#: at a rate that stratum never delivered).
TIME_LENGTH_SCALE_FLOOR_MONTHS = 1.0


class TimeAwareGrid:
    """A search grid with TIME as one more model input (decision 194, 2026-09-17).

    Wraps a :class:`JointParameterGrid` (or :class:`ParameterGrid`). The GP sees the base grid's
    standardised settings axes plus one standardised time axis, in months since the record began,
    with its own fitted ARD length scale -- so a rating that drifts over the year is explained by
    time rather than smeared over the settings, and a short fitted time scale says the record is
    non-stationary. The search grid itself (``grid_X``) carries NO time column: a prediction on it
    is a prediction AT THE PRESENT (``t_now_months``, the end of the newest epoch), which is what
    the current map draws. An input row given without a time column is likewise taken to be
    "now"; a row with one is taken at that time, which is how the hold-out check asks the model
    about the past.
    """

    def __init__(self, base, *, t_obs_months, t_now_months,
                 min_length_scale_months=TIME_LENGTH_SCALE_FLOOR_MONTHS):
        self.base = base
        self.n_base = base.grid_X().shape[1]
        self.min_length_scale_months = float(min_length_scale_months)
        t = np.asarray(t_obs_months, float)
        self.t_obs_months = t
        self.t_loc = float(np.nanmean(t)) if t.size else 0.0
        self.t_scale = float(max(np.nanstd(t), 1e-9)) if t.size else 1.0
        self.t_now = float(t_now_months)

    # ---- the base grid's own surface, untouched ----
    def __len__(self): return len(self.base)
    @property
    def shape(self): return self.base.shape
    def __getattr__(self, name):
        # `freqs`, `amps_left`, `amps_right`, `raw`, ... belong to the base grid. Guarded so an
        # instance being unpickled (no `base` yet) does not recurse.
        if name == "base" or "base" not in self.__dict__:
            raise AttributeError(name)
        return getattr(self.base, name)
    def grid_X(self): return self.base.grid_X()
    def as_surface(self, values): return self.base.as_surface(values)
    def snap(self, X): return self.base.snap(self._settings(X))
    def index_of(self, X): return self.base.index_of(self._settings(X))

    def _settings(self, X):
        X = np.atleast_2d(np.asarray(X, float))
        return X[:, :self.n_base]

    def with_time(self, X):
        """``X`` with a time column: the given one, or ``t_now`` where none was given."""
        X = np.atleast_2d(np.asarray(X, float))
        if X.shape[1] == self.n_base:
            return np.column_stack([X, np.full(X.shape[0], self.t_now)])
        if X.shape[1] == self.n_base + 1:
            return X
        raise ValueError(f"expected {self.n_base} settings columns, optionally followed by one "
                         f"time column (months); got {X.shape[1]} columns")

    def transform(self, X):
        X = self.with_time(X)
        Z = self.base.transform(X[:, :self.n_base])
        return np.column_stack([Z, (X[:, -1] - self.t_loc) / self.t_scale])

    def time_length_scale_months(self, standardised_length_scale):
        """A fitted length scale on the standardised time axis, back in months."""
        return float(standardised_length_scale) * self.t_scale

    def time_length_scale_bounds(self, upper_standardised):
        """The time axis's length-scale box on the standardised axis: the floor in months,
        standardised, up to the same upper bound the settings axes use (never below it)."""
        lo = self.min_length_scale_months / self.t_scale
        return (lo, max(float(upper_standardised), lo * 1.001))


def _make_kernel(n_dim, length_scale_bounds, nugget_bounds, fixed_length_scale=None,
                 bounds_by_dim=None):
    """Matern-3/2 ARD kernel plus a white nugget.

    ``fixed_length_scale`` pins the length scales instead of fitting them. This exists because
    of a measured degeneracy in the RCS08 warm start: the marginal likelihood is essentially
    flat in the FREQUENCY length scale (lml -48.14 at 0.02 versus -48.21 at 0.15 on the
    standardised log2 axis), so maximum likelihood drives it to zero and the surrogate treats
    every frequency as an independent block with no borrowing at all. That is a statement about
    the historical design — frequency levels are separated in time, so between-frequency
    contrasts absorb the temporal trend — not about the underlying physiology. When the data
    cannot determine a hyperparameter, pinning it to a stated scientific assumption is more
    honest than accepting the degenerate MLE. See OBJECTIVE_SPEC amendment 2026-08-29.

    Pinning is PER DIMENSION. Pass ``None`` in a slot to leave that dimension free, e.g.
    ``fixed_length_scale=[0.823, None]`` pins frequency and fits amplitude. A dimension is pinned
    by collapsing its bounds to a point rather than by marking the whole kernel fixed, so the
    remaining dimensions, the signal variance and the nugget are still fitted by marginal
    likelihood. Passing a scalar or a fully-specified sequence pins every dimension, which also
    means leave-one-out refits inherit the full-data hyperparameters instead of re-estimating
    them — see :meth:`ObjectiveGP.loo_predict`.
    """
    # ``bounds_by_dim``: an optional per-dimension override of ``length_scale_bounds`` (a list
    # with a (lo, hi) or None per dimension) -- the time axis's floor (TimeAwareGrid) uses it.
    per_dim = list(bounds_by_dim) if bounds_by_dim is not None else [None] * n_dim
    if fixed_length_scale is None and any(b is not None for b in per_dim):
        fixed_length_scale = [None] * n_dim
    if fixed_length_scale is not None:
        spec = np.atleast_1d(np.asarray(fixed_length_scale, dtype=object))
        if spec.size == 1:
            spec = np.repeat(spec, n_dim)
        if spec.size != n_dim:
            raise ValueError(f"fixed_length_scale must have {n_dim} entries or be scalar")
        ls, bounds = [], []
        for k, v in enumerate(spec):
            if v is None:
                b = tuple(per_dim[k]) if per_dim[k] is not None else tuple(length_scale_bounds)
                ls.append(float(np.clip(1.0, b[0], b[1])))
                bounds.append(b)
            else:
                val = float(v)
                ls.append(val)
                # Pin with a hairline-width box rather than exact point bounds: sklearn
                # log-transforms the bounds and hands them to lbfgs, and a zero-width box makes
                # the optimizer return ABNORMAL with nan hyperparameters. 1e-6 relative width is
                # pinned for every practical purpose.
                bounds.append((val * (1.0 - 1e-6), val * (1.0 + 1e-6)))
        matern = Matern(length_scale=np.asarray(ls, float), length_scale_bounds=bounds, nu=1.5)
    else:
        matern = Matern(length_scale=np.ones(n_dim), length_scale_bounds=length_scale_bounds,
                        nu=1.5)
    return (ConstantKernel(1.0, (1e-3, 1e3)) * matern
            + WhiteKernel(noise_level=1e-2, noise_level_bounds=nugget_bounds))


class ObjectiveGP:
    """Fixed-noise GP over the composite objective. Lower J is better."""

    def __init__(self, grid: ParameterGrid, *, length_scale_bounds=(0.15, 20.0),
                 nugget_bounds=(1e-6, 1.0), n_restarts=12, random_state=0,
                 fixed_length_scale=None):
        self.grid = grid
        self.length_scale_bounds = length_scale_bounds
        self.nugget_bounds = nugget_bounds
        self.n_restarts = n_restarts
        self.random_state = random_state
        self.fixed_length_scale = fixed_length_scale
        self.gp_ = None

    def _clone(self):
        return ObjectiveGP(self.grid, length_scale_bounds=self.length_scale_bounds,
                           nugget_bounds=self.nugget_bounds, n_restarts=self.n_restarts,
                           random_state=self.random_state,
                           fixed_length_scale=self.fixed_length_scale)

    def fit(self, X, y, y_var):
        X = np.atleast_2d(np.asarray(X, float))
        y = np.asarray(y, float).ravel()
        y_var = np.asarray(y_var, float).ravel()
        if not (len(y) == len(y_var) == X.shape[0]):
            raise ValueError("X, y and y_var must have matching length")
        if np.any(y_var <= 0):
            raise ValueError("observation variances must be strictly positive")
        if not np.all(np.isfinite(y)):
            raise ValueError(
                "non-finite J passed to ObjectiveGP: these are hard-infeasible cells "
                "(moderate/severe side effect). Filter on the `feasible` flag from "
                "build_objective before fitting; they inform the SafetyGP, not this one.")
        if len(y) < 3:
            raise ValueError(f"need at least 3 observations to fit hyperparameters, got {len(y)}")

        if isinstance(self.grid, TimeAwareGrid):
            X = self.grid.with_time(X)
        Z = self.grid.transform(X)
        pins = self.fixed_length_scale
        bounds_by_dim = None
        if isinstance(self.grid, TimeAwareGrid):
            if pins is not None and np.size(pins) == Z.shape[1] - 1:
                pins = list(pins) + [None]          # the time axis is always fitted
            bounds_by_dim = [None] * (Z.shape[1] - 1) + [
                self.grid.time_length_scale_bounds(self.length_scale_bounds[1])]

        self._y_loc = float(y.mean())
        self._y_scale = float(max(y.std(ddof=0), 1e-9))
        yz = (y - self._y_loc) / self._y_scale
        alpha = y_var / self._y_scale ** 2  # same units as the standardised kernel diagonal

        self.gp_ = GaussianProcessRegressor(
            kernel=_make_kernel(Z.shape[1], self.length_scale_bounds, self.nugget_bounds, pins,
                                bounds_by_dim=bounds_by_dim),
            alpha=alpha, normalize_y=False,
            n_restarts_optimizer=self.n_restarts, random_state=self.random_state,
        ).fit(Z, yz)
        self.X_, self.y_, self.y_var_ = X, y, y_var
        return self

    @property
    def time_length_scale_months(self):
        """The fitted time length scale in months, or None when the grid has no time axis."""
        self._check()
        if not isinstance(self.grid, TimeAwareGrid):
            return None
        for k in (self.gp_.kernel_.k1, getattr(self.gp_.kernel_.k1, "k2", None)):
            ls = getattr(k, "length_scale", None)
            if ls is not None and np.size(ls) == self.grid.n_base + 1:
                return self.grid.time_length_scale_months(np.asarray(ls, float)[-1])
        return None

    def _check(self):
        if self.gp_ is None:
            raise RuntimeError("ObjectiveGP is not fitted")

    def predict(self, X, return_std=True):
        """Posterior mean (and SD) in the original J units."""
        self._check()
        out = self.gp_.predict(self.grid.transform(X), return_std=return_std)
        if not return_std:
            return out * self._y_scale + self._y_loc
        mu, sd = out
        return mu * self._y_scale + self._y_loc, sd * self._y_scale

    def predict_grid(self):
        return self.predict(self.grid.grid_X())

    @property
    def hyperparameters(self):
        self._check()
        k = self.gp_.kernel_
        return dict(kernel=str(k), log_marginal_likelihood=float(
            self.gp_.log_marginal_likelihood_value_))

    def with_fantasy(self, X_new, var_new):
        """Copy of this GP conditioned on hypothetical observations at ``X_new``.

        Sequential-greedy batch selection needs the posterior *after* the previously chosen
        batch members have been evaluated, before any of them actually has been. The fantasy
        value used is the current posterior mean at each new point (the kriging-believer
        heuristic), which is the standard choice when the acquisition has no closed-form batch
        form. Kernel hyperparameters are frozen at their fitted values rather than re-estimated,
        so the fantasy cannot move the length scales — only the posterior.
        """
        self._check()
        X_new = np.atleast_2d(np.asarray(X_new, float))
        if isinstance(self.grid, TimeAwareGrid):
            X_new = self.grid.with_time(X_new)
        var_new = np.broadcast_to(np.asarray(var_new, float), (X_new.shape[0],)).copy()
        y_new = self.predict(X_new, return_std=False)
        X = np.vstack([self.X_, X_new])
        y = np.concatenate([self.y_, np.atleast_1d(y_new)])
        v = np.concatenate([self.y_var_, var_new])

        out = self._clone()
        out._y_loc, out._y_scale = self._y_loc, self._y_scale
        yz = (y - out._y_loc) / out._y_scale
        out.gp_ = GaussianProcessRegressor(
            kernel=self.gp_.kernel_, optimizer=None, normalize_y=False,
            alpha=v / out._y_scale ** 2, random_state=self.random_state,
        ).fit(self.grid.transform(X), yz)
        out.X_, out.y_, out.y_var_ = X, y, v
        return out

    def loo_predict(self, groups=None):
        """Leave-one-out (or leave-one-group-out) predictions for calibration checking.

        Refits from scratch on each fold, so hyperparameters are re-estimated on the training
        fold only. That is slower than the analytic LOO shortcut but it is the honest thing to
        report: the shortcut leaks the held-out point into the hyperparameters.
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


class _MonotoneMean:
    """Non-decreasing prior mean in amplitude, guaranteed by construction.

    Wraps a polynomial with a running-maximum envelope evaluated on a fine amplitude lattice:
    ``m(a) = max over a' <= a of poly(a')``. This is a projection onto the monotone cone and it
    makes the guarantee unconditional, including outside the range where the polynomial was
    fitted. The envelope matters because the prior mean is evaluated over the whole search grid
    while the fit only ever sees the amplitudes that were actually programmed; a degree-2 fit
    whose vertex falls just below the observed minimum decreases on the extrapolated left tail,
    which would have the safety model predicting *lower* severity at *higher* amplitude — the
    exact failure the monotone mean exists to prevent.
    """

    def __init__(self, poly, lo, hi, n=1024):
        self.poly = poly
        self._a = np.linspace(float(lo), float(hi), int(n))
        self._m = np.maximum.accumulate(poly(self._a))

    def __call__(self, a):
        return np.interp(np.asarray(a, float), self._a, self._m,
                         left=self._m[0], right=self._m[-1])


def _monotone_poly2(a, s, check_range=None):
    """Degree-2 least-squares fit in amplitude, demoted if it is not non-decreasing.

    Side-effect severity is monotone increasing in amplitude, so the usual zero-mean GP prior is
    simply the wrong shape — Sarikhani et al. fit a second-degree polynomial and used it as the
    prior mean. Here the fit is checked for monotonicity over ``check_range``, which must be the
    range the mean will be *evaluated* on (the search grid), not the range it was fitted on, and
    demoted to linear then constant if it fails. The returned callable additionally carries the
    running-maximum envelope, so monotonicity holds whatever the polynomial does.
    """
    a = np.asarray(a, float).ravel()
    s = np.asarray(s, float).ravel()
    lo, hi = check_range if check_range is not None else (a.min(), a.max())
    lo, hi = float(min(lo, a.min())), float(max(hi, a.max()))
    if len(np.unique(a)) >= 3:
        c = np.polyfit(a, s, 2)                      # c[0]a^2 + c[1]a + c[2]
        deriv = np.polyval([2 * c[0], c[1]], np.linspace(lo, hi, 256))
        if np.all(deriv >= -1e-9):
            return _MonotoneMean(np.poly1d(c), lo, hi), 2
    if len(np.unique(a)) >= 2:
        c = np.polyfit(a, s, 1)
        if c[0] >= 0:
            return _MonotoneMean(np.poly1d(c), lo, hi), 1
    return _MonotoneMean(np.poly1d([float(np.mean(s))]), lo, hi), 0


class SafetyGP:
    """GP over side-effect severity with a monotone-in-amplitude polynomial prior mean.

    The safe set is the region whose *upper* confidence bound stays below the severity
    threshold, ``mu + beta*sigma < threshold``. ``beta`` is the single exposed conservatism
    knob: Cole et al. 2024 swept 30 configuration combinations and found it the only parameter
    that significantly predicted unsafe overshoot.
    """

    def __init__(self, grid: ParameterGrid, *, threshold=SE_THRESHOLD,
                 length_scale_bounds=(0.15, 200.0), nugget_bounds=(1e-6, 2.0),
                 n_restarts=12, random_state=0):
        # Upper bound is deliberately loose: the monotone polynomial prior mean absorbs most of
        # the amplitude structure, so the residual GP legitimately wants a very long length
        # scale. Clipping it at 20 produced a spurious convergence warning on every fit.
        self.grid = grid
        self.threshold = float(threshold)
        self.length_scale_bounds = length_scale_bounds
        self.nugget_bounds = nugget_bounds
        self.n_restarts = n_restarts
        self.random_state = random_state
        self.gp_ = None
        self.prior_degree_ = None

    @staticmethod
    def seed_from_history(delivered, limits, *, tolerated_severity=0.0,
                          limit_severity=SE_THRESHOLD, var_tolerated=0.5, var_limit=1.5):
        """Two-anchor safety seed from the historical record.

        Phase 1 established that the PRO battery carries no structured side-effect severity
        field, so the safety model cannot be warm-started from reports. The history contains two
        indirect signals instead, and BOTH anchors are needed:

        ``delivered``
            ``(freq_hz, amp_mA)`` pairs the patient actually sustained. A setting she ran for
            weeks was tolerated, which is evidence that severity there is *below* threshold.
            Encoded at ``tolerated_severity`` (default 0 = none).
        ``limits``
            ``(freq_hz, amp_mA)`` pairs from the programmed ``UpperLimitInMilliAmps``. A
            clinician judged that amplitude the edge of acceptable, so severity there is *at*
            threshold.

        Seeding from the limits alone is the trap: every pseudo-observation then sits exactly at
        the threshold, so ``mu + beta*sigma >= threshold`` everywhere and the safe set is empty
        for any ``beta > 0``. The tolerated anchors are what give the monotone prior mean a ramp
        to fit and leave headroom below the limit.

        Both anchors carry deliberately large variances because the inference is indirect. Never
        mix these with real severity reports without keeping an ``se_observed`` flag alongside,
        and drop the seeds once prospective reports exist.

        Returns ``(X, severity, severity_var)`` ready for :meth:`fit`.
        """
        Xd = np.atleast_2d(np.asarray(delivered, float))
        Xl = np.atleast_2d(np.asarray(limits, float))
        for name, A in (("delivered", Xd), ("limits", Xl)):
            if A.size and A.shape[1] != 2:
                raise ValueError(f"{name} must be (n, 2) columns (freq_hz, amp_mA)")
        Xd = Xd[np.isfinite(Xd).all(axis=1)] if Xd.size else Xd.reshape(0, 2)
        Xl = Xl[np.isfinite(Xl).all(axis=1)] if Xl.size else Xl.reshape(0, 2)
        if Xd.shape[0] == 0 or Xl.shape[0] == 0:
            raise ValueError(
                "need at least one tolerated anchor AND one limit anchor; seeding from limits "
                "alone yields an empty safe set for any beta > 0")
        X = np.vstack([Xd, Xl])
        s = np.concatenate([np.full(Xd.shape[0], float(tolerated_severity)),
                            np.full(Xl.shape[0], float(limit_severity))])
        v = np.concatenate([np.full(Xd.shape[0], float(var_tolerated)),
                            np.full(Xl.shape[0], float(var_limit))])
        return X, s, v

    def fit(self, X, severity, severity_var=None):
        X = np.atleast_2d(np.asarray(X, float))
        s = np.asarray(severity, float).ravel()
        if X.shape[0] != s.size:
            raise ValueError("X and severity must have matching length")
        v = np.full(s.shape, 0.25) if severity_var is None else np.asarray(severity_var, float).ravel()
        if np.any(v <= 0):
            raise ValueError("severity variances must be strictly positive")

        self.prior_, self.prior_degree_ = _monotone_poly2(X[:, 1], s)
        resid = s - self.prior_(X[:, 1])
        self._r_scale = float(max(resid.std(ddof=0), 1e-9))

        self.gp_ = GaussianProcessRegressor(
            kernel=_make_kernel(X.shape[1], self.length_scale_bounds, self.nugget_bounds),
            alpha=v / self._r_scale ** 2, normalize_y=False,
            n_restarts_optimizer=self.n_restarts, random_state=self.random_state,
        ).fit(self.grid.transform(X), resid / self._r_scale)
        self.X_, self.s_, self.s_var_ = X, s, v
        return self

    def predict(self, X):
        if self.gp_ is None:
            raise RuntimeError("SafetyGP is not fitted")
        X = np.atleast_2d(np.asarray(X, float))
        mu_r, sd_r = self.gp_.predict(self.grid.transform(X), return_std=True)
        return self.prior_(X[:, 1]) + mu_r * self._r_scale, sd_r * self._r_scale

    def safe_mask(self, X=None, beta=2.0):
        """Boolean mask of cells whose severity upper confidence bound clears the threshold.

        An all-False mask is a legitimate result (nothing is provably safe yet) but it is also
        the signature of a degenerate seed, so callers should check ``.any()`` rather than
        reducing over the masked amplitudes directly. See :meth:`seed_from_history`.
        """
        X = self.grid.grid_X() if X is None else X
        mu, sd = self.predict(X)
        return (mu + float(beta) * sd) < self.threshold

    def max_safe_amplitude(self, beta=2.0, mask=None):
        """Highest amplitude in the safe set, or NaN when the safe set is empty."""
        m = self.safe_mask(beta=beta) if mask is None else np.asarray(mask, bool)
        return float(self.grid.grid_X()[m, 1].max()) if m.any() else float("nan")

    def expansion_capped_mask(self, worst_severity="none", prev_max_amp=None, beta=2.0,
                              caps=None):
        """Safe mask intersected with the per-batch amplitude-expansion cap.

        The confidence-bound safe-set formulation with an unbounded Lipschitz constant expands
        aggressively, so Sarikhani et al. added a hard cap on how far the boundary may move in
        one step, keyed to the worst severity reported so far. Two independent brakes.
        """
        caps = caps or {"none": 0.4, "mild": 0.2, "mild_persistent": 0.1, "moderate": 0.0, "severe": 0.0}
        key = str(worst_severity).strip().lower().replace(" ", "_").replace("-", "_")
        if key not in caps:
            raise ValueError(f"unknown severity {worst_severity!r}; expected {sorted(caps)}")
        mask = self.safe_mask(beta=beta)
        if prev_max_amp is None:
            return mask
        ceiling = float(prev_max_amp) + caps[key]
        return mask & (self.grid.grid_X()[:, 1] <= ceiling)
