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

Merged here 2026-10-05: test_psd_rows_cache_generations.py, test_rows_set_cache_by_pain_set_class.py, test_recording_spectrum_key_is_its_own_ratings.py, test_spectrum_builder_counts.py.
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

        rows, n_cached, n_computed, _q = B._assemble_psd_rows_cached(UID)
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
        rows1, nc1, ncomp1, _q = B._assemble_psd_rows_cached(UID)
        assert ncomp1 == 2 and nc1 == 0
        assert bench.decodes == 2

        rows2, nc2, ncomp2, _q = B._assemble_psd_rows_cached(UID)
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
        rows, nc, ncomp, _q = B._assemble_psd_rows_cached(UID, force_recompute=True)
        assert ncomp == 2, "force_recompute must ignore both caches and decode every recording"
        assert bench.decodes == 4
        # And the caches are repaired: the very next ordinary call decodes nothing.
        _, _, ncomp2, _q = B._assemble_psd_rows_cached(UID)
        assert ncomp2 == 0
        assert bench.decodes == 4
    print("OK force_recompute ignores both caches and repairs them for the next ordinary call")


# --------------------------------------------------------------------------------------------------
# merged from test_psd_rows_cache_generations.py
# P-07 (handoff pending-items list, 2026-09-25): the per-recording PSD cache directory
# (`_psd_rows_cache_dir`) is never swept -- only the much smaller rows-SET cache is (`_sweep_old_rows_
# cache`) -- so every time `_CHANNEL_CANON_VERSION`, `_TD_MISSING_VERSION` or `_TD_CENTERED_VERSION`
# is bumped, the files the OLD value named are left on disk forever; nothing ever reads or deletes
# them again.
#
# `psd_rows_cache_generation_report` is a READ-ONLY dry run: it counts what is already there, grouped
# by naming generation, and how many bytes each generation holds. This file proves it counts correctly
# and deletes nothing; it does not delete anything itself, and neither does the function under test.
#
# No Django and no database: stubbed the way test_shared_raw_lsb_cache.py stubs Server.
#
# Run inside the container:
#     python3 _agent_bridge/run_tests.py


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


# --------------------------------------------------------------------------------------------------
# merged from test_rows_set_cache_by_pain_set_class.py
# Review B4 (2026-09-12): the rows-set cache keeps one entry per PAIN-SET CLASS, not one in total.
#
# `_assemble_psd_rows_cached` stores the fully assembled per-recording rows for one recording set
# under `rows_<uid>_<sig>.pkl`. The page asks for rating-centred rows (a report set is given); the
# calibration panel and the daily ingest's warm ask for the legacy first-window rows (none is). The
# two are two different signatures of the same kind, and the sweep after each write removed every
# other entry of this participant's -- so the page and the panel evicted each other's rows-set daily,
# and each paid the per-recording loop again. The file name now carries the class (`_p` / `_nop`)
# and the sweep removes only the same class. Pinned on the files that remain on disk.


def _rows_files(bench):
    return sorted(n for n in os.listdir(bench.index_dir) if n.startswith("rows_"))


def test_a_legacy_and_a_rating_centred_rows_set_both_remain():
    with _Bench(n=2) as bench:
        bench.entries[0]["source"] = "TD streaming"
        import numpy as np
        pro = np.array([1_700_000_000.0 + 40.0])
        B._assemble_psd_rows_cached(UID)                      # legacy first-window rows
        B._assemble_psd_rows_cached(UID, pro_times=pro)       # rating-centred rows
        files = _rows_files(bench)
        assert len(files) == 2, files
        assert sum(f.endswith("_nop.pkl") for f in files) == 1, files
        assert sum(f.endswith("_p.pkl") for f in files) == 1, files
        # both are still HITS: a third and fourth call decode nothing
        decodes = bench.decodes
        _r, _nc, ncomp_a, _q = B._assemble_psd_rows_cached(UID)
        _r, _nc, ncomp_b, _q = B._assemble_psd_rows_cached(UID, pro_times=pro)
        assert (ncomp_a, ncomp_b) == (0, 0) and bench.decodes == decodes, (ncomp_a, ncomp_b)


def test_a_new_recording_set_still_evicts_the_older_entry_of_its_own_class_only():
    with _Bench(n=2) as bench:
        import numpy as np
        pro = np.array([1_700_000_000.0 + 40.0])
        bench.entries[0]["source"] = "TD streaming"
        B._assemble_psd_rows_cached(UID)
        B._assemble_psd_rows_cached(UID, pro_times=pro)
        # a different report set is a different rating-centred signature: the OLD `_p` entry goes,
        # the `_nop` entry stays
        B._assemble_psd_rows_cached(UID, pro_times=np.array([1_700_000_000.0 + 50.0]))
        files = _rows_files(bench)
        assert len(files) == 2, files
        assert sum(f.endswith("_nop.pkl") for f in files) == 1, files
        assert sum(f.endswith("_p.pkl") for f in files) == 1, files


