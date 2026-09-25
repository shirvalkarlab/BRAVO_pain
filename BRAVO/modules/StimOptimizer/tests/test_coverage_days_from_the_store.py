"""The coverage check counts the same days whether the matched table was just built or read back
from the store (found 2026-09-24 while proving the implant-date cutoff).

The table keeps each epoch's rating days as a tuple when built, and Parquet hands them back as a
numpy array. The check recognised only tuples, lists and sets, so a served table's days read as
unknown: the observed-days path fell back to adding up per-epoch day counts (a day shared by two
epochs counted twice: 81 days where the union is 78 on RCS08's L1.6/R1.2) or, on the schedule card,
to nothing at all (0 days, "does not qualify", for pairs with 16 and 19 real days).
"""
import numpy as np
import pandas as pd

from StimOptimizer import stage1_openloop as S1


def _frame(as_array):
    days = [("2026-01-01", "2026-01-02"), ("2026-01-02", "2026-01-03")]
    conv = (lambda d: np.array(d, dtype=object)) if as_array else tuple
    return pd.DataFrame(dict(amp_mA_Left=[1.6, 1.6], amp_mA_Right=[1.2, 1.2], n=[5.0, 5.0],
                             rating_days=[conv(d) for d in days], n_rating_days=[2, 2]))


def test_days_read_back_as_arrays_are_the_union_not_a_sum():
    built = S1.current_coverage(_frame(False))
    served = S1.current_coverage(_frame(True))
    assert [p["n_days"] for p in built["pairs"]] == [3.0]
    assert [p["n_days"] for p in served["pairs"]] == [3.0]


def test_served_days_are_not_lost_when_no_count_column_comes_with_them():
    f = _frame(True).drop(columns=["n_rating_days"])
    assert [p["n_days"] for p in S1.current_coverage(f)["pairs"]] == [3.0]
