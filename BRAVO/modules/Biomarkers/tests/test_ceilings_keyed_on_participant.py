"""Review B3 (2026-09-12): RCS08's outlier ceilings apply to RCS08 and to nobody else.

`analytics.BAND_SWEEP_LSB_CEILINGS` holds the 99.5th-percentile ceilings measured on RCS08's own
history (decision 94), under the six standard Percept contact-pair names every participant has.
Keyed on the contact alone, a second participant with the same six names would have had RCS08's
numbers applied to their own band powers, silently. The table is now keyed on the participant
first, and the sweep looks it up through one function.

Since 2026-10-03 (decision 410) the sweep reads no ceiling table: every contact of every
participant is judged by its own 7-MAD-above bound. The table stays as the measured record of
decision 94, and its lookup still refuses another participant. Plain asserts.
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


def test_the_lookup_never_hands_rcs08s_numbers_to_another_participant():
    assert A.band_sweep_ceiling_table("another-participant", "ZERO_THREE_RIGHT") is None
    assert A.band_sweep_lsb_ceiling("another-participant", "ZERO_THREE_RIGHT", 24.5) is None
    assert A.band_sweep_ceiling_table(None, "ZERO_THREE_RIGHT") is None


def test_the_sweep_no_longer_reads_the_table():
    """Since 2026-10-03 (decision 410) every contact of every participant is judged by its own
    7-MAD-above bound (`analytics.chunk_upper_bounds`); the table chooses nothing in the sweep."""
    import inspect
    from .. import bravo_service as B
    src = inspect.getsource(B._band_time_sweep_power_by_seconds).split('"""')[2]
    assert "band_sweep_ceiling_table(" not in src and "BAND_SWEEP_LSB_CEILINGS" not in src


if __name__ == "__main__":
    test_the_table_is_keyed_on_rcs08_and_holds_its_six_contacts()
    test_the_lookup_never_hands_rcs08s_numbers_to_another_participant()
    test_the_sweep_no_longer_reads_the_table()
    print("All ceiling-keyed-on-participant tests passed.")
