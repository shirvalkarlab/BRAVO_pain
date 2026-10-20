"""Metadata-only source corrections must invalidate every shared recording view."""
import pytest
from modules.DecodeCommon import recording_identity as identity


def test_row_order_and_mapping_order_stable_but_evidence_changes():
    a = identity.row_identity("a", "bytes", "chronic", {"ScheduleFlagged": [], "x": 1})
    b = identity.row_identity("b", "bytes", "chronic", {})
    assert a == identity.row_identity("a", "bytes", "chronic", {"x": 1, "ScheduleFlagged": []})
    baseline = identity.digest([a, b], 0, "config-a")
    assert baseline == identity.digest([b, a], None, "config-a")
    for field, value in (("ContactSchedule", [[1, "L"]]), ("FreqScheduleHz", [[1, 20]]),
                         ("SignalLeadSchedule", [[1, "RIGHT"]]),
                         ("ScheduleFlagged", [[1, None]]), ("ScheduleNoRecord", []),
                         ("ScheduleSource", "verified source")):
        changed = identity.row_identity("b", "bytes", "chronic", {field: value})
        assert baseline != identity.digest([a, changed], 0, "config-a")
    assert baseline != identity.digest([a, b], 1, "config-a")
    assert baseline != identity.digest([a, b], 0, "config-b")
    assert identity.row_identity("a", "bytes", "chronic", None) != identity.row_identity("a", "bytes", "chronic", {})


def test_invalid_nonfinite_metadata_cannot_claim_a_valid_identity():
    with pytest.raises(ValueError):
        identity.row_identity("a", "b", "c", {"x": float("nan")})
    with pytest.raises(ValueError):
        identity.digest([], float("inf"), "config")
