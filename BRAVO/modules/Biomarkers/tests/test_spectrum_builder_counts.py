"""Review B6 (2026-09-12): the spectrum builder's two silent failures are logged AND counted.

`_welch_rows_into` had two bare `except` blocks. The first wrapped the rating-centred spectrum:
when it raised, the recording fell through to a spectrum stamped at the recording START (a
different quantity), with no log line and no counter. The second wrapped the first-window
spectrum: when it raised, the recording was simply absent from the pool. Both outcomes were then
persisted by the per-recording cache. Each is now counted, the counts ride with the cached rows to
the assembled matrix payload and to the page's `cache` block, and a file written before the
counters existed reads as "not recorded" rather than as zero.

Tests pin VALUES: the fell-back recording's row time equals its start time AND the counter reads
1; a first-window failure is counted as skipped; the counts survive both cache layers; a legacy
file is reported as unknown. Plain asserts, stubbed like `test_psd_rows_manifest.py`.
"""
import logging
import os
import pathlib
import sys
import unittest.mock as mock

import numpy as np

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from .test_psd_rows_manifest import B, UID, _Bench   # noqa: E402  (same stubs, same runner)
from ..routines import streaming_psd as _sp           # noqa: E402

FS = 250.0
T0 = 1_700_000_000.0


def _td_rec(start, seconds=90, seed=0):
    rng = np.random.default_rng(seed)
    n = int(seconds * FS)
    return {"ChannelNames": ["ZERO_THREE_LEFT"], "Data": rng.standard_normal((n, 1)),
            "SamplingRate": FS, "StartTime": start, "Duration": n / FS,
            "Missing": np.zeros((n, 1)), "RecordingType": "MedtronicBrainSenseTimeDomain"}


def test_a_failed_centred_spectrum_falls_back_to_the_start_and_is_counted_once():
    rec_ok, rec_bad = _td_rec(T0, seed=1), _td_rec(T0 + 10_000.0, seed=2)
    pro = np.array([T0 + 40.0, T0 + 10_000.0 + 40.0])     # one rating inside each recording
    real = _sp.welch_rating_centered

    def _flaky(sig, names, fs, keep, centers_s, missing=None):
        # raise for the second recording only (identified by its own random data)
        if np.array_equal(sig, rec_bad["Data"].T):
            raise RuntimeError("synthetic centred failure")
        return real(sig, names, fs, keep, centers_s, missing=missing)

    rows, counts = [], B._new_welch_counts()
    with mock.patch.object(_sp, "welch_rating_centered", side_effect=_flaky), \
            mock.patch.object(B._log, "warning") as warn:
        got = B._welch_rows_into(rows, [rec_ok, rec_bad], "TD streaming", _sp, pro_times=pro,
                                 counts=counts)
    assert got == (1, 0), got
    assert counts == {"n_centered_fell_back": 1, "n_skipped": 0}, counts
    times = sorted(r["t"] for r in rows)
    # the good recording's row is stamped at its RATING; the failed one's at its START
    assert times == [T0 + 40.0, T0 + 10_000.0], times
    # ... and it was logged, with the traceback
    msgs = [c.args[0] for c in warn.call_args_list]
    assert any("rating-centred spectrum failed" in m for m in msgs), msgs
    assert all(c.kwargs.get("exc_info") for c in warn.call_args_list), "log without exc_info"


def test_a_failed_first_window_spectrum_is_counted_as_skipped():
    rec = _td_rec(T0, seed=3)
    rows, counts = [], B._new_welch_counts()
    with mock.patch.object(_sp, "welch_psd_for_instance", side_effect=ValueError("synthetic")), \
            mock.patch.object(B._log, "warning") as warn:
        got = B._welch_rows_into(rows, [rec], "Montage/survey", _sp, counts=counts)
    assert got == (0, 1) and rows == [], (got, rows)
    assert counts == {"n_centered_fell_back": 0, "n_skipped": 1}
    assert any("first-window spectrum failed" in c.args[0] for c in warn.call_args_list)


