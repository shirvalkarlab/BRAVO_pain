"""Tests for the 3 s-tile cache that the server's four worker processes share through a file.

WHAT THESE TESTS ARE FOR. Cutting participant RCS08's whole recording history into 3 s pieces and
computing a 98-band spectrum for each takes 37 s, and until now that work was remembered only
inside the one worker process that did it, so the first page view to reach each of the four
workers paid it again, and every edit to any Python file threw all four memories away. The tiles
are now also written to a file that every worker can read. These tests hold the file to the two
properties that make it safe to trust:

  * IT ANSWERS WITH THE SAME NUMBERS a fresh build would produce, value by value.
  * IT STOPS ANSWERING THE MOMENT ITS INPUTS CHANGE, because the key is the identity and content
    of every recording that feeds it and never a clock.

and to the three properties that make it safe to run in a server:

  * A DAMAGED FILE IS A REBUILD, NOT AN ERROR on the clinician's page.
  * TWO WORKERS BUILDING AT ONCE cannot leave a half-written file for a third to read.
  * WARMING IT AFTER AN INGEST cannot make an ingest fail, and costs almost nothing when there is
    nothing to do.

No Django and no database: `Server`, `Server.models` and `modules.Database` are stubbed the way
tests/test_redcap_request_scope.py stubs them, the recording rows the key is built from are
replaced by a small stand-in, and every file is written under a temporary directory.

Run inside the container:
    python3 _agent_bridge/run_tests.py
"""
import os
import pathlib
import pickle
import shutil
import sys
import tempfile
import threading
import unittest.mock as mock

