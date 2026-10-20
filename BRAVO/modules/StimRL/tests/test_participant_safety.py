"""Synthetic safety inputs prove that no participant inherits another's ceiling."""
import json

import numpy as np
import pytest

from StimRL.data_pipeline import (
    ClinicalConfigurationUnavailable, RetrospectiveDB, SafetyModel,
)


@pytest.fixture
def private_config(tmp_path, monkeypatch):
    path = tmp_path / "clinical.json"
    record = {
        "values_mA": {"Left": 2.0, "Right": 3.0},
        "provenance": "Synthetic test ceilings, not clinical guidance",
        "evidence_ref": "synthetic-fixture",
        "source_commit": "a" * 40,
    }
    path.write_text(json.dumps({"schema_version": 1, "participants": {
        "synthetic-a": {"safety_ceiling": record},
        "synthetic-b": {"safety_ceiling": {**record, "values_mA": {"Left": 1.0, "Right": 1.5}}},
    }}))
    path.chmod(0o600)
    monkeypatch.setenv("BRAVO_CLINICAL_CONFIG_FILE", str(path))
    return path


def test_absent_configuration_does_not_supply_a_study_default(monkeypatch):
    monkeypatch.delenv("BRAVO_CLINICAL_CONFIG_FILE", raising=False)
    with pytest.raises(ClinicalConfigurationUnavailable):
        SafetyModel()
    with pytest.raises(ClinicalConfigurationUnavailable):
        SafetyModel.for_participant("synthetic-a")


def test_exact_identity_and_separate_side_limits(private_config):
    a = SafetyModel.for_participant("synthetic-a")
    b = SafetyModel.for_participant("synthetic-b")
    assert a.warn == {"Left": 1.5, "Right": 2.5}
    assert a.risk((70, 1.75, 2.75, 100, 100)) == pytest.approx(0.5)
    assert not a.violates((70, 2, 3, 100, 100))
    assert a.violates((70, 2.1, 1, 100, 100))
    assert a.violates((70, 1, 3.1, 100, 100))
    assert b.violates((70, 1.5, 1, 100, 100))
    for unknown in (None, "", "other-participant"):
        with pytest.raises(ClinicalConfigurationUnavailable):
            SafetyModel.for_participant(unknown)


def test_snapshot_identity_drives_lookup(private_config, tmp_path):
    # Bypass optional SQLAlchemy: safety lookup only requires the export manifest.
    db = object.__new__(RetrospectiveDB)
    db.data_dir = str(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"uid": "synthetic-b"}))
    assert db.safety_model().ceiling == {"Left": 1.0, "Right": 1.5}
    manifest.write_text("{}")
    with pytest.raises(ClinicalConfigurationUnavailable):
        db.safety_model()


@pytest.mark.parametrize("ceiling", [None, True, 0, -1, float("nan"), float("inf"), "invalid", {"Left": 2}])
def test_invalid_or_missing_ceilings_are_unavailable(ceiling):
    with pytest.raises(ClinicalConfigurationUnavailable):
        SafetyModel(ceiling=ceiling)


@pytest.mark.parametrize("warn", [-1, 2, 3, float("nan"), True, {"Left": 1}])
def test_invalid_warning_currents_are_unavailable(warn):
    with pytest.raises(ClinicalConfigurationUnavailable):
        SafetyModel(ceiling=2, warn=warn)


def test_low_ceiling_retains_finite_warning_interval():
    s = SafetyModel(ceiling=0.25)
    assert s.warn == {"Left": 0.0, "Right": 0.0}
    assert s.side_risk(0.125) == pytest.approx(0.5)
    assert s.side_risk(np.nan) == 0.0  # legacy missing-current risk semantics


def test_configured_values_must_be_side_specific(private_config):
    document = json.loads(private_config.read_text())
    document["participants"]["synthetic-a"]["safety_ceiling"]["values_mA"] = 2
    private_config.write_text(json.dumps(document))
    with pytest.raises(ClinicalConfigurationUnavailable):
        SafetyModel.for_participant("synthetic-a")
