"""Tests for the two shortcuts in front of `_assemble_psd_rows_cached`'s per-recording loop: the
rows-set stamp (skip the loop entirely when the recording set has not moved) and the per-recording
manifest (skip asking the file system about a recording the manifest already calls good).

WHAT THIS GUARDS AGAINST. A first draft of the manifest treated "not listed in the manifest" as
"the file is missing", which would have redecoded every recording in this participant's whole
history the first time this code ran, ignoring however many per-recording files were already on
disk from before the manifest existed. `test_a_cold_manifest_still_finds_files_already_on_disk`
is the regression test for that: it seeds one recording's file directly (as if from an earlier
run, with no manifest entry for it) and checks the file is used, not redecoded.

No Django and no database: stubbed the way test_shared_raw_lsb_cache.py stubs them.

Run inside the container:
    python3 _agent_bridge/run_tests.py
"""
import os
import pathlib
import shutil
import sys
import tempfile
import unittest.mock as mock

import numpy as np

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _import_service():
    for mod in ("Server", "Server.models", "modules.Database"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    for mod in ("modules.Biomarkers.pipeline", "modules.Biomarkers.adapter"):
        if mod not in sys.modules:
            sys.modules[mod] = mock.MagicMock()
    import modules.Biomarkers.bravo_service as bs
    return bs


B = _import_service()
UID = "test-participant"


class _Rec:
    def __init__(self, pointer, hashed):
        self.pointer = pointer
        self.hashed = hashed


class _Bench:
    """Two temporary directories (per-recording files, and the manifest/rows-cache index),
    stand-in entries feeding `_assemble_psd_rows_cached`, and a decode counter."""

    def __init__(self, n=3):
        self.rows_dir = None
        self.index_dir = None
        self.n = n
        self.decodes = 0

    def __enter__(self):
        self.rows_dir = tempfile.mkdtemp(prefix="test_psd_rows_")
        self.index_dir = tempfile.mkdtemp(prefix="test_psd_index_")
        self._saved_rows_dir = B._psd_rows_cache_dir
        self._saved_index_dir = B._psd_rows_index_dir
        self._saved_entries = B._recording_rows_for_psd
        B._psd_rows_cache_dir = lambda: self.rows_dir
        B._psd_rows_index_dir = lambda: self.index_dir

        entries = [{"rec": _Rec(f"ptr{i}", f"hash{i}"), "uid": f"uid{i}",
                    "hash": f"hash{i}", "source": "Montage/survey"} for i in range(self.n)]
        B._recording_rows_for_psd = lambda uid: entries
        self.entries = entries

        def _fake_load(pointer, hashed):
            self.decodes += 1
            return {"ChannelNames": ["ZERO_THREE_LEFT"], "Data": np.zeros((250, 1)),
                    "SamplingRate": 250.0, "StartTime": 1_700_000_000.0, "Duration": 1.0,
                    "RecordingType": "Streaming survey"}
        self._db_patch = mock.patch.object(B.Database, "loadSourceFile",
                                            side_effect=_fake_load, create=True)
        self._db_patch.start()

        def _fake_event_rows(participant_uid, sensing_index=None):
            return []
        self._ev_patch = mock.patch.object(B, "_event_psd_rows", side_effect=_fake_event_rows)
        self._ev_patch.start()
        return self

    def __exit__(self, *exc):
        self._db_patch.stop()
        self._ev_patch.stop()
        B._psd_rows_cache_dir = self._saved_rows_dir
        B._psd_rows_index_dir = self._saved_index_dir
        B._recording_rows_for_psd = self._saved_entries
        shutil.rmtree(self.rows_dir, ignore_errors=True)
        shutil.rmtree(self.index_dir, ignore_errors=True)
        return False

    def key_for(self, i):
        return B._recording_psd_cache_path(self.entries[i]["uid"], self.entries[i]["hash"], "")


def test_a_cold_manifest_still_finds_files_already_on_disk():
    """The regression test. A per-recording file exists but the manifest has never heard of it
    (as it never will, the very first time this code runs on an already-warm directory): the file
    must still be found and used, not redecoded."""
    with _Bench(n=3) as bench:
        path = bench.key_for(1)
        B._save_recording_psd_rows(path, [{"channel": "ZERO_THREE_LEFT", "source": "Montage/survey",
                                            "t": 1.0, "freq": np.array([1.0, 2.0]),
                                            "power": np.array([3.0, 4.0]), "dur": 1.0}])
        assert os.path.exists(path)
        assert not os.path.exists(B._rows_manifest_path(UID))   # no manifest at all yet

        rows, n_cached, n_computed = B._assemble_psd_rows_cached(UID)
        # Entry 1's file was found without a manifest entry; only entries 0 and 2 were decoded.
        assert n_cached == 1, f"expected the pre-existing file to be found, got n_cached={n_cached}"
        assert n_computed == 2, f"expected the two recordings with no file decoded, got {n_computed}"
        assert bench.decodes == 2
        assert len(rows) == 3

        manifest = B._load_rows_manifest(UID)
        assert os.path.basename(path) in manifest, "finding the file on disk must repair the manifest"
    print("OK a cold manifest still finds a per-recording file already on disk, and repairs itself")


def test_a_manifest_hit_skips_the_existence_check_and_still_matches():
    """A recording the manifest already calls good is opened directly; the rows it contributes are
    identical to a full recompute of the same recording."""
    with _Bench(n=2) as bench:
        rows1, nc1, ncomp1 = B._assemble_psd_rows_cached(UID)
        assert ncomp1 == 2 and nc1 == 0
        assert bench.decodes == 2

        rows2, nc2, ncomp2 = B._assemble_psd_rows_cached(UID)
        # Second call: everything is either in the rows-set cache or the per-recording manifest,
        # so nothing is decoded again.
        assert ncomp2 == 0, f"expected no further decodes on the second call, got {ncomp2}"
        assert bench.decodes == 2, "no recording should be decoded twice"
        assert len(rows1) == len(rows2)
    print("OK a manifest/rows-cache hit decodes nothing further and the rows still match")


def test_force_recompute_ignores_and_then_repairs_both_caches():
    """force_recompute must still decode everything even when the rows-set cache and the manifest
    both already have a complete, valid answer -- and must leave both repaired afterward."""
    with _Bench(n=2) as bench:
        B._assemble_psd_rows_cached(UID)
        assert bench.decodes == 2
        rows, nc, ncomp = B._assemble_psd_rows_cached(UID, force_recompute=True)
        assert ncomp == 2, "force_recompute must ignore both caches and decode every recording"
        assert bench.decodes == 4
        # And the caches are repaired: the very next ordinary call decodes nothing.
        _, _, ncomp2 = B._assemble_psd_rows_cached(UID)
        assert ncomp2 == 0
        assert bench.decodes == 4
    print("OK force_recompute ignores both caches and repairs them for the next ordinary call")


if __name__ == "__main__":
    test_a_cold_manifest_still_finds_files_already_on_disk()
    test_a_manifest_hit_skips_the_existence_check_and_still_matches()
    test_force_recompute_ignores_and_then_repairs_both_caches()
