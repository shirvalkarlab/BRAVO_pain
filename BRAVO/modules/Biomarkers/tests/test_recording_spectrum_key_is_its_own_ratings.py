"""Review B5 (2026-09-12): a voltage-trace recording's spectrum file is keyed on the ratings inside
ITS OWN coverage, not on every rating in the record.

The rating-centred rows for one recording depend only on the ratings that fall inside that
recording (`_welch_rows_into`'s `in_win`), yet the file was keyed on a hash of every rating time
in the record -- so after every rating RCS08 filed, the next page compute re-Welched all 386
voltage-trace recordings and left 386 new files behind (6,309 files on 2026-09-07). The key is now
the ratings inside `[start - 60 s, start + duration + 60 s]`, read off the Recording row's own
`date` and `metadata["Duration"]` with no decode; a row with no duration keeps the whole-set key
and is counted; a recording's older rating-centred files are removed once the new one lands, and
a file built under the old whole-set key for the current report set is renamed rather than
re-Welched.

Pinned on file NAMES on disk: the review's test (an inside rating moving changes the name, an
outside one moving does not), the sibling sweep, the fallback, and the one-time migration.
"""
import os

import numpy as np

from .test_psd_rows_manifest import B, UID, _Bench

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


if __name__ == "__main__":
    test_moving_the_inside_rating_changes_the_name_and_moving_the_outside_one_does_not()
    test_a_rating_within_the_margin_of_the_edge_is_in_the_key()
    test_a_row_without_a_duration_keeps_the_whole_set_key_and_is_counted()
    test_the_assembly_writes_one_file_per_recording_and_sweeps_its_older_rating_centred_files()
    test_a_whole_set_file_for_the_current_report_set_is_renamed_not_rebuilt()
    print("All per-recording-key tests passed.")
