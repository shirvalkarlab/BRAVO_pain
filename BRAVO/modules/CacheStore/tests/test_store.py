"""Behaviour tests for the one cache store.

Django-free: every test points the store at a temporary directory of its own, so nothing here
reads or writes the real cache. Plain `assert` throughout because the container has no pytest and
`pytest.approx` / `pytest.raises` are unavailable there.
"""
import datetime
import json
import os
import pathlib
import pickle
import shutil
import sys
import tempfile

import numpy as np
import pandas as pd

_BRAVO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_BRAVO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BRAVO_ROOT))

from modules.CacheStore import provenance as prov
from modules.CacheStore import store as st

UID = "2e3c75c00d7f4f37b53a048d195f11da"


class _Sandbox:
    """Point the store at a fresh directory and turn the ledger off for the duration.

    The ledger is off because these tests must run with no database at all; `test_ledger.py`
    covers it separately and skips itself when no database is configured.
    """

    def __enter__(self):
        from modules.CacheStore import ledger
        self._dir = tempfile.mkdtemp(prefix="bravo_store_test_")
        self._prev_dir = st.DIR_OVERRIDE
        self._prev_ledger = ledger.ENABLED
        st.DIR_OVERRIDE = self._dir
        ledger.ENABLED = False
        st.clear()
        return self._dir

    def __exit__(self, *exc):
        from modules.CacheStore import ledger
        st.DIR_OVERRIDE = self._prev_dir
        ledger.ENABLED = self._prev_ledger
        shutil.rmtree(self._dir, ignore_errors=True)
        return False


def _tree(root):
    """Every file under the root with its size and content hash, for byte-identity checks."""
    import hashlib
    out = {}
    for dirpath, _dirs, names in os.walk(root):
        for n in sorted(names):
            p = os.path.join(dirpath, n)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = (os.path.getsize(p),
                                                 hashlib.sha256(fh.read()).hexdigest())
    return out


# --------------------------------------------------------------------------------------------
# each format round-trips, and the format is chosen by the shape of the payload
# --------------------------------------------------------------------------------------------

def test_a_table_goes_to_parquet_and_round_trips_with_its_timezone_intact():
    """The timestamp is the reason comma-separated and JSON files were excluded, so it is tested."""
    with _Sandbox():
        df = pd.DataFrame({
            "when": pd.to_datetime(["2026-08-18 09:00:00", "2026-08-18 09:01:00"], utc=True),
            "amplitude_ma": [1.0, 2.5],
            "channel": ["ZERO_TWO_LEFT", "ZERO_TWO_LEFT"],
        })
        assert st.choose_format(df) == "parquet"
        assert st.store("therapy_pain_matched", UID, ("sig", 1), df) is True
        back = st.load("therapy_pain_matched", UID, ("sig", 1))
        assert back is not None
        assert list(back.columns) == list(df.columns)
        assert len(back) == len(df)
        # The timezone survived. A comma-separated file would have returned naive strings here.
        assert str(back["when"].dtype).startswith("datetime64[") and "UTC" in str(back["when"].dtype)
        assert back["when"].iloc[0] == df["when"].iloc[0]
        assert back["amplitude_ma"].tolist() == df["amplitude_ma"].tolist()


def test_arrays_go_to_a_compressed_array_file_and_round_trip_exactly():
    with _Sandbox():
        payload = {"tiles": np.arange(24, dtype=float).reshape(2, 3, 4),
                   "centers_hz": np.array([8.5, 9.5, 10.5])}
        assert st.choose_format(payload) == "npz"
        assert st.store("raw_lsb_tiles", UID, ("tiles", 7), payload) is True
        back = st.load("raw_lsb_tiles", UID, ("tiles", 7))
        assert back is not None and set(back) == {"tiles", "centers_hz"}
        # Exact equality, not a tolerance: this is a stored copy of the same numbers, and any
        # difference at all would mean the store changed a measurement.
        assert np.array_equal(back["tiles"], payload["tiles"])
        assert np.array_equal(back["centers_hz"], payload["centers_hz"])


