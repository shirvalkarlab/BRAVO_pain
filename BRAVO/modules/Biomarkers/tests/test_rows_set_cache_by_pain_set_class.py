"""Review B4 (2026-09-12): the rows-set cache keeps one entry per PAIN-SET CLASS, not one in total.

`_assemble_psd_rows_cached` stores the fully assembled per-recording rows for one recording set
under `rows_<uid>_<sig>.pkl`. The page asks for rating-centred rows (a report set is given); the
calibration panel and the daily ingest's warm ask for the legacy first-window rows (none is). The
two are two different signatures of the same kind, and the sweep after each write removed every
other entry of this participant's -- so the page and the panel evicted each other's rows-set daily,
and each paid the per-recording loop again. The file name now carries the class (`_p` / `_nop`)
and the sweep removes only the same class. Pinned on the files that remain on disk.
"""
import os

from .test_psd_rows_manifest import B, UID, _Bench


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


if __name__ == "__main__":
    test_a_legacy_and_a_rating_centred_rows_set_both_remain()
    test_a_new_recording_set_still_evicts_the_older_entry_of_its_own_class_only()
    test_a_file_from_before_the_class_suffix_is_swept_by_either_class()
    print("All rows-set-class tests passed.")
