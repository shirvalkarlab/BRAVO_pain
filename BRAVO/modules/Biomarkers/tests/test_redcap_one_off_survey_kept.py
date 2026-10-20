"""Portable backend behavior tests."""
import pandas as pd

from modules.Biomarkers.routines.redcap_client import process_redcap

FM = {"instruments": ["stage_1_daily_surveys_vasnrsmpq"], "timestamp_label": "date_time_s1_daily",
      "metric_labels": {"nrs": "pain_nrs_s1_daily"}}


def test_one_off_filing_of_the_survey_is_kept():
    raw = pd.DataFrame({
        "record_id": ["synthetic-survey-participant"] * 4,
        "redcap_repeat_instrument": ["stage_1_daily_surveys_vasnrsmpq", None, "mood_vasaudio_recording", None],
        "date_time_s1_daily": ["2025-01-01 10:00:00", "2025-01-02 11:00:00", None, None],
        "pain_nrs_s1_daily": [2, 7, None, None],
    })
    out = process_redcap(raw, FM)
    assert sorted(out["nrs"].tolist()) == [2, 7]
