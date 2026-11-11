"""Chance test for a band's mixed model with every shuffle worked out at once (decision 477). On no
page today: nothing in the platform calls it.

THE MODEL. The band's mixed model (`analytics.band_mixedmodel_inference`) is a logistic regression
of high against low pain on band power with one random intercept per week:
``pain_high ~ band_power + (1 | week)``. Asking whether band power matters by shuffling means
refitting that model once per shuffle: about 0.5 s a fit in lme4, so 1,000 shuffles take minutes.

THE SHORTCUT, AND WHY IT IS EXACT AS A CHANCE TEST. The model WITHOUT band power is fitted once.
Band power then enters only through a score statistic, how strongly the pain left unexplained by the
null model lines up with band power, divided by its own standard error (GMMAT's test; Chen et al.
2016, Am J Hum Genet 98:653). For a matrix whose columns are the observed and every shuffled band
power, all the statistics are two matrix products. The statistic is an approximation to lme4's Wald
z (they correlate 0.9996 on RCS08, decision 475), but a chance test needs only that the observed and
every shuffled order are scored by the SAME function, so its p is exact either way.

  * Working model at the null fit: working response ``Ytilde = eta + (y - mu) / w``, covariance
    ``Sigma = diag(1/w) + tau Z Z'`` (Z: which week each sample is in; tau: the week variance).
  * ``P = Sigma^-1 - Sigma^-1 X0 (X0' Sigma^-1 X0)^-1 X0' Sigma^-1`` (X0: the null's fixed effects).
  * Statistic for a band-power column x: ``T = x' P Ytilde``, variance ``x' P x``, ``z = T / sd``.
    P removes X0 exactly, so adding any mix of the null's fixed effects to x changes nothing.
  * ``Sigma^-1`` is never formed: within one week ``Sigma_j = diag(1/w_j) + tau 1 1'``, inverted in
    closed form (Sherman-Morrison), so the cost is linear in the samples.

WHICH SHUFFLE (decision 315 decides it). Pain and band power both drift slowly; shuffling samples
independently, even within a week, breaks that drift and makes p too small (on RCS08's layout an
unrelated made-up band read p <= 0.05 in 10.7% of records). The default is therefore the exact
rotation test: the pain series, carrying its weeks and its covariates, slid along the band-power
series by every possible number of samples, the end wrapped to the start, each rotation once. In
code the band power is rotated against fixed pain rows, which pairs the same values. n samples give
n orders including the observed one, so the smallest p is 1/n. ``scheme="within_cluster"`` (shuffle
within each week, drawn at random) is offered only for data with no order in time.

COVARIATES. With fixed effects beyond the intercept, band power is first made uncorrelated with them
under the null's weighting and only that remainder is moved ("Smith" in Winkler et al. 2014,
NeuroImage 92:381), so a rotation cannot break band power's link with a covariate.

Run the tests (plain asserts):  python3 modules/Biomarkers/tests/test_mixed_model_shuffle.py
"""
import numpy as np

#: Two statistics closer than this, relative to the observed one, count as a tie, and a tie counts
#: as at least as extreme (the safe direction): a rotation that reproduces the observed pairing
#: exactly can come out a few units in the last place apart from it.
TIE_RELATIVE = 1e-10


def _clusters(cluster):
    codes, cl = np.unique(np.asarray(cluster), return_inverse=True)
    return cl.astype(int), len(codes)


def sigma_inverse_times(M, w, tau, cl, n_clusters):
    """``Sigma^-1 M`` for ``Sigma = diag(1/w) + tau Z Z'``, with no n-by-n matrix.

    Within week j: ``Sigma_j^-1 = W_j - tau W_j 1 1' W_j / (1 + tau sum(w_j))`` (Sherman-Morrison)."""
    M = np.asarray(M, float)
    one_d = M.ndim == 1
    if one_d:
        M = M[:, None]
    wM = w[:, None] * M
    sums = np.zeros((n_clusters, M.shape[1]))
    np.add.at(sums, cl, wM)
    sw = np.bincount(cl, weights=w, minlength=n_clusters)
    out = wM - (tau * w)[:, None] * (sums / (1.0 + tau * sw)[:, None])[cl]
    return out[:, 0] if one_d else out


