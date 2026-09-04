"""Tests for the wild cluster bootstrap-t, including the simulations that justify using it.

WHY THIS FILE CONTAINS SIMULATIONS AND NOT ONLY ASSERTIONS. The claim being made by edges.py is
that below forty clusters the cluster-robust variance estimator rejects a true null far more often
than the nominal five percent, and that the wild cluster bootstrap-t does not. That claim is the
entire justification for replacing one with the other, and it is checkable by simulation rather than
by citation. The functions ``null_rejection_table`` and ``power_table`` are the check; the tests
below call them with a small number of Monte Carlo replications so that the suite stays fast, and
the same functions are called with many more replications to produce the numbers in the written
report. If the bootstrap ever stops controlling size, these tests fail rather than the module
quietly going back to manufacturing resolution.

THE SIMULATION DESIGN MIRRORS THE REAL PROBLEM. The regressor is held CONSTANT within each cluster,
because that is what the real data looks like: a setting epoch is a stretch during which the
stimulation amplitude did not change, so every spectral sample in an epoch carries the same
amplitude. Within-cluster correlation is introduced by a cluster-level random shift in the outcome.
This combination — a between-cluster regressor plus a cluster-level error component — is the case in
which the effective sample size is the number of CLUSTERS rather than the number of observations,
and it is the case in which treating observations as independent, or trusting a sandwich estimator
built from a handful of clusters, does the most damage.
"""
import numpy as np
import pytest

from ClosedLoopDeployment import edges as E


# ------------------------------------------------------------------------------------------------
# A deliberately slow, explicit reference implementation.
#
# edges.py computes the bootstrap with vectorised algebra that exploits the fact that the restricted
# residuals are affine in the candidate coefficient value. That algebra is worth having because it
# makes full test inversion affordable, but it is also the kind of derivation that can be wrong in a
# way no eyeball catches. This reference does the textbook thing instead: it builds each bootstrap
# outcome vector one replication at a time, refits by least squares, and forms the cluster-robust
# sandwich explicitly. It is far too slow for production and exists only so the fast path can be
# checked against something written a different way.
# ------------------------------------------------------------------------------------------------
def _cr0_se_explicit(X, resid, groups, j):
    XtX_inv = np.linalg.inv(X.T @ X)
    meat = np.zeros((X.shape[1], X.shape[1]))
    for g in np.unique(groups):
        m = groups == g
        s = X[m].T @ resid[m]
        meat += np.outer(s, s)
    return float(np.sqrt((XtX_inv @ meat @ XtX_inv)[j, j]))


def reference_wcb_p(y, X, groups, *, j=1, null_value=0.0, per_observation=False, n_boot=None,
                    seed=0):
    """Textbook restricted wild cluster bootstrap-t, one explicit refit per replication.

    ``per_observation=True`` draws a Rademacher sign for every ROW instead of every cluster. That is
    the mistake the implementation must not make, and having it available here lets a test show that
    the two procedures give materially different answers, so a regression to per-observation weights
    would be caught by a failing comparison rather than by inspection.
    """
    y, X, groups = np.asarray(y, float), np.asarray(X, float), np.asarray(groups)
    uniq = np.unique(groups)
    G = uniq.size
    b_hat = np.linalg.lstsq(X, y, rcond=None)[0]
    se_hat = _cr0_se_explicit(X, y - X @ b_hat, groups, j)
    t_obs = (b_hat[j] - null_value) / se_hat

    keep = [i for i in range(X.shape[1]) if i != j]
    Xr = X[:, keep]
    yr = y - null_value * X[:, j]
    b_tilde = np.linalg.lstsq(Xr, yr, rcond=None)[0]
    u = yr - Xr @ b_tilde
    fitted = Xr @ b_tilde + null_value * X[:, j]

    if n_boot is None:
        W = (1.0 - 2.0 * ((np.arange(2 ** G)[:, None] >> np.arange(G)[None, :]) & 1)).astype(float)
        enumerated = True
    else:
        rng = np.random.default_rng(seed)
        W = rng.integers(0, 2, size=(n_boot, G)).astype(float) * 2.0 - 1.0
        enumerated = False

    rng_obs = np.random.default_rng(seed + 1)
    hits = 0
    for r in range(W.shape[0]):
        if per_observation:
            w = rng_obs.integers(0, 2, size=y.size).astype(float) * 2.0 - 1.0
        else:
            w = np.array([W[r, list(uniq).index(g)] for g in groups], float)
        ystar = fitted + w * u
        bstar = np.linalg.lstsq(X, ystar, rcond=None)[0]
        se = _cr0_se_explicit(X, ystar - X @ bstar, groups, j)
        if se > 0 and abs((bstar[j] - null_value) / se) >= abs(t_obs) - 1e-9 * max(1.0, abs(t_obs)):
            hits += 1
    if enumerated:
        return hits / W.shape[0]
    return (1 + hits) / (W.shape[0] + 1)