def test_anything_else_falls_back_to_pickle():
    with _Sandbox():
        payload = {"verdict": "device_native", "n_windows": 6, "ratio": 1.10,
                   "rows": [{"center_hz": 23.44, "route": "device_native"}]}
        assert st.choose_format(payload) == "pickle"
        assert st.store("ground_truth_verdict", UID, ("gt", 1), payload, writer="biomarkers", provenance=[]) is True
        assert st.load("ground_truth_verdict", UID, ("gt", 1)) == payload


# --------------------------------------------------------------------------------------------
# the key decides, not the caller
# --------------------------------------------------------------------------------------------

def test_a_matching_key_leaves_the_directory_byte_identical():
    """THE KEY DECIDES WHETHER TO WRITE. This is the assertion that makes that claim checkable."""
    with _Sandbox() as root:
        df = pd.DataFrame({"a": [1, 2, 3]})
        built = []
        got, wrote = st.store_if_absent("biomarker_band_results", UID, ("k", 1),
                                        lambda: (built.append(1), df)[1],
                                        writer="biomarkers", provenance=[])
        assert wrote is True and len(built) == 1 and got is not None
        before = _tree(root)
        assert before, "the first write should have produced files"

        got2, wrote2 = st.store_if_absent("biomarker_band_results", UID, ("k", 1),
                                          lambda: (built.append(1), df)[1],
                                          writer="biomarkers", provenance=[])
        assert wrote2 is False, "a matching key must not write"
        assert len(built) == 1, "a matching key must not even rebuild the payload"
        assert got2 is not None and len(got2) == 3
        assert _tree(root) == before, "a matching key changed the directory"


def test_a_different_signature_is_a_miss_and_not_a_wrong_answer():
    with _Sandbox():
        st.store("biomarker_band_results", UID, ("k", 1), pd.DataFrame({"a": [1]}), writer="biomarkers", provenance=[])
        assert st.load("biomarker_band_results", UID, ("k", 2)) is None


def test_a_file_whose_stored_signature_disagrees_is_discarded_rather_than_returned():
    """A hash can collide and a stale file can be left by differently-keyed code.

    The check is on the signature itself, so the failure mode is a rebuild and never a wrong
    answer. Built by writing a legacy-shaped pickle by hand under the name a different signature
    hashes to.
    """
    with _Sandbox():
        wanted = ("k", "wanted")
        stem = st._stem("ground_truth_verdict", UID, wanted)
        with open(stem + ".pkl", "wb") as fh:
            pickle.dump({"signature": ("k", "SOMETHING ELSE"), "payload": {"bad": True}}, fh)
        assert os.path.exists(stem + ".pkl")
        assert st.load("ground_truth_verdict", UID, wanted) is None
        assert not os.path.exists(stem + ".pkl"), "the unusable entry should have been removed"


def test_a_payload_with_no_sidecar_in_a_checkable_format_is_refused():
    """Parquet cannot carry the wrapper the pickle path uses, so with no sidecar it is unverifiable.

    Refusing is the only safe answer: a rebuild is always correct and a wrong answer is not.
    """
    with _Sandbox():
        sig = ("k", 9)
        st.store("biomarker_band_results", UID, sig, pd.DataFrame({"a": [1]}), writer="biomarkers", provenance=[])
        stem = st._stem("biomarker_band_results", UID, sig)
        os.remove(stem + ".meta.json")
        assert st.load("biomarker_band_results", UID, sig) is None


# --------------------------------------------------------------------------------------------
# the stamp
# --------------------------------------------------------------------------------------------

def test_the_stamp_is_readable_without_opening_the_payload():
    with _Sandbox():
        sig = ("tiles", 3)
        st.store("raw_lsb_tiles", UID, sig,
                 {"tiles": np.zeros((2, 2))}, trigger="ingest", n_recordings=832,
                 writer="biomarkers")
        stamp = st.read_stamp("raw_lsb_tiles", UID, sig)
        assert stamp is not None
        assert stamp["trigger"] == "ingest"
        assert stamp["n_recordings"] == 832
        assert stamp["writer"] == "biomarkers"
        assert stamp["kind"] == "raw_lsb_tiles"
        assert stamp["format"] == "npz"
        assert stamp["payload_bytes"] > 0
        # A real timestamp, parseable, and carrying a timezone rather than a bare local clock.
        when = datetime.datetime.fromisoformat(stamp["written_utc"])
        assert when.tzinfo is not None


