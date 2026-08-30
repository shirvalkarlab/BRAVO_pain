"""Preference Gaussian process over forced binary comparisons of stimulation settings.

This is the second, independent model required by OBJECTIVE_SPEC section 6: it is fitted from
the patient's A-versus-B judgements alone and never averaged into the composite objective. The
two are reported side by side because they are known to disagree — Louie et al. 2021
(doi:10.1186/s12984-021-00873-9) found the objective optimizer driving frequency to the highest
tolerable value while the preference model peaked at 70-110 Hz, the lowest frequency still
giving near-maximal benefit.

Model. Binary-probit preference likelihood with a GP prior on the latent value function
(Chu & Ghahramani's preference-learning GP), the formulation Louie et al. used for the probit
GP, Zhao et al. 2021 (doi:10.1109/TNSRE.2021.3113636) used for spinal cord stimulation, and
Dastin-van Rijn et al. 2021 (doi:10.3390/brainsci12010025) used for the central post-stroke
pain case. For a comparison ``a > b``:

    P(a > b | f) = Phi( (f(a) - f(b)) / (sqrt(2) * sigma) )

with ``sigma`` FIXED at 1.0 and not learned, following Louie et al. The latent scale is
therefore only identified up to the kernel amplitude, which is why preference values are
reported as a ranking and a normalised surface rather than in clinical units.

Higher latent value means *more preferred*. Note this is the opposite sign convention to the
composite objective J, which is minimised; :meth:`PreferenceGP.best` returns the argmax and
callers converting between the two must negate explicitly.

Posterior by Laplace approximation: Newton iterations to the MAP latent, then the standard
GP predictive with the Hessian of the negative log-likelihood as the effective precision.
No standard scikit-learn or statsmodels routine implements this likelihood, which is why it is
written out here rather than delegated.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm
from sklearn.gaussian_process.kernels import ConstantKernel, Matern

from .surrogate import ParameterGrid


class PreferenceGP:
    """Pairwise-probit GP over the latent preference value of each tested setting.

    Parameters
    ----------
    grid
        The shared :class:`ParameterGrid`, so the preference surface is defined on exactly the
        same cells as the objective surface.
    sigma
        Comparison noise scale, fixed at 1.0 per Louie et al.; exposed only so that the choice
        is visible rather than buried.
    """

    def __init__(self, grid: ParameterGrid, *, sigma=1.0, length_scale_bounds=(0.15, 20.0),
                 jitter=1e-6, max_newton=100, tol=1e-8):
        self.grid = grid
        self.sigma = float(sigma)
        self.length_scale_bounds = length_scale_bounds
        self.jitter = float(jitter)
        self.max_newton = int(max_newton)
        self.tol = float(tol)
        self.f_ = None

    # --- likelihood pieces -------------------------------------------------------------
    def _z(self, f, wins, losses):
        return (f[wins] - f[losses]) / (np.sqrt(2.0) * self.sigma)

    def _grad_hess(self, f, wins, losses):
        """Gradient and (negative) Hessian of the log preference likelihood w.r.t. f."""
        n = f.size
        z = self._z(f, wins, losses)
        pdf = norm.pdf(z)
        cdf = np.clip(norm.cdf(z), 1e-12, 1.0)
        r = pdf / cdf                                    # d/dz log Phi(z)
        c = 1.0 / (np.sqrt(2.0) * self.sigma)
        g = np.zeros(n)
        np.add.at(g, wins, c * r)
        np.add.at(g, losses, -c * r)
        # -d^2/dz^2 log Phi(z) = r*(z + r)  >= 0
        lam = r * (z + r)
        W = np.zeros((n, n))
        cc = c * c
        for k, (i, j) in enumerate(zip(wins, losses)):
            W[i, i] += cc * lam[k]
            W[j, j] += cc * lam[k]
            W[i, j] -= cc * lam[k]
            W[j, i] -= cc * lam[k]
        return g, W

    def _loglik(self, f, wins, losses):
        return float(np.sum(np.log(np.clip(norm.cdf(self._z(f, wins, losses)), 1e-12, 1.0))))

    # --- fitting -----------------------------------------------------------------------
    def fit(self, X, comparisons, *, length_scale=None):
        """Fit the latent value function from pairwise judgements.

        Parameters
        ----------
        X
            ``(n, 2)`` array of the DISTINCT settings that were compared, in (freq_hz, amp_mA).
        comparisons
            Iterable of ``(i, j)`` index pairs into ``X`` meaning "setting i was preferred to
            setting j". Ties must be dropped by the caller, not encoded as either direction.
        length_scale
            ARD length scales for the transformed axes. Preference data carry too little
            information to fit kernel hyperparameters reliably at realistic comparison counts,
            so the default borrows nothing and simply uses unit length scales on the
            standardised axes. Pass the objective GP's fitted length scales to share smoothness
            across the two models — a deliberate choice, not a default.
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

        wins, losses = pairs[:, 0], pairs[:, 1]
        Z = self.grid.transform(X)
        ls = np.ones(Z.shape[1]) if length_scale is None else np.asarray(length_scale, float)
        # Fixed kernel: with a probit preference likelihood the marginal likelihood is only
        # available through the Laplace approximation, and at realistic comparison counts
        # optimising it overfits the amplitude. Length scales are supplied, not learned.
        self.kernel_ = ConstantKernel(1.0, "fixed") * Matern(
            length_scale=ls, nu=1.5, length_scale_bounds="fixed")
        K = self.kernel_(Z) + self.jitter * np.eye(Z.shape[0])

        f = np.zeros(X.shape[0])
        prev = -np.inf
        for _ in range(self.max_newton):
            g, W = self._grad_hess(f, wins, losses)
            A = np.linalg.inv(K) + W
            # Newton step on the MAP objective  log p(D|f) - 0.5 f' K^-1 f
            rhs = g - np.linalg.solve(K, f)
            f = f + np.linalg.solve(A, rhs)
            obj = self._loglik(f, wins, losses) - 0.5 * f @ np.linalg.solve(K, f)
            if abs(obj - prev) < self.tol:
                break
            prev = obj
        _, W = self._grad_hess(f, wins, losses)
        self.X_, self.Z_, self.K_, self.W_, self.f_ = X, Z, K, W, f
        self.pairs_ = pairs
        self.map_objective_ = prev
        # posterior covariance of the latent at the training settings (Laplace)
        self.cov_ = np.linalg.inv(np.linalg.inv(K) + W)
        return self

    # --- prediction ---------------------------------------------------------------------
    def predict(self, X=None):
        """Latent preference mean and SD. Higher mean = more preferred."""
        if self.f_ is None:
            raise RuntimeError("PreferenceGP is not fitted")
        Xq = self.grid.grid_X() if X is None else np.atleast_2d(np.asarray(X, float))
        Zq = self.grid.transform(Xq)
        Ks = self.kernel_(Zq, self.Z_)
        Kinv = np.linalg.inv(self.K_)
        mu = Ks @ (Kinv @ self.f_)
        Kss = self.kernel_.diag(Zq)
        M = Kinv - Kinv @ self.cov_ @ Kinv
        var = np.maximum(Kss - np.einsum("ij,jk,ik->i", Ks, M, Ks), 0.0)
        return mu, np.sqrt(var)

    def best(self, X=None):
        """Index and location of the most-preferred cell (argmax of the latent mean)."""
        Xq = self.grid.grid_X() if X is None else np.atleast_2d(np.asarray(X, float))
        mu, _ = self.predict(Xq)
        i = int(np.argmax(mu))
        return i, Xq[i]

    def prob_prefer(self, Xa, Xb):
        """Posterior probability that setting a is preferred to setting b.

        Uses the Laplace latent mean and variance, so the comparison noise and the model
        uncertainty are both included. This is the quantity to report when asking the patient
        to adjudicate two candidates: a probability near 0.5 means the model cannot separate
        them and the comparison is worth collecting.
        """
        mu, sd = self.predict(np.vstack([np.atleast_2d(Xa), np.atleast_2d(Xb)]))
        k = mu.size // 2
        dm = mu[:k] - mu[k:]
        dv = sd[:k] ** 2 + sd[k:] ** 2 + 2.0 * self.sigma ** 2
        return norm.cdf(dm / np.sqrt(dv))

    def holdout_accuracy(self, folds=5, random_state=0):
        """Fraction of held-out comparisons predicted correctly.

        Zhao et al. 2021 reported 71.5% in internal cross-validation and 65.6% prospectively for
        spinal cord stimulation, both significantly above chance, and published the validation
        protocol precisely because a preference model that cannot predict held-out preferences is
        not a therapeutic target. Same test, same purpose.
        """
        if self.f_ is None:
            raise RuntimeError("PreferenceGP is not fitted")
        rng = np.random.default_rng(random_state)
        m = self.pairs_.shape[0]
        if m < folds * 2:
            raise ValueError(f"need at least {folds * 2} comparisons for {folds}-fold CV, have {m}")
        order = rng.permutation(m)
        correct = total = 0
        for k in range(folds):
            te = order[k::folds]
            tr = np.setdiff1d(order, te)
            ls = self.kernel_.k2.length_scale
            fold = PreferenceGP(self.grid, sigma=self.sigma,
                                length_scale_bounds=self.length_scale_bounds,
                                jitter=self.jitter).fit(self.X_, self.pairs_[tr],
                                                        length_scale=ls)
            mu, _ = fold.predict(self.X_)
            for i, j in self.pairs_[te]:
                correct += int(mu[i] > mu[j])
                total += 1
        return correct / total
