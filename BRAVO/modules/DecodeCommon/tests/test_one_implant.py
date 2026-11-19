"""Which device records are one implant (decision 489; `DecodeCommon/implants.py`): a shared serial
number, or an owner the PI's ruling lists with both records of the listed type. Plain asserts."""
import sys
import pathlib

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from DecodeCommon import implants as I

RCS08 = "2e3c75c00d7f4f37b53a048d195f11da"


def test_a_shared_serial_is_one_implant_for_any_owner():
    assert I.same_implant("p1", "Percept PC", "AAA", "p1", "Percept PC", "AAA")
    assert not I.same_implant("p1", "Percept PC", "AAA", "p1", "Percept PC", "BBB")


def test_rcs08s_records_of_its_device_type_are_one_implant_whatever_the_serial():
    assert I.same_implant(RCS08, "Percept RC", "masked7", RCS08, "Percept RC", "restored10")


def test_the_link_needs_the_listed_owner_and_type_on_both_records():
    assert not I.same_implant(RCS08, "Percept RC", "x", "someone-else", "Percept RC", "y")
    assert not I.same_implant(RCS08, "Percept RC", "x", RCS08, "Percept PC", "y")
    assert not I.same_implant("someone-else", "Percept RC", "x", "someone-else", "Percept RC", "y")


def test_every_entry_names_its_ruling():
    assert all(v.get("ruling") and v.get("type") for v in I.ONE_IMPLANT.values())
