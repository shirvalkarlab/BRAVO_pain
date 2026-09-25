"""The settings stream starts at the implant date (the PI, 2026-09-24).

On RCS08 the stream's first rows were four 'Past Therapy' snapshots from January to April 2025,
read off the device at its first clinic session (2025-07-17) and never delivered to the patient; the
device record's implant date is 2025-07-16 18:06 UTC. A setting holds until the next change, so the
one in force at implant is kept and moved to the implant date; everything earlier goes.
"""
import pandas as pd

from StimOptimizer import adapter as AD

IMPLANT = pd.Timestamp("2025-07-16 18:06", tz="UTC")


def _stream():
    rows = []
    for days, amp in [(-179, 2.9), (-149, 2.9), (-119, 2.9), (-89, 2.9), (2, 0.0), (40, 1.5)]:
        for hemi in ("Left", "Right"):
            rows.append(dict(t=IMPLANT + pd.Timedelta(days=days), src="history", hemi=hemi, amp=amp,
                             pw=60.0, rate=55.0, upper=None, upper_is_patient_limit=None,
                             cathode="2", schema="x"))
    return pd.DataFrame(rows)


def test_rows_before_implant_go_and_the_setting_in_force_at_implant_starts_there():
    out = AD.apply_data_start(_stream(), IMPLANT.timestamp())
    for hemi in ("Left", "Right"):
        s = out[out.hemi == hemi].sort_values("t")
        assert list(s.t) == [IMPLANT, IMPLANT + pd.Timedelta(days=2), IMPLANT + pd.Timedelta(days=40)]
        assert list(s.amp) == [2.9, 0.0, 1.5]


def test_no_start_leaves_the_stream_as_it_was():
    s = _stream()
    out = AD.apply_data_start(s, 0.0)
    assert out.reset_index(drop=True).equals(s.reset_index(drop=True))


def test_the_stored_stream_is_keyed_on_a_rule_that_starts_at_implant():
    assert "implant" in AD._THERAPY_SETTINGS_RULE_VERSION