def test_the_newest_stamp_is_found_without_knowing_todays_signature():
    """A page says "last updated" before it knows whether today's key matches."""
    with _Sandbox():
        st.store("inputs", UID, ("s", 1), {"a": 1}, trigger="first", writer="biomarkers", provenance=[])
        st.store("inputs", UID, ("s", 2), {"a": 2}, trigger="second", writer="biomarkers", provenance=[])
        newest = st.newest_stamp("inputs", UID)
        assert newest is not None and newest["trigger"] == "second"


def test_the_sidecar_is_the_commit_marker_so_a_half_written_entry_is_invisible():
    """Simulates a writer that died between the payload and the sidecar."""
    with _Sandbox():
        sig = ("k", 11)
        st.store("biomarker_band_results", UID, sig, pd.DataFrame({"a": [1]}), writer="biomarkers", provenance=[])
        stem = st._stem("biomarker_band_results", UID, sig)
        os.rename(stem + ".meta.json", stem + ".meta.json.7.tmp")
        assert st.load("biomarker_band_results", UID, sig) is None


# --------------------------------------------------------------------------------------------
# housekeeping
# --------------------------------------------------------------------------------------------

def test_a_new_entry_sweeps_this_participants_older_ones_and_leaves_others_alone():
    """245 MB per entry means an unswept directory grows by gigabytes a month."""
    with _Sandbox():
        other = "OTHER_PARTICIPANT_UID"
        st.store("raw_lsb_tiles", UID, ("s", 1), {"a": np.zeros(3)})
        st.store("raw_lsb_tiles", other, ("s", 1), {"a": np.zeros(3)})
        assert st.load("raw_lsb_tiles", UID, ("s", 1)) is not None

        st.store("raw_lsb_tiles", UID, ("s", 2), {"a": np.ones(3)})
        assert st.load("raw_lsb_tiles", UID, ("s", 1)) is None, "the older entry should be gone"
        assert st.load("raw_lsb_tiles", UID, ("s", 2)) is not None
        assert st.load("raw_lsb_tiles", other, ("s", 1)) is not None, \
            "another participant's entry must never be swept"


def test_a_history_kind_keeps_its_superseded_entries_and_every_other_kind_still_sweeps():
    """The pain-report snapshot exists so a result can name the exact report table it used. A
    swept snapshot would leave the ledger row and not the table, so this kind keeps its history."""
    with _Sandbox():
        assert "redcap_reports" in st.KEEP_HISTORY_KINDS
        a = pd.DataFrame({"nrs": [3.0, 4.0]})
        b = pd.DataFrame({"nrs": [3.0, 4.0, 5.0]})
        st.store("redcap_reports", UID, ("r", 1), a, writer="biomarkers", provenance=[])
        st.store("redcap_reports", UID, ("r", 2), b, writer="biomarkers", provenance=[])
        assert st.load("redcap_reports", UID, ("r", 1)) is not None, \
            "the earlier report set was swept, so a result citing it can no longer be reproduced"
        assert len(st.load("redcap_reports", UID, ("r", 2))) == 3
        # the control: a kind not in the set still sweeps, so the tile behaviour is unchanged
        st.store("biomarker_band_results", UID, ("k", 1), a, writer="biomarkers", provenance=[])
        st.store("biomarker_band_results", UID, ("k", 2), b, writer="biomarkers", provenance=[])
        assert st.load("biomarker_band_results", UID, ("k", 1)) is None


