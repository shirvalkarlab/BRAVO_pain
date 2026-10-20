"""Two guards every offline model on this record has to pass through.

They exist because of what this participant's data are: pain scores that resemble their neighbours
in time, and a stimulation current that moves both the band power and the pain. Any model fitted
here can score well for either reason without carrying a single fact about the brain.

  * **The time-blocked split with an embargo.** Neighbouring rows are nearly the same measurement,
    so a fold whose training rows sit next to its test rows is scored on data it has effectively
    seen. The gap is set from the series' OWN decorrelation timescale rather than a number somebody
    liked (`block_length_for`), because that timescale is the thing being guarded against.
  * **The current-confound gate.** Every candidate a model proposes is reported plainly AND with
    the stimulation current in force taken out, with the same interval on each, so nobody has to
    remember to ask (decisions 232, 234; the PI, 2026-09-22: reported descriptively).

WHAT IS ASSERTED: that the embargo really removes the neighbours and is derived, not typed; that a
model which only memorises its neighbours loses its skill once they are gone, while one that carries
real information keeps it; that the gate collapses a candidate which is only the current and keeps
one that is not; and that a covariate which cannot adjust anything is refused with a reason.

Run inside the container:
    docker exec -w /usr/src/BRAVO bravo_pain-bravo-server-1 python3 -W ignore \\
        modules/Biomarkers/tests/test_offline_model_guards.py
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import stats_utils as SU       # noqa: E402


def _autocorrelated(n=400, rho=0.9, seed=0):
    rng = np.random.default_rng(seed)
    y = np.zeros(n)
    for i in range(1, n):
        y[i] = rho * y[i - 1] + rng.normal(0, 1)
    return y


# ---------------------------------------------------------------------------------------------
# 1. the folds: contiguous in time, every row tested once, and the neighbours really gone
# ---------------------------------------------------------------------------------------------

def test_the_folds_are_blocks_of_time_and_the_embargo_comes_from_the_series_itself():
    y = _autocorrelated()
    folds = SU.purged_time_blocked_folds(len(y), y=y, n_folds=5)
    assert len(folds) == 5
    embargo = SU.block_length_for(y, len(y))
    assert embargo > 1, "this fixture is autocorrelated, so its own timescale is more than one row"
    tested = []
    for tr, te in folds:
        tested.extend(te.tolist())
        # a test block is contiguous in time
        assert np.array_equal(te, np.arange(te[0], te[-1] + 1))
        # and no training row sits within the embargo of it
        if tr.size:
            gap = np.min(np.abs(tr[:, None] - te[None, :]))
            assert gap > embargo, f"a training row sits {gap} rows from the test block"
    assert sorted(tested) == list(range(len(y))), "every row is tested exactly once"


def test_the_embargo_can_be_given_and_zero_puts_the_neighbours_back():
    y = _autocorrelated()
    tight = SU.purged_time_blocked_folds(len(y), y=y, n_folds=5, embargo=0)
    tr, te = tight[2]
    assert np.min(np.abs(tr[:, None] - te[None, :])) == 1, "with no embargo the neighbours are back"
    wide = SU.purged_time_blocked_folds(len(y), y=y, n_folds=5, embargo=25)
    tr2, te2 = wide[2]
    assert np.min(np.abs(tr2[:, None] - te2[None, :])) > 25


def test_a_model_that_only_memorises_its_neighbours_loses_its_skill_when_they_are_gone():
    """The leak, shown rather than asserted: predict each held-out value by the nearest TRAINING row
    in time. With the neighbours in the training fold that scores well and means nothing; with the
    embargo it falls back to what the series' own persistence can really support.

    Measured here while building it (400 rows, lag-1 0.95, its own timescale 16 rows), because the
    size of the leak depends on how long the held-out blocks are and that is worth knowing:

        blocks of 80 rows   0.18 with the neighbours, 0.33 without
        blocks of 20 rows   0.75 with, 0.08 without
        blocks of 10 rows   0.83 with, 0.19 without
        blocks of  3 rows   0.92 with, 0.22 without

    So the guard matters most where the blocks are SHORT -- which is the regime a record of this size
    forces, since a few long blocks leave almost nothing to train on. With blocks longer than the
    embargo itself the trick has no neighbours to exploit in the first place and the two columns are
    both noise, which is why the row at the top does not order the way the others do.
    """
    y = _autocorrelated(rho=0.95, seed=3)

    def skill(folds):
        pred, true = [], []
        for tr, te in folds:
            if not tr.size:
                continue
            nearest = tr[np.argmin(np.abs(tr[:, None] - te[None, :]), axis=0)]
            pred.extend(y[nearest].tolist())
            true.extend(y[te].tolist())
        return float(np.corrcoef(pred, true)[0, 1])

    leaky = skill(SU.purged_time_blocked_folds(len(y), y=y, n_folds=40, embargo=0))
    guarded = skill(SU.purged_time_blocked_folds(len(y), y=y, n_folds=40))
    assert leaky > 0.7, f"without the embargo the neighbour trick scores {leaky:.2f}"
    assert guarded < leaky - 0.4, f"with it, {guarded:.2f} against {leaky:.2f}"
    print(f"OK the neighbour trick scores {leaky:.2f} with the neighbours and {guarded:.2f} without")


# ---------------------------------------------------------------------------------------------
# 2. the current-confound gate
# ---------------------------------------------------------------------------------------------

def test_a_candidate_that_is_only_the_current_does_not_survive_the_gate():
    rng = np.random.default_rng(1)
    n = 200
    current = rng.choice([0.0, 1.0, 1.6, 2.5, 3.5, 4.5], size=n)
    z = (current - current.mean()) / current.std()
    pain = 50.0 - 8.0 * z + rng.normal(0, 4, n)
    power = 200.0 - 20.0 * z + rng.normal(0, 12, n)
    got = SU.confound_gate(power, pain, current, label="the stimulation current in force")
    assert abs(got["r"]) > 0.3 and abs(got["r_adjusted"]) < 0.15
    assert got["survives"] is False
    assert got["r_adjusted_ci"][0] < 0 < got["r_adjusted_ci"][1]
    assert "does not survive" in got["verdict"] and "current" in got["verdict"]
    print(f"OK a current-only candidate reads {got['r']:+.3f} and {got['r_adjusted']:+.3f} adjusted")


def test_a_candidate_that_carries_something_else_survives_it():
    rng = np.random.default_rng(2)
    n = 200
    current = rng.choice([0.0, 1.0, 2.5, 4.5], size=n)
    own = rng.normal(0, 1, n)
    pain = 50.0 - 4.0 * current + 9.0 * own
    power = 200.0 + 25.0 * own + rng.normal(0, 5, n)
    got = SU.confound_gate(power, pain, current, label="the stimulation current in force")
    assert got["survives"] is True and abs(got["r_adjusted"]) > 0.3
    assert got["r_adjusted_ci"][0] * got["r_adjusted_ci"][1] > 0
    assert "survives" in got["verdict"]


def test_a_covariate_that_cannot_adjust_anything_is_refused_with_a_reason():
    rng = np.random.default_rng(3)
    n = 60
    x, y = rng.normal(0, 1, n), rng.normal(0, 1, n)
    flat = SU.confound_gate(x, y, np.full(n, 2.5), label="the stimulation current in force")
    assert flat["survives"] is None and "constant" in flat["reason"].lower()
    missing = SU.confound_gate(x, y, np.full(n, np.nan), label="x")
    assert missing["survives"] is None and missing["reason"]
    print("OK a constant or absent covariate is refused, not silently passed")


if __name__ == "__main__":
    test_the_folds_are_blocks_of_time_and_the_embargo_comes_from_the_series_itself()
    test_the_embargo_can_be_given_and_zero_puts_the_neighbours_back()
    test_a_model_that_only_memorises_its_neighbours_loses_its_skill_when_they_are_gone()
    test_a_candidate_that_is_only_the_current_does_not_survive_the_gate()
    test_a_candidate_that_carries_something_else_survives_it()
    test_a_covariate_that_cannot_adjust_anything_is_refused_with_a_reason()
    print("All offline-model guard tests passed.")
