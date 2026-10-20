"""Synthetic participant isolation and private-config invalidation at consumer boundaries."""
import dataclasses
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "BRAVO" / "modules"))
from ClosedLoopDeployment import adapter as AD, pipeline as PL, prescription as PR
from ClosedLoopDeployment import safe_current as SAFE, timing_recommendation as TR
from ClosedLoopDeployment.types import ThresholdPlan
from DecodeCommon import private_clinical_config as CC
from StimOptimizer import bravo_service as SO


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "clinical.json"
    provenance = {"provenance": "synthetic evidence", "source_commit": "a" * 40,
                  "evidence_ref": "synthetic-test-only"}
    document = {"schema_version": 1, "participants": {}}
    for uid, left, right in (("synthetic-A", 2.25, 3.75), ("synthetic-B", 1.75, 2.75)):
        document["participants"][uid] = {
            "safety_ceiling": dict(provenance, values_mA={"Left": left, "Right": right}),
            "timing": dict(provenance, fields={key: {"value_ms": 3000 if key == "averaging_ms" else 12000,
                                                       "why": "synthetic timing", "confidence": "Low"}
                                                for key in TR.TIMING_FIELDS})}

    def write():
        path.write_text(json.dumps(document))
        path.chmod(0o600)
    write()
    monkeypatch.setenv(CC.ENVIRONMENT_VARIABLE, str(path))
    return document, write


def plan(lo=1.0, hi=4.0):
    return ThresholdPlan(upper=20.0, lower=10.0, capture_amp_low=lo, capture_amp_high=hi)


def test_exact_participant_and_side_caps_preserve_observed_capture(config):
    a = SAFE.apply_to_plan(plan(), "synthetic-A", "Left")
    b = SAFE.apply_to_plan(plan(), "synthetic-B", "Left")
    right = SAFE.apply_to_plan(plan(), "synthetic-A", "Right")
    assert a.capture_amp_high == b.capture_amp_high == right.capture_amp_high == 4.0
    assert a.amplitude_limits() == (1.0, 2.25)
    assert b.amplitude_limits() == (1.0, 1.75)
    assert right.amplitude_limits() == (1.0, 3.75)
    assert a.safety_participant_uid == "synthetic-A"
    assert a.safety_hemisphere == "Left"
    assert a.safety_config_digest == CC.config_digest()
    assert "4 mA" in a.amp_limit_high_note
    assert SAFE.ensure_applied(a).amplitude_limits() == a.amplitude_limits()


@pytest.mark.parametrize("kwargs", [{"participant_uid": "synthetic-B"}, {"side": "Right"}])
def test_copied_plan_cannot_cross_subject_or_side(config, kwargs):
    a = SAFE.apply_to_plan(plan(), "synthetic-A", "Left")
    with pytest.raises(CC.ClinicalConfigurationUnavailable, match="different participant or side"):
        SAFE.ensure_applied(a, **kwargs)


def test_numeric_unbound_plan_is_not_authority(config):
    fake = dataclasses.replace(plan(), safety_ceiling_mA=4.5, safety_ceiling_provenance="old")
    with pytest.raises(CC.ClinicalConfigurationUnavailable, match="no exact participant"):
        SAFE.ensure_applied(fake)
    assert SAFE.ensure_applied(fake, participant_uid="synthetic-B", side="Left").amplitude_limits() == (1, 1.75)
    assert SAFE.ensure_applied(None) is None
    assert SAFE.apply_to_plan(None, "synthetic-A", "Left") is None


def test_changed_or_removed_config_revalidates_bound_plan(config, monkeypatch):
    document, write = config
    a = SAFE.apply_to_plan(plan(), "synthetic-A", "Left")
    document["participants"]["synthetic-A"]["safety_ceiling"]["values_mA"]["Left"] = 1.5
    write()
    updated = SAFE.ensure_applied(a)
    assert updated.amplitude_limits() == (1, 1.5)
    assert updated.safety_config_digest != a.safety_config_digest
    monkeypatch.delenv(CC.ENVIRONMENT_VARIABLE)
    with pytest.raises(CC.ClinicalConfigurationUnavailable):
        SAFE.ensure_applied(a)


def test_unknown_config_and_midread_change_fail_closed(config, monkeypatch):
    with pytest.raises(CC.ClinicalConfigurationUnavailable):
        SAFE.apply_to_plan(plan(), "unconfigured", "Left")
    digests = iter(("old", "new"))
    monkeypatch.setattr(SAFE._clinical, "config_digest", lambda: next(digests))
    with pytest.raises(CC.ClinicalConfigurationUnavailable, match="changed while reading"):
        SAFE.apply_to_plan(plan(), "synthetic-A", "Left")


