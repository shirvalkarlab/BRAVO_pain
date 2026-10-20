"""Synthetic clinical configuration cases; no historical participant data."""
import json
import os
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from modules.DecodeCommon import private_clinical_config as C
from modules.StimOptimizer import safety_ceiling as SC
from modules.ClosedLoopDeployment import timing_recommendation as TR


@pytest.fixture
def configuration(tmp_path, monkeypatch):
    document = {"schema_version": 1, "participants": {"synthetic-alpha": {
        "safety_ceiling": {"values_mA": {"Left": 2.2, "Right": 3.1},
                           "provenance": "Synthetic clinician statement", "source_commit": "a" * 40,
                           "evidence_ref": "synthetic/statement"},
        "timing": {"fields": {key: {"value_ms": 6000, "why": "Synthetic replay evidence",
                                   "confidence": "Medium"} for key in TR.TIMING_FIELDS},
                   "provenance": "Synthetic timing evidence", "source_commit": "b" * 40,
                   "evidence_ref": "synthetic/replay"}}}}
    path = tmp_path / "clinical.json"
    def write(value=document):
        path.write_text(json.dumps(value))
        path.chmod(0o600)
    write()
    monkeypatch.setenv(C.ENVIRONMENT_VARIABLE, str(path))
    return document, path, write


def test_explicit_participant_and_side_binding(configuration):
    assert SC.ceiling_for("synthetic-alpha", "Left") == (2.2, "Synthetic clinician statement")
    assert SC.ceilings_by_hemisphere("synthetic-alpha")["Right"][0] == 3.1
    for uid in ("synthetic-beta", None, " "):
        with pytest.raises(C.ClinicalConfigurationUnavailable):
            SC.ceiling_for(uid, "Left")
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        SC.ceiling_for("synthetic-alpha", "Other")
    out = TR.for_participant("synthetic-alpha")
    assert set(out) == set(TR.TIMING_FIELDS)
    assert out["averaging_ms"] == {"value_ms": 6000, "why": "Synthetic replay evidence",
                                   "confidence": "Medium", "provenance": "Synthetic timing evidence",
                                   "participant_uid": "synthetic-alpha", "config_digest": C.config_digest()}
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        TR.for_participant("synthetic-beta")


def test_never_default_to_higher_ceiling(configuration, monkeypatch):
    monkeypatch.delenv(C.ENVIRONMENT_VARIABLE)
    for call in (lambda: SC.ceiling_for("synthetic-alpha", "Left"),
                 lambda: SC.ceiling_mA_by_side(), lambda: SC.ceiling_anchors(None, [20]),
                 lambda: SC.held_at_or_below_ceiling(1, None, side="Left"),
                 lambda: SC.safety_seed([], "a", freq_grid=[20]),
                 lambda: TR.for_participant("synthetic-alpha")):
        with pytest.raises(C.ClinicalConfigurationUnavailable):
            call()
    assert C.config_digest() == "clinical-config-unavailable-v1"


@pytest.mark.parametrize("value", [None, "bad", True, -1, 0, float("nan"), float("inf")])
def test_invalid_amplitudes(configuration, value):
    doc, _, write = configuration
    doc["participants"]["synthetic-alpha"]["safety_ceiling"]["values_mA"]["Left"] = value
    write()
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        SC.ceiling_for("synthetic-alpha", "Left")


def test_conservative_clamp_and_content_invalidation(configuration):
    doc, _, write = configuration
    before = C.config_digest()
    doc["participants"]["synthetic-alpha"]["safety_ceiling"]["values_mA"]["Left"] = 9
    write()
    value, provenance = SC.ceiling_for("synthetic-alpha", "Left")
    assert value == SC.OBJ.AMP_HARD_LIMIT_MA
    assert "clamped" in provenance
    assert C.config_digest() != before
    assert SC.ceiling_mA_by_side({"Left": (2.2, "source"), "Right": [3.1]}) == {"Left": 2.2, "Right": 3.1}
    assert SC.ceiling_mA_by_side({"Left": 9}, sides=("Left",)) == {"Left": SC.OBJ.AMP_HARD_LIMIT_MA}
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        SC.ceiling_mA_by_side({"Left": []}, sides=("Left",))
    np.testing.assert_array_equal(SC.within_ceiling_mask([2, 3], None, {"Left": 2.2}), [True, False])
    np.testing.assert_array_equal(SC.within_ceiling_mask(None, [1, 4], {"Right": 3.1}), [True, False])
    np.testing.assert_array_equal(SC.within_ceiling_mask([2, 3], [4, 1], {"Left": 2.2, "Right": 3.1}), [False, False])
    assert SC.within_ceiling_mask(None, None).item()
    np.testing.assert_array_equal(SC.ceiling_anchors(2.2, [20, 30]), [[20, 2.2], [30, 2.2]])


