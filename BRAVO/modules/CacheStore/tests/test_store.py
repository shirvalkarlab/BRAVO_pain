"""Behaviour tests for the one cache store.

Merged here 2026-10-05: test_keep_newest.py, test_mapped_format.py (their sections below keep their
own notes).

Django-free: every test points the store at a temporary directory of its own, so nothing here
reads or writes the real cache. Plain `assert` throughout, and no test takes arguments, because the
container's runner (`run_tests.py`) calls each `test_*` with nothing.
"""
import datetime
import json
import mmap
import os
import pickle
import shutil
import tempfile

import numpy as np
import pandas as pd

from modules.CacheStore import provenance as prov
from modules.CacheStore import store as st
from modules.CacheStore.tests._helpers import UID, Sandbox as _Sandbox, tree as _tree


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


def test_a_table_with_no_committed_sidecar_is_refused_whether_removed_or_half_written():
    """Parquet cannot carry the wrapper the pickle path uses, so with no sidecar it is unverifiable;
    refusing is the only safe answer (a rebuild is always correct and a wrong answer is not). The
    sidecar is also the commit marker: a writer that died between the payload and the sidecar
    leaves only a temporary sidecar, and the half-written entry must be invisible.
    (Merged 2026-10-05 from `test_a_payload_with_no_sidecar_in_a_checkable_format_is_refused` and
    `test_the_sidecar_is_the_commit_marker_so_a_half_written_entry_is_invisible`.)"""
    for case in ("sidecar removed", "sidecar left as a temporary file"):
        with _Sandbox():
            sig = ("k", 9)
            st.store("biomarker_band_results", UID, sig, pd.DataFrame({"a": [1]}),
                     writer="biomarkers", provenance=[])
            stem = st._stem("biomarker_band_results", UID, sig)
            if case == "sidecar removed":
                os.remove(stem + ".meta.json")
            else:
                os.rename(stem + ".meta.json", stem + ".meta.json.7.tmp")
            assert st.load("biomarker_band_results", UID, sig) is None, case


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


# --------------------------------------------------------------------------------------------
# housekeeping
# --------------------------------------------------------------------------------------------

def test_a_new_entry_sweeps_this_participants_older_ones_and_leaves_others_alone():
    """245 MB per entry means an unswept directory grows by gigabytes a month. The default of one
    entry per kind is unchanged for a kind not listed in `KEEP_NEWEST_BY_KIND`, and that matters:
    a tile kind that quietly began keeping twelve would cost about three gigabytes per participant
    (absorbed 2026-10-05: `test_keep_newest.py::test_a_kind_that_is_not_listed_still_keeps_exactly_one`)."""
    with _Sandbox():
        assert _ONE_ONLY == "raw_lsb_tiles" and _ONE_ONLY not in st.KEEP_NEWEST_BY_KIND
        other = "OTHER_PARTICIPANT_UID"
        st.store("raw_lsb_tiles", UID, ("s", 1), {"a": np.zeros(3)})
        st.store("raw_lsb_tiles", other, ("s", 1), {"a": np.zeros(3)})
        assert st.load("raw_lsb_tiles", UID, ("s", 1)) is not None

        st.store("raw_lsb_tiles", UID, ("s", 2), {"a": np.ones(3)})
        assert st.load("raw_lsb_tiles", UID, ("s", 1)) is None, "the older entry should be gone"
        assert st.load("raw_lsb_tiles", UID, ("s", 2)) is not None
        assert len(_payload_files("raw_lsb_tiles")) == 1, "a kind not listed keeps exactly one"
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


def test_the_signature_naming_matches_the_predecessors_exactly_and_names_the_product_key():
    """The existing 782 MB of files depend on `repr` of the signature and a 20-byte digest.

    A different encoding would silently miss every one of them, so the recipe is pinned here; and
    a product key names the kind, the participant and that same signature digest. (Merged
    2026-10-05 with `test_a_product_key_names_the_kind_the_participant_and_the_signature`.)
    """
    import hashlib
    sig = ("a", 1, None, 2.5)
    assert st.signature_key(sig) == hashlib.blake2b(repr(sig).encode("utf8"),
                                                    digest_size=20).hexdigest()
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


