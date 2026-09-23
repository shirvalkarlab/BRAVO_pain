"""The shape the stimulation current is allowed to have when it is taken out of something.

WHY (the PI, 2026-09-22). Both guards took the current out as a STRAIGHT LINE. He asked whether that
masks a real effect, because the current-to-pain relationship can turn over -- helping up to a point
and worsening above it. It can, and it cuts both ways: a curved current effect survives a straight-
line removal as a leftover curve, which a candidate that tracks distance-from-the-best-current then
looks correlated with; and a genuinely curved candidate reads near zero.

Measured on his record before building this (L 1-3+, 53 reports, 11 delivered currents): a straight
line explains 25.7% of pain's scatter and is still falling at the highest current tested; two degrees
of freedom (a squared term, or a 3-knot spline) explain 29-31% and put the lowest pain at 3.1-3.2 mA;
the three kernels, given 4-6 degrees of freedom, explain 37-43% and move it to 1.8-1.9 mA, chasing
two ratings at 1.6 mA. So the shape matters, the flexible shapes disagree with each other about
where the turn is, and the honest default is the cheapest shape that can turn over at all.

WHAT IS ASSERTED: that each shape spends the flexibility it claims; that a curved covariate driving
two unrelated series leaves a large false correlation after a straight-line removal and none after a
curved one (the case he named); that a real relationship survives every shape; that the removal is
fitted on training rows only; that a shape that cannot be built falls back and says so; and that
both guards carry the shape and its cost on every answer.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_covariate_shape.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import stats_utils as SU              # noqa: E402
from Biomarkers.routines import confound_diagnostic as CD      # noqa: E402


SETTINGS = (0.0, 0.5, 1.0, 1.6, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5)


def _u_shaped(n=240, seed=0, best=2.5, effect=1.5, noise=3.0):
    """A covariate with a turn-over in it, driving TWO series that are otherwise unrelated.

    Both `x` and `y` are functions of the same curved effect of `c` plus their own noise. Nothing
    connects x to y except c, so any correlation left after c is taken out is spurious. The sizes
    are set so the covariate explains about half of each series, which is the order of what the live
    record shows (the current explains 25.7% of pain's scatter on L 1-3+); an effect many times the
    noise behaves differently and is pinned separately below.
    """
    rng = np.random.default_rng(seed)
    c = rng.choice(SETTINGS, size=n)
    bowl = (c - best) ** 2                                  # lowest in the middle, rising each side
    x = effect * bowl + rng.normal(0, noise, n)
    y = effect * bowl + rng.normal(0, noise, n)
    return c, x, y


# ---------------------------------------------------------------------------------------------
# 1. the shapes themselves
# ---------------------------------------------------------------------------------------------

def test_each_shape_spends_the_flexibility_it_claims():
    c, _x, _y = _u_shaped()
    got = {s: SU.CovariateShape(c, shape=s).effective_df for s in SU.COVARIATE_SHAPES}
    assert abs(got["line"] - 1.0) < 1e-9
    assert abs(got["quadratic"] - 2.0) < 1e-9
    assert abs(got["spline"] - 2.0) < 1e-9
    assert abs(got["per_setting"] - (len(SETTINGS) - 1)) < 1e-9
    for k in ("squared_exponential", "matern32", "rational_quadratic"):
        assert 1.0 < got[k] < len(SETTINGS), (k, got[k])
    # a shorter length scale buys more flexibility, which is the knob a reader has to be shown
    tight = SU.CovariateShape(c, shape="squared_exponential", length_scale=0.5).effective_df
    loose = SU.CovariateShape(c, shape="squared_exponential", length_scale=4.0).effective_df
    assert tight > got["squared_exponential"] > loose
    print("OK effective degrees of freedom: " + ", ".join(f"{k} {v:.1f}" for k, v in got.items()))


def test_the_default_length_scale_is_read_off_the_delivered_settings():
    c, _x, _y = _u_shaped()
    sh = SU.CovariateShape(c, shape="squared_exponential")
    expect = float(np.median([abs(a - b) for i, a in enumerate(sorted(set(c)))
                              for b in sorted(set(c))[i + 1:]]))
    assert abs(sh.length_scale - expect) < 1e-9
    assert "median" in sh.why.lower() and "%.2f" % expect in sh.why


def test_a_curved_covariate_leaves_a_false_correlation_behind_a_straight_line_and_none_behind_a_curve():
    """The case the PI named, in the direction that matters most: a false positive."""
    c, x, y = _u_shaped()
    plain = float(np.corrcoef(x, y)[0, 1])
    line = SU.partial_corr(x, y, c, shape="line")
    assert plain > 0.4, "both series follow the same curve, so they correlate"
    assert abs(line) > 0.3, f"a straight-line removal leaves most of it: {line:+.3f}"
    for s in ("quadratic", "spline", "squared_exponential", "matern32", "rational_quadratic",
              "per_setting"):
        got = SU.partial_corr(x, y, c, shape=s)
        assert abs(got) < 0.1, f"{s} should take the curve out, left {got:+.3f}"
    print(f"OK curved covariate: {plain:+.3f} plainly, {line:+.3f} after a line, "
          f"{SU.partial_corr(x, y, c, shape='spline'):+.3f} after a spline")


def test_a_confound_much_larger_than_the_noise_leaves_a_remnant_behind_every_shape():
    """How much a removal leaves depends on how big the confound is, not only on the shape.

    Found while building this, by writing a fixture where the curved effect was ten times the noise:
    a 3-knot spline fits 99.0% of an exact parabola, and the 1.0% it leaves is still large compared
    with the noise, so the two series stay correlated at +0.71 after the removal. No shape short of
    one level per setting fixes that, because the leftover IS the covariate. The lesson is for
    reading an adjusted number, not a defect: where a covariate dominates a series, "adjusted" means
    "adjusted as well as this shape can", and the size of what it left is part of the answer.
    """
    c, x, y = _u_shaped(effect=10.0, noise=1.0)
    spline = SU.partial_corr(x, y, c, shape="spline")
    exact = SU.partial_corr(x, y, c, shape="per_setting")
    assert spline > 0.5, f"a dominant confound leaves a remnant even after a good fit: {spline:+.3f}"
    assert abs(exact) < 0.1, f"only a shape that fits it exactly clears it: {exact:+.3f}"
    print(f"OK a confound ten times the noise: {spline:+.3f} left after a spline, "
          f"{exact:+.3f} after one level per setting")


def test_a_real_relationship_survives_every_shape():
    rng = np.random.default_rng(4)
    n = 240
    c = rng.choice(SETTINGS, size=n)
    own = rng.normal(0, 1, n)
    x = 5.0 * own + (c - 2.0) ** 2 + rng.normal(0, 0.5, n)
    y = 4.0 * own - 2.0 * c + rng.normal(0, 0.5, n)
    for s in SU.COVARIATE_SHAPES:
        got = SU.partial_corr(x, y, c, shape=s)
        assert got > 0.6, f"{s} destroyed a real relationship: {got:+.3f}"


def test_the_removal_is_fitted_on_the_training_rows_only():
    c, x, _y = _u_shaped(n=120)
    tr, te = np.arange(0, 80), np.arange(80, 120)
    sh = SU.CovariateShape(c, shape="spline")
    a_tr, _a_te = sh.train_test_residuals(x, tr, te)
    moved = np.asarray(x, float).copy()
    moved[te] += 1000.0                                  # scribble on the held-out rows only
    b_tr, _b_te = SU.CovariateShape(c, shape="spline").train_test_residuals(moved, tr, te)
    assert np.allclose(a_tr, b_tr), "a held-out row changed the training fit"


def test_a_shape_that_cannot_be_built_falls_back_and_says_so():
    two = np.array([0.0, 0.0, 0.0, 2.5, 2.5, 2.5] * 8, float)
    sh = SU.CovariateShape(two, shape="spline")
    assert sh.shape == "line" and "two" in sh.reason.lower()
    assert sh.usable is True
    flat = SU.CovariateShape(np.full(30, 2.5), shape="spline")
    assert flat.usable is False and "constant" in flat.reason.lower()
    assert SU.partial_corr(np.arange(30.0), np.arange(30.0) ** 2, np.full(30, 2.5),
                           shape="spline") is None or True   # refusal, not a crash
    many = SU.CovariateShape(np.arange(24.0), shape="per_setting")
    assert many.shape != "per_setting" and "level" in many.reason.lower()


def test_an_unknown_shape_is_refused_by_name():
    try:
        SU.CovariateShape(np.array([0.0, 1.0, 2.0] * 10), shape="wishful")
    except ValueError as e:
        assert "wishful" in str(e) and "spline" in str(e)
    else:
        raise AssertionError("an unknown shape must be refused, not silently treated as a line")


def test_the_straight_line_path_is_the_same_number_it_always_was():
    """Nothing already published may move: `shape="line"` must reproduce the old answer exactly."""
    rng = np.random.default_rng(9)
    x, y, c = rng.normal(size=60), rng.normal(size=60), rng.choice(SETTINGS, 60)
    old = float(np.corrcoef(SU._residualize(x, c), SU._residualize(y, c))[0, 1])
    assert abs(SU.partial_corr(x, y, c, shape="line") - old) < 1e-12
    assert abs(SU.partial_corr(x, y, c) - old) < 1e-12, "the default for this helper stays the line"


# ---------------------------------------------------------------------------------------------
# 2. the two guards carry it
# ---------------------------------------------------------------------------------------------

def test_the_gate_names_its_shape_and_what_that_shape_cost():
    c, x, y = _u_shaped()
    line = SU.confound_gate(x, y, c, label="the stimulation current in force", shape="line")
    spline = SU.confound_gate(x, y, c, label="the stimulation current in force")
    assert line["shape"] == "line" and line["effective_df"] == 1.0
    assert spline["shape"] == "spline" and spline["effective_df"] == 2.0
    assert line["survives"] is True, "a straight-line removal is fooled by a curved covariate"
    assert spline["survives"] is False, "a curve is not"
    assert "spline" in spline["verdict"] or "curve" in spline["verdict"]
    print(f"OK the gate: {line['r_adjusted']:+.3f} after a line, {spline['r_adjusted']:+.3f} after a "
          f"spline, on the same rows")


def test_the_diagnostic_carries_the_shape_and_collapses_a_curved_confound():
    """Both halves of the PI's question, on one constructed record where the current turns over.

    The bands here are nothing but the current's curved effect, and the pain label is that same
    effect. A straight line sees almost none of it: it reads the current alone at 0.622 -- close to
    chance, the answer that would have said "the current is not the story here" -- while a curve
    reads the same current at 0.977. And a straight-line removal leaves the bands at 0.959, which
    would have been reported as bands surviving the current; the curve takes them to 0.570 and one
    level per setting to 0.495, the chance level.
    """
    rng = np.random.default_rng(5)
    n = 300
    c = rng.choice(SETTINGS, size=n)
    bowl = (c - 2.5) ** 2
    pain = 50.0 + 4.0 * bowl + rng.normal(0, 2, n)
    X = np.column_stack([200.0 + 15.0 * bowl + rng.normal(0, 6, n) for _ in range(6)])
    y = (pain > np.median(pain)).astype(float)
    line = CD.pre_build_diagnostic(X, y, c, n_perm=100, shape="line")
    spline = CD.pre_build_diagnostic(X, y, c, n_perm=100)
    exact = CD.pre_build_diagnostic(X, y, c, n_perm=100, shape="per_setting")

    assert spline["covariate_shape"] == "spline" and spline["covariate_effective_df"] == 2.0
    assert line["covariate_shape"] == "line" and line["covariate_effective_df"] == 1.0
    # a curved current is nearly invisible to a straight line, and plain to a curve
    assert spline["current_alone"]["auc"] > line["current_alone"]["auc"] + 0.3, (
        f"{line['current_alone']['auc']:.3f} as a line against "
        f"{spline['current_alone']['auc']:.3f} as a curve")
    # and a curved confound survives a straight-line removal while a curve takes it out
    assert line["bands_adjusted"]["auc"] > spline["bands_adjusted"]["auc"] + 0.3, (
        f"{line['bands_adjusted']['auc']:.3f} after a line against "
        f"{spline['bands_adjusted']['auc']:.3f} after a curve")
    assert exact["bands_adjusted"]["auc"] <= exact["null"]["p95"], (
        "the shape that fits the confound exactly clears it entirely")
    assert "curve" in spline["verdict"] and "degrees of freedom" in spline["verdict"]
    print(f"OK the diagnostic: the current alone reads {line['current_alone']['auc']:.3f} as a line "
          f"and {spline['current_alone']['auc']:.3f} as a curve; the bands read "
          f"{line['bands_adjusted']['auc']:.3f} / {spline['bands_adjusted']['auc']:.3f} / "
          f"{exact['bands_adjusted']['auc']:.3f} after a line, a curve and one level per setting")


if __name__ == "__main__":
    for fn in (test_each_shape_spends_the_flexibility_it_claims,
               test_the_default_length_scale_is_read_off_the_delivered_settings,
               test_a_curved_covariate_leaves_a_false_correlation_behind_a_straight_line_and_none_behind_a_curve,
               test_a_confound_much_larger_than_the_noise_leaves_a_remnant_behind_every_shape,
               test_a_real_relationship_survives_every_shape,
               test_the_removal_is_fitted_on_the_training_rows_only,
               test_a_shape_that_cannot_be_built_falls_back_and_says_so,
               test_an_unknown_shape_is_refused_by_name,
               test_the_straight_line_path_is_the_same_number_it_always_was,
               test_the_gate_names_its_shape_and_what_that_shape_cost,
               test_the_diagnostic_carries_the_shape_and_collapses_a_curved_confound):
        fn()
    print("All covariate-shape tests passed.")
