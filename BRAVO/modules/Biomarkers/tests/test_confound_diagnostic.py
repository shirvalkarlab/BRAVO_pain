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
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \
        modules/Biomarkers/tests/test_confound_diagnostic.py
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
    # and the same fit with the neighbours put back scores HIGHER, which is the reason for the gap
    loose = CD.pre_build_diagnostic(X, y, cur, n_perm=20, embargo=0)
    assert loose["bands_plain"]["auc"] >= got["bands_plain"]["auc"] - 1e-9


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


if __name__ == "__main__":
    test_a_current_that_drives_both_reads_high_plainly_and_collapses_once_it_is_taken_out()
    test_bands_that_carry_something_of_their_own_survive_the_adjustment()
    test_noise_reads_as_noise_against_a_null_that_keeps_pain_s_own_persistence()
    test_the_folds_are_the_embargoed_ones_and_the_gap_is_the_label_s_own_timescale()
    test_an_out_of_sample_score_below_chance_is_reported_as_it_is_and_never_folded()
    test_the_adjusted_reading_gets_its_own_null_that_refits_the_adjusted_pipeline()
    test_the_adjusted_null_is_none_when_the_adjusted_reading_itself_could_not_be_made()
    test_too_few_rows_is_a_reason_rather_than_a_number()
    print("All confound-diagnostic tests passed.")
