"""A daily survey filed once rather than as a repeat is still a rating (the PI, 2026-10-05: "double
check the redcap ingestion", decision 448). On RCS08 one report of 2025-07-30 (NRS, VAS and MPQ scores)
was filed under the REDCap event `stage_2_baseline_arm_1` as a one-off survey, so its repeat label
is empty and the instrument filter dropped it.

Values: a repeat-labelled row and a one-off row carrying the survey's timestamp and a score are both
kept; a row of another instrument, and an empty one-off row, are not."""
import pandas as pd

from modules.Biomarkers.routines.redcap_client import process_redcap

FM = {"instruments": ["stage_1_daily_surveys_vasnrsmpq"], "timestamp_label": "date_time_s1_daily",
      "metric_labels": {"nrs": "pain_nrs_s1_daily"}}


def test_one_off_filing_of_the_survey_is_kept():
    raw = pd.DataFrame({
        "record_id": ["RCS08"] * 4,
        "redcap_repeat_instrument": ["stage_1_daily_surveys_vasnrsmpq", None, "mood_vasaudio_recording", None],
        "date_time_s1_daily": ["2025-07-29 10:00:00", "2025-07-30 11:25:38", None, None],
        "pain_nrs_s1_daily": [5, 6, None, None],
    })
    out = process_redcap(raw, FM)
    assert sorted(out["nrs"].tolist()) == [5, 6]
