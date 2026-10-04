"""Decoded recordings shared by every web worker through one mapped file (the PI, 2026-10-04,
decision 414).

Until now each of the 16 workers decoded RCS08's recordings into its own memory and kept up to
3,000 MB of them, handing every caller a deep copy (1.5 s a request). Now the first worker to need
a set of recordings decodes it and saves it in the store's mapped format; every worker then reads
the arrays from the same disk-cache pages, and each read is its own copy-on-write view.

Values, not shapes:

  * the second load reads nothing from the device files and returns the same content;
  * a caller changing what it got changes nothing a later load returns;
  * the saved copy is filed under exactly the recordings it holds (their ids and content hashes):
    a changed file is decoded again;
  * a load in which any recording failed to decode is not saved;
  * the labels read from the database rows (centre frequency, schedules, recording type) are put on
    after every read, so a change to a row reaches the next load without decoding again;
  * with the switch off, every load decodes as before and nothing is saved.
"""
import shutil
import tempfile

import numpy as np

from modules.Biomarkers import bravo_service as B
from modules import Database
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


def _with(fn, *, mapped=True, fail=()):
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


def test_the_second_load_reads_no_file_and_returns_the_same_content():
    def run(calls):
        a = B._decoded_payloads("P", RECS)
        n = len(calls)
        b = B._decoded_payloads("P", RECS)
        assert n == 2 and len(calls) == 2, calls
        assert _flat(a) == _flat(b)
    _with(run)


def test_a_caller_changing_its_copy_changes_nothing_a_later_load_returns():
    def run(calls):
        B._decoded_payloads("P", RECS)
        a = B._decoded_payloads("P", RECS)
        a["r1"][0]["Data"][:] = -1.0
        a["r1"][0]["Extra"] = "changed"
        b = B._decoded_payloads("P", RECS)
        assert "Extra" not in b["r1"][0]
        assert np.array_equal(b["r1"][0]["Data"], np.arange(50, dtype=float) + len("/x/r1"))
    _with(run)


def test_a_file_with_new_content_is_decoded_again():
    def run(calls):
        B._decoded_payloads("P", RECS)
        B._decoded_payloads("P", [RECS[0], _Rec("r2", "h2-new")])
        assert calls[-2:] == [("/x/r1", "h1"), ("/x/r2", "h2-new")] or \
            sorted(calls[-2:]) == [("/x/r1", "h1"), ("/x/r2", "h2-new")]
    _with(run)


def test_a_load_with_a_failed_recording_is_not_saved():
    def run(calls):
        a = B._decoded_payloads("P", RECS)
        assert a["r2"] is None
        B._decoded_payloads("P", RECS)
        assert len(calls) == 4, "nothing was saved, so both loads decoded"
    _with(run, fail=("/x/r2",))


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
    _with(run)


def test_with_the_switch_off_every_load_decodes_and_nothing_is_saved():
    def run(calls):
        B._decoded_payloads("P", RECS)
        B._decoded_payloads("P", RECS)
        assert len(calls) == 4
    _with(run, mapped=False)
