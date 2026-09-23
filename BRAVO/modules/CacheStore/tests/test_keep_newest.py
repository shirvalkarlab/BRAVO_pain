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


def test_the_spectrum_matrix_keeps_its_two_live_writers_entries():
    """Biomarkers review B4 (2026-09-12). The assembled spectrum matrix has two live writers under
    two keys -- the page's rating-centred key and the daily ingest's legacy first-window key --
    and under a limit of one they evicted each other every day. Written in turn, both must still
    read back; a third key still evicts the oldest."""
    kind = "biomarker_psd_matrix"
    assert st.KEEP_NEWEST_BY_KIND.get(kind) == 2
    with _Sandbox():
        sig_page = (kind, "v1", UID, "recordings", "reports-abc")   # the page: with a report set
        sig_ingest = (kind, "v1", UID, "recordings", "")            # the ingest: no report set
        st.store(kind, UID, sig_page, {"which": "page"}, writer="biomarkers", provenance=[])
        st.store(kind, UID, sig_ingest, {"which": "ingest"}, writer="biomarkers", provenance=[])
        assert st.load(kind, UID, sig_page) == {"which": "page"}, "the ingest's write evicted the page's"
        assert st.load(kind, UID, sig_ingest) == {"which": "ingest"}
        assert len(_payload_files(kind)) == 2
        sig_page2 = (kind, "v1", UID, "recordings", "reports-def")  # a new rating: a third key
        st.store(kind, UID, sig_page2, {"which": "page2"}, writer="biomarkers", provenance=[])
        assert len(_payload_files(kind)) == 2, _payload_files(kind)
        assert st.load(kind, UID, sig_page) is None, "the oldest goes"
        assert st.load(kind, UID, sig_page2) == {"which": "page2"}


def test_the_stim_optimizer_response_keeps_both_page_requests():
    """The Stim Optimizer page makes two requests, plain and with the two-stage plan, each under
    its own key (2026-09-12). Under a limit of one they evicted each other, so the second page
    load rebuilt what the first had just stored. Written in turn, both must still read back."""
    kind = "stim_optimizer_response"
    assert st.KEEP_NEWEST_BY_KIND.get(kind) == 2
    with _Sandbox():
        sig_plain = (kind, "v1", UID, "inputs", "two_stage=0")
        sig_two = (kind, "v1", UID, "inputs", "two_stage=1")
        st.store(kind, UID, sig_plain, {"which": "plain"}, writer="stim_optimizer", provenance=[])
        st.store(kind, UID, sig_two, {"which": "two_stage"}, writer="stim_optimizer", provenance=[])
        assert st.load(kind, UID, sig_plain)["which"] == "plain"
        assert st.load(kind, UID, sig_two)["which"] == "two_stage"


def test_the_stability_answer_keeps_one_entry_per_grid_it_answers():
    """Found live on 2026-09-23: the heat maps' stability column read "not tested" on all 132 rows
    of every grid, while the background log said "stored 132 of 132 points" dozens of times that
    day. The stability answer is filed under the key of the grid it answers (the grid's own key is
    part of it), so each grid -- each pain score, at the reader's settings and at the daily
    defaults -- is its own entry of this kind. Under the default of one, every run deleted the run
    before it: one entry was left on disk, filed under whichever grid ran last, and every other
    grid, the page's own among them, found nothing. The decision-107 failure a fourth time.

    So the stability kind keeps as many entries as the grid kind it answers, and twelve answers
    written in turn all read back. The kind name is spelled out because the constant that holds it
    (`Biomarkers.bravo_service.STABILITY_GRID_KIND`) lives in a module that needs Django."""
    kind = "biomarker_band_stability_grid"
    assert st.KEEP_NEWEST_BY_KIND.get(kind, 1) >= st.KEEP_NEWEST_BY_KIND[KIND], (
        "one stability answer per grid needs at least as many entries as there are grids")
    grid_keys = [f"grid-{m}-{s}" for s in ("reader", "daily")
                 for m in ("nrs", "vas", "left_leg_vas", "back_vas", "mpq_sum", "composite")]
    with _Sandbox():
        sigs = {}
        for g in grid_keys:
            sigs[g] = (kind, "v1", UID, g, 5.0, "points-132")
            st.store(kind, UID, sigs[g], {"points": [g]}, writer="biomarkers", provenance=[])
        lost = [g for g in grid_keys if st.load(kind, UID, sigs[g], consumer="biomarkers") is None]
    assert not lost, f"these grids' stability answers were evicted by later runs: {lost}"