class NullModel:
    """The quantities of the fitted null model a score statistic needs, and P applied to anything.

    ``eta``: the null's linear predictor per sample, random intercepts included; ``w``: the working
    weights (binomial: mu (1 - mu); gaussian: 1 / residual variance); ``y_work``: the working
    response; ``X0``: the null's fixed-effect columns (n x p); ``tau``: the week variance."""

    def __init__(self, *, y, eta, tau, cluster, X0=None, family="binomial", residual_var=None):
        y = np.asarray(y, float)
        eta = np.asarray(eta, float)
        n = len(y)
        if len(eta) != n or len(cluster) != n:
            raise ValueError("y, eta and cluster must have one value per sample")
        if not (np.isfinite(y).all() and np.isfinite(eta).all()):
            raise ValueError("y and eta must be finite")
        self.family = family
        if family == "binomial":
            mu = 1.0 / (1.0 + np.exp(-eta))
            w = mu * (1.0 - mu)
            self.y_work = eta + (y - mu) / w
        elif family == "gaussian":
            if residual_var is None or not residual_var > 0:
                raise ValueError("a gaussian null model needs its residual variance")
            mu = eta
            w = np.full(n, 1.0 / float(residual_var))
            self.y_work = y.copy()
        else:
            raise ValueError(f"family must be 'binomial' or 'gaussian', not {family!r}")
        if not (w > 0).all():
            raise ValueError("every working weight must be positive (a fitted probability of 0 or 1)")
        self.y, self.mu, self.w, self.eta = y, mu, w, eta
        self.tau = max(float(tau), 0.0)
        self.cl, self.G = _clusters(cluster)
        self.X0 = np.ones((n, 1)) if X0 is None else np.asarray(X0, float).reshape(n, -1)
        self.S0 = self.sinv(self.X0)                                   # Sigma^-1 X0
        self.A = np.linalg.inv(self.X0.T @ self.S0)                    # (X0' Sigma^-1 X0)^-1
        self.r = self.P(self.y_work)                                   # P Ytilde

    def sinv(self, M):
        return sigma_inverse_times(M, self.w, self.tau, self.cl, self.G)

    def P(self, M):
        """``P M``; M is a vector or a matrix of columns."""
        SM = self.sinv(M)
        return SM - self.S0 @ (self.A @ (self.X0.T @ SM))

    def residualize(self, x):
        """x less its Sigma^-1-weighted projection on X0: the part a rotation may move (Smith)."""
        x = np.asarray(x, float)
        return x - self.X0 @ (self.A @ (self.S0.T @ x))

    def score_z(self, X):
        """The score statistic z for every column of X (n x k), or for one vector."""
        X = np.asarray(X, float)
        one_d = X.ndim == 1
        if one_d:
            X = X[:, None]
        T = X.T @ self.r
        V = np.einsum("ij,ij->j", X, self.P(X))
        z = np.full(X.shape[1], np.nan)
        ok = np.isfinite(V) & (V > 0)
        z[ok] = T[ok] / np.sqrt(V[ok])
        return z[0] if one_d else z


def rotation_matrix(x):
    """Every rotation of x as columns, the observed order first: column k is x slid by k samples."""
    x = np.asarray(x, float)
    n = len(x)
    idx = (np.arange(n)[:, None] + np.arange(n)[None, :]) % n
    return x[idx]


def within_cluster_matrix(x, cluster, n_shuffles, rng):
    """The observed x first, then ``n_shuffles`` shuffles of x within each cluster, drawn at random."""
    x = np.asarray(x, float)
    cl, _ = _clusters(cluster)
    order = np.argsort(cl, kind="stable")
    bounds = np.r_[0, np.flatnonzero(np.diff(cl[order])) + 1, len(x)]
    out = np.empty((len(x), n_shuffles + 1))
    out[:, 0] = x
    for k in range(1, n_shuffles + 1):
        perm = np.arange(len(x))
        for a, b in zip(bounds[:-1], bounds[1:]):
            g = order[a:b]
            perm[g] = g[rng.permutation(b - a)]
        out[:, k] = x[perm]
    return out


def shuffle_p(z, alternative="two-sided"):
    """``(#{shuffled at least as extreme as observed} + 1) / (#shuffled + 1)``; z[0] is observed."""
    z = np.asarray(z, float)
    if not np.isfinite(z[0]):
        return np.nan
    null = z[1:][np.isfinite(z[1:])]
    if alternative == "two-sided":
        obs, null = abs(z[0]), np.abs(null)
    elif alternative == "greater":
        obs = z[0]
    elif alternative == "less":
        obs, null = -z[0], -null
    else:
        raise ValueError("alternative must be 'two-sided', 'greater' or 'less'")
    tol = TIE_RELATIVE * max(1.0, abs(obs))
    return (int(np.sum(null >= obs - tol)) + 1) / (len(null) + 1)