def test_store_if_absent_reads_from_the_root_it_writes_to():
    """Found by the first snapshot test: the read went to the production root while the write went
    to the caller's, so under an override the key never matched and every call wrote."""
    with _Sandbox() as sandbox_root:
        other = tempfile.mkdtemp(prefix="bravo_store_root_")
        try:
            df = pd.DataFrame({"a": [1]})
            st.store_if_absent("biomarker_band_results", UID, ("k", 1), lambda: df, root=other,
                               writer="biomarkers", provenance=[])
            before = _tree(other)
            _got, wrote = st.store_if_absent("biomarker_band_results", UID, ("k", 1),
                                             lambda: df, root=other,
                                             writer="biomarkers", provenance=[])
            assert wrote is False, "the second call wrote again under an explicit root"
            assert _tree(other) == before
            assert _tree(sandbox_root) == {}, "nothing should have landed in the default root"
        finally:
            shutil.rmtree(other, ignore_errors=True)


def test_the_ledger_records_production_writes_and_not_writes_under_an_override():
    """Found in the live ledger: 214 rows for "test-participant" from the container's tile tests.
    The ledger carries no directory, so only the store can keep test writes out of it."""
    from modules.CacheStore import ledger
    recorded = []
    prev_record, prev_enabled = ledger.record, ledger.ENABLED
    ledger.record, ledger.ENABLED = (lambda meta: recorded.append(meta)), True
    try:
        with _Sandbox():                                   # DIR_OVERRIDE set: a test root
            st.store("biomarker_band_results", UID, ("k", 1), pd.DataFrame({"a": [1]}), writer="biomarkers", provenance=[])
            assert recorded == [], "a write under the test override reached the ledger"
        other = tempfile.mkdtemp(prefix="bravo_store_root_")
        try:
            st.store("biomarker_band_results", UID, ("k", 2), pd.DataFrame({"a": [1]}),
                     root=other, writer="biomarkers", provenance=[])                           # an explicit caller root
            assert recorded == [], "a write under a caller's own root reached the ledger"
        finally:
            shutil.rmtree(other, ignore_errors=True)
        prod = tempfile.mkdtemp(prefix="bravo_store_prod_")
        prev_dir, prev_env = st.DIR_OVERRIDE, os.environ.get("DATASERVER_PATH")
        st.DIR_OVERRIDE = None
        os.environ["DATASERVER_PATH"] = prod
        try:
            if st.root_dir() == os.path.join(prod, "cache"):   # no Django settings in the way
                st.store("biomarker_band_results", UID, ("k", 3), pd.DataFrame({"a": [1]}), writer="biomarkers", provenance=[])
                assert len(recorded) == 1 and recorded[0]["kind"] == "biomarker_band_results"
        finally:
            st.DIR_OVERRIDE = prev_dir
            if prev_env is None:
                os.environ.pop("DATASERVER_PATH", None)
            else:
                os.environ["DATASERVER_PATH"] = prev_env
            shutil.rmtree(prod, ignore_errors=True)
    finally:
        ledger.record, ledger.ENABLED = prev_record, prev_enabled


def test_a_derived_kind_with_no_writer_is_refused_and_a_raw_kind_is_not():
    """A sidecar with no writer and no provenance looks like a raw input to anything that later
    cites it. The store refuses the write so a call site that forgot is found at write time."""
    with _Sandbox() as root:
        assert st.store("biomarker_band_results", UID, ("k", 1), pd.DataFrame({"a": [1]})) is False
        assert _tree(root) == {}, "a refused write left a file behind"
        assert st._EVENTS["refused_no_writer"] >= 1
        # the raw kinds carry no writer requirement: the tiles are written by the tile builder
        assert st.store("raw_lsb_tiles", UID, ("t", 1), {"a": np.zeros(2)}) is True
        # a derived kind with a writer but no chain is written, counted, and carries an empty chain
        before = st._EVENTS["written_without_provenance"]
        assert st.store("biomarker_band_results", UID, ("k", 2), pd.DataFrame({"a": [1]}),
                        writer="biomarkers") is True
        assert st._EVENTS["written_without_provenance"] == before + 1
        assert st.read_stamp("biomarker_band_results", UID, ("k", 2))["provenance"] == []


