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
# A written correction in parentheses ("L 100 (did 110 accidentally) / R 150", the real cell
# G16 of the 2026-09-02 in-clinic workbook) must yield the DELIVERED value, not the pre-parenthesis
# planned one, and must not be silently dropped (P-13).
# =====================================================================================

def test_a_pw_correction_in_parentheses_gives_the_delivered_left_value(tmp_path):
    rows = [
        {"Group": "A", "Contacts": "1+2-9-10-", "Amp (mA)": "3.5/3.0", "Rate (Hz)": 55.0,
         "PW (µs)": "L 100 (did 110 accidentally) / R 150", "Duration (s)": 120.0,
         "Timestamp": datetime.time(12, 23, 6), "Overall": 5.0},
    ]
    path = _write_generic_workbook(tmp_path / "wb_pw_correction.xlsx", rows)
    df, counts = _parse(path)
    assert len(df) == 1
    row = df.iloc[0]
    # the patient actually received 110 us on the left, not the planned 100
    assert row["pw_us_Left"] == 110.0
    assert row["pw_us_Right"] == 150.0


def test_an_amp_correction_in_parentheses_gives_the_delivered_right_value(tmp_path):
    rows = [
        {"Group": "A", "Contacts": "1+2-9-10-", "Amp (mA)": "L 1.0 / R 2.0 (actually 2.5)",
         "Rate (Hz)": 55.0, "PW (µs)": "60/150", "Duration (s)": 120.0,
         "Timestamp": datetime.time(12, 0, 0), "Overall": 5.0},
    ]
    path = _write_generic_workbook(tmp_path / "wb_amp_correction.xlsx", rows)
    df, counts = _parse(path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["amp_mA_Left"] == 1.0
    assert row["amp_mA_Right"] == 2.5


def test_a_correction_worded_should_be_is_also_read(tmp_path):
    rows = [
        {"Group": "A", "Contacts": "1+2-9-10-", "Amp (mA)": "L 0.5 (typo, should be 1.5) / R 1.0",
         "Rate (Hz)": 55.0, "PW (µs)": "60/150", "Duration (s)": 120.0,
         "Timestamp": datetime.time(12, 0, 0), "Overall": 5.0},
    ]
    path = _write_generic_workbook(tmp_path / "wb_amp_shouldbe.xlsx", rows)
    df, counts = _parse(path)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["amp_mA_Left"] == 1.5
    assert row["amp_mA_Right"] == 1.0


def test_an_adapting_range_cell_is_not_mistaken_for_a_correction(tmp_path):
    """"Adapting (0 to1.6 & 0 to 1.2)" -- a real cell (RCS08, April 2026 in-clinic sheet) -- names
    an adaptive stimulation RANGE, not a left/right pair. The "&" and "/" that can appear inside
    such a parenthetical are not the bilateral separator, and must not be read as one: an earlier
    version of the P-13 fix split on them and invented an amplitude (0.0) that was never in the
    cell. The whole cell has no usable single value and must stay unparsed, exactly as before the
    fix (regression test, found live on RCS08 rather than in a unit test)."""
    rows = [
        {"Group": "A", "Contacts": "1+2-9-10-", "Amp (mA)": "Adapting (0 to1.6 & 0 to 1.2)",
         "Rate (Hz)": 55.0, "PW (µs)": "60/150", "Duration (s)": 120.0,
         "Timestamp": datetime.time(12, 0, 0), "Overall": 5.0},
        {"Group": "A", "Contacts": "1+2-9-10-", "Amp (mA)": "Adapting (1.8/1.2)",
         "Rate (Hz)": 55.0, "PW (µs)": "60/150", "Duration (s)": 120.0,
         "Timestamp": datetime.time(12, 5, 0), "Overall": 6.0},
    ]
    path = _write_generic_workbook(tmp_path / "wb_adapting.xlsx", rows)
    df, counts = _parse(path)
    # neither row ever set a real amplitude, so neither carries a pain score with a setting
    assert len(df) == 0
    assert counts.n_skipped_no_setting == 2


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
    # One visit day per repetition (decision 184: the coverage check counts the days a current
    # pair was rated on, and one afternoon of steps is one occasion however many steps it holds).
    per_rep = len(levels) ** 2
    d["t0"] = [pd.Timestamp("2026-07-01", tz="UTC") + pd.Timedelta(days=i // per_rep, minutes=2 * (i % per_rep))
               for i in range(len(d))]
    d["rating_days"] = [(t.strftime("%Y-%m-%d"),) for t in d["t0"]]
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
    d["rating_days"] = [(t.strftime("%Y-%m-%d"),) for t in d["t0"]]      # decision 184
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


def _scored_steps(scores, amps_left, amps_right=None, rate=55.0):
    """One clinic step per (score, current) pair, a left-leg score on every row so the epoch
    frame keeps them, currents in mA; `amps_right` defaults to 0 (a left-only ladder)."""
    amps_right = [0.0] * len(scores) if amps_right is None else amps_right
    rows = []
    for i, (sc, aL, aR) in enumerate(zip(scores, amps_left, amps_right)):
        rows.append(dict(visit_date="v1", setting="clinic", file="f", sha256="x", t_local=None,
                         t_utc=pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=i),
                         amp_mA_Left=aL, amp_mA_Right=aR, freq_hz=rate, pw_us_Left=60.0,
                         pw_us_Right=60.0, contacts_raw="c", duration_s=60.0,
                         side_effect_score=sc, overall=np.nan, head=np.nan, back=np.nan,
                         left_leg=5.0, left_foot=np.nan, right_leg=np.nan, right_foot=np.nan,
                         notes=None, row_index=i))
    return pd.DataFrame(rows)


def test_sheet_score_2_is_mild_persistent_and_costs_more_than_mild():
    """The sheet's own printed ladder is 0 none, 1 mild, 2 mild persistent, 3 moderate, 4 avoid.
    Until 2026-09-15 a 2 was folded into "mild"; the PI ruled it costs more (2.0 NRS points)."""
    from StimOptimizer.routines import objective as OBJ
    assert CP.SIDE_EFFECT_SEVERITY_LABEL[2] == "mild_persistent"
    assert CP.SIDE_EFFECT_SEVERITY_LABEL[1] == "mild"
    ep = CP.epoch_frame_from_steps(_scored_steps([1.0, 2.0, 0.0], [1.0, 2.0, 3.0]))
    by_amp = {float(r["amp_mA_Left"]): r["se_severity"] for _, r in ep.iterrows()}
    assert by_amp == {1.0: "mild", 2.0: "mild_persistent", 3.0: "none"}
    ep["epoch"] = np.arange(len(ep), dtype=float)
    d = OBJ.build_objective(ep, incumbent_epoch=0.0, pooled_var_override=1.0)
    assert dict(zip(d["amp_mA_Left"].astype(float), d["J_SE"])) == {1.0: 1.0, 2.0: 2.0, 3.0: 0.0}


# ---------------------------------------------------------------------------------------------
# amplitude versus reported severity, recomputed from the record on every request (2026-09-15,
# the PI: "recompute always") -- never a number typed into a docstring
# ---------------------------------------------------------------------------------------------
def test_amplitude_severity_evidence_is_not_assessable_below_the_row_floor():
    ev = CP.amplitude_severity_evidence(_scored_steps([0.0, 1.0, 0.0], [1.0, 2.0, 3.0]))
    assert ev["assessable"] is False
    assert ev["n_scored_stim_on"] == 3
    assert str(CP.SEVERITY_EVIDENCE_MIN_ROWS) in ev["reason"]
    assert "not assessable" in ev["sentence"]
    assert "-0.013" not in ev["sentence"]


def test_amplitude_severity_evidence_is_not_assessable_when_every_score_is_the_same():
    n = CP.SEVERITY_EVIDENCE_MIN_ROWS + 2
    ev = CP.amplitude_severity_evidence(_scored_steps([0.0] * n, list(np.linspace(1, 4, n))))
    assert ev["assessable"] is False
    assert "no variation" in ev["reason"]


def test_amplitude_severity_evidence_reports_a_rising_ladder_with_its_numbers():
    n = CP.SEVERITY_EVIDENCE_MIN_ROWS + 4
    amps = list(np.linspace(0.5, 4.5, n))
    scores = [0.0 if a < 2 else (1.0 if a < 3 else (2.0 if a < 4 else 3.0)) for a in amps]
    ev = CP.amplitude_severity_evidence(_scored_steps(scores, amps))
    assert ev["assessable"] is True
    assert ev["rho"] > 0.9 and ev["p"] < 0.01
    assert ev["n_scored_stim_on"] == n
    assert ev["n_above_4mA"] == sum(a > 4.0 for a in amps)
    assert ev["current_used"] == "the higher of the two sides' currents on each step"
    assert f"{ev['rho']:+.2f}" in ev["sentence"] and str(n) in ev["sentence"]
    assert "rises" in ev["sentence"]


def test_amplitude_severity_evidence_ignores_unscored_rows_and_stimulation_off():
    n = CP.SEVERITY_EVIDENCE_MIN_ROWS
    scores = [1.0] * n + [np.nan, 3.0]
    amps = list(np.linspace(1, 4, n)) + [4.5, 0.0]           # unscored; scored but stim off
    ev = CP.amplitude_severity_evidence(_scored_steps(scores, amps))
    assert ev["n_scored_stim_on"] == n
    assert ev["n_above_4mA"] == 0


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


# ---------------------------------------------------------------------------------------------
# the reference setting (2026-09-15): the clinic stream's zero is the device's setting in force
# wherever a clinic step exists at that rate and those pulse widths, else the last clinic step,
# said plainly
# ---------------------------------------------------------------------------------------------
def _ep_frame():
    import pandas as pd
    return pd.DataFrame([
        dict(epoch=0.0, freq_hz=55.0, amp_mA_Left=1.0, amp_mA_Right=1.0, pw_us_Left=100.0,
             pw_us_Right=150.0, n=2, t0=pd.Timestamp("2026-01-01T10:00Z")),
        dict(epoch=1.0, freq_hz=55.0, amp_mA_Left=3.0, amp_mA_Right=2.0, pw_us_Left=100.0,
             pw_us_Right=150.0, n=5, t0=pd.Timestamp("2026-02-01T10:00Z")),
        dict(epoch=2.0, freq_hz=55.0, amp_mA_Left=3.0, amp_mA_Right=2.0, pw_us_Left=60.0,
             pw_us_Right=160.0, n=9, t0=pd.Timestamp("2026-03-01T10:00Z")),
        dict(epoch=3.0, freq_hz=145.0, amp_mA_Left=1.0, amp_mA_Right=0.5, pw_us_Left=100.0,
             pw_us_Right=150.0, n=1, t0=pd.Timestamp("2026-04-01T10:00Z")),
    ])


def test_reference_is_the_nearest_clinic_step_at_the_in_force_rate_and_pulse_widths():
    from StimOptimizer import clinic_pain as CP
    in_force = {"Left": {"rate_hz": 55.0, "pulse_width_us": 100.0, "amplitude_mA": 3.0},
                "Right": {"rate_hz": 55.0, "pulse_width_us": 150.0, "amplitude_mA": 2.5}}
    epoch, info = CP.reference_epoch_for(_ep_frame(), in_force)
    # epoch 1 (100/150, L3/R2) is 0.5 mA away; epoch 0 is 2.5 mA away; epoch 2 has the wrong pulse
    # widths despite identical currents; epoch 3 is the wrong rate.
    assert epoch == 1.0
    assert info["source"] == "nearest_clinic_step_to_setting_in_force"
    assert info["distance_mA"] == 0.5
    assert info["n_steps_at_reference"] == 5
    assert "0.50 mA from the L 3 / R 2.5 mA in force" in info["sentence"]


def test_reference_falls_back_to_the_last_step_and_says_so_when_nothing_matches():
    from StimOptimizer import clinic_pain as CP
    in_force = {"Left": {"rate_hz": 110.0, "pulse_width_us": 100.0, "amplitude_mA": 3.0},
                "Right": {"rate_hz": 110.0, "pulse_width_us": 150.0, "amplitude_mA": 2.5}}
    epoch, info = CP.reference_epoch_for(_ep_frame(), in_force)
    assert epoch == 3.0 and info["source"] == "last_clinic_step"
    assert info["rate_hz"] == 145.0
    assert "no clinic step was ever run at the device's setting in force (110 Hz" in info["sentence"]
    assert "NOT the setting in force" in info["sentence"]


def test_reference_with_no_in_force_uses_the_last_step_and_names_the_reason():
    from StimOptimizer import clinic_pain as CP
    epoch, info = CP.reference_epoch_for(_ep_frame(), None)
    assert epoch == 3.0 and info["source"] == "last_clinic_step"
    assert "was not available to reference to" in info["sentence"]


def test_sheet_ratings_kind_matches_the_ingest():
    """Decision 186: the Biomarkers heat maps read the ingested clinic steps under a kind name
    spelled in their own module (Biomarkers may not import StimOptimizer). The two spellings must
    stay one kind, or the switch would quietly read nothing."""
    import os as _os
    import re as _re
    src = open(_os.path.join(_os.path.dirname(__file__), "..", "..", "Biomarkers", "bravo_service.py")).read()
    m = _re.search(r'^CLINIC_SHEET_STEPS_KIND = "([^"]+)"', src, _re.M)     # read, not imported: Django
    assert m and m.group(1) == CP.CLINIC_PAIN_KIND

# ---------------------------------------------------------------------------------------------
# the clinic fit follows the SITE it is asked for (the PI, 2026-09-22, ruling 4 of decision 233)
# ---------------------------------------------------------------------------------------------
def test_the_clinic_fit_asks_stage_one_for_the_site_it_was_given_not_always_the_left_leg(monkeypatch):
    """Until 2026-09-22 `fit_clinic_rate_strata` hard-coded `primary_item="left_leg"` where it calls
    Stage 1, so a request for another site came back with the LEFT LEG's numbers under that site's
    label -- the wrong-key defect CLAUDE.md rule 11 exists for, found by running the back site and
    the left leg and seeing identical output. The epoch frame is site-agnostic (it carries every
    site's column and its SD), so the site is decided at the fit, and that is what this pins."""
    steps = pd.DataFrame([
        dict(visit_date="v1", setting="clinic", file="f", sha256="x", t_local=None,
             t_utc=pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(hours=i),
             amp_mA_Left=float(a), amp_mA_Right=1.0, freq_hz=55.0, pw_us_Left=60.0,
             pw_us_Right=160.0, contacts_raw="c", duration_s=60.0, side_effect_score=np.nan,
             overall=np.nan, head=np.nan, back=float(9 - i), left_leg=float(i),
             left_foot=np.nan, right_leg=np.nan, right_foot=np.nan, notes=None, row_index=i)
        for i, a in enumerate([0.0, 1.0, 2.0, 3.0])
    ])
    # the frame carries both sites, with different scores, so a fit that follows the site cannot
    # produce the same answer for the two
    ep = CP.epoch_frame_from_steps(steps)
    assert list(ep["pain_Left_Leg"]) != list(ep["pain_Back"])

    seen = []
    from StimOptimizer import stage1_openloop as S1

    def _capture(frame, **kw):
        seen.append(kw.get("primary_item"))
        raise RuntimeError("stopped: the call is what this test is about")

    monkeypatch.setattr(S1, "run_stage1", _capture)
    monkeypatch.setattr(CP, "load_clinic_steps",
                        lambda *a, **k: (steps, {"signature_key": "k"}, None))
    got = CP.fit_clinic_rate_strata("uid", primary_item="back")
    assert seen == ["back"], f"the fit must ask Stage 1 for the site it was given, asked for {seen}"
    assert got["available"] is False and "stopped" in (got["reason"] or "")

    seen.clear()
    CP.fit_clinic_rate_strata("uid")                       # the default is unchanged
    assert seen == ["left_leg"]
