"""Phase 2: the three edges of the amplitude -> power -> pain triangle, estimated honestly.

The triangle is the module's whole argument. Closing the loop on a band requires all three of:

  E1  amplitude -> band power    the device can MOVE the signal (otherwise there is no control)
  E2  band power -> pain         the signal TRACKS the patient (otherwise control is pointless)
  E3  amplitude -> pain          the therapy WORKS (otherwise there is nothing to automate)

and requires their signs to be mutually consistent, which is what consistency.py tests.

WHY THE CLUSTERING UNIT IS RECORDED ON EVERY ESTIMATE. The fourteen-finding audit of the biomarker
plate found that the dominant source of overstated significance in this project was treating
correlated observations as independent — spectral samples within one setting epoch, or several
epochs belonging to one pain rating. Cluster-robust standard errors at the right unit are therefore
not a refinement here, they are the difference between a defensible number and an artefact, and an
EdgeEstimate that cannot state its clustering unit is not usable downstream.

WHAT E1 CANNOT BE ON THIS DATA. In the historical record, amplitude was escalated over months, so
amplitude is confounded with time and with everything else that drifts: impedance, disease state,
medication, the patient's expectations. No estimator removes that. E1 computed here is a SCREENING
statistic for deciding what to titrate prospectively, and it is labelled as such on the estimate
itself so that no panel can present it as a causal effect.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .types import EdgeEstimate


#: The number of clusters at or above which the cluster-robust (CR0) variance estimator is used
#: directly, and BELOW which inference is taken from the wild cluster bootstrap-t instead.
#:
#: This constant used to be a disqualification: any estimate with fewer clusters than this was
#: flagged unreliable and could not be assessed. The diagnosis behind that flag is correct and is
#: measured on this dataset. With few clusters CR0 is anti-conservative, meaning its intervals are
#: too NARROW, so it manufactures resolution rather than losing it; on the RCS08 record, cells with
#: three setting epochs reported all eighteen bands as resolved while the whole-epoch permutation on
#: the same cells returned a family-wise p of 1.00. But the RCS08 record has a maximum of 35 setting
#: epochs in any band-cell and a median of 7, so a floor of 40 disqualified every cell that exists
#: and will ever exist here, which is a refusal wearing the clothes of a criterion.
#:
#: The threshold is therefore now a SWITCH between two estimators rather than a gate. Below it, the
#: reported p-value and confidence interval come from the wild cluster bootstrap-t with Rademacher
#: weights imposed under the null (Cameron, Gelbach and Miller 2008), which is the inference method
#: with demonstrated size properties in the five-to-forty cluster range; the simulation in
#: tests/test_bootstrap.py measures both estimators against a known null and records what each one
#: actually does. The few-cluster condition is still reported on the estimate, but as information
#: about which estimator produced the numbers, not as a reason to withhold them.
#:
#: The value 40 itself follows the conventional rule of thumb in the clustered-inference literature
#: (Cameron and Miller 2015, "A Practitioner's Guide to Cluster-Robust Inference", section VI):
#: there is no sharp cutoff, and 40 is the commonly cited point above which the asymptotic
#: cluster-robust approximation is usually adequate. It is deliberately conservative, because using
#: the bootstrap when it was not needed costs computer time, whereas using CR0 when it was not
#: warranted costs a false claim about a patient's brain.
MIN_RELIABLE_CLUSTERS = 40

#: At or below this many clusters the whole Rademacher weight space is ENUMERATED rather than
#: sampled, because there are only 2**G distinct sign vectors and sampling 999 of them would draw
#: the same handful repeatedly while pretending to a resolution of one in a thousand. 2**12 = 4096,
#: which is the point where enumeration stops being cheaper than the usual 999 replications.
#:
#: This is also the range in which a reader has to be TOLD that the p-value is coarse. Two of the
#: 2**G sign vectors — all plus one and all minus one — reproduce the observed sample exactly under
#: the imposed null, so the enumerated p-value can never fall below 2 / 2**G. At eight clusters
#: that floor is 0.0078, at six it is 0.031, and at five it is 0.0625, which is ABOVE the
#: conventional five percent: with five clusters and Rademacher weights no result can be called
#: significant at the five percent level no matter how large the effect. That is a known and
#: deliberate property of the method (Cameron, Gelbach and Miller 2008, section IV; Webb 2013
#: proposes a six-point weight distribution specifically to relieve it), and it is reported on every
#: result through the `enumerable`, `n_sign_vectors` and `p_resolution` fields rather than hidden.
MAX_ENUMERABLE_CLUSTERS = 12


def _cluster_ols(y, X, groups, *, names=None):
    """OLS with cluster-robust (CR0) standard errors. Returns (params, bse, n_clusters).

    statsmodels is used rather than a hand-rolled sandwich because the conventional implementation
    handles the small-sample correction and the singular cases consistently, and because a
    re-implementation would be one more thing to audit.
    """
    import statsmodels.api as sm
    y = np.asarray(y, float)
    X = np.asarray(X, float)
    g = np.asarray(groups)
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1) & pd.notna(g)
    y, X, g = y[ok], X[ok], g[ok]
    if y.size < 3 or np.unique(g).size < 2:
        return None, None, int(np.unique(g).size if g.size else 0)
    res = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": g})
    return res, np.asarray(res.bse, float), int(np.unique(g).size)


# --------------------------------------------------------------------------------------------
# The wild cluster bootstrap-t
#
# WHY THIS EXISTS. Everything in this module is estimated on a handful of clusters: a setting epoch
# is a stretch during which the stimulation settings did not change, and RCS08 has at most 35 of
# them in any band-cell and typically 7. Cluster-robust standard errors are consistent as the
# NUMBER OF CLUSTERS grows, not as the number of observations grows, so at these cluster counts the
# CR0 sandwich has no asymptotic argument behind it and is known to be biased downward. Adding more
# spectral samples inside an epoch does not help, because those samples are not independent
# observations of the amplitude-power relationship; only more epochs would help, and the historical
# record contains the epochs it contains.
#
# The wild cluster bootstrap-t of Cameron, Gelbach and Miller (2008), "Bootstrap-Based Improvements
# for Inference with Clustered Errors", Review of Economics and Statistics 90(3), is the standard
# answer in this regime. Instead of trusting the sandwich to give the right standard error, it
# builds the sampling distribution of the t STATISTIC itself by re-generating the outcome many
# times under a null-imposed model, flipping the sign of each cluster's whole residual vector, and
# recomputing the same t statistic each time. The observed t is then read against that distribution
# rather than against a normal or t table. Because the statistic's own denominator is recomputed in
# every replication, the method corrects for the downward bias of the denominator instead of
# assuming it away.
#
# WHAT MUST NOT BE GOT WRONG. The sign is drawn ONCE PER CLUSTER and applied to every observation in
# that cluster. Drawing a sign per observation destroys exactly the within-cluster dependence the
# procedure exists to respect, and silently degrades the method to an ordinary residual bootstrap
# whose intervals are as narrow as the ones being replaced. There is a test for this
# (tests/test_bootstrap.py) that checks the weight structure directly rather than trusting the
# output to look reasonable.
# --------------------------------------------------------------------------------------------
def _rademacher_weights(n_clusters, n_boot, seed):
    """Return (W, method, n_sign_vectors) where W has one row per replication and one column per
    CLUSTER, with entries +1 or -1.

    One column per cluster, not one per observation. The caller expands each row across that
    cluster's rows, so this shape is what makes the per-cluster requirement structural rather than
    a matter of remembering to do it.

    When the number of clusters is small enough that the whole weight space fits
    (``n_clusters <= MAX_ENUMERABLE_CLUSTERS``) every one of the 2**G sign vectors is returned
    exactly once. Sampling in that regime would draw the same few vectors repeatedly and report a
    resolution of one in a thousand that the weight space cannot deliver; enumerating instead makes
    the p-value exact for the chosen weight distribution and makes its coarseness visible.
    """
    G = int(n_clusters)
    if G <= MAX_ENUMERABLE_CLUSTERS:
        n_vec = 2 ** G
        bits = (np.arange(n_vec, dtype=np.int64)[:, None] >> np.arange(G)[None, :]) & 1
        return (1.0 - 2.0 * bits).astype(float), "enumerated", n_vec
    rng = np.random.default_rng(seed)
    W = rng.integers(0, 2, size=(int(n_boot), G)).astype(float) * 2.0 - 1.0
    return W, "sampled", 2 ** G


def _cr0_variance(X, resid, seg_starts, XtX_inv):
    """The CR0 cluster-robust covariance matrix, computed here rather than taken from statsmodels.

    Computed locally for one reason: the bootstrap has to apply the SAME variance formula to every
    replication that it applies to the observed sample, and reaching into statsmodels once per
    replication would cost a model fit per replication for a quantity that is three matrix products.
    No small-sample correction factor is applied. Any correction that depends only on the number of
    observations, regressors and clusters — statsmodels' default ``(n-1)/(n-k) * G/(G-1)`` among
    them — is the same constant in the observed sample and in every replication, so it multiplies
    both sides of the comparison ``|t*| >= |t_obs|`` and cancels exactly. Leaving it out therefore
    changes no bootstrap p-value, and putting it in would invite the reader to think it did.

    ``resid`` may be a single vector or a (replications, observations) matrix; rows of X must be
    sorted by cluster and ``seg_starts`` gives the first row index of each cluster.
    """
    R = np.atleast_2d(np.asarray(resid, float))                     # (B, n)
    k = X.shape[1]
    S = np.empty((k, R.shape[0], seg_starts.size), float)           # (k, B, G)
    for i in range(k):
        S[i] = np.add.reduceat(R * X[:, i], seg_starts, axis=1)
    meat = np.einsum("ibg,jbg->bij", S, S)                          # (B, k, k)
    return np.einsum("ip,bpq,qj->bij", XtX_inv, meat, XtX_inv)


class _BootstrapPlan:
    """Everything needed to evaluate the bootstrap-t at ANY candidate coefficient value, computed
    once.

    The reason this is a prepared object rather than a function call per candidate value is that
    confidence intervals here are formed by INVERTING the test — asking which candidate values the
    bootstrap-t would not reject — and a naive implementation redraws and refits for every candidate
    on the grid, which multiplies the cost by the grid size. That is avoidable exactly, not
    approximately. Under the imposed null at candidate value b0 the restricted residuals are

        u(b0) = M_r y - b0 * M_r x_j

    where M_r annihilates the OTHER regressors, so they are affine in b0. Everything downstream is
    then either affine in b0 (the bootstrap coefficient and the bootstrap residuals) or quadratic in
    b0 (the CR0 meat matrix, being a sum of outer products of affine terms). So the two affine
    pieces and the three quadratic-form pieces are accumulated once here, and each candidate value
    costs a handful of small matrix products instead of a fresh set of replications. The interval
    that comes out is the genuine inverted-test interval, not a normal approximation dressed up.
    """

    def __init__(self, y, X, groups, *, coef_index, n_boot, seed, impose_null, chunk=256):
        y = np.asarray(y, float)
        X = np.asarray(X, float)
        g = np.asarray(groups)
        ok = np.isfinite(y) & np.isfinite(X).all(axis=1) & pd.notna(g)
        y, X, g = y[ok], X[ok], g[ok]
        self.available, self.reason = False, ""
        self.n, k = X.shape[0], X.shape[1]
        if not (0 <= int(coef_index) < k):
            self.reason = f"coef_index {coef_index} is not a column of the design"
            return
        self.j = int(coef_index)
        order = np.argsort(g, kind="stable")
        y, X, g = y[order], X[order], g[order]
        uniq, self.seg_starts, counts = np.unique(g, return_index=True, return_counts=True)
        self.n_clusters = int(uniq.size)
        if self.n_clusters < 2:
            self.reason = (f"{self.n_clusters} cluster(s); the sign-flip distribution needs at "
                           "least two clusters to have any support")
            return
        if self.n <= k or np.linalg.matrix_rank(X) < k:
            self.reason = "design matrix is rank deficient or has no residual degrees of freedom"
            return

        XtX_inv = np.linalg.inv(X.T @ X)
        A = XtX_inv @ X.T                                            # (k, n)
        self.b_hat = float((A @ y)[self.j])
        resid = y - X @ (A @ y)
        V = _cr0_variance(X, resid, self.seg_starts, XtX_inv)[0]
        var_j = float(V[self.j, self.j])
        if not np.isfinite(var_j) or var_j <= 0:
            self.reason = "the observed CR0 variance is zero or not finite"
            return
        self.se_cr0 = float(np.sqrt(var_j))

        # The two residual pieces. Under the restricted (null-imposed) variant the residuals are
        # taken from the model that FORCES the coefficient to the candidate value, which is what
        # gives the method its size properties, and they are affine in that value. Under the
        # unrestricted variant they are the ordinary residuals and do not depend on it at all.
        if impose_null:
            keep = [i for i in range(k) if i != self.j]
            if keep:
                Xr = X[:, keep]
                Pr = Xr @ np.linalg.pinv(Xr)
                u0 = y - Pr @ y
                u1 = X[:, self.j] - Pr @ X[:, self.j]
            else:
                u0, u1 = y.copy(), X[:, self.j].copy()
            self.centre_at_bhat = False
        else:
            u0, u1 = resid, np.zeros_like(resid)
            self.centre_at_bhat = True

        W, self.method, self.n_sign_vectors = _rademacher_weights(self.n_clusters, n_boot, seed)
        self.n_boot = int(W.shape[0])
        self.impose_null = bool(impose_null)

        # Accumulate, in blocks of replications to bound memory: the affine pieces of the bootstrap
        # coefficient, and the three matrices that make the CR0 meat a quadratic in the candidate
        # value.
        self.num0 = np.empty(self.n_boot, float)
        self.num1 = np.empty(self.n_boot, float)
        self.M0 = np.empty((self.n_boot, k, k), float)
        self.M1 = np.empty((self.n_boot, k, k), float)
        self.M2 = np.empty((self.n_boot, k, k), float)
        Aj = A[self.j]
        for s in range(0, self.n_boot, chunk):
            Wb = np.repeat(W[s:s + chunk], counts, axis=1)           # (b, n) sign per CLUSTER
            # One sign-flipped copy of each residual piece. The bootstrap coefficient is read off
            # with the ordinary OLS operator, and the bootstrap residuals are formed by removing the
            # fitted part, both of which are linear in the weighted residuals.
            U0w, U1w = Wb * u0[None, :], Wb * u1[None, :]
            self.num0[s:s + Wb.shape[0]] = U0w @ Aj
            self.num1[s:s + Wb.shape[0]] = U1w @ Aj
            E0 = U0w - (U0w @ A.T) @ X.T
            E1 = U1w - (U1w @ A.T) @ X.T
            Sp = np.empty((k, Wb.shape[0], self.n_clusters), float)
            Sq = np.empty_like(Sp)
            for i in range(k):
                Sp[i] = np.add.reduceat(E0 * X[:, i], self.seg_starts, axis=1)
                Sq[i] = np.add.reduceat(E1 * X[:, i], self.seg_starts, axis=1)
            self.M0[s:s + Wb.shape[0]] = np.einsum("ibg,jbg->bij", Sp, Sp)
            self.M1[s:s + Wb.shape[0]] = np.einsum("ibg,jbg->bij", Sp, Sq)
            self.M2[s:s + Wb.shape[0]] = np.einsum("ibg,jbg->bij", Sq, Sq)
        self.XtX_inv = XtX_inv
        self.available = True

    # -- the achievable resolution of the p-value ---------------------------------------------
    @property
    def enumerable(self):
        return self.n_clusters <= MAX_ENUMERABLE_CLUSTERS

    @property
    def p_resolution(self):
        """The smallest p-value this configuration can return.

        When the weight space is enumerated the floor is 2 / 2**G, not 1 / 2**G, because the
        all-plus-one and all-minus-one sign vectors both reproduce the observed sample under the
        imposed null and therefore always tie with the observed statistic. When it is sampled the
        floor is the usual 1 / (n_boot + 1).
        """
        if self.method == "enumerated":
            return 2.0 / float(self.n_sign_vectors)
        return 1.0 / float(self.n_boot + 1)

    def t_star(self, b0):
        """The bootstrap distribution of the t statistic at candidate value ``b0``."""
        num = self.num0 - b0 * self.num1
        meat = self.M0 - b0 * (self.M1 + np.swapaxes(self.M1, 1, 2)) + (b0 ** 2) * self.M2
        V = np.einsum("ip,bpq,qj->bij", self.XtX_inv, meat, self.XtX_inv)
        var = V[:, self.j, self.j]
        with np.errstate(invalid="ignore", divide="ignore"):
            return num / np.sqrt(np.where(var > 0, var, np.nan))

    def t_obs(self, b0):
        """The observed statistic, always the studentised distance from the candidate value."""
        return (self.b_hat - b0) / self.se_cr0

    def p_value(self, b0=0.0):
        """Two-sided bootstrap-t p-value for the hypothesis that the coefficient equals ``b0``."""
        ts = self.t_star(b0)
        tob = abs(self.t_obs(b0))
        good = np.isfinite(ts)
        # A tolerance is needed because the all-plus-one weight vector reconstructs the observed
        # sample exactly in arithmetic but only to rounding in floating point, and that replication
        # must be counted as the tie it is rather than dropped by a strict comparison.
        tol = 1e-9 * max(1.0, tob)
        hits = int((np.abs(ts[good]) >= tob - tol).sum())
        n_used = int(good.sum())
        if n_used == 0:
            return float("nan"), 0, 0
        if self.method == "enumerated":
            return float(hits) / float(n_used), hits, n_used
        return float(1 + hits) / float(n_used + 1), hits, n_used


def wild_cluster_bootstrap_t(y, X, groups, *, coef_index=1, n_boot=999, seed=0, impose_null=True,
                             null_value=0.0):
    """Wild cluster bootstrap-t p-value for one coefficient, valid at small cluster counts.

    Cameron, Gelbach and Miller (2008). The outcome is re-generated many times from a model that
    holds the coefficient at ``null_value``, with the sign of each cluster's residual vector flipped
    at random, and the same cluster-robust t statistic is recomputed on every replication. The
    observed statistic is then compared with that distribution.

    WHY THE RESTRICTED VARIANT IS THE DEFAULT. ``impose_null=True`` re-generates the data from the
    model in which the null is TRUE (the WCR variant of the original paper). This is the choice that
    gives the method its size properties, because the distribution being built is then the
    distribution of the statistic under the hypothesis actually being tested; the unrestricted
    variant builds it around the estimate instead, and Cameron, Gelbach and Miller (2008, section
    IV) report that it over-rejects in exactly the few-cluster range this module works in. The
    argument is left as an explicit keyword rather than hard-wired because the two variants differ
    by a diagnosis rather than a detail, and a reader of this code should be able to see which was
    used and reproduce the other.

    Returns a dictionary with the p-value, the number of replications actually used, the number of
    clusters, the observed t statistic, and the achievable resolution of the p-value. It also
    reports whether the weight space was small enough to enumerate and how many distinct sign
    vectors exist, so a reader can see when the p-value is coarse rather than having to know that
    Rademacher weights on G clusters admit only 2**G possibilities.
    """
    plan = _BootstrapPlan(y, X, groups, coef_index=coef_index, n_boot=n_boot, seed=seed,
                          impose_null=impose_null)
    if not plan.available:
        return {"available": False, "reason": plan.reason, "p": None, "n_clusters": plan.n_clusters,
                "n_boot": 0, "t_obs": None, "p_resolution": None}
    p, hits, used = plan.p_value(null_value)
    return {"available": True, "p": p, "n_boot": used, "n_boot_requested": plan.n_boot,
            "n_clusters": plan.n_clusters, "t_obs": float(plan.t_obs(null_value)),
            "p_resolution": plan.p_resolution, "enumerable": plan.enumerable,
            "n_sign_vectors": int(plan.n_sign_vectors), "weights": "rademacher",
            "draw": plan.method, "impose_null": plan.impose_null, "coef_index": int(coef_index),
            "null_value": float(null_value), "estimate": plan.b_hat, "se_cr0": plan.se_cr0,
            "n": int(plan.n), "n_exceedances": hits,
            "note": ("wild cluster bootstrap-t, Rademacher weights drawn once per cluster, "
                     f"{plan.method} weight space of {plan.n_sign_vectors} sign vectors "
                     f"(Cameron, Gelbach and Miller 2008)")}


def wild_cluster_bootstrap_ci(y, X, groups, *, coef_index=1, n_boot=999, seed=0, alpha=0.05,
                              n_grid=161, max_widen=6, refine_steps=48):
    """Confidence interval for one coefficient by INVERTING the bootstrap-t test.

    The interval is the set of candidate coefficient values the bootstrap-t does not reject at level
    ``alpha``. This is the only way to get an interval with the same small-sample properties as the
    p-value: taking the bootstrap p-value and then reporting the CR0 interval beside it would pair
    valid inference with the invalid interval it was brought in to replace, and a reader comparing
    the two would find the interval excluding zero while the p-value did not.

    THE COST, SINCE THE ALTERNATIVE WAS TO SUBSTITUTE SOMETHING CHEAPER. Full inversion is done, not
    approximated. It is affordable because the restricted residuals are affine in the candidate
    value, so one set of replications serves the whole grid (see ``_BootstrapPlan``); the grid
    therefore costs a few small matrix products per candidate instead of a full set of bootstrap
    refits, and the endpoints are then refined by bisection to well past the precision anyone
    reports. Measured on a band-cell of the size this module sees — of the order of seven hundred
    spectral samples spread over eight to thirty-five setting epochs — a full inversion takes
    between 30 and 75 milliseconds against 0.2 to 0.3 milliseconds for the CR0 fit it replaces, so
    it is one to four hundred times the cost of the thing it replaces and still under a tenth of a
    second per edge. Scanning the 324 era-stratified band-cells of the RCS08 record takes about
    eleven seconds. The cost grows with the number of ROWS, not with the grid, so a cell with tens
    of thousands of samples takes seconds rather than milliseconds; that is worth knowing before
    calling this on a table that has not been reduced to band powers.

    The grid is centred on the point estimate, which is always inside the interval because the
    observed statistic is zero there and every replication ties with it. If the accepted set reaches
    the edge of the grid the grid is widened and retried; if it still reaches the edge, or if the
    achievable p-value floor is above ``alpha`` so that nothing can be rejected at all, the interval
    is UNBOUNDED and is reported as absent with the reason stated. An absent interval is not a
    failure of the computation, it is the honest answer when a five-cluster sign-flip distribution
    cannot deliver a five percent test.
    """
    plan = _BootstrapPlan(y, X, groups, coef_index=coef_index, n_boot=n_boot, seed=seed,
                          impose_null=True)
    out = {"available": False, "ci": None, "alpha": float(alpha), "reason": ""}
    if not plan.available:
        out["reason"] = plan.reason
        out["n_clusters"] = plan.n_clusters
        return out
    p0, _, _ = plan.p_value(0.0)
    out.update({"available": True, "p_at_null": p0, "estimate": plan.b_hat,
                "se_cr0": plan.se_cr0, "n_clusters": plan.n_clusters, "n_boot": plan.n_boot,
                "draw": plan.method, "enumerable": plan.enumerable,
                "n_sign_vectors": int(plan.n_sign_vectors),
                "p_resolution": plan.p_resolution, "n": int(plan.n)})
    if plan.p_resolution > alpha:
        out["ci_unbounded"] = True
        out["reason"] = (f"the {plan.method} Rademacher weight space on {plan.n_clusters} clusters "
                         f"cannot produce a p-value below {plan.p_resolution:.4f}, which is above "
                         f"alpha = {alpha}, so no candidate value is rejected and the interval is "
                         "unbounded in both directions")
        return out

    half = 10.0 * plan.se_cr0
    grid = accept = None
    for _ in range(int(max_widen)):
        grid = plan.b_hat + np.linspace(-half, half, int(n_grid))
        accept = np.array([plan.p_value(float(b))[0] > alpha for b in grid])
        if not (accept[0] or accept[-1]):
            break
        half *= 4.0
    else:
        out["ci_unbounded"] = True
        out["reason"] = ("the accepted set still reached the edge of a grid spanning "
                         f"+/- {half / plan.se_cr0:.0f} CR0 standard errors, so the interval is "
                         "treated as unbounded rather than silently truncated at the grid")
        return out

    centre = int(np.argmin(np.abs(grid - plan.b_hat)))
    lo_i = centre
    while lo_i > 0 and accept[lo_i - 1]:
        lo_i -= 1
    hi_i = centre
    while hi_i < accept.size - 1 and accept[hi_i + 1]:
        hi_i += 1

    def _boundary(inside, outside):
        for _ in range(int(refine_steps)):
            mid = 0.5 * (inside + outside)
            if plan.p_value(float(mid))[0] > alpha:
                inside = mid
            else:
                outside = mid
        return 0.5 * (inside + outside)

    lo = _boundary(grid[lo_i], grid[lo_i - 1])
    hi = _boundary(grid[hi_i], grid[hi_i + 1])
    out["ci"] = (float(lo), float(hi))
    out["ci_unbounded"] = False
    out["n_grid"] = int(n_grid)
    # The accepted set of a bootstrap test need not be an interval. When it is not, the reported
    # interval is the connected component containing the point estimate, and the reader is told,
    # because quietly reporting the hull of a disconnected set would overstate what was accepted.
    outside = int(accept.sum()) - (hi_i - lo_i + 1)
    out["acceptance_nonconvex"] = bool(outside > 0)
    out["n_accepted_outside_reported_interval"] = int(max(outside, 0))
    return out


def _small_sample_inference(y, X, groups, *, coef_index=1, n_boot=999, seed=0, alpha=0.05):
    """The p-value and interval that the three edges use when the cluster count is below
    ``MIN_RELIABLE_CLUSTERS``, together with the sentence that says so on the estimate.

    Factored out so that all three edges switch estimators identically. An edge that switched on a
    slightly different condition, or described the switch differently, would leave a reader
    comparing two edges unable to tell whether a difference between them was in the data or in the
    inference.
    """
    ci = wild_cluster_bootstrap_ci(y, X, groups, coef_index=coef_index, n_boot=n_boot, seed=seed,
                                   alpha=alpha)
    if not ci.get("available"):
        return None, None, ("INFERENCE UNAVAILABLE: the wild cluster bootstrap could not be formed "
                            f"({ci.get('reason')}), and the CR0 interval is not reported in its "
                            "place because at this cluster count it would be too narrow."), ci
    floor = ci["p_resolution"]
    where = ("the whole Rademacher weight space of "
             f"{ci['n_sign_vectors']} sign vectors was enumerated exactly"
             if ci["draw"] == "enumerated" else
             f"{ci['n_boot']} replications were drawn from the {ci['n_sign_vectors']} possible "
             "sign vectors")
    note = (f"INFERENCE FROM THE WILD CLUSTER BOOTSTRAP-t, not from CR0. With {ci['n_clusters']} "
            f"clusters — below the {MIN_RELIABLE_CLUSTERS} at which the cluster-robust variance "
            "estimator has an asymptotic argument behind it — CR0 intervals are too narrow and "
            "manufacture resolution. The p-value and interval reported here come instead from the "
            "restricted wild cluster bootstrap-t with Rademacher weights drawn once per cluster "
            f"(Cameron, Gelbach and Miller 2008); {where}, and the smallest p-value this weight "
            f"space can return is {floor:.4g}. The interval is the set of coefficient values that "
            "test does not reject, obtained by inverting it.")
    if ci.get("ci_unbounded"):
        note += (" THE INTERVAL IS UNBOUNDED and is reported as absent: " + ci.get("reason", "")
                 + ". The edge is therefore unresolved, which is a statement about how few "
                   "clusters there are and not about how large the effect is.")
    if ci.get("acceptance_nonconvex"):
        note += (f" The bootstrap accepted {ci['n_accepted_outside_reported_interval']} candidate "
                 "values outside the reported interval; the interval given is the connected "
                 "component containing the point estimate.")
    return ci["p_at_null"], ci["ci"], note, ci


def actuation_edge(T, *, channel, center_hz, hemisphere="Left", scale="power_linear",
                   n_boot=999, seed=0):
    """E1: does band power move with programmed amplitude?

    Cluster unit is the SETTING EPOCH. Every spectral sample recorded while one set of stimulation
    parameters was in force is one observation of that setting, not many independent ones; treating
    them as independent is the pseudoreplication the audit identified.

    Estimated on the LINEAR power scale by default, because rule D11 records that the device
    computes LFP power as a linear sum of squared magnitude, and an edge intended to predict device
    behaviour should be on the device's own scale.
    """
    from .adapter import resolve_setting_column
    amp_col = resolve_setting_column(T.columns if T is not None else [], "amp", hemisphere)
    if amp_col is None:
        return EdgeEstimate("E1", None, None, None, 0, "setting epoch", 0, scale,
                            note=f"no amplitude column for the {hemisphere} hemisphere under any "
                                 "known spelling; the joined table carried no delivered amplitude, "
                                 "so an actuation slope cannot be formed")
    need = {amp_col, scale, "setting_epoch", "channel", "center_hz"}
    if T is None or T.empty or not need.issubset(T.columns):
        return EdgeEstimate("E1", None, None, None, 0, "setting epoch", 0, scale,
                            note=f"missing columns: {sorted(need - set(T.columns if T is not None else []))}")
    d = T[(T.channel == channel) & (np.isclose(T.center_hz, center_hz))].copy()
    d = d.dropna(subset=[amp_col, scale, "setting_epoch"])
    d = d[d.setting_epoch >= 0]
    if len(d) < 6:
        return EdgeEstimate("E1", None, None, None, len(d), "setting epoch",
                            int(d.setting_epoch.nunique()), scale, note="too few usable samples")
    X = np.column_stack([np.ones(len(d)), pd.to_numeric(d[amp_col], errors="coerce").to_numpy()])
    res, bse, nclu = _cluster_ols(d[scale].to_numpy(), X, d.setting_epoch.to_numpy())
    if res is None:
        return EdgeEstimate("E1", None, None, None, len(d), "setting epoch", nclu, scale,
                            note="fewer than two setting epochs; a within-subject slope is not "
                                 "identifiable from a single setting")
    b = float(res.params[1]); se = float(bse[1])
    p, ci = float(res.pvalues[1]), (b - 1.96 * se, b + 1.96 * se)
    note = ("SCREENING STATISTIC ONLY. Amplitude is confounded with time in the historical record, "
            "so this cannot be read as the causal effect of amplitude on power. Its purpose is to "
            "choose what to titrate.")
    conf = ["time", "impedance drift", "concurrent rate changes"]
    if nclu < MIN_RELIABLE_CLUSTERS:
        note += (f" FEW CLUSTERS: {nclu} setting epochs is below the {MIN_RELIABLE_CLUSTERS} at "
                 "which the cluster-robust variance estimator has an asymptotic argument behind it. "
                 "This is reported as information about which estimator was used, not as a reason "
                 "to withhold the estimate. ")
        conf.append("few clusters")
        p, ci, boot_note, _ = _small_sample_inference(
            d[scale].to_numpy(float), X, d.setting_epoch.to_numpy(), n_boot=n_boot, seed=seed)
        note += boot_note
    else:
        note += (f" Inference is CR0 cluster-robust at the setting epoch on {nclu} clusters, which "
                 f"is at or above the {MIN_RELIABLE_CLUSTERS}-cluster point where the asymptotic "
                 "approximation is usually adequate.")
    return EdgeEstimate("E1", b, ci, p, len(d), "setting epoch", nclu, scale,
                        note=note, confounded_by=conf)


def state_edge(T, *, channel, center_hz, outcome="nrs", scale="power_linear",
               cluster="report_id", n_boot=999, seed=0):
    """E2: does the band track the patient's pain at fixed stimulation?

    Cluster unit is the RATING. One pain report is matched to a window containing many spectral
    samples; those samples share the report's value entirely, so they carry one observation of the
    pain-power relationship between them.
    """
    need = {scale, outcome, "channel", "center_hz"}
    if T is None or T.empty or not need.issubset(T.columns):
        return EdgeEstimate("E2", None, None, None, 0, cluster, 0, scale,
                            note=f"missing columns: {sorted(need - set(T.columns if T is not None else []))}")
    d = T[(T.channel == channel) & (np.isclose(T.center_hz, center_hz))].copy()
    grp = cluster if cluster in d.columns else None
    if grp is None:
        return EdgeEstimate("E2", None, None, None, len(d), cluster, 0, scale,
                            note=f"no {cluster} column: the rating-level cluster is unavailable, and "
                                 "estimating this edge without it would reproduce the "
                                 "pseudoreplication the audit flagged")
    d = d.dropna(subset=[scale, outcome, grp])
    if len(d) < 6:
        return EdgeEstimate("E2", None, None, None, len(d), cluster,
                            int(d[grp].nunique()), scale, note="too few usable samples")
    X = np.column_stack([np.ones(len(d)), d[scale].to_numpy(float)])
    res, bse, nclu = _cluster_ols(d[outcome].to_numpy(float), X, d[grp].to_numpy())
    if res is None:
        return EdgeEstimate("E2", None, None, None, len(d), cluster, nclu, scale,
                            note="fewer than two rating clusters")
    b = float(res.params[1]); se = float(bse[1])
    p, ci = float(res.pvalues[1]), (b - 1.96 * se, b + 1.96 * se)
    n2 = ("clustered at the rating, which is the unit that carries one independent observation "
          "of pain. ")
    if nclu < MIN_RELIABLE_CLUSTERS:
        n2 += (f"FEW CLUSTERS: {nclu} ratings is below {MIN_RELIABLE_CLUSTERS}. ")
        p, ci, boot_note, _ = _small_sample_inference(
            d[outcome].to_numpy(float), X, d[grp].to_numpy(), n_boot=n_boot, seed=seed)
        n2 += boot_note
    else:
        n2 += (f"Inference is CR0 cluster-robust on {nclu} clusters, at or above the "
               f"{MIN_RELIABLE_CLUSTERS}-cluster point where that approximation is usually "
               "adequate.")
    return EdgeEstimate("E2", b, ci, p, len(d), cluster, nclu, scale, note=n2)


def therapy_edge(design_matrix, *, outcome="nrs", amp_col="amp_mA_Left", cluster="epoch",
                 n_boot=999, seed=0):
    """E3: does pain change with amplitude across settings?

    Read from the exposure-epoch design matrix rather than the spectral table, because this edge
    does not involve the brain signal at all. Era-blocking is the caller's responsibility; the note
    records whether a block variable was supplied, since an unblocked estimate on this record is
    dominated by the same amplitude-time confound that limits E1.
    """
    if design_matrix is None or len(design_matrix) == 0:
        return EdgeEstimate("E3", None, None, None, 0, cluster, 0, "mA", note="no design matrix")
    d = design_matrix.copy()
    if amp_col not in d.columns or outcome not in d.columns:
        return EdgeEstimate("E3", None, None, None, 0, cluster, 0, "mA",
                            note=f"missing {amp_col!r} or {outcome!r}")
    grp = cluster if cluster in d.columns else None
    d = d.dropna(subset=[amp_col, outcome] + ([grp] if grp else []))
    if len(d) < 6 or grp is None:
        return EdgeEstimate("E3", None, None, None, len(d), cluster, 0, "mA",
                            note="too few epochs, or no cluster column")
    X = np.column_stack([np.ones(len(d)), d[amp_col].to_numpy(float)])
    res, bse, nclu = _cluster_ols(d[outcome].to_numpy(float), X, d[grp].to_numpy())
    if res is None:
        return EdgeEstimate("E3", None, None, None, len(d), cluster, nclu, "mA",
                            note="fewer than two epoch clusters")
    b = float(res.params[1]); se = float(bse[1])
    p, ci = float(res.pvalues[1]), (b - 1.96 * se, b + 1.96 * se)
    note = ("unblocked unless the caller supplied an era-restricted matrix; on the historical "
            "record an unblocked estimate carries the amplitude-time confound. ")
    if nclu < MIN_RELIABLE_CLUSTERS:
        note += f"FEW CLUSTERS: {nclu} epochs is below {MIN_RELIABLE_CLUSTERS}. "
        p, ci, boot_note, _ = _small_sample_inference(
            d[outcome].to_numpy(float), X, d[grp].to_numpy(), n_boot=n_boot, seed=seed)
        note += boot_note
    else:
        note += (f"Inference is CR0 cluster-robust on {nclu} clusters, at or above the "
                 f"{MIN_RELIABLE_CLUSTERS}-cluster point where that approximation is usually "
                 "adequate.")
    return EdgeEstimate("E3", b, ci, p, len(d), cluster, nclu, "mA", note=note,
                        confounded_by=["time"])


def max_statistic_permutation(T, *, channels, centers, amp_col="amp_mA_Left",
                              scale="power_linear", n_perm=2000, seed=0):
    """Family-wise corrected p for "does ANY band-cell respond to amplitude?".

    Permutes amplitude BETWEEN SETTING EPOCHS, keeping every sample within an epoch together, and
    records the largest absolute t statistic across all band-cells in each replicate. Comparing the
    observed maximum against that distribution corrects for having scanned many cells without
    assuming they are independent — which they are not, since neighbouring bands share spectral
    bins and channels share a lead.

    Permuting whole epochs rather than samples is the point: shuffling samples would break the
    within-epoch dependence and produce a null that is far too narrow, which is the mechanism that
    made earlier scans look significant.
    """
    if T is None or T.empty or amp_col not in T.columns:
        return {"available": False, "reason": "no usable table"}
    rng = np.random.default_rng(seed)
    cells = [(c, f) for c in channels for f in centers]
    base = T[T.setting_epoch >= 0].dropna(subset=[amp_col, scale, "setting_epoch"])
    if base.empty:
        return {"available": False, "reason": "no rows with an epoch and both variables"}
    ep = base[["setting_epoch", amp_col]].drop_duplicates("setting_epoch").set_index("setting_epoch")[amp_col]
    if ep.size < 3:
        return {"available": False, "reason": f"only {ep.size} setting epochs; a permutation null "
                                              "over epochs needs at least three"}

    def _tmax(amp_map):
        best = 0.0
        for ch, fc in cells:
            d = base[(base.channel == ch) & (np.isclose(base.center_hz, fc))]
            if len(d) < 6 or d.setting_epoch.nunique() < 2:
                continue
            a = d.setting_epoch.map(amp_map).to_numpy(float)
            X = np.column_stack([np.ones(len(d)), a])
            res, bse, _ = _cluster_ols(d[scale].to_numpy(float), X, d.setting_epoch.to_numpy())
            if res is None or not np.isfinite(bse[1]) or bse[1] == 0:
                continue
            best = max(best, abs(float(res.params[1]) / float(bse[1])))
        return best

    obs = _tmax(ep.to_dict())
    vals = ep.to_numpy()
    null = np.empty(n_perm, float)
    for i in range(n_perm):
        null[i] = _tmax(dict(zip(ep.index, rng.permutation(vals))))
    p = float((1 + (null >= obs).sum()) / (1 + n_perm))
    return {"available": True, "observed_max_t": obs, "p_fwer": p, "n_perm": int(n_perm),
            "n_cells": len(cells), "n_epochs_permuted": int(ep.size),
            "resolution": 1.0 / (1 + n_perm),
            "note": ("amplitude permuted between whole setting epochs, preserving within-epoch "
                     "dependence. Permuting individual samples would give a null that is far too "
                     "narrow.")}