def test_held_current_and_observation_anchors():
    assert SC.held_at_or_below_ceiling(4, 2.2, side="Left")["current_mA"] == 2.2
    for current in (None, 1.1, float("nan")):
        assert not SC.held_at_or_below_ceiling(current, 2.2, side="Left")["above_ceiling"]
    frame = pd.DataFrame({"freq_hz": [20]*5, "amp": [1, 1, 1, 0, 1], "dur_h": [80, 80, 80, 80, 1],
                          "se_severity": [None, "mild", "severe", None, "moderate"]})
    np.testing.assert_array_equal(SC.tolerated_anchors(frame, "amp", min_tolerated_h=72), [[20, 1], [20, 1]])
    assert SC.n_intolerable_excluded(frame, "amp", min_tolerated_h=72) == 1
    assert not SC._intolerable_mask(frame.drop(columns="se_severity")).any()
    _, _, _, meta = SC.safety_seed(frame, "amp", freq_grid=[20, 30], ceiling=(2.2, "synthetic"))
    assert meta["safety_ceiling_mA"] == 2.2
    assert meta["n_tolerated_anchors"] == 2


@pytest.mark.parametrize("document", [[], {}, {"schema_version": True}, {"schema_version": 2},
    {"schema_version": 1}, {"schema_version": 1, "participants": []},
    {"schema_version": 1, "participants": {"synthetic-alpha": []}},
    {"schema_version": 1, "participants": {"synthetic-alpha": {"timing": []}}}])
def test_invalid_schema(configuration, document):
    _, _, write = configuration
    write(document)
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        C.participant_section("synthetic-alpha", "timing")


@pytest.mark.parametrize("raw", ["{", '{"schema_version":1,"schema_version":1}', b'\xff'])
def test_invalid_json(configuration, raw):
    _, path, _ = configuration
    path.write_bytes(raw.encode() if isinstance(raw, str) else raw)
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        C.participant_section("synthetic-alpha", "timing")


@pytest.mark.parametrize("key,value", [("provenance", None), ("provenance", ""),
    ("provenance", " "), ("evidence_ref", 4), ("source_commit", "wrong")])
def test_required_provenance(configuration, key, value):
    doc, _, write = configuration
    doc["participants"]["synthetic-alpha"]["timing"][key] = value
    write()
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        TR.for_participant("synthetic-alpha")


def test_rejects_unsafe_files(configuration, monkeypatch, tmp_path):
    _, path, _ = configuration
    path.chmod(0o644)
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        C._read_bytes()
    path.chmod(0o600)
    link = tmp_path / "link"
    link.symlink_to(path)
    monkeypatch.setenv(C.ENVIRONMENT_VARIABLE, str(link))
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        C._read_bytes()
    for invalid in (tmp_path, tmp_path / "absent"):
        monkeypatch.setenv(C.ENVIRONMENT_VARIABLE, str(invalid))
        with pytest.raises(C.ClinicalConfigurationUnavailable):
            C._read_bytes()
    monkeypatch.setenv(C.ENVIRONMENT_VARIABLE, str(path))
    monkeypatch.setattr(C.os, "geteuid", lambda: -1)
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        C._read_bytes()


def test_size_bound_even_if_file_grows(configuration, monkeypatch):
    _, path, _ = configuration
    monkeypatch.setattr(C, "_MAX_BYTES", 10)
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        C._read_bytes()
    original = os.fstat
    def small_stat(fd):
        info = original(fd)
        return SimpleNamespace(st_mode=info.st_mode, st_uid=info.st_uid, st_size=0)
    monkeypatch.setattr(C.os, "fstat", small_stat)
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        C._read_bytes()


