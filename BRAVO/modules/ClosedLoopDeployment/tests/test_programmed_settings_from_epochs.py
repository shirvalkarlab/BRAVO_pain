"""Tests for `adapter.programmed_settings_from_epochs` and its wiring into `report_for_participant`.

Why this exists: a band picked from the calibrated grid carries a channel and a centre frequency
and nothing about stimulation, so D27 and D31 both went unknown or blocked for a reason that has
nothing to do with the band -- the frontend never sends a rate or pulse width. The device's own
programmed setting is on record in the exposure-epoch table, and this reads it rather than leaving
the two facts `None` forever.
"""
from __future__ import annotations

import pandas as pd
import pytest

from ClosedLoopDeployment import adapter as AD


def _epochs(*, n=1):
    """One or more exposure epochs in the real column shape (`StimOptimizer.adapter.exposure_epochs`).

    Every column the real table carries is present, including the ones this function does not
    read, so a test failure here cannot be blamed on an unrealistic fixture.
    """
    t0 = pd.Timestamp("2026-09-01T00:00:00Z")
    rows = []
    for k in range(n):
        rows.append({
            "epoch": float(k + 1),
            "t_start": t0 + pd.Timedelta(days=k),
            "t_end": t0 + pd.Timedelta(days=k + 1),
            "dur_h": 24.0,
            "open_ended": False,
            "freq_hz": 55.0 + k,
            "amp_mA_Left": 3.0,
            "amp_mA_Right": 2.5,
            "pw_us_Left": 100.0 + k,
            "pw_us_Right": 150.0 + k,
            "cathode_Left": "1",
            "cathode_Right": "1",
        })
    rows[-1]["open_ended"] = True
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------
# programmed_settings_from_epochs itself
# ------------------------------------------------------------------------------------------------
def test_reads_the_open_ended_epoch_on_the_named_hemisphere():
    eps = _epochs(n=3)
    out = AD.programmed_settings_from_epochs(eps, "Left")
    # The open-ended row is the last one built (k=2): freq 57.0, pw_us_Left 102.0.
    assert out["rate_hz"] == 57.0
    assert out["pulse_width_us"] == 102.0
    assert "exposure epoch" in out["_provenance"]
    assert "open-ended" in out["_provenance"]
    assert "Left" in out["_provenance"]


def test_the_value_is_hemisphere_specific_a_right_candidate_gets_pw_us_right():
    eps = _epochs(n=1)
    left = AD.programmed_settings_from_epochs(eps, "Left")
    right = AD.programmed_settings_from_epochs(eps, "Right")
    assert left["pulse_width_us"] == 100.0
    assert right["pulse_width_us"] == 150.0
    # Both sides share the one rate the device runs at.
    assert left["rate_hz"] == right["rate_hz"] == 55.0


def test_the_open_ended_epoch_wins_over_a_newer_looking_closed_one():
    eps = _epochs(n=2)
    # Make the FIRST (closed) epoch look newer by giving it a later t_start than the open-ended
    # one, so a naive "sort by time and take the last row" would pick the wrong row.
    eps.loc[0, "t_start"] = pd.Timestamp("2026-12-31T00:00:00Z")
    eps.loc[0, "freq_hz"] = 999.0
    eps.loc[0, "pw_us_Left"] = 999.0
    out = AD.programmed_settings_from_epochs(eps, "Left")
    # The open-ended row (epoch 2, index 1) must win even though epoch 1 starts later.
    assert out["rate_hz"] == 56.0
    assert out["pulse_width_us"] == 101.0


def test_with_no_open_ended_epoch_the_newest_start_time_wins():
    eps = _epochs(n=3)
    eps["open_ended"] = False
    out = AD.programmed_settings_from_epochs(eps, "Left")
    # epoch 3 (index 2) has the latest t_start.
    assert out["rate_hz"] == 57.0
    assert out["pulse_width_us"] == 102.0
    assert "closed" in out["_provenance"]


def test_no_epoch_frame_means_the_keys_are_absent_not_fabricated():
    assert AD.programmed_settings_from_epochs(None, "Left") == {}
    assert AD.programmed_settings_from_epochs(pd.DataFrame(), "Left") == {}


def test_an_unrecognised_hemisphere_supplies_nothing():
    eps = _epochs(n=1)
    assert AD.programmed_settings_from_epochs(eps, None) == {}
    assert AD.programmed_settings_from_epochs(eps, "Both") == {}


def test_a_missing_pulse_width_column_leaves_that_key_absent_but_still_reports_the_rate():
    eps = _epochs(n=1).drop(columns=["pw_us_Right"])
    out = AD.programmed_settings_from_epochs(eps, "Right")
    assert "pulse_width_us" not in out
    assert out["rate_hz"] == 55.0


def test_a_nan_pulse_width_in_the_epoch_leaves_that_key_absent():
    eps = _epochs(n=1)
    eps.loc[0, "pw_us_Left"] = float("nan")
    out = AD.programmed_settings_from_epochs(eps, "Left")
    assert "pulse_width_us" not in out
    assert out["rate_hz"] == 55.0


# ------------------------------------------------------------------------------------------------
# Wiring: pipeline._facts_for never overrides a candidate's own explicit value.
# ------------------------------------------------------------------------------------------------
def test_pipelines_facts_for_does_not_override_a_candidates_own_rate_and_pulse_width():
    from ClosedLoopDeployment import pipeline as PL

    candidate = {"channel": "ONE_THREE_LEFT", "rate_hz": 110.0, "pulse_width_us": 60.0}
    device_facts = {"rate_hz": 55.0, "pulse_width_us": 100.0}
    facts = PL._facts_for(candidate, None, None, "power_linear", device_facts=device_facts)
    assert facts["rate_hz"] == 110.0
    assert facts["pulse_width_us"] == 60.0


def test_pipelines_facts_for_fills_in_an_absent_rate_and_pulse_width_from_device_facts():
    from ClosedLoopDeployment import pipeline as PL

    candidate = {"channel": "ONE_THREE_LEFT"}
    device_facts = {"rate_hz": 55.0, "pulse_width_us": 100.0}
    facts = PL._facts_for(candidate, None, None, "power_linear", device_facts=device_facts)
    assert facts["rate_hz"] == 55.0
    assert facts["pulse_width_us"] == 100.0