def test_a_mismatched_sidecar_is_a_miss_without_the_payload_being_opened():
    """A caller that only wants to know whether to write must not pay for reading a payload."""
    with _Sandbox():
        st.store("biomarker_band_results", UID, ("k", 1), pd.DataFrame({"a": [1]}),
                 writer="biomarkers", provenance=[])
        stem = st._stem("biomarker_band_results", UID, ("k", 1))
        opened = []
        real = st._load_payload

        def spy(path, fmt):
            opened.append(path)
            return real(path, fmt)
        st._load_payload = spy
        try:
            # same file name would need the same signature; forge a sidecar mismatch instead
            with open(st._meta_path(stem)) as fh:
                meta = json.load(fh)
            meta["signature_key"] = "0" * 40
            with open(st._meta_path(stem), "w") as fh:
                json.dump(meta, fh)
            assert st.load("biomarker_band_results", UID, ("k", 1)) is None
            assert opened == [], "the payload was opened although the sidecar already said no"
        finally:
            st._load_payload = real


def test_the_newest_entry_can_be_read_by_name_with_its_stamp_and_still_refused_by_consumer():
    """A reader that cannot rebuild the writer's key asks for the newest entry and gets the
    sidecar with it. The refusal applies as it does to a keyed read."""
    with _Sandbox():
        assert st.load_newest("amplitude_effect_by_band", UID) == (None, None)
        tiles = st.product_key("raw_lsb_tiles", UID, ("t", 1))
        st.store("amplitude_effect_by_band", UID, ("older", 1), pd.DataFrame({"a": [1]}),
                 writer="closed_loop", provenance=prov.flatten(
                     [prov.entry(tiles, kind="raw_lsb_tiles", writer="biomarkers")]))
        got, stamp = st.load_newest("amplitude_effect_by_band", UID, consumer="stim_optimizer")
        assert got is not None and len(got) == 1
        assert stamp["writer"] == "closed_loop" and stamp["provenance"][0]["key"] == tiles
        # a chain that contains the reader's own choice is refused, by name as by key
        ladder = st.product_key("exploration_ladder", UID, ("l", 1))
        st.store("amplitude_effect_by_band", UID, ("newer", 2), pd.DataFrame({"a": [2]}),
                 writer="closed_loop", provenance=prov.flatten(
                     [prov.entry(ladder, kind="exploration_ladder", writer="stim_optimizer")]))
        raised = False
        try:
            st.load_newest("amplitude_effect_by_band", UID, consumer="stim_optimizer")
        except prov.SelfDerivedProduct:
            raised = True
        assert raised, "the newest entry derived from the reader's own ladder was released"
        got, _ = st.load_newest("amplitude_effect_by_band", UID, consumer="closed_loop")
        assert int(got["a"].iloc[0]) == 2, "the newest entry, not the first, is the one read"


def test_an_entry_over_the_limit_is_refused_and_leaves_nothing_behind():
    with _Sandbox() as root:
        st.MAX_BYTES_BY_KIND["tiny_kind"] = 64
        try:
            payload = {"a": np.arange(10_000, dtype=float)}
            assert st.store("tiny_kind", UID, ("s", 1), payload, writer="biomarkers", provenance=[]) is False
            assert st.load("tiny_kind", UID, ("s", 1)) is None
            leftover = [p for p in _tree(root) if "tiny_kind" in p]
            assert leftover == [], f"the refused write left files behind: {leftover}"
        finally:
            st.MAX_BYTES_BY_KIND.pop("tiny_kind", None)


