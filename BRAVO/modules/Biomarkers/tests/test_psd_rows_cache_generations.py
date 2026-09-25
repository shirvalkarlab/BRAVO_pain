"""P-07 (handoff pending-items list, 2026-09-25): the per-recording PSD cache directory
(`_psd_rows_cache_dir`) is never swept -- only the much smaller rows-SET cache is (`_sweep_old_rows_
cache`) -- so every time `_CHANNEL_CANON_VERSION`, `_TD_MISSING_VERSION` or `_TD_CENTERED_VERSION`
is bumped, the files the OLD value named are left on disk forever; nothing ever reads or deletes
them again.

`psd_rows_cache_generation_report` is a READ-ONLY dry run: it counts what is already there, grouped
by naming generation, and how many bytes each generation holds. This file proves it counts correctly
and deletes nothing; it does not delete anything itself, and neither does the function under test.

No Django and no database: stubbed the way test_shared_raw_lsb_cache.py stubs Server.

Run inside the container:
    python3 _agent_bridge/run_tests.py
"""
import os
import pathlib
import shutil
import sys
import tempfile
import unittest.mock as mock

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


class _TempCacheDir:
    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="test_psd_rows_gen_")
        self._saved = B._psd_rows_cache_dir
        B._psd_rows_cache_dir = lambda: self.dir
        return self

    def __exit__(self, *exc):
        B._psd_rows_cache_dir = self._saved
        shutil.rmtree(self.dir, ignore_errors=True)
        return False

    def write(self, name, n_bytes):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as fh:
            fh.write(b"\0" * n_bytes)
        return path


def test_empty_directory_reports_all_zeros():
    with _TempCacheDir():
        out = B.psd_rows_cache_generation_report()
    assert out == {"total_files": 0, "total_bytes": 0, "current_generation": None,
                   "other_generations": [], "unparsed": {"files": 0, "bytes": 0}}, out


def test_current_generation_files_are_counted_together_pro_sig_and_all():
    """Two rating-centred files under the SAME current naming rule but DIFFERENT PRO-set hashes
    (as two different report sets would produce) land in ONE current-generation bucket, not two."""
    cur = f"{B._CHANNEL_CANON_VERSION}_{B._TD_MISSING_VERSION}"
    with _TempCacheDir() as t:
        t.write(f"rec1_hash1_w30p0_{cur}.npz", 100)                                    # non-centred
        t.write(f"rec2_hash2_w30p0_{cur}_pabc123abc123_{B._TD_CENTERED_VERSION}.npz", 200)
        t.write(f"rec3_hash3_w30p0_{cur}_pdef456def456_{B._TD_CENTERED_VERSION}.npz", 300)
        out = B.psd_rows_cache_generation_report()
    assert out["total_files"] == 3
    assert out["total_bytes"] == 600
    assert out["current_generation"] == {"suffix": cur, "files": 3, "bytes": 600}, out
    assert out["other_generations"] == []
    assert out["unparsed"] == {"files": 0, "bytes": 0}


def test_an_older_generation_is_counted_apart_from_current_and_by_size():
    """A file named under an earlier channel-canon rule (as `_CHANNEL_CANON_VERSION` was before its
    last bump) is a different generation: counted separately, never mistaken for current, and the
    generations are reported largest-first."""
    cur = f"{B._CHANNEL_CANON_VERSION}_{B._TD_MISSING_VERSION}"
    old_channel_canon = "v1_no_ring_awareness"     # stands in for whatever the value was before v2
    with _TempCacheDir() as t:
        t.write(f"rec1_hash1_w30p0_{cur}.npz", 10)
        t.write(f"rec2_hash2_w30p0_{old_channel_canon}_{B._TD_MISSING_VERSION}.npz", 1000)
        t.write(f"rec3_hash3_w30p0_{old_channel_canon}_{B._TD_MISSING_VERSION}.npz", 2000)
        out = B.psd_rows_cache_generation_report()
    assert out["total_files"] == 3
    assert out["total_bytes"] == 3010
    assert out["current_generation"] == {"suffix": cur, "files": 1, "bytes": 10}, out
    assert out["other_generations"] == [
        {"suffix": f"{old_channel_canon}_{B._TD_MISSING_VERSION}", "files": 2, "bytes": 3000},
    ], out["other_generations"]


def test_two_older_generations_are_kept_apart_and_sorted_biggest_first():
    cur = f"{B._CHANNEL_CANON_VERSION}_{B._TD_MISSING_VERSION}"
    with _TempCacheDir() as t:
        t.write(f"rec1_hash1_w30p0_generationA.npz", 50)
        t.write(f"rec2_hash2_w30p0_generationB.npz", 500)
        t.write(f"rec3_hash3_w30p0_generationB.npz", 700)
        out = B.psd_rows_cache_generation_report()
    assert out["current_generation"] is None, out    # neither generation matches today's rule
    assert [g["suffix"] for g in out["other_generations"]] == ["generationB", "generationA"], out
    assert out["other_generations"][0] == {"suffix": "generationB", "files": 2, "bytes": 1200}


def test_a_name_with_no_recognizable_suffix_is_counted_as_unparsed_not_silently_dropped():
    with _TempCacheDir() as t:
        t.write("some_ancient_file_with_no_version_tag.npz", 42)
        out = B.psd_rows_cache_generation_report()
    assert out["total_files"] == 1 and out["total_bytes"] == 42
    assert out["unparsed"] == {"files": 1, "bytes": 42}
    assert out["current_generation"] is None
    assert out["other_generations"] == []


def test_an_in_flight_temp_write_is_never_counted():
    """`_save_recording_psd_rows`'s own temp file (`<name>.tmp.npz`) is a write in progress, not a
    finished cache entry -- a dry run (or a later, real sweep) must never count or touch it."""
    cur = f"{B._CHANNEL_CANON_VERSION}_{B._TD_MISSING_VERSION}"
    with _TempCacheDir() as t:
        t.write(f"rec1_hash1_w30p0_{cur}.npz", 10)
        t.write(f"rec1_hash1_w30p0_{cur}.tmp.npz", 999999)
        out = B.psd_rows_cache_generation_report()
    assert out["total_files"] == 1 and out["total_bytes"] == 10, out


def test_the_dry_run_deletes_nothing():
    cur = f"{B._CHANNEL_CANON_VERSION}_{B._TD_MISSING_VERSION}"
    with _TempCacheDir() as t:
        paths = [t.write(f"rec1_hash1_w30p0_{cur}.npz", 10),
                 t.write("rec2_hash2_w30p0_generationX.npz", 20)]
        B.psd_rows_cache_generation_report()
        assert all(os.path.exists(p) for p in paths), "the dry run must not delete any file"


if __name__ == "__main__":
    test_empty_directory_reports_all_zeros()
    test_current_generation_files_are_counted_together_pro_sig_and_all()
    test_an_older_generation_is_counted_apart_from_current_and_by_size()
    test_two_older_generations_are_kept_apart_and_sorted_biggest_first()
    test_a_name_with_no_recognizable_suffix_is_counted_as_unparsed_not_silently_dropped()
    test_an_in_flight_temp_write_is_never_counted()
    test_the_dry_run_deletes_nothing()
    print("All PSD-rows-cache generation-report tests passed.")
