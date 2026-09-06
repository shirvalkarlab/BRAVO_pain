"""Unit test for redcap_client.process_redcap (raw REDCap export -> tidy PRO table).

Builds a synthetic frame shaped like PyCap's export_records(format_type='df') output (MultiIndex
on record_id / redcap_event_name / redcap_repeat_instance, with a redcap_repeat_instrument column,
plus an unrelated instrument and another patient that must be filtered out), then checks the
filter -> rename/sum -> sort -> fillna behavior. Run inside the container:

    docker compose exec -w /usr/src/BRAVO bravo-server python3 -W ignore \
        modules/Biomarkers/tests/test_process_redcap.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Biomarkers.routines import redcap_client  # noqa: E402


def _raw_frame():
    rows = [
        # record_id, event, instrument, instance, ts, nrs, vas, mpq_a1, mpq_a2, other_field
        ("RCS08", "visit_1", "daily_pain_survey", 1, "2025-09-02 09:00", 8, 80, 5, 6, 999),
        ("RCS08", "visit_1", "daily_pain_survey", 2, "2025-09-01 09:00", 2, 20, 1, 1, 999),  # earlier -> sorts first
        ("RCS08", "visit_1", "daily_pain_survey", 3, "2025-09-03 09:00", np.nan, 50, np.nan, 2, 999),  # NaN -> 0
        ("RCS08", "visit_1", "other_instrument", 1, "2025-09-04 09:00", 1, 1, 1, 1, 1),  # wrong instrument -> dropped
        ("RCS09", "visit_1", "daily_pain_survey", 1, "2025-09-02 09:00", 9, 90, 7, 7, 7),  # other patient -> dropped
    ]
    cols = ["record_id", "redcap_event_name", "redcap_repeat_instrument", "redcap_repeat_instance",
            "date_time_s1_daily", "nrs", "vas", "mpq_item1_aff", "mpq_item2_aff", "unused"]
    df = pd.DataFrame(rows, columns=cols)
    return df.set_index(["record_id", "redcap_event_name", "redcap_repeat_instance"])


def main():
    field_map = {
        "pt": "RCS08",
        "instruments": ["daily_pain_survey"],
        "timestamp_label": "date_time_s1_daily",
        "metric_labels": {
            "nrs": "nrs",
            "vas": "vas",
            "mpq_aff": ["mpq_item1_aff", "mpq_item2_aff"],
        },
    }
    out = redcap_client.process_redcap(_raw_frame(), field_map)

    # 3 RCS08 daily_pain_survey rows survive (other instrument + other patient filtered out).
    assert len(out) == 3, f"expected 3 rows, got {len(out)}"
    # Canonical timestamp column present and sorted ascending.
    assert "date_time_s1_daily" in out.columns
    ts = list(out["date_time_s1_daily"])
    assert ts == sorted(ts), f"not sorted: {ts}"
    assert ts[0] == "2025-09-01 09:00"
    # Scalar mapping. A missing report stays NaN (NOT fabricated as 0) — rigor fix.
    import math
    nrs = list(out["nrs"])
    assert nrs[0] == 2 and nrs[1] == 8 and math.isnan(nrs[2]), nrs   # 3rd report missing -> NaN
    # List mapping summed row-wise with min_count=1 (>=1 present -> sum of present; all-missing -> NaN).
    assert list(out["mpq_aff"]) == [2, 11, 2], list(out["mpq_aff"])  # 1+1, 5+6, (missing,2)->2
    # Only canonical keys + timestamp are emitted; unrelated raw columns dropped.
    assert "unused" not in out.columns
    assert set(out.columns) == {"nrs", "vas", "mpq_aff", "date_time_s1_daily"}, list(out.columns)

    print("OK process_redcap: rows=%d cols=%s" % (len(out), list(out.columns)))
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