def test_the_store_turned_off_is_a_miss_and_never_an_exception():
    """With the store off, a cache is simply absent. It must not fail a page.

    Uses the explicit off switch rather than clearing the storage path, because on a configured
    server Django supplies that path and the environment variable is not what decides. That is
    exactly how the first version of this test failed in the container while passing on the host.
    """
    prev_enabled, prev_dir = st.ENABLED, st.DIR_OVERRIDE
    try:
        st.ENABLED = False
        assert st.root_dir() is None
        assert st.kind_dir("raw_lsb_tiles") is None
        assert st.load("raw_lsb_tiles", UID, ("s", 1)) is None
        assert st.store("raw_lsb_tiles", UID, ("s", 1), {"a": np.zeros(2)}) is False
        assert st.read_stamp("raw_lsb_tiles", UID, ("s", 1)) is None
        assert st.newest_stamp("raw_lsb_tiles", UID) is None
        assert st.stats()["root"] is None
        assert st.clear() == 0
    finally:
        st.ENABLED, st.DIR_OVERRIDE = prev_enabled, prev_dir


def test_the_off_switch_does_not_delete_anything():
    """Turning the store off must be reversible: the files are still there when it comes back."""
    with _Sandbox() as root:
        st.store("inputs", UID, ("s", 1), {"a": 1}, writer="biomarkers", provenance=[])
        before = _tree(root)
        assert before
        st.ENABLED = False
        try:
            assert st.load("inputs", UID, ("s", 1)) is None
        finally:
            st.ENABLED = True
        assert _tree(root) == before
        assert st.load("inputs", UID, ("s", 1)) == {"a": 1}


#: The closed-loop module's old per-entry cap, and the measured size of the biomarker tile entry.
_OLD_SMALL_CAP_BYTES = 256 * 1024 * 1024          # 268,435,456
_MEASURED_TILE_BYTES = int(245.90e6)              # 245.90 MB, measured on the real record


def test_the_two_predecessors_mismatched_limits_are_gone_and_the_larger_one_won():
    """1,073,741,824 against 268,435,456 for no stated reason, and the larger was chosen.

    THE REASON IS HEADROOM, NOT REFUSAL. An earlier version of this test said the smaller cap
    "would have refused the 245 MB tile entry" and asserted `245 MiB < MAX_BYTES_DEFAULT`, which
    is true of the smaller cap as well and so discriminated nothing. 268,435,456 bytes is 256 MiB
    and the entry fits under it. What is wrong with it is that it fits by 4 to 9 percent, on the
    one entry the cache exists to hold, and crossing a cap is silent.
    """
    assert st.MAX_BYTES_DEFAULT == 1024 * 1024 * 1024
    assert _OLD_SMALL_CAP_BYTES == 268_435_456
    # The claim being corrected: the smaller cap DID fit the measured entry.
    assert _OLD_SMALL_CAP_BYTES > _MEASURED_TILE_BYTES
    # And this is what was actually wrong with it - headroom in single-digit percent.
    assert _OLD_SMALL_CAP_BYTES / _MEASURED_TILE_BYTES < 1.10
    # The chosen cap leaves room for the tile set to grow with more visits and more channels.
    assert st.MAX_BYTES_DEFAULT / _MEASURED_TILE_BYTES > 4.0


def test_stats_reports_what_is_on_disk_and_what_the_store_has_done():
    with _Sandbox():
        st.store("inputs", UID, ("s", 1), {"a": 1}, writer="biomarkers", provenance=[])
        st.load("inputs", UID, ("s", 1))
        st.load("inputs", UID, ("s", 999))
        s = st.stats("inputs")
        assert s["directories"].get("closed_loop", {}).get("entries") == 1
        assert s["bytes"] > 0
        assert s["events"]["writes"] >= 1
        assert s["events"]["hits"] >= 1
        assert s["events"]["misses"] >= 1
        assert s["kind_directory"].endswith("closed_loop")


# --------------------------------------------------------------------------------------------
# backward compatibility with what is already on disk
# --------------------------------------------------------------------------------------------

