"""The lab's clinic-and-home testing workbooks as a second, independent pain stream
(`StimOptimizer.clinic_pain`). Constructed workbooks, written with openpyxl to a temporary
directory, so every assertion is checked against a real .xlsx file read back through the real
parser rather than against a hand-built DataFrame.
"""
import datetime

import numpy as np
import pandas as pd
import pytest

openpyxl = pytest.importorskip("openpyxl")

from StimOptimizer import bravo_service as BS
from StimOptimizer import clinic_pain as CP
from StimOptimizer import stage1_openloop as S1

# =====================================================================================
# Workbook construction helpers
# =====================================================================================

GENERIC_HEADER = ["Group", "Contacts", "sEEG Contacts", "Amp (mA)", "Rate (Hz)", "PW (µs)",
                 "Threshold", "Duration (s)", "Side Effect?", "Timestamp",
                 "Movement/Change point", "General Notes", "Overall", "Head", "Back",
                 "Left Leg", "Left Foot", "Right Leg", "Right Foot"]


def _write_generic_workbook(path, rows, *, header=GENERIC_HEADER, header_row=11):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Stim Testing"
    for c, name in enumerate(header, start=1):
        ws.cell(row=header_row, column=c, value=name)
    for i, row in enumerate(rows):
        r = header_row + 1 + i
        for c, name in enumerate(header, start=1):
            if name in row:
                ws.cell(row=r, column=c, value=row[name])
    wb.save(str(path))
    return path


def _parse(path):
    df = CP.parse_workbook(str(path))
    return df, df.attrs["counts"]


# =====================================================================================
# The two-row step: a ramp/hold row, then a test-period row carrying the pain score.
# =====================================================================================

