"""Nothing dated before the implant date is the patient (the PI, 2026-09-24). Runs on both suites,
so no test takes arguments."""
import numpy as np

try:
    from modules.DecodeCommon import data_start as DS
except ImportError:
    from DecodeCommon import data_start as DS

IMPLANT = 1752689160.0          # 2025-07-16 18:06 UTC, RCS08's device record


def test_the_earliest_dated_device_row_is_the_start_and_undated_rows_are_unknown_not_1970():
    assert DS.earliest_implant_s([0.0, None, IMPLANT, IMPLANT + 86400.0]) == IMPLANT
    assert DS.earliest_implant_s([0.0, None]) == DS.NO_START
    assert DS.earliest_implant_s([]) == DS.NO_START


def test_measurements_before_the_start_are_dropped_and_no_start_drops_nothing():
    t = np.array([IMPLANT - 86400.0 * 28, IMPLANT - 1.0, IMPLANT, IMPLANT + 60.0])
    assert DS.keep_from(t, IMPLANT).tolist() == [False, False, True, True]
    assert DS.keep_from(t, DS.NO_START).all()


def test_the_setting_in_force_at_implant_is_kept_and_moved_to_the_implant_date():
    # four 'Past Therapy' snapshots 30 days apart, then the first clinic change two days after implant
    t = np.array([IMPLANT - 179 * 86400.0, IMPLANT - 149 * 86400.0, IMPLANT - 119 * 86400.0,
                  IMPLANT - 89 * 86400.0, IMPLANT + 2 * 86400.0])
    keep, new = DS.clamp_changes(t, IMPLANT)
    assert keep.tolist() == [False, False, False, True, True]
    assert new[3] == IMPLANT and new[4] == t[4]


def test_clamping_with_no_start_or_nothing_before_it_changes_nothing():
    t = np.array([IMPLANT + 10.0, IMPLANT + 20.0])
    for start in (DS.NO_START, IMPLANT):
        keep, new = DS.clamp_changes(t, start)
        assert keep.all() and (new == t).all()


def test_a_segment_is_cut_on_its_time_axis_and_one_wholly_before_is_gone():
    t = np.array([IMPLANT - 10.0, IMPLANT + 10.0, IMPLANT + 20.0])
    rows = np.arange(6.0).reshape(3, 2)                      # time on axis 0 (a chronic file)
    tt, dd = DS.trim_segment(t, rows, IMPLANT, time_axis=0)
    assert tt.tolist() == [IMPLANT + 10.0, IMPLANT + 20.0] and dd.tolist() == [[2.0, 3.0], [4.0, 5.0]]
    cols = rows.T                                            # time on axis 1 (a chronic-view segment)
    tt, dd = DS.trim_segment(t, cols, IMPLANT, time_axis=1)
    assert dd.tolist() == [[2.0, 4.0], [3.0, 5.0]]
    assert DS.trim_segment(t[:1], rows[:1], IMPLANT, time_axis=0) is None
    assert DS.trim_segment(t, rows, DS.NO_START, time_axis=0)[1] is rows


def test_a_listed_row_before_the_start_goes_unless_it_runs_past_it():
    assert DS.listed_date(IMPLANT + 5.0, IMPLANT) == IMPLANT + 5.0
    assert DS.listed_date(IMPLANT - 5.0, IMPLANT) is None
    assert DS.listed_date(IMPLANT - 5.0, IMPLANT, spans_start=True) == IMPLANT
    assert DS.listed_date(IMPLANT - 5.0, DS.NO_START) == IMPLANT - 5.0