# ------------------------------------------------------------------------------------------------
# The simulation used both as a test and as the evidence in the written report.
# ------------------------------------------------------------------------------------------------
def simulate_clustered(G, *, beta=0.0, m=20, rho=0.5, seed=0):
    """One dataset: regressor constant within cluster, cluster-level shift in the outcome.

    ``rho`` is the share of the outcome's error variance carried by the cluster-level component, so
    ``rho = 0`` is independent errors and ``rho = 0.5`` means half the error variance is common to
    every observation in a cluster. Real spectral samples within one setting epoch are far more
    alike than this, so 0.5 is a mild rather than an extreme choice.
    """
    rng = np.random.default_rng(seed)
    x_cluster = rng.normal(size=G)
    x = np.repeat(x_cluster, m)
    a = np.repeat(rng.normal(scale=np.sqrt(rho), size=G), m)
    e = rng.normal(scale=np.sqrt(1.0 - rho), size=G * m)
    y = beta * x + a + e
    X = np.column_stack([np.ones(G * m), x])
    groups = np.repeat(np.arange(G), m)
    return y, X, groups


def _cr0_decision(y, X, groups, alpha=0.05):
    """The incumbent decision rule, exactly as edges.py made it before this change.

    Returns (rejects_by_interval, p_from_statsmodels). The first is the one that matters, because
    ``EdgeEstimate.resolved`` is defined by the interval excluding zero and the interval was
    ``estimate +/- 1.96 * se``. The statsmodels p-value is returned alongside because it uses a t
    distribution with G-1 degrees of freedom and a small-sample correction, so it is a slightly
    kinder version of the same estimator and it is fair to show both.
    """
    import statsmodels.api as sm
    res = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
    b, se = float(res.params[1]), float(res.bse[1])
    lo, hi = b - 1.96 * se, b + 1.96 * se
    return bool((lo > 0 and hi > 0) or (lo < 0 and hi < 0)), float(res.pvalues[1])


def null_rejection_table(cluster_counts=(5, 8, 15, 35), *, n_sim=200, beta=0.0, m=20, rho=0.5,
                         n_boot=999, alpha=0.05, seed=1000):
    """Empirical rejection rate at nominal ``alpha`` for CR0 and for the bootstrap-t.

    With ``beta = 0`` every rejection is a false one, so the column to read is how far each rate
    sits above ``alpha``. With ``beta`` non-zero the same numbers are power.
    """
    rows = []
    for G in cluster_counts:
        cr0_ci = cr0_p = boot_p = boot_ci = 0
        n_boot_unbounded = 0
        floor = None
        for s in range(n_sim):
            y, X, groups = simulate_clustered(G, beta=beta, m=m, rho=rho, seed=seed + s)
            rej_ci, p_sm = _cr0_decision(y, X, groups, alpha)
            cr0_ci += int(rej_ci)
            cr0_p += int(p_sm < alpha)
            bt = E.wild_cluster_bootstrap_t(y, X, groups, n_boot=n_boot, seed=s)
            floor = bt["p_resolution"]
            boot_p += int(bt["p"] < alpha)
            ci = E.wild_cluster_bootstrap_ci(y, X, groups, n_boot=n_boot, seed=s, alpha=alpha)
            if ci.get("ci_unbounded"):
                n_boot_unbounded += 1
            elif ci.get("ci") is not None:
                lo, hi = ci["ci"]
                boot_ci += int((lo > 0 and hi > 0) or (lo < 0 and hi < 0))
        rows.append({"n_clusters": G, "n_sim": n_sim,
                     "cr0_interval_rejects": cr0_ci / n_sim,
                     "cr0_pvalue_rejects": cr0_p / n_sim,
                     "bootstrap_p_rejects": boot_p / n_sim,
                     "bootstrap_ci_excludes_zero": boot_ci / n_sim,
                     "bootstrap_ci_unbounded": n_boot_unbounded / n_sim,
                     "bootstrap_p_floor": floor})
    return rows


