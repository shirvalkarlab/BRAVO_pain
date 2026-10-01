"""Unpacked recordings kept in the web worker between requests (2026-10-02, the Jetstream2 BRAVO:
unpacking RCS08's 1,738 recordings cost 12.3 s of every Closed-Loop request; a deep copy of what
was kept costs 1.5 s). Off unless a memory budget is set (BRAVO_RECORDING_CACHE_MB): the decoded
recordings are 4.0 GB per worker, which only the Jetstream2 BRAVO can spare.

Values, not shapes: the second load returns the same content without reading the file again; a
caller changing what it got changes nothing anyone else gets; a changed file (new content hash)
is read again; the budget evicts the oldest; with no budget every load reads the file.
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


def test_a_kept_recording_is_not_read_again_and_its_content_is_unchanged():
    def run(calls):
        a = B._load_source_file_kept("/x/r1", "h1")
        b = B._load_source_file_kept("/x/r1", "h1")
        assert calls == [("/x/r1", "h1")]
        assert np.array_equal(a[0]["Data"], b[0]["Data"]) and a[0]["Pointer"] == b[0]["Pointer"]
    _with(100, run)


def test_a_caller_changing_its_copy_changes_nothing_anyone_else_gets():
    def run(calls):
        a = B._load_source_file_kept("/x/r1", "h1")
        a[0]["Data"][:] = -1.0
        a[0]["Extra"] = "changed"
        a.append({"junk": 1})
        b = B._load_source_file_kept("/x/r1", "h1")
        assert len(b) == 1 and "Extra" not in b[0]
        assert np.array_equal(b[0]["Data"], np.arange(10, dtype=float))
    _with(100, run)


def test_a_file_with_new_content_is_read_again():
    def run(calls):
        B._load_source_file_kept("/x/r1", "h1")
        B._load_source_file_kept("/x/r1", "h2")
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