def test_a_request_supplied_identifier_cannot_climb_out_of_the_cache_directory():
    """Open item 17, closed 2026-09-10. `ParticipantId` arrives from the request body, and when the
    database finds nobody by that name the raw string still became part of a file path. A real
    identifier is 32 hex characters; anything else is neutralised rather than trusted.

    Checked on the VALUE -- the path that comes back stays inside the kind's own directory and
    contains no separator -- rather than on the presence of a helper. And a real identifier must
    come through untouched, or every existing entry on disk would stop being found.
    """
    with _Sandbox():
        d = st.kind_dir("inputs")
        for hostile in ("../../etc/passwd", "a/b/c", "x.y.z", "..", "u;rm -rf", " "):
            stem = st._stem("inputs", hostile, ("sig",))
            assert stem is not None
            assert os.path.dirname(stem) == d, (hostile, stem)
            tail = os.path.basename(stem)
            assert "/" not in tail and ".." not in tail, (hostile, tail)
        # A genuine identifier is left exactly as it is.
        stem = st._stem("inputs", UID, ("sig",))
        assert f".{UID}." in os.path.basename(stem)
        # The legacy-named tiles keep their historical spelling for None, so nothing on disk is
        # orphaned; a hostile value under that naming is still neutralised.
        assert ".None." in os.path.basename(st._stem("raw_lsb_tiles", None, ("sig",)))
        assert ".." not in os.path.basename(st._stem("raw_lsb_tiles", "../x", ("sig",)))
        # And the sweep's own marker uses the SAME spelling, or a write would evict nothing.
        st.store("inputs", "../evil", ("s1",), {"v": 1}, writer="t", provenance=[])
        st.store("inputs", "../evil", ("s2",), {"v": 2}, writer="t", provenance=[])
        names = [n for n in os.listdir(d) if n.startswith("inputs.") and not n.endswith(".meta.json")]
        assert len(names) == 1, names
        assert all(".___evil." in n for n in names), names     # ".", ".", "/" -> three underscores


# --------------------------------------------------------------------------------------------
# how many current entries of one kind one participant may keep (was test_keep_newest.py)
#
# THE DEFECT THIS PINS WAS REAL AND SILENT. The store kept exactly one entry per participant per
# kind, replaced whole on every write. The band-by-length grid is keyed on the pain score among
# other things, so the six scores are six entries of one kind for one participant -- and writing
# the sixth deleted the other five. Measured on RCS08 on 2026-09-10 while building the every-score
# precompute (open item 7): six grids were computed and stored, each write reporting success, and
# ONE file was left on disk. The page then rebuilt a score that had just been "stored", in 8.9 s,
# and nothing on any page or in any log said why. Every test passed throughout, because no test
# asked what happened to the entry written before last. The first test below is the load-bearing
# one, written as the failing case: six entries written in turn, six expected back.
# --------------------------------------------------------------------------------------------

_SWEEP_KIND = "biomarker_band_sweep"   # a kind whose key carries the reader's own choice
_ONE_ONLY = "raw_lsb_tiles"            # a kind that must keep on keeping exactly one


def _write(kind, metric, payload=None):
    """One entry whose key differs only in the pain score, as the real grid's key does."""
    sig = (kind, "v1", UID, "tiles-key", "reports-key", metric)
    st.store(kind, UID, sig, payload if payload is not None else {"metric": metric},
             writer="biomarkers", provenance=[])
    return sig


def _payload_files(kind):
    d = st.kind_dir(kind, create=False)
    names = [n for n in (os.listdir(d) if d else []) if UID in n]
    return sorted(n for n in names if not n.endswith(".meta.json"))


def test_six_pain_scores_written_in_turn_are_all_still_readable():
    """THE LOAD-BEARING ONE. Six scores in, six scores back, each with its own value.

    Read back through the store's own `load` rather than by counting files, so this fails if the
    entries survive on disk but cannot be served -- which is the only thing a reader would notice.
    """
    metrics = ["nrs", "vas", "left_leg_vas", "back_vas", "mpq_sum", "composite_mpq_leftleg"]
    with _Sandbox():
        sigs = {m: _write(_SWEEP_KIND, m) for m in metrics}
        got = {m: st.load(_SWEEP_KIND, UID, sigs[m], consumer="biomarkers") for m in metrics}
    missing = [m for m in metrics if got[m] is None]
    assert not missing, f"these pain scores were evicted by later writes: {missing}"
    for m in metrics:
        assert got[m] == {"metric": m}, (m, got[m])