def test_degenerate_and_missing_capture_values_remain_explicit(config):
    a = SAFE.apply_to_plan(plan(lo=3, hi=4), "synthetic-A", "Left")
    assert a.amplitude_limits() == (2.25, 2.25)
    assert "No range is left" in a.amp_limit_low_note
    b = SAFE.apply_to_plan(plan(lo=None, hi=None), "synthetic-A", "Left")
    assert b.amplitude_limits() == (None, None)
    assert SAFE.cap("unknown", 2, "synthetic", was="capture") == ("unknown", None)
    assert SAFE.cap(float("inf"), 2, "synthetic", was="capture") == (float("inf"), None)
    assert SAFE.cap(1, 2, "synthetic", was="capture") == (1, None)


def test_prescription_and_simulation_refuse_cross_participant(config):
    a = SAFE.apply_to_plan(plan(), "synthetic-A", "Left")
    with pytest.raises(CC.ClinicalConfigurationUnavailable):
        PR.prescribe(mode=PR.PA.DUAL, threshold_plan=a, participant_uid="synthetic-B", hemisphere="Left")
    response = AD.write_simulation("synthetic-B", rep=SimpleNamespace(threshold=a), candidate={}, hemisphere="Left",
                                   build={}, power_scale="raw", epochs=None)
    assert response["written"] is False
    assert response["unavailable_kind"] == "clinical_configuration"
    response = AD.write_robustness("synthetic-B", threshold_plan=a, candidate={}, hemisphere="Left")
    assert response["written"] is False
    assert response["unavailable_kind"] == "clinical_configuration"


def test_prescription_requires_plan_and_timing_evidence(config):
    with pytest.raises(CC.ClinicalConfigurationUnavailable, match="no participant-bound"):
        PR.prescribe(mode=PR.PA.DUAL)
    document, write = config
    a = SAFE.apply_to_plan(plan(), "synthetic-A", "Left")
    good = PR.prescribe(mode=PR.PA.DUAL, threshold_plan=a)
    assert good.fields
    del document["participants"]["synthetic-A"]["timing"]
    write()
    with pytest.raises(CC.ClinicalConfigurationUnavailable):
        PR.prescribe(mode=PR.PA.DUAL, threshold_plan=a)


def test_pipeline_keeps_observations_but_withholds_unbounded_plan(monkeypatch):
    monkeypatch.delenv(CC.ENVIRONMENT_VARIABLE, raising=False)
    rows = []
    for k, current in enumerate((1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5)):
        for j in range(6):
            rows.append({"t": k * 100 + j, "channel": "SYNTHETIC_RIGHT", "setting_epoch": k,
                         "center_hz": 25, "amp_mA_Left": 1, "amp_mA_Right": current,
                         "power_linear": 600 - 40 * current + j / 10,
                         "nrs": 8 - 0.6 * current + j / 100, "report_id": f"r{k}"})
    monkeypatch.setattr(AD, "joined_table_cached", lambda *a, **kw: pd.DataFrame(rows))
    protocol = SimpleNamespace(titration_plan=lambda *a, **kw: pytest.fail("no unbounded titration ladder"))
    monkeypatch.setattr(PL, "_optional", lambda name: protocol if name == "protocol" else None)
    report = PL.run("synthetic-unconfigured", psd_frame=pd.DataFrame({"x": [1]}),
                    epochs=pd.DataFrame({"x": [1]}), hemisphere="Right", n_boot=20,
                    candidates=[{"channel": "SYNTHETIC_RIGHT", "center_hz": 25,
                                 "sensing_hemisphere": "Right", "actuated_hemisphere": "Right"}])
    assert report.threshold is None
    assert report.replay is None and report.prescription is None
    assert any("clinical configuration unavailable" in reason for reason in report.blockers)


