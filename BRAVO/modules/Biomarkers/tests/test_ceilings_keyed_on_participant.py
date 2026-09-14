"""Review B3 (2026-09-12): RCS08's outlier ceilings apply to RCS08 and to nobody else.

`analytics.BAND_SWEEP_LSB_CEILINGS` holds the 99.5th-percentile ceilings measured on RCS08's own
history (decision 94), under the six standard Percept contact-pair names every participant has.
Keyed on the contact alone, a second participant with the same six names would have had RCS08's
numbers applied to their own band powers, silently. The table is now keyed on the participant
first, and the sweep looks it up through one function.

Pinned on the sweep's own return value: for `ZERO_THREE_RIGHT` under a made-up participant the
per-piece ceiling rule does not run (`chunk_exclusion` is None -- the MAD rule's path), under
RCS08's uid it does (a dict). Plain asserts; the container runner has no pytest.
"""
from ..routines import analytics as A
from .test_device_spectrum_mark import _sweep_power, COVERED_UID, COVERED_CHANNEL

RCS08 = "2e3c75c00d7f4f37b53a048d195f11da"


def test_the_table_is_keyed_on_rcs08_and_holds_its_six_contacts():
    assert COVERED_UID == RCS08
    assert set(A.BAND_SWEEP_LSB_CEILINGS) == {RCS08}, "one participant's ceilings, under its own uid"
    assert set(A.BAND_SWEEP_LSB_CEILINGS[RCS08]) == {
        "ZERO_THREE_RIGHT", "ONE_THREE_LEFT", "ZERO_THREE_LEFT", "ZERO_TWO_LEFT",
        "ONE_THREE_RIGHT", "ZERO_TWO_RIGHT"}
    # One real number, read back through the lookup: the 24.5 Hz ceiling on R 0-3.
    assert A.band_sweep_lsb_ceiling(RCS08, "ZERO_THREE_RIGHT", 24.5) == 498.6
    assert A.band_sweep_ceiling_table(RCS08, "ZERO_THREE_RIGHT")[24.5] == 498.6


def test_another_participant_with_the_same_contact_name_takes_the_mad_rule():
    *_rest, chunk_excl, _flags = _sweep_power("ZERO_THREE_RIGHT", participant_uid="another-participant")
    assert chunk_excl is None, "RCS08's ceilings ran for a participant they were not measured on"
    *_rest, chunk_excl, _flags = _sweep_power("ZERO_THREE_RIGHT", participant_uid=None)
    assert chunk_excl is None, "no participant named, so no participant's ceilings may run"
    assert A.band_sweep_ceiling_table("another-participant", "ZERO_THREE_RIGHT") is None
    assert A.band_sweep_lsb_ceiling("another-participant", "ZERO_THREE_RIGHT", 24.5) is None


def test_rcs08_still_takes_its_own_ceilings():
    *_rest, chunk_excl, _flags = _sweep_power("ZERO_THREE_RIGHT", participant_uid=RCS08)
    assert isinstance(chunk_excl, dict), chunk_excl
    assert chunk_excl.get("rule") or chunk_excl, "the per-piece ceiling rule reports itself"
    # and a contact RCS08's table does not name still takes the MAD rule
    *_rest, chunk_excl, _flags = _sweep_power("A_CONTACT_WITH_NO_CEILING_TABLE", participant_uid=RCS08)
    assert chunk_excl is None


def test_the_service_reads_the_table_through_the_one_lookup_only():
    """The dict is read in one place (`analytics.band_sweep_ceiling_table`); the service does not
    index it itself, so the participant key cannot be dropped at one call site (review B9.2)."""
    import inspect
    from .. import bravo_service as B
    src = inspect.getsource(B._band_time_sweep_power_by_seconds)
    assert "band_sweep_ceiling_table(participant_uid, channel)" in src
    assert "BAND_SWEEP_LSB_CEILINGS.get(" not in src


if __name__ == "__main__":
    test_the_table_is_keyed_on_rcs08_and_holds_its_six_contacts()
    test_another_participant_with_the_same_contact_name_takes_the_mad_rule()
    test_rcs08_still_takes_its_own_ceilings()
    test_the_service_reads_the_table_through_the_one_lookup_only()
    print("All ceiling-keyed-on-participant tests passed.")