def test_the_limit_is_a_limit_and_the_oldest_entry_is_the_one_that_goes():
    """Keeping several is not keeping all of them: a store that only grows is not a cache
    (decision 28's reasoning for bounding Redis). The entry just written is always kept, and the
    oldest of the rest is the first to go."""
    limit = st.KEEP_NEWEST_BY_KIND[_SWEEP_KIND]
    with _Sandbox():
        sigs = [_write(_SWEEP_KIND, f"m{i:03d}") for i in range(limit + 4)]
        files = _payload_files(_SWEEP_KIND)
        assert len(files) == limit, (len(files), limit)
        # The newest `limit` are readable; everything older is gone.
        for sig in sigs[-limit:]:
            assert st.load(_SWEEP_KIND, UID, sig, consumer="biomarkers") is not None
        for sig in sigs[:-limit]:
            assert st.load(_SWEEP_KIND, UID, sig, consumer="biomarkers") is None


def test_an_entry_is_removed_whole_rather_than_leaving_a_sidecar_behind():
    """An entry is a payload plus a `.meta.json` sidecar, and the sidecar is the commit marker.
    A sweep that removed one and left the other would leave something that reads as an entry and
    has no content -- so the two are grouped by stem and go together."""
    limit = st.KEEP_NEWEST_BY_KIND[_SWEEP_KIND]
    with _Sandbox():
        for i in range(limit + 3):
            _write(_SWEEP_KIND, f"m{i:03d}")
        d = st.kind_dir(_SWEEP_KIND, create=False)
        names = [n for n in os.listdir(d) if UID in n]
        payloads = {n.rsplit(".", 1)[0] for n in names if not n.endswith(".meta.json")}
        sidecars = {n[:-len(".meta.json")] for n in names if n.endswith(".meta.json")}
        assert payloads == sidecars, (sorted(payloads ^ sidecars))
        assert len(payloads) == limit


def test_one_participants_scores_do_not_evict_anothers():
    """The sweep has always been scoped to one participant, and the limit must not quietly change
    that -- a limit of twelve counted across participants would evict a second patient's answers as
    soon as the first had a full set."""
    other = "1111111111111111111111111111aaaa"
    limit = st.KEEP_NEWEST_BY_KIND[_SWEEP_KIND]
    with _Sandbox():
        mine = [_write(_SWEEP_KIND, f"m{i:03d}") for i in range(limit)]
        for i in range(limit):
            sig = (_SWEEP_KIND, "v1", other, "tiles-key", "reports-key", f"m{i:03d}")
            st.store(_SWEEP_KIND, other, sig, {"metric": f"m{i:03d}"}, writer="biomarkers", provenance=[])
        for sig in mine:
            assert st.load(_SWEEP_KIND, UID, sig, consumer="biomarkers") is not None


def test_the_two_writer_kinds_keep_both_entries_and_a_third_key_evicts_the_oldest():
    """Two kinds each have two live writers under two keys, and under a limit of one they evicted
    each other: the assembled spectrum matrix (Biomarkers review B4, 2026-09-12: the page's
    rating-centred key and the daily ingest's legacy first-window key, evicting each other every
    day) and the Stim Optimizer response (2026-09-12: the page's two requests, plain and with the
    two-stage plan, so the second page load rebuilt what the first had just stored). Written in
    turn, both must still read back; a third key still evicts the oldest. (Merged 2026-10-05 from
    `test_the_spectrum_matrix_keeps_its_two_live_writers_entries` and
    `test_the_stim_optimizer_response_keeps_both_page_requests`.)"""
    cases = {
        "biomarker_psd_matrix": ("biomarkers", ("recordings", "reports-abc"), ("recordings", ""),
                                 ("recordings", "reports-def")),
        "stim_optimizer_response": ("stim_optimizer", ("inputs", "two_stage=0"),
                                    ("inputs", "two_stage=1"), ("inputs", "two_stage=1", "new")),
    }
    for kind, (writer, first, second, third) in cases.items():
        assert st.KEEP_NEWEST_BY_KIND.get(kind) == 2, kind
        with _Sandbox():
            sig_a, sig_b, sig_c = ((kind, "v1", UID) + x for x in (first, second, third))
            st.store(kind, UID, sig_a, {"which": "a"}, writer=writer, provenance=[])
            st.store(kind, UID, sig_b, {"which": "b"}, writer=writer, provenance=[])
            assert st.load(kind, UID, sig_a) == {"which": "a"}, f"{kind}: the second write evicted the first"
            assert st.load(kind, UID, sig_b) == {"which": "b"}, kind
            assert len(_payload_files(kind)) == 2, kind
            st.store(kind, UID, sig_c, {"which": "c"}, writer=writer, provenance=[])
            assert len(_payload_files(kind)) == 2, (kind, _payload_files(kind))
            assert st.load(kind, UID, sig_a) is None, f"{kind}: the oldest goes"
            assert st.load(kind, UID, sig_c) == {"which": "c"}, kind


