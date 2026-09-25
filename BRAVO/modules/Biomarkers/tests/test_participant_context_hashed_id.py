"""The participant-context service (`/service/queryParticipantContext`) failed for RCS08: one of its
source files carries no `hashed_id`, and the check for "already on the tablet" read it with [] and
raised KeyError before any session was returned (found 2026-09-24 proving decision 263). A file with
no hashed_id cannot match a tablet's list, so it is simply not one of them. Container suite."""
from types import SimpleNamespace

from modules import Database


def test_a_file_with_no_hashed_id_is_not_on_the_tablet_and_does_not_raise():
    no_id = SimpleNamespace(metadata={"Device": "d"})
    with_id = SimpleNamespace(metadata={"Device": "d", "hashed_id": "abc"})
    assert Database._already_on_tablet(no_id, ["abc"]) is False
    assert Database._already_on_tablet(with_id, ["abc"]) is True
    assert Database._already_on_tablet(with_id, []) is False