def test_two_row_step_inherits_settings_from_the_ramp_row(tmp_path):
    rows = [
        {"Group": "A", "Contacts": "1+2-9-10-", "Amp (mA)": "1.4/3.0", "Rate (Hz)": 55.0,
         "PW (µs)": "60/150", "Duration (s)": 120.0,
         "Timestamp": datetime.time(12, 19, 6)},
        {"Duration (s)": 120.0, "Timestamp": datetime.time(12, 21, 6),
         "Overall": 6.0, "Left Leg": 5.0},
    ]
    path = _write_generic_workbook(tmp_path / "wb1.xlsx", rows)
    df, counts = _parse(path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["amp_mA_Left"] == 1.4
    assert row["amp_mA_Right"] == 3.0
    assert row["freq_hz"] == 55.0
    assert row["pw_us_Left"] == 60.0
    assert row["pw_us_Right"] == 150.0
    assert row["overall"] == 6.0
    assert row["left_leg"] == 5.0
    assert counts.n_steps == 1          # one row supplied a setting
    assert counts.n_with_pain == 1      # one row carried a pain score
    assert counts.n_skipped_no_setting == 0


def test_score_on_the_first_row_is_also_read(tmp_path):
    """Some workbooks put the pain score on the SAME row as the setting."""
    rows = [
        {"Group": "B", "Contacts": "C+1-9-10-", "Amp (mA)": 0.0, "Rate (Hz)": 165.0,
         "PW (µs)": "60/160", "Duration (s)": 240.0,
         "Timestamp": datetime.time(12, 22, 34), "Overall": 8.0, "Back": 8.0,
         "Left Leg": 7.0},
    ]
    path = _write_generic_workbook(tmp_path / "wb2.xlsx", rows)
    df, counts = _parse(path)
    assert len(df) == 1
    assert df.iloc[0]["amp_mA_Left"] == 0.0 and df.iloc[0]["amp_mA_Right"] == 0.0
    assert df.iloc[0]["back"] == 8.0
    assert counts.n_with_pain == 1


# =====================================================================================
# Bilateral cells: "L x / R y", "x/y" and "x&y" all give LEFT-before-the-separator.
# =====================================================================================

@pytest.mark.parametrize("i,amp_cell,expect_left,expect_right", [
    (0, "L 1.4 / R 3.0", 1.4, 3.0),
    (1, "0.0/2.5", 0.0, 2.5),
    (2, "0.5&2.5", 0.5, 2.5),
])
def test_bilateral_amp_forms_keep_left_before_the_separator(tmp_path, i, amp_cell, expect_left,
                                                             expect_right):
    rows = [
        {"Group": "A", "Contacts": "1+2-9-10-", "Amp (mA)": amp_cell, "Rate (Hz)": 55.0,
         "PW (µs)": "60/150", "Duration (s)": 120.0,
         "Timestamp": datetime.time(12, 0, 0), "Overall": 5.0},
    ]
    path = _write_generic_workbook(tmp_path / f"wb_bilateral_{i}.xlsx", rows)
    df, counts = _parse(path)
    assert len(df) == 1
    assert df.iloc[0]["amp_mA_Left"] == pytest.approx(expect_left)
    assert df.iloc[0]["amp_mA_Right"] == pytest.approx(expect_right)


# =====================================================================================
# The "Timastamp" / "PW (ms)" header typos, tolerated rather than corrected upstream.
# =====================================================================================

def test_the_timastamp_and_pw_ms_typos_are_tolerated(tmp_path):
    typo_header = ["Group", "Contacts", "sEEG Contacts", "Amp (mA)", "Rate (Hz)", "PW (ms)",
                   "Duration (s)", "Side Effect? ", "Timastamp", "Verbal", "Head", "Back",
                   "Left Leg", "Left Foot", "General Notes"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Stim Testing"
    for c, name in enumerate(typo_header, start=1):
        ws.cell(row=11, column=c, value=name)
    row = {"Group": "B", "Contacts": "c+ 9-10-", "Amp (mA)": 0.5, "Rate (Hz)": 110.0,
          "PW (ms)": 100.0, "Duration (s)": 30.0, "Timastamp": datetime.time(12, 45, 1),
          "Verbal": 8.0, "Left Leg": 7.0}
    for c, name in enumerate(typo_header, start=1):
        if name in row:
            ws.cell(row=12, column=c, value=row[name])
    path = tmp_path / "wb_typo.xlsx"
    wb.save(str(path))
    df, counts = _parse(path)
    assert len(df) == 1
    r = df.iloc[0]
    # "PW (ms)" carries MICROSECOND values despite the label -- taken as-is, never converted.
    assert r["pw_us_Left"] == 100.0 and r["pw_us_Right"] == 100.0
    assert r["overall"] == 8.0          # "Verbal" is the same field as "Overall"
    assert r["left_leg"] == 7.0
    assert pd.notna(r["t_local"])


# =====================================================================================
# A prose pain description is counted, never parsed into a number.
# =====================================================================================

def test_prose_pain_description_is_counted_not_parsed(tmp_path):
    rows = [
        {"Group": "B", "Contacts": "C+ 9-10-", "Amp (mA)": 1.0, "Rate (Hz)": 110.0,
         "PW (µs)": 100.0, "Duration (s)": 30.0, "Timestamp": datetime.time(10, 54, 48),
         "General Notes": "Left leg: 8->0, feels much better now"},
    ]
    path = _write_generic_workbook(tmp_path / "wb_prose.xlsx", rows)
    df, counts = _parse(path)
    # no pain COLUMN carries a number on this row, so no step is emitted at all
    assert len(df) == 0
    assert counts.n_unparsed_prose == 1


# =====================================================================================
# Missing right-side columns (the three 2025 workbooks) give NaN, not zero.
# =====================================================================================

def test_missing_right_side_columns_give_nan(tmp_path):
    header = ["Group", "Contacts", "sEEG Contacts", "Amp (mA)", "Rate (Hz)", "PW (µs)",
             "Duration (s)", "Side Effect", "Timestamp", "Verbal", "Head", "Back",
             "Left Leg", "Left Foot", "General Notes"]
    rows = [
        {"Group": "B", "Contacts": "c+ 9-10-", "Amp (mA)": 0.5, "Rate (Hz)": 110.0,
         "PW (µs)": 100.0, "Duration (s)": 30.0, "Timestamp": datetime.time(12, 45, 1),
         "Verbal": 8.0, "Left Leg": 7.0},
    ]
    path = _write_generic_workbook(tmp_path / "wb_noright.xlsx", rows, header=header)
    df, counts = _parse(path)
    assert len(df) == 1
    r = df.iloc[0]
    assert r["overall"] == 8.0 and r["left_leg"] == 7.0
    assert pd.isna(r["right_leg"]) and pd.isna(r["right_foot"])


# =====================================================================================
# A skipped row: a pain score with no setting ever seen before it in the file.
# =====================================================================================

def test_a_pain_score_with_no_prior_setting_is_skipped_not_guessed(tmp_path):
    rows = [
        {"Overall": 8.0, "Back": 8.0},   # no Amp/Contacts anywhere above this row
        {"Group": "A", "Contacts": "1+2-", "Amp (mA)": 1.0, "Rate (Hz)": 55.0,
         "PW (µs)": 60.0, "Duration (s)": 60.0, "Timestamp": datetime.time(11, 0, 0),
         "Overall": 5.0},
    ]
    path = _write_generic_workbook(tmp_path / "wb_skip.xlsx", rows)
    df, counts = _parse(path)
    assert len(df) == 1
    assert counts.n_skipped_no_setting == 1
    assert counts.n_with_pain == 1


# =====================================================================================
# The Excel date-conversion trap: "8/10" typed into an unformatted cell becomes a real date
# (month 8, day 10), found by reading the real September 2025 and June 2026 workbooks.
# =====================================================================================

def test_a_pain_score_auto_converted_to_an_excel_date_is_read_back(tmp_path):
    rows = [
        {"Group": "B", "Contacts": "c+ 9-10-", "Amp (mA)": 2.0, "Rate (Hz)": 110.0,
         "PW (µs)": 100.0, "Duration (s)": 30.0, "Timestamp": datetime.time(10, 59, 50),
         # Excel's own auto-conversion of the text "8/10": a date object, month=8, day=10.
         "Overall": datetime.datetime(2025, 8, 10), "Back": datetime.datetime(2025, 7, 10)},
    ]
    path = _write_generic_workbook(tmp_path / "wb_date.xlsx", rows)
    df, counts = _parse(path)
    assert len(df) == 1
    assert df.iloc[0]["overall"] == 8.0
    assert df.iloc[0]["back"] == 7.0


def test_a_date_that_does_not_fit_the_day_ten_shape_is_left_unparsed():
    assert CP._parse_pain_value(datetime.datetime(2025, 8, 15)) is None
    assert CP._parse_pain_value(datetime.datetime(2025, 11, 10)) is None
    assert CP._parse_pain_value(datetime.datetime(2025, 3, 10)) == 3.0


def test_n_over_10_string_form_is_read_as_the_numerator():
    assert CP._parse_pain_value("9/10") == 9.0
    assert CP._parse_pain_value("0") == 0.0
    assert CP._parse_pain_value(None) is None
    assert CP._parse_pain_value("not a score") is None


# =====================================================================================
# The clinic-stream fit: the same per-rate two-input surface as the REDCap stream.
# =====================================================================================

def _clinic_epoch_frame(*, slope_per_mA=0.0, noise_sd=0.3, n_reps=3, seed=0):
    """One rate (55 Hz), a 5x5 (left, right) current grid, ONE clinic step per cell per
    repetition -- mirrors `test_stage1._current_effect_matrix`, but in the acute clinic-testing
    frame's own column names (`pain_Left_Leg`), n=1 per epoch, and short clinic-scale durations."""
    rng = np.random.default_rng(seed)
    levels = [0.0, 1.0, 2.0, 3.0, 4.0]
    rows, ep = [], 0
    for rep in range(int(n_reps)):
        for l in levels:
            for r in levels:
                ep += 1
                pain = 6.0 - float(slope_per_mA) * (l + r) + noise_sd * rng.standard_normal()
                rows.append(dict(epoch=float(ep), freq_hz=55.0, pw_us_Left=60.0,
                                 pw_us_Right=160.0, amp_mA_Left=l, amp_mA_Right=r, n=1.0,
                                 dur_h=60.0 / 3600.0, pain_Left_Leg=float(pain),
                                 pain_Left_Leg_sd=np.nan))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2026-07-01", periods=len(d), freq="2min", tz="UTC")
    return d


def test_clinic_stream_fit_resolves_a_real_current_effect(monkeypatch):
    # n_reps=6: `n` is 1 per clinic step (real clinic steps, not pooled REDCap epochs), and the
    # honest-current coverage check sums `n` per (left, right) current pair, requiring at least 5
    # -- so each of the 25 current combinations needs at least 5 repeated clinic steps behind it.
    d = _clinic_epoch_frame(slope_per_mA=1.2, noise_sd=0.2, n_reps=6, seed=1)
    incumbent = float(d.iloc[0]["epoch"])
    res = S1.run_stage1(d, hemispheres=("Left", "Right"), primary_item="left_leg",
                        incumbent_epoch=incumbent, pooled_var_override=1.0,
                        min_tolerated_h=CP.CLINIC_MIN_TOLERATED_H)
    ((_key, sl),) = res.slices.items()
    rs = sl.rate_strata[55.0]
    assert rs.fitted is True
    assert rs.resolution["resolved"] is True, rs.resolution["sentence"]


def test_clinic_stream_fit_does_not_resolve_with_no_current_effect():
    d = _clinic_epoch_frame(slope_per_mA=0.0, noise_sd=2.0, n_reps=6, seed=2)
    incumbent = float(d.iloc[0]["epoch"])
    res = S1.run_stage1(d, hemispheres=("Left", "Right"), primary_item="left_leg",
                        incumbent_epoch=incumbent, pooled_var_override=1.0,
                        min_tolerated_h=CP.CLINIC_MIN_TOLERATED_H)
    ((_key, sl),) = res.slices.items()
    rs = sl.rate_strata[55.0]
    assert rs.fitted is True
    assert rs.resolution["resolved"] is False


def _redcap_shaped_epoch_frame(*, slope_per_mA, noise_sd, n_per_cell=15, n_reps=3, seed=0):
    """The exact recipe `test_stage1._current_effect_matrix` uses, proven to resolve there, in
    the acute clinic-testing frame's own column names -- used here only to give the GLUE LAYER
    (`_clinic_stream_stage1_block`, the response serialisation) a design already known to
    resolve, isolating the assertion under test -- that every serialised row carries
    `source == "clinic_sheets"` -- from how strong a signal a GP fit happens to need."""
    rng = np.random.default_rng(seed)
    levels = [0.0, 1.0, 2.0, 3.0, 4.0]
    rows, ep = [], 0
    for _rep in range(int(n_reps)):
        for l in levels:
            for r in levels:
                ep += 1
                pain = 6.0 - float(slope_per_mA) * (l + r) + noise_sd * rng.standard_normal()
                rows.append(dict(epoch=float(ep), freq_hz=55.0, pw_us_Left=60.0,
                                 pw_us_Right=160.0, amp_mA_Left=l, amp_mA_Right=r,
                                 n=float(n_per_cell), dur_h=200.0, pain_Left_Leg=float(pain),
                                 pain_Left_Leg_sd=1.0))
    d = pd.DataFrame(rows)
    d["t0"] = pd.date_range("2026-07-01", periods=len(d), freq="6h", tz="UTC")
    return d


def test_clinic_rate_strata_rows_carry_source_clinic_sheets(monkeypatch):
    """`bravo_service._clinic_stream_stage1_block` -- the real glue the response serialises --
    tags every row with `source == "clinic_sheets"` and never touches the REDCap-based fit."""
    stub_steps = pd.DataFrame({"file": ["x"] * 3, "visit_date": ["v1", "v1", "v2"],
                               "setting": ["clinic", "clinic", "home"],
                               "freq_hz": [55.0, 55.0, 110.0],
                               "amp_mA_Left": [1.0, 2.0, 1.0], "amp_mA_Right": [1.0, 1.0, 2.0],
                               "left_leg": [5.0, 4.0, 6.0], "overall": [np.nan] * 3})
    monkeypatch.setattr(BS.CLPAIN, "load_clinic_steps",
                        lambda participant, **kw: (stub_steps, {"signature_key": "test"}, None))
    monkeypatch.setattr(BS.CLPAIN, "epoch_frame_from_steps",
                        lambda steps, **kw: _redcap_shaped_epoch_frame(
                            slope_per_mA=1.2, noise_sd=0.3, seed=3))
    block = BS._clinic_stream_stage1_block(
        participant=object(), hemispheres=("Left", "Right"),
        safety_ceiling_by_hemisphere=None, redcap_pooled_var=1.0)
    assert block["clinic_stream"]["available"] is True
    rows = block["rate_strata_clinic"]
    assert len(rows) >= 1
    assert all(r["source"] == "clinic_sheets" for r in rows)
    fitted = [r for r in rows if r["fitted"]]
    assert any(r.get("resolved") for r in fitted)


def _steps_from_epoch_frame(ep):
    """A minimal `steps`-shaped frame (one row per pain observation) that
    `epoch_frame_from_steps` will re-derive back into (approximately) the same epochs, for testing
    the glue layer without a real workbook."""
    rows = []
    for _, r in ep.iterrows():
        rows.append(dict(visit_date="test visit", setting="clinic", file="wb.xlsx", sha256="x",
                         t_local=None, t_utc=r["t0"], amp_mA_Left=r["amp_mA_Left"],
                         amp_mA_Right=r["amp_mA_Right"], freq_hz=r["freq_hz"],
                         pw_us_Left=r["pw_us_Left"], pw_us_Right=r["pw_us_Right"],
                         contacts_raw="c+", duration_s=60.0, side_effect_score=np.nan,
                         overall=np.nan, head=np.nan, back=np.nan,
                         left_leg=r["pain_Left_Leg"], left_foot=np.nan, right_leg=np.nan,
                         right_foot=np.nan, notes=None, row_index=0))
    return pd.DataFrame(rows)


def test_epoch_frame_pools_repeated_identical_settings():
    """`epoch_frame_from_steps` collapses a setting tested more than once into ONE epoch with
    n = the repeat count, so `pooled_within_epoch_var` has something to pool."""
    steps = pd.DataFrame([
        dict(visit_date="v1", setting="clinic", file="f", sha256="x", t_local=None,
            t_utc=pd.Timestamp("2026-01-01", tz="UTC"), amp_mA_Left=1.0, amp_mA_Right=1.0,
            freq_hz=55.0, pw_us_Left=60.0, pw_us_Right=60.0, contacts_raw="c",
            duration_s=60.0, side_effect_score=np.nan, overall=np.nan, head=np.nan,
            back=np.nan, left_leg=v, left_foot=np.nan, right_leg=np.nan, right_foot=np.nan,
            notes=None, row_index=i)
        for i, v in enumerate([5.0, 6.0, 4.0])
    ])
    ep = CP.epoch_frame_from_steps(steps)
    assert len(ep) == 1
    assert ep.iloc[0]["n"] == 3
    assert ep.iloc[0]["pain_Left_Leg"] == pytest.approx(5.0)
    assert ep.iloc[0]["pain_Left_Leg_sd"] == pytest.approx(1.0)