# ------------------------------------------------------------------------------------------------
# Structure: the weights, and the discreteness of the weight space.
# ------------------------------------------------------------------------------------------------
def test_rademacher_weights_have_one_column_per_cluster_not_one_per_observation():
    """The single most important structural property. A sign per observation would destroy the
    within-cluster dependence the whole method exists to respect, and would silently reduce this to
    an ordinary residual bootstrap whose intervals are as narrow as the CR0 ones being replaced."""
    W, method, n_vec = E._rademacher_weights(6, 999, 0)
    assert W.shape[1] == 6, "one column per cluster"
    assert set(np.unique(W)) == {-1.0, 1.0}, "Rademacher weights take only +1 and -1"
    assert method == "enumerated" and n_vec == 64
    assert np.unique(W, axis=0).shape[0] == 64, "every sign vector appears exactly once"
    W2, method2, n_vec2 = E._rademacher_weights(20, 500, 0)
    assert W2.shape == (500, 20) and method2 == "sampled" and n_vec2 == 2 ** 20
    # a drawn weight matrix must be balanced in expectation rather than degenerate
    assert abs(W2.mean()) < 0.1


def test_the_bootstrap_matches_an_independent_textbook_implementation():
    """The fast path in edges.py exploits an algebraic identity to avoid refitting per replication.
    This checks it against an explicit loop that refits every time and builds the sandwich by hand,
    written a different way so that a mistake in the derivation shows up as a disagreement."""
    y, X, groups = simulate_clustered(6, beta=0.4, m=10, rho=0.5, seed=7)
    fast = E.wild_cluster_bootstrap_t(y, X, groups)
    slow = reference_wcb_p(y, X, groups)
    assert fast["draw"] == "enumerated"
    assert fast["p"] == pytest.approx(slow, abs=1e-12), (
        "the vectorised bootstrap must reproduce the explicit one exactly when both enumerate")