def test_a_file_from_before_the_class_suffix_is_swept_by_either_class():
    with _Bench(n=1) as bench:
        old = os.path.join(bench.index_dir, f"rows_{UID}_deadbeef.pkl")
        with open(old, "wb") as fh:
            fh.write(b"x")
        B._assemble_psd_rows_cached(UID)
        files = _rows_files(bench)
        assert not any(f == os.path.basename(old) for f in files), files
        assert len(files) == 1 and files[0].endswith("_nop.pkl"), files


# --------------------------------------------------------------------------------------------------
# merged from test_recording_spectrum_key_is_its_own_ratings.py
# Review B5 (2026-09-12): a voltage-trace recording's spectrum file is keyed on the ratings inside
# ITS OWN coverage, not on every rating in the record.
#
# The rating-centred rows for one recording depend only on the ratings that fall inside that
# recording (`_welch_rows_into`'s `in_win`), yet the file was keyed on a hash of every rating time
# in the record -- so after every rating RCS08 filed, the next page compute re-Welched all 386
# voltage-trace recordings and left 386 new files behind (6,309 files on 2026-09-07). The key is now
# the ratings inside `[start - 60 s, start + duration + 60 s]`, read off the Recording row's own
# `date` and `metadata["Duration"]` with no decode; a row with no duration keeps the whole-set key
# and is counted; a recording's older rating-centred files are removed once the new one lands, and
# a file built under the old whole-set key for the current report set is renamed rather than
# re-Welched.
#
# Pinned on file NAMES on disk: the review's test (an inside rating moving changes the name, an
# outside one moving does not), the sibling sweep, the fallback, and the one-time migration.


T0 = 1_700_000_000.0
WEEK = 7 * 86_400.0


def _entry(t0=T0, dur=90.0):
    return {"uid": "uidX", "hash": "hashX", "source": "TD streaming", "t0": t0, "dur": dur}


def _key(entry, pro):
    pt = np.asarray(pro, dtype=float)
    whole = B._pro_set_signature(pt)
    sig, fell_back = B._recording_pro_signature(entry, pt, whole)
    return os.path.basename(B._recording_psd_cache_path(entry["uid"], entry["hash"], sig)), fell_back


def test_moving_the_inside_rating_changes_the_name_and_moving_the_outside_one_does_not():
    inside, outside = T0 + 40.0, T0 + WEEK
    name0, fb0 = _key(_entry(), [inside, outside])
    name_out_moved, fb1 = _key(_entry(), [inside, outside + 3_600.0])
    name_in_moved, fb2 = _key(_entry(), [inside + 5.0, outside])
    assert not (fb0 or fb1 or fb2)
    assert name_out_moved == name0, (name0, name_out_moved)
    assert name_in_moved != name0, (name0, name_in_moved)
    # a NEW rating a week away changes nothing either (the case that cost 386 files a rating)
    name_new_far, _ = _key(_entry(), [inside, outside, outside + 2 * WEEK])
    assert name_new_far == name0
    # and a recording with no rating inside has the same name as the first-window rows
    name_empty, _ = _key(_entry(), [outside])
    assert name_empty == os.path.basename(B._recording_psd_cache_path("uidX", "hashX", ""))


def test_a_rating_within_the_margin_of_the_edge_is_in_the_key():
    name_a, _ = _key(_entry(), [T0 + 90.0 + 30.0])       # 30 s after the end: inside the margin
    name_b, _ = _key(_entry(), [T0 + 90.0 + 30.0 + 1.0])
    assert name_a != name_b
    name_c, _ = _key(_entry(), [T0 + 90.0 + 61.0])        # beyond the margin: not in the key
    assert name_c == os.path.basename(B._recording_psd_cache_path("uidX", "hashX", ""))


def test_a_row_without_a_duration_keeps_the_whole_set_key_and_is_counted():
    pro = [T0 + 40.0, T0 + WEEK]
    whole = B._pro_set_signature(np.asarray(pro))
    for e in (_entry(dur=None), _entry(t0=None)):
        sig, fell_back = B._recording_pro_signature(e, np.asarray(pro), whole)
        assert fell_back and sig == whole
    sig, fell_back = B._recording_pro_signature({"source": "Montage/survey", "uid": "u", "hash": "h",
                                                 "t0": T0, "dur": 30.0}, None, "")
    assert fell_back and sig == ""      # no report set at all: the legacy path, as before


