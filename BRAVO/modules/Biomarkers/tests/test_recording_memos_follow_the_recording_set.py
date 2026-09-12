"""The in-process recording memos are keyed on the participant's CURRENT recording set.

WHY, 2026-09-11. Four memos in `bravo_service` (`_RECORDINGS_SETUP_MEMO`, `_POWER_LIST_MEMO`,
`_AVAILABILITY_RECORDINGS_MEMO`, `_AVAILABILITY_RESULT_MEMO`) were keyed on the participant uid
alone, justified by "recordings are immutable once exported". Each recording is; the SET is not:
the daily noon ingest adds 4-5 recording rows for RCS08 every day, nothing cleared the memos, and a
gunicorn worker that had served the timeline before noon kept serving the previous day's list until
it restarted. Reproduced in one process on the live server before the fix: a new recording row
appeared, the endpoint performed 0 recording loads and reported the old count (574 chronic rows);
after the fix, 5 loads and 575.

These tests need no database: the recording-set identity and the loaders are stubbed, so what is
pinned is the KEYING -- the same set is served from memory, a different set is a miss -- and the
bounded eviction that was already there. Plain asserts, no pytest fixtures (the container runner
has no pytest).
"""
import inspect
import os
import sys

_BRAVO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, _BRAVO_ROOT)
sys.path.insert(0, os.path.join(_BRAVO_ROOT, "modules"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "BRAVO.settings")
try:
    import django  # noqa: E402
    django.setup()
except Exception:
    pass
from Biomarkers import bravo_service as bs  # noqa: E402

UID = "memo-test-participant"


class _Stubs:
    """Swap the identity and the loaders for counting stand-ins; restore on exit, always."""

    def __init__(self, identity):
        self.identity = identity
        self.loads = []

    def __enter__(self):
        self._saved = {n: getattr(bs, n) for n in (
            "_recording_set_identity", "_load_recordings", "_build_sensing_config_index",
            "_event_psd_lsb_blocks", "_montage_psd_lsb_blocks", "_derive_chan_order")}
        bs._recording_set_identity = lambda uid: self.identity
        bs._load_recordings = lambda uid, types: (self.loads.append(tuple(types)) or [])
        bs._build_sensing_config_index = lambda td: {}
        bs._event_psd_lsb_blocks = lambda uid, **k: []
        bs._montage_psd_lsb_blocks = lambda uid, **k: []
        bs._derive_chan_order = lambda td: []
        for memo in (bs._RECORDINGS_SETUP_MEMO, bs._POWER_LIST_MEMO, bs._AVAILABILITY_RECORDINGS_MEMO):
            memo.clear()
        return self

    def __exit__(self, *exc):
        for n, v in self._saved.items():
            setattr(bs, n, v)
        for memo in (bs._RECORDINGS_SETUP_MEMO, bs._POWER_LIST_MEMO, bs._AVAILABILITY_RECORDINGS_MEMO):
            memo.clear()
        return False


_MEMOS = (
    ("availability recordings", lambda: bs._availability_recordings_cached(UID), 3),
    ("power list", lambda: bs._power_list_cached(UID), 2),
    ("recordings setup", lambda: bs._recordings_setup_cached(UID), 2),
)


def test_the_same_recording_set_is_served_from_memory():
    """Second call for an unchanged recording set performs no recording load at all."""
    for label, call, n_loads in _MEMOS:
        with _Stubs((UID, 10, "aaaa")) as st:
            first = call()
            assert len(st.loads) == n_loads, (label, st.loads)
            second = call()
            assert len(st.loads) == n_loads, (label, "reloaded although nothing changed", st.loads)
            assert second is first, label


def test_a_new_recording_row_is_a_miss_for_every_memo():
    """A different recording-set identity (one more row, or a different digest) reloads."""
    for label, call, n_loads in _MEMOS:
        with _Stubs((UID, 10, "aaaa")) as st:
            call()
            assert len(st.loads) == n_loads, label
            st.identity = (UID, 11, "bbbb")          # the daily ingest added a row
            call()
            assert len(st.loads) == 2 * n_loads, (label, "did not reload after the set changed", st.loads)
            st.identity = (UID, 10, "aaaa")          # the earlier set is still in memory
            call()
            assert len(st.loads) == 2 * n_loads, (label, "reloaded a set already held", st.loads)


def test_the_memo_stays_bounded_across_many_recording_sets():
    """The size cap that existed before still holds when the key carries the recording set."""
    for label, call, _ in _MEMOS:
        with _Stubs((UID, 0, "x")) as st:
            for i in range(bs._AVAILABILITY_RECORDINGS_MEMO_MAX + 5):
                st.identity = (UID, i, "digest-%d" % i)
                call()
            sizes = {"availability recordings": len(bs._AVAILABILITY_RECORDINGS_MEMO),
                     "power list": len(bs._POWER_LIST_MEMO),
                     "recordings setup": len(bs._RECORDINGS_SETUP_MEMO)}
            caps = {"availability recordings": bs._AVAILABILITY_RECORDINGS_MEMO_MAX,
                    "power list": bs._POWER_LIST_MEMO_MAX,
                    "recordings setup": bs._RECORDINGS_SETUP_MEMO_MAX}
            assert sizes[label] <= caps[label], (label, sizes[label], caps[label])


def test_the_timeline_result_key_carries_the_recording_set():
    """The availability endpoint's own result memo is keyed on the recording set too -- read from
    the source, since calling the endpoint needs a participant, REDCap and the recordings. A key
    without it would serve yesterday's timeline even though the three loaders below it had moved."""
    src = inspect.getsource(bs.availability_for_participant)
    key_lines = [ln for ln in src.splitlines() if "cache_key = (" in ln]
    assert len(key_lines) == 1, key_lines
    assert "recording_set" in key_lines[0], key_lines[0]
    assert "_recording_set_identity(participant_uid)" in src
    # and the recordings memo is handed the same identity rather than computing it twice
    assert "_availability_recordings_cached(" in src and "recording_set=recording_set" in src


def test_the_identity_of_an_unknown_participant_is_empty_not_an_error():
    ident = bs._recording_set_identity("no-such-participant-uid")
    assert ident == ("no-such-participant-uid", 0, ""), ident