def test_the_stability_answer_keeps_one_entry_per_grid_it_answers():
    """Found live on 2026-09-23: the heat maps' stability column read "not tested" on all 132 rows
    of every grid, while the background log said "stored 132 of 132 points" dozens of times that
    day. The stability answer is filed under the key of the grid it answers (the grid's own key is
    part of it), so each grid -- each pain score, at the reader's settings and at the daily
    defaults -- is its own entry of this kind. Under the default of one, every run deleted the run
    before it: one entry was left on disk, filed under whichever grid ran last, and every other
    grid, the page's own among them, found nothing. The decision-107 failure a fourth time.

    So the stability kind keeps as many entries as the grid kind it answers, and twelve answers
    written in turn all read back. The kind name is spelled out because the constant that holds it
    (`Biomarkers.bravo_service.STABILITY_GRID_KIND`) lives in a module that needs Django."""
    kind = "biomarker_band_stability_grid"
    assert st.KEEP_NEWEST_BY_KIND.get(kind, 1) >= st.KEEP_NEWEST_BY_KIND[_SWEEP_KIND], (
        "one stability answer per grid needs at least as many entries as there are grids")
    grid_keys = [f"grid-{m}-{s}" for s in ("reader", "daily")
                 for m in ("nrs", "vas", "left_leg_vas", "back_vas", "mpq_sum", "composite")]
    with _Sandbox():
        sigs = {}
        for g in grid_keys:
            sigs[g] = (kind, "v1", UID, g, 5.0, "points-132")
            st.store(kind, UID, sigs[g], {"points": [g]}, writer="biomarkers", provenance=[])
        lost = [g for g in grid_keys if st.load(kind, UID, sigs[g], consumer="biomarkers") is None]
    assert not lost, f"these grids' stability answers were evicted by later runs: {lost}"


def test_the_newest_entry_of_a_keep_group_outlives_twelve_later_writes():
    """Decision 317 found it live on 2026-09-26: all twelve grids kept for RCS08 were built under
    the Biomarkers page's settings, so the grid under the daily default settings -- the one the Stim
    Optimizer reads on every request -- had been evicted, and each of those requests rebuilt it
    (10.4-10.7 s). The limit sweeps by age alone, and a page used at other settings writes grids
    faster than the daily pass does.

    A writer may name a keep group in the sidecar (`extra["keep_group"]`). The newest entry of each
    group survives the sweep and does not count toward the limit; older entries of the same group
    compete by age as before, so the protection cannot make the store grow without bound."""
    limit = st.KEEP_NEWEST_BY_KIND[_SWEEP_KIND]
    with _Sandbox():
        old_default = (_SWEEP_KIND, "v1", UID, "tiles-key", "reports-OLD", "nrs-defaults")
        st.store(_SWEEP_KIND, UID, old_default, {"which": "old default"}, writer="biomarkers",
                 provenance=[], extra={"keep_group": "default_settings:nrs"})
        default = (_SWEEP_KIND, "v1", UID, "tiles-key", "reports-key", "nrs-defaults")
        st.store(_SWEEP_KIND, UID, default, {"which": "default"}, writer="biomarkers", provenance=[],
                 extra={"keep_group": "default_settings:nrs"})
        page = [_write(_SWEEP_KIND, f"page-{i:03d}") for i in range(limit + 3)]
        assert st.load(_SWEEP_KIND, UID, default, consumer="biomarkers") == {"which": "default"}, (
            "the newest daily-default grid was evicted by grids at other settings")
        assert st.load(_SWEEP_KIND, UID, old_default, consumer="biomarkers") is None, (
            "an older entry of the same group must still age out")
        for sig in page[-limit:]:
            assert st.load(_SWEEP_KIND, UID, sig, consumer="biomarkers") is not None, (
                "the protected entry must not count toward the limit")
        assert len(_payload_files(_SWEEP_KIND)) == limit + 1