@pytest.mark.parametrize("change", ["missing", "extra", "not_mapping", "entry_not_mapping", "no_value",
    "bad_value", "bool", "negative", "nan", "inf", "zero_average", "bad_confidence", "no_reason", "empty_reason"])
def test_invalid_timing_fails_closed(configuration, change):
    doc, _, write = configuration
    section = doc["participants"]["synthetic-alpha"]["timing"]
    fields = section["fields"]
    entry = fields["averaging_ms"]
    if change == "missing": del fields["onset_lower_ms"]
    elif change == "extra": fields["unknown"] = {}
    elif change == "not_mapping": section["fields"] = []
    elif change == "entry_not_mapping": fields["averaging_ms"] = []
    elif change == "no_value": del entry["value_ms"]
    elif change in ("bad_value", "bool", "negative", "nan", "inf", "zero_average"):
        entry["value_ms"] = {"bad_value": "bad", "bool": True, "negative": -1, "nan": float("nan"), "inf": float("inf"), "zero_average": 0}[change]
    elif change == "bad_confidence": entry["confidence"] = "certain"
    elif change == "no_reason": del entry["why"]
    else: entry["why"] = " "
    write()
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        TR.for_participant("synthetic-alpha")


def test_missing_ceiling_table(configuration):
    doc, _, write = configuration
    doc["participants"]["synthetic-alpha"]["safety_ceiling"]["values_mA"] = None
    write()
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        SC.ceiling_for("synthetic-alpha", "Left")


def test_band_timing_uses_only_valid_participant_evidence(configuration):
    assert TR.for_band("synthetic-alpha", None) == TR.for_participant("synthetic-alpha")
    assert TR.for_band("synthetic-alpha", {"available": False}) == TR.for_participant("synthetic-alpha")
    result = {"available": True, "onset_s": 9, "zero_undone_reached": True,
              "pick": {"transitions_per_hour": 1.2}, "hours_replayed": 4,
              "candidate": {"channel": "synthetic channel", "center_hz": 20}}
    out = TR.for_band("synthetic-alpha", result)
    assert out["onset_upper_ms"]["value_ms"] == 9000
    assert out["transition_up_ms"]["value_ms"] == 6000
    assert all(entry["participant_uid"] == "synthetic-alpha" and entry["config_digest"] == C.config_digest()
               for entry in out.values())
    assert "1.2" in out["onset_upper_ms"]["why"]
    result["pick"] = {}
    assert TR.for_band("synthetic-alpha", result)["onset_upper_ms"]["confidence"] == "Medium"
    result["zero_undone_reached"] = False
    assert TR.for_band("synthetic-alpha", result)["onset_upper_ms"]["confidence"] == "Low"
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        TR.for_band("synthetic-beta", result)
    for bad in (None, "invalid", -1, 0, float("nan")):
        result["onset_s"] = bad
        with pytest.raises(C.ClinicalConfigurationUnavailable):
            TR.for_band("synthetic-alpha", result)
    del result["onset_s"]
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        TR.for_band("synthetic-alpha", result)


def test_import_spellings_share_exception_identity():
    from DecodeCommon import private_clinical_config as host
    assert host is C
    assert SC.ClinicalConfigurationUnavailable is C.ClinicalConfigurationUnavailable
    assert TR.ClinicalConfigurationUnavailable is C.ClinicalConfigurationUnavailable


@pytest.fixture
def gate_configuration(configuration):
    doc, path, write = configuration
    participant = doc["participants"]["synthetic-alpha"]
    participant["adaptive_eligibility"] = {"programming_mode": "parkinsons", "source_commit": "c"*40,
        "evidence_ref": "synthetic/mode", "provenance": "Synthetic programmed mode observation"}
    participant["stage_gate_evidence"] = {
        "selected_bands": [{"outcome": "synthetic score", "center_hz": 20, "band_width_hz": 4,
                            "r": -0.2, "perm_p": 0.8, "fdr_q": None,
                            "exceeds_null_95th": False, "provenance": "Synthetic selected-band analysis"}],
        "response_summary": {"responds": False, "n_cells_suppressing": 1, "n_cells_total": 4,
                             "one_sided_p": 0.8, "replication_note": "", "source": "Synthetic response analysis"},
        "source_commit": "d"*40, "evidence_ref": "synthetic/gate", "provenance": "Synthetic historical handover"}
    write()
    return participant, write