def test_each_clusters_sign_is_applied_to_every_row_of_that_cluster():
    """Checks the expansion itself rather than its consequences.

    The bootstrap coefficient must be a function of the G cluster signs alone, so that two weight
    patterns agreeing on every cluster sign but disagreeing about which rows inside a cluster got
    which sign cannot give different answers. Here the module's stored bootstrap coefficients are
    reproduced one sign vector at a time by expanding each sign across its cluster's rows by hand,
    and are then shown to differ from what a within-cluster mixture of signs would give.

    A NOTE ON WHY THIS IS TESTED STRUCTURALLY AND NOT BY REJECTION RATE. The obvious test would be
    to show that per-observation weights over-reject a true null. Measured on this simulation design
    they do not by much: at eight clusters with half the error variance carried at the cluster level,
    three hundred replications gave 0.037 for per-cluster weights and 0.040 for per-observation. The
    reason is that averaging m independent signs inside a cluster leaves a cluster-level weight that
    is still mean-zero, merely smaller by a factor of about the square root of the cluster size, and
    a studentised statistic divides that factor out again. So the per-observation mistake is not
    self-announcing through size, which is exactly why it has to be caught structurally: it produces
    a different procedure and different numbers, and nothing in the output looks wrong.
    """
    y, X, groups = simulate_clustered(5, beta=0.3, m=4, rho=0.6, seed=17)
    plan = E._BootstrapPlan(y, X, groups, coef_index=1, n_boot=999, seed=0, impose_null=True)
    assert plan.available and plan.method == "enumerated" and plan.n_boot == 32

    # rebuild the restricted residuals and the OLS operator independently of the plan
    Xs, ys, gs = X[np.argsort(groups, kind="stable")], y[np.argsort(groups, kind="stable")], np.sort(groups)
    Xr = Xs[:, [0]]
    u0 = ys - Xr @ np.linalg.pinv(Xr) @ ys
    Aj = (np.linalg.inv(Xs.T @ Xs) @ Xs.T)[1]
    W, _, _ = E._rademacher_weights(5, 999, 0)
    uniq = list(np.unique(gs))
    for r in range(W.shape[0]):
        per_cluster = np.array([W[r, uniq.index(g)] for g in gs], float)
        assert plan.num0[r] == pytest.approx(float(Aj @ (per_cluster * u0)), abs=1e-12), (
            f"sign vector {r} was not expanded one sign per cluster")

    # a pattern with the same cluster signs but mixed within one cluster must give something else
    mixed = np.array([W[3, uniq.index(g)] for g in gs], float)
    mixed[0] *= -1.0
    assert abs(float(Aj @ (mixed * u0)) - plan.num0[3]) > 1e-6, (
        "if a within-cluster sign flip changed nothing, this test would not be detecting anything")

    # and the p-value the module reports is the per-cluster one, checked against the slow reference
    assert E.wild_cluster_bootstrap_t(y, X, groups)["p"] == pytest.approx(
        reference_wcb_p(y, X, groups), abs=1e-12)
    assert reference_wcb_p(y, X, groups, n_boot=200, seed=3) != pytest.approx(
        reference_wcb_p(y, X, groups, n_boot=200, seed=3, per_observation=True), abs=1e-6), (
        "the two procedures are different procedures and must not be confused for one another")


def test_the_weight_space_is_enumerated_and_its_discreteness_is_reported_below_twelve_clusters():
    """With G clusters there are only 2**G distinct sign vectors, so the p-value is coarse and the
    reader has to be told rather than left to infer it from a suspiciously round number."""
    for G in (5, 8, 12):
        y, X, groups = simulate_clustered(G, beta=0.0, m=12, rho=0.5, seed=G)
        out = E.wild_cluster_bootstrap_t(y, X, groups)
        assert out["enumerable"] is True
        assert out["n_sign_vectors"] == 2 ** G
        assert out["draw"] == "enumerated"
        assert out["n_boot"] == 2 ** G, "every sign vector used, not 999 samples of them"
        assert out["p_resolution"] == pytest.approx(2.0 / 2 ** G)
        assert out["p"] >= out["p_resolution"] - 1e-12
        # the p-value must be an exact multiple of the enumeration grid
        assert (out["p"] * 2 ** G) == pytest.approx(round(out["p"] * 2 ** G), abs=1e-9)
    # above the enumeration limit the resolution is the conventional 1 / (n_boot + 1)
    y, X, groups = simulate_clustered(20, beta=0.0, m=10, rho=0.5, seed=2)
    out = E.wild_cluster_bootstrap_t(y, X, groups, n_boot=499)
    assert out["enumerable"] is False and out["draw"] == "sampled"
    assert out["p_resolution"] == pytest.approx(1 / 500)


def test_five_clusters_cannot_reject_at_five_percent_and_says_so_instead_of_pretending():
    """A known and deliberate property of Rademacher weights (Cameron, Gelbach and Miller 2008): at
    five clusters the smallest attainable p-value is 2/32 = 0.0625, which is above 0.05. No effect,
    however large, can be called significant at the five percent level. The right behaviour is to
    report an unbounded interval with the reason, not to widen the level or switch back to CR0."""
    y, X, groups = simulate_clustered(5, beta=8.0, m=40, rho=0.3, seed=5)
    out = E.wild_cluster_bootstrap_t(y, X, groups)
    assert out["p_resolution"] == pytest.approx(0.0625)
    assert out["p"] >= 0.0625 - 1e-12, "no p-value below the floor may be reported"
    ci = E.wild_cluster_bootstrap_ci(y, X, groups)
    assert ci["ci"] is None and ci["ci_unbounded"] is True
    assert "cannot produce a p-value below" in ci["reason"]
    # and the CR0 estimator on the same data is confident, which is the point
    rej, _ = _cr0_decision(y, X, groups)
    assert rej is True, "CR0 resolves this while the bootstrap correctly cannot"