def test_a_kind_that_keeps_one_ignores_keep_groups():
    """The protection applies only where a kind already keeps several; a 245 MB tile entry that
    named a keep group must still be replaced, never joined by a second copy."""
    with _Sandbox():
        first = (_ONE_ONLY, "v1", UID, "a")
        st.store(_ONE_ONLY, UID, first, {"m": "a"}, writer="biomarkers", provenance=[],
                 extra={"keep_group": "x"})
        _write(_ONE_ONLY, "b")
        assert len(_payload_files(_ONE_ONLY)) == 1
        assert st.load(_ONE_ONLY, UID, first, consumer="biomarkers") is None


# --------------------------------------------------------------------------------------------
# the "mapped" format: one saved copy read by every worker through the disk cache
# (was test_mapped_format.py)
#
# WHY (the PI, 2026-10-04: "go ahead and implement shared memory scheme"; measured 2026-10-04 in
# decision 414). Each of the 16 web workers held its own decoded copy of RCS08's recordings, about
# 6.7 GB a worker. Mapped, the arrays are read from one file on the volume: every worker's pages
# come from the same disk-cache pages, so the copy is held once (measured: 6,621 MB shared and
# 129 MB private per process, against 6,733 MB private for a process holding its own copy).
# Pinned, each on the values it produces: a nested payload comes back equal and backed by the
# file; each read is its own copy-on-write view (the loaders change recordings in place); a
# damaged file or another signature is a miss, never an error or a wrong answer; the format is
# used only when a caller asks for it.
# --------------------------------------------------------------------------------------------

_MAPPED_KIND = "therapy_settings"   # a raw kind: needs no writer, so the tests stay about the format
_MAPPED_SIG = ("mapped-test", 1)


def _payload():
    rng = np.random.default_rng(0)
    return {
        "recordings": [
            {"Data": rng.normal(size=(3, 5000)).astype(np.float32), "Time": np.arange(5000.0),
             "Channel": "ZERO_TWO_LEFT", "SamplingRate": 250, "Missing": None},
            {"Data": rng.integers(0, 9, size=1234, dtype=np.int16), "Flags": np.zeros(7, bool),
             "Nested": {"deep": [np.linspace(0, 1, 11), "text", 3.5]}},
        ],
        "table": pd.DataFrame({"t": np.arange(4.0), "power": [1.0, 2.0, np.nan, 4.0]}),
        "empty": np.zeros((0, 3)),
        "strided": np.arange(20.0)[::2],
    }


def _same(a, b):
    if isinstance(a, np.ndarray):
        return (isinstance(b, np.ndarray) and a.dtype == b.dtype and a.shape == b.shape
                and np.array_equal(a, b, equal_nan=a.dtype.kind == "f"))
    if isinstance(a, pd.DataFrame):
        return isinstance(b, pd.DataFrame) and a.equals(b)
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return type(a) is type(b) and len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _backed_by_a_map(a):
    base = a
    while getattr(base, "base", None) is not None:
        base = base.base
        if isinstance(base, mmap.mmap):
            return True
        if isinstance(base, memoryview) and isinstance(base.obj, mmap.mmap):
            return True
    return False


