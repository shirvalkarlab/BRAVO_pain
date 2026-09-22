"""Does the surface the current-map card draws predict a stretch it has not seen?

WHY THIS EXISTS. `OBJECTIVE_SPEC.md` §6 pre-registered three criteria for the surrogate -- it must
beat a precision-weighted mean of the training fold on held-out epochs, twice (leaving out one epoch
at a time, and leaving out a whole block of time at a time), and its intervals must cover what they
claim. `routines/validation.py` implements them and **nothing on the live path has ever run them**:
measured on 2026-09-22, the check is imported nowhere outside its own module, and its warm-start
helper raises on the hard-infeasible epochs the objective has flagged since, so it cannot have run
in a long time. Run by hand that night on the live per-rate strata, it FAILS on both fitted rates.

So the check now runs where the surface is fitted, and its answer travels with the stratum.

THE PI'S RULING (2026-09-22, ruling 6 of decision 233): **a warning, never blocking.** The spec's own
consequence -- "any single failure -> surrogate may not select settings" -- is not adopted. A failed
check changes no recommendation, refuses nothing, and is reported.

WHAT IS ASSERTED: that the check runs and lands on the stratum; that it says "not computable" rather
than a number where a fold has too little to train on (a rate with one or three epochs, which this
record has); that it never refuses anything; and that its wording says the consequence.
"""
import numpy as np
import pytest

from StimOptimizer import stage1_openloop as S1


from StimOptimizer.tests.test_stage1 import _matrix       # the fixture Stage 1 is already tested on


def _fitted_strata(res):
    """Every fitted per-rate surface, reached the way the page's own serialiser reaches them
    (`bravo_service._rate_stratum_index`): one joint stratum per pulse-width pair under `.slices`,
    and each of those holds one `RateStratum` per rate."""
    out = []
    for _key, sl in (getattr(res, "slices", None) or {}).items():
        for _rate, rs in (getattr(sl, "rate_strata", None) or {}).items():
            if getattr(rs, "fitted", False):
                out.append(rs)
    return out


def test_every_fitted_surface_carries_the_pre_registered_check_and_it_blocks_nothing():
    res = S1.run_stage1(_matrix(), hemispheres=("Left", "Right"), primary_item="left_leg_vas",
                        data_horizon="2026-12-31")
    strata = _fitted_strata(res)
    assert strata, "the fixture must fit at least one per-rate surface"
    for rs in strata:
        cal = rs.meta.get("calibration")
        assert cal is not None, "every fitted surface reports the check"
        assert set(cal) >= {"checks", "summary", "passes", "blocking", "consequence"}
        assert cal["blocking"] is False, "the PI, 2026-09-22: a warning, never blocking"
        assert "warning" in cal["consequence"].lower()
        assert "refuses nothing" in cal["consequence"].lower()
        # the three pre-registered criteria are named, whatever their answers
        assert set(cal["checks"]) == {"C1_loeo_skill", "C2_loera_skill", "C3_calibration"}
        for k, v in cal["checks"].items():
            assert v in (True, False, None), (k, v)


def test_a_fold_that_cannot_be_trained_on_says_not_computable_rather_than_passing_or_failing():
    """A fold with nothing to hold out is not a pass and not a failure.

    (The first version of this test tried to reach that state through a small `run_stage1` fit and
    could not: at nine epochs the block fold splits three ways and IS computable. The state belongs
    to the fold, so it is tested at the fold.)
    """
    res = S1.run_stage1(_matrix(n_per_cell=9, pw_pairs=((60.0, 160.0),), rates=(55.0,)),
                        hemispheres=("Left", "Right"), primary_item="left_leg_vas",
                        data_horizon="2026-12-31")
    rs = _fitted_strata(res)[0]
    gp = rs.gp
    y, v = np.asarray(gp.y_, float), np.asarray(gp.y_var_, float)

    one_block, ratio = S1._one_calibration_fold(gp, y, v, np.zeros(len(y), dtype=int),
                                                name="leave-one-block-out")
    assert ratio is None and one_block["mae_ratio"] is None
    assert "not computable" in one_block["reason"].lower() and "one group" in one_block["reason"]

    # and a fold whose held-out epochs mostly cannot be predicted comes back the same way: the
    # surrogate's own `loo_predict` skips any fold with fewer than three rows to train on, and a
    # ratio computed from the two that survived would be a number nobody should read.
    class _MostlyUnpredictable:
        y_, y_var_ = gp.y_, gp.y_var_

        @staticmethod
        def loo_predict(groups=None):
            mu = np.full(len(y), np.nan)
            mu[:2] = y[:2]
            return mu, np.full(len(y), 1.0)

    thin, ratio2 = S1._one_calibration_fold(_MostlyUnpredictable, y, v, np.arange(len(y)), name="x")
    assert ratio2 is None and "not computable" in (thin["reason"] or "").lower()
    assert "could be predicted" in thin["reason"]

    # whatever the answers are, the block never refuses anything
    cal = rs.meta["calibration"]
    assert cal["blocking"] is False and cal["checks"]["C2_loera_skill"] in (True, False, None)


def test_the_check_never_changes_what_the_search_recommends():
    """The same fit, with the check computed and with it switched off, must resolve the same way."""
    res_on = S1.run_stage1(_matrix(), hemispheres=("Left", "Right"), primary_item="left_leg_vas",
                           data_horizon="2026-12-31")
    res_off = S1.run_stage1(_matrix(), hemispheres=("Left", "Right"), primary_item="left_leg_vas",
                            data_horizon="2026-12-31", calibration_check=False)
    a, b = _fitted_strata(res_on)[0], _fitted_strata(res_off)[0]
    assert a.resolution.get("resolved") == b.resolution.get("resolved")
    assert a.x_star == b.x_star and np.isclose(a.mu_star, b.mu_star)
    assert b.meta.get("calibration") is None, "switched off means not computed, not a blank"


if __name__ == "__main__":                              # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