def test_the_counts_survive_the_per_recording_file_and_the_rows_set_cache():
    """A recording Welch'd once with a failure reports the same counts on every later assembly,
    whether served from its own file or from the rows-set cache; a file from before the counters
    existed is reported as unknown, not as zero."""
    with _Bench(n=3) as bench:
        # make entry 0 a TD-streaming recording whose centred spectrum fails
        bench.entries[0]["source"] = "TD streaming"
        real_load = B.Database.loadSourceFile.side_effect
        rec_bad = _td_rec(T0, seed=4)

        def _load(pointer, hashed):
            if pointer == "ptr0":
                bench.decodes += 1
                return rec_bad
            return real_load(pointer, hashed)
        B.Database.loadSourceFile.side_effect = _load
        pro = np.array([T0 + 40.0])
        # a legacy file (no counters stored) for entry 2, as a file written before 2026-09-12
        legacy = B._recording_psd_cache_path(bench.entries[2]["uid"], bench.entries[2]["hash"], "")
        B._save_recording_psd_rows(legacy, [{"channel": "ZERO_THREE_LEFT", "source": "Montage/survey",
                                             "t": 1.0, "freq": np.array([1.0, 2.0]),
                                             "power": np.array([3.0, 4.0]), "dur": 1.0}])
        with mock.patch.object(_sp, "welch_rating_centered", side_effect=RuntimeError("synthetic")):
            rows, nc, ncomp, q1 = B._assemble_psd_rows_cached(UID, pro_times=pro)
        assert ncomp == 2 and nc == 1, (ncomp, nc)
        # (the bench's rows carry no coverage, so the one TD recording is keyed on the whole set)
        assert q1 == {"n_centered_fell_back": 1, "n_skipped": 0, "n_recordings_without_counts": 1,
                      "n_recordings_keyed_on_whole_set": 1}, q1
        # entry 0's own file carries its counts
        path0 = B._recording_psd_cache_path("uid0", "hash0", B._pro_set_signature(pro))
        _rows0, c0 = B._load_recording_psd_rows(path0, with_counts=True)
        assert c0 == {"n_centered_fell_back": 1, "n_skipped": 0}, c0
        _rows2, c2 = B._load_recording_psd_rows(legacy, with_counts=True)
        assert c2 is None, "a legacy file has no counters; it must read as unknown"
        # second assembly: rows-set cache hit, same quality
        _rows, nc2, ncomp2, q2 = B._assemble_psd_rows_cached(UID, pro_times=pro)
        assert ncomp2 == 0 and q2 == q1, (ncomp2, q2)
        # third: rows-set cache removed, every recording served from its own file, same quality
        pro_sig = B._pro_set_signature(pro)
        os.remove(B._rows_cache_path(UID, B._rows_set_signature(
            bench.entries, lambda e: B._recording_psd_cache_path(
                e["uid"], e["hash"], pro_sig if e["source"] == "TD streaming" else "")), pro_sig))
        _rows, nc3, ncomp3, q3 = B._assemble_psd_rows_cached(UID, pro_times=pro)
        assert ncomp3 == 0 and nc3 == 3 and q3 == q1, (ncomp3, nc3, q3)


def test_the_matrix_payload_carries_the_counts_and_the_page_reads_them_back():
    mat = {"X": np.zeros((2, 3)), "t": np.array([1.0, 2.0]), "channel": ["a", "b"],
           "source": ["s", "s"], "f_set": np.array([1.0, 2.0, 3.0]), "dur": [1.0, 1.0]}
    q = {"n_centered_fell_back": 2, "n_skipped": 1, "n_recordings_without_counts": 5,
         "n_recordings_keyed_on_whole_set": 0}
    payload = B._psd_matrix_payload(mat, quality=q)
    assert B._psd_matrix_quality(payload) == q
    assert B._psd_matrix_quality(B._psd_matrix_payload(mat)) is None, "a payload without counts"
    # the counts are one-element integer arrays, which is what the store's array format holds
    assert payload["n_centered_fell_back"].shape == (1,) and int(payload["n_skipped"][0]) == 1


if __name__ == "__main__":
    test_a_failed_centred_spectrum_falls_back_to_the_start_and_is_counted_once()
    test_a_failed_first_window_spectrum_is_counted_as_skipped()
    test_the_counts_survive_the_per_recording_file_and_the_rows_set_cache()
    test_the_matrix_payload_carries_the_counts_and_the_page_reads_them_back()
    print("All spectrum-builder-count tests passed.")