def test_a_mapped_entry_reads_back_equal_backed_by_its_file_aligned_and_only_under_its_signature():
    """A nested payload comes back equal, every array with its own type and shape, by key and as
    the newest entry; the arrays are read from the file, not copied into the process; every array
    starts on a 64-byte boundary; another signature is a miss. (Merged 2026-10-05 from
    `test_a_nested_payload_round_trips_exactly`, `test_the_arrays_are_read_from_the_file_not_copied`,
    `test_every_array_starts_on_a_64_byte_boundary`, `test_the_newest_entry_is_read_mapped_too` and
    `test_another_signature_is_a_miss`, which each stored the same payload.)"""
    with _Sandbox():
        p = _payload()
        assert st.store(_MAPPED_KIND, UID, _MAPPED_SIG, p, fmt="mapped") is True
        got = st.load(_MAPPED_KIND, UID, _MAPPED_SIG)
        assert got is not None and _same(p, got)
        assert st.read_stamp(_MAPPED_KIND, UID, _MAPPED_SIG)["format"] == "mapped"
        assert _backed_by_a_map(got["recordings"][0]["Data"])
        assert _backed_by_a_map(got["recordings"][1]["Nested"]["deep"][0])
        for arr in (got["recordings"][0]["Data"], got["recordings"][0]["Time"],
                    got["recordings"][1]["Data"]):
            assert arr.__array_interface__["data"][0] % 64 == 0
        newest, stamp = st.load_newest(_MAPPED_KIND, UID)
        assert stamp["format"] == "mapped" and _same(_payload(), newest), "the newest entry"
        assert st.load(_MAPPED_KIND, UID, ("mapped-test", 2)) is None, "another signature"


def test_each_read_is_its_own_copy_and_the_file_is_never_written():
    with _Sandbox():
        st.store(_MAPPED_KIND, UID, _MAPPED_SIG, _payload(), fmt="mapped")
        path = st._existing_payload_path(st._stem(_MAPPED_KIND, UID, _MAPPED_SIG))
        before = open(path, "rb").read()
        a = st.load(_MAPPED_KIND, UID, _MAPPED_SIG)
        b = st.load(_MAPPED_KIND, UID, _MAPPED_SIG)
        a["recordings"][0]["Data"][:] = -1.0                      # in place, as a loader may do
        a["recordings"][0]["Channel"] = "CHANGED"
        assert float(b["recordings"][0]["Data"][0, 0]) != -1.0
        assert b["recordings"][0]["Channel"] == "ZERO_TWO_LEFT"
        c = st.load(_MAPPED_KIND, UID, _MAPPED_SIG)
        assert _same(_payload(), c), "a later read sees the stored values"
        assert open(path, "rb").read() == before


def test_a_damaged_file_is_a_miss_and_is_removed():
    with _Sandbox():
        st.store(_MAPPED_KIND, UID, _MAPPED_SIG, _payload(), fmt="mapped")
        path = st._existing_payload_path(st._stem(_MAPPED_KIND, UID, _MAPPED_SIG))
        with open(path, "r+b") as fh:
            fh.truncate(100)
        assert st.load(_MAPPED_KIND, UID, _MAPPED_SIG) is None
        assert not os.path.exists(path)


def test_the_format_is_used_only_when_asked_for():
    assert st.choose_format(_payload()) == "pickle"
    assert st.choose_format({"a": np.zeros(3)}) == "npz"
    with _Sandbox():
        st.store(_MAPPED_KIND, UID, _MAPPED_SIG, _payload())
        assert st.read_stamp(_MAPPED_KIND, UID, _MAPPED_SIG)["format"] == "pickle"


def test_a_file_that_cannot_be_mapped_is_a_miss_and_is_kept():
    """Running out of file handles is not a damaged entry: the file stays for the next read."""
    import mmap as _mmap_mod
    with _Sandbox():
        st.store(_MAPPED_KIND, UID, _MAPPED_SIG, _payload(), fmt="mapped")
        path = st._existing_payload_path(st._stem(_MAPPED_KIND, UID, _MAPPED_SIG))
        real = _mmap_mod.mmap

        def refuse(*a, **k):
            raise OSError(24, "Too many open files")
        _mmap_mod.mmap = refuse
        try:
            assert st.load(_MAPPED_KIND, UID, _MAPPED_SIG) is None
            assert st.load_newest(_MAPPED_KIND, UID)[0] is None
        finally:
            _mmap_mod.mmap = real
        assert os.path.exists(path)
        assert st.load(_MAPPED_KIND, UID, _MAPPED_SIG) is not None