def test_the_existing_tile_files_are_still_found_by_their_historical_name():
    """245.90 MB of tiles cost 37 s to rebuild, so the naming for that one kind is frozen.

    This reproduces the predecessor's exact file name and wrapper by hand, with no sidecar, and
    requires that the new store reads it.
    """
    with _Sandbox() as root:
        sig = ("legacy", 1)
        d = os.path.join(root, "biomarker_shared")
        os.makedirs(d, exist_ok=True)
        key = st.signature_key(sig)
        legacy = os.path.join(d, f"raw_lsb_tiles.v1.{UID}.{key}.pkl")
        with open(legacy, "wb") as fh:
            pickle.dump({"signature": sig, "payload": {"tiles": [1, 2, 3]},
                         "written_utc": "2026-09-06T04:45:00+00:00"}, fh, protocol=5)
        assert st.load("raw_lsb_tiles", UID, sig) == {"tiles": [1, 2, 3]}
        assert st.stats()["events"]["legacy_no_sidecar"] >= 1


def test_the_signature_naming_matches_the_predecessors_exactly():
    """The existing 782 MB of files depend on `repr` of the signature and a 20-byte digest.

    A different encoding would silently miss every one of them, so the recipe is pinned here.
    """
    import hashlib
    sig = ("a", 1, None, 2.5)
    assert st.signature_key(sig) == hashlib.blake2b(repr(sig).encode("utf8"),
                                                    digest_size=20).hexdigest()


def test_a_product_key_names_the_kind_the_participant_and_the_signature():
    key = st.product_key("biomarker_band_results", UID, ("s", 1))
    assert key == f"biomarker_band_results/{UID}/{st.signature_key(('s', 1))}"
    assert prov.module_of(key) == "biomarkers"


def test_stamp_for_key_finds_the_entry_named_and_not_the_newest():
    """`redcap_reports` keeps its history, so two entries of one kind can coexist."""
    with _Sandbox() as root:
        a = st.store("redcap_reports", UID, ("set", 1), pd.DataFrame({"x": [1]}), root=root)
        b = st.store("redcap_reports", UID, ("set", 2), pd.DataFrame({"x": [2]}), root=root)
        key_a = st.product_key("redcap_reports", UID, ("set", 1))
        got = st.stamp_for_key(key_a, root=root)
        assert got and got["signature_key"] == key_a.split("/")[-1]
        assert st.newest_stamp("redcap_reports", UID, root=root)["signature_key"] != got["signature_key"]
        assert st.stamp_for_key("redcap_reports/%s/0000" % UID, root=root) is None
        assert st.stamp_for_key("not-a-key", root=root) is None
        del a, b


def test_load_newest_reports_an_unreadable_entry_and_discards_it():
    with _Sandbox() as root:
        st.store("amplitude_effect_by_band", UID, ("amp", 9), pd.DataFrame({"x": [1.0]}),
                 writer="closed_loop", provenance=[], root=root)
        d = st.kind_dir("amplitude_effect_by_band", create=False, root=root)
        payload = [f for f in os.listdir(d) if f.endswith(".parquet")][0]
        with open(os.path.join(d, payload), "wb") as fh:
            fh.write(b"garbage")
        table, stamp = st.load_newest("amplitude_effect_by_band", UID, root=root)
        assert table is None and stamp and stamp["writer"] == "closed_loop"
        assert os.listdir(d) == [], "an unreadable entry is discarded, not offered again"
        assert st.load_newest("amplitude_effect_by_band", UID, root=root) == (None, None)


def test_the_page_status_reads_the_sidecar_and_says_when_there_is_nothing_yet():
    with _Sandbox() as root:
        none = st.status_for_page("stim_optimizer_response", UID, ("s", 1), what_it_means="m", root=root)
        assert none["exists"] is False and none["last_built_utc"] is None and "no stored entry" in none["note"]
        st.store("stim_optimizer_response", UID, ("s", 1), {"a": 1}, writer="stim_optimizer",
                 provenance=[], trigger="stim_optimizer_request", n_recordings=7, root=root)
        got = st.status_for_page("stim_optimizer_response", UID, ("s", 1), what_it_means="m", root=root)
        assert got["exists"] is True and got["last_built_utc"] and got["trigger"] == "stim_optimizer_request"
        assert got["n_recordings"] == 7 and got["writer"] == "stim_optimizer" and got["what_it_means"] == "m"
        assert st.status_for_page("stim_optimizer_response", UID, None, what_it_means="m", root=root)["exists"] is False
