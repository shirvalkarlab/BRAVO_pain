"""Unpacked recordings kept in the web worker between requests (2026-10-02, the Jetstream2 BRAVO:
unpacking RCS08's 1,738 recordings cost 12.3 s of every Closed-Loop request; a deep copy of what
was kept costs 1.5 s). Off unless a memory budget is set (BRAVO_RECORDING_CACHE_MB): the decoded
recordings are 4.0 GB per worker, which only the Jetstream2 BRAVO can spare.

Values, not shapes: the second load returns the same content without reading the file again; a
caller changing what it got changes nothing anyone else gets; a changed file (new content hash)
is read again; the budget evicts the oldest; with no budget every load reads the file.

Merged here 2026-10-05: test_mapped_recordings.py.
"""
import numpy as np
from modules.Biomarkers import bravo_service as B
from modules import Database


def _fake_reader(calls):
    def read(pointer, hashed, bytes=False):
        calls.append((pointer, hashed))
        n = 1000 if pointer.endswith("big") else 10
        return [{"Data": np.arange(n, dtype=float), "ChannelNames": ["A"], "Pointer": pointer}]
    return read


def _with(budget_mb, fn):
    old_reader, old_env = Database.loadSourceFile, B.os.environ.get(B.RECORDING_CACHE_ENV)
    calls = []
    Database.loadSourceFile = _fake_reader(calls)
    if budget_mb is None:
        B.os.environ.pop(B.RECORDING_CACHE_ENV, None)
    else:
        B.os.environ[B.RECORDING_CACHE_ENV] = str(budget_mb)
    B._RECORDING_CACHE.clear()
    try:
        fn(calls)
    finally:
        Database.loadSourceFile = old_reader
        if old_env is None:
            B.os.environ.pop(B.RECORDING_CACHE_ENV, None)
        else:
            B.os.environ[B.RECORDING_CACHE_ENV] = old_env
        B._RECORDING_CACHE.clear()


def test_a_kept_recording_is_served_as_its_own_copy_and_read_again_only_when_its_content_changes():
    def run(calls):
        a = B._load_source_file_kept("/x/r1", "h1")
        b = B._load_source_file_kept("/x/r1", "h1")
        assert calls == [("/x/r1", "h1")], "a kept recording is not read again"
        assert np.array_equal(a[0]["Data"], b[0]["Data"]) and a[0]["Pointer"] == b[0]["Pointer"]
        a[0]["Data"][:] = -1.0                              # a caller changing its copy ...
        a[0]["Extra"] = "changed"
        a.append({"junk": 1})
        c = B._load_source_file_kept("/x/r1", "h1")         # ... changes nothing anyone else gets
        assert len(c) == 1 and "Extra" not in c[0]
        assert np.array_equal(c[0]["Data"], np.arange(10, dtype=float))
        B._load_source_file_kept("/x/r1", "h2")             # a file with new content is read again
        assert calls == [("/x/r1", "h1"), ("/x/r1", "h2")]
    _with(100, run)


def test_the_budget_evicts_the_oldest_recording():
    def run(calls):
        B._load_source_file_kept("/x/a_big", "h")          # 8,000 bytes
        B._load_source_file_kept("/x/b_big", "h")          # 8,000 bytes: over 0.01 MB, evicts a
        B._load_source_file_kept("/x/b_big", "h")          # kept
        B._load_source_file_kept("/x/a_big", "h")          # read again
        assert calls == [("/x/a_big", "h"), ("/x/b_big", "h"), ("/x/a_big", "h")]
    _with(0.01, run)


def test_with_no_budget_every_load_reads_the_file():
    def run(calls):
        B._load_source_file_kept("/x/r1", "h1")
        B._load_source_file_kept("/x/r1", "h1")
        assert calls == [("/x/r1", "h1"), ("/x/r1", "h1")]
    _with(None, run)


# --------------------------------------------------------------------------------------------------
# merged from test_mapped_recordings.py
# Decoded recordings shared by every web worker through one mapped file (the PI, 2026-10-04,
# decision 414).
#
# Until now each of the 16 workers decoded RCS08's recordings into its own memory and kept up to
# 3,000 MB of them, handing every caller a deep copy (1.5 s a request). Now the first worker to need
# a set of recordings decodes it and saves it in the store's mapped format; every worker then reads
# the arrays from the same disk-cache pages, and each read is its own copy-on-write view.
#
# Values, not shapes:
#
#   * the second load reads nothing from the device files and returns the same content;
#   * a caller changing what it got changes nothing a later load returns;
#   * the saved copy is filed under exactly the recordings it holds (their ids and content hashes):
#     a changed file is decoded again;
#   * a load in which any recording failed to decode is not saved;
#   * the labels read from the database rows (centre frequency, schedules, recording type) are put on
#     after every read, so a change to a row reaches the next load without decoding again;
#   * with the switch off, every load decodes as before and nothing is saved.