import numpy as np

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _import_service():
    """Import `bravo_service` without Django."""
    for mod in ("Server", "Server.models", "modules.Database"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    for mod in ("modules.Biomarkers.pipeline", "modules.Biomarkers.adapter"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    import modules.Biomarkers.bravo_service as bs
    return bs


B = _import_service()
from modules.Biomarkers.routines import availability as AV  # noqa: E402

CENTERS = tuple(float(c) for c in np.arange(2.5, 30.0, 5.0))     # 6 band centres, enough to test
UID = "test-participant"


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# stand-ins for the inputs
# ─────────────────────────────────────────────────────────────────────────────────────────────────
class _Row:
    """One recording row, carrying only the columns the key reads."""

    def __init__(self, uid, hashed, type_, metadata=None):
        self.uid = uid
        self.hashed = hashed
        self.type = type_
        self.metadata = metadata


def _rows(n_td=2, n_event=2, event_fft=(1.0, 2.0, 3.0)):
    out = [_Row(f"td{i}", f"hash-td{i}", "MedtronicBrainSenseTimeDomain",
                {"CenterFrequencyHz": 12.0}) for i in range(n_td)]
    out += [_Row(f"ev{i}", "", B.PATIENT_EVENT_TYPE,
                 {"HemisphereLocationDef.Left": {"DateTime": f"2026-09-0{i + 1}T10:00:00Z",
                                                 "SenseID": "ZERO_THREE_LEFT",
                                                 "Frequency": [2.5, 7.5, 12.5],
                                                 "FFTBinData": list(event_fft)}})
            for i in range(n_event)]
    return out


def _td_recording(t0=1_700_000_000.0, seconds=60.0, fs=250.0, seed=0, amplitude=20.0):
    """One decoded time-domain recording, shaped the way the platform's loader yields them."""
    n = int(seconds * fs)
    rng = np.random.default_rng(seed)
    data = (amplitude * rng.standard_normal((n, 1))).astype(float)
    return {"ChannelNames": ["ZERO_THREE_LEFT"], "Data": data, "SamplingRate": fs,
            "StartTime": t0, "Duration": seconds, "product": "streaming_td",
            "RecordingType": "MedtronicBrainSenseTimeDomain"}


def _event_blocks(n=3, scale=1.0):
    """Three patient-event spectra, spread across the recording."""
    return [_event_block(t=1_700_000_000.0 + 10.0 * (i + 1), scale=scale) for i in range(n)]


def _event_block(t=1_700_000_004.0, scale=1.0):
    """One patient-event device spectrum, shaped the way `_event_psd_lsb_blocks` yields them."""
    freq = np.arange(1.0, 100.0, 1.0)
    return {"channel": "ZERO_THREE_LEFT", "t": t,
            "freq": freq.tolist(),
            "power": (scale * np.exp(-((freq - 12.0) ** 2) / 50.0)).tolist(),
            "center_hz": 12.0}


class _Bench:
    """A temporary shared-cache directory plus a stand-in for the recording rows.

    Everything a test changes is put back on exit, including the two process memos, so tests can
    run in any order inside one interpreter — which is how the container's runner runs them.
    """

    def __init__(self, rows=None):
        self.rows = _rows() if rows is None else rows
        self.dir = None
        self._saved = None

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="bravo_shared_tiles_")
        self._saved = (B._SHARED_CACHE_DIR_OVERRIDE, dict(B._SHARED_CACHE_EVENTS),
                       dict(B._RAW_LSB_CACHE_MEMO))
        B._SHARED_CACHE_DIR_OVERRIDE = self.dir
        B._RAW_LSB_CACHE_MEMO.clear()
        for k in B._SHARED_CACHE_EVENTS:
            B._SHARED_CACHE_EVENTS[k] = 0
        self._patch = mock.patch.object(B, "_raw_lsb_recording_identity", self._identity)
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        B._SHARED_CACHE_DIR_OVERRIDE = self._saved[0]
        B._SHARED_CACHE_EVENTS.clear(); B._SHARED_CACHE_EVENTS.update(self._saved[1])
        B._RAW_LSB_CACHE_MEMO.clear(); B._RAW_LSB_CACHE_MEMO.update(self._saved[2])
        shutil.rmtree(self.dir, ignore_errors=True)
        return False

    def _identity(self, participant_uid):
        """The real key over the stand-in rows: the real function's body with the query removed."""
        import hashlib
        parts = []
        for r in self.rows:
            if str(r.type) == B.PATIENT_EVENT_TYPE:
                extra = repr(r.metadata)
            elif isinstance(r.metadata, dict):
                extra = "%r|%r|%r" % (r.metadata.get("CenterFrequencyHz"),
                                      r.metadata.get("FreqScheduleHz"),
                                      r.metadata.get("ContactSchedule"))
            else:
                extra = ""
            parts.append("%s~%s~%s~%s" % (r.uid, r.hashed or "", r.type, extra))
        h = hashlib.sha1()
        for s in sorted(parts):
            h.update(s.encode("utf8", "replace")); h.update(b"\x00")
        return (str(participant_uid), 1, len(self.rows), h.hexdigest()[:20])

    def files(self):
        return sorted(f for f in os.listdir(self.dir) if f.endswith(".pkl"))

    def build(self, td=None, events=None, *, fresh_process=False, use_shared_cache=True):
        """One call of the cached builder. `fresh_process` empties this process's memo first, which
        is what a worker that has just started, or has just been replaced by a reload, sees."""
        if fresh_process:
            B._RAW_LSB_CACHE_MEMO.clear()
        return B._raw_lsb_cache_cached(
            UID, ["ZERO_THREE_LEFT"],
            [_td_recording()] if td is None else td,
            _event_blocks() if events is None else events,
            montage_psd_blocks=[], centers=CENTERS, use_shared_cache=use_shared_cache)


def _or_empty(v):
    """`v`, or an empty list when it is missing, without asking an array whether it is truthy."""
    return [] if v is None else v


def _families_equal(a, b):
    """Every value of two tile caches compared, whatever shape each field is stored in.

    Returns (n_compared, n_different). The per-window spectra are compared through the same
    conversion the matcher uses, so a list of lists and the array it becomes are held to exact
    equality rather than to a tolerance; two missing values in the same place count as equal.
    """
    compared = different = 0
    keys = sorted(set(a) | set(b))
    for ch in keys:
        ea, eb = a.get(ch), b.get(ch)
        if not isinstance(ea, dict) or not isinstance(eb, dict):
            compared += 1
            different += int(ea is not eb)
            continue
        for k in sorted(set(ea) | set(eb)):
            if k in ("td", "psd"):
                continue
            compared += 1
            different += int(not np.array_equal(np.asarray(ea.get(k), dtype=object),
                                                np.asarray(eb.get(k), dtype=object)))
        for fam in ("td", "psd"):
            fa, fb = ea.get(fam) or {}, eb.get(fam) or {}
            nC = int(np.asarray(ea.get("centers_hz") or [], dtype=float).size)
            for k in sorted(set(fa) | set(fb)):
                if k == AV._LSB_MAT_MEMO_KEY:
                    continue
                if k == "lsb":
                    # `x or []` is wrong here for the same reason it was wrong inside
                    # `_lsb_family_mat`: one of these two sides is an array once it has been
                    # through the file, and asking an array whether it is truthy raises.
                    ma = AV._lsb_rows_to_mat(_or_empty(fa.get(k)), nC)
                    mb = AV._lsb_rows_to_mat(_or_empty(fb.get(k)), nC)
                    compared += int(ma.size)
                    if ma.shape != mb.shape:
                        different += max(ma.size, mb.size)
                    else:
                        different += int(np.count_nonzero(
                            ~((ma == mb) | (np.isnan(ma) & np.isnan(mb)))))
                    continue
                va = np.asarray(fa.get(k) if fa.get(k) is not None else [], dtype=object).ravel()
                vb = np.asarray(fb.get(k) if fb.get(k) is not None else [], dtype=object).ravel()
                compared += int(max(va.size, vb.size))
                if va.shape != vb.shape:
                    different += int(max(va.size, vb.size))
                else:
                    different += int(np.count_nonzero(va != vb))
    return compared, different


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# the file is written, found by a fresh process, and holds the same numbers
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_first_build_writes_one_file_and_a_fresh_process_reads_it():
    with _Bench() as bench:
        first = bench.build()
        assert len(bench.files()) == 1, bench.files()
        assert B._SHARED_CACHE_EVENTS["writes"] == 1
        second = bench.build(fresh_process=True)
        assert B._SHARED_CACHE_EVENTS["hits"] == 1, B._SHARED_CACHE_EVENTS
        assert B._SHARED_CACHE_EVENTS["writes"] == 1, "a hit must not write the file again"
        compared, different = _families_equal(first, second)
        assert compared > 100, compared
        assert different == 0, (compared, different)


def test_the_stored_tiles_hold_the_same_numbers_as_a_build_that_never_saw_the_file():
    with _Bench() as bench:
        bench.build()
        from_file = bench.build(fresh_process=True)
        bypassed = bench.build(fresh_process=True, use_shared_cache=False)
        compared, different = _families_equal(from_file, bypassed)
        assert compared > 100, compared
        assert different == 0, (compared, different)


def test_a_second_worker_pays_no_build_when_the_file_is_there():
    """The point of the file: the tiles are computed once, not once per worker."""
    with _Bench() as bench:
        with mock.patch.object(AV, "raw_lsb_spectrum_cache",
                               wraps=AV.raw_lsb_spectrum_cache) as spy:
            bench.build()
            assert spy.call_count == 1
            bench.build(fresh_process=True)
            bench.build(fresh_process=True)
            assert spy.call_count == 1, "a worker that found the file must not build the tiles"


def test_the_matcher_reads_a_restored_cache_and_matches_a_rating_the_same_way():
    """The restored tiles go through the live matcher, not just through equality checks."""
    with _Bench() as bench:
        built = bench.build(use_shared_cache=False)
        bench.build()                                     # writes the file
        restored = bench.build(fresh_process=True)
        pro = np.asarray([1_700_000_006.0], dtype=float)
        a, sa = AV.live_lsb_spectrum_match(pro, built["ZERO_THREE_LEFT"],
                                           tol_s=60.0, td_quantity_s=30.0)
        b, sb = AV.live_lsb_spectrum_match(pro, restored["ZERO_THREE_LEFT"],
                                           tol_s=60.0, td_quantity_s=30.0)
        assert sa["n_pro_td"] == sb["n_pro_td"] == 1, (sa, sb)
        va = np.asarray([np.nan if x is None else x for x in a[0]["lsb"]], dtype=float)
        vb = np.asarray([np.nan if x is None else x for x in b[0]["lsb"]], dtype=float)
        assert np.isfinite(va).any(), "the test rating must actually match a tile"
        assert np.array_equal(va, vb, equal_nan=True), (va, vb)
        assert a[0]["tier"] == b[0]["tier"] and a[0]["used_s"] == b[0]["used_s"]


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# it stops answering when its inputs change
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_changed_recording_set_misses_the_file():
    with _Bench() as bench:
        bench.build()
        before = B._shared_path(B._RAW_LSB_SHARED_KIND, UID,
                                B._raw_lsb_shared_signature(UID, CENTERS))
        bench.rows = _rows(n_td=3)                        # one recording ingested
        after = B._shared_path(B._RAW_LSB_SHARED_KIND, UID,
                               B._raw_lsb_shared_signature(UID, CENTERS))
        assert before != after, "an added recording must change the key"
        with mock.patch.object(AV, "raw_lsb_spectrum_cache",
                               wraps=AV.raw_lsb_spectrum_cache) as spy:
            bench.build(fresh_process=True)
            assert spy.call_count == 1, "a changed recording set must rebuild"
        assert bench.files() == [os.path.basename(after)], \
            "the superseded entry must not be left behind"


def test_a_recording_edited_in_place_misses_the_file():
    """A re-decode that keeps the row's identity but changes its content hash must miss."""
    with _Bench() as bench:
        bench.build()
        before = bench.files()
        bench.rows[0].hashed = "hash-td0-rewritten"
        with mock.patch.object(AV, "raw_lsb_spectrum_cache",
                               wraps=AV.raw_lsb_spectrum_cache) as spy:
            bench.build(fresh_process=True)
            assert spy.call_count == 1
        assert bench.files() != before


def test_a_changed_patient_event_spectrum_misses_the_file():
    """The patient-event rows carry NO content hash, so their spectra are hashed themselves."""
    with _Bench() as bench:
        bench.build()
        before = B._raw_lsb_shared_signature(UID, CENTERS)
        bench.rows = _rows(event_fft=(1.0, 2.0, 4.0))     # same row, one number changed
        after = B._raw_lsb_shared_signature(UID, CENTERS)
        assert before != after, "a changed patient-event spectrum must change the key"


def test_a_changed_sensing_centre_on_a_row_misses_the_file():
    """`CenterFrequencyHz` is stamped on the row after decoding, so no file hash covers it."""
    with _Bench() as bench:
        before = B._raw_lsb_shared_signature(UID, CENTERS)
        bench.rows[0].metadata = {"CenterFrequencyHz": 18.0}
        assert B._raw_lsb_shared_signature(UID, CENTERS) != before


def test_a_changed_constant_misses_the_file():
    """Editing the transform's calibration changes every stored number and must miss."""
    with _Bench() as bench:
        bench.build()
        before = bench.files()
        with mock.patch.object(B.analytics, "LSB_PER_UV2_TRANSFORM",
                               float(B.analytics.LSB_PER_UV2_TRANSFORM) * 2.0):
            key_now = B._shared_path(B._RAW_LSB_SHARED_KIND, UID,
                                     B._raw_lsb_shared_signature(UID, CENTERS))
            assert os.path.basename(key_now) not in before
            with mock.patch.object(AV, "raw_lsb_spectrum_cache",
                                   wraps=AV.raw_lsb_spectrum_cache) as spy:
                bench.build(fresh_process=True)
                assert spy.call_count == 1


def test_a_changed_band_centre_grid_misses_the_file():
    with _Bench() as bench:
        a = B._raw_lsb_shared_signature(UID, CENTERS)
        b = B._raw_lsb_shared_signature(UID, tuple(list(CENTERS) + [40.0]))
        assert a != b


def test_the_pain_reports_are_not_in_the_key_and_do_not_invalidate_the_tiles():
    """The tiles are built with no knowledge of any rating, so a new pain report must NOT throw
    away a 37 s build. The reports are fetched and matched live on every request instead, which is
    what keeps the answer fresh — nothing about a rating is stored in this file."""
    with _Bench() as bench:
        bench.build()
        key = B._raw_lsb_shared_signature(UID, CENTERS)
        assert not any("pro" in str(part).lower() for part in key), key
        restored = bench.build(fresh_process=True)
        one = np.asarray([1_700_000_006.0], dtype=float)
        two = np.asarray([1_700_000_006.0, 1_700_000_009.0], dtype=float)
        _, s1 = AV.live_lsb_spectrum_match(one, restored["ZERO_THREE_LEFT"],
                                           tol_s=60.0, td_quantity_s=30.0)
        _, s2 = AV.live_lsb_spectrum_match(two, restored["ZERO_THREE_LEFT"],
                                           tol_s=60.0, td_quantity_s=30.0)
        assert s1["n_pro"] == 1 and s2["n_pro"] == 2, (s1, s2)
        assert B._SHARED_CACHE_EVENTS["writes"] == 1, "a new pain report must not rewrite the file"


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# a damaged file, a torn file, and a directory that cannot be used
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_truncated_file_is_a_rebuild_not_an_error():
    with _Bench() as bench:
        bench.build()
        path = os.path.join(bench.dir, bench.files()[0])
        with open(path, "r+b") as fh:
            fh.truncate(os.path.getsize(path) // 3)
        out = bench.build(fresh_process=True)
        assert out and "ZERO_THREE_LEFT" in out
        assert B._SHARED_CACHE_EVENTS["unreadable"] == 1, B._SHARED_CACHE_EVENTS
        assert len(bench.files()) == 1, "the damaged file must be replaced"


def test_a_file_full_of_nonsense_is_a_rebuild_not_an_error():
    with _Bench() as bench:
        bench.build()
        path = os.path.join(bench.dir, bench.files()[0])
        with open(path, "wb") as fh:
            fh.write(b"this is not a pickle at all")
        out = bench.build(fresh_process=True)
        assert out and "ZERO_THREE_LEFT" in out
        assert B._SHARED_CACHE_EVENTS["unreadable"] == 1


def test_a_file_written_under_a_different_key_is_a_rebuild_not_a_wrong_answer():
    """The signature inside the file is checked, so a name collision cannot serve wrong tiles."""
    with _Bench() as bench:
        bench.build()
        path = os.path.join(bench.dir, bench.files()[0])
        with open(path, "rb") as fh:
            stored = pickle.load(fh)
        stored["signature"] = ("something", "else")
        with open(path, "wb") as fh:
            pickle.dump(stored, fh, protocol=5)
        with mock.patch.object(AV, "raw_lsb_spectrum_cache",
                              wraps=AV.raw_lsb_spectrum_cache) as spy:
            bench.build(fresh_process=True)
            assert spy.call_count == 1


def test_no_directory_means_memory_only_and_is_not_an_error():
    with _Bench() as bench:
        B._SHARED_CACHE_DIR_OVERRIDE = None
        with mock.patch.object(B, "_psd_cache_dir", side_effect=RuntimeError("no Django here")):
            assert B.shared_cache_dir() is None
            out = bench.build(fresh_process=True)
            assert out and "ZERO_THREE_LEFT" in out


def test_two_builders_at_once_leave_one_whole_file():
    """Four workers with no warm file all build at once on the first burst of page views.

    The file is written to a temporary name and moved into place, so a reader arriving in the
    middle of a write sees either the old whole file or the new whole file. This runs the two
    builds in threads, then checks that what is on disk reads back completely and holds the same
    numbers as a build that never touched the file.
    """
    with _Bench() as bench:
        errors = []

        def one():
            try:
                B._raw_lsb_cache_cached(UID, ["ZERO_THREE_LEFT"], [_td_recording()],
                                        _event_blocks(), montage_psd_blocks=[],
                                        centers=CENTERS)
            except Exception as exc:                       # noqa: BLE001 - reported below
                errors.append(repr(exc))

        threads = [threading.Thread(target=one) for _ in range(2)]
        B._RAW_LSB_CACHE_MEMO.clear()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors
        assert len(bench.files()) == 1, bench.files()
        assert not [f for f in os.listdir(bench.dir) if f.endswith(".tmp")], \
            "no temporary file may be left behind"
        loaded = bench.build(fresh_process=True)
        bypassed = bench.build(fresh_process=True, use_shared_cache=False)
        compared, different = _families_equal(loaded, bypassed)
        assert compared > 100 and different == 0, (compared, different)


def test_an_entry_over_the_size_limit_is_refused_rather_than_written():
    with _Bench() as bench:
        saved = B._SHARED_CACHE_MAX_BYTES
        try:
            B._SHARED_CACHE_MAX_BYTES = 32
            out = bench.build()
            assert out and "ZERO_THREE_LEFT" in out
            assert bench.files() == []
            assert B._SHARED_CACHE_EVENTS["refused_too_big"] == 1
        finally:
            B._SHARED_CACHE_MAX_BYTES = saved


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# warming after an ingest
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def _warm_patches(bench, td=None, events=None):
    """The loaders `warm_shared_raw_cache` calls, replaced by the stand-in recordings."""
    td = [_td_recording()] if td is None else td
    events = _event_blocks() if events is None else events
    return (
        mock.patch.object(B, "_load_recordings",
                          side_effect=lambda uid, types: (td if types is B.TIMEDOMAIN_TYPES
                                                          else [])),
        mock.patch.object(B, "_event_psd_lsb_blocks", return_value=events),
        mock.patch.object(B, "_montage_psd_lsb_blocks", return_value=[]),
        mock.patch.object(B, "_derive_chan_order", return_value=["ZERO_THREE_LEFT"]),
    )


def test_warming_builds_the_file_when_it_is_absent():
    with _Bench() as bench:
        patches = _warm_patches(bench)
        for p in patches:
            p.start()
        try:
            got = B.warm_shared_raw_cache(UID, centers=CENTERS)
        finally:
            for p in patches:
                p.stop()
        assert got["status"] == "built", got
        assert got["file_written"] is True, got
        assert len(bench.files()) == 1, bench.files()


def test_warming_is_a_no_op_when_the_file_is_already_there():
    with _Bench() as bench:
        bench.build()
        assert len(bench.files()) == 1
        patches = _warm_patches(bench)
        for p in patches:
            p.start()
        try:
            with mock.patch.object(AV, "raw_lsb_spectrum_cache",
                                   wraps=AV.raw_lsb_spectrum_cache) as spy:
                got = B.warm_shared_raw_cache(UID, centers=CENTERS)
                assert spy.call_count == 0, "an already-warm participant must build nothing"
            assert B._load_recordings.call_count == 0, \
                "an already-warm participant must not read any stored recording"
        finally:
            for p in patches:
                p.stop()
        assert got["status"] == "already_warm", got


def test_warming_never_raises_when_the_work_fails():
    """An ingest must not fail because a cache could not be warmed."""
    with _Bench() as bench:
        with mock.patch.object(B, "_load_recordings",
                               side_effect=RuntimeError("the stored file could not be read")):
            got = B.warm_shared_raw_cache(UID, centers=CENTERS)
        assert got["status"] == "failed", got
        assert "could not be read" in got["error"]
        assert bench.files() == []


def test_warming_reports_when_there_is_nothing_to_warm():
    with _Bench() as bench:
        with mock.patch.object(B, "_raw_lsb_recording_identity", return_value=None):
            assert B.warm_shared_raw_cache(UID, centers=CENTERS)["status"] == "no_recordings"
        patches = _warm_patches(bench)
        for p in patches:
            p.start()
        try:
            with mock.patch.object(B, "_derive_chan_order", return_value=[]):
                got = B.warm_shared_raw_cache(UID, centers=CENTERS)
        finally:
            for p in patches:
                p.stop()
        assert got["status"] == "nothing_to_build", got


def test_the_ingest_warm_also_warms_the_tiles():
    """`warm_psd_cache` is what ingestion calls, so the tiles have to be warmed from there."""
    with _Bench():
        with mock.patch.object(B, "_cached_psd_matrix", return_value={"logX": []}) as psd, \
             mock.patch.object(B, "warm_shared_raw_cache",
                               return_value={"status": "already_warm"}) as tiles:
            got = B.warm_psd_cache(UID)
        assert psd.call_count == 1
        assert tiles.call_count == 1 and tiles.call_args[0][0] == UID
        assert got == {"logX": []}, "the spectra answer must be handed back unchanged"


def test_the_tiles_are_warmed_even_when_the_spectra_warm_fails():
    """The two products are independent; one failing must not skip the other."""
    with _Bench():
        with mock.patch.object(B, "_cached_psd_matrix", side_effect=RuntimeError("no spectra")), \
             mock.patch.object(B, "warm_shared_raw_cache",
                               return_value={"status": "built", "seconds": 1.0}) as tiles:
            got = B.warm_psd_cache(UID)
        assert tiles.call_count == 1
        assert got is None


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# the storage shape itself
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_stored_shape_round_trips_every_field():
    with _Bench() as bench:
        built = bench.build(use_shared_cache=False)
        packed = B._raw_lsb_pack(built)
        entry = packed["ZERO_THREE_LEFT"]
        assert isinstance(entry["td"]["lsb"], np.ndarray) and entry["td"]["lsb"].dtype == float
        assert isinstance(entry["td"]["ok"], np.ndarray) and entry["td"]["ok"].dtype == bool
        assert set(entry["td"]["source"]) == {"labels", "codes"}
        assert AV._LSB_MAT_MEMO_KEY not in entry["td"]
        compared, different = _families_equal(built, B._raw_lsb_unpack(packed))
        assert compared > 100 and different == 0, (compared, different)


def test_the_matchers_own_matrix_is_not_stored_twice():
    """After the matcher runs, the family dict also holds the matrix it built. Storing that would
    put the same numbers in the file twice; on RCS08 it doubles the entry from 245 MB to 511 MB."""
    with _Bench() as bench:
        built = bench.build(use_shared_cache=False)
        AV.live_lsb_spectrum_match(np.asarray([1_700_000_006.0]), built["ZERO_THREE_LEFT"],
                                   tol_s=60.0, td_quantity_s=30.0)
        assert AV._LSB_MAT_MEMO_KEY in built["ZERO_THREE_LEFT"]["td"], \
            "the matcher is expected to park its matrix here"
        packed = B._raw_lsb_pack(built)
        assert AV._LSB_MAT_MEMO_KEY not in packed["ZERO_THREE_LEFT"]["td"]


def test_the_matrix_reader_accepts_an_array_and_a_list_alike():
    rows = [[1.0, None, 3.0], [4.0, 5.0, None]]
    from_list = AV._lsb_rows_to_mat(rows, 3)
    from_array = AV._lsb_rows_to_mat(from_list, 3)
    assert np.array_equal(from_list, from_array, equal_nan=True)
    assert AV._lsb_rows_to_mat(np.empty((0, 3)), 3).shape == (0, 3)
    assert AV._lsb_family_mat({"lsb": from_list}, 3).shape == (2, 3)
    assert AV._lsb_family_mat({}, 3).shape == (0, 3)
    narrow = AV._lsb_rows_to_mat(np.asarray([[1.0, 2.0]]), 3)
    assert narrow.shape == (1, 3) and np.isnan(narrow[0, 2])


def test_the_reported_numbers_describe_what_the_files_did():
    with _Bench() as bench:
        bench.build()
        bench.build(fresh_process=True)
        stats = B.shared_cache_stats()
        assert stats["entries"] == 1 and stats["bytes"] > 0
        assert stats["events"]["writes"] == 1 and stats["events"]["hits"] == 1
        assert B.clear_shared_cache() == 1
        assert B.shared_cache_stats()["entries"] == 0


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(list(globals().items())):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
            except Exception as exc:                       # noqa: BLE001 - reported below
                failed += 1
                print("FAIL", name, repr(exc)[:300])
    print(f"PASS={passed} FAIL={failed}")
