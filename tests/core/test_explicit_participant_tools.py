"""Offline data tools must never select a real participant implicitly."""
from pathlib import Path

import pytest
from modules.ControlAnalyses.run import parse_arguments as control_arguments
from modules.StimRL.export_snapshot import parse_arguments as export_arguments


@pytest.mark.parametrize("arguments", [[], ["all"]])
def test_control_requires_explicit_participant(arguments):
    with pytest.raises(SystemExit) as caught:
        control_arguments(arguments)
    assert caught.value.code == 2


def test_control_uses_explicit_selection():
    result = control_arguments(["all", "synthetic-one"])
    assert result.key == "all"
    assert result.participant == "synthetic-one"


@pytest.mark.parametrize("arguments", [[], ["--participant", "synthetic-one"], ["--output", "/tmp/example"]])
def test_export_requires_explicit_participant_and_destination(arguments):
    with pytest.raises(SystemExit) as caught:
        export_arguments(arguments)
    assert caught.value.code == 2


def test_export_uses_explicit_selection():
    result = export_arguments(["--participant", "synthetic-two", "--output", "/tmp/synthetic-output"])
    assert result.participant == "synthetic-two"
    assert result.output == Path("/tmp/synthetic-output")