def test_the_assembly_writes_one_file_per_recording_and_sweeps_its_older_rating_centred_files():
    with _Bench(n=2) as bench:
        bench.entries[0].update({"source": "TD streaming", "t0": T0, "dur": 90.0})
        bench.entries[1].update({"t0": T0 + 5_000.0, "dur": 30.0})
        real_load = B.Database.loadSourceFile.side_effect

        def _load(pointer, hashed):
            if pointer == "ptr0":
                bench.decodes += 1
                rng = np.random.default_rng(0)
                n = int(90 * 250)
                return {"ChannelNames": ["ZERO_THREE_LEFT"], "Data": rng.standard_normal((n, 1)),
                        "SamplingRate": 250.0, "StartTime": T0, "Duration": 90.0,
                        "Missing": np.zeros((n, 1))}
            return real_load(pointer, hashed)
        B.Database.loadSourceFile.side_effect = _load

        pro1 = np.array([T0 + 40.0, T0 + WEEK])
        rows1, _nc, ncomp1, q1 = B._assemble_psd_rows_cached(UID, pro_times=pro1)
        assert ncomp1 == 2 and q1["n_recordings_keyed_on_whole_set"] == 0, (ncomp1, q1)
        files1 = sorted(os.listdir(bench.rows_dir))
        assert len(files1) == 2, files1
        # a rating filed a week away: NOTHING is re-Welched and no new file appears
        pro2 = np.array([T0 + 40.0, T0 + WEEK, T0 + 2 * WEEK])
        rows2, _nc, ncomp2, _q = B._assemble_psd_rows_cached(UID, pro_times=pro2)
        assert ncomp2 == 0, "a far-away rating must not re-Welch anything"
        assert sorted(os.listdir(bench.rows_dir)) == files1
        # the inside rating moves: recording 0 is re-Welched, its old file is swept, still 2 files
        pro3 = np.array([T0 + 45.0, T0 + WEEK, T0 + 2 * WEEK])
        rows3, _nc, ncomp3, _q = B._assemble_psd_rows_cached(UID, pro_times=pro3)
        assert ncomp3 == 1, ncomp3
        files3 = sorted(os.listdir(bench.rows_dir))
        assert len(files3) == 2, files3
        assert files3 != files1
        t_rows3 = sorted(r["t"] for r in rows3 if r["source"] == "TD streaming")
        assert t_rows3 == [T0 + 45.0], t_rows3      # the row is centred on the moved rating
        # the swept name is no longer in the manifest either
        manifest = B._load_rows_manifest(UID)
        assert all(n in files3 for n in manifest if n.endswith(".npz")), (manifest, files3)


def test_a_whole_set_file_for_the_current_report_set_is_renamed_not_rebuilt():
    """The one-time migration: a file under the pre-B5 whole-set key, for THIS report set, is
    moved onto the new per-recording key and its rows served, with no decode."""
    with _Bench(n=1) as bench:
        bench.entries[0].update({"source": "TD streaming", "t0": T0, "dur": 90.0})
        pro = np.array([T0 + 40.0, T0 + WEEK])
        whole = B._pro_set_signature(pro)
        old_path = B._recording_psd_cache_path("uid0", "hash0", whole)
        B._save_recording_psd_rows(old_path, [{"channel": "ZERO_THREE_LEFT", "source": "TD streaming",
                                               "t": T0 + 40.0, "freq": np.array([1.0, 2.0]),
                                               "power": np.array([3.0, 4.0]), "dur": 30.0}])
        rows, nc, ncomp, _q = B._assemble_psd_rows_cached(UID, pro_times=pro)
        assert (nc, ncomp, bench.decodes) == (1, 0, 0), (nc, ncomp, bench.decodes)
        assert [r["t"] for r in rows] == [T0 + 40.0]
        assert not os.path.exists(old_path), "the old file is moved, not copied"
        sig, _fb = B._recording_pro_signature(bench.entries[0], pro, whole)
        assert os.path.exists(B._recording_psd_cache_path("uid0", "hash0", sig))


# --------------------------------------------------------------------------------------------------
# merged from test_spectrum_builder_counts.py
# Review B6 (2026-09-12): the spectrum builder's two silent failures are logged AND counted.
#
# `_welch_rows_into` had two bare `except` blocks. The first wrapped the rating-centred spectrum:
# when it raised, the recording fell through to a spectrum stamped at the recording START (a
# different quantity), with no log line and no counter. The second wrapped the first-window
# spectrum: when it raised, the recording was simply absent from the pool. Both outcomes were then
# persisted by the per-recording cache. Each is now counted, the counts ride with the cached rows to
# the assembled matrix payload and to the page's `cache` block, and a file written before the
# counters existed reads as "not recorded" rather than as zero.
#
# Tests pin VALUES: the fell-back recording's row time equals its start time AND the counter reads
# 1; a first-window failure is counted as skipped; the counts survive both cache layers; a legacy
# file is reported as unknown. Plain asserts, stubbed like `test_psd_rows_manifest.py`.


import logging
from ..routines import streaming_psd as _sp           # noqa: E402
FS = 250.0


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