def test_stim_optimizer_checks_ceiling_before_any_data_or_cached_response(monkeypatch):
    import types
    monkeypatch.delenv(CC.ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setitem(sys.modules, "Server", types.SimpleNamespace(
        models=SimpleNamespace(Participant=SimpleNamespace(find=lambda **kw: SimpleNamespace(uid=kw["uid"])))))
    monkeypatch.setattr(SO.adapter, "settings_stream", lambda *a, **kw: pytest.fail("must refuse before data access"))
    result = SO._run_for_participant({"ParticipantId": "synthetic-unconfigured"})
    assert result["available"] is False
    assert result["unavailable_kind"] == "clinical_configuration"


def test_config_changes_invalidate_scientific_result_keys(config, monkeypatch):
    monkeypatch.setattr(AD, "recording_set_signature", lambda participant: ("synthetic-recording",))
    base = dict(tiles_key="tiles", contact="PAIR", centre_hz=25, hemisphere="Left")
    def keys():
        return (
            SO._response_signature("synthetic-A", "matched", "tiles", "amp", "gt", {}, ("nrs",), ("Left",), 1, "none"),
            AD.simulation_signature("synthetic-A", **base, plan=plan(), power_scale="raw", n_resample=10, seed=0),
            AD.design_rule_signature("synthetic-A", **base, upper=20, lower=10),
            AD.band_timing_signature("synthetic-A", **base, amp_low=1, amp_high=2),
            AD.robustness_signature("synthetic-A", **base, upper=20, lower=10, amp_low=1, amp_high=2, n_boot=10, seed=0),
        )
    before = keys()
    document, write = config
    document["participants"]["synthetic-A"]["timing"]["fields"]["onset_upper_ms"]["value_ms"] = 15000
    write()
    after = keys()
    assert all(old != new for old, new in zip(before, after))
    assert SO._products_signature(before[0]) != SO._products_signature(after[0])


@pytest.mark.parametrize("reader", [AD.simulation_if_stored, AD.design_rule_if_stored, AD.robustness_if_stored, AD.band_timing_if_stored])
def test_newest_lookup_rejects_stale_config_even_same_candidate(config, monkeypatch, reader):
    candidate = {"channel": "PAIR", "center_hz": 25}
    tag = AD._simulation_candidate_tag("PAIR", 25, "Left")
    def load(*args, match, **kwargs):
        assert not match({"extra": {"candidate": tag}})
        assert not match({"extra": {"candidate": tag, "clinical_config_digest": "old"}})
        assert match({"extra": {"candidate": tag, "clinical_config_digest": CC.config_digest()}})
        return {"available": True}, {}
    monkeypatch.setattr(AD._cache_store, "load_newest", load)
    assert reader("synthetic-A", candidate, hemisphere="Left")["available"]


def test_ground_truth_key_changes_with_private_power_ceiling(monkeypatch):
    from ClosedLoopDeployment import ceiling_thresholds as QC
    monkeypatch.setattr(AD, "recording_set_signature", lambda participant: ())
    monkeypatch.setattr(QC, "configuration_identity", lambda uid: (1, "valid", "one"))
    before = AD.ground_truth_signature("synthetic-A", tiles_key="tiles")
    monkeypatch.setattr(QC, "configuration_identity", lambda uid: (1, "valid", "two"))
    assert before != AD.ground_truth_signature("synthetic-A", tiles_key="tiles")


def test_explicit_timing_cannot_bypass_participant_or_snapshot_binding(config):
    document, write = config
    a = SAFE.apply_to_plan(plan(), "synthetic-A", "Left")
    with pytest.raises(CC.ClinicalConfigurationUnavailable, match="incomplete"):
        PR.prescribe(mode=PR.PA.DUAL, threshold_plan=a, record_timing={})
    with pytest.raises(CC.ClinicalConfigurationUnavailable, match="another participant"):
        PR.prescribe(mode=PR.PA.DUAL, threshold_plan=a, record_timing=TR.for_participant("synthetic-B"))
    timing = TR.for_participant("synthetic-A")
    document["participants"]["synthetic-A"]["timing"]["fields"]["averaging_ms"]["value_ms"] = 2000
    write()
    with pytest.raises(CC.ClinicalConfigurationUnavailable, match="outdated"):
        PR.prescribe(mode=PR.PA.DUAL, threshold_plan=a, record_timing=timing)


def test_eligibility_never_assumes_programming_mode(config, monkeypatch):
    document, write = config
    assert "programming_mode" not in PL._participant_facts("synthetic-unconfigured")
    evidence = {"programming_mode": "non_parkinsons", "indication": "synthetic-indication"}
    assert PL._participant_facts("synthetic-unconfigured", evidence)["programming_mode"] == "non_parkinsons"
    provenance = {"provenance": "synthetic", "evidence_ref": "fixture", "source_commit": "a" * 40}
    document["participants"]["synthetic-A"]["adaptive_eligibility"] = dict(provenance, programming_mode="parkinsons", uid="synthetic-B")
    write()
    assert PL._participant_facts("synthetic-A")["programming_mode"] == "parkinsons"
    assert PL._participant_facts("synthetic-A")["uid"] == "synthetic-A"
    assert PL._participant_facts("synthetic-A", evidence)["programming_mode"] == "non_parkinsons"


@pytest.mark.parametrize("fields,label", [
    ({}, "Reference timing (assumed)"),
    ({"averaging_ms": 3000}, "Reference timing (partly assumed)"),
    ({"averaging_ms": 3000, "onset_upper_ms": 12000, "detection_blanking_ms": 12000,
      "transition_up_ms": 12000, "transition_down_ms": 12000}, "As programmed today"),
])
def test_reference_simulation_never_claims_missing_timing_is_observed(config, fields, label):
    scenarios = AD._timing_runs_for_simulation(
        "synthetic-A", "Left", {"active_sensing_group_timing": {"Left": fields}})
    assert scenarios["programmed"]["label"] == label
    assert scenarios["programmed"]["params"] == AD._simulation_params_from_timing_dict(fields)
    assert scenarios["recommended"]["params"]["averaging_ms"] == 3000
    if label.startswith("Reference"):
        assert "does not establish" in scenarios["programmed"]["source"]
