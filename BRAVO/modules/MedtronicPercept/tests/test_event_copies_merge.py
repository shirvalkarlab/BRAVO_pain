"""A patient event appears in several exports, and its copies differ: the device adds the PSD to a
later export, drops it from a still later one, lists one side only, or leaves the contact pair
(SenseID) empty. The ingester used to keep whichever copy it stored first and skip the rest, which
lost the PSD of 263 RCS08 events (the PI, 2026-10-05: ingest ALL data, decision 439). Every copy
is now merged into one event; an event with no brain data in any copy is not stored.

Values: no stored copy and a PSD -> create; no PSD in any copy -> nothing stored; stored without
PSD, later copy with -> attach; stored one side, later copy the other -> both sides; empty SenseID
filled; identical copy -> nothing to do; differing spectra on one side -> kept as stored, flagged."""
from modules.MedtronicPercept.BrainSenseEvent import mergeEventData

L = "HemisphereLocationDef.Left"
R = "HemisphereLocationDef.Right"


def side(power, sense="ZERO_THREE_LEFT"):
    return {"Frequency": [1.0, 2.0], "FFTBinData": list(power), "SenseID": sense}


def test_first_copy_with_a_spectrum_is_created_and_one_without_is_not_stored():
    assert mergeEventData(None, {L: side([1, 2])}) == ("create", {L: side([1, 2])}, [])
    assert mergeEventData(None, None)[0] == "drop"
    assert mergeEventData(None, {})[0] == "drop"


def test_a_later_copy_attaches_the_spectrum_or_the_missing_side():
    assert mergeEventData({}, {L: side([1, 2])}) == ("update", {L: side([1, 2])}, [])
    got = mergeEventData({L: side([1, 2])}, {L: side([1, 2]), R: side([3, 4], "ZERO_THREE_RIGHT")})
    assert got == ("update", {L: side([1, 2]), R: side([3, 4], "ZERO_THREE_RIGHT")}, [])


def test_an_empty_contact_pair_is_filled_from_a_later_copy():
    got = mergeEventData({L: side([1, 2], "")}, {L: side([1, 2])})
    assert got == ("update", {L: side([1, 2])}, [])


def test_an_identical_or_poorer_copy_changes_nothing():
    assert mergeEventData({L: side([1, 2])}, {L: side([1, 2])})[0] == "keep"
    assert mergeEventData({L: side([1, 2])}, None)[0] == "keep"
    assert mergeEventData({L: side([1, 2])}, {L: side([1, 2], "")})[0] == "keep"


def test_differing_spectra_keep_the_stored_one_and_are_flagged():
    action, merged, conflicts = mergeEventData({L: side([1, 2])}, {L: side([9, 9])})
    assert action == "keep" and merged == {L: side([1, 2])}
    assert conflicts == [L]


def test_non_side_fields_of_the_stored_metadata_are_kept():
    stored = {L: side([1, 2]), "note": "x"}
    action, merged, _ = mergeEventData(stored, {R: side([3, 4], "ZERO_THREE_RIGHT")})
    assert action == "update" and merged["note"] == "x" and set(merged) == {L, R, "note"}
