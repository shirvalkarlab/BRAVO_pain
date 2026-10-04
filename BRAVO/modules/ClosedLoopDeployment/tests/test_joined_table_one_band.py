"""The joined table is built for the chosen contact and band only (the PI, 2026-10-04, decision 419).

The report built one row per 3 s chunk for every contact and every band (about 1.6 million rows on
RCS08, 8.5 s of the 40 s report), and every reader then took the rows of one contact at one band.
Built for that contact and band alone, the rows -- and every value read from them -- are the same;
the manifest's row count still states the size of the whole table, so no field of the report moves.
"""
import numpy as np
import pandas as pd

try:
    from modules.ClosedLoopDeployment import adapter as AD, pipeline as PL, edges as E
except ImportError:                                              # pragma: no cover - host spelling
    from ClosedLoopDeployment import adapter as AD, pipeline as PL, edges as E

from ClosedLoopDeployment.tests.test_chunk_rule_on_e2_and_threshold import (
    _cache, _epochs, _pro, CAND, FC)
from StimOptimizer.routines import lfp_evidence as EV


def _frame():
    a, b = _cache(seed=0), _cache(seed=1)
    b = dict(b, channel="ONE_THREE_LEFT")
    return EV.frame_from_lsb_cache({"ZERO_TWO_LEFT": a, "ONE_THREE_LEFT": b})


def test_the_one_band_table_is_the_full_tables_rows_for_that_band():
    f, e = _frame(), _epochs()
    full = AD.joined_table(f, e, centers=(8.5, 12.5, FC), pro_frame=_pro())
    one = AD.joined_table(f, e, centers=(FC,), pro_frame=_pro(), channels=("ZERO_TWO_LEFT",))
    want = full[(full.channel == "ZERO_TWO_LEFT") & np.isclose(full.center_hz, FC)].reset_index(drop=True)
    assert list(one.columns) == list(want.columns)
    pd.testing.assert_frame_equal(one.reset_index(drop=True), want, check_exact=True)


def test_the_row_count_of_the_whole_table_is_kept():
    f, e = _frame(), _epochs()
    cen = (8.5, 12.5, FC)
    full = AD.joined_table(f, e, centers=cen, pro_frame=_pro())
    one = AD.joined_table(f, e, centers=cen, pro_frame=_pro(), channels=("ZERO_TWO_LEFT",),
                          only_center=FC)
    assert one.attrs["n_rows_all_contacts_bands"] == len(full)
    assert set(one.channel) == {"ZERO_TWO_LEFT"} and set(one.center_hz) == {FC}


def test_the_report_reads_the_same_answers_and_states_the_same_row_count():
    f, e = _frame(), _epochs()
    rep = PL.run("P", psd_frame=f, epochs=e, pro_frame=_pro(), candidates=CAND, hemisphere="Left")
    cen = tuple(sorted(set(AD.DEFAULT_BAND_CENTERS_HZ) | {FC}))
    full = AD.joined_table(f, e, centers=cen, pro_frame=_pro())
    assert rep.manifest["n_table_rows"] == len(full)
    e1 = E.actuation_edge(full, channel="ZERO_TWO_LEFT", center_hz=FC, hemisphere="Left")
    e2 = E.state_edge(full, channel="ZERO_TWO_LEFT", center_hz=FC, outcome="nrs",
                      adjust_for_column="amp_mA_Left")
    for got, want in ((rep.edges["E1"], e1), (rep.edges["E2"], e2)):
        assert (got.estimate, got.ci, got.n, got.note) == (want.estimate, want.ci, want.n, want.note)
