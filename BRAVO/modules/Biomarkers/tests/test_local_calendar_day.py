"""Review B1 (2026-09-12): "the same calendar day" is the CALIFORNIA day, not the UTC day.

The chronic pain detector joins each 10-minute brain-signal sample to the pain ratings filed on
the same calendar day, and the pain cut is computed on one value per day. Both used to read the
day off the UTC instant, whose boundary is 4-5 pm in California, so a rating filed at 18:00 local
was averaged into the NEXT day's samples. Every test here asserts a VALUE that comes out one way
under the California day and the other way under the UTC day; the fixtures are chosen so that the
old rule would fail each assertion, not merely produce a different shape.

Runs in the container (plain asserts) and under pytest.
"""
import sys
import pathlib
import datetime as _dt

import numpy as np
import pandas as pd

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.Biomarkers import adapter
from modules.Biomarkers import pipeline
from modules.Biomarkers.routines import local_time


def _utc(s):
    return pd.Timestamp(s)


def _epoch(s):
    return float(pd.Timestamp(s).timestamp())


# A rating at 2025-07-21 18:00 California (PDT, UTC-7) is 2025-07-22 01:00 UTC.
RATING_UTC = "2025-07-22 01:00:00"
# Two chronic samples at local noon on the 21st and the 22nd: 19:00 UTC each day.
SAMPLE_21_UTC = "2025-07-21 19:00:00"
SAMPLE_22_UTC = "2025-07-22 19:00:00"


def _pro_df():
    return pd.DataFrame({"date_time_s1_daily": ["2025-07-21 18:00:00"], "nrs": [7.0],
                         "_pro_time_utc": pd.to_datetime([RATING_UTC])})


def _chronic():
    return {"Time": np.array([_epoch(SAMPLE_21_UTC), _epoch(SAMPLE_22_UTC)]),
            "Data": np.array([[100.0, 2.0], [110.0, 2.0]]),
            "ChannelNames": ["L LFP", "L Amplitude"], "SamplingRate": -1,
            "StartTime": _epoch(SAMPLE_21_UTC), "Duration": 0.0}


def test_the_zone_is_named_once_and_the_helper_reads_it():
    assert local_time.PRO_LOCAL_TZ == "America/Los_Angeles"
    # Scalar, Series, list: the same date, and NaT stays empty rather than becoming a date.
    assert local_time.local_calendar_day(_utc(RATING_UTC)) == _dt.date(2025, 7, 21)
    ser = local_time.local_calendar_day(pd.Series([_utc(RATING_UTC), pd.NaT]))
    assert ser.iloc[0] == _dt.date(2025, 7, 21) and pd.isna(ser.iloc[1])
    idx = local_time.local_calendar_day([_utc(RATING_UTC), pd.NaT])
    assert idx[0] == _dt.date(2025, 7, 21) and idx[1] is None
    assert local_time.local_calendar_day(pd.NaT) is None
    # A tz-aware input is converted from its own zone, not re-read as UTC.
    aware = pd.Timestamp("2025-07-21 18:00:00", tz="America/Los_Angeles")
    assert local_time.local_calendar_day(aware) == _dt.date(2025, 7, 21)


def test_the_boundary_follows_daylight_saving():
    """The day turns over at 07:00 UTC in summer (PDT) and 08:00 UTC in winter (PST)."""
    d = local_time.local_calendar_day
    assert d(_utc("2025-07-22 06:59:59")) == _dt.date(2025, 7, 21)
    assert d(_utc("2025-07-22 07:00:00")) == _dt.date(2025, 7, 22)
    assert d(_utc("2025-01-22 07:59:59")) == _dt.date(2025, 1, 21)
    assert d(_utc("2025-01-22 08:00:00")) == _dt.date(2025, 1, 22)


def test_an_evening_rating_joins_that_days_sample_and_not_the_next_days():
    """The review's test: the 21st's sample carries the 18:00 rating; the 22nd's carries nothing.
    Under the UTC day the rating (01:00 UTC on the 22nd) went to the 22nd's sample instead."""
    out = adapter.align_pros(_pro_df(), target="chronic", chronic=_chronic(), metrics=("nrs",))
    assert len(out) == 2
    assert out.iloc[0]["nrs"] == 7.0, out
    assert np.isnan(out.iloc[1]["nrs"]), out


