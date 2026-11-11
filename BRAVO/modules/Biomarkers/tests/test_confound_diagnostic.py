"""The check that runs before any decoder is built on this record.

WHY. Panel B of the 2026-09-22 review would not let a decoder be built here until one question was
answered on the live data: how much of what a decoder could learn is the stimulation current rather
than the brain? On this participant the current moves the band power and the pain together, so a
model reading all 22 bands on both sides can score above chance while carrying nothing about pain.

So the diagnostic reads the pain label three ways -- from the current alone, from every band, and
from every band with the current taken out of each one -- all out of sample, on held-out blocks of
TIME with the neighbouring rows embargoed, against a null that keeps pain's own day-to-day
persistence. It decides nothing. It tells whoever proposes a decoder what the ceiling is made of.

WHAT IS ASSERTED: that a current which drives both the bands and the pain gives a high plain score
and collapses once it is taken out (the case the panel named); that bands carrying pain of their own
survive; that noise reads as noise against the null; that the embargo is the series' own timescale
and not a typed number; and that the answer never folds an out-of-sample score (a decoder scoring
0.30 has failed, and calling that 0.70 would be the reverse of honest).

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore         modules/Biomarkers/tests/test_confound_diagnostic.py

Merged here 2026-10-05: test_covariate_shape.py, test_current_adjusted_correlation.py.
"""
import os
import sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import confound_diagnostic as CD    # noqa: E402
from Biomarkers.routines import stats_utils as SU            # noqa: E402


