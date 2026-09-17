"""S4 of the 2026-09-15 review (decision 184): the coverage half of the honest-current check counts
OCCASIONS -- distinct California calendar days with a rating -- for every (left, right) current
pair, not only ratings. Decision 111 measured that two ratings an hour apart differ by 0.37 points:
they are close to one observation. Five ratings filed in one afternoon used to satisfy the
five-report floor exactly as five ratings on five days did.
"""
import numpy as np
import pandas as pd
import pytest

from StimOptimizer import adapter as AD
from StimOptimizer import clinic_pain as CP
from StimOptimizer import current_map_schedule as CMS
from StimOptimizer import stage1_openloop as S1


def _eight_pairs(days_per_pair):
    L = [0.0, 0.0, 1.0, 1.0, 2.0, 2.0, 4.0, 4.0]
    R = [0.0, 4.0, 1.0, 3.0, 0.0, 4.0, 0.0, 4.0]
    days = [tuple(f"2026-01-{d + 1:02d}" for d in range(days_per_pair)) for _ in L]
    return pd.DataFrame({"amp_mA_Left": L, "amp_mA_Right": R, "n": [8] * 8, "rating_days": days})


def test_five_ratings_on_one_day_do_not_make_a_covered_pair():
    one_day = S1.current_coverage(_eight_pairs(1))
    assert one_day["n_pairs"] == 0
    assert one_day["passes"] is False
    assert one_day["days_per_pair_required"] == S1.CURRENT_COVERAGE_MIN_DAYS_PER_PAIR == 2
    two_days = S1.current_coverage(_eight_pairs(2))
    assert two_days["n_pairs"] == 8
    assert two_days["passes"] is True
    assert two_days["min_days_over_pairs"] == 2


def test_two_stretches_at_one_pair_sharing_a_day_count_that_day_once():
    d = pd.DataFrame({"amp_mA_Left": [1.0, 1.0], "amp_mA_Right": [2.0, 2.0], "n": [3, 3],
                      "rating_days": [("2026-01-01", "2026-01-02"), ("2026-01-02",)]})
    cov = S1.current_coverage(d, min_pairs=1, min_span_mA=0.0)
    assert cov["min_days_over_pairs"] == 2      # the union, not 3


def test_a_frame_that_carries_no_days_cannot_pass():
    bare = pd.DataFrame({"amp_mA_Left": [0.0, 4.0, 0.0, 4.0, 2.0, 2.0],
                         "amp_mA_Right": [0.0, 4.0, 4.0, 0.0, 0.0, 4.0], "n": [8] * 6})
    cov = S1.current_coverage(bare)
    assert cov["passes"] is False and cov["days_known"] is False


def test_planned_steps_are_credited_their_hold_days():
    steps = [dict(amp_left_mA=l, amp_right_mA=r, planned_days=5)
             for l in (0.0, 1.0, 2.5, 4.0) for r in (0.0, 1.0, 2.5, 4.0)]
    wtb = CMS.what_this_buys(None, steps, target_reports=5)
    assert wtb["resolution_coverage_would_pass"] is True
    assert wtb["coverage_after_schedule"]["min_days_over_pairs"] == 5
    one_day = [dict(s, planned_days=1) for s in steps]
    assert CMS.what_this_buys(None, one_day, target_reports=5)["resolution_coverage_would_pass"] is False


def test_the_redcap_epochs_carry_their_california_rating_days():
    epochs = pd.DataFrame({"epoch": [0.0], "t_start": [pd.Timestamp("2026-01-01T00:00Z")],
                           "t_end": [pd.Timestamp("2026-01-10T00:00Z")], "dur_h": [216.0],
                           "amp_mA_Left": [1.0], "amp_mA_Right": [1.0], "freq_hz": [55.0],
                           "pw_us_Left": [60.0], "pw_us_Right": [60.0], "open_ended": [True]})
    # 03:00Z on the 2nd is still the 1st in California; 20:00Z on the 2nd is the 2nd
    times = ["2026-01-02T03:00:00Z", "2026-01-02T20:00:00Z", "2026-01-02T21:00:00Z"]
    pro = pd.DataFrame({"nrs": [5.0, 6.0, 7.0]})
    out = AD.attach_pros(epochs, pro, times, items=("nrs",))
    assert int(out["n"].iloc[0]) == 3
    assert tuple(out["rating_days"].iloc[0]) == ("2026-01-01", "2026-01-02")
    assert int(out["n_rating_days"].iloc[0]) == 2


def test_the_clinic_epochs_carry_their_rating_days():
    rows = []
    for i, day in enumerate(("2026-03-04", "2026-03-04", "2026-03-19")):
        rows.append(dict(visit_date=day, setting="clinic", file="f", sha256="x", t_local=None,
                         t_utc=pd.Timestamp(day + "T18:00", tz="UTC") + pd.Timedelta(minutes=i),
                         amp_mA_Left=1.0, amp_mA_Right=0.0, freq_hz=55.0, pw_us_Left=60.0,
                         pw_us_Right=60.0, contacts_raw="c", duration_s=60.0,
                         side_effect_score=0.0, overall=np.nan, head=np.nan, back=np.nan,
                         left_leg=5.0, left_foot=np.nan, right_leg=np.nan, right_foot=np.nan,
                         notes=None, row_index=i))
    ep = CP.epoch_frame_from_steps(pd.DataFrame(rows))
    assert len(ep) == 1
    assert tuple(ep["rating_days"].iloc[0]) == ("2026-03-04", "2026-03-19")
    assert int(ep["n_rating_days"].iloc[0]) == 2