def shuffle_test(null, x, *, order=None, scheme="rotation", n_shuffles=1000, rng=None,
                 alternative="two-sided", keep_null=False):
    """The chance test of adding x to a fitted ``NullModel``.

    ``order``: the samples' times (or any sort key); rotation needs the rows in time order, so they
    are sorted by it first (rows already in order may pass None). ``scheme``: "rotation" (every
    rotation once, the default and the only one for a series in time) or "within_cluster"
    (``n_shuffles`` random shuffles within each cluster; only for data with no order in time)."""
    x = np.asarray(x, float)
    n = len(x)
    if n != len(null.y):
        raise ValueError("x must have one value per sample of the null model")
    if not np.isfinite(x).all():
        raise ValueError("x must be finite")
    x_move = null.residualize(x) if null.X0.shape[1] > 1 else x
    if scheme == "rotation":
        srt = np.arange(n) if order is None else np.argsort(np.asarray(order), kind="stable")
        X = np.empty((n, n))
        X[srt] = rotation_matrix(x_move[srt])
        words = "exact: every rotation once"
    elif scheme == "within_cluster":
        rng = np.random.default_rng() if rng is None else rng
        X = within_cluster_matrix(x_move, null.cl, int(n_shuffles), rng)
        words = f"{int(n_shuffles)} random shuffles within each cluster"
    else:
        raise ValueError("scheme must be 'rotation' or 'within_cluster'")
    X[:, 0] = x                                    # the observed column is x itself
    z = null.score_z(X)
    out = {"z": float(z[0]), "p": float(shuffle_p(z, alternative)), "alternative": alternative,
           "scheme": scheme, "how": words, "n": n, "n_clusters": int(null.G), "tau": null.tau,
           "n_orders": int(X.shape[1]), "n_unusable": int(np.sum(~np.isfinite(z[1:]))),
           "p_floor": 1.0 / X.shape[1]}
    if keep_null:
        out["z_all"] = z
    return out


def null_fit_lme4(y, cluster, X0=None, *, family="binomial", names=None):
    """Fit the null model in lme4 (through pymer4, as the band's mixed model is fitted) and return a
    ``NullModel`` with lme4's own answer: its fitted values, random intercepts included, and the week
    variance; plus ``(converged, warnings)``. Needs R; the container has it, the host does not."""
    import pandas as pd
    from pymer4.models import Lmer
    from modules.Biomarkers.routines.analytics import _rpy2_converter_ctx
    n = len(y)
    X0 = None if X0 is None else np.asarray(X0, float).reshape(n, -1)
    df = pd.DataFrame({"y": np.asarray(y, float), "cluster": [str(c) for c in cluster]})
    terms = []
    if X0 is not None:                                   # columns beyond the intercept, by name
        names = names or [f"c{j}" for j in range(X0.shape[1])]
        for j, nm in enumerate(names):
            if np.allclose(X0[:, j], 1.0):
                continue
            df[nm] = X0[:, j]; terms.append(nm)
    formula = "y ~ " + (" + ".join(terms) if terms else "1") + " + (1|cluster)"
    with _rpy2_converter_ctx():
        m = Lmer(formula, data=df, family=family)
        m.fit(summarize=False)
        rv = m.ranef_var
    warnings = [str(w) for w in (getattr(m, "warnings", None) or [])]
    converged = not any(("failed to converge" in w.lower()) or ("unidentifiable" in w.lower())
                        for w in warnings)
    fits = np.asarray(m.fits, float)
    tau = float(rv.loc[rv.index[0], "Var"])
    if family == "binomial":
        f = np.clip(fits, 1e-15, 1 - 1e-15)
        eta, resid = np.log(f / (1 - f)), None
    else:
        eta = fits
        resid = float(rv["Var"].iloc[-1])                 # the Residual row
    X0_full = np.column_stack([np.ones(n)] + [df[t].to_numpy(float) for t in terms])
    return NullModel(y=y, eta=eta, tau=tau, cluster=cluster, X0=X0_full, family=family,
                     residual_var=resid), converged, warnings