def test_explicit_gate_and_mode_bindings(gate_configuration):
    from modules.StimOptimizer.routines import stage_gate as G, percept_adaptive as PA
    participant, write = gate_configuration
    bands, response = G.source_evidence_for("synthetic-alpha")
    assert bands[0].center_hz == 20
    assert not bands[0].statistically_supported()
    assert response.responds is False
    assert response.n_cells_total == 4
    assert PA.participant_eligibility("synthetic-alpha")["programming_mode"] == "parkinsons"
    participant["adaptive_eligibility"]["programming_mode"] = "non_parkinsons"
    write()
    assert PA.participant_eligibility("synthetic-alpha")["programming_mode"] == "non_parkinsons"
    for call in (G.source_evidence_for, PA.participant_eligibility):
        with pytest.raises(C.ClinicalConfigurationUnavailable):
            call("synthetic-beta")
    participant["adaptive_eligibility"]["programming_mode"] = "unknown"
    write()
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        PA.participant_eligibility("synthetic-alpha")


@pytest.mark.parametrize("target,key,value", [
    ("root", "selected_bands", []), ("root", "response_summary", []),
    ("root", "selected_bands", [None]), ("root", "selected_bands", [{}]),
    ("band", "outcome", ""), ("band", "provenance", None), ("band", "center_hz", 0),
    ("band", "band_width_hz", 0), ("band", "r", float("nan")), ("band", "r", -2),
    ("band", "r", True), ("band", "r", "bad"), ("band", "perm_p", 2),
    ("band", "exceeds_null_95th", 1),
    ("response", "responds", 1), ("response", "n_cells_suppressing", -1),
    ("response", "n_cells_total", 1.5), ("response", "n_cells_suppressing", 5),
    ("response", "one_sided_p", -1), ("response", "source", ""),
    ("response", "source", None), ("response", "replication_note", None),
    ("root", "response_summary", {}),
])
def test_invalid_gate_evidence(gate_configuration, target, key, value):
    participant, write = gate_configuration
    evidence = participant["stage_gate_evidence"]
    scope = evidence if target == "root" else evidence["selected_bands"][0] if target == "band" else evidence["response_summary"]
    scope[key] = value
    write()
    with pytest.raises(C.ClinicalConfigurationUnavailable):
        C.stage_gate_evidence_for("synthetic-alpha")


def test_absent_statistic_is_not_an_invented_verdict(gate_configuration):
    participant, write = gate_configuration
    record = participant["stage_gate_evidence"]
    record["selected_bands"][0].update(perm_p=None, fdr_q=None, exceeds_null_95th=None)
    record["response_summary"].update(responds=None, n_cells_suppressing=None, n_cells_total=None, one_sided_p=None)
    write()
    assert C.stage_gate_evidence_for("synthetic-alpha")["response_summary"]["responds"] is None


def test_gate_cannot_default_missing_side_to_grid_limit():
    from modules.StimOptimizer.routines import stage_gate as G
    for ceiling, sides in ((None, ["Left"]), ({"Left": 2}, ["Left", "Right"]), ({}, [])):
        with pytest.raises(C.ClinicalConfigurationUnavailable):
            G._ceiling_by_side(ceiling, sides)
    assert G._ceiling_by_side(2.2, ["Left"]) == (2.2, None)
    scalar, sides = G._ceiling_by_side({"Left": (2.2, "source"), "Right": [3.1]}, ["Left", "Right"])
    assert scalar == 2.2
    assert sides == {"Left": {"ceiling_mA": 2.2, "provenance": "source"},
                     "Right": {"ceiling_mA": 3.1, "provenance": "caller-supplied"}}
    assert G._ceiling_by_side({"Left": 2.2}, ["Left"])[0] == 2.2


def test_section_digest_describes_parsed_bytes(configuration, monkeypatch):
    import hashlib
    _, path, _ = configuration
    original = path.read_bytes()
    original_loads = C.json.loads
    def replace_while_parsing(raw, **kwargs):
        path.write_text("{}"); path.chmod(0o600)
        return original_loads(raw, **kwargs)
    monkeypatch.setattr(C.json, "loads", replace_while_parsing)
    section = C.participant_section("synthetic-alpha", "timing")
    assert section["configuration_digest"] == hashlib.sha256(original).hexdigest()
    assert section["configuration_digest"] != C.config_digest()
