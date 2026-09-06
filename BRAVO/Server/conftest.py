"""Opt-in synthetic fixtures for portable server tests; no private policy files."""
import csv

import pytest


@pytest.fixture
def synthetic_oura_policy(tmp_path, monkeypatch):
    """Invented exclusion window with different day and sample end boundaries.

    These dates are test inputs, not assertions about the real participant policy.
    The participant code is required by the production policy schema.
    """
    from modules.OURA import QualityControl

    path = tmp_path / "synthetic_oura_policy.csv"
    fields = ["target_time_basis", "participant_id", "action", "start_inclusive",
              "end_exclusive", "filter_id", "reason"]
    rows = [
        ["Oura day", "RCS08", "exclude", "2026-04-30", "2026-05-28",
         "synthetic-day", "Invented day exclusion"],
        ["timezone-aware timestamp", "RCS08", "exclude", "2026-04-30T00:00:00-07:00",
         "2026-05-27T12:00:00-07:00", "synthetic-time", "Invented sample exclusion"],
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(rows)
    monkeypatch.setattr(QualityControl, "POLICY_PATH", path)
    return path
