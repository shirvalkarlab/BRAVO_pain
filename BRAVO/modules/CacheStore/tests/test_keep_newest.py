"""How many current entries of one kind one participant may keep.

THE DEFECT THIS PINS WAS REAL AND SILENT. The store kept exactly one entry per participant per
kind, replaced whole on every write. The band-by-length grid is keyed on the pain score among other
things, so the six scores are six entries of one kind for one participant -- and writing the sixth
deleted the other five. Measured on RCS08 on 2026-09-10 while building the every-score precompute
(open item 7): six grids were computed and stored, each write reporting success, and ONE file was
left on disk. The page then rebuilt a score that had just been "stored", in 8.9 s, and nothing on
any page or in any log said why. Every test passed throughout, because no test asked what happened
to the entry written before last.

The first test is the load-bearing one and is written as the failing case: six entries written in
turn, six expected back. Under the old rule it returns one.

Django-free, like its neighbours: the store is pointed at a temporary directory of its own, and
plain `assert` is used because the container has no pytest.
"""
import os
import pathlib
import shutil
import sys
import tempfile

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.CacheStore import store as st

UID = "2e3c75c00d7f4f37b53a048d195f11da"
KIND = "biomarker_band_sweep"          # a kind whose key carries the reader's own choice
ONE_ONLY = "raw_lsb_tiles"             # a kind that must keep on keeping exactly one


class _Sandbox:
    def __enter__(self):
        from modules.CacheStore import ledger
        self._dir = tempfile.mkdtemp(prefix="bravo_keep_newest_test_")
        self._prev_dir, self._prev_ledger = st.DIR_OVERRIDE, ledger.ENABLED
        st.DIR_OVERRIDE, ledger.ENABLED = self._dir, False
        return self

    def __exit__(self, *exc):
        from modules.CacheStore import ledger
        st.DIR_OVERRIDE, ledger.ENABLED = self._prev_dir, self._prev_ledger
        shutil.rmtree(self._dir, ignore_errors=True)
        return False


def _write(kind, metric, payload=None):
    """One entry whose key differs only in the pain score, as the real grid's key does."""
    sig = (kind, "v1", UID, "tiles-key", "reports-key", metric)
    st.store(kind, UID, sig, payload if payload is not None else {"metric": metric},
             writer="biomarkers", provenance=[])
    return sig


def _payload_files(kind):
    d = st.kind_dir(kind, create=False)
    names = [n for n in (os.listdir(d) if d else []) if UID in n]
    return sorted(n for n in names if not n.endswith(".meta.json"))


def test_six_pain_scores_written_in_turn_are_all_still_readable():
    """THE LOAD-BEARING ONE. Six scores in, six scores back, each with its own value.

    Read back through the store's own `load` rather than by counting files, so this fails if the
    entries survive on disk but cannot be served -- which is the only thing a reader would notice.
    """
    metrics = ["nrs", "vas", "left_leg_vas", "back_vas", "mpq_sum", "composite_mpq_leftleg"]
    with _Sandbox():
        sigs = {m: _write(KIND, m) for m in metrics}
        got = {m: st.load(KIND, UID, sigs[m], consumer="biomarkers") for m in metrics}
    missing = [m for m in metrics if got[m] is None]
    assert not missing, f"these pain scores were evicted by later writes: {missing}"
    for m in metrics:
        assert got[m] == {"metric": m}, (m, got[m])


def test_a_kind_that_is_not_listed_still_keeps_exactly_one():
    """The default is unchanged, and that matters: one tile entry is 245 MB, so a kind that quietly
    began keeping twelve of them would cost about three gigabytes per participant."""
    with _Sandbox():
        assert ONE_ONLY not in st.KEEP_NEWEST_BY_KIND
        first = _write(ONE_ONLY, "a")
        second = _write(ONE_ONLY, "b")
        assert len(_payload_files(ONE_ONLY)) == 1
        assert st.load(ONE_ONLY, UID, second, consumer="biomarkers") == {"metric": "b"}
        assert st.load(ONE_ONLY, UID, first, consumer="biomarkers") is None


def test_the_limit_is_a_limit_and_the_oldest_entry_is_the_one_that_goes():
    """Keeping several is not keeping all of them: a store that only grows is not a cache
    (decision 28's reasoning for bounding Redis). The entry just written is always kept, and the
    oldest of the rest is the first to go."""
    limit = st.KEEP_NEWEST_BY_KIND[KIND]
    with _Sandbox():
        sigs = [_write(KIND, f"m{i:03d}") for i in range(limit + 4)]
        files = _payload_files(KIND)
        assert len(files) == limit, (len(files), limit)
        # The newest `limit` are readable; everything older is gone.
        for sig in sigs[-limit:]:
            assert st.load(KIND, UID, sig, consumer="biomarkers") is not None
        for sig in sigs[:-limit]:
            assert st.load(KIND, UID, sig, consumer="biomarkers") is None


def test_an_entry_is_removed_whole_rather_than_leaving_a_sidecar_behind():
    """An entry is a payload plus a `.meta.json` sidecar, and the sidecar is the commit marker.
    A sweep that removed one and left the other would leave something that reads as an entry and
    has no content -- so the two are grouped by stem and go together."""
    limit = st.KEEP_NEWEST_BY_KIND[KIND]
    with _Sandbox():
        for i in range(limit + 3):
            _write(KIND, f"m{i:03d}")
        d = st.kind_dir(KIND, create=False)
        names = [n for n in os.listdir(d) if UID in n]
        payloads = {n.rsplit(".", 1)[0] for n in names if not n.endswith(".meta.json")}
        sidecars = {n[:-len(".meta.json")] for n in names if n.endswith(".meta.json")}
        assert payloads == sidecars, (sorted(payloads ^ sidecars))
        assert len(payloads) == limit


def test_one_participants_scores_do_not_evict_anothers():
    """The sweep has always been scoped to one participant, and the limit must not quietly change
    that -- a limit of twelve counted across participants would evict a second patient's answers as
    soon as the first had a full set."""
    other = "1111111111111111111111111111aaaa"
    limit = st.KEEP_NEWEST_BY_KIND[KIND]
    with _Sandbox():
        mine = [_write(KIND, f"m{i:03d}") for i in range(limit)]
        for i in range(limit):
            sig = (KIND, "v1", other, "tiles-key", "reports-key", f"m{i:03d}")
            st.store(KIND, other, sig, {"metric": f"m{i:03d}"}, writer="biomarkers", provenance=[])
        for sig in mine:
            assert st.load(KIND, UID, sig, consumer="biomarkers") is not None