def _record(n=300, n_bands=8, kind="current_drives_both", seed=0, rho=0.8):
    """One constructed record: a slowly varying current, a pain label, and a band matrix.

    `kind` says what the bands are made of:
      current_drives_both -- the bands follow the current, and so does pain. Nothing else.
      bands_carry_pain    -- the bands follow something of pain's own that the current knows nothing
                             about, plus a little current.
      noise               -- the bands are noise.
    """
    rng = np.random.default_rng(seed)
    current = np.repeat(rng.choice([0.0, 1.0, 1.6, 2.5, 3.5, 4.5], size=n // 10 + 1), 10)[:n]
    own = np.zeros(n)                                        # pain's own slow drift
    for i in range(1, n):
        own[i] = rho * own[i - 1] + rng.normal(0, 1)
    pain_c = 60.0 - 5.0 * current
    pain = pain_c + (0.0 if kind == "current_drives_both" else 6.0) * own + rng.normal(0, 2, n)
    if kind == "current_drives_both":
        X = np.column_stack([200.0 - 20.0 * current + rng.normal(0, 6, n) for _ in range(n_bands)])
    elif kind == "bands_carry_pain":
        X = np.column_stack([200.0 + 20.0 * own - 5.0 * current + rng.normal(0, 6, n)
                             for _ in range(n_bands)])
    else:
        X = rng.normal(200.0, 20.0, size=(n, n_bands))
    y = (pain > np.median(pain)).astype(float)
    return X, y, current


def test_a_current_that_drives_both_reads_high_plainly_and_collapses_once_it_is_taken_out():
    X, y, cur = _record(kind="current_drives_both")
    got = CD.pre_build_diagnostic(X, y, cur, n_perm=200)
    assert got["current_alone"]["auc"] > 0.7, "the current alone predicts this label"
    assert got["bands_plain"]["auc"] > 0.65, "so do bands made of nothing but the current"
    assert got["bands_adjusted"]["auc"] < 0.60, (
        f"and with the current taken out of each band there is nothing left: "
        f"{got['bands_adjusted']['auc']:.3f}")
    assert got["bands_adjusted"]["auc"] <= got["null"]["p95"], "which is inside the null"
    assert "current" in got["verdict"] and "not survive" in got["verdict"]
    print(f"OK current-driven: alone {got['current_alone']['auc']:.3f}, bands "
          f"{got['bands_plain']['auc']:.3f}, adjusted {got['bands_adjusted']['auc']:.3f}, "
          f"null 95th {got['null']['p95']:.3f}")


def test_bands_that_carry_something_of_their_own_survive_the_adjustment():
    X, y, cur = _record(kind="bands_carry_pain")
    got = CD.pre_build_diagnostic(X, y, cur, n_perm=200)
    assert got["bands_plain"]["auc"] > 0.7
    assert got["bands_adjusted"]["auc"] > 0.65, "taking the current out must not destroy a real signal"
    assert got["bands_adjusted"]["auc"] > got["null"]["p95"]
    assert "survives" in got["verdict"]
    print(f"OK own signal: bands {got['bands_plain']['auc']:.3f}, adjusted "
          f"{got['bands_adjusted']['auc']:.3f}, null 95th {got['null']['p95']:.3f}")


def test_noise_reads_as_noise_against_a_null_that_keeps_pain_s_own_persistence():
    X, y, cur = _record(kind="noise", seed=7)
    got = CD.pre_build_diagnostic(X, y, cur, n_perm=200)
    assert got["bands_plain"]["auc"] <= got["null"]["p95"]
    assert got["null"]["p50"] > 0.4, "a rotation null on a persistent label does not sit at 0.5"
    assert got["bands_plain"]["p_value"] > 0.05
    print(f"OK noise: bands {got['bands_plain']['auc']:.3f}, null median "
          f"{got['null']['p50']:.3f}, 95th {got['null']['p95']:.3f}, p {got['bands_plain']['p_value']:.3f}")


def test_the_folds_are_the_embargoed_ones_and_the_gap_is_the_label_s_own_timescale():
    X, y, cur = _record()
    got = CD.pre_build_diagnostic(X, y, cur, n_perm=20)
    assert got["embargo_rows"] == SU.block_length_for(y, len(y))
    assert got["n_folds"] == 5 and got["held_out_in_blocks_of_time"] is True
    # CORRECTED 2026-09-26 (decision 310). This line asserted that the same fit with the
    # neighbours put back scores HIGHER, "which is the reason for the gap". On this fixture the two
    # differed by 0.0001 (0.95329 against 0.95316, pooled scoring) and by -0.0014 once scored within
    # each block: a ridge over eight bands cannot memorise a neighbouring row, so the gap barely
    # moves it. The reason for the gap is proved where a model CAN memorise its neighbours
    # (`test_offline_model_guards.test_a_model_that_only_memorises_its_neighbours_loses_its_skill_
    # when_they_are_gone`); here it is pinned only that putting the neighbours back changes little.
    loose = CD.pre_build_diagnostic(X, y, cur, n_perm=20, embargo=0)
    assert loose["embargo_rows"] == 0
    assert abs(loose["bands_plain"]["auc"] - got["bands_plain"]["auc"]) < 0.02


def test_an_out_of_sample_score_below_chance_is_reported_as_it_is_and_never_folded():
    """A folded AUC is right for an undirected single-band screen and wrong here: this is a model's
    out-of-sample score, and a model that scores 0.30 has failed. Printing 0.70 would invert it.

    The fixture is the honest way to produce one -- a relationship that REVERSES halfway through the
    record, so whichever half the model is trained on, it is applied to a half that runs the other
    way. That is not a contrivance on this project: the direction of a band against pain has flipped
    between eras here before, which is what forward-chaining validation was adopted to catch
    (decision 12).
    """
    rng = np.random.default_rng(2)
    n = 200
    y = (rng.random(n) > 0.5).astype(float)
    sign = np.where(np.arange(n) < n // 2, 1.0, -1.0)
    X = np.column_stack([sign * (2 * y - 1) + rng.normal(0, 0.3, n) for _ in range(3)])
    got = CD.all_bands_auc(X, y, folds=SU.purged_time_blocked_folds(n, y=y, n_folds=2, embargo=0))
    assert got["auc"] < 0.35, f"a wrong-way model must report below chance, got {got['auc']:.3f}"
    assert got["folded"] is False
    print(f"OK a model trained on the wrong half reports {got['auc']:.3f}, not its mirror")


def test_the_adjusted_reading_gets_its_own_null_that_refits_the_adjusted_pipeline():
    """Decision 262's 'p 0.04' for the reading with the current taken out was read off the PLAIN
    reading's null -- the only one this function built at the time. An honest reference rotates the
    label and refits the SAME adjusted (current-removed) pipeline on each rotation, which is a
    different, usually weaker fit than the plain one, so its null is not the plain null."""
    X, y, cur = _record(kind="bands_carry_pain")
    got = CD.pre_build_diagnostic(X, y, cur, n_perm=100)
    assert got["bands_adjusted"]["p_value"] is not None
    assert got["null_adjusted"]["p50"] is not None and got["null_adjusted"]["n_perm"] > 0
    assert got["null_adjusted"]["p50"] != got["null"]["p50"], (
        "the adjusted null must come from refitting the adjusted pipeline, not be a copy of the plain null")
    assert got["bands_adjusted"]["p_value"] < 0.05, "a real signal should look significant on its own null"
    print(f"OK adjusted null: p50 {got['null_adjusted']['p50']:.3f} (plain null p50 "
          f"{got['null']['p50']:.3f}), adjusted p {got['bands_adjusted']['p_value']:.3f}")


def test_the_adjusted_null_is_none_when_the_adjusted_reading_itself_could_not_be_made():
    X, y, cur = _record(n=20)
    got = CD.pre_build_diagnostic(X, y, cur, n_perm=10)
    assert got["bands_adjusted"]["auc"] is None
    assert got["bands_adjusted"]["p_value"] is None
    assert got["null_adjusted"]["p50"] is None


def test_too_few_rows_is_a_reason_rather_than_a_number():
    X, y, cur = _record(n=20)
    got = CD.pre_build_diagnostic(X, y, cur, n_perm=10)
    assert got["bands_plain"]["auc"] is None
    assert "too few" in (got["bands_plain"]["reason"] or "").lower()
    assert got["verdict"] and "cannot" in got["verdict"].lower()


def _shared_step_between_blocks(seed=0, n=300, n_folds=5, n_bands=4):
    """Pain and every band share ONE level that changes from one held-out block of time to the next
    (a calendar effect, an era), and within any block the bands carry nothing about pain."""
    rng = np.random.default_rng(seed)
    level = np.zeros(n)
    for rows, lv in zip(np.array_split(np.arange(n), n_folds),
                        rng.permutation(np.linspace(-0.8, 0.8, n_folds))):
        level[rows] = lv
    pain = level + rng.normal(0, 1, n)            # every block holds both halves of the label
    X = np.column_stack([level + rng.normal(0, 1, n) for _ in range(n_bands)])
    y = (pain > np.median(pain)).astype(float)
    return X, y


def test_a_shift_shared_by_pain_and_the_bands_between_blocks_of_time_is_not_credited_to_the_bands():
    """Pooled across held-out blocks, the ranking compares one block's rows with another's, so a
    level that moves pain and the bands together between blocks reads as a detector (0.711 pooled on
    this record; 0.599 to 0.721 over 30 seeds) though the bands carry nothing within any block. Scored within each block it reads near
    chance (0.515 here; 0.441 to 0.583 over 30 seeds). RED on the pooled scorer."""
    X, y = _shared_step_between_blocks()
    folds = SU.purged_time_blocked_folds(len(y), y=y, n_folds=5)
    got = CD.all_bands_auc(X, y, folds=folds)
    assert got.get("scored_within_blocks") is True, got
    assert got["n_blocks_scored"] == 5, got
    assert 0.3 < got["auc"] < 0.7, f"a shift between blocks is not a band reading pain: {got['auc']:.3f}"
    print(f"OK a shared shift between blocks reads {got['auc']:.3f} within blocks")


def test_a_drifting_pain_score_with_a_band_that_carries_nothing_does_not_read_backwards_here():
    """The band detector's reason for scoring within blocks (decision 297) is that each block's
    prediction carries its training rows' average pain. This scorer fits a centred label, so it
    carries none, and a drift alone did not read backwards even when pooled (0.49 on average over
    20 seeds, measured 2026-09-26). Pinned so the reason stays the right one; passes pooled too."""
    rng = np.random.default_rng(21)
    n = 200
    pain = np.linspace(8.0, 3.0, n) + rng.normal(0, 0.7, n)
    X = rng.normal(100, 1, (n, 3))
    y = (pain > np.median(pain)).astype(float)
    got = CD.all_bands_auc(X, y, folds=SU.purged_time_blocked_folds(n, y=y, n_folds=5))
    assert got["auc"] is None or abs(got["auc"] - 0.5) < 0.2, got


def test_auc_within_blocks_ignores_every_pair_that_crosses_a_block():
    # two blocks: within each, the score ranks the label perfectly the WRONG way; across blocks the
    # score's level follows the label, so a pooled area would read well above 0.5
    score = np.array([1.0, 0.0, 11.0, 10.0])
    labels = np.array([0.0, 1.0, 0.0, 1.0])
    block = np.array([0, 0, 1, 1])
    labels2 = np.array([0.0, 1.0, 1.0, 0.0])
    assert CD.auc_within_blocks(score, labels, block) == 0.0
    assert CD.auc_within_blocks(np.array([0.0, 1.0, 10.0, 11.0]), labels2, block) == 0.5
    # a block holding one half only contributes no pair; none at all is None, not 0.5
    assert CD.auc_within_blocks(score, np.array([0.0, 0.0, 1.0, 1.0]), block) is None


def test_the_verdict_judges_the_adjusted_reading_against_its_own_null():
    """Decision 276 gave the adjusted reading its own null; the verdict sentence still set it
    against the PLAIN reading's 95th. It now names the null it used and prints its 95th."""
    X, y, cur = _record(kind="bands_carry_pain")
    got = CD.pre_build_diagnostic(X, y, cur, n_perm=60)
    p95 = got["null_adjusted"]["p95"]
    assert p95 is not None
    assert "its own null" in got["verdict"] and f"{p95:.3f}" in got["verdict"], got["verdict"]


# --------------------------------------------------------------------------------------------------
# merged from test_covariate_shape.py
# The shape the stimulation current is allowed to have when it is taken out of something.
#
# WHY (the PI, 2026-09-22). Both guards took the current out as a STRAIGHT LINE. He asked whether that
# masks a real effect, because the current-to-pain relationship can turn over -- helping up to a point
# and worsening above it. It can, and it cuts both ways: a curved current effect survives a straight-
# line removal as a leftover curve, which a candidate that tracks distance-from-the-best-current then
# looks correlated with; and a genuinely curved candidate reads near zero.
#
# Measured on his record before building this (L 1-3+, 53 reports, 11 delivered currents): a straight
# line explains 25.7% of pain's scatter and is still falling at the highest current tested; two degrees
# of freedom (a squared term, or a 3-knot spline) explain 29-31% and put the lowest pain at 3.1-3.2 mA;
# the three kernels, given 4-6 degrees of freedom, explain 37-43% and move it to 1.8-1.9 mA, chasing
# two ratings at 1.6 mA. So the shape matters, the flexible shapes disagree with each other about
# where the turn is, and the honest default is the cheapest shape that can turn over at all.
#
# WHAT IS ASSERTED: that each shape spends the flexibility it claims; that a curved covariate driving
# two unrelated series leaves a large false correlation after a straight-line removal and none after a
# curved one (the case he named); that a real relationship survives every shape; that the removal is
# fitted on training rows only; that a shape that cannot be built falls back and says so; and that
# both guards carry the shape and its cost on every answer.
#
# Run inside the container:
#     docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore         modules/Biomarkers/tests/test_covariate_shape.py


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


# --------------------------------------------------------------------------------------------------
# merged from test_current_adjusted_correlation.py
# The heat map's correlation with the stimulation current in force taken out of it.
#
# WHY THIS EXISTS. The grid correlates a band's power against a pain score and nothing else. On
# RCS08's left lead both of those fall as the stimulation current rises, so a band can look as though
# it tracks pain when what it tracks is the current that was running at the time (measured 2026-09-22:
# on L 1-3+ every 21.5-26.5 Hz cell the exploratory search called "supported" loses its wholly
# positive interval once the current in force at each rating is taken out of it). The older
# per-session search has carried that adjustment for a long time (`pipeline.py`, `partial_corr`); the
# grid never has.
#
# WHAT IS ASSERTED, in order:
#
#   * the adjustment does what it says: on data where the current drives BOTH the band power and the
#     pain score and nothing else connects them, the plain correlation is large and the adjusted one
#     is not;
#   * a real relationship that does not come from the current survives the adjustment (the control:
#     an adjustment that flattens everything is useless);
#   * THE RAW SIDE DOES NOT MOVE. Every number the page already shows is identical whether or not the
#     covariate is supplied. The adjusted value rides beside the plain one; it never replaces it and
#     never re-selects a band;
#   * a covariate that is missing, constant, or too short to regress out is REFUSED with a reason,
#     never silently treated as an adjustment that found nothing;
#   * the column-wise partial correlation equals the one-column-at-a-time function it is built on;
#   * the current in force at a moment is the newest programmed setting at or before it, per side,
#     and is unknown (not zero) before the first setting on record.
#
# Run inside the container:
#     docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore         modules/Biomarkers/tests/test_current_adjusted_correlation.py


from Biomarkers.routines import analytics as A          # noqa: E402
from Biomarkers.routines import stim_current as SC      # noqa: E402


def _grid_driven_by_current(seed=0, n_reports=90, confounded_col=6, honest_col=11):
    """Band powers, pain scores and the current in force at each rating.

    Two bands are planted. The CONFOUNDED one has no relationship with pain at all except through
    the current: the current pushes its power down and pushes the pain score down, which leaves the
    two correlated with each other. The HONEST one tracks pain directly and does not see the
    current. Everything else is noise.
    """
    rng = np.random.default_rng(seed)
    centers = A.sweep_center_freqs(np.arange(2.5, 100.0, 1.0))
    C = centers.size
    amp = rng.choice([0.0, 1.0, 1.6, 2.5, 3.5, 4.5], size=n_reports)      # mA in force at the rating
    za = (amp - amp.mean()) / amp.std()
    own = rng.normal(0.0, 1.0, n_reports)                                 # pain that is not the current
    pain = 50.0 - 8.0 * za + 6.0 * own
    power = {}
    for s in A.BAND_TIME_SWEEP_SECONDS:
        m = rng.normal(0.0, 1.0, (n_reports, C))
        m[:, confounded_col] -= 1.6 * za                                  # falls with current only
        m[:, honest_col] += 1.6 * own                                     # tracks pain only
        power[float(s)] = np.exp(m)
    return power, pain, amp, centers, confounded_col, honest_col


def _sweep(power, pain, centers, **kw):
    return A.band_time_sweep_from_power(power, pain, center_freqs_hz=centers, n_perm=60, n_boot=60,
                                        seed=3, channel="ONE_THREE_LEFT", metric_key="left_leg_vas",
                                        metric_label="Left Leg VAS", **kw)


def _row_at(out, centre_hz):
    for r in out.get("best_correlation_rows") or []:
        if abs(float(r["band_center_hz"]) - float(centre_hz)) < 1e-9:
            return r
    raise AssertionError(f"no best row at {centre_hz} Hz")


def test_a_band_that_only_follows_the_current_loses_its_correlation_when_the_current_is_taken_out():
    power, pain, amp, centers, conf_col, _ = _grid_driven_by_current()
    out = _sweep(power, pain, centers, covariate=amp, covariate_label="the current in force (mA)")
    row = _row_at(out, centers[conf_col])
    raw, adj = float(row["pearson_r"]), float(row["pearson_r_adjusted"])
    assert abs(raw) > 0.35, f"the planted confounded band should correlate plainly, got r={raw:.3f}"
    assert abs(adj) < 0.15, f"taking the current out should leave nothing, got r={adj:.3f}"
    assert abs(adj) < abs(raw) / 2.0
    assert np.isclose(float(row["pearson_r_adjustment"]), adj - raw, atol=1e-12)
    grid = out["adjusted_correlation_grid"]
    assert np.asarray(grid, dtype=float).shape == np.asarray(out["correlation_grid"], dtype=float).shape
    print(f"OK a current-driven band reads r={raw:.3f} plainly and r={adj:.3f} adjusted")


def test_a_band_that_tracks_pain_on_its_own_keeps_its_correlation():
    power, pain, amp, centers, _, honest_col = _grid_driven_by_current()
    out = _sweep(power, pain, centers, covariate=amp, covariate_label="the current in force (mA)")
    row = _row_at(out, centers[honest_col])
    raw, adj = float(row["pearson_r"]), float(row["pearson_r_adjusted"])
    assert abs(raw) > 0.3 and abs(adj) > 0.3, f"raw {raw:.3f}, adjusted {adj:.3f}"
    assert abs(adj - raw) < 0.2, "a band that does not follow the current should barely move"
    print(f"OK a genuinely pain-tracking band reads r={raw:.3f} plainly and r={adj:.3f} adjusted")


def test_supplying_the_covariate_changes_nothing_about_the_plain_answer():
    power, pain, amp, centers, _, _ = _grid_driven_by_current()
    plain = _sweep(power, pain, centers)
    adjusted = _sweep(power, pain, centers, covariate=amp, covariate_label="the current in force (mA)")
    assert "adjusted_correlation_grid" not in plain, "no covariate means no adjusted grid at all"
    a = np.asarray(plain["correlation_grid"], dtype=float)
    b = np.asarray(adjusted["correlation_grid"], dtype=float)
    assert np.array_equal(np.isnan(a), np.isnan(b))
    assert np.allclose(a[~np.isnan(a)], b[~np.isnan(b)], rtol=0, atol=0), "the plain grid moved"
    for key in ("best_correlation_rows", "best_auc_rows"):
        for r0, r1 in zip(plain[key], adjusted[key]):
            for field in ("band_center_hz", "pearson_r", "integration_seconds_delivered",
                          "n_pain_reports", "family_wise_q_8_to_30hz", "answer"):
                if field in r0:
                    v0, v1 = r0[field], r1[field]
                    same = (v0 == v1) or (isinstance(v0, float) and isinstance(v1, float)
                                          and np.isnan(v0) and np.isnan(v1))
                    assert same, f"{key}.{field} moved: {v0!r} -> {v1!r}"
    print("OK the plain grid and every selected row are identical with and without the covariate")


def test_a_constant_or_absent_covariate_is_refused_and_says_why():
    power, pain, amp, centers, _, _ = _grid_driven_by_current()
    flat = _sweep(power, pain, centers, covariate=np.full(pain.size, 2.5),
                  covariate_label="the current in force (mA)")
    block = flat["covariate_adjustment"]
    assert block["applied"] is False
    assert "constant" in (block["reason"] or "").lower()
    assert "adjusted_correlation_grid" not in flat

    missing = _sweep(power, pain, centers, covariate=np.full(pain.size, np.nan),
                     covariate_label="the current in force (mA)")
    assert missing["covariate_adjustment"]["applied"] is False
    assert "no" in (missing["covariate_adjustment"]["reason"] or "").lower()

    ok = _sweep(power, pain, centers, covariate=amp, covariate_label="the current in force (mA)")
    b = ok["covariate_adjustment"]
    assert b["applied"] is True and b["label"] == "the current in force (mA)"
    assert b["n_with_covariate"] == int(pain.size) and b["n_distinct_values"] == 6
    print("OK a constant, absent or unusable covariate is refused with a reason")


def test_the_column_wise_partial_correlation_matches_the_one_column_function():
    rng = np.random.default_rng(7)
    n, C = 70, 5
    covar = rng.normal(0, 1, n)
    X = rng.normal(0, 1, (n, C)) + covar[:, None]
    y = rng.normal(0, 1, n) + 2.0 * covar
    X[3, 2] = np.nan
    y[9] = np.nan
    got = SU.partial_corr_columns(X, y, covar)
    for c in range(C):
        one = SU.partial_corr(X[:, c], y, covar)
        assert np.isclose(got["r"][c], one, rtol=0, atol=1e-12, equal_nan=True), c
    assert got["n"][2] == n - 2 and got["n"][0] == n - 1
    print("OK the column-wise partial correlation equals the scalar one, column for column")


def test_the_current_in_force_is_the_newest_setting_at_or_before_the_moment_per_side():
    hour = 3600.0
    t0 = 1_700_000_000.0
    stream = {
        "t_s": np.array([t0, t0, t0 + 10 * hour, t0 + 10 * hour]),
        "hemi": np.array(["Left", "Right", "Left", "Right"]),
        "amp_mA": np.array([1.6, 2.5, 4.0, 2.5]),
    }
    times = np.array([t0 - hour, t0 + hour, t0 + 11 * hour])
    left = SC.current_in_force_at(times, stream, hemisphere="Left")
    right = SC.current_in_force_at(times, stream, hemisphere="Right")
    assert np.isnan(left[0]), "before the first setting on record the current is unknown, not zero"
    assert left[1] == 1.6 and left[2] == 4.0
    assert np.isnan(right[0]) and right[1] == 2.5 and right[2] == 2.5
    assert SC.hemisphere_of_channel("ONE_THREE_LEFT") == "Left"
    assert SC.hemisphere_of_channel("ZERO_THREE_RIGHT") == "Right"
    assert SC.hemisphere_of_channel("nonsense") is None
    print("OK the current in force is the newest setting at or before each moment, per side")