def test_imposing_the_null_is_the_default_and_the_unrestricted_variant_is_recorded():
    y, X, groups = simulate_clustered(8, beta=0.5, m=15, rho=0.5, seed=21)
    d = E.wild_cluster_bootstrap_t(y, X, groups)
    u = E.wild_cluster_bootstrap_t(y, X, groups, impose_null=False)
    assert d["impose_null"] is True and u["impose_null"] is False
    assert d["p"] != u["p"], "the two variants build different distributions and must not coincide"


def test_the_bootstrap_is_reproducible_and_deterministic_when_enumerated():
    y, X, groups = simulate_clustered(9, beta=0.3, m=10, rho=0.4, seed=31)
    a = E.wild_cluster_bootstrap_t(y, X, groups, seed=0)
    b = E.wild_cluster_bootstrap_t(y, X, groups, seed=12345)
    assert a["p"] == b["p"], "an enumerated weight space cannot depend on the seed"
    y2, X2, g2 = simulate_clustered(25, beta=0.3, m=10, rho=0.4, seed=31)
    assert (E.wild_cluster_bootstrap_t(y2, X2, g2, seed=4)["p"]
            == E.wild_cluster_bootstrap_t(y2, X2, g2, seed=4)["p"]), "same seed, same answer"


# ------------------------------------------------------------------------------------------------
# The interval, obtained by inverting the test rather than by a normal approximation.
# ------------------------------------------------------------------------------------------------
def test_the_interval_is_the_set_of_values_the_bootstrap_does_not_reject():
    """The defining property of an inverted-test interval: its endpoints are where the bootstrap
    p-value crosses alpha, and a value just inside is accepted while a value just outside is not.
    Checked by evaluating the p-value at the reported endpoints rather than by trusting the search.
    """
    y, X, groups = simulate_clustered(10, beta=1.0, m=20, rho=0.5, seed=41)
    out = E.wild_cluster_bootstrap_ci(y, X, groups, alpha=0.05)
    lo, hi = out["ci"]
    assert lo < out["estimate"] < hi
    width = hi - lo
    for b0, expect_accepted in ((lo + 1e-4 * width, True), (hi - 1e-4 * width, True),
                                (lo - 1e-3 * width, False), (hi + 1e-3 * width, False)):
        p = E.wild_cluster_bootstrap_t(y, X, groups, null_value=b0)["p"]
        assert (p > 0.05) is expect_accepted, f"at b0 = {b0} the bootstrap p was {p}"


def test_the_interval_and_the_p_value_agree_about_zero():
    """Reporting a bootstrap p-value beside a CR0 interval was the failure mode to avoid: a reader
    would find the interval excluding zero while the p-value did not. Because both now come from the
    same inverted test they cannot disagree, and this is the test that would catch a regression to
    mixing the two."""
    for seed in range(12):
        y, X, groups = simulate_clustered(9, beta=0.6, m=15, rho=0.5, seed=seed)
        p = E.wild_cluster_bootstrap_t(y, X, groups)["p"]
        ci = E.wild_cluster_bootstrap_ci(y, X, groups, alpha=0.05)
        if ci["ci"] is None:
            assert p >= 0.05
            continue
        lo, hi = ci["ci"]
        excludes_zero = (lo > 0 and hi > 0) or (lo < 0 and hi < 0)
        assert excludes_zero == (p < 0.05), f"seed {seed}: p = {p}, ci = {ci['ci']}"