import shutil
import tempfile
from modules.CacheStore import locks as L


class _Rec:
    def __init__(self, uid, hashed, rtype="MedtronicBrainSenseTimeDomain", metadata=None):
        self.uid, self.pointer, self.hashed = uid, f"/x/{uid}", hashed
        self.type, self.metadata = rtype, (metadata or {})


def _reader(calls, fail=()):
    def read(pointer, hashed, bytes=False):
        calls.append((pointer, hashed))
        if pointer in fail:
            raise IOError("cannot decode")
        n = 50 if pointer.endswith("1") else 20
        return [{"Data": np.arange(n, dtype=float) + len(pointer), "ChannelNames": ["A"],
                 "Pointer": pointer}]
    return read


def _with_mapped(fn, *, mapped=True, fail=()):
    old = (Database.loadSourceFile, B._SHARED_CACHE_DIR_OVERRIDE, B.MAPPED_RECORDINGS, L.ENABLED)
    old_env = B.os.environ.pop(B.RECORDING_CACHE_ENV, None)      # no worker-private copies here
    B._RECORDING_CACHE.clear()
    d = tempfile.mkdtemp(prefix="bravo_mapped_rec_")
    calls = []
    Database.loadSourceFile = _reader(calls, fail)
    B._SHARED_CACHE_DIR_OVERRIDE, B.MAPPED_RECORDINGS, L.ENABLED = d, mapped, False
    try:
        fn(calls)
    finally:
        (Database.loadSourceFile, B._SHARED_CACHE_DIR_OVERRIDE, B.MAPPED_RECORDINGS,
         L.ENABLED) = old
        if old_env is not None:
            B.os.environ[B.RECORDING_CACHE_ENV] = old_env
        B._RECORDING_CACHE.clear()
        shutil.rmtree(d, ignore_errors=True)


RECS = [_Rec("r1", "h1"), _Rec("r2", "h2", "MedtronicChronic", {"CenterFrequencyHz": 18.5})]


def _flat(decoded):
    return {k: [(np.asarray(d["Data"]).tolist(), d.get("Pointer")) for d in v]
            for k, v in decoded.items()}


def test_a_mapped_set_is_read_with_no_decoding_as_its_own_copy_and_decoded_again_when_a_file_changes():
    def run(calls):
        a = B._decoded_payloads("P", RECS)
        n = len(calls)
        b = B._decoded_payloads("P", RECS)
        assert n == 2 and len(calls) == 2, ("the second load reads no file", calls)
        assert _flat(a) == _flat(b)
        b["r1"][0]["Data"][:] = -1.0                        # a caller changing its copy ...
        b["r1"][0]["Extra"] = "changed"
        c = B._decoded_payloads("P", RECS)                  # ... changes nothing a later load returns
        assert "Extra" not in c["r1"][0]
        assert np.array_equal(c["r1"][0]["Data"], np.arange(50, dtype=float) + len("/x/r1"))
        B._decoded_payloads("P", [RECS[0], _Rec("r2", "h2-new")])   # a file with new content
        assert sorted(calls[-2:]) == [("/x/r1", "h1"), ("/x/r2", "h2-new")], calls
    _with_mapped(run)


def test_a_load_with_a_failed_recording_is_not_saved():
    def run(calls):
        a = B._decoded_payloads("P", RECS)
        assert a["r2"] is None
        B._decoded_payloads("P", RECS)
        assert len(calls) == 4, "nothing was saved, so both loads decoded"
    _with_mapped(run, fail=("/x/r2",))


def test_the_row_labels_are_put_on_after_every_read():
    def run(calls):
        B._decoded_payloads("P", RECS)
        recs = [RECS[0], _Rec("r2", "h2", "MedtronicChronic", {"CenterFrequencyHz": 22.5})]
        got = B._decoded_with_row_labels("P", recs)
        by_ptr = {d["Pointer"]: d for d in got}
        assert by_ptr["/x/r2"]["CenterFrequencyHz"] == 22.5
        assert by_ptr["/x/r2"]["RecordingType"] == "MedtronicChronic"
        assert by_ptr["/x/r1"]["RecordingType"] == "MedtronicBrainSenseTimeDomain"
        assert len(calls) == 2, "the label change needed no decoding"
    _with_mapped(run)


def test_with_the_switch_off_every_load_decodes_and_nothing_is_saved():
    def run(calls):
        B._decoded_payloads("P", RECS)
        B._decoded_payloads("P", RECS)
        assert len(calls) == 4
    _with_mapped(run, mapped=False)