def test_the_legacy_same_day_session_join_uses_the_same_day():
    """Slider off (no tolerance): a session at local noon on the 21st is matched to the 18:00
    rating of the 21st; a session at local noon on the 22nd is not."""
    recs = [{"StartTime": _epoch(SAMPLE_21_UTC), "Data": np.zeros((10, 2)),
             "ChannelNames": ["a", "b"], "SamplingRate": 250.0},
            {"StartTime": _epoch(SAMPLE_22_UTC), "Data": np.zeros((10, 2)),
             "ChannelNames": ["a", "b"], "SamplingRate": 250.0}]
    df = adapter.align_pros(_pro_df(), target="session", recordings=recs, metrics=("nrs",))
    assert list(df["session_date"]) == [_dt.date(2025, 7, 21), _dt.date(2025, 7, 22)]
    assert list(df["matched"]) == [True, False]
    assert df.iloc[0]["nrs_mean"] == 7.0 and np.isnan(df.iloc[1]["nrs_mean"])
    assert df.iloc[0]["matched_pro_time"] == pd.Timestamp("2025-07-21")


def test_the_daily_series_behind_the_pain_cut_is_binned_by_local_day():
    """Three samples: 9 at 23:00 local on the 21st (06:00 UTC on the 22nd), 1 at noon on the 22nd,
    3 at noon on the 23rd. Local days give the daily series [9, 1, 3], median 3, so the third
    sample is labelled high (3 >= 3). UTC days merged the first two into one day with mean 5,
    giving [5, 3], median 4, and labelled the third sample low. The value pins the rule."""
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2025-07-22 06:00:00", "2025-07-22 19:00:00",
                                     "2025-07-23 19:00:00"]),
        "nrs": [9.0, 1.0, 3.0]})
    pl = adapter._threshold_pain_level(df, "nrs", strategy="median", daily_broadcast=True)
    assert list(pl) == [1.0, 0.0, 1.0], list(pl)


def test_the_binarization_preview_and_day_counts_use_the_same_day():
    """The per-band daily rows the page's binarization preview shows, and the day counts under
    each frequency, are binned by the same rule -- two local days here, where the UTC rule saw one."""
    cv = pd.DataFrame({
        "timestamp": pd.to_datetime(["2025-07-22 06:00:00", "2025-07-22 19:00:00"]),
        "LFP_smoothed": [1.0, 2.0], "pain_level": [1.0, 0.0], "nrs": [9.0, 1.0],
        "frequency_hz": [20.5, 20.5]})
    out = pipeline._decode_by_frequency(cv, "nrs", min_labeled=1)
    daily = out["20.5"]["binarization"]["daily"]
    assert [d["day"] for d in daily] == ["2025-07-21", "2025-07-22"], daily
    assert [d["mean"] for d in daily] == [9.0, 1.0]
    counts = pipeline._available_frequencies(cv)
    assert counts[0]["n_days"] == 2 and counts[0]["n_days_labeled"] == 2, counts


def test_the_service_binds_the_same_zone():
    """`bravo_service._PRO_LOCAL_TZ` is the one definition, not a second string."""
    try:
        from modules.Biomarkers import bravo_service as B
    except Exception:          # the host suite has no Django; the container runner does
        return
    assert B._PRO_LOCAL_TZ is local_time.PRO_LOCAL_TZ


if __name__ == "__main__":
    test_the_zone_is_named_once_and_the_helper_reads_it()
    test_the_boundary_follows_daylight_saving()
    test_an_evening_rating_joins_that_days_sample_and_not_the_next_days()
    test_the_legacy_same_day_session_join_uses_the_same_day()
    test_the_daily_series_behind_the_pain_cut_is_binned_by_local_day()
    test_the_binarization_preview_and_day_counts_use_the_same_day()
    test_the_service_binds_the_same_zone()
    print("All local-calendar-day tests passed.")