def test_the_bootstrap_interval_is_wider_than_the_cr0_interval_at_few_clusters():
    """Not a definition but a measurable consequence, and the reason the change raises rigor: at
    these cluster counts the CR0 interval is too narrow, so the valid interval must generally be
    wider. Averaged over datasets rather than asserted on one, because either interval can be the
    narrower on a single draw."""
    import statsmodels.api as sm
    ratios = []
    for seed in range(15):
        y, X, groups = simulate_clustered(8, beta=0.0, m=20, rho=0.5, seed=200 + seed)
        res = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
        cr0_width = 2 * 1.96 * float(res.bse[1])
        ci = E.wild_cluster_bootstrap_ci(y, X, groups)
        if ci["ci"] is not None:
            ratios.append((ci["ci"][1] - ci["ci"][0]) / cr0_width)
    assert len(ratios) >= 10, "most datasets at eight clusters should still give a bounded interval"
    assert np.median(ratios) > 1.2, f"median width ratio was {np.median(ratios):.2f}"


# ------------------------------------------------------------------------------------------------
# Size and power. These are the numbers that justify the change.
# ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("G,min_cr0_rate", [(8, 0.15), (15, 0.09)])
def test_cr0_over_rejects_a_true_null_and_the_bootstrap_does_not(G, min_cr0_rate):
    """The evidence for the whole change, run at a small number of Monte Carlo replications so the
    suite stays fast. The full-size version of this simulation is in the written report.

    The required CR0 rate falls as the number of clusters rises because that is the actual shape of
    the problem: the cluster-robust sandwich is consistent in the number of clusters, so its
    over-rejection is worst when clusters are fewest and fades as they accumulate. That fading is
    the reason MIN_RELIABLE_CLUSTERS is a threshold at all rather than a blanket preference for the
    bootstrap. Measured here at nominal five percent, CR0 rejects a true null about a fifth of the
    time at eight clusters and about a seventh at fifteen.

    The thresholds are otherwise loose on purpose. With 120 replications the Monte Carlo standard
    error on a rate near 0.05 is about 0.02, so the bootstrap is allowed anything up to 0.12 — a
    band wide enough that the test is about the qualitative fact rather than the third decimal
    place, and narrow enough that losing size control would fail it.
    """
    rows = null_rejection_table((G,), n_sim=120, n_boot=399, m=20, rho=0.5, seed=9000)
    r = rows[0]
    assert r["cr0_interval_rejects"] > min_cr0_rate, (
        f"CR0 rejected a true null {r['cr0_interval_rejects']:.1%} of the time at {G} clusters; "
        "if this ever falls near nominal the premise of the change needs re-examining")
    assert r["bootstrap_p_rejects"] <= 0.12, (
        f"the bootstrap rejected a true null {r['bootstrap_p_rejects']:.1%} of the time at "
        f"{G} clusters, which is not size control")
    assert r["bootstrap_p_rejects"] < r["cr0_interval_rejects"]


def test_the_bootstrap_still_detects_a_real_effect():
    """The other half of the argument. A method that never rejects controls size trivially and is
    useless; this shows the bootstrap keeps most of the power against an effect large relative to
    the between-cluster noise, so the change has not been bought by making everything
    non-significant."""
    rows = null_rejection_table((15,), n_sim=120, n_boot=399, beta=1.2, m=20, rho=0.5, seed=7000)
    r = rows[0]
    assert r["bootstrap_p_rejects"] > 0.7, (
        f"power was only {r['bootstrap_p_rejects']:.1%} against a clear effect")
    assert r["bootstrap_ci_excludes_zero"] == pytest.approx(r["bootstrap_p_rejects"], abs=0.02)


# ------------------------------------------------------------------------------------------------
# The switch inside the three edges.
# ------------------------------------------------------------------------------------------------
def _toy_table(n_epochs=6, per_epoch=5, slope=-2.0, noise=0.2, seed=0):
    import pandas as pd
    rng = np.random.default_rng(seed)
    rows = []
    for e in range(n_epochs):
        amp = 1.0 + e * 0.5
        for _ in range(per_epoch):
            rows.append({"t": float(e), "channel": "CH", "setting_epoch": e, "center_hz": 20.5,
                         "amp_mA_Left": amp,
                         "power_linear": 10.0 + slope * amp + rng.normal(0, noise),
                         "nrs": 5.0 + 0.5 * amp + rng.normal(0, noise),
                         "report_id": f"r{e}"})
    return pd.DataFrame(rows)


