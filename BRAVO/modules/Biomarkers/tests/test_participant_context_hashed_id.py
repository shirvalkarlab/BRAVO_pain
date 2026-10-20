"""A source file without hashed_id cannot match a tablet's list. The participant-context
service must handle that missing field without KeyError and still return sessions.
These tests construct the missing-metadata case directly."""
from types import SimpleNamespace

from modules import Database


def test_a_file_with_no_hashed_id_is_not_on_the_tablet_and_does_not_raise():
    no_id = SimpleNamespace(metadata={"Device": "d"})
    with_id = SimpleNamespace(metadata={"Device": "d", "hashed_id": "abc"})
    assert Database._already_on_tablet(no_id, ["abc"]) is False
    assert Database._already_on_tablet(with_id, ["abc"]) is True
    assert Database._already_on_tablet(with_id, []) is False
