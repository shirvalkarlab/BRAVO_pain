"""Entirely synthetic reviewed-contact decisions; no source or service access."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from modules.MedtronicPercept import BrainSenseEvent as events
from modules.MedtronicPercept import ContactAdjudication as contacts

LEFT = "HemisphereLocationDef.Left"
RIGHT = "HemisphereLocationDef.Right"
PAIR = "SensingElectrodeConfigDef.ONE_AND_THREE"
OTHER = "SensingElectrodeConfigDef.ZERO_AND_THREE"


def reviewed_block():
    block = {"Frequency": [0., 1., 2.], "FFTBinData": [0., 2., -1.],
             "DateTimeBlockId": 7, "DateTimeOffsetInSeconds": 100,
             "DateTime": "2026-01-01T00:00:00Z", "GroupId": "GroupIdDef.GROUP_D",
             "SenseID": "", "SenseIDStatus": "ambiguous", "SenseIDConflict": True,
             "SenseIDObservations": [{"sense_id": PAIR}, {"sense_id": OTHER}],
             "RawSpectrumIdentity": {"version": events.RAW_SPECTRUM_VERSION,
                 "source_id": "synthetic-source", "source_hash": "source-checksum",
                 "sha256": "a" * 64, "raw_identity_sha256": "b" * 64}}
    block["ContactAdjudication"] = {
        "version": contacts.VERSION, "method": contacts.METHOD, "status": contacts.STATUS,
        "recording_uid": "synthetic-record", "hemisphere": LEFT, "sense_id": PAIR,
        "reviewed_at": "2026-01-02T00:00:00Z", "evidence_sha256": "c" * 64,
        "raw_identity_sha256": "b" * 64, "raw_spectrum_sha256": "a" * 64,
        "stored_spectrum_sha256": events.rawSpectrumDigest(block),
        "native_clock": {k: block[k] for k in ("DateTimeBlockId", "DateTimeOffsetInSeconds", "GroupId")},
        "source_claims": sorted([PAIR, OTHER]),
    }
    return block


def effective(block, hemisphere=LEFT, uid="synthetic-record"):
    return contacts.validated_contact_adjudication(block, hemisphere=hemisphere, recording_uid=uid)


def test_valid_review_preserves_raw_conflict_and_exposes_no_private_evidence():
    block = reviewed_block(); before = deepcopy(block)
    assert effective(block) == {"sense_id": PAIR, "status": contacts.STATUS,
                                "summary": contacts.SUMMARY, "source_conflict": True}
    assert block == before
    for hemisphere, uid in [(RIGHT, "synthetic-record"), (LEFT, "another-record"), (LEFT, None)]:
        assert effective(block, hemisphere, uid) is None


@pytest.mark.parametrize("field,value", [
    ("version", "unknown"), ("method", "nearest_export"), ("status", "resolved"),
    ("sense_id", "NOT_SET"), ("sense_id", "SensingElectrodeConfigDef.ZERO_AND_ONE"),
    ("evidence_sha256", "bad"), ("raw_identity_sha256", "d" * 64),
    ("raw_spectrum_sha256", "d" * 64), ("stored_spectrum_sha256", "d" * 64),
    ("reviewed_at", "2026-01-02"), ("reviewed_at", "invalid"),
    ("native_clock", {}), ("source_claims", [PAIR]),
])
def test_incomplete_or_mismatched_review_fails_closed(field, value):
    block = reviewed_block(); block["ContactAdjudication"][field] = value
    assert effective(block) is None


@pytest.mark.parametrize("change", ["array", "clock", "group", "identity", "version", "source",
                                  "new_claim", "unverified_claim", "identity_unverified", "missing_review"])
def test_changed_evidence_never_keeps_stale_assignment(change):
    block = reviewed_block()
    if change == "array": block["FFTBinData"][1] = 9
    if change == "clock": block["DateTimeOffsetInSeconds"] += 1
    if change == "group": block["GroupId"] = "GroupIdDef.GROUP_A"
    if change == "identity": block["RawSpectrumIdentity"]["raw_identity_sha256"] = "d" * 64
    if change == "version": block["RawSpectrumIdentity"]["version"] = "old"
    if change == "source": block["RawSpectrumIdentity"].pop("source_id")
    if change == "new_claim": block["SenseIDObservations"].append({"sense_id": "SensingElectrodeConfigDef.ZERO_AND_ONE"})
    if change == "unverified_claim": block["UnverifiedSenseIDObservations"] = [{"sense_id": PAIR}]
    if change == "identity_unverified": block["SpectrumIdentityStatus"] = "unverified"
    if change == "missing_review": block.pop("ContactAdjudication")
    assert effective(block) is None


def test_duplicate_import_and_blank_claims_preserve_review_without_reclassifying_source():
    block = reviewed_block(); incoming = deepcopy(block)
    incoming.pop("ContactAdjudication"); incoming.pop("SenseIDObservations")
    incoming["SenseID"] = OTHER
    _, merged, conflicts = events.mergeEventData({LEFT: block}, {LEFT: incoming})
    assert conflicts == [LEFT] and merged[LEFT]["SenseIDStatus"] == "ambiguous"
    assert merged[LEFT]["SenseID"] == "" and merged[LEFT]["FFTBinData"] == block["FFTBinData"]
    assert effective(merged[LEFT])["sense_id"] == PAIR
    merged[LEFT]["SenseIDObservations"].append({"sense_id": "NOT_SET"})
    assert effective(merged[LEFT])["sense_id"] == PAIR


@pytest.mark.parametrize("observations", [None, [], {}, [None], ["not-an-observation"],
                                         [{"sense_id": 3}], [{"sense_id": True}]])
def test_missing_or_malformed_source_ledger_cannot_authorize_review(observations):
    block = reviewed_block()
    block["SenseIDObservations"] = observations
    assert effective(block) is None


@pytest.mark.parametrize("absent", [None, "", "  ", "SenseIDDef.NOT_SET"])
def test_missing_contact_on_additional_copy_is_not_new_conflicting_evidence(absent):
    block = reviewed_block()
    block["SenseIDObservations"].append({"sense_id": absent, "source": {"source_id": "later-copy"}})
    before = deepcopy(block)
    assert effective(block)["sense_id"] == PAIR
    assert block == before  # Even the absent claim and its source stay in the ledger.


def test_raw_display_qualifies_decision_and_keeps_raw_conflict():
    block = reviewed_block()
    device = SimpleNamespace(get_info=lambda: {"Heritage": [], "Electrodes": []})
    devices = SimpleNamespace(filter=lambda **kw: SimpleNamespace(first=lambda: device))
    row = {"Id": "synthetic-record", "Device": "synthetic", "Metadata": {LEFT: block}, "Date": 1.}
    shown = events.extractBrainSenseEventRecording(row, devices)[0]
    assert shown["SenseConfig"] == PAIR and shown["SenseConfigStatus"] == contacts.STATUS
    assert shown["SenseConfigConflict"] and shown["SenseConfigRawStatus"] == "ambiguous"
    assert shown["SenseConfigAdjudicationSummary"] == contacts.SUMMARY
    assert shown["Power"] == block["FFTBinData"]
    block.pop("ContactAdjudication")
    shown = events.extractBrainSenseEventRecording(row, devices)[0]
    assert shown["SenseConfig"] == "" and shown["SenseConfigStatus"] == "ambiguous"


def test_both_biomarker_consumers_use_same_review_and_removal_withholds(monkeypatch):
    from modules.Biomarkers import bravo_service as bs
    block = reviewed_block()
    monkeypatch.setattr(bs.models.Participant, "find", lambda **kw: object())
    monkeypatch.setattr(bs.models.SourceFile, "find_all", lambda **kw: [object()])
    monkeypatch.setattr(bs, "_patient_event_rows", lambda *a: [SimpleNamespace(
        uid="synthetic-record", metadata={LEFT: block}, date=1., name="Synthetic")])
    for name in ("_event_psd_rows", "_event_psd_index"):
        row = getattr(bs, name)("synthetic")[0]
        assert row["channel"] == "ONE_THREE_LEFT"
        assert row["contact_status"] == contacts.STATUS and row["contact_source_conflict"]
        assert row["contact_assignment_note"] == contacts.SUMMARY
    block.pop("ContactAdjudication")
    assert bs._event_psd_rows("synthetic") == bs._event_psd_index("synthetic") == []


def test_review_addition_and_removal_change_matrix_cache_identity(monkeypatch):
    from modules.Biomarkers import bravo_service as bs
    block = reviewed_block(); review = block.pop("ContactAdjudication")
    class Rows:
        def values_list(self, *fields):
            return [("synthetic-record", "same-file", {LEFT: block})]
    monkeypatch.setattr(bs, "_recording_rows_for_psd", lambda *a: [])
    monkeypatch.setattr(bs.models.Participant, "find", lambda **kw: object())
    monkeypatch.setattr(bs.models.SourceFile, "find_all", lambda **kw: [object()])
    monkeypatch.setattr(bs, "_patient_event_rows", lambda *a: Rows())
    before = bs._psd_matrix_signature_orm("synthetic")[0]
    block["ContactAdjudication"] = review
    assert bs._psd_matrix_signature_orm("synthetic")[0] != before
    block.pop("ContactAdjudication")
    assert bs._psd_matrix_signature_orm("synthetic")[0] == before