def test_below_the_threshold_the_edge_reports_bootstrap_inference_and_names_the_estimator():
    e = E.actuation_edge(_toy_table(n_epochs=8), channel="CH", center_hz=20.5)
    assert e.n_clusters == 8
    assert "WILD CLUSTER BOOTSTRAP-t" in e.note and "not from CR0" in e.note
    assert "Cameron, Gelbach and Miller 2008" in e.note
    assert str(E.MIN_RELIABLE_CLUSTERS) in e.note, "the note must name the cluster-count threshold"
    # the reported p must be exactly what the bootstrap returns for the same data, not a CR0 p
    T = _toy_table(n_epochs=8)
    X = np.column_stack([np.ones(len(T)), T.amp_mA_Left.to_numpy(float)])
    boot = E.wild_cluster_bootstrap_t(T.power_linear.to_numpy(float), X,
                                      T.setting_epoch.to_numpy())
    assert e.p == pytest.approx(boot["p"])
    assert e.p >= 2.0 / 2 ** 8, "the reported p cannot sit below the weight space's floor"


def test_at_or_above_the_threshold_the_edge_stays_on_cr0_and_says_so():
    e = E.actuation_edge(_toy_table(n_epochs=E.MIN_RELIABLE_CLUSTERS, per_epoch=3),
                         channel="CH", center_hz=20.5)
    assert e.n_clusters == E.MIN_RELIABLE_CLUSTERS
    assert "CR0 cluster-robust" in e.note and "WILD CLUSTER BOOTSTRAP" not in e.note
    assert e.ci is not None and e.resolved


def test_a_few_cluster_edge_is_reported_rather_than_disqualified():
    """The behaviour this change was made for. Four setting epochs used to mean the estimate was
    flagged unreliable and there was nothing further to say. It now carries a point estimate, the
    cluster count, and inference that is valid at four clusters — which at four clusters means an
    unbounded interval, stated as such."""
    e = E.actuation_edge(_toy_table(n_epochs=4, per_epoch=8), channel="CH", center_hz=20.5)
    assert e.estimate is not None and e.n_clusters == 4
    assert e.p == pytest.approx(2.0 / 16), "the enumerated floor at four clusters is 2/16"
    assert e.ci is None and not e.resolved
    assert "UNBOUNDED" in e.note
    assert "FEW CLUSTERS" in e.note, "the historical marker stays, as information"


def test_the_state_edge_and_therapy_edge_switch_on_the_same_condition():
    import pandas as pd
    e2 = E.state_edge(_toy_table(n_epochs=9), channel="CH", center_hz=20.5)
    assert e2.n_clusters == 9 and "WILD CLUSTER BOOTSTRAP-t" in e2.note
    dm = pd.DataFrame({"epoch": np.arange(10), "amp_mA_Left": np.linspace(1, 4, 10),
                       "nrs": 6 - 0.8 * np.linspace(1, 4, 10)
                              + np.random.default_rng(0).normal(0, 0.15, 10)})
    e3 = E.therapy_edge(dm)
    assert e3.n_clusters == 10 and "WILD CLUSTER BOOTSTRAP-t" in e3.note
    assert e3.p >= 2.0 / 2 ** 10


def test_the_edge_refuses_to_fall_back_to_cr0_when_the_bootstrap_cannot_be_formed():
    """If the bootstrap is unavailable the edge must report no interval rather than quietly
    substituting the CR0 one, because substituting it would put the too-narrow interval back exactly
    where the valid one was supposed to go."""
    y = np.arange(10.0)
    X = np.column_stack([np.ones(10), np.zeros(10)])       # rank deficient on purpose
    p, ci, note, raw = E._small_sample_inference(y, X, np.repeat(np.arange(5), 2))
    assert p is None and ci is None
    assert "INFERENCE UNAVAILABLE" in note and "not reported in its place" in note
    assert raw["available"] is False
